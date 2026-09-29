"""Sprint 9.11 批次 C1：四源主体对齐的单测。

钉死的是 ``specs/m4-affiliation-detection.md`` §4.6 的**口径**，不是实现细节：

- 对齐三级递减（税号 → 名称 → 地址），**先命中者胜**；
- 多候选**不自动合并**（并错两家比漏并一家危险）；
- ``unaligned_subjects.reason`` 三值逐字照 §4.6.4；
- chunk id 形如 ``chunk-<12 hex>``（**R16**：冒号形态会让引用被静默丢弃）；
- 语料 schema 违规必须**报出并终止**，不静默跳过。

全部用例**不连 Neo4j / 不写 PG**（纯函数 + 合成语料干跑）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.ingest_affiliation_sources import (
    CORPUS_DIR,
    MIN_ALIGNMENT_RATE,
    AlignmentMatch,
    CorpusError,
    _evidence_chunk_id,
    align_counterparty,
    align_sources,
    build_evidence,
    build_master_index,
    normalize_address,
    normalize_name,
    normalize_tax_id,
    read_csv,
    validate_corpus,
)


# --------------------------------------------------------------------------- #
# 规范化
# --------------------------------------------------------------------------- #
def test_normalize_tax_id_accepts_gb32100_and_rejects_others() -> None:
    assert normalize_tax_id("91110108MA01T2W3XX") == "91110108MA01T2W3XX"
    assert (
        normalize_tax_id(" 91110108ma01t2w3xx ") == "91110108MA01T2W3XX"
    )  # 去空白 + 大写
    # I / O / S / V / Z 不在 GB32100 字符集内
    assert normalize_tax_id("91110108MA01T2W3XI") is None
    assert normalize_tax_id("91110108MA01T2W3X") is None  # 17 位
    assert normalize_tax_id("") is None
    assert normalize_tax_id(None) is None


def test_normalize_name_strips_suffixes_and_fullwidth() -> None:
    # 「有限公司」/「股份」剥离 ⇒ 两家不同形态的公司落到同一个规范化名（构成多候选）
    assert normalize_name("北京恒信达科技有限公司") == "北京恒信达科技"
    assert normalize_name("北京恒信达科技股份有限公司") == "北京恒信达科技"
    assert normalize_name("北京恒信达科技公司") == "北京恒信达科技"
    assert normalize_name(" 北京 恒信达科技有限公司 ") == "北京恒信达科技"  # 去空白
    # 非后缀不剥（「集团」不是公司后缀 ⇒ 与「…机械」不是同一家）
    assert normalize_name("天津滨海华元机械集团") == "天津滨海华元机械集团"


def test_normalize_address_normalizes_fullwidth_but_not_geo_prefix() -> None:
    assert (
        normalize_address("合肥市高新区望江西路９００号") == "合肥市高新区望江西路900号"
    )
    assert (
        normalize_address("北京市海淀区中关村南大街1号")
        == "北京市海淀区中关村南大街1号"
    )
    # 地址异写「1号楼」≠「1号」：不做模糊归并（假合并比漏合并危险）
    assert normalize_address("北京市海淀区中关村南大街1号楼") != normalize_address(
        "北京市海淀区中关村南大街1号"
    )


# --------------------------------------------------------------------------- #
# 三级对齐
# --------------------------------------------------------------------------- #
def _index() -> object:
    suppliers = [
        {
            "supplier_id": "S001",
            "tax_id": "91110108MA01T2W3XX",
            "name": "北京恒信达科技有限公司",
            "address": "北京市海淀区中关村南大街1号",
        },
        {
            "supplier_id": "S002",
            "tax_id": "91110108MA01T2W4XX",
            "name": "北京恒信达科技股份有限公司",
            "address": "北京市海淀区中关村南大街2号",
        },
    ]
    return build_master_index(suppliers)


def test_align_prefers_tax_id_over_name() -> None:
    index = _index()
    # 名称指向 S002（地址 2 号），但税号是 S001 ⇒ **税号级胜出**
    row = {
        "counterparty_tax_id": "91110108MA01T2W3XX",
        "counterparty_name": "北京恒信达科技股份有限公司",
        "counterparty_address": "北京市海淀区中关村南大街2号",
    }
    match = align_counterparty(row, index)
    assert match.subject_id == "SUBJECT:91110108MA01T2W3XX"
    assert match.level == "tax_id"
    assert match.reason is None


def test_align_falls_back_to_name_then_address() -> None:
    # 税号缺、名称是 S001 的别名写法（唯一） ⇒ 名称级
    by_name = align_counterparty(
        {
            "counterparty_tax_id": "",
            "counterparty_name": "合肥徽风新能源公司",
            "counterparty_address": "未知地址",
        },
        _single_supplier_index(),
    )
    assert by_name.subject_id == "SUBJECT:91340104MA16A3T9WX"
    assert by_name.level == "name"

    # 税号缺、名称对不上、地址精确 ⇒ 地址级
    by_address = align_counterparty(
        {
            "counterparty_tax_id": "",
            "counterparty_name": "天津滨海华元机械集团",
            "counterparty_address": "天津市塘沽区新港路12号",
        },
        _single_supplier_index(),
    )
    assert by_address.subject_id == "SUBJECT:91120116MA10G9B6DX"
    assert by_address.level == "address"


def _single_supplier_index() -> object:
    suppliers = [
        {
            "supplier_id": "S017",
            "tax_id": "91340104MA16A3T9WX",
            "name": "合肥徽风新能源有限公司",
            "address": "合肥市高新区望江西路900号",
        },
        {
            "supplier_id": "S011",
            "tax_id": "91120116MA10G9B6DX",
            "name": "天津滨海华元机械有限公司",
            "address": "天津市塘沽区新港路12号",
        },
    ]
    return build_master_index(suppliers)


def test_align_reports_multiple_candidates_instead_of_merging() -> None:
    index = _index()
    match = align_counterparty(
        {
            "counterparty_tax_id": "",
            "counterparty_name": "北京恒信达科技公司",
            "counterparty_address": "北京市海淀区中关村南大街1号",
        },
        index,
    )
    assert match.subject_id is None
    assert match.reason == "multiple_candidates"
    assert match.candidates == (
        "SUBJECT:91110108MA01T2W3XX",
        "SUBJECT:91110108MA01T2W4XX",
    )


def test_align_reason_distinguishes_missing_tax_id_from_name_mismatch() -> None:
    index = _index()
    # 税号缺 + 名称 / 地址都未命中 ⇒ tax_id_missing
    missing = align_counterparty(
        {
            "counterparty_tax_id": "",
            "counterparty_name": "未知供应商甲",
            "counterparty_address": "北京市朝阳区建国路1号",
        },
        index,
    )
    assert missing.reason == "tax_id_missing"

    # 税号有值（格式合法）但三级都未命中 ⇒ name_mismatch
    mismatch = align_counterparty(
        {
            "counterparty_tax_id": "91110108MA99Y9Y9XX",
            "counterparty_name": "北京新联达科技有限公司",
            "counterparty_address": "北京市昌平区回龙观东大街5号",
        },
        index,
    )
    assert mismatch.reason == "name_mismatch"
    assert mismatch.subject_id is None


# --------------------------------------------------------------------------- #
# 合成语料端到端（干跑，不连库）
# --------------------------------------------------------------------------- #
def _load_corpus() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    return (
        read_csv(Path(CORPUS_DIR) / "suppliers.csv"),
        read_csv(Path(CORPUS_DIR) / "invoices.csv"),
        read_csv(Path(CORPUS_DIR) / "vouchers.csv"),
    )


def test_synthetic_corpus_alignment_rate_meets_spec() -> None:
    suppliers, invoices, vouchers = _load_corpus()
    validate_corpus(suppliers, invoices, vouchers)
    _, _, stats = align_sources(invoices, vouchers, build_master_index(suppliers))

    assert stats.total == 90  # 发票 60 + 凭证 30
    assert stats.rate >= MIN_ALIGNMENT_RATE
    # 刻意植入 4 条必然未对齐 ⇒ 率**不可能**是 1.0（否则说明植入失效）
    assert stats.unaligned == 4
    assert stats.aligned == 86
    assert stats.rate == pytest.approx(86 / 90)


def test_synthetic_corpus_unaligned_reasons_cover_all_three_kinds() -> None:
    suppliers, invoices, vouchers = _load_corpus()
    _, _, stats = align_sources(invoices, vouchers, build_master_index(suppliers))
    reasons = {row["reason"] for row in stats.unaligned_rows}
    assert reasons == {"tax_id_missing", "name_mismatch", "multiple_candidates"}
    # 每条未对齐都必须带 raw_name 与 source_doc_id（落 unaligned_subjects 的必填列）
    for row in stats.unaligned_rows:
        assert row["raw_name"]
        assert row["source_doc_id"]


def test_synthetic_corpus_exercises_all_three_levels() -> None:
    """三级都真的被用到——否则「三级递减」只是写在文档里的摆设。"""
    suppliers, invoices, vouchers = _load_corpus()
    _, _, stats = align_sources(invoices, vouchers, build_master_index(suppliers))
    assert set(stats.by_level) == {"tax_id", "name", "address"}


# --------------------------------------------------------------------------- #
# 语料 schema 违规：必须报出，不静默
# --------------------------------------------------------------------------- #
def _ok_supplier() -> dict[str, str]:
    """最小合法主数据行（含 §4.6.6 增补的电话 / 法人类）。"""
    return {
        "supplier_id": "S001",
        "tax_id": "91110108MA01T2W3XX",
        "name": "北京恒信达科技有限公司",
        "address": "北京市海淀区中关村南大街1号",
        "phone": "010-62000000",
        "legal_rep_name": "王伟",
        "legal_rep_id": "110101199001010001",
    }


def _ok_voucher() -> dict[str, str]:
    """最小合法凭证行（含 §4.6.6 增补的 ``trade_ref``）。"""
    return {
        "voucher_no": "PZ-1",
        "counterparty_tax_id": "",
        "counterparty_name": "乙",
        "counterparty_address": "另一地址",
        "amount": "2.00",
        "posting_date": "2026-04-01",
        "trade_ref": "",
    }


def test_corpus_errors_are_reported_not_swallowed() -> None:
    ok_row = {
        "invoice_no": "FP-1",
        "counterparty_tax_id": "",
        "counterparty_name": "甲",
        "counterparty_address": "某地址",
        "amount": "1.00",
        "issue_date": "2026-03-01",
        "trade_ref": "",
    }

    suppliers = [_ok_supplier()]
    vouchers = [_ok_voucher()]

    with pytest.raises(CorpusError, match="缺少列"):
        validate_corpus(
            suppliers, [{k: v for k, v in ok_row.items() if k != "amount"}], vouchers
        )

    with pytest.raises(CorpusError, match="格式非法"):
        validate_corpus(
            suppliers,
            [{**ok_row, "counterparty_tax_id": "91110108MA99Y9Y9"}],
            vouchers,
        )

    with pytest.raises(CorpusError, match="amount"):
        validate_corpus(suppliers, [{**ok_row, "amount": "0"}], vouchers)

    with pytest.raises(CorpusError, match="YYYY-MM-DD"):
        validate_corpus(suppliers, [{**ok_row, "issue_date": "2026/03/01"}], vouchers)

    with pytest.raises(CorpusError, match="重复"):
        validate_corpus(
            suppliers, [ok_row, {**ok_row, "counterparty_name": "乙"}], vouchers
        )


def test_tax_id_may_be_empty_but_must_be_valid_when_present() -> None:
    """「税号缺失」是 §4.5 的真实业务情形（可空），但**有值却非法**是语料错误。"""
    empty_ok = {
        "invoice_no": "FP-1",
        "counterparty_tax_id": "",
        "counterparty_name": "甲",
        "counterparty_address": "某地址",
        "amount": "1.00",
        "issue_date": "2026-03-01",
        "trade_ref": "",
    }
    # 不抛 ⇒ 空值合法
    validate_corpus([_ok_supplier()], [empty_ok], [_ok_voucher()])
    with pytest.raises(CorpusError):
        validate_corpus(
            [_ok_supplier()],
            [{**empty_ok, "counterparty_tax_id": "ABC"}],
            [_ok_voucher()],
        )


# --------------------------------------------------------------------------- #
# R16：chunk id 形态
# --------------------------------------------------------------------------- #
def test_chunk_id_matches_citation_pattern() -> None:
    """``agents.py::_CITATION_ID_PATTERN`` 只认 ``chunk-[0-9A-Za-z]``。

    形态不对 ⇒ 引用被**静默丢弃** ⇒ 问答以 ``no_grounded_evidence`` 拒答
    （Sprint 9.5 真机事故）。这个断言就是那次事故的回归闸门。
    """
    chunk_id = _evidence_chunk_id("invoices.csv", "FP2026-0001")
    assert re.fullmatch(r"chunk-[0-9a-f]{12}", chunk_id), chunk_id
    # 同一输入恒定（幂等）
    assert chunk_id == _evidence_chunk_id("invoices.csv", "FP2026-0001")
    assert chunk_id != _evidence_chunk_id("invoices.csv", "FP2026-0002")


def test_evidence_rows_cover_every_source_row() -> None:
    suppliers, invoices, vouchers = _load_corpus()
    doc_rows, chunk_rows, mention_rows = build_evidence(suppliers, invoices, vouchers)
    assert len(doc_rows) == 3
    assert len(chunk_rows) == len(suppliers) + len(invoices) + len(vouchers)
    assert len(mention_rows) == len(chunk_rows)
    # CSV 无页码 ⇒ page 一律 null（**不**伪造页码）
    assert all(row["page"] is None for row in chunk_rows)


def test_alignment_match_defaults_are_immutable() -> None:
    match = AlignmentMatch(subject_id="SUBJECT:X", level="tax_id")
    assert match.reason is None
    assert match.candidates == ()
    # frozen ⇒ 落库前不允许被就地改写（``FrozenInstanceError`` 是 AttributeError 子类）
    with pytest.raises(AttributeError):
        match.subject_id = "OTHER"  # type: ignore[misc]
