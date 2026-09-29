"""Sprint 9.13 批次 C3：实体消解的单测。

钉死的是 ``specs/m2-extract-kg.md`` **§4.5.1** 的**口径**，不是实现细节：

- 三档边界（0.90 / 0.70）与「< 0.70 **不落表**」；
- **N1** 税号冲突 ⇒ 封顶 0.85 ⇒ **永不 auto_merged**（审计正确性优先于召回）；
- **N2** 多候选 ⇒ 全部降级，不自动合并；
- **N3** 同税号 ⇒ 不产生候选；
- 结构信号**单独出现不产生候选**（同法人 / 同电话是"关联方"证据，不是"同一主体"证据）；
- 合成语料端到端：`auto_merged` 恰好 1 条、N1 反例落 `human_review`、终态 87/90。

全部用例**不连 Neo4j / 不写 PG**（纯函数 + 合成语料干跑）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.kg.entity_resolution import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_THRESHOLD,
    STATUS_AUTO_MERGED,
    STATUS_HUMAN_REVIEW,
    TAX_ID_CONFLICT_CAP,
    SubjectProfile,
    classify,
    generate_candidates,
    name_similarity,
    score_pair,
    structure_bonus,
)
from scripts.ingest_affiliation_sources import (
    CORPUS_DIR,
    MIN_ALIGNMENT_RATE,
    align_sources,
    build_master_index,
    normalize_name,
    read_csv,
    resolve_unaligned,
    validate_corpus,
)


# --------------------------------------------------------------------------- #
# 名称相似度（§4.5.1 S1）
# --------------------------------------------------------------------------- #
def test_name_similarity_identical_and_empty() -> None:
    assert name_similarity("北京恒信达科技", "北京恒信达科技") == 1.0
    assert name_similarity("", "北京恒信达科技") == 0.0
    assert name_similarity("北京恒信达科技", "") == 0.0


def test_name_similarity_one_char_insertion_scores_high() -> None:
    """「武汉市长江智联科技」vs「武汉长江智联科技」：插一个"市"字 ⇒ 仍应判相似。

    这是 §4.5.1 S1 取 ``max(ratio, jaccard)`` 的**理由**：jaccard 对长度差敏感
    （本例只有 0.67），若取平均或只取 jaccard，真实的别名写法会被判成"不像"。
    """
    sim = name_similarity("武汉市长江智联科技", "武汉长江智联科技")
    assert sim >= AUTO_MERGE_THRESHOLD
    assert sim < 1.0


def test_name_similarity_different_companies_not_auto_merged() -> None:
    """「新联达」vs「恒信达」不是同一家：**不得**达到自动合并线。

    （实测 0.714 ⇒ 仍会进人工队列——这是**对的**：审计上"是不是笔误"值得人看一眼，
    判据只挡住"自动合并"这一档，不假装算法能替人下结论。）
    """
    sim = name_similarity("北京新联达科技", "北京恒信达科技")
    assert sim < AUTO_MERGE_THRESHOLD
    assert classify(sim) == STATUS_HUMAN_REVIEW


def test_name_similarity_symmetric() -> None:
    left = name_similarity("天津市滨海华元机械", "天津滨海华元机械")
    right = name_similarity("天津滨海华元机械", "天津市滨海华元机械")
    assert left == pytest.approx(right)


# --------------------------------------------------------------------------- #
# 结构信号（§4.5.1 S2）
# --------------------------------------------------------------------------- #
def _profile(**kwargs: object) -> SubjectProfile:
    base = {
        "subject_id": "SUBJECT:X",
        "norm_name": "北京恒信达科技",
        "tax_id": None,
    }
    base.update(kwargs)  # type: ignore[arg-type]
    return SubjectProfile(**base)  # type: ignore[arg-type]


def test_structure_bonus_caps_at_ten_percent() -> None:
    left = _profile(address="addr", phone="010-1", legal_rep="李强")
    right = _profile(
        subject_id="SUBJECT:Y", address="addr", phone="010-1", legal_rep="李强"
    )
    # 三项全中 = 0.15 ⇒ 被上限压到 0.10（判据明定，不是实现随手写的）
    assert structure_bonus(left, right) == pytest.approx(0.10)


def test_structure_bonus_ignores_missing_values() -> None:
    """缺失即不参与比较——不猜、不填默认值。"""
    left = _profile(address="addr")
    right = _profile(subject_id="SUBJECT:Y", address="addr")
    assert structure_bonus(left, right) == pytest.approx(0.05)


# --------------------------------------------------------------------------- #
# 否决（§4.5.1 第 4 条）
# --------------------------------------------------------------------------- #
def test_n1_tax_id_conflict_caps_similarity_and_blocks_auto_merge() -> None:
    """**N1**：税号都合法且不同 ⇒ 封顶 0.85 ⇒ **永不 auto_merged**。

    这是本判据最要紧的一条：名称完全相同（1.0）也不行——不同统一社会信用代码
    = 法律上不同主体，自动并掉等于抹掉 M4 要找的关联方。
    """
    left = _profile(tax_id="91110108MA01T2W3XX")
    right = _profile(subject_id="SUBJECT:Y", tax_id="91110108MA01T2W4XX")
    similarity, signals = score_pair(left, right)
    assert signals["tax_conflict"] is True
    assert similarity == pytest.approx(TAX_ID_CONFLICT_CAP)
    assert classify(similarity) == STATUS_HUMAN_REVIEW


def test_same_tax_id_is_not_a_candidate_n3() -> None:
    """**N3**：税号相同 ⇒ 本就是同一节点，不产生候选。"""
    left = _profile(tax_id="91110108MA01T2W3XX")
    right = _profile(subject_id="SUBJECT:Y", tax_id="91110108MA01T2W3XX")
    result = generate_candidates([left, right], [])
    assert result.candidates == []


def test_structure_signal_alone_does_not_create_candidate() -> None:
    """同法人 + 同电话但名称毫不相像 ⇒ **不产生候选**（§4.5.1 S2 末句）。"""
    left = _profile(norm_name="甲", address="addr", phone="010-1", legal_rep="李强")
    right = _profile(
        subject_id="SUBJECT:Y",
        norm_name="乙",
        address="addr",
        phone="010-1",
        legal_rep="李强",
    )
    result = generate_candidates([left, right], [])
    assert result.candidates == []


def test_n2_multiple_auto_candidates_all_downgraded() -> None:
    """**N2**：同一 raw 有 >1 个 ≥0.90 候选 ⇒ 全部降 `human_review`、**不合并**。

    并错两家比漏并一家危险得多（沿用 S9.11 裁决 D-B）。
    """
    raw = _profile(subject_id="RAW:invoices.csv:FP-1", norm_name="北京恒信达科技")
    first = _profile(subject_id="SUBJECT:A", norm_name="北京恒信达科技")
    second = _profile(subject_id="SUBJECT:B", norm_name="北京恒信达科技")
    result = generate_candidates([first, second], [raw])
    raw_candidates = [
        item for item in result.candidates if item.left_id == raw.subject_id
    ]
    assert len(raw_candidates) == 2
    assert {item.status for item in raw_candidates} == {STATUS_HUMAN_REVIEW}
    assert all(item.signals.get("multi_candidate") for item in raw_candidates)
    # 关键：**没有任何**自动合并被采纳
    assert result.auto_merges == {}


def test_below_review_threshold_is_not_persisted() -> None:
    assert classify(REVIEW_THRESHOLD - 0.001) is None
    assert classify(REVIEW_THRESHOLD) == STATUS_HUMAN_REVIEW
    assert classify(AUTO_MERGE_THRESHOLD) == STATUS_AUTO_MERGED


# --------------------------------------------------------------------------- #
# 合成语料端到端（真机判据，§4.5.1 第 6 条）
# --------------------------------------------------------------------------- #
def _load_corpus() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    return (
        read_csv(Path(CORPUS_DIR) / "suppliers.csv"),
        read_csv(Path(CORPUS_DIR) / "invoices.csv"),
        read_csv(Path(CORPUS_DIR) / "vouchers.csv"),
    )


def test_synthetic_corpus_resolution_three_buckets() -> None:
    """真机判据：**`auto_merged` 恰好 1 条** + N1 反例落 `human_review` + 终态 87/90。"""
    suppliers, invoices, vouchers = _load_corpus()
    validate_corpus(suppliers, invoices, vouchers)
    index = build_master_index(suppliers)
    invoice_matches, voucher_matches, stats = align_sources(invoices, vouchers, index)

    # 消解**前**：S9.11 的判据必须仍然成立（语料改名不得推翻 C1）
    assert stats.total == 90
    assert stats.unaligned == 4
    assert stats.rate >= MIN_ALIGNMENT_RATE

    candidates, resolved_rows = resolve_unaligned(
        index=index,
        stats=stats,
        invoice_matches=invoice_matches,
        voucher_matches=voucher_matches,
    )

    auto = [item for item in candidates if item.status == STATUS_AUTO_MERGED]
    assert len(auto) == 1
    assert auto[0].left_id == "RAW:invoices.csv:FP2026-0012"
    # 归并到 S009（武汉长江智联科技，税号 91420111MA08J2D8FX）
    assert auto[0].right_id.endswith("MA08J2D8FX")
    assert auto[0].similarity == pytest.approx(0.941176, abs=1e-5)
    assert len(resolved_rows) == 1

    # **N1 反例**：名称极像（≈0.89）但有合法税号且与主数据不同 ⇒ 只能人工看
    n1 = [item for item in candidates if item.left_id == "RAW:vouchers.csv:PZ2026-0008"]
    assert len(n1) == 1
    assert n1[0].status == STATUS_HUMAN_REVIEW
    assert n1[0].signals["tax_conflict"] is True

    # **误并 0**：不得出现两个 canonical 主体被自动合并
    assert not [
        item
        for item in candidates
        if item.status == STATUS_AUTO_MERGED and item.left_id.startswith("SUBJECT:")
    ]

    # 终态对齐率（判据 ≥ 0.95）
    assert stats.aligned == 87
    assert stats.unaligned == 3
    assert stats.rate == pytest.approx(87 / 90)


def test_synthetic_corpus_canonical_pair_is_human_review_not_merged() -> None:
    """S001「…有限公司」/ S002「…股份公司」规范化名**完全相同**但税号不同
    ⇒ 判据必须把它们送人工队列，**不得**自动合并（这是 N1 在真机上的落点）。
    """
    suppliers, invoices, vouchers = _load_corpus()
    index = build_master_index(suppliers)
    invoice_matches, voucher_matches, stats = align_sources(invoices, vouchers, index)
    candidates, _ = resolve_unaligned(
        index=index,
        stats=stats,
        invoice_matches=invoice_matches,
        voucher_matches=voucher_matches,
    )
    pair = [
        item
        for item in candidates
        if item.left_id.endswith("MA01T2W3XX") and item.right_id.endswith("MA01T2W4XX")
    ]
    assert len(pair) == 1
    assert pair[0].status == STATUS_HUMAN_REVIEW
    assert pair[0].similarity == pytest.approx(TAX_ID_CONFLICT_CAP)


def test_normalize_name_alias_pair_collapses_to_same_key() -> None:
    """植入的两条别名**规范化后仍不同**（否则 S9.11 的三级对齐就直接命中了，
    也就轮不到消解器出场）——这是 D-H「改名不增行」能同时满足两侧判据的前提。
    """
    assert normalize_name("武汉市长江智联科技有限公司") != normalize_name(
        "武汉长江智联科技有限公司"
    )
    assert normalize_name("天津市滨海华元机械有限公司") != normalize_name(
        "天津滨海华元机械有限公司"
    )
