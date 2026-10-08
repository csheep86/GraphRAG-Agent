"""M5 §3 验收 3 / §4.5 / §5.3：统一脱敏工具 `mask(field, category)`。

**这批用例最要紧的不是"mask 会不会算"，而是"原文到底有没有跑出去"**（决策 **D8**）：

- 只断言 `mask()` 的返回值不含原文 ⇒ **恒绿失效**（R-9）：返回值当然不含原文。
  所以本文件两条核心判据断言的是——
  ① **已落库的 `audit_log.detail` JSON**（真 PostgreSQL，写进去再读回来）；
  ② **运行期捕获的 loguru JSON 输出**。
- 两条判据都先断言「确实抓到了 / 确实写了 1 行」，否则"没抓到"会让断言空转。

八类语料固定（¥0，不调真 LLM），形态逐字取自 spec §4.5 的「示例」列。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.masking import (
    BANK_ACCOUNT,
    CATEGORIES,
    CONTRACT_AMOUNT,
    FILENAME,
    ID_CARD,
    INVOICE_NO,
    LEGAL_PERSON,
    PHONE,
    SENSITIVE_DETAIL_FIELDS,
    TAX_NO,
    mask,
)
from app.db.models import AuditLog
from app.db.session import session_scope
from app.services.audit import record_audit_entry
from app.services.documents import hash_filename

# --------------------------------------------------------------------------- #
# 固定演示语料：八类各一条，**key 名全部落在登记表里**（这样才能验"自动"）
# --------------------------------------------------------------------------- #

SAMPLES: dict[str, str] = {
    "contract_amount": "1,234,567.89",
    "invoice_no": "INV202403150001",
    "tax_no": "91310000MA1FL1234X",
    "legal_person": "张三",
    "bank_account": "6228123456781234",
    "id_card": "110101199003071234",
    "phone": "13812341234",
    "filename": "2024年度采购合同.pdf",
}

#: spec §4.5「示例」列给出的**脱敏后**形态（逐字对偶，判据 1）
EXPECTED: dict[str, str] = {
    "contract_amount": "***,***.00",
    "invoice_no": "INV2****0001",
    "bank_account": "6228 **** **** 1234",
    "phone": "138****1234",
}

#: 走哈希的三类（「原文 → 64 字符 hex」）
HASHED: dict[str, str] = {
    "tax_no": TAX_NO,
    "legal_person": LEGAL_PERSON,
    "id_card": ID_CARD,
}

#: 中文形态（全角数字 / 空格分隔）—— 不归一化就会漏判，
#: 而漏掉的那部分正是「判据绿、实际漏绕过」
VARIANTS: dict[str, tuple[str, str, str]] = {
    "bank_fullwidth": (
        BANK_ACCOUNT,
        "６２２８１２３４５６７８１２３４",
        "6228 **** **** 1234",
    ),
    "phone_fullwidth": (PHONE, "１３８１２３４１２３４", "138****1234"),
    "bank_spaced": (BANK_ACCOUNT, "6228 1234 5678 1234", "6228 **** **** 1234"),
    "phone_spaced": (PHONE, "138 1234 1234", "138****1234"),
}


# --------------------------------------------------------------------------- #
# 1. 八类策略逐字照 spec §4.5
# --------------------------------------------------------------------------- #


def test_eight_categories_are_registered() -> None:
    assert CATEGORIES == (
        CONTRACT_AMOUNT,
        INVOICE_NO,
        TAX_NO,
        LEGAL_PERSON,
        BANK_ACCOUNT,
        ID_CARD,
        PHONE,
        FILENAME,
    )
    # 登记表收录的类别必须**全都在**八类里（否则那条规则永远走不到）
    assert set(SENSITIVE_DETAIL_FIELDS.values()) <= set(CATEGORIES)


@pytest.mark.parametrize(("key", "expected"), sorted(EXPECTED.items()))
def test_masked_form_matches_spec_example(key: str, expected: str) -> None:
    """判据 1：`1,234,567.89` → `***,***.00` 这类对偶，逐字照 spec §4.5 示例列。"""
    assert mask(SAMPLES[key], SENSITIVE_DETAIL_FIELDS[key]) == expected


@pytest.mark.parametrize(
    ("category", "variant", "expected"), [VARIANTS[k] for k in sorted(VARIANTS)]
)
def test_chinese_variants_are_normalized_before_masking(
    category: str, variant: str, expected: str
) -> None:
    """全角数字 / 空格分隔必须与半角产出**同一个**掩码（陷阱表最后一条）。"""
    assert mask(variant, category) == expected


@pytest.mark.parametrize(("key", "category"), sorted(HASHED.items()))
def test_hashed_categories_are_64_hex(key: str, category: str) -> None:
    """税号 / 法人姓名 / 身份证：SHA-256 + salt ⇒ 64 字符 hex，且不等于原文。"""
    masked = mask(SAMPLES[key], category)
    assert len(masked) == 64
    assert all(ch in "0123456789abcdef" for ch in masked)
    assert masked != SAMPLES[key]


def test_id_card_normalization_makes_variants_collide() -> None:
    """加了空格 / 连字符的同一个人 ⇒ **同一个**哈希（否则就是一次成功的绕过）。"""
    plain = mask("110101199003071234", ID_CARD)
    assert plain == mask("110101 1990 0307 1234", ID_CARD)
    assert plain == mask("110101-1990-0307-1234", ID_CARD)
    assert plain != mask("110101199003071235", ID_CARD)


# --------------------------------------------------------------------------- #
# 2. 文件名类 = 既有 `documents.hash_filename`（决策 D4）
# --------------------------------------------------------------------------- #


def test_filename_masks_to_the_existing_hash() -> None:
    """判据 2：产出必须与 `documents.filename_hash` **逐字节相同**，不得另给一套。"""
    assert mask(SAMPLES["filename"], FILENAME) == hash_filename(SAMPLES["filename"])


def test_filename_hash_value_is_unchanged_from_previous_version() -> None:
    """判据 9：既有语义未被改写——独立复算一遍 SHA-256（不复用被测实现）。"""
    name = SAMPLES["filename"]
    assert mask(name, FILENAME) == hashlib.sha256(name.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 3. salt 真的从 settings 读到（陷阱：extra="ignore" 会静默吃掉拼错的环境变量）
# --------------------------------------------------------------------------- #


def test_mask_salt_is_read_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert settings.mask_salt  # 先断言"读到了"，而不只是"设了"

    expected = hashlib.sha256(f"{settings.mask_salt}|张三".encode()).hexdigest()
    assert mask("张三", LEGAL_PERSON) == expected

    # 换 salt ⇒ 换哈希（证明上面那个等式不是因为 salt 根本没参与）
    monkeypatch.setattr(settings, "mask_salt", "another-salt")
    assert settings.mask_salt == "another-salt"
    assert (
        mask("张三", LEGAL_PERSON)
        == hashlib.sha256("another-salt|张三".encode()).hexdigest()
    )


# --------------------------------------------------------------------------- #
# 4. 边界：短输入 / 未知类别（决策 P5E-3 / P5E-4）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "category"),
    [
        ("123", BANK_ACCOUNT),
        ("1234567", BANK_ACCOUNT),
        ("12345678", BANK_ACCOUNT),  # 8 位会退化成"首尾各 4 位全露出"⇒ 也全掩
        ("138", PHONE),
        ("INV1", INVOICE_NO),
    ],
)
def test_short_input_is_fully_masked_never_echoed(value: str, category: str) -> None:
    assert mask(value, category) == "****"


def test_unknown_category_raises_instead_of_echoing_original() -> None:
    """未登记类别**必须**抛错：静默返回原文 = 「以为脱敏了其实没有」。"""
    with pytest.raises(ValueError, match="未登记的敏感字段类别"):
        mask("13812341234", "something_sensitive")


def test_empty_contract_amount_is_not_invented() -> None:
    assert mask("", CONTRACT_AMOUNT) == ""


# --------------------------------------------------------------------------- #
# 5. 判据 4：审计链路 —— 落库**之后**读回来，断言无一类原文
# --------------------------------------------------------------------------- #

PROBE_ACTION = "mask.probe"
PROBE_OVERRIDE_ACTION = "mask.probe_override"
PROBE_NONE_ACTION = "mask.probe_none"


@pytest.fixture
def wiped_audit_log() -> Iterator[None]:
    """清空默认租户的 `audit_log`（中间件会全量写，不清空就断言不了"本次"）。

    与 `tests/test_audit.py::empty_audit_log` 同一口径（它两个 org 各清一次，
    本文件只写默认 org ⇒ 清一个即可）。
    """
    with session_scope(org_id=get_settings().default_org_id) as session:
        session.query(AuditLog).delete()
        session.commit()
    yield


def _read_probe(action: str) -> dict[str, object]:
    with session_scope(org_id=get_settings().default_org_id) as session:
        rows = list(
            session.scalars(select(AuditLog).where(AuditLog.action == action)).all()
        )
    assert len(rows) == 1, f"action={action} 应恰好 1 行，实际 {len(rows)}"
    return dict(rows[0].detail or {})


def test_audit_detail_persisted_without_any_original(wiped_audit_log: None) -> None:
    """**核心判据**：写一条含八类原文的 `detail` ⇒ 落到 PG 读回来 ⇒ JSON 里无原文。

    断言对象是**库里的 JSON**，不是 `mask()` 的返回值（D8）。
    """
    settings = get_settings()
    with session_scope(org_id=settings.default_org_id) as session:
        assert record_audit_entry(
            session,
            org_id=settings.default_org_id,
            action=PROBE_ACTION,
            resource="test://masking",
            status="success",
            trace_id=uuid4(),
            actor_id=settings.default_actor_id,
            detail=dict(SAMPLES),
        )
        session.commit()

    stored = _read_probe(PROBE_ACTION)
    blob = json.dumps(stored, ensure_ascii=False)

    for key, original in SAMPLES.items():
        assert original not in blob, f"{key} 的原文落进了 audit_log.detail"
        assert stored[key] != original

    # 顺带钉住掩码类的**形态**（抽样两条，逐字照 spec 示例）
    assert stored["contract_amount"] == "***,***.00"
    assert stored["invoice_no"] == "INV2****0001"


def test_audit_detail_honours_explicit_sensitive_override(
    wiped_audit_log: None,
) -> None:
    """登记表之外的 key 可由调用方**显式**声明（Non-goal 10：类别不靠猜）。"""
    settings = get_settings()
    with session_scope(org_id=settings.default_org_id) as session:
        assert record_audit_entry(
            session,
            org_id=settings.default_org_id,
            action=PROBE_OVERRIDE_ACTION,
            resource="test://masking",
            status="success",
            trace_id=uuid4(),
            detail={"supplier_mobile": "13812341234", "note": "普通文本"},
            sensitive={"supplier_mobile": PHONE},
        )
        session.commit()

    stored = _read_probe(PROBE_OVERRIDE_ACTION)
    assert stored["supplier_mobile"] == "138****1234"
    # 未登记、也未显式声明的 key **原样**通过（这就是"只覆盖登记表"的诚实边界）
    assert stored["note"] == "普通文本"


def test_audit_detail_none_stays_none(wiped_audit_log: None) -> None:
    """`detail=None` 不得被脱敏器变成 `{}`（既有调用方大量不传 detail）。"""
    settings = get_settings()
    with session_scope(org_id=settings.default_org_id) as session:
        assert record_audit_entry(
            session,
            org_id=settings.default_org_id,
            action=PROBE_NONE_ACTION,
            resource="test://masking",
            status="success",
            trace_id=uuid4(),
        )
        session.commit()

    with session_scope(org_id=get_settings().default_org_id) as session:
        rows = list(
            session.scalars(
                select(AuditLog).where(AuditLog.action == PROBE_NONE_ACTION)
            ).all()
        )

    assert len(rows) == 1
    assert rows[0].detail is None


# --------------------------------------------------------------------------- #
# 6. 判据 5：日志链路 —— 运行期捕获 loguru JSON 输出，断言无原文
# --------------------------------------------------------------------------- #


@pytest.fixture
def json_log_sink() -> Iterator[list[str]]:
    """捕获 loguru 的 **JSON** 输出（本项目日志不走 stdlib ⇒ 不用 caplog）。"""
    from app.core.logging import setup_logging

    # 顺序不能反：`setup_logging()` 里的 `logger.remove()` 会把 sink 一起摘掉
    # （它有幂等守卫，第二次调用直接返回 ⇒ 先装 patcher 再挂 sink 才稳）。
    setup_logging()

    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="INFO",
        serialize=True,
    )
    try:
        yield captured
    finally:
        logger.remove(sink_id)


def test_loguru_json_output_has_no_original(json_log_sink: list[str]) -> None:
    """**核心判据**：`logger.bind(**八类原文)` ⇒ JSON 输出里一类原文都没有。"""
    logger.bind(**SAMPLES).info("mask_probe")

    assert len(json_log_sink) == 1, "没抓到日志 ⇒ 断言会空转（恒绿陷阱）"
    output = json_log_sink[0]

    for key, original in SAMPLES.items():
        assert original not in output, f"{key} 的原文进了日志"

    extra = json.loads(output)["record"]["extra"]
    assert extra["contract_amount"] == "***,***.00"
    assert extra["invoice_no"] == "INV2****0001"
    assert extra["bank_account"] == "6228 **** **** 1234"
    assert extra["phone"] == "138****1234"
    assert extra["filename"] == hash_filename(SAMPLES["filename"])
    assert len(extra["tax_no"]) == 64


def test_loguru_unregistered_extra_key_is_untouched(json_log_sink: list[str]) -> None:
    """诚实边界：登记表没收录的 key **照样**原样进日志——不许外推成"全字段已脱敏"。"""
    logger.bind(supplier_mobile="13812341234").info("mask_probe_unregistered")

    assert len(json_log_sink) == 1
    assert "13812341234" in json_log_sink[0]
