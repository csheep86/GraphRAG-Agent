"""**A8 扩标（P6-A）**：语料生成器 + 统计口径（Clopper-Pearson 单侧界）的护栏。

**为什么要这些用例**：A8 裁决的核心是「**判定用置信界，不只用点估计**」——
9/9 的召回点估计 = 1.00，而它的 95% 下界只有 **0.717 < 0.80**
⇒ "满分"根本支持不了"达标"。这条链路里任何一环松了（界算错 / 方向反了 /
判定只看点估计），都会把"判不出"读成"已达标"。

**两类用例**：
- 纯逻辑（**不需要 Neo4j**）：界值、判定语义、生成器确定性 / 规模 / 文本证据；
- 真图端到端（需 `GRAPH_REAL_NEO4J_*`，CI 由 job env 注入）：v2 语料上真的
  20/20 全中、误报 0 条，且**界达标**。
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from app.evaluation.criteria import Verdict, judge
from app.evaluation.dataset import load_affiliation_gold, load_affiliation_meta
from app.evaluation.stats import (
    DEFAULT_ALPHA,
    clopper_pearson_lower,
    clopper_pearson_upper,
    one_sided_bound,
)

_GRAPH_ENV = (
    "GRAPH_REAL_NEO4J_URI",
    "GRAPH_REAL_NEO4J_USER",
    "GRAPH_REAL_NEO4J_PASSWORD",
)
_REAL_GRAPH = all(os.environ.get(name) for name in _GRAPH_ENV)
_SKIP_REASON = f"需要真 Neo4j（设 {_GRAPH_ENV}）；CI 由 job env 注入"

#: 裁决表给的**近似**值 vs 本批**精确**实算值（差异见集成日志 §4）
#: —— 这里断言的是实算值（近似值偏乐观，会让"达标"被误判为成立）
LOWER_9_9 = 0.7169
LOWER_16_20 = 0.5990
LOWER_19_20 = 0.7839
LOWER_20_20 = 0.8609
UPPER_0_9 = 0.2831
UPPER_0_20 = 0.1391
UPPER_1_20 = 0.2161


# --------------------------------------------------------------------------- #
# 一、置信界（纯逻辑）
# --------------------------------------------------------------------------- #
def test_lower_bound_matches_reference_values() -> None:
    """下界必须等于 Clopper-Pearson **精确**值。

    ⚠️ 这组数字**推翻了** L10-A8 裁决表里的近似值（那里写 19/20 ≈ 0.82）：
    精确值是 **0.7839 < 0.80** ⇒ **19/20 并不支持「召回 ≥ 0.80」**，
    20 组必须 **20/20 全中**（下界 0.8609）才支持。门槛比裁决表**更严**。
    """
    assert clopper_pearson_lower(9, 9) == pytest.approx(LOWER_9_9, abs=1e-3)
    assert clopper_pearson_lower(16, 20) == pytest.approx(LOWER_16_20, abs=1e-3)
    assert clopper_pearson_lower(19, 20) == pytest.approx(LOWER_19_20, abs=1e-3)
    assert clopper_pearson_lower(20, 20) == pytest.approx(LOWER_20_20, abs=1e-3)


def test_upper_bound_matches_reference_values() -> None:
    """上界（误报用）：0/9 ⇒ 0.283（**远大于** 0.15 ⇒ 9 组判不出误报达标）。"""
    assert clopper_pearson_upper(0, 9) == pytest.approx(UPPER_0_9, abs=1e-3)
    assert clopper_pearson_upper(0, 20) == pytest.approx(UPPER_0_20, abs=1e-3)
    assert clopper_pearson_upper(1, 20) == pytest.approx(UPPER_1_20, abs=1e-3)


def test_nine_groups_cannot_support_the_threshold() -> None:
    """**A8 的本体结论**：9 组即便满分，也**不支持**召回 ≥ 0.80 / 误报 ≤ 0.15。

    这条是全批的理由所在——把它删了，A8 就退化成"语料大了一点"。
    """
    assert clopper_pearson_lower(9, 9) < 0.80, "9/9 的下界必须 < 0.80（否则 A8 不成立）"
    assert clopper_pearson_upper(0, 9) > 0.15, "0/9 的误报上界必须 > 0.15"


def test_twenty_groups_need_all_hits() -> None:
    """20 组：19/20 **不够**（0.7839 < 0.80），20/20 才够（0.8609）。"""
    assert clopper_pearson_lower(19, 20) < 0.80
    assert clopper_pearson_lower(20, 20) >= 0.80
    assert clopper_pearson_upper(0, 20) <= 0.15
    assert clopper_pearson_upper(1, 20) > 0.15, "误报 1 条即不成立"


def test_bounds_are_monotonic_and_bounded() -> None:
    lower = [clopper_pearson_lower(k, 20) for k in range(21)]
    upper = [clopper_pearson_upper(k, 20) for k in range(21)]
    assert lower == sorted(lower), "命中越多，下界必须越高"
    assert upper == sorted(upper), "误报越多，上界必须越高"
    assert lower[0] == 0.0 and upper[20] == 1.0
    assert 0.0 <= lower[-1] <= 1.0


def test_direction_helper_picks_the_right_side() -> None:
    """越高越好 ⇒ 下界；越低越好 ⇒ 上界（**方向搞反就是假绿**）。"""
    assert one_sided_bound(20, 20, higher_is_better=True) == pytest.approx(
        clopper_pearson_lower(20, 20)
    )
    assert one_sided_bound(0, 20, higher_is_better=False) == pytest.approx(
        clopper_pearson_upper(0, 20)
    )


def test_bounds_reject_bad_input() -> None:
    """无分母 / 越界 ⇒ **报错**，不返回 0（0 会被读成"达标"）。"""
    with pytest.raises(ValueError, match="n 必须"):
        clopper_pearson_lower(1, 0)
    with pytest.raises(ValueError, match="k 必须"):
        clopper_pearson_upper(3, 2)
    assert DEFAULT_ALPHA == 0.05


# --------------------------------------------------------------------------- #
# 二、判定语义：界不达标 ⇒ UNDERPOWERED（**不是** PASS）
# --------------------------------------------------------------------------- #
def test_judge_marks_underpowered_when_bound_fails() -> None:
    """点估计达标但**界**不达标 ⇒ ``UNDERPOWERED``（9/9 = 1.00 正是这种）。"""
    assert judge(1.00, threshold=0.80, ci_bound=LOWER_9_9) is Verdict.UNDERPOWERED, (
        "9 组的满分必须判 UNDERPOWERED——判成 PASS 就把「判不出」读成「已达标」"
    )


def test_judge_passes_only_when_point_and_bound_both_ok() -> None:
    assert judge(1.00, threshold=0.80, ci_bound=LOWER_20_20) is Verdict.PASS
    assert judge(0.90, threshold=0.80, ci_bound=0.70) is Verdict.UNDERPOWERED


def test_judge_fpr_uses_upper_bound() -> None:
    """误报越低越好 ⇒ 看**上界**：点估计 0.0 但上界 0.283 ⇒ UNDERPOWERED。"""
    assert (
        judge(0.0, threshold=0.15, higher_is_better=False, ci_bound=UPPER_0_9)
        is Verdict.UNDERPOWERED
    )
    assert (
        judge(0.0, threshold=0.15, higher_is_better=False, ci_bound=UPPER_0_20)
        is Verdict.PASS
    )
    #: 点估计不达标 ⇒ 无论界如何都 FAIL
    assert (
        judge(0.4, threshold=0.15, higher_is_better=False, ci_bound=0.5) is Verdict.FAIL
    )


def test_runner_marks_v1_underpowered_and_v2_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**接线测试**：同样的"满分"，v1（9 组）判 UNDERPOWERED，v2（20 组）判 PASS。

    为什么要有这条：上面几条测的是 `judge` 本身，而"runner **真的把界传进去了**"
    没人盯——漏传 `ci_bound` 会静默回到"点估计达标即 PASS"（9 组的 1.00 又被读成达标）。
    这里桩掉唯一的 Neo4j 依赖（`_detect_findings`），其余走真实代码路径。
    """
    import app.evaluation.runner as runner

    #: v2 是 ``PASS(provisional)`` **而不是**裸 PASS：阈值 0.80 / 0.15 取自 spec
    #: 但**未校准**（TBD-7）⇒ 按 §5.2 第 3 条不给裸 PASS。这是**刻意的**，不是缺陷。
    for version, expected in (
        ("v1", Verdict.UNDERPOWERED),
        ("v2", Verdict.PASS_PROVISIONAL),
    ):
        gold = load_affiliation_gold(version)
        monkeypatch.setattr(
            runner, "_detect_findings", lambda _ctx, _gold=gold: (_gold, None)
        )
        recall_result, fpr_result = runner._affiliation_results(
            runner.RunnerContext(mode="live", git_hash="test", gold_version=version)
        )
        assert recall_result.value == 1.0, "桩数据应当满分（否则不是满分的情形）"
        assert recall_result.verdict is expected, f"{version} 召回判定应为 {expected}"
        assert fpr_result.verdict is expected, f"{version} 误报判定应为 {expected}"
        assert (recall_result.detail or {}).get("n") == len(gold)
        assert (recall_result.detail or {}).get("corpus_layer") == "L1"


def test_judge_without_bound_keeps_old_behaviour() -> None:
    """不给界 ⇒ 与以前一致（**不给界的判据不得被新语义误伤**）。"""
    assert judge(1.0, threshold=0.80) is Verdict.PASS
    assert judge(0.5, threshold=0.80) is Verdict.FAIL
    assert judge(None, threshold=0.80) is Verdict.INDETERMINATE


# --------------------------------------------------------------------------- #
# 三、生成器与 gold v2（纯逻辑）
# --------------------------------------------------------------------------- #
def test_generator_is_deterministic() -> None:
    """固定 seed ⇒ **字节级**可复现（换语料必须换 seed，否则归因失效）。"""
    from scripts.gen_affiliation_corpus import generate

    first, gold_first = generate()
    second, gold_second = generate()
    assert first == second
    assert gold_first == gold_second


def test_corpus_scale_matches_spec() -> None:
    """spec §3 验收 6：200 合同 / 500 发票 / 100 凭证 / **20 组**。"""
    from scripts.gen_affiliation_corpus import (
        N_CONTRACTS,
        N_INVOICES,
        N_PLANTED_PER_TYPE,
        N_VOUCHERS,
        generate,
        self_check,
    )

    documents, gold = generate()
    assert len(documents["contracts"]) == N_CONTRACTS == 200
    assert len(documents["invoices"]) == N_INVOICES == 500
    assert len(documents["vouchers"]) == N_VOUCHERS == 100
    assert len(gold["findings"]) == 20
    assert self_check(documents, gold) == [], self_check(documents, gold)

    by_type: dict[str, int] = {}
    for finding in gold["findings"]:
        by_type[finding["type"]] = by_type.get(finding["type"], 0) + 1
    assert by_type == {
        kind: N_PLANTED_PER_TYPE
        for kind in (
            "shared_legal_rep",
            "shared_address",
            "shared_phone",
            "cycle",
            "amount_mismatch",
        )
    }, f"五类必须各 4 组（每类 ≥4 ⇒ 共 20），实际 {by_type}"


def test_every_planted_group_has_text_evidence() -> None:
    """**A8 裁决 3**：植入必须有**文本体现**，否则测的仍是"读结构化字段"。"""
    from scripts.gen_affiliation_corpus import generate

    _, gold = generate()
    for finding in gold["findings"]:
        assert finding.get("text_evidence"), f"{finding['type']} 组缺文本证据"
        assert len(finding["text_evidence"]) > 10


def test_gold_v2_node_ids_follow_live_id_space() -> None:
    """成员必须是**图节点 id**（shared_* 恒 2 个主体；共享节点不计入）。"""
    gold = load_affiliation_gold("v2")
    raw = load_affiliation_meta("v2")
    assert raw["entity_id_space"]["verified_against_live_output"] is True
    assert raw["source"]["corpus_layer"] == "L1", "L1 必须标明（不得说成端到端）"
    assert len(gold) == 20
    for finding in gold:
        if finding.type.startswith("shared_"):
            assert len(finding.members()) == 2
            assert all(m.startswith("SUBJECT:") for m in finding.members())
        elif finding.type == "cycle":
            assert 2 <= len(finding.members()) <= 4
            assert all(m.startswith("SUBJECT:") for m in finding.members())
        else:
            prefixes = {m.split(":")[0] for m in finding.members()}
            assert prefixes == {"CONTRACT", "INVOICE", "VOUCHER"}


def test_gold_v1_still_default() -> None:
    """换语料**不得靠默认值悄悄发生**：默认仍是 v1（A8 之前的结论不漂移）。"""
    assert len(load_affiliation_gold()) == 9
    assert load_affiliation_meta()["kg_version"] == "affiliation-demo-v1"


def test_corpus_files_exist_and_carry_text_columns() -> None:
    """入库语料必须带**正文列**（`:Chunk.text` 由整行拼接 ⇒ 正文自动进证据链）。"""
    import csv

    from scripts.gen_affiliation_corpus import DEFAULT_OUT_DIR

    for name, column in (
        ("contracts", "contract_text"),
        ("invoices", "invoice_text"),
        ("vouchers", "voucher_text"),
    ):
        path: Path = DEFAULT_OUT_DIR / f"{name}.csv"
        assert path.exists(), f"{path} 缺失（语料随生成器入库，换版有 git 痕迹）"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert column in rows[0]
        assert all(row[column].strip() for row in rows[:5]), "正文不得为空"


# --------------------------------------------------------------------------- #
# 四、真图端到端（**需要真 Neo4j**）
# --------------------------------------------------------------------------- #
@pytest.fixture
def real_graph(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """把 Neo4j 指向真图库（teardown 必须再 reset 一次，否则单例 driver 泄漏）。"""
    from app.core.config import get_settings
    from app.services.graphs import GraphService

    settings = get_settings()
    monkeypatch.setattr(settings, "neo4j_uri", os.environ[_GRAPH_ENV[0]])
    monkeypatch.setattr(settings, "neo4j_user", os.environ[_GRAPH_ENV[1]])
    monkeypatch.setattr(settings, "neo4j_password", os.environ[_GRAPH_ENV[2]])
    GraphService.reset()
    yield
    GraphService.reset()


@pytest.mark.skipif(not _REAL_GRAPH, reason=_SKIP_REASON)
def test_g25_v2_corpus_meets_thresholds_by_confidence_bound(real_graph: None) -> None:
    """**v2 语料上按界判定达标**（L1 算法层）：20/20 全中 + 误报 0 条。

    为什么敢断言具体数字：语料由固定 seed 生成、检测**只读图、不经 LLM**
    ⇒ 完全确定性（不是"碰巧一次"）。若哪天这里红了，就是**真的退化了**。

    ⚠️ 结论口径：**L1 算法层**达标；**端到端（M2 抽取）未验证**（A8 裁决 4）。
    """
    from app.evaluation.affiliation import findings_from_suspicions
    from app.evaluation.metrics import (
        findings_false_positive_rate,
        findings_recall,
    )
    from app.services.kg import AffiliationService

    gold = load_affiliation_gold("v2")
    meta = load_affiliation_meta("v2")
    space = meta["entity_id_space"]
    suspicions = AffiliationService().detect(
        kg_version=str(meta["kg_version"]),
        org_id=UUID(str(meta["org_id"])),
        limit=500,
    )
    detected = findings_from_suspicions(
        suspicions, non_member_prefixes=tuple(space["non_member_prefixes"])
    )
    recall = findings_recall(gold, detected)
    fpr = findings_false_positive_rate(detected, gold)

    hit = int(recall.options["hit"])
    n_gold = int(recall.options["n"])
    spurious = int(fpr.options["spurious"])
    n_detected = int(fpr.options["n"])

    assert (hit, n_gold) == (20, 20), f"命中 {hit}/{n_gold} ⇒ 召回达标要求 20/20"
    assert spurious == 0, f"误报 {spurious} 条 ⇒ 1 条即上界 > 0.15（不达标）"

    #: **判定用界**（这才是 A8 的本意）
    assert (
        judge(recall.value, threshold=0.80, ci_bound=clopper_pearson_lower(hit, n_gold))
        is Verdict.PASS
    )
    assert (
        judge(
            fpr.value,
            threshold=0.15,
            higher_is_better=False,
            ci_bound=clopper_pearson_upper(spurious, n_detected),
        )
        is Verdict.PASS
    )
