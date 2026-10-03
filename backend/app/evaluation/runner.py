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

from app.evaluation.affiliation import DEFAULT_NON_MEMBER_PREFIXES
from app.evaluation.criteria import (
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
    dataset_versions,
    load_affiliation_gold,
    load_affiliation_meta,
    load_fixture_baseline,
    load_manifest,
    load_multihop_set,
    load_question_set,
)
from app.evaluation.metrics import (
    AnswerRecord,
    CitationRef,
    Finding,
    accuracy,
    citation_coverage,
    findings_false_positive_rate,
    findings_recall,
    graph_gain,
)

#: 判据名（**唯一真源**；与矩阵 §5.1 的 C1–C3 对应）。
C_MULTIHOP = "multihop_accuracy"
C_CITATION = "c2_c_citation_coverage"
C_GAIN = "c1_graph_gain"
C_RECALL = "c2_a_hidden_relation_recall"
C_FPR = "c2_b_false_positive_rate"
C_COST = "c3_a_single_doc_cost"
C_COST_RATIO = "c3_b_incremental_cost_ratio"

ALL_CRITERIA = (
    C_GAIN,
    C_MULTIHOP,
    C_RECALL,
    C_FPR,
    C_CITATION,
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
        rubric=str(manifest.get("rubric", {}).get("id", "rubric-v1")),
        notes=extra.get("notes"),
    )


# ---------------------------------------------------------------------------
# 判据执行器
# ---------------------------------------------------------------------------


def eval_citation_coverage(ctx: dict[str, Any]) -> CriterionResult:
    """**C2-c 引用覆盖率**（硬约束 1.00）：真跑 M3 问答链路。"""
    runner_ctx: RunnerContext = ctx["ctx"]
    if runner_ctx.mode != "live":
        return CriterionResult(
            criterion=C_CITATION,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v3"),
            blocked_by="需 live 模式（POST /api/v1/agent/query）；offline 不产出判据数字",
            verdict=Verdict.INDETERMINATE,
        )

    questions = load_question_set()
    answers: list[AnswerRecord] = []
    refusals: list[dict[str, Any]] = []
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
        if bool(response.get("refused")) != item.should_refuse:
            refusals.append(
                {
                    "index": item.index,
                    "expected": item.should_refuse,
                    "actual": bool(response.get("refused")),
                    "question": item.question,
                }
            )

    if not answers:
        #: **链路不可用**：不出数（0 会被读成"覆盖率为 0"），如实标 UNKNOWN。
        first = failures[0]["error"] if failures else "无响应"
        return CriterionResult(
            criterion=C_CITATION,
            status=CriterionStatus.UNKNOWN,
            value=None,
            provenance=_provenance(runner_ctx, dataset_version="controlled-qset-v3"),
            blocked_by=(
                f"链路不可用：{len(failures)}/{len(questions)} 题请求失败（首错：{first}）"
                "——常见原因：① 后端未起或 EVAL_BASE_URL 不对；"
                "② PG 无 ready 的 kg_version（演示数据未重建）"
            ),
            verdict=Verdict.INDETERMINATE,
            detail={"failures": failures, "asked": len(questions)},
        )

    metric = citation_coverage(tuple(answers), include_refused=False)
    strict = citation_coverage(tuple(answers), include_refused=False, require_span=True)
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
            dataset_version="controlled-qset-v3",
            kg_version=", ".join(sorted(kg_versions)),
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
            "request_failures": failures,
            "coverage_require_span": strict.value,
            "kg_versions": sorted(kg_versions),
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


def _affiliation_blocked_by() -> tuple[str, bool]:
    """C2-a / C2-b 的阻塞原因（``("", True)`` = 不阻塞，可出数）。

    **2026-10-03 已核对**：真机样本（``AffiliationService.detect``）确认
    gold 与疑点输出的 id 空间**同构**（图节点 id），逐组比对通过
    ⇒ 数据文件置 ``verified_against_live_output=true`` ⇒ 本函数不再阻塞。

    保留本函数的原因：**未核对就比对 = 全不命中 = 召回被读成 0**，
    会误触发反证 F2。这条闸不能拆，只能由数据文件的标志位放行。
    """
    space = load_affiliation_meta().get("entity_id_space", {})
    verified = bool(space.get("verified_against_live_output", False))
    if not verified:
        return (
            f"gold-affiliation-v1 的实体 id 空间({space.get('space')})"
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
    meta = load_affiliation_meta()
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
    gold = load_affiliation_gold()
    meta = load_affiliation_meta()

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
    status, reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True, corpus_is_final=False
    )
    #: A8：阈值来自 spec，但**语料规模不足**（8/60/30/9 vs 200/500/100/20）
    #: ⇒ 这里的「达标」**不是** spec 验收结论 ⇒ 走 provisional，不给裸 PASS。
    caveat = (
        "A8：阈值取自 spec，但演示语料规模不足（README §5 明示不宣称召回 ≥ 0.80 / "
        "误报 ≤ 0.15）⇒ 达标也只记 PASS(provisional)，不作 spec 验收结论"
    )
    shared_status = status if recall.value is not None else CriterionStatus.UNKNOWN

    return (
        CriterionResult(
            criterion=C_RECALL,
            status=shared_status,
            value=recall.value,
            provenance=_provenance(
                runner_ctx,
                dataset_version=str(meta.get("version") or "gold-affiliation-v1"),
                kg_version=str(meta.get("kg_version")),
                corpus="demo/affiliation（合成演示语料，9 组植入）",
                notes="; ".join(x for x in (reason, caveat) if x),
            ),
            blocked_by=None
            if recall.value is not None
            else (recall.reason or "无分母"),
            threshold=0.80,
            threshold_source="provisional",  # A8：语料规模不足 ⇒ 达标不构成验收结论
            verdict=judge(recall.value, threshold=0.80, threshold_source="provisional"),
            detail={
                "gold_count": len(gold),
                "detected_count": len(findings),
                "matched": len(
                    {f.match_key("type_and_members") for f in gold}
                    & {f.match_key("type_and_members") for f in findings}
                ),
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
                dataset_version=str(meta.get("version") or "gold-affiliation-v1"),
                kg_version=str(meta.get("kg_version")),
                corpus="demo/affiliation（合成演示语料，9 组植入）",
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
            ),
            detail={
                "gold_count": len(gold),
                "detected_count": len(findings),
                "spurious": len(
                    {f.match_key("type_and_members") for f in findings}
                    - {f.match_key("type_and_members") for f in gold}
                ),
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


def _register_builtin_criteria() -> None:
    """注册内置判据（**唯一真源**：新增判据必须在此登记）。"""
    for name, evaluator in (
        (C_CITATION, eval_citation_coverage),
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
    for name, reason in (
        (C_GAIN, "baseline-not-implemented（A1：RAG 基线检索未实现，C1 分母不存在）"),
        (C_COST, "P5-M6（cost_metrics 表未建，token 未落库）"),
        (C_COST_RATIO, "P5-M6（增量重算未实现）"),
    ):
        if name not in _registered():
            register_criterion(name, PlaceholderEvaluator(name, blocked_by=reason))


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
    "RunnerContext",
    "ask",
    "dataset_version_map",
    "gold_findings",
    "question_count",
    "run",
    "self_test",
    "upgrade_todo",
]
