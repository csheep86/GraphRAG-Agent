"""`app/evaluation/metrics.py` 的边界用例（**E1.2**：指标口径必须被 CI 真测到）。

为什么单测要钉这么细：这些边界正是"数字看上去对、其实没测出来"的高发地——

- **空集 / 零除**（A7）：返回 ``0`` 会被读成"召回为 0" ⇒ 误触发反证 **F2**；
- **并列与去重**：现脚本踩过「并列退化为 ``chunk_id`` 字典序 ≈ 随机抽样」的坑；
- **拒答是否入分母**（A6）：矩阵字面与现脚本实现**不一致**，两档都要有结论；
- **匹配口径**（A2）与**去重口径**（A5）：口径一变数字就变，必须各自钉死。
"""

from __future__ import annotations

import pytest

from app.evaluation.metrics import (
    UNIT_TOKEN_PER_DOC,
    AnswerRecord,
    CitationRef,
    DocumentCostRecord,
    Finding,
    Relation,
    accuracy,
    citation_coverage,
    dedupe_document_costs,
    false_positive_rate,
    findings_false_positive_rate,
    findings_recall,
    graph_gain,
    recall,
    single_doc_cost,
)


def _rel(head: str, tail: str, rtype: str = "SHARE_LEGAL_PERSON") -> Relation:
    return Relation(head_id=head, tail_id=tail, relation_type=rtype)


# ---------------------------------------------------------------------------
# C2-a 召回（A2 匹配口径 / A7 零除）
# ---------------------------------------------------------------------------


def test_recall_empty_gold_is_none_not_zero() -> None:
    """空 gold ⇒ ``None`` + reason：**严禁**返回 0（0 会被读成"召回为 0"）。"""
    result = recall((), (_rel("A", "B"),))
    assert result.value is None
    assert "gold 为空" in (result.reason or "")


def test_recall_full_hit_is_one() -> None:
    gold = (_rel("A", "B"), _rel("C", "D"))
    detected = (_rel("A", "B"), _rel("C", "D"))
    assert recall(gold, detected).value == 1.0


def test_recall_is_direction_sensitive() -> None:
    """方向敏感：`(A→B)` 与 `(B→A)` **不等价**。"""
    gold = (_rel("A", "B"),)
    assert recall(gold, (_rel("A", "B"),)).value == 1.0
    assert recall(gold, (_rel("B", "A"),)).value == 0.0


def test_recall_match_rule_changes_result() -> None:
    """A2：三种匹配口径给出的结论**不同** —— 口径必须显式写在结果里。"""
    gold = (Relation("A", "B", "R1", head_name="甲", tail_name="乙"),)
    detected = (Relation("A", "B", "R2", head_name="甲", tail_name="乙"),)

    assert recall(gold, detected, match_rule="triple").value == 0.0  # 关系类型不同
    assert recall(gold, detected, match_rule="entity_pair").value == 1.0  # 忽略类型
    assert recall(gold, detected, match_rule="canonical_name").value == 0.0
    assert recall(gold, detected).options["match_rule"] == "triple"


def test_recall_dedupe_is_deterministic() -> None:
    """重复项（同键）只算一次；**且**同键重复不改变顺序性结论。"""
    gold = (_rel("A", "B"), _rel("A", "B"), _rel("C", "D"))
    detected = (_rel("A", "B"), _rel("A", "B"))
    # gold 去重后 2 条，命中 1 条 ⇒ 0.5（不是 1/3 也不是 2/2）
    assert recall(gold, detected).value == 0.5


# ---------------------------------------------------------------------------
# C2-b 误报率（A7：0/0 不是 0）
# ---------------------------------------------------------------------------


def test_fpr_empty_detected_is_none_not_zero() -> None:
    result = false_positive_rate((), (_rel("A", "B"),))
    assert result.value is None
    assert "识别出总数为 0" in (result.reason or "")


def test_fpr_zero_when_all_detected_are_in_gold() -> None:
    gold = (_rel("A", "B"), _rel("C", "D"))
    detected = (_rel("A", "B"), _rel("C", "D"))
    assert false_positive_rate(detected, gold).value == 0.0


def test_fpr_counts_spurious_only() -> None:
    gold = (_rel("A", "B"),)
    detected = (_rel("A", "B"), _rel("X", "Y"))
    assert false_positive_rate(detected, gold).value == 0.5


# ---------------------------------------------------------------------------
# C1 增益（A7：基线为 0 ⇒ 不返回 inf）
# ---------------------------------------------------------------------------


def test_gain_basic() -> None:
    """(0.88 − 0.80) / 0.80 = 0.10（浮点 ⇒ 用 approx，不写死等值）。"""
    assert graph_gain(0.88, 0.80).value == pytest.approx(0.1)


def test_gain_zero_baseline_is_none_not_inf() -> None:
    result = graph_gain(0.88, 0.0)
    assert result.value is None
    assert "≤ 0" in (result.reason or "")


def test_gain_missing_side_is_none() -> None:
    """A1：基线侧缺失（RAG 基线未实现）⇒ ``None``，不是"增益无穷大"。"""
    assert graph_gain(0.88, None).value is None
    assert graph_gain(None, 0.8).value is None


# ---------------------------------------------------------------------------
# C2-c 引用覆盖率（A6：拒答是否入分母）
# ---------------------------------------------------------------------------


def _answer(refused: bool, n: int = 1, *, span: bool = False) -> AnswerRecord:
    return AnswerRecord(
        refused=refused,
        citations=tuple(CitationRef(f"chunk-{i}", has_span=span) for i in range(n)),
    )


def test_coverage_full_when_all_answers_cited() -> None:
    answers = (_answer(False), _answer(False, 2))
    assert citation_coverage(answers).value == 1.0


def test_coverage_excludes_non_chunk_citations() -> None:
    """引用 ``chunk_id`` 不以 ``chunk-`` 开头 ⇒ 不算"可回溯"（与现脚本同口径）。"""
    bad = AnswerRecord(refused=False, citations=(CitationRef("doc-1"),))
    assert citation_coverage((bad,)).value == 0.0


def test_coverage_refused_excluded_by_default_matches_legacy_script() -> None:
    """默认档与现 `eval_controlled_qset.py` 一致：分母**排除**拒答。"""
    answers = (_answer(False), AnswerRecord(refused=True, citations=()))
    assert citation_coverage(answers).value == 1.0


def test_coverage_refused_included_lowers_result() -> None:
    """A6 另一档：拒答计入分母 ⇒ 拒答无引用，必然拉低覆盖率。"""
    answers = (_answer(False), AnswerRecord(refused=True, citations=()))
    result = citation_coverage(answers, include_refused=True)
    assert result.value == 0.5
    assert result.options["include_refused"] == "True"


def test_coverage_require_span_flag() -> None:
    """矩阵原文要求"含可回溯 span"：``require_span=True`` 时 chunk 前缀不够。"""
    answers = (_answer(False),)
    assert citation_coverage(answers, require_span=True).value == 0.0
    assert (
        citation_coverage((_answer(False, span=True),), require_span=True).value == 1.0
    )


def test_coverage_empty_denominator_is_none() -> None:
    result = citation_coverage((AnswerRecord(refused=True),))
    assert result.value is None
    assert "分母为 0" in (result.reason or "")


# ---------------------------------------------------------------------------
# C3-a 单文档成本（A4 单位 / A5 去重 / A7 零除）
# ---------------------------------------------------------------------------


def test_single_doc_cost_unit_is_token_per_doc() -> None:
    records = (DocumentCostRecord("d1", 1000),)
    result = single_doc_cost(records)
    assert result.unit == UNIT_TOKEN_PER_DOC
    assert result.value == 1000.0


def test_single_doc_cost_no_success_is_none() -> None:
    """全是失败记录 ⇒ ``None``（不返回 0）。"""
    records = (DocumentCostRecord("d1", 1000, outcome="failed"),)
    result = single_doc_cost(records)
    assert result.value is None
    assert "无成功记录" in (result.reason or "")


def test_single_doc_cost_dedup_rules_differ() -> None:
    """A5：同一文档重算两次，三种口径给出三个数 —— 口径必须显式。"""
    records = (
        DocumentCostRecord("d1", 1000, sequence=0),
        DocumentCostRecord("d1", 3000, sequence=1),  # 重算
    )
    assert single_doc_cost(records).value == 3000.0  # last_success（默认）
    assert single_doc_cost(records, rule="first_success").value == 1000.0
    assert single_doc_cost(records, rule="sum_all").value == 4000.0
    assert single_doc_cost(records).options["dedup_rule"] == "last_success"


def test_single_doc_cost_ignores_failed_and_superseded() -> None:
    records = (
        DocumentCostRecord("d1", 1000, outcome="completed", sequence=0),
        DocumentCostRecord("d1", 9999, outcome="failed", sequence=1),
        DocumentCostRecord("d1", 8888, outcome="superseded", sequence=2),
    )
    assert dedupe_document_costs(records) == {"d1": 1000}


def test_single_doc_cost_averages_across_documents() -> None:
    records = (DocumentCostRecord("d1", 1000), DocumentCostRecord("d2", 3000))
    assert single_doc_cost(records).value == 2000.0


# ---------------------------------------------------------------------------
# C2-a / C2-b 的**组级**口径（M4 疑点不是二元组）
# ---------------------------------------------------------------------------


def test_findings_recall_is_order_insensitive() -> None:
    """成员顺序不同仍应命中（持股环的 4 个主体没有先天顺序）。"""
    gold = (Finding("cycle", ("S007", "S009", "S011")),)
    detected = (Finding("cycle", ("S011", "S007", "S009")),)
    assert findings_recall(gold, detected).value == 1.0


def test_findings_recall_requires_type_match_by_default() -> None:
    """默认口径「type + 成员」：类型不同 ⇒ 不命中。"""
    gold = (Finding("shared_legal_rep", ("S004", "S010")),)
    detected = (Finding("shared_address", ("S004", "S010")),)
    assert findings_recall(gold, detected).value == 0.0
    assert findings_recall(gold, detected, match_rule="members_only").value == 1.0


def test_findings_recall_empty_gold_is_none_not_zero() -> None:
    result = findings_recall((), (Finding("cycle", ("S001", "S002")),))
    assert result.value is None
    assert "gold 为空" in (result.reason or "")


def test_findings_fpr_empty_detected_is_none_not_zero() -> None:
    result = findings_false_positive_rate((), (Finding("cycle", ("S001", "S002")),))
    assert result.value is None
    assert "识别出总数为 0" in (result.reason or "")


def test_findings_fpr_counts_spurious_groups() -> None:
    gold = (Finding("shared_legal_rep", ("S004", "S010")),)
    detected = (
        Finding("shared_legal_rep", ("S004", "S010")),
        Finding("shared_phone", ("S002", "S013")),
    )
    assert findings_false_positive_rate(detected, gold).value == 0.5


def test_findings_duplicate_detection_counts_once() -> None:
    """同一疑点重复报 ⇒ 去重后只算一次（否则误报率会被重复上报灌水）。"""
    gold = (Finding("shared_legal_rep", ("S004", "S010")),)
    detected = (
        Finding("shared_legal_rep", ("S004", "S010")),
        Finding("shared_legal_rep", ("S010", "S004")),
    )
    assert findings_false_positive_rate(detected, gold).value == 0.0


# ---------------------------------------------------------------------------
# 答对率（A3：脚本不做关键词判分）
# ---------------------------------------------------------------------------


def test_accuracy_none_when_nothing_judged() -> None:
    """未判分 ⇒ ``None``，不是 0（否则"还没判"会被读成"全答错"）。"""
    result = accuracy((AnswerRecord(refused=False),))
    assert result.value is None
    assert "无已判分答案" in (result.reason or "")


def test_accuracy_counts_only_judged() -> None:
    answers = (
        AnswerRecord(refused=False, correct=True, judged_by="architect"),
        AnswerRecord(refused=False, correct=False, judged_by="architect"),
        AnswerRecord(refused=False),  # 未判分 ⇒ 不入分母
    )
    assert accuracy(answers).value == 0.5
