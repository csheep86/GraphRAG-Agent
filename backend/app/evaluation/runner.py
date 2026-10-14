"""评测**执行器**（E2）：offline / live 双模式，产出 :class:`CriterionResult` 列表。

**两种模式的分工（刻意不对称）**：

- ``offline``（**默认**）——**不依赖 LLM / 网络 / Neo4j**，CI 可跑、断网可跑。
  它做的事是：**跑通管道**（数据集加载 → 指标函数 → 报告格式 → 幂等），
  以及把**依赖真机**的判据如实标成 ``UNKNOWN`` / ``BLOCKED``。
  ⚠️ **offline 不产出任何判据数字**——断网跑出来的"召回 0.8"必然是假的。
  口径演练走报告里的 ``self_test`` 块（**显式标 `synthetic: true`**，与判据分区存放）。
- ``live``——打真实 HTTP（``POST /api/v1/agent/query`` 等），只对**链路已实现**的判据出数字。

**与 P5-M6 的交接面**：依赖 M6 的判据在这里注册为 :class:`PlaceholderEvaluator`，
M6 落地后**只替换 evaluator**，不动指标函数、不改报告格式。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from app.db.models import COST_STAGE_EXTRACTION
from app.evaluation.affiliation import DEFAULT_NON_MEMBER_PREFIXES
from app.evaluation.corpus_layer import (
    LAYER_ALGORITHM,
    LAYER_END_TO_END,
    detect_corpus_layer,
)
from app.evaluation.criteria import (
    THRESHOLD_CALIBRATED,
    THRESHOLD_ENV_OVERRIDE,
    THRESHOLD_PROVISIONAL,
    CriterionResult,
    CriterionStatus,
    PlaceholderEvaluator,
    Provenance,
    Verdict,
    judge,
    register_criterion,
    resolve_status,
)
from app.evaluation.dataset import (
    DEFAULT_AFFILIATION_VERSION,
    dataset_versions,
    load_affiliation_gold,
    load_affiliation_meta,
    load_fixture_baseline,
    load_manifest,
    load_multihop_set,
    load_question_set,
)
from app.evaluation.metrics import (
    COST_RATIO_SIGNIFICANT,
    UNIT_COST_RATIO,
    UNIT_TOKEN_PER_DOC,
    AnswerRecord,
    CitationRef,
    Finding,
    accuracy,
    citation_coverage,
    findings_false_positive_rate,
    findings_recall,
    graph_gain,
)
from app.evaluation.stats import (
    DEFAULT_ALPHA,
    clopper_pearson_lower,
    clopper_pearson_upper,
)

#: 判据名（**唯一真源**；与矩阵 §5.1 的 C1–C3 对应）。
C_MULTIHOP = "multihop_accuracy"
C_CITATION = "c2_c_citation_coverage"
C_GAIN = "c1_graph_gain"
C_RECALL = "c2_a_hidden_relation_recall"
C_FPR = "c2_b_false_positive_rate"
C_COST = "c3_a_single_doc_cost"
C_COST_RATIO = "c3_b_incremental_cost_ratio"
#: **L8 / L10-A6 配套第 2 条**：拒答误伤（Sprint 6 §5.3 验收第 1 条「拒答 0 误伤」）。
#: 刻意**不**叫 ``c2_d_*``——它不属于矩阵 §5.1 的 C1–C3 编号，编造编号会让人
#: 误以为矩阵里有这一条；它锚定的是 Sprint 6 §5.3 的验收条款。
C_REFUSAL = "refusal_false_refusal"

#: **C1 的阈值（10%）**——阈值**未校准**（TBD-7 未收敛 + 基线非终局）
#: ⇒ 即便达标也只能给 ``PASS(provisional)``，**不给裸 PASS**（§5.2 第 3 条）。
C1_GAIN_THRESHOLD = 0.10

#: ⚠️ **本常量已删除（P6-D，2026-10-05）**：原先写死 ``QSET_CORPUS_LAYER = "L1"``，
#: 意味着即便链路已经打通到 L2，报告**照样标 L1**；反之改一行常量就能把 L1 说成 L2，
#: 而没有任何机器证据能证伪 ⇒ 属**假绿入口**。
#: 现改为按图内实测判定：:func:`app.evaluation.corpus_layer.detect_corpus_layer`。

ALL_CRITERIA = (
    C_GAIN,
    C_MULTIHOP,
    C_RECALL,
    C_FPR,
    C_CITATION,
    #: **L8**：拒答误伤紧跟 C2-c —— 它俩同源，且**不许互相顶替**
    #: （摆在一起才看得见"1.00 旁边还挂着 1 条误伤"）
    C_REFUSAL,
    C_COST,
    C_COST_RATIO,
)

BASE_URL = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:8002")
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"


@dataclass(frozen=True)
class RunnerContext:
    """一次评测运行的上下文（**全部显式传入**，不隐式读配置）。"""

    mode: Literal["offline", "live"]
    git_hash: str
    base_url: str = BASE_URL
    org_id: str = ORG_ID
    actor_id: str = ACTOR_ID
    #: 人工判分：``{题号: correct}``（A3：脚本不自动判分）。
    judgements: dict[int, bool] | None = None
    judged_by: str = "architect"
    #: **A8 可复现（P7-K）**：判分所**绑定**的那一趟坐标（由图侧判分表自证），
    #: 出数前用它验环境 + 验答案；``None`` ⇒ 无法证明「这批答案就是人判过的那批」。
    judgement_basis: Any | None = None
    #: 同上，**基线侧**用另一张判分表 ⇒ 也必须有自己的 basis（A1 裁决 3）。
    baseline_judgement_basis: Any | None = None
    #: **A1（2026-10-05）**：**基线侧**的独立判分（同一份 rubric、同一批改）。
    #: 为什么必须是**另一份**：两侧的答案由不同检索产出，同一题在两侧对错可以不同
    #: ⇒ 共用一张判分表等于替基线"预设答案"，那会让增益失去意义（L10-A1 条款 3）。
    baseline_judgements: dict[int, bool] | None = None
    #: **A8（2026-10-04）**：C2-a / C2-b 用哪版 gold 语料
    #: （``v1`` = 8/60/30/9 手工语料；``v2`` = 200/500/100/20 扩标语料）。
    #: **刻意默认 v1**：换语料会换结论 ⇒ 必须显式选，不能靠默认值悄悄换。
    gold_version: str = DEFAULT_AFFILIATION_VERSION


# ---------------------------------------------------------------------------
# 真机访问（live 模式）
# ---------------------------------------------------------------------------


def ask(
    question: str, *, ctx: RunnerContext, scope: str = "cross_doc"
) -> dict[str, Any]:
    """打 ``POST /api/v1/agent/query``（与既有 `eval_controlled_qset.py::ask` 同形状）。"""
    payload = json.dumps({"question": question, "scope": scope}).encode()
    request = urllib.request.Request(  # noqa: S310 - 固定本地地址
        f"{ctx.base_url}/api/v1/agent/query",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Org-Id": ctx.org_id,
            "X-Actor-Id": ctx.actor_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))  # type: ignore[no-any-return]


def ask_safe(
    question: str, *, ctx: RunnerContext
) -> tuple[dict[str, Any] | None, str | None]:
    """同 :func:`ask`，但**不抛异常**：返回 ``(响应, 错误)``。

    为什么必须吞掉异常（**2026-10-03 真跑学到的**）：后端链路不可用时（PG 无 ready
    版本 ⇒ `agent/query` 恒 501），抛栈会让脚本直接崩 ⇒ 一份报告都拿不到，
    「链路不可用」也就无法被如实标成 ``UNKNOWN``——那正是"没测出来"最容易被写成
    "没这事"的入口。判据脚本**必须**跑完并给出结论。
    """
    try:
        return ask(question, ctx=ctx), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - 评估器需跑完全集再给结论
        return None, repr(exc)


def _to_answer(
    response: dict[str, Any], *, correct: bool | None, judged_by: str | None
) -> AnswerRecord:
    """把 M3 响应投影成 :class:`AnswerRecord`。

    ``has_span``：``char_end > char_offset`` ⇒ 有**非退化**区间（回退档 = 整段引用，
    区间退化或 `char_end == char_offset` ⇒ 不算可回溯 span，见 A6）。
    """
    citations = tuple(
        CitationRef(
            chunk_id=str(item.get("chunk_id") or ""),
            has_span=int(item.get("char_end") or 0) > int(item.get("char_offset") or 0),
        )
        for item in (response.get("citations") or [])
    )
    return AnswerRecord(
        refused=bool(response.get("refused")),
        citations=citations,
        correct=correct,
        judged_by=judged_by,
        #: **判分留证**（P6-F）：不参与任何判据计算，只为了让判分人对着原文判。
        answer_text=str(response.get("answer") or ""),
    )


def _provenance(
    ctx: RunnerContext, *, dataset_version: str, **extra: Any
) -> Provenance:
    manifest = load_manifest()
    return Provenance(
        dataset_version=dataset_version,
        mode=ctx.mode,
        git_hash=ctx.git_hash,
        kg_version=str(extra.get("kg_version") or "attendance-demo-v1"),
        #: 语料**按判据分**：C2-a / C2-b 跑的是 ``demo/affiliation`` 合成语料，
        #: 与问答类判据的 ``demo/attendance`` 不是同一份——写错了归因就错了。
        corpus=str(extra.get("corpus") or "demo/attendance（仿真演示语料）"),
        corpus_layer=extra.get("corpus_layer"),
        rubric=str(manifest.get("rubric", {}).get("id", "rubric-v1")),
        #: **P7-K（出口判据 5）**：环境坐标进**归因**而不是只进 detail——
        #: 写在 detail 里可以被读者忽略，写进归因 ⇒ 脱离坐标无法引用这个数字。
        pool_fingerprint=extra.get("pool_fingerprint"),
        generation_model=extra.get("generation_model"),
        top_k=extra.get("top_k"),
        notes=extra.get("notes"),
    )


# ---------------------------------------------------------------------------
# 判据执行器
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _QaRun:
    """一次问答全集的**结果快照**（A6 / L8：C2-c 与拒答误伤**同源**）。

    为什么要它：拒答误伤立独立判据后，若两个判据**各跑一遍** M3 问答链路，
    就要付**两倍 LLM 调用**，且两遍的拒答结果可能不一致（LLM 有抖动）
    ⇒ 同一批答案算出两个相互矛盾的结论。既然是同源判据，就**只跑一遍**。
    """

    answers: tuple[AnswerRecord, ...]
    #: **A1（2026-10-05）**：与 :attr:`answers` **逐位对齐**的题号。
    #: 为什么必须记：成功后才会 append answer，失败题被跳过 ⇒ 光有 ``answers``
    #: 无法把人工判分（``{题号: correct}``）对回具体那一题。
    answered_indices: tuple[int, ...]
    #: **误伤**：本该作答却拒答（`should_refuse=False` 却 `refused=True`）——L8 的 Q8 属这一类
    false_refusals: tuple[dict[str, Any], ...]
    #: **漏拒**：本该拒答却作答（该拒没拒）——**不进**拒答误伤判据（方向不同，见 L8）
    missed_refusals: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, Any], ...]
    kg_versions: tuple[str, ...]
    asked: int


#: 一次运行内**只跑一遍**问答全集（同源判据共享；键含 mode，避免离线/在线串味）。
_QA_CACHE: dict[str, _QaRun] = {}


def _qa_run(runner_ctx: RunnerContext) -> _QaRun:
    """跑一遍受控题集（**不抛异常**），结果进缓存供 C2-c 与拒答误伤共用。"""
    if runner_ctx.mode in _QA_CACHE:
        return _QA_CACHE[runner_ctx.mode]

    questions = load_question_set()
    answers: list[AnswerRecord] = []
    answered_indices: list[int] = []
    false_refusals: list[dict[str, Any]] = []
    missed_refusals: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    kg_versions: set[str] = set()
    for item in questions:
        response, error = ask_safe(item.question, ctx=runner_ctx)
        if response is None:
            failures.append(
                {"index": item.index, "error": error, "question": item.question}
            )
            continue
        kg_versions.add(str(response.get("kg_version")))
        answers.append(_to_answer(response, correct=None, judged_by=None))
        answered_indices.append(item.index)
        actual = bool(response.get("refused"))
        if actual != item.should_refuse:
            mismatch = {
                "index": item.index,
                "expected": item.should_refuse,
                "actual": actual,
                "question": item.question,
            }
            #: **方向必须分家**："不该拒却拒"（误伤）与"该拒没拒"（漏拒）后果不同
            #: ——误伤直接吃掉 C2-c 的分子，漏拒是放行；混在一个列表里 ⇒ 判据值失真。
            if actual and not item.should_refuse:
                false_refusals.append(mismatch)
            else:
                missed_refusals.append(mismatch)

    snapshot = _QaRun(
        answers=tuple(answers),
        answered_indices=tuple(answered_indices),
        false_refusals=tuple(false_refusals),
        missed_refusals=tuple(missed_refusals),
        failures=tuple(failures),
        kg_versions=tuple(sorted(kg_versions)),
        asked=len(questions),
    )
    _QA_CACHE[runner_ctx.mode] = snapshot
    return snapshot


def _qa_unavailable(
    criterion: str, runner_ctx: RunnerContext, snapshot: _QaRun
) -> CriterionResult:
    """问答链路不可用 ⇒ **UNKNOWN + value=None**（0 会被读成"零误伤 / 零覆盖"）。"""
    first = snapshot.failures[0]["error"] if snapshot.failures else "无响应"
    return CriterionResult(
        criterion=criterion,
        status=CriterionStatus.UNKNOWN,
        value=None,
        provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v4"),
        blocked_by=(
            f"链路不可用：{len(snapshot.failures)}/{snapshot.asked} 题请求失败"
            f"（首错：{first}）——常见原因：① 后端未起或 EVAL_BASE_URL 不对；"
            "② PG 无 ready 的 kg_version（演示数据未重建）"
        ),
        verdict=Verdict.INDETERMINATE,
        detail={"failures": list(snapshot.failures), "asked": snapshot.asked},
    )


def eval_citation_coverage(ctx: dict[str, Any]) -> CriterionResult:
    """**C2-c 引用覆盖率**（硬约束 1.00）：真跑 M3 问答链路。"""
    runner_ctx: RunnerContext = ctx["ctx"]
    if runner_ctx.mode != "live":
        return CriterionResult(
            criterion=C_CITATION,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v4"),
            blocked_by="需 live 模式（POST /api/v1/agent/query）；offline 不产出判据数字",
            verdict=Verdict.INDETERMINATE,
        )

    snapshot = _qa_run(runner_ctx)
    answers = snapshot.answers
    refusals = list(snapshot.false_refusals) + list(snapshot.missed_refusals)
    failures = list(snapshot.failures)
    kg_versions = set(snapshot.kg_versions)

    if not answers:
        return _qa_unavailable(C_CITATION, runner_ctx, snapshot)

    #: **判据值 = 排除拒答档**（L10-A6 裁决，不改行为）
    metric = citation_coverage(tuple(answers), include_refused=False)
    strict = citation_coverage(tuple(answers), include_refused=False, require_span=True)
    #: **A6 配套第 1 条：含拒答那一档必须同时输出**（此前两处都传 False ⇒ 这档从未露过面）
    with_refused = citation_coverage(tuple(answers), include_refused=True)
    strict_with_refused = citation_coverage(
        tuple(answers), include_refused=True, require_span=True
    )
    status, reason = resolve_status(
        link_ready=True,
        dataset_ready=True,
        rubric_defined=True,
        corpus_is_final=False,  # 演示语料 ≠ 终局语料
    )
    return CriterionResult(
        criterion=C_CITATION,
        status=status if metric.value is not None else CriterionStatus.UNKNOWN,
        value=metric.value,
        provenance=_provenance(
            runner_ctx,
            dataset_version="controlled-qset-v4",
            kg_version=", ".join(sorted(kg_versions)),
            corpus_layer=_detect_layer(kg_versions, runner_ctx.org_id),
            notes=reason,
        ),
        blocked_by=None if metric.value is not None else (metric.reason or "无分母"),
        threshold=1.0,
        threshold_source="calibrated",  # 1.00 是矩阵硬约束，非 provisional
        verdict=judge(metric.value, threshold=1.0, threshold_source="calibrated"),
        detail={
            "answered": sum(1 for a in answers if not a.refused),
            "refused": sum(1 for a in answers if a.refused),
            "refusal_mismatches": refusals,
            #: ⚠️ **口径标注**：value 走的是**排除拒答**档；含拒答档在这里**并列展示**，
            #: 但**不是**判据值（L10-A6：含拒答 ⇒ 11/14 = 0.786 ⇒ 触发 F3 / NO-GO）。
            "coverage_basis": "exclude_refused（判据值口径；L10-A6 裁决）",
            "coverage_including_refused": with_refused.value,
            "coverage_require_span": strict.value,
            "coverage_require_span_including_refused": strict_with_refused.value,
            "false_refusals": list(snapshot.false_refusals),
            "missed_refusals": list(snapshot.missed_refusals),
            "request_failures": failures,
            "kg_versions": sorted(kg_versions),
        },
    )


def eval_refusal_false_refusal(ctx: dict[str, Any]) -> CriterionResult:
    """**拒答误伤**（L8 / Sprint 6 §5.3 验收第 1 条「拒答 0 误伤」）= **误伤条数**，阈值 **0**。

    为什么必须独立成判据（L10-A6 配套第 2 条）：

    - **误伤会直接吃掉 C2-c 的分子**——一条本该作答的题被拒答，它就没有引用，
      于是 C2-c（排除拒答口径）**看不见它**；
    - 反过来若把拒答塞进 C2-c 分母 ⇒ 11/14 = 0.786 ⇒ **触发 F3 / MVP NO-GO**，
      且会**诱导"为了让覆盖率绿而放宽拒答判定"**（该拒的不拒，**比误伤更糟**）。

    ⇒ 两条判据**各管一件事、不许互相顶替**：C2-c 管"给出的答案能不能回溯"，
    本判据管"该给的有没有给"。

    **只数误伤**（`should_refuse=False` 却拒答），**不数漏拒**（该拒没拒）——
    那是另一个方向、另一个后果，混进来会让本判据的 0 阈值失去意义。

    ⚠️ **当前实测 = 1 条（Q8）⇒ FAIL**，归 P6 必修（**本批只立判据、不修链路**）。
    """
    runner_ctx: RunnerContext = ctx["ctx"]
    if runner_ctx.mode != "live":
        return CriterionResult(
            criterion=C_REFUSAL,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v4"),
            blocked_by="需 live 模式（POST /api/v1/agent/query）；offline 不产出判据数字",
            verdict=Verdict.INDETERMINATE,
        )

    snapshot = _qa_run(runner_ctx)
    if not snapshot.answers:
        return _qa_unavailable(C_REFUSAL, runner_ctx, snapshot)

    false_count = len(snapshot.false_refusals)
    status, reason = resolve_status(
        link_ready=True,
        dataset_ready=True,
        rubric_defined=True,
        corpus_is_final=False,
    )
    return CriterionResult(
        criterion=C_REFUSAL,
        status=status,
        value=float(false_count),
        unit="条（误伤数）",
        provenance=_provenance(
            runner_ctx,
            dataset_version="controlled-qset-v4",
            kg_version=", ".join(snapshot.kg_versions),
            corpus_layer=_detect_layer(snapshot.kg_versions, runner_ctx.org_id),
            notes="; ".join(
                x
                for x in (
                    reason,
                    "口径：should_refuse=False 却拒答 ⇒ 误伤；"
                    "Sprint 6 §5.3 验收第 1 条「拒答 0 误伤」",
                )
                if x
            ),
        ),
        threshold=0.0,
        threshold_source=THRESHOLD_CALIBRATED,  # 「0 误伤」是验收条款，非 provisional
        verdict=judge(
            float(false_count),
            threshold=0.0,
            threshold_source=THRESHOLD_CALIBRATED,
            higher_is_better=False,
        ),
        detail={
            "asked": snapshot.asked,
            "answered": sum(1 for a in snapshot.answers if not a.refused),
            "refused": sum(1 for a in snapshot.answers if a.refused),
            "false_refusals": list(snapshot.false_refusals),
            "missed_refusals": list(snapshot.missed_refusals),
            "note": (
                "与 C2-c **同源共用一遍问答**（不重复付 LLM 调用）；"
                "C2-c 的 1.00 **不含**拒答题，误伤在这里**单独计**"
            ),
        },
    )


def eval_multihop_accuracy(ctx: dict[str, Any]) -> CriterionResult:
    """**多跳答对率**：真跑问答 + **人工判分**（A3）。"""
    runner_ctx: RunnerContext = ctx["ctx"]
    if runner_ctx.mode != "live":
        return CriterionResult(
            criterion=C_MULTIHOP,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="gold-multihop-v1"),
            blocked_by="需 live 模式；offline 不产出判据数字",
            verdict=Verdict.INDETERMINATE,
        )

    items = load_multihop_set()
    judgements = runner_ctx.judgements or {}
    #: gold 里已存的 correct（P6-T 写回的那份）**保留为兜底**，但它只有在后面
    #: 两道门都通过之后才允许被套用（P7-K D5：答案漂移时不许吃这本老账）。
    gold_correct = {item.index: item.correct for item in items}
    answers: list[AnswerRecord] = []
    indices: list[int] = []
    failures: list[dict[str, Any]] = []
    for item in items:
        response, error = ask_safe(item.question, ctx=runner_ctx)
        if response is None:
            failures.append(
                {"index": item.index, "error": error, "question": item.question}
            )
            continue
        answers.append(_to_answer(response, correct=None, judged_by=None))
        indices.append(item.index)

    if not answers:
        first = failures[0]["error"] if failures else "无响应"
        return CriterionResult(
            criterion=C_MULTIHOP,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="gold-multihop-v1"),
            blocked_by=f"链路不可用：{len(failures)}/{len(items)} 题请求失败（首错：{first}）",
            verdict=Verdict.INDETERMINATE,
            detail={"failures": failures, "asked": len(items)},
        )

    #: **P7-K 门 ①——环境自检**：本次链路是否还站在判分当时的那个环境上。
    #: 放在**出数之前**而不是之后：环境不对时再去跑 6 道题只是白烧一次 LLM。
    coords = _live_env_coords(runner_ctx)
    blocked, gate_detail = _reproducibility_gate(
        runner_ctx.judgement_basis,
        dataset_version="gold-multihop-v1",
        git_hash=runner_ctx.git_hash,
        pool_fingerprint=coords[0] if coords else None,
        top_k=coords[1] if coords else None,
        generation_model=coords[2] if coords else None,
    )
    if blocked is not None:
        return _blocked_result(
            C_MULTIHOP,
            runner_ctx,
            dataset_version="gold-multihop-v1",
            blocked_by=blocked,
            threshold=0.80,
            threshold_source="calibrated",
            asked=len(items),
            note=(
                "环境不可复现 ⇒ 判分表不得复用：要么回到原环境重跑，"
                "要么只重判差异题后再出数（重 number 跑不为「让数字好看」）"
            ),
            answer_texts=_awaiting_judgement(tuple(answers), tuple(indices)),
            **gate_detail,
        )

    #: **P7-K 门 ②——答案比对**：拒答 / 原文漂移 ⇒ 旧判分不再适用于这批答案。
    stale = _answer_gate(runner_ctx.judgement_basis, indices, answers)
    if stale:
        return _blocked_result(
            C_MULTIHOP,
            runner_ctx,
            dataset_version="gold-multihop-v1",
            blocked_by=(
                f"判分已过期：{len(stale)}/{len(answers)} 题的本次答案与判分材料不一致"
                "（拒答或答案原文漂移）⇒ 旧判分不得套用（P6-T canary 的形状）"
            ),
            threshold=0.80,
            threshold_source="calibrated",
            asked=len(items),
            stale_answers=stale,
            answer_texts=_awaiting_judgement(tuple(answers), tuple(indices)),
        )

    judged = _apply_judgements(
        tuple(indices),
        tuple(answers),
        judgements,
        gold_correct,
        runner_ctx.judged_by,
    )
    metric = accuracy(judged)
    if metric.value is None:
        return CriterionResult(
            criterion=C_MULTIHOP,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="gold-multihop-v1"),
            blocked_by=(
                "A3：无已判分答案（请用 --judgements 提供人工判分，"
                "或把判分写回 gold-multihop-v1.json 的 correct 字段）；脚本不自动判分"
            ),
            verdict=Verdict.INDETERMINATE,
            detail={
                "asked": len(items),
                "judged": 0,
                #: **P6-T（D3）**：多跳此前**只报数字不报原文** ⇒ 人拿着它无从判分。
                #: 与 C1 同一条理由（A3：人不该盲判）⇒ 缺判分时把答案原文一并摊开。
                "answer_texts": _awaiting_judgement(tuple(answers), tuple(indices)),
            },
        )
    status, reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True, corpus_is_final=False
    )
    return CriterionResult(
        criterion=C_MULTIHOP,
        status=status,
        value=metric.value,
        provenance=_provenance(
            runner_ctx,
            dataset_version="gold-multihop-v1",
            pool_fingerprint=coords[0] if coords else None,
            generation_model=coords[2] if coords else None,
            top_k=coords[1] if coords else None,
            notes=reason,
        ),
        threshold=0.80,
        threshold_source="calibrated",  # 0.80 来自矩阵，非 provisional
        verdict=judge(metric.value, threshold=0.80, threshold_source="calibrated"),
        detail={
            "asked": len(items),
            "judged": sum(1 for a in judged if a.correct is not None),
            "judged_by": runner_ctx.judged_by,
            #: **P6-T（D2）**：与 C1 同一条留证要求——出数这一趟的答案原文**必须落盘**，
            #: 否则无从证明「人判的那 6 条」==「出数这一趟的 6 条」（判据 4）。
            "answer_texts": _awaiting_judgement(tuple(answers), tuple(indices)),
        },
    )


def _affiliation_blocked_by(
    version: str = DEFAULT_AFFILIATION_VERSION,
) -> tuple[str, bool]:
    """C2-a / C2-b 的阻塞原因（``("", True)`` = 不阻塞，可出数）。

    **2026-10-03 已核对**：真机样本（``AffiliationService.detect``）确认
    gold 与疑点输出的 id 空间**同构**（图节点 id），逐组比对通过
    ⇒ 数据文件置 ``verified_against_live_output=true`` ⇒ 本函数不再阻塞。

    保留本函数的原因：**未核对就比对 = 全不命中 = 召回被读成 0**，
    会误触发反证 F2。这条闸不能拆，只能由数据文件的标志位放行。
    """
    space = load_affiliation_meta(version).get("entity_id_space", {})
    verified = bool(space.get("verified_against_live_output", False))
    if not verified:
        return (
            f"gold-affiliation-{version} 的实体 id 空间({space.get('space')})"
            "尚未与真机疑点输出核对（MANIFEST 登记）⇒ "
            "不比对就不出数（避免 0 命中被读成召回为 0）",
            False,
        )
    return "", True


#: 一次运行内**只跑一次** M4 检测（C2-a / C2-b 同源；跑两遍既浪费也可能不一致）。
_DETECTION_CACHE: dict[tuple[str, str, str], tuple[Finding, ...]] = {}


def _detect_findings(
    runner_ctx: RunnerContext,
) -> tuple[tuple[Finding, ...] | None, str | None]:
    """同 :func:`ask_safe` 的口径：**不抛异常**，返回 ``(疑点, 错误)``。"""
    meta = load_affiliation_meta(runner_ctx.gold_version)
    kg_version = str(meta["kg_version"])
    org_id = str(meta["org_id"])
    key = (runner_ctx.mode, kg_version, org_id)
    if key in _DETECTION_CACHE:
        return _DETECTION_CACHE[key], None
    try:
        from uuid import UUID

        from app.evaluation.affiliation import findings_from_suspicions
        from app.services.kg import AffiliationService

        space = meta.get("entity_id_space", {})
        prefixes = tuple(space.get("non_member_prefixes") or ())
        suspicions = AffiliationService().detect(
            kg_version=kg_version, org_id=UUID(org_id), limit=500
        )
        findings = findings_from_suspicions(
            suspicions, non_member_prefixes=prefixes or DEFAULT_NON_MEMBER_PREFIXES
        )
    except Exception as exc:  # noqa: BLE001 - 判据脚本必须跑完并给结论
        return None, repr(exc)
    _DETECTION_CACHE[key] = findings
    return findings, None


def _affiliation_results(
    runner_ctx: RunnerContext,
) -> tuple[CriterionResult, CriterionResult]:
    """C2-a 召回 + C2-b 误报（**一次检测，两个指标**）。"""
    version = runner_ctx.gold_version
    gold = load_affiliation_gold(version)
    meta = load_affiliation_meta(version)

    if runner_ctx.mode != "live":
        blocked = "需 live 模式（M4 检测读 Neo4j 图谱）；offline 不产出判据数字"
        return (
            _unknown(C_RECALL, runner_ctx, blocked),
            _unknown(C_FPR, runner_ctx, blocked),
        )

    findings, error = _detect_findings(runner_ctx)
    if findings is None:
        blocked = f"M4 检测不可用：{error}"
        return (
            _unknown(C_RECALL, runner_ctx, blocked),
            _unknown(C_FPR, runner_ctx, blocked),
        )

    recall = findings_recall(gold, findings)
    fpr = findings_false_positive_rate(findings, gold)

    #: **A8 统计口径**：光有点估计判不了达标——9/9 的 1.00，下界只有 0.717 < 0.80。
    #: 故把 ``n`` 与 **95% 单侧置信界**一并算出，并**用界判定**
    #: （C2-a 用下界；C2-b 用上界）。
    hit = int(recall.options.get("hit", 0) or 0)
    n_gold = int(recall.options.get("n", len(gold)) or len(gold))
    spurious = int(fpr.options.get("spurious", 0) or 0)
    n_detected = int(fpr.options.get("n", len(findings)) or len(findings))
    recall_bound = clopper_pearson_lower(hit, n_gold)
    fpr_bound = clopper_pearson_upper(spurious, n_detected)
    #: 语料层（A8 裁决 4）：v1/v2 都是 **L1 算法层** ⇒ 不得说成端到端结论。
    corpus_layer = str(meta.get("source", {}).get("corpus_layer") or "L1")
    corpus_desc = str(
        meta.get("source", {}).get("corpus")
        or "demo/affiliation（合成演示语料，9 组植入）"
    )

    status, reason = resolve_status(
        link_ready=True,
        dataset_ready=True,
        rubric_defined=True,
        #: v2 = spec 规模（200/500/100/20）⇒ 语料**终局**；v1 仍是非终局。
        corpus_is_final=(version == "v2"),
    )
    if version == "v1":
        caveat = (
            "A8：语料仍是 8/60/30/9（spec 要 200/500/100/20）⇒ 规模不足以判达标；"
            f"本次 {hit}/{n_gold} 的 95% 单侧下界 = {recall_bound:.4f}，"
            f"误报 {spurious}/{n_detected} 的上界 = {fpr_bound:.4f}"
            " ⇒ 达标也只记 PASS(provisional)，不作 spec 验收结论"
        )
    else:
        caveat = (
            "A8 扩标语料（200/500/100/20，L1 算法层）；"
            f"{hit}/{n_gold} 下界 {recall_bound:.4f}、误报 {spurious}/{n_detected} "
            f"上界 {fpr_bound:.4f} ⇒ **判定用界**（界不达标即 UNDERPOWERED）。"
            " ⚠️ L1 = 合成语料直接入图，**未经端到端（M2 抽取）验证**"
        )
    shared_status = status if recall.value is not None else CriterionStatus.UNKNOWN

    return (
        CriterionResult(
            criterion=C_RECALL,
            status=shared_status,
            value=recall.value,
            provenance=_provenance(
                runner_ctx,
                dataset_version=str(
                    meta.get("version") or f"gold-affiliation-{version}"
                ),
                kg_version=str(meta.get("kg_version")),
                corpus=corpus_desc,
                corpus_layer=corpus_layer,
                notes="; ".join(x for x in (reason, caveat) if x),
            ),
            blocked_by=None
            if recall.value is not None
            else (recall.reason or "无分母"),
            threshold=0.80,
            threshold_source="provisional",  # 阈值取自 spec（未校准 ⇒ 不给裸 PASS）
            verdict=judge(
                recall.value,
                threshold=0.80,
                threshold_source="provisional",
                ci_bound=recall_bound,
            ),
            detail={
                "gold_count": n_gold,
                "detected_count": n_detected,
                "matched": hit,
                "n": n_gold,
                "ci_lower": round(recall_bound, 4),
                "ci_upper": round(clopper_pearson_upper(hit, n_gold), 4),
                "alpha": DEFAULT_ALPHA,
                "corpus_layer": corpus_layer,
                "match_rule": "type_and_members（成员为图节点 id，共享节点不计入）",
                "detected_by_type": _by_type(findings),
            },
        ),
        CriterionResult(
            criterion=C_FPR,
            status=status if fpr.value is not None else CriterionStatus.UNKNOWN,
            value=fpr.value,
            provenance=_provenance(
                runner_ctx,
                dataset_version=str(
                    meta.get("version") or f"gold-affiliation-{version}"
                ),
                kg_version=str(meta.get("kg_version")),
                corpus=corpus_desc,
                corpus_layer=corpus_layer,
                notes="; ".join(x for x in (reason, caveat) if x),
            ),
            blocked_by=None if fpr.value is not None else (fpr.reason or "无分母"),
            threshold=0.15,
            threshold_source="provisional",  # 同上（A8）
            verdict=judge(
                fpr.value,
                threshold=0.15,
                threshold_source="provisional",
                higher_is_better=False,
                ci_bound=fpr_bound,
            ),
            detail={
                "gold_count": n_gold,
                "detected_count": n_detected,
                "spurious": spurious,
                "n": n_detected,
                "ci_lower": round(clopper_pearson_lower(spurious, n_detected), 4),
                "ci_upper": round(fpr_bound, 4),
                "alpha": DEFAULT_ALPHA,
                "corpus_layer": corpus_layer,
                "detected_by_type": _by_type(findings),
            },
        ),
    )


def _by_type(findings: tuple[Finding, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.type] = counts.get(finding.type, 0) + 1
    return dict(sorted(counts.items()))


def _unknown(
    criterion: str, runner_ctx: RunnerContext, blocked_by: str
) -> CriterionResult:
    """统一构造「没测出来」的结果：**value 恒为 null**（不是 0）。"""
    return CriterionResult(
        criterion=criterion,
        status=CriterionStatus.UNKNOWN,
        value=None,
        provenance=_provenance(
            runner_ctx,
            dataset_version="gold-affiliation-v1",
            kg_version=str(load_affiliation_meta().get("kg_version") or ""),
            corpus="demo/affiliation（合成演示语料，9 组植入）",
        ),
        blocked_by=blocked_by,
        verdict=Verdict.INDETERMINATE,
    )


def eval_hidden_relation_recall(ctx: dict[str, Any]) -> CriterionResult:
    """**C2-a 隐性关联召回**（真机 M4 检测 vs gold）。"""
    return _affiliation_results(ctx["ctx"])[0]


def eval_hidden_relation_fpr(ctx: dict[str, Any]) -> CriterionResult:
    """**C2-b 误报率**（真机 M4 检测 vs gold）。"""
    return _affiliation_results(ctx["ctx"])[1]


#: C3-a 阈值的环境变量名（**显式覆盖** ⇒ 阈值来源从 provisional 升为 env-override，
#: 因为「人裁决过」与「推算默认值」在报告里必须长得不一样）。
ENV_COST_CEILING = "EVAL_SINGLE_DOC_TOKEN_CEILING"


def resolve_cost_ceiling() -> tuple[int, str]:
    """**C3-a 的阈值与来源**（TBD-7 / D2）。

    返回 ``(ceiling, threshold_source)``：

    - 环境变量 :data:`ENV_COST_CEILING` **显式设置** ⇒ ``env-override``（人工裁决过）；
    - 否则取 ``Settings.eval_single_doc_token_ceiling`` **默认** ⇒ ``provisional``
      ⇒ 判定只能给 ``PASS(provisional)``（§5.2 第 3 条防假绿）。

    **为什么不直接读 Settings**：``Settings`` 分不出「默认值」与「人显式设的值」，
    而这两者在验收时的分量完全不同（前者不构成 TBD-7 收敛证据）。
    """
    from app.core.config import get_settings  # noqa: PLC0415 - 避免 import 期读配置

    raw = os.environ.get(ENV_COST_CEILING)
    if raw is None or not raw.strip():
        return (
            int(get_settings().eval_single_doc_token_ceiling),
            THRESHOLD_PROVISIONAL,
        )
    try:
        return int(raw.strip()), THRESHOLD_ENV_OVERRIDE
    except ValueError as exc:
        raise ValueError(
            f"{ENV_COST_CEILING} 必须是整数（单位 token/文档），实际={raw!r}"
        ) from exc


def _cost_blocked(
    criterion: str,
    runner_ctx: RunnerContext,
    *,
    blocked_by: str,
    threshold: float,
    threshold_source: str,
    unit: str | None = None,
    detail: dict[str, Any] | None = None,
) -> CriterionResult:
    """C3-a / C3-b 的「没测出来」——**value 恒为 None**，阈值照实带出（与 C1 同口径）。

    为什么阈值要照实带出：这两条判据的状态是「**判据存在、阈值已定、取不到数**」，
    与「还没做」必须长得不一样，否则 TBD-7 会停在"不可判"的死状态（D2）。
    """
    return CriterionResult(
        criterion=criterion,
        status=CriterionStatus.BLOCKED,
        value=None,
        provenance=_provenance(
            runner_ctx,
            dataset_version="n/a（cost_metrics 无可用样本行）",
            kg_version="n/a",
            corpus="n/a（无样本行 ⇒ 无语料口径）",
        ),
        unit=unit,
        blocked_by=blocked_by,
        threshold=threshold,
        threshold_source=threshold_source,
        verdict=Verdict.INDETERMINATE,
        detail=detail,
    )


def _cost_reading(
    runner_ctx: RunnerContext, *, stage: str
) -> tuple[dict[str, Any] | None, str | None]:
    """读 ``cost_metrics`` 的 ``stage`` 聚合；读不到 ⇒ ``(None, 真实原因)``。

    **为什么失败也要带原因而不是吞掉**：``blocked_by`` 若只写「读不到」，后来人
    无从区分「落点坏了」与「压根没跑过」——而这两者的处置完全不同（前者要修代码，
    后者只需跑一轮真机）。P6-V4 正是被这条含混坑住的：旧文案写「缺落点」，
    落点其实早就有了，缺的只是**一次真实运行**。

    **为什么不开会话就返回而不是抛**：判据脚本**必须**跑完并给出结论
    （2026-10-03 真跑学到的教训：抛栈 ⇒ 一份报告都拿不到）。
    """
    from app.db.session import session_scope  # noqa: PLC0415 - 延迟导入，offline 不碰库
    from app.services.cost_metrics import aggregate_stage  # noqa: PLC0415

    try:
        parsed = UUID(str(runner_ctx.org_id))
    except (TypeError, ValueError):
        return None, f"RunnerContext.org_id 不是合法 UUID：{runner_ctx.org_id!r}"
    try:
        with session_scope(org_id=parsed) as db:
            return aggregate_stage(db=db, org_id=parsed, stage=stage), None
    except Exception as exc:  # noqa: BLE001 - 库不可用 ⇒ 转成 BLOCKED，不是崩
        return None, f"cost_metrics 不可读（stage={stage}）：{exc!r}"


def _cost_window(aggregate: dict[str, Any]) -> str:
    """样本区间（报告用）；无行 ⇒ ``n/a``。"""
    start, end = aggregate.get("date_from"), aggregate.get("date_to")
    if start is None or end is None:
        return "n/a"
    return f"{start.isoformat()}..{end.isoformat()}"


def eval_single_doc_cost(ctx: dict[str, Any]) -> CriterionResult:
    """**C3-a 单文档成本**（TBD-7）：**真读 ``cost_metrics`` 的抽取口径**。

    **P6-V4（2026-10-11）出数化**：M2 抽取侧的 token 落点**已在 P6-V2 落地**
    （``cost_metrics.record_extraction_usage``，写 ``stage='extraction'`` 行），
    故「缺 M2 抽取侧 token 落点」这条旧理由**已失效**——本函数不再写死 ``BLOCKED``，
    改成三态：

    - **offline**：不读库（offline **不产出判据数字**）⇒ ``BLOCKED`` + 真实缺口；
    - **live 且有样本行**：**出数**（``单文档成本 = 总和(token) / 去重文档数``，
      ``unit=token/doc``），按阈值判 ``PASS / FAIL``；
    - **live 但无样本行**：仍是 ``BLOCKED``，理由换成「**没跑过**，不是**没落点**」。

    **为什么只取 ``stage='extraction'``**：本项口径是「（全量）单文档**抽取**成本」。
    问答那一行是检索级开销，混进来会让分子（抽取 token）与分母（抽取过的文档）
    不是同一个过程——混口径的数比没有数更糟（它会看起来像一个正常的成本）。

    ⚠️ **TBD-7 仍未校准**：出数也只给 ``PASS(provisional)``（§5.2 第 3 条防假绿），
    **不构成达标证据**，除非 ``EVAL_SINGLE_DOC_TOKEN_CEILING`` 由人显式裁决。
    """
    runner_ctx: RunnerContext = ctx["ctx"]
    ceiling, source = resolve_cost_ceiling()
    note = (
        "阈值来自 config 推算（provisional），**不是**达标线；"
        "校准命令 scripts/eval_acceptance.py --calibrate"
        if source == THRESHOLD_PROVISIONAL
        else "阈值来自 EVAL_SINGLE_DOC_TOKEN_CEILING（人工裁决过）"
    )
    if runner_ctx.mode != "live":
        return _cost_blocked(
            C_COST,
            runner_ctx,
            blocked_by="offline 不读 cost_metrics（判据数字只在 live 下出）；"
            "真值还需 ① 跑过一次 M2 抽取（才会落 stage='extraction' 样本行）"
            " ② TBD-7 阈值校准（当前为 provisional）",
            threshold=float(ceiling),
            threshold_source=source,
            unit=UNIT_TOKEN_PER_DOC,
            detail={"ceiling": ceiling, "ceiling_source": source, "note": note},
        )

    aggregate, failure = _cost_reading(runner_ctx, stage=COST_STAGE_EXTRACTION)
    doc_count = int(aggregate["doc_count"]) if aggregate else 0
    tokens = int(aggregate["token_usage_total"]) if aggregate else 0
    if aggregate is None or doc_count <= 0 or tokens <= 0:
        #: **措辞纪律**：这里写「**没跑过**」而不是「**缺落点**」——落点 P6-V2 就有
        #: 了。照抄旧文案会让后来人以为还差一整段实现（P6-V4 立项正是因此）。
        reason = failure or (
            "cost_metrics 有 stage='extraction' 落点，但**还没跑过** M2 抽取"
            " ⇒ 无样本行、无可比分母"
        )
        return _cost_blocked(
            C_COST,
            runner_ctx,
            blocked_by=f"{reason}；且 TBD-7 未校准（阈值 {ceiling} 为 {source}）",
            threshold=float(ceiling),
            threshold_source=source,
            unit=UNIT_TOKEN_PER_DOC,
            detail={
                "ceiling": ceiling,
                "ceiling_source": source,
                "stage": COST_STAGE_EXTRACTION,
                "rows": int(aggregate["rows"]) if aggregate else 0,
                "note": note,
            },
        )

    value = tokens / doc_count
    status, _reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True
    )
    return CriterionResult(
        criterion=C_COST,
        status=status,
        value=value,
        provenance=_provenance(
            runner_ctx,
            dataset_version=f"cost_metrics:stage={COST_STAGE_EXTRACTION}"
            f"（{aggregate['rows']} 行 / {doc_count} 份文档）",
            corpus="实际入库语料（非固定演示集）",
            notes=f"样本区间 {_cost_window(aggregate)}（UTC 自然日）",
        ),
        unit=UNIT_TOKEN_PER_DOC,
        threshold=float(ceiling),
        threshold_source=source,
        verdict=judge(
            value,
            threshold=float(ceiling),
            threshold_source=source,
            higher_is_better=False,
        ),
        detail={
            "ceiling": ceiling,
            "ceiling_source": source,
            "stage": COST_STAGE_EXTRACTION,
            "rows": int(aggregate["rows"]),
            "token_usage_total": tokens,
            "doc_count": doc_count,
            "window": _cost_window(aggregate),
            "note": note,
        },
    )


def eval_incremental_cost_ratio(ctx: dict[str, Any]) -> CriterionResult:
    """**C3-b 增量 / 全量成本比**：阈值按矩阵「显著 < 1.00」（**D3：不落 config**）。

    **P6-V4（2026-10-11）出数化**：两侧写入方**已在 P6-V3 落地**
    （``record_full_rebuild_cost`` / ``record_incremental_rebuild_cost``，
    单位同为**图元素个数**），故「无写入方」这条旧理由**已失效**。与 C3-a 同三态。

    **量纲**（2026-10-10 裁决 A 组，本批**不推翻**）：分子 = 增量重算重写的图元素个数，
    分母 = 首次全量构建的图元素个数 ⇒ 比值**无量纲**（``unit=ratio``）。

    ⚠️ **无分母 ⇒ ``BLOCKED`` + ``value=null``**，**不是** 0：0 会被读成「比值真的小」，
    那正是本判据最危险的假绿方向。表内 ``cost_ratio`` 列的 ``0/0 → 0.0`` 语义
    （``_refresh_cost_ratio``）本批**未改**，改的是**判据读到 0 分母时不采纳它**。
    """
    runner_ctx: RunnerContext = ctx["ctx"]
    detail_base = {
        "threshold_origin": "矩阵 §5.1「显著 < 1.00」，人工裁决定值（非实测推算）",
        "note": "D3：本阈值**不落 config**；注意它与 spec §6 的告警线 "
        "COST_RATIO_ALERT_THRESHOLD（P6-V 落地，运行期告警）不是同一个东西",
    }
    if runner_ctx.mode != "live":
        return _cost_blocked(
            C_COST_RATIO,
            runner_ctx,
            blocked_by="offline 不读 cost_metrics（判据数字只在 live 下出）；"
            "真值还需 ① 跑过一次首次全量构建（分母）② 跑过一次增量重算（分子）",
            threshold=COST_RATIO_SIGNIFICANT,
            threshold_source=THRESHOLD_CALIBRATED,
            unit=UNIT_COST_RATIO,
            detail=dict(detail_base),
        )

    aggregate, failure = _cost_reading(runner_ctx, stage=COST_STAGE_EXTRACTION)
    full = float(aggregate["full_rebuild_cost"]) if aggregate else 0.0
    incremental = float(aggregate["incremental_cost"]) if aggregate else 0.0
    if aggregate is None or full <= 0:
        #: 同上措辞纪律：写「没跑过」，不写「无写入方」（写入方 P6-V3 已落地）。
        reason = failure or (
            "cost_metrics 的两侧列有写入方，但**还没跑过**首次全量构建"
            "（无分母）与增量重算（无分子）"
        )
        return _cost_blocked(
            C_COST_RATIO,
            runner_ctx,
            blocked_by=f"{reason}；两侧同为「图元素个数」，"
            "未跑出分母前比值无定义（**不**按 0.0 计）",
            threshold=COST_RATIO_SIGNIFICANT,
            threshold_source=THRESHOLD_CALIBRATED,
            unit=UNIT_COST_RATIO,
            detail={
                **detail_base,
                "rows": int(aggregate["rows"]) if aggregate else 0,
                "incremental_cost": incremental,
                "full_rebuild_cost": full,
            },
        )

    value = incremental / full
    status, _reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True
    )
    return CriterionResult(
        criterion=C_COST_RATIO,
        status=status,
        value=value,
        provenance=_provenance(
            runner_ctx,
            dataset_version=f"cost_metrics:图规模（{aggregate['rows']} 行）",
            corpus="实际入库语料（非固定演示集）",
            notes=f"样本区间 {_cost_window(aggregate)}（UTC 自然日）",
        ),
        unit=UNIT_COST_RATIO,
        threshold=COST_RATIO_SIGNIFICANT,
        threshold_source=THRESHOLD_CALIBRATED,
        verdict=judge(
            value,
            threshold=COST_RATIO_SIGNIFICANT,
            threshold_source=THRESHOLD_CALIBRATED,
            higher_is_better=False,
        ),
        detail={
            **detail_base,
            "rows": int(aggregate["rows"]),
            "incremental_cost": incremental,
            "full_rebuild_cost": full,
            "window": _cost_window(aggregate),
        },
    )


def _judged_answers(
    answers: tuple[AnswerRecord, ...],
    indices: tuple[int, ...],
    judgements: dict[int, bool] | None,
    judged_by: str,
) -> tuple[AnswerRecord, ...]:
    """把人工判分贴回对应答案（**未判分的题不入分母**，A3）。"""
    table = judgements or {}
    return tuple(
        AnswerRecord(
            refused=answer.refused,
            citations=answer.citations,
            correct=table.get(index),
            judged_by=judged_by if index in table else None,
        )
        for index, answer in zip(indices, answers, strict=True)
    )


def _apply_judgements(
    indices: Sequence[int],
    answers: Sequence[AnswerRecord],
    judgements: Mapping[int, bool] | None,
    gold_correct: Mapping[int, bool | None],
    judged_by: str,
) -> tuple[AnswerRecord, ...]:
    """套人工判分；``gold_correct`` 是 gold 里已存的那份（P6-T 写回），作兜底。

    为什么保留兜底却不算违规：它被套用的**前置条件**是 :func:`_answer_gate` 与
    :func:`_reproducibility_gate` 都已通过 ⇒ 已证明「这批答案 == 当时人判的那批」。
    缺了那两道门，兜底就会退化成 P6-T 那条 canary（6/6 拒答照样出 0.8333）。
    """
    table = judgements or {}
    applied: list[AnswerRecord] = []
    for index, answer in zip(indices, answers, strict=True):
        correct = table.get(int(index), gold_correct.get(int(index)))
        applied.append(
            AnswerRecord(
                refused=answer.refused,
                citations=answer.citations,
                answer_text=answer.answer_text,
                correct=correct,
                #: 未判分的题**不许落 judged_by**（A3：没人判过却写着某人的名字，
                #: 事后就分不清这题到底判没判）。
                judged_by=judged_by if correct is not None else None,
            )
        )
    return tuple(applied)


def _awaiting_judgement(
    answers: tuple[AnswerRecord, ...], indices: tuple[int, ...]
) -> list[dict[str, Any]]:
    """把**待判分**的答案原文摊开（A3：人不该盲判）。

    为什么必须给原文：判分表一旦写下去就决定了 C1 的数字。若判分时只能看到
    ``refused / citations 数``，事后谁也复核不了某题当初答了什么 ⇒ 判据不可信。
    （P6-F：``answer_text`` 因此进了 :class:`AnswerRecord`。）
    """
    return [
        {
            "index": index,
            "refused": answer.refused,
            "citations": len(answer.citations),
            "answer": answer.answer_text,
        }
        for index, answer in zip(indices, answers, strict=False)
    ]


# ---------------------------------------------------------------------------
# A8 可复现门（P7-K）
# ---------------------------------------------------------------------------


def _clean_str(value: Any) -> str | None:
    """把「空 / None」统一归一成 ``None``（JSON 里的 ``""`` 不算登记过）。

    为什么要这一步：答卷里缺失的坐标常写成 ``""``。若拿它去比对会把
    「当时没记录」读成「本次不一致」⇒ **假红**，而假红会反过来把真红淹没。
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class JudgementBasis:
    """**判分当时那一趟**的环境坐标与答案原文（A8 可复现 / P7-K 的锚）。

    它同时支撑两条门：

    - **D4（版本漂移）**：判分是在某个池 / 某版代码 / 某个模型上做的；换环境重跑
      ⇒ 答案已经不是人判过的那批 ⇒ 复用判分即**空心出数**。
      P6-T 实测过成因：请求显式带 ``attendance-demo-v1``，链路却永远取 PG 里
      ``ready_at`` 最新的那条 ⇒ 检索落在增量版本的池上 ⇒ **6/6 全拒答**。
    - **D5（空心 PASS）**：``eval_multihop_accuracy`` 原写法是
      ``correct = judgements.get(item.index, item.correct)``——它**从不看本次答案**，
      所以 6/6 拒答照样报 ``0.8333 PASS``（P6-T canary 实证）。

    加载来源是判分表的 ``_source_sheets`` 元信息。为什么让判分表**自证来源**
    而不是新增命令行参数：**参数可以被忘传**，而判分表不写来源本身就违反了
    「判分文件必须能自解释」的既有约定（``eval_acceptance.py::_load_judgements``）。
    """

    dataset_version: str
    source: str
    git_hash: str | None
    pool_fingerprint: str | None
    top_k: int | None
    generation_model: str | None
    #: 题号 -> 判分所见答案原文（**逐字**比对用）
    answers: Mapping[int, str]

    @classmethod
    def load(cls, judgement_path: Path | None, *, side: str) -> JudgementBasis | None:
        """按判分表的 ``_source_sheets`` 找到那份答卷并抽出坐标。

        **找不到 ⇒ 返回 ``None`` 而不抛**：没有 basis 时判据走「未核 + 如实登记」，
        **不等于**静默放行——见 :func:`_reproducibility_gate`。
        """
        if judgement_path is None:
            return None
        sheet_path = cls._locate_sheets(judgement_path)
        if sheet_path is None:
            return None
        try:
            sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

        rows = sheet.get(side) or []
        spec = sheet.get(f"_{side}_spec") or {}
        pool = spec.get("pool") or {}
        answers: dict[int, str] = {}
        for row in rows:
            raw_index = str(row.get("index") or "").strip()
            #: 非数字题号（如手工备注行）直接跳过：它不参与判分，混进来只会
            #: 让比对函数以为某题「没有被判过」。
            if raw_index.lstrip("-").isdigit():
                answers[int(raw_index)] = str(row.get("answer") or "")
        top_k = spec.get("top_k")
        return cls(
            dataset_version=str(sheet.get("_dataset_version") or ""),
            source=sheet_path.name,
            git_hash=_clean_str(sheet.get("_git_hash")),
            pool_fingerprint=_clean_str(pool.get("fingerprint")),
            top_k=top_k if isinstance(top_k, int) else None,
            generation_model=_clean_str(spec.get("generation_model")),
            answers=answers,
        )

    @staticmethod
    def _locate_sheets(judgement_path: Path) -> Path | None:
        """判分表 ``_source_sheets`` 指向的答卷（**先在同目录找**）。"""
        try:
            table = json.loads(judgement_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        sheet_name = table.get("_source_sheets")
        if not isinstance(sheet_name, str) or not sheet_name.strip():
            return None
        candidate = judgement_path.parent / Path(sheet_name).name
        return candidate if candidate.is_file() else None

    def env_mismatch(
        self,
        *,
        git_hash: str,
        pool_fingerprint: str | None,
        top_k: int | None,
        generation_model: str | None,
    ) -> str | None:
        """环境是否与判分时一致：不符返回**原因**，一致返回 ``None``。

        两侧都可能有 ``None`` ⇒ **不比对**（判分材料没登记，或本次取不到该坐标）。
        为什么不把这些判成不一致：拿「当时没记录 / 本次没取到」当证据去证伪，
        等于制造一种**无法被反驳的假红**——它会反过来把真红淹没。
        """
        if self.git_hash and git_hash and self.git_hash != git_hash:
            return f"代码版本不同（判分 {self.git_hash} / 本次 {git_hash}）"
        if (
            self.pool_fingerprint
            and pool_fingerprint
            and self.pool_fingerprint != pool_fingerprint
        ):
            return (
                f"chunk 池不同（判分 {self.pool_fingerprint} / 本次 "
                f"{pool_fingerprint}）⇒ 检索到的不是同一批证据"
            )
        if self.top_k is not None and top_k is not None and self.top_k != top_k:
            return f"注入证据条数不同（判分 {self.top_k} / 本次 {top_k}）"
        if (
            self.generation_model
            and generation_model
            and self.generation_model != generation_model
        ):
            return (
                f"生成模型不同（判分 {self.generation_model} / 本次 "
                f"{generation_model}）"
            )
        return None

    def stale_answers(
        self, indices: Sequence[int], answers: Sequence[AnswerRecord]
    ) -> list[dict[str, Any]]:
        """逐题列出「本次答案 ≠ 判分所见答案」（空 = 全部一致）。

        **拒答一律计为不一致**：拒答没有答案原文，判分人当时判的是一段文字，
        ⇒ 拿那段文字的判分结果往拒答上套，就是 P6-T 那条 canary 的原样复现。
        """
        stale: list[dict[str, Any]] = []
        for index, answer in zip(indices, answers, strict=False):
            expected = self.answers.get(int(index))
            if answer.refused:
                stale.append(
                    {
                        "index": int(index),
                        "reason": "本次答案为拒答（无答案可判）",
                        "judged_answer_head": (expected or "")[:80],
                    }
                )
                continue
            if expected is None:
                continue
            if answer.answer_text.strip() != expected.strip():
                stale.append(
                    {
                        "index": int(index),
                        "reason": "答案原文与判分所见不一致",
                        "judged_answer_head": expected[:80],
                        "current_answer_head": answer.answer_text[:80],
                    }
                )
        return stale


_UNCHECKED_NOTE = (
    "未提供判分材料来源（判分表缺 _source_sheets）⇒ "
    "无法证明「本次答案」就是「当时人判的那批答案」"
)


def _reproducibility_gate(
    basis: JudgementBasis | None,
    *,
    dataset_version: str,
    git_hash: str,
    pool_fingerprint: str | None = None,
    top_k: int | None = None,
    generation_model: str | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """出数前的**环境自检**（P7-K 出口判据 2）。

    :returns: ``(blocked_by, detail)`` —— ``blocked_by`` 非 ``None`` ⇒
        **必须转 BLOCKED 且 value=None**（不是 0、也不是旧值）。

    三种返回值：

    - 坐标不符 ⇒ ``("判分环境不可复现：…", {...})`` ⇒ BLOCKED；
    - 无 basis / basis 属于别的数据集 ⇒ ``(None, {"reproducibility": "unchecked"})``
      ⇒ **照旧出数但如实登记**，不许写成"已核实";
    - 一致 ⇒ ``(None, {"reproducibility": "verified"})``。
    """
    if basis is None:
        return None, {"reproducibility": "unchecked", "note": _UNCHECKED_NOTE}
    if basis.dataset_version and basis.dataset_version != dataset_version:
        return None, {
            "reproducibility": "unchecked",
            "note": (
                f"判分材料 {basis.source} 属于 {basis.dataset_version}，"
                f"与本判据的 {dataset_version} 不是同一数据集 ⇒ 不适用"
            ),
        }
    mismatched = basis.env_mismatch(
        git_hash=git_hash,
        pool_fingerprint=pool_fingerprint,
        top_k=top_k,
        generation_model=generation_model,
    )
    if mismatched is not None:
        return (
            f"判分环境不可复现：{mismatched}（判分材料 {basis.source}）",
            {
                "reproducibility": "blocked",
                "expected": {
                    "git_hash": basis.git_hash,
                    "pool_fingerprint": basis.pool_fingerprint,
                    "top_k": basis.top_k,
                    "generation_model": basis.generation_model,
                },
                "actual": {
                    "git_hash": git_hash,
                    "pool_fingerprint": pool_fingerprint,
                    "top_k": top_k,
                    "generation_model": generation_model,
                },
            },
        )
    return None, {"reproducibility": "verified", "basis_source": basis.source}


def _live_env_coords(runner_ctx: RunnerContext) -> tuple[str, int, str] | None:
    """本次运行的 ``(池指纹, top_k, 生成模型)``；取不到返回 ``None``。

    为什么 best-effort（**吞异常**而不是报错）：坐标只用于**证伪**「判分还能不能复用」，
    取不到它说明的是"本次无从比对"，不能顺势把判据判死 ⇒ 是否出数交给
    :func:`_reproducibility_gate` 决定。
    """
    try:
        from uuid import UUID  # noqa: PLC0415

        from app.evaluation.baseline import (  # noqa: PLC0415
            build_pool_ref,
            graph_side_spec,
        )
        from app.services.graphs import GraphService  # noqa: PLC0415

        snapshot = _qa_run(runner_ctx)
        kg_version = next(iter(snapshot.kg_versions), "")
        pool = GraphService.instance().fetch_chunk_pool(
            kg_version=kg_version, org_id=UUID(runner_ctx.org_id)
        )
        pool_ref = build_pool_ref(
            kg_version=kg_version, org_id=runner_ctx.org_id, chunks=pool
        )
        spec = graph_side_spec(pool=pool_ref, judged_by=runner_ctx.judged_by)
    except Exception:  # noqa: BLE001 - 坐标取不到 ⇒ 无从比对，不拖垮判据
        return None
    return spec.pool.fingerprint, spec.top_k, spec.generation_model


def _refused_entries(
    indices: Sequence[int], answers: Sequence[AnswerRecord]
) -> list[dict[str, Any]]:
    """本次**拒答**的题（P6-T canary 的原样形状：全拒答仍报 0.8333 PASS）。"""
    return [
        {
            "index": int(index),
            "reason": "本次答案为拒答（无答案可判）",
            "answer_head": answer.answer_text[:80],
        }
        for index, answer in zip(indices, answers, strict=False)
        if answer.refused
    ]


def _answer_gate(
    basis: JudgementBasis | None,
    indices: Sequence[int],
    answers: Sequence[AnswerRecord],
) -> list[dict[str, Any]]:
    """本次答案是否还能套用判分：**空列表 = 可以**，否则逐题给出理由。

    两条独立证据：

    1. **拒答**（不需要判分材料也能查）：拒答没有答案原文，判分人判的是一段文字
       ⇒ 把那段文字的判分套到拒答上，就是 P6-T canary 的形状；
    2. **答案原文漂移**（需要 basis）：更像日常形态——环境没报错、链路也通，
       但证据换了 ⇒ 答案悄悄变了，而判分表还是旧的。
    """
    if isinstance(basis, JudgementBasis):
        return basis.stale_answers(indices, answers)
    return _refused_entries(indices, answers)


def _blocked_result(
    criterion: str,
    runner_ctx: RunnerContext,
    *,
    dataset_version: str,
    blocked_by: str,
    threshold: float,
    threshold_source: str,
    **detail: Any,
) -> CriterionResult:
    """「不给数字」的统一出口：**value=None + INDETERMINATE**（不是 0、不是旧值）。"""
    return CriterionResult(
        criterion=criterion,
        status=CriterionStatus.UNKNOWN,
        value=None,
        provenance=_provenance(runner_ctx, dataset_version=dataset_version),
        blocked_by=blocked_by,
        verdict=Verdict.INDETERMINATE,
        threshold=threshold,
        threshold_source=threshold_source,
        detail=detail or None,
    )


def _c1_unknown(
    runner_ctx: RunnerContext, blocked_by: str, **detail: Any
) -> CriterionResult:
    """C1 的「没测出来」——**value 恒为 None**，阈值照实带出（与 C3 同口径）。"""
    return CriterionResult(
        criterion=C_GAIN,
        status=CriterionStatus.UNKNOWN,
        value=None,
        provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v4"),
        blocked_by=blocked_by,
        verdict=Verdict.INDETERMINATE,
        threshold=C1_GAIN_THRESHOLD,
        threshold_source=THRESHOLD_PROVISIONAL,
        detail=detail or None,
    )


def _detect_layer(kg_versions: Any, org_id: str) -> str | None:
    """按**图内实测**判语料层（P6-D）：多版本时**取最高层**。

    为什么取最高而不是取第一个：一次运行若同时碰过 L1 与 L2 的图，
    标低的那档等于**用弱样本掩盖强样本**（反向也成立：标高会假绿）。
    ⇒ 只有"真的跑到了 L2"才写 L2，其余按实测写 L1，**判不出来就空着**。
    """
    parsed_org: UUID | None = None
    if org_id:
        try:
            parsed_org = UUID(org_id)
        except ValueError:
            parsed_org = None

    layers: list[str] = []
    for version in sorted(str(v) for v in kg_versions):
        if not version or version == "None":
            continue
        try:
            layer = detect_corpus_layer(kg_version=version, org_id=parsed_org)
        except Exception:  # noqa: BLE001 - 归因判不出来 ⇒ 空着，不拖垮整份报告
            return None
        if layer:
            layers.append(layer)
    if LAYER_END_TO_END in layers:
        return LAYER_END_TO_END
    if LAYER_ALGORITHM in layers:
        return LAYER_ALGORITHM
    return None


def _graph_spec(runner_ctx: RunnerContext, pool_ref: Any) -> Any:
    """图侧的共因清单（``retriever`` 取 :data:`RETRIEVER_GRAPH`，
    P6-J 起 = ``graph_mentions+lexical_rerank``）。"""
    from app.evaluation.baseline import graph_side_spec  # noqa: PLC0415

    return graph_side_spec(pool=pool_ref, judged_by=runner_ctx.judged_by)


def _baseline_spec(runner_ctx: RunnerContext, pool_ref: Any, embedder: Any) -> Any:
    """基线侧的共因清单（``retriever = dense_top_k`` ⇒ 与图侧的唯一差异）。"""
    from app.core.config import get_settings  # noqa: PLC0415
    from app.evaluation.baseline import baseline_side_spec  # noqa: PLC0415

    return baseline_side_spec(
        pool=pool_ref,
        embedder=embedder,
        top_k=get_settings().eval_baseline_top_k,
        judged_by=runner_ctx.judged_by,
    )


def _load_pool_and_specs(
    runner_ctx: RunnerContext, embedder: Any
) -> tuple[Any, Any, Any, list]:
    """两侧共用**同一个池**：只加载一次，再由双方各自算指纹（不同 ⇒ 必是换了池）。"""
    from uuid import UUID  # noqa: PLC0415

    from app.evaluation.baseline import build_pool_ref  # noqa: PLC0415
    from app.services.graphs import GraphService

    snapshot = _qa_run(runner_ctx)
    kg_version = next(iter(snapshot.kg_versions), "")
    pool = GraphService.instance().fetch_chunk_pool(
        kg_version=kg_version, org_id=UUID(runner_ctx.org_id)
    )
    pool_ref = build_pool_ref(
        kg_version=kg_version, org_id=runner_ctx.org_id, chunks=pool
    )
    return (
        _graph_spec(runner_ctx, pool_ref),
        _baseline_spec(runner_ctx, pool_ref, embedder),
        pool_ref,
        pool,
    )


def eval_graph_gain(ctx: dict[str, Any]) -> CriterionResult:
    """**C1 图谱相对 RAG 增益**（A1 / L10-A1）：两侧**同一批改分**才敢出数。

    三条硬要求：

    1. **双侧同源判分**（不是各判各的）：图侧答案来自产品 HTTP 链路，基线侧来自
       :mod:`app.evaluation.baseline` 的 dense top-k 检索 + **同一份 Prompt、同一个
       ChatModel、同一个解析器、同一套引用回查** ⇒ 唯一变量是**检索方式**；
    2. **可比性前置断言**：两侧池指纹 / k / 生成模型 / prompt 版本任一不一致
       ⇒ **返回 UNKNOWN，不给数字**（不公平条件下算出的增益比没有数字更糟）；
       **P6-S**：它与双侧 spec 已提到**判分闸门之前**执行——否则「判完 80 题才发现
       两侧不可比」会让人工劳动全部作废（详见函数体注释）；
    3. **反向守卫**：增益**保号**——基线反超 ⇒ 值为负且 ``regression_warning`` 显式出现，
       **不许**取绝对值，也不许被 10% 阈值判定悄悄吞掉。

    ⚠️ **A3**：两侧**都**必须有人工判分，缺任一侧 ⇒ UNKNOWN（**不是 0、不是 PASS**）。
    """
    runner_ctx: RunnerContext = ctx["ctx"]
    if runner_ctx.mode != "live":
        return _c1_unknown(
            runner_ctx,
            "需 live 模式（C1 要跑两侧问答链路）；offline 不产出判据数字",
        )

    snapshot = _qa_run(runner_ctx)
    if not snapshot.answers:
        return _qa_unavailable(C_GAIN, runner_ctx, snapshot)

    #: **P6-S：双侧共因清单与可比性断言必须在人工判分之前可见**
    #:
    #: 为什么提到最前面（原本排在判分闸门之后）：那时一旦判分缺失就把整个函数
    #: return 掉 ⇒ 没有判分就完全看不到两侧是怎么比的 ⇒
    #: 「判完 80 题才发现两侧不可比」会让人工劳动**全部作废**。提到前面之后：
    #: ① 缺判分时报告照样**不带任何数字**，但把两侧 spec 与可比性结论摊开；
    #: ② 不可比 ⇒ **在此即返回**，不再花 40 次 LLM 去跑一趟注定作废的基线侧。
    from app.evaluation.baseline import comparability_error  # noqa: PLC0415

    embedder = _build_embedder_or_none()
    if embedder is None:
        return _c1_unknown(
            runner_ctx,
            "基线侧不可用：embedding 未配置（EVAL_EMBEDDING_MODEL / *_API_KEY）",
        )
    graph_spec, base_spec, _pool_ref, _pool = _load_pool_and_specs(runner_ctx, embedder)
    incomparable = comparability_error(graph_spec, base_spec)
    if incomparable is not None:
        return _c1_unknown(
            runner_ctx,
            f"L10-A1 反向守卫：{incomparable}",
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
        )

    #: **P7-K 门 ①——环境自检**（判分是否还能复用）。
    #: 坐标直接复用 :func:`_load_pool_and_specs` 已算好的图侧 spec：不重复建池、
    #: 不多一次 Neo4j 查询，也避免两侧坐标来自两次不同的加载。
    blocked, gate_detail = _reproducibility_gate(
        runner_ctx.judgement_basis,
        dataset_version="controlled-qset-v4",
        git_hash=runner_ctx.git_hash,
        pool_fingerprint=graph_spec.pool.fingerprint,
        top_k=graph_spec.top_k,
        generation_model=graph_spec.generation_model,
    )
    if blocked is not None:
        return _c1_unknown(
            runner_ctx,
            blocked,
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
            **gate_detail,
        )

    #: **P7-K 门 ②——答案比对（图侧）**：这批答案是不是当时人判过的那批。
    graph_stale = _answer_gate(
        runner_ctx.judgement_basis, snapshot.answered_indices, snapshot.answers
    )
    if graph_stale:
        return _c1_unknown(
            runner_ctx,
            f"判分已过期：图侧 {len(graph_stale)}/{len(snapshot.answers)} 题"
            "的本次答案与判分材料不一致（拒答或答案原文漂移）⇒ 旧判分不得套用",
            stale_answers=graph_stale,
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
            awaiting_graph=_awaiting_judgement(
                snapshot.answers, snapshot.answered_indices
            ),
        )

    graph_answers = _judged_answers(
        snapshot.answers,
        snapshot.answered_indices,
        runner_ctx.judgements,
        runner_ctx.judged_by,
    )
    graph_metric = accuracy(graph_answers)

    baseline_error, baseline_answers, baseline_indices = _run_baseline_side(runner_ctx)

    #: 门 ② 的**基线侧**：它用另一张判分表（A1 裁决 3）⇒ 必须有自己的 basis。
    baseline_stale = _answer_gate(
        runner_ctx.baseline_judgement_basis, baseline_indices, baseline_answers
    )
    if baseline_stale:
        return _c1_unknown(
            runner_ctx,
            f"判分已过期：基线侧 {len(baseline_stale)}/{len(baseline_answers)} 题"
            "的本次答案与判分材料不一致（拒答或答案原文漂移）⇒ 旧判分不得套用",
            stale_answers=baseline_stale,
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
            awaiting_baseline=_awaiting_judgement(baseline_answers, baseline_indices),
        )
    baseline_metric = (
        accuracy(
            _judged_answers(
                baseline_answers,
                baseline_indices,
                runner_ctx.baseline_judgements,
                runner_ctx.judged_by,
            )
        )
        if baseline_error is None
        else None
    )

    if graph_metric.value is None:
        return _c1_unknown(
            runner_ctx,
            "A3：图侧没有一题被人工判分（用 --judgements 提供）；"
            "脚本不自动判分 ⇒ 不判就等于没跑",
            #: **把两侧原文一并摊出来**：免得"先判图侧、再判基线侧"要跑两趟才知道答了什么
            awaiting_graph=_awaiting_judgement(
                snapshot.answers, snapshot.answered_indices
            ),
            awaiting_baseline=_awaiting_judgement(baseline_answers, baseline_indices),
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
        )
    if baseline_error is not None:
        return _c1_unknown(
            runner_ctx,
            f"基线侧不可用：{baseline_error}",
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
        )
    if baseline_metric.value is None:  # type: ignore[union-attr]
        return _c1_unknown(
            runner_ctx,
            "A3：基线侧没有一题被人工判分（用 --baseline-judgements 提供）；"
            "只判图谱侧 ⇒ 增益无从计算",
            awaiting_baseline=_awaiting_judgement(baseline_answers, baseline_indices),
            graph_spec=graph_spec.as_dict(),
            baseline_spec=base_spec.as_dict(),
        )

    metric = graph_gain(graph_metric.value, baseline_metric.value)
    if metric.value is None:
        return _c1_unknown(runner_ctx, metric.reason or "增益无定义")

    regression = metric.value < 0
    status, reason = resolve_status(
        link_ready=True,
        dataset_ready=True,
        rubric_defined=True,
        #: 基线是**项目内自建**（L10-A1 条款 6 / G5 声明）⇒ 非终局
        corpus_is_final=False,
    )
    return CriterionResult(
        criterion=C_GAIN,
        status=status,
        value=metric.value,
        provenance=_provenance(
            runner_ctx,
            dataset_version="controlled-qset-v4",
            kg_version=", ".join(snapshot.kg_versions),
            #: **P7-K**：出数的同时把"判分所绑定的环境"一并写出——少了这三行，
            #: 这份数字可以被**脱离坐标**引用，那正是 P6-T D4/D5 的形状。
            pool_fingerprint=graph_spec.pool.fingerprint,
            generation_model=graph_spec.generation_model,
            top_k=graph_spec.top_k,
            #: **随实测反推**（P6-D）：图里有 M2 抽取产物 ⇒ L2，只有直灌数据 ⇒ L1，
            #: 图不可用 ⇒ None（宁可空着，不许填一个漂亮的层号）。
            corpus_layer=_detect_layer(snapshot.kg_versions, runner_ctx.org_id),
            notes="; ".join(
                x
                for x in (
                    reason,
                    "基线 = 项目内自建 dense top-k，**非客户现有系统**"
                    " ⇒ 增益只对该基线成立（L10-A1 条款 6 / G5 声明）",
                    "残留变量：as_of_date 走 db=None 口径"
                    "（演示语料全部无 document_date ⇒ 两侧同解）",
                    "追问记忆：A8 只解决 L1；本判据仍未走端到端（L2）",
                )
                if x
            ),
        ),
        threshold=C1_GAIN_THRESHOLD,
        threshold_source=THRESHOLD_PROVISIONAL,
        verdict=judge(
            metric.value,
            threshold=C1_GAIN_THRESHOLD,
            threshold_source=THRESHOLD_PROVISIONAL,
        ),
        detail={
            #: **基线分必须落盘**（L10-A1 条款 4 ①）：只落增益则复核不了分母
            "graph_accuracy": graph_metric.value,
            "baseline_accuracy": baseline_metric.value,
            "graph_judged": sum(1 for a in graph_answers if a.correct is not None),
            "baseline_judged": sum(
                1
                for a in _judged_answers(
                    baseline_answers,
                    baseline_indices,
                    runner_ctx.baseline_judgements,
                    runner_ctx.judged_by,
                )
                if a.correct is not None
            ),
            "graph_spec": graph_spec.as_dict(),
            "baseline_spec": base_spec.as_dict(),
            "regression_warning": "基线反超图谱（增益为负）" if regression else None,
            #: **P6-T（D2）**：出数这一趟的答案原文**必须落盘** —— 判分是在 P6-S 定格的
            #: 那份答卷上做的，而出数会**重新生成答案**；没有原文就无从逐题证明
            #: 「人判的 80 条」==「出数这一趟的 80 条」（判据 4：不许判在别人头上）。
            "answer_texts_graph": _awaiting_judgement(
                snapshot.answers, snapshot.answered_indices
            ),
            "answer_texts_baseline": _awaiting_judgement(
                baseline_answers, baseline_indices
            ),
        },
    )


def _build_embedder_or_none() -> Any:
    """装默认 embedder；不可用返回 ``None``（**不**退化成关键词检索）。"""
    from app.evaluation.baseline import EmbedderUnavailable, build_default_embedder

    try:
        return build_default_embedder()
    except EmbedderUnavailable:
        return None


def _run_baseline_side(
    runner_ctx: RunnerContext,
) -> tuple[str | None, tuple[AnswerRecord, ...], tuple[int, ...]]:
    """跑一遍**基线侧**问答；返回 ``(错误, 答案, 题号)``。**不抛异常**（同 `ask_safe`）。"""
    import asyncio  # noqa: PLC0415
    from uuid import UUID  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.evaluation.baseline import (
        DenseTopKRetriever,
        EmbedderUnavailable,
        answer_with_dense,
    )
    from app.services.graphs import GraphService

    embedder = _build_embedder_or_none()
    if embedder is None:
        return "embedding 未配置（EVAL_EMBEDDING_MODEL / *_API_KEY）", (), ()

    snapshot = _qa_run(runner_ctx)
    kg_version = next(iter(snapshot.kg_versions), "")
    if not kg_version:
        return "取不到图侧的 kg_version ⇒ 无法确定基线该用哪一版 chunk 池", (), ()

    try:
        pool = GraphService.instance().fetch_chunk_pool(
            kg_version=kg_version, org_id=UUID(runner_ctx.org_id)
        )
    except Exception as exc:  # noqa: BLE001 - 图库故障要转成字面看得懂的原因
        return f"基线候选池读取失败：{exc!r}", (), ()
    if not pool:
        return "基线候选池为空（该 kg_version 下无 :Chunk ⇒ 无从召回）", (), ()

    retriever = DenseTopKRetriever(embedder, top_k=get_settings().eval_baseline_top_k)
    answers: list[AnswerRecord] = []
    indices: list[int] = []
    errors: list[str] = []
    for item in load_question_set():
        try:
            retrieved = retriever.retrieve(item.question, pool)
            answers.append(
                asyncio.run(
                    answer_with_dense(question=item.question, evidence_chunks=retrieved)
                )
            )
            indices.append(item.index)
        except EmbedderUnavailable as exc:
            return str(exc), (), ()
        except Exception as exc:  # noqa: BLE001 - 单题失败不拖垮整批改判
            errors.append(f"#{item.index}: {exc!r}")
    if not answers:
        return "基线侧全部题目失败：" + "; ".join(errors[:3]), (), ()
    return None, tuple(answers), tuple(indices)


def _register_builtin_criteria() -> None:
    """注册内置判据（**唯一真源**：新增判据必须在此登记）。"""
    for name, evaluator in (
        (C_CITATION, eval_citation_coverage),
        (C_REFUSAL, eval_refusal_false_refusal),
        (C_MULTIHOP, eval_multihop_accuracy),
    ):
        if name not in _registered():
            register_criterion(name, evaluator)

    blocked_by, verified = _affiliation_blocked_by()
    affiliation_evaluators = (
        (eval_hidden_relation_recall, eval_hidden_relation_fpr)
        if verified
        else (
            PlaceholderEvaluator(C_RECALL, blocked_by=blocked_by),
            PlaceholderEvaluator(C_FPR, blocked_by=blocked_by),
        )
    )
    for name, evaluator in zip((C_RECALL, C_FPR), affiliation_evaluators, strict=True):
        if name not in _registered():
            register_criterion(name, evaluator)
    if C_GAIN not in _registered():
        #: **A1（2026-10-05，P6-C）**：换成真 evaluator（dense top-k 基线 + 双侧同源判分）。
        #: 阈值口径保持不变（10% / provisional）——**本批不碰阈值**，TBD-7 归阶段 ⑤。
        register_criterion(C_GAIN, eval_graph_gain)
    #: C3-a / C3-b **不用** PlaceholderEvaluator：它们**有阈值**（TBD-7 已落 config），
    #: 只是没有值 ⇒ 用真 evaluator 带出 threshold / threshold_source。
    for name, evaluator in (
        (C_COST, eval_single_doc_cost),
        (C_COST_RATIO, eval_incremental_cost_ratio),
    ):
        if name not in _registered():
            register_criterion(name, evaluator)


def _registered() -> dict[str, Any]:
    from app.evaluation import criteria  # noqa: PLC0415

    return criteria.CRITERIA


def run(
    ctx: RunnerContext, *, criteria: tuple[str, ...] = ALL_CRITERIA
) -> list[CriterionResult]:
    """按注册顺序执行判据，返回结果列表。"""
    _register_builtin_criteria()
    registry = _registered()
    payload = {
        "ctx": ctx,
        "dataset_version": "manifest:" + str(load_manifest().get("manifest_version")),
    }
    results: list[CriterionResult] = []
    for name in criteria:
        if name not in registry:
            raise KeyError(f"未登记的判据: {name}（新增判据必须先在 runner 注册）")
        results.append(registry[name](payload))
    return results


def self_test() -> dict[str, Any]:
    """**口径演练**（**构造输入**，不是判据）：验证五个指标函数在断网下都能跑通。

    ⚠️ 报告里这一块**明确标 `synthetic: true`**，与 `criteria` 分区存放——
    绝不允许演练值被读成测量结果。
    """
    gold = (
        Finding("shared_legal_rep", ("S004", "S010")),
        Finding("cycle", ("S007", "S009", "S011")),
    )
    detected = (
        Finding("shared_legal_rep", ("S010", "S004")),  # 成员顺序不同 ⇒ 仍应命中
        Finding("shared_phone", ("S002", "S013")),  # 误报
    )
    baseline = load_fixture_baseline()["self_test"]
    answers = (
        AnswerRecord(refused=False, citations=(CitationRef("chunk-1", has_span=True),)),
        AnswerRecord(refused=True, citations=()),
    )
    return {
        "synthetic": True,
        "note": "构造输入，仅验证口径可跑通；**不得**作为任何判据的结论",
        "metrics": {
            "findings_recall": findings_recall(gold, detected).value,
            "findings_false_positive_rate": findings_false_positive_rate(
                detected, gold
            ).value,
            "graph_gain": graph_gain(
                baseline["graph_accuracy"], baseline["baseline_accuracy"]
            ).value,
            "citation_coverage": citation_coverage(answers).value,
        },
    }


def upgrade_todo() -> list[str]:
    """报告顶部要打印的「升为 `MEASURED` 还缺什么」（proposal §4.2 第 3 条）。"""
    todo = [
        #: **P6-S 订正**：A1 **已裁决**（2026-10-03）且 dense top-k 基线**已实现**
        #: （`app/evaluation/baseline.py`）⇒ 原句「定义与实现（A1 待裁决）」已过期。
        #: 真实缺口换成了 A3：**两侧各 40 题的人工判分**（缺判分 ⇒ 无分母，属 P6-T）。
        f"{C_GAIN}: 需要两侧各 40 题的**人工判分**（A3：脚本不代判 ⇒ P6-T）",
        # **2026-10-11 P6-V4 订正**：落点**全齐**（M2 抽取侧 = P6-V2、增量重算
        # 两侧 = P6-V3），runner 也**已出数化** ⇒ 剩下的**不是代码缺口**，而是
        # 「**还没跑过一次真机**」（无样本行）+ TBD-7 未校准。旧写法把「缺落点」
        # 当成永久文案留了下来，而落点早就有了——这正是 P6-V4 立项的原因。
        f"{C_COST} / {C_COST_RATIO}: 落点与读口**已齐**（P6-V2/V3/V4），但还没跑过"
        f"一次真机 ⇒ 无 M2 抽取样本行、无增量重算分子/分母；"
        f"且 TBD-7 未校准（阈值仍 {THRESHOLD_PROVISIONAL}）",
    ]
    blocked_by, verified = _affiliation_blocked_by()
    if not verified:
        todo.append(f"{C_RECALL} / {C_FPR}: {blocked_by}")
    todo.append("全部判据：终局需**全量语料** + gold 扩标（当前仅为演示 / 合成语料）")
    return todo


def gold_findings() -> tuple[Finding, ...]:
    """（供外部工具使用）M4 gold 疑点集。"""
    return load_affiliation_gold()


def question_count() -> int:
    """受控问题集题数（报告用）。"""
    return len(load_question_set())


def dataset_version_map() -> dict[str, str]:
    return dataset_versions()


__all__ = [
    "ALL_CRITERIA",
    "C_CITATION",
    "C_COST",
    "C_COST_RATIO",
    "C_FPR",
    "C_GAIN",
    "C_MULTIHOP",
    "C_RECALL",
    "C_REFUSAL",
    "ENV_COST_CEILING",
    "RunnerContext",
    "ask",
    "dataset_version_map",
    "eval_incremental_cost_ratio",
    "eval_refusal_false_refusal",
    "eval_single_doc_cost",
    "gold_findings",
    "question_count",
    "resolve_cost_ceiling",
    "run",
    "self_test",
    "upgrade_todo",
]
