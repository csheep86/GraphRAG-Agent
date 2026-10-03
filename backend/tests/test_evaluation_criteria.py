"""`app/evaluation/criteria.py` 四态状态机的守卫（**E1.3**）。

核心要钉住两件事（对应 `changes/P0-m6-eval/proposal.md` §4.2）：

1. **`BLOCKED` 结构上不许带数字** —— `0.0` 会被读成"召回为 0" ⇒ 误触发反证 **F2**；
   靠**构造即报错**（`__post_init__`），不靠调用方自觉；
2. **阈值来源为 provisional 时不得给纯 PASS** —— 防"阈值没校准却宣称达标"（§5.2 第 2 / 3 条）。
"""

from __future__ import annotations

import pytest

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
    unregister_criterion,
)

PROV = Provenance(
    dataset_version="qset-v3",
    mode="offline",
    git_hash="820e6f57",
    kg_version="attendance-demo-v1",
)


# ---------------------------------------------------------------------------
# 构造即校验：BLOCKED 不得带数字
# ---------------------------------------------------------------------------


def test_blocked_with_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="BLOCKED 不得携带数字"):
        CriterionResult(
            criterion="c3_a",
            status=CriterionStatus.BLOCKED,
            value=0.0,
            provenance=PROV,
            blocked_by="P5-M6",
        )


def test_blocked_without_blocked_by_is_rejected() -> None:
    with pytest.raises(ValueError, match="blocked_by"):
        CriterionResult(
            criterion="c3_a",
            status=CriterionStatus.BLOCKED,
            value=None,
            provenance=PROV,
        )


def test_measured_without_value_is_rejected() -> None:
    """无值却声称 MEASURED = 把"没测出来"写成"测了"。"""
    with pytest.raises(ValueError, match="必须有值"):
        CriterionResult(
            criterion="c2_c",
            status=CriterionStatus.MEASURED,
            value=None,
            provenance=PROV,
        )


def test_unknown_with_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="UNKNOWN 不得携带数字"):
        CriterionResult(
            criterion="c2_a",
            status=CriterionStatus.UNKNOWN,
            value=0.8,
            provenance=PROV,
        )


def test_threshold_source_without_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="threshold_source"):
        CriterionResult(
            criterion="c3_a",
            status=CriterionStatus.MEASURED,
            value=100.0,
            provenance=PROV,
            threshold_source=THRESHOLD_PROVISIONAL,
        )


def test_valid_blocked_result() -> None:
    result = CriterionResult(
        criterion="c3_b",
        status=CriterionStatus.BLOCKED,
        value=None,
        provenance=PROV,
        blocked_by="P5-M6",
        verdict=Verdict.INDETERMINATE,
    )
    assert result.value is None
    assert result.blocked_by == "P5-M6"


# ---------------------------------------------------------------------------
# 三条自证线（§4.2 第 3 条）
# ---------------------------------------------------------------------------


def test_resolve_status_link_missing_is_blocked() -> None:
    status, reason = resolve_status(
        link_ready=False, dataset_ready=True, rubric_defined=True
    )
    assert status is CriterionStatus.BLOCKED
    assert reason == "被测链路未实现"


def test_resolve_status_dataset_missing_is_unknown() -> None:
    status, _ = resolve_status(
        link_ready=True, dataset_ready=False, rubric_defined=True
    )
    assert status is CriterionStatus.UNKNOWN


def test_resolve_status_rubric_missing_is_unknown() -> None:
    status, _ = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=False
    )
    assert status is CriterionStatus.UNKNOWN


def test_resolve_status_non_final_corpus_is_provisional() -> None:
    status, reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True, corpus_is_final=False
    )
    assert status is CriterionStatus.MEASURED_PROVISIONAL
    assert "非终局" in (reason or "")


def test_resolve_status_all_ready_is_measured() -> None:
    status, reason = resolve_status(
        link_ready=True, dataset_ready=True, rubric_defined=True, corpus_is_final=True
    )
    assert status is CriterionStatus.MEASURED
    assert reason is None


# ---------------------------------------------------------------------------
# 判定与阈值来源（§5.2 三重防假绿）
# ---------------------------------------------------------------------------


def test_judge_pass_with_calibrated_threshold() -> None:
    """成本类指标是**上界**（越小越好）：低于阈值才 PASS。"""
    assert judge(10_000.0, threshold=32_000, higher_is_better=False) is Verdict.PASS


def test_judge_provisional_threshold_downgrades_pass() -> None:
    """**关键防假绿**：阈值未校准 ⇒ 只给 `PASS(provisional)`，不宣称达标。"""
    verdict = judge(
        10_000.0,
        threshold=32_000,
        threshold_source=THRESHOLD_PROVISIONAL,
        higher_is_better=False,
    )
    assert verdict is Verdict.PASS_PROVISIONAL
    assert "provisional" in verdict.value


def test_judge_env_override_is_plain_pass() -> None:
    """人在 `.env` 显式覆盖 ⇒ 视为已裁决，给纯 PASS。"""
    assert (
        judge(
            10_000.0,
            threshold=32_000,
            threshold_source=THRESHOLD_ENV_OVERRIDE,
            higher_is_better=False,
        )
        is Verdict.PASS
    )


def test_judge_calibrated_threshold_is_plain_pass() -> None:
    assert (
        judge(
            10_000.0,
            threshold=32_000,
            threshold_source=THRESHOLD_CALIBRATED,
            higher_is_better=False,
        )
        is Verdict.PASS
    )


def test_judge_fail_when_over_ceiling() -> None:
    assert (
        judge(
            50_000.0,
            threshold=32_000,
            threshold_source=THRESHOLD_CALIBRATED,
            higher_is_better=False,
        )
        is Verdict.FAIL
    )


def test_judge_indeterminate_when_value_or_threshold_missing() -> None:
    """值缺失或阈值未定 ⇒ 不判（既不是 PASS 也不是 FAIL，避免死状态被读成达标）。"""
    assert judge(None, threshold=32_000) is Verdict.INDETERMINATE
    assert judge(100.0, threshold=None) is Verdict.INDETERMINATE


def test_judge_lower_is_better() -> None:
    """误报率这类"越小越好"的指标：低于阈值才 PASS。"""
    assert judge(0.05, threshold=0.15, higher_is_better=False) is Verdict.PASS
    assert judge(0.30, threshold=0.15, higher_is_better=False) is Verdict.FAIL


# ---------------------------------------------------------------------------
# 占位执行点 = 与 P5-M6 的交接面
# ---------------------------------------------------------------------------


def test_placeholder_evaluator_never_yields_numbers() -> None:
    evaluator = PlaceholderEvaluator("c3_a", blocked_by="P5-M6")
    result = evaluator(
        {"dataset_version": "qset-v3", "mode": "offline", "git_hash": "x"}
    )
    assert result.status is CriterionStatus.BLOCKED
    assert result.value is None
    assert result.blocked_by == "P5-M6"
    assert result.verdict is Verdict.INDETERMINATE


def test_criteria_registry_rejects_duplicate_and_allows_replace() -> None:
    """登记唯一真源：**不许**静默覆盖；替换须先显式 unregister（P5-M6 的替换动作）。"""
    register_criterion("tmp_crit", PlaceholderEvaluator("tmp_crit", blocked_by="X"))
    with pytest.raises(ValueError, match="已登记"):
        register_criterion("tmp_crit", PlaceholderEvaluator("tmp_crit", blocked_by="Y"))
    unregister_criterion("tmp_crit")
    register_criterion("tmp_crit", PlaceholderEvaluator("tmp_crit", blocked_by="Z"))
    unregister_criterion("tmp_crit")
