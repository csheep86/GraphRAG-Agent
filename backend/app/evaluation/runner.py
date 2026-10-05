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
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

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
    answers: list[AnswerRecord] = []
    failures: list[dict[str, Any]] = []
    for item in items:
        response, error = ask_safe(item.question, ctx=runner_ctx)
        if response is None:
            failures.append(
                {"index": item.index, "error": error, "question": item.question}
            )
            continue
        correct = judgements.get(item.index, item.correct)
        answers.append(
            _to_answer(
                response,
                correct=correct,
                judged_by=runner_ctx.judged_by if correct is not None else None,
            )
        )

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

    metric = accuracy(tuple(answers))
    if metric.value is None:
        return CriterionResult(
            criterion=C_MULTIHOP,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="gold-multihop-v1"),
            blocked_by="A3：无已判分答案（请用 --judgements 提供人工判分，脚本不自动判分）",
            verdict=Verdict.INDETERMINATE,
            detail={"asked": len(items), "judged": 0},
        )
    status, reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True, corpus_is_final=False
    )
    return CriterionResult(
        criterion=C_MULTIHOP,
        status=status,
        value=metric.value,
        provenance=_provenance(
            runner_ctx, dataset_version="gold-multihop-v1", notes=reason
        ),
        threshold=0.80,
        threshold_source="calibrated",  # 0.80 来自矩阵，非 provisional
        verdict=judge(metric.value, threshold=0.80, threshold_source="calibrated"),
        detail={
            "asked": len(items),
            "judged": sum(1 for a in answers if a.correct is not None),
            "judged_by": runner_ctx.judged_by,
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


def eval_single_doc_cost(ctx: dict[str, Any]) -> CriterionResult:
    """**C3-a 单文档成本**（TBD-7）：**阈值已定、值还没有**。

    ``P5-M6`` 之前没有 ``cost_metrics`` ⇒ **无真实分母** ⇒ 状态仍是 ``BLOCKED``
    （``value=null``，**不是** 0）。但**阈值与来源照实带出**——
    「判据存在、阈值未校准」和「还没做」在报告里必须长得不一样，
    否则 TBD-7 永远停在"不可判"的死状态（D2 的裁决理由）。
    """
    runner_ctx: RunnerContext = ctx["ctx"]
    ceiling, source = resolve_cost_ceiling()
    return CriterionResult(
        criterion=C_COST,
        status=CriterionStatus.BLOCKED,
        value=None,
        provenance=_provenance(
            runner_ctx,
            dataset_version="n/a（cost_metrics 未落库，无分母）",
            kg_version="n/a",
            corpus="n/a（无成本数据）",
        ),
        unit=UNIT_TOKEN_PER_DOC,
        blocked_by="P5-M6（cost_metrics 表未建、token 未落库 ⇒ 无真实分母）",
        threshold=float(ceiling),
        threshold_source=source,
        verdict=Verdict.INDETERMINATE,
        detail={
            "ceiling": ceiling,
            "ceiling_source": source,
            "note": "阈值来自 config 推算（provisional），**不是**达标线；"
            "校准命令 scripts/eval_acceptance.py --calibrate",
        },
    )


def eval_incremental_cost_ratio(ctx: dict[str, Any]) -> CriterionResult:
    """**C3-b 增量 / 全量成本比**：阈值按矩阵「显著 < 1.00」（**D3：不落 config**）。"""
    runner_ctx: RunnerContext = ctx["ctx"]
    return CriterionResult(
        criterion=C_COST_RATIO,
        status=CriterionStatus.BLOCKED,
        value=None,
        provenance=_provenance(
            runner_ctx,
            dataset_version="n/a（无增量重算，无分母）",
            kg_version="n/a",
            corpus="n/a（无成本数据）",
        ),
        blocked_by="P5-M6（增量重算未实现）",
        threshold=COST_RATIO_SIGNIFICANT,
        threshold_source=THRESHOLD_CALIBRATED,
        verdict=Verdict.INDETERMINATE,
        detail={
            "threshold_origin": "矩阵 §5.1「显著 < 1.00」，人工裁决定值（非实测推算）",
            "note": "D3：本阈值**不落 config**（无真实消费者 ⇒ 落了即幽灵配置）",
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

    graph_answers = _judged_answers(
        snapshot.answers,
        snapshot.answered_indices,
        runner_ctx.judgements,
        runner_ctx.judged_by,
    )
    graph_metric = accuracy(graph_answers)

    baseline_error, baseline_answers, baseline_indices = _run_baseline_side(runner_ctx)
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
        )
    if baseline_error is not None:
        return _c1_unknown(runner_ctx, f"基线侧不可用：{baseline_error}")
    if baseline_metric.value is None:  # type: ignore[union-attr]
        return _c1_unknown(
            runner_ctx,
            "A3：基线侧没有一题被人工判分（用 --baseline-judgements 提供）；"
            "只判图谱侧 ⇒ 增益无从计算",
            awaiting_baseline=_awaiting_judgement(baseline_answers, baseline_indices),
        )

    #: 可比性前置断言（此处才装 embedder：缺 key ⇒ 上面会先以 baseline_error 返回）
    from app.evaluation.baseline import comparability_error  # noqa: PLC0415

    embedder = _build_embedder_or_none()
    graph_spec, base_spec, _pool_ref, _pool = _load_pool_and_specs(runner_ctx, embedder)
    incomparable = comparability_error(graph_spec, base_spec)
    if incomparable is not None:
        return _c1_unknown(
            runner_ctx,
            f"L10-A1 反向守卫：{incomparable}",
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
        f"{C_GAIN}: 需要 RAG 基线检索的定义与实现（A1 待裁决）",
        f"{C_COST} / {C_COST_RATIO}: 需要 P5-M6 落 cost_metrics 与增量重算",
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
