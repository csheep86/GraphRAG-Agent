"""`app/evaluation/dataset.py` 的守卫（**E2.2**）：数据集**版本化 + 结构校验**。

为什么要测数据集本身：数据集是结论的归因。题号重复、hops < 2、gold 成员为空
这类问题**不会报错，只会让指标悄悄变坏**——所以必须由测试拦在加载阶段。
"""

from __future__ import annotations

import pytest

from app.evaluation.dataset import (
    DATA_DIR,
    DatasetError,
    dataset_versions,
    load_affiliation_gold,
    load_affiliation_meta,
    load_fixture_baseline,
    load_manifest,
    load_multihop_set,
    load_question_set,
)


def test_data_dir_is_inside_backend_and_not_gitignored() -> None:
    """数据集必须**入库**（未被 .gitignore 忽略）——不入库的换版没有 git 痕迹。"""
    assert DATA_DIR.exists()
    assert (DATA_DIR / "MANIFEST.json").exists()


def test_manifest_has_version_and_rubric() -> None:
    manifest = load_manifest()
    assert manifest["manifest_version"]
    # A3：rubric 必须写死，否则两次判分不可比
    assert manifest["rubric"]["id"]
    assert manifest["rubric"]["correct_rule"]
    assert manifest["annotator"]
    assert manifest["annotated_at"]


def test_manifest_lists_all_datasets() -> None:
    manifest = load_manifest()
    ids = {entry["id"] for entry in manifest["datasets"]}
    assert {
        "controlled-qset-v3",
        "controlled-qset-v4",
        "gold-multihop-v1",
        "gold-affiliation-v1",
        "fixture-baseline-v1",
    } == ids
    for entry in manifest["datasets"]:
        assert (DATA_DIR / entry["path"]).exists(), (
            f"{entry['id']} 的 path 指向不存在的文件"
        )


def _current_qset_entry() -> dict:
    """当前生效题集在 MANIFEST 里的登记条目（**题数的单一真源**，不写死）。"""
    manifest = load_manifest()
    for entry in manifest["datasets"]:
        if entry["id"] == "controlled-qset-v4":
            return entry
    raise AssertionError("MANIFEST 里找不到 controlled-qset-v4 条目")


def test_question_set_shape_and_no_duplicate_index() -> None:
    entry = _current_qset_entry()
    expected_total = int(entry["items"])
    # 库外题刻意保留，用于验证拒答出口不被误伤
    expected_refuse = int(entry["out_of_corpus"])

    items = load_question_set()
    assert len(items) == expected_total
    assert len({item.index for item in items}) == expected_total
    assert sum(1 for item in items if item.should_refuse) == expected_refuse
    for item in items:
        assert item.question
        assert item.source_doc, f"Q{item.index} 缺出处（出处缺失 ⇒ 判分无法复核）"
        assert item.expected_points, f"Q{item.index} 缺期望要点（判分无据）"


def test_qset_sensitivity_stays_within_budget() -> None:
    """**灵敏度预算**：单题翻转 = 1/题数，必须 ≤ 2.5pp。

    这条的存在理由（P6-H）：14 题时单题就是 ±7.14pp，而 C1 离 10% 阈值只差 0.9pp
    ⇒ 结论比噪声还小，那种分母上校准阈值毫无意义。故把 40 题的下限钉成机器判据：
    以后若有人为了省事裁题，这条会红。
    """
    items = load_question_set()
    sensitivity_pp = 100.0 / len(items)
    assert sensitivity_pp <= 2.5, (
        f"题数 {len(items)} ⇒ 单题翻转 {sensitivity_pp:.2f}pp，超出 2.5pp 预算；"
        "扩容是为了阶段⑤阈值校准有意义，不得随意裁题"
    )


def test_multihop_all_items_are_really_multihop() -> None:
    items = load_multihop_set()
    assert items
    for item in items:
        assert item.hops >= 2, f"#{item.index} 只有 {item.hops} 跳 ⇒ 不是多跳题"
        assert item.hop_path, f"#{item.index} 缺跳数路径（无法复核跳数）"
        assert item.expected_points
    # A3：默认全部**未判分** ⇒ correct 为 None（不是 False）
    assert all(item.correct is None for item in items)


def test_affiliation_gold_has_nine_findings() -> None:
    """9 组 = demo/affiliation/README.md §3.1 的植入数（1+1+1+3+3）。"""
    findings = load_affiliation_gold()
    assert len(findings) == 9
    by_type: dict[str, int] = {}
    for finding in findings:
        by_type[finding.type] = by_type.get(finding.type, 0) + 1
    assert by_type == {
        "shared_legal_rep": 1,
        "shared_address": 1,
        "shared_phone": 1,
        "cycle": 3,
        "amount_mismatch": 3,
    }


def test_finding_members_are_deterministic() -> None:
    """成员**去重 + 排序** ⇒ 顺序不敏感（同一疑点换个成员顺序仍应命中）。"""
    findings = load_affiliation_gold()
    for finding in findings:
        assert finding.members() == tuple(sorted(set(finding.entity_ids)))
        assert finding.members()


def test_affiliation_id_space_is_verified_against_live_output() -> None:
    """**关键守卫（2026-10-03 已核对）**：id 空间必须与真机输出同构，否则召回恒为 0。

    初版误写成 ``supplier_id``（真机输出里那只是**节点属性**，不是 id）⇒ 恒不命中；
    现改为真机空间（图节点 id）并置 ``verified=true`` ⇒ 执行器才允许出数。
    """
    space = load_affiliation_meta()["entity_id_space"]
    assert space["verified_against_live_output"] is True
    assert space["space"] == "graph_node_id"
    assert space["subject_id_form"] == "SUBJECT:<tax_id>"
    #: 共享证据节点（ADDRESS / PHONE / LEGALPERSON）**不算成员**——
    #: gold 的 shared_* 成员恒为 2 个主体，真机返回 3 个 id，不滤掉就永远对不上。
    assert "ADDRESS:" in space["non_member_prefixes"]
    assert "SUBJECT:" in space["member_prefixes"]


def test_gold_members_live_in_the_real_id_space() -> None:
    """gold 参与比对的成员**必须**是真机 id 空间（否则召回恒 0）。"""
    findings = load_affiliation_gold()
    assert findings
    for finding in findings:
        for member in finding.members():
            assert member.startswith(
                ("SUBJECT:", "CONTRACT:", "INVOICE:", "VOUCHER:")
            ), f"{finding.type} 的成员 {member} 不在真机 id 空间"


def test_fixture_baseline_is_explicitly_not_a_measurement() -> None:
    """fixture 基线**不含**任何基线测量结果（A1）——给假基线分数就是拿假数据算真判据。"""
    baseline = load_fixture_baseline()
    assert baseline["provided"] is False
    assert baseline["baseline_accuracy"] is None
    assert "非产品基线" in baseline["warning"]


def test_dataset_versions_are_reported() -> None:
    versions = dataset_versions()
    assert versions["manifest"]
    assert versions["controlled-qset-v3"] == "v3-2026-09-30"
    assert versions["gold-affiliation-v1"] == "v1-2026-10-03"


def test_dataset_error_is_raised_not_silently_defaulted() -> None:
    """缺字段 ⇒ 显式 `DatasetError`（静默兜底会把"数据集坏了"变成"指标变差"）。"""
    from app.evaluation.dataset import _require

    with pytest.raises(DatasetError, match="缺字段"):
        _require({"index": 1}, "question", where="unit-test")
    # None 也视为缺失（JSON 里 `"question": null` 与缺字段等价）
    with pytest.raises(DatasetError, match="缺字段"):
        _require({"question": None}, "question", where="unit-test")
