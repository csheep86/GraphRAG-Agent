"""统一敏感字段脱敏工具 ``mask(field, category)``（M5 §3 验收 3 / §4.5 / §5.3）。

spec §5.3 把 M5 的基础设施定为**三个统一组件**，第三个就是本模块：
「统一敏感字段脱敏工具函数（``mask(field, category)``）：所有写日志前必须经过脱敏」。
spec §4.5 给了**八类策略表**，末段给了硬约束：**原文不得落库，且由单元测试断言**。

四条实现纪律（决定了本模块长什么样）：

1. **类别由调用方 / 登记表显式给，代码绝不"猜"**（批次 Non-goal 10）。
   让代码去推断"这个值像不像身份证" ⇒ 漏判时无处追责，且漏判方向恒为"放行"。
2. **未登记类别一律抛错，绝不静默返回原文**（决策 **P5E-4**）。
   「以为脱敏了其实原样写出」是本模块最坏的失效形态——它比不脱敏更危险，
   因为它会让人以为已经安全。
3. **一律单向**：哈希类加 salt 后不可逆；掩码类丢掉的部分不留任何旁路可供拼回
   （批次 Non-goal 7）。**不做**「脱敏后可还原」。
4. **绝不造第三个哈希实现**：文件名类**直接调用** ``documents.hash_filename``
   （决策 **D4**，产出必须逐字节相同）；加 salt 的 SHA-256 复用
   ``license/fingerprint.py:69`` ``build_fingerprint`` 的**形态**
   （归一化 → ``f"{salt}|{value}"`` → ``sha256``）。

**两处接线**（§5.3）：① ``audit.py::record_audit_entry`` 写 ``detail`` 之前；
② ``core/logging.py`` 的 loguru JSON 出口（patcher）。

⚠️ **本模块不覆盖的**（不许外推）：日志 ``message`` 正文里的原文、本模块之外的
第九类字段、以及登记表未收录的 key 名——它们照样漏。
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any, Final

from app.core.config import get_settings

# --------------------------------------------------------------------------- #
# 八类敏感字段（spec §4.5 表格逐行对应）
# --------------------------------------------------------------------------- #

#: 合同金额：完整数字 → 掩码（`1,234,567.89` → `***,***.00`）
CONTRACT_AMOUNT: Final = "contract_amount"
#: 发票号：保留前缀 4 位 + 掩码（`INV202403150001` → `INV2****0001`）
INVOICE_NO: Final = "invoice_no"
#: 税号：SHA-256 + salt 哈希（原文 → 64 字符 hex）
TAX_NO: Final = "tax_no"
#: 法人姓名：SHA-256 + salt 哈希
LEGAL_PERSON: Final = "legal_person"
#: 银行账号：仅保留后 4 位（`6228 **** **** 1234`）
BANK_ACCOUNT: Final = "bank_account"
#: 身份证：SHA-256 + salt 哈希
ID_CARD: Final = "id_card"
#: 电话：仅保留后 4 位（`138****1234`）
PHONE: Final = "phone"
#: 文件名：SHA-256 哈希（与 `documents.filename_hash` **复用同一实现**）
FILENAME: Final = "filename"

#: 全八类（顺序照 spec §4.5 表格）
CATEGORIES: Final[tuple[str, ...]] = (
    CONTRACT_AMOUNT,
    INVOICE_NO,
    TAX_NO,
    LEGAL_PERSON,
    BANK_ACCOUNT,
    ID_CARD,
    PHONE,
    FILENAME,
)

#: 「什么都没留下」的统一掩码串（短输入 / 脱敏失败时的 fail-closed 形态）
FULL_MASK: Final = "****"

#: 合同金额的**固定**掩码（spec §4.5 示例 `***,***.00`）
CONTRACT_AMOUNT_MASK: Final = "***,***.00"

#: 电话保留的前缀位数（spec §4.5 示例 `138****1234`：号段不属于身份信息）
_PHONE_HEAD_LEN: Final = 3
#: 银行账号保留的前缀位数（spec §4.5 示例 `6228 **** ...`：卡 BIN）
_BANK_HEAD_LEN: Final = 4
#: 尾部保留位数（spec §4.5 的「后 4 位」）
_TAIL_LEN: Final = 4

#: 全角数字 → 半角（陷阱表：中文形态不归一化 ⇒ 掩码漏判，且漏的那部分
#: 正是「判据绿、实际漏」的那部分）
_FULLWIDTH_DIGITS: Final = {0xFF10 + offset: 0x30 + offset for offset in range(10)}


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #


def _digits_only(value: str) -> str:
    """全角归一 + 只留 ASCII 数字（吃掉千分位 / 空格 / 连字符等一切分隔）。"""
    return "".join(
        ch for ch in value.translate(_FULLWIDTH_DIGITS) if ch.isascii() and ch.isdigit()
    )


def _strip_spaces(value: str) -> str:
    """全角归一 + 去掉所有空白（发票号形态 `INV 2024 0315 0001`）。"""
    return "".join(ch for ch in value.translate(_FULLWIDTH_DIGITS) if not ch.isspace())


def _alnum_only(value: str) -> str:
    """小写 + 只留字母数字——与 ``build_fingerprint`` 的归一化**同款**。

    归一化后 ``110101 1990 0307 1234`` 与 ``110101199003071234`` 落到**同一个**
    哈希：不归一化的话，加个空格就是一次成功的绕过。
    """
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _salted_sha256(value: str, *, salt: str) -> str:
    """加 salt 的 SHA-256 → **64 字符 hex**（spec §4.5 三行原文口径）。

    salt 的拼接形态照抄 ``license/fingerprint.py:79``
    （``f"{salt}|{normalized}"``），**不另起一套**。
    """
    digest = hashlib.sha256(f"{salt}|{_alnum_only(value)}".encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# 八类策略（逐条对应 spec §4.5 的「脱敏策略」列）
# --------------------------------------------------------------------------- #


def _mask_contract_amount(value: str) -> str:
    """合同金额：完整数字 → **固定**掩码（决策 **P5E-2**）。

    ⚠️ 为什么是固定串而不是「按千分位逐组掩码」：按组数掩码会保留**量级**
    （三组 = 百万级、一组 = 千级），而金额的量级本身就是敏感信息。
    spec 示例 `1,234,567.89` → `***,***.00` 与原文字节一致，且不含任何量级。
    """
    return CONTRACT_AMOUNT_MASK if value.strip() else ""


def _mask_invoice_no(value: str) -> str:
    """发票号：保留前缀 4 位 + 固定 `****` + 后 4 位（中段**不**按长度外推）。"""
    text = _strip_spaces(value)
    if len(text) < 8:  # 决策 P5E-3：不足即全掩码，绝不回退原文
        return FULL_MASK
    return f"{text[:4]}****{text[-4:]}"


def _mask_bank_account(value: str) -> str:
    """银行账号：前 4 位（卡 BIN）+ 中段每 4 位一组 `****` + 后 4 位。

    ⚠️ spec §4.5 的**策略列**写「仅保留后 4 位」，而**示例列**是
    `6228 **** **** 1234`（保留了前 4 位）。二者冲突 ⇒ 取**示例列**
    （决策 **P5E-1**）：示例是 spec 里唯一给出具体形态的一侧，而批次判据 1
    要求「逐字照示例」。若后续裁决改取策略列的字面语义，只需改本函数。
    """
    digits = _digits_only(value)
    # +1：保证中段**至少**被掩掉一位（8 位卡号会退化成"首尾各 4 位全露出"）
    if len(digits) < _BANK_HEAD_LEN + _TAIL_LEN + 1:
        return FULL_MASK
    middle = len(digits) - _BANK_HEAD_LEN - _TAIL_LEN
    groups = max(1, math.ceil(middle / 4))
    return " ".join([digits[:_BANK_HEAD_LEN], *(["****"] * groups), digits[-4:]])


def _mask_phone(value: str) -> str:
    """电话：前 3 位（号段）+ `****` + 后 4 位（示例 `138****1234`，决策 P5E-1）。"""
    digits = _digits_only(value)
    if len(digits) < _PHONE_HEAD_LEN + _TAIL_LEN + 1:
        return FULL_MASK
    return f"{digits[:_PHONE_HEAD_LEN]}****{digits[-4:]}"


def _mask_hashed(value: str) -> str:
    """税号 / 法人姓名 / 身份证：SHA-256 + salt → 64 字符 hex（单向、不可逆）。"""
    return _salted_sha256(value, salt=get_settings().mask_salt)


def _mask_filename(value: str) -> str:
    """文件名：**直接调用** `documents.hash_filename`（决策 **D4**）。

    为什么是函数内 import：`app/core/` 属于基础设施层，而 ``documents`` 会连带
    拉起 ``app.tasks.*`` 一整条依赖链；放在模块顶层会把这条链塞进每一个
    导入 ``core.logging`` 的入口（含 CLI / 脚本）。这里是热路径（每行日志都可能
    走），但 import 只在首次付费，语义与顶层完全一致。
    """
    from app.services.documents import hash_filename  # noqa: PLC0415 - 见上

    return hash_filename(value)


_STRATEGIES: Final[dict[str, Callable[[str], str]]] = {
    CONTRACT_AMOUNT: _mask_contract_amount,
    INVOICE_NO: _mask_invoice_no,
    TAX_NO: _mask_hashed,
    LEGAL_PERSON: _mask_hashed,
    BANK_ACCOUNT: _mask_bank_account,
    ID_CARD: _mask_hashed,
    PHONE: _mask_phone,
    FILENAME: _mask_filename,
}


def mask(field: str, category: str) -> str:
    """按 spec §4.5 的策略脱敏**一个**值。

    :param field: 待脱敏的原文。
    :param category: 八类之一（见 :data:`CATEGORIES`）。
    :raises ValueError: 类别未登记——**绝不**静默返回原文（决策 **P5E-4**）。
    """
    strategy = _STRATEGIES.get(category)
    if strategy is None:
        raise ValueError(
            f"未登记的敏感字段类别 {category!r}；合法取值 CATEGORIES="
            f"{list(CATEGORIES)}。未登记类别一律抛错——静默返回原文等于"
            "「以为脱敏了其实没有」，比不脱敏更危险"
        )
    return strategy(field)


# --------------------------------------------------------------------------- #
# 登记表：detail / log extra 的「自动」脱敏（Non-goal 10 的落点）
# --------------------------------------------------------------------------- #

#: **敏感字段登记表**：``audit_log.detail`` / loguru ``extra`` 的 **key 名** → 类别。
#:
#: 为什么是「按 key 名登记」而不是「按值猜」：后者是 Non-goal 10 明令禁止的
#: 自动识别——猜错的那一侧恒为「放行」，且漏判无从追责。登记表是**声明式**的：
#: 加一类就加一行，漏一类就明确地漏一行，评审时看得见。
SENSITIVE_DETAIL_FIELDS: Final[dict[str, str]] = {
    "contract_amount": CONTRACT_AMOUNT,
    "amount": CONTRACT_AMOUNT,
    "invoice_no": INVOICE_NO,
    "invoice_number": INVOICE_NO,
    "tax_no": TAX_NO,
    "tax_id": TAX_NO,
    "legal_person": LEGAL_PERSON,
    "legal_rep": LEGAL_PERSON,
    "bank_account": BANK_ACCOUNT,
    "bank_card": BANK_ACCOUNT,
    "id_card": ID_CARD,
    "id_no": ID_CARD,
    "phone": PHONE,
    "mobile": PHONE,
    "tel": PHONE,
    "filename": FILENAME,
    "file_name": FILENAME,
}


def mask_mapping(
    values: Mapping[str, Any],
    *,
    sensitive: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """按登记表脱敏一个映射（`audit_log.detail` / loguru `extra` 共用一份口径）。

    :param sensitive: 调用方**显式**增补 / 覆盖的 ``key → category``。
        登记表给出「自动」（spec §3 验收 3 原文），本参数给调用方一个
        登记表之外的显式入口——两者合并，**登记表不因显式指定而失效**。
    """
    rules = {**SENSITIVE_DETAIL_FIELDS, **(sensitive or {})}
    return _mask_mapping(values, rules)


def _mask_mapping(
    values: Mapping[str, Any], rules: Mapping[str, str]
) -> dict[str, Any]:
    return {
        key: _mask_value(value, rules.get(key), rules) for key, value in values.items()
    }


def _mask_value(value: Any, category: str | None, rules: Mapping[str, str]) -> Any:
    """递归脱敏：dict / list 下探，字符串按类别脱敏，其余原样。

    ⚠️ 脱敏失败（未登记类别等）⇒ **回落到 `FULL_MASK` 而不是原文**：
    这是 fail-closed，写库 / 打日志的路径上「宁可少记，不可泄露」。
    """
    if isinstance(value, Mapping):
        return _mask_mapping(value, rules)
    if isinstance(value, list):
        return [_mask_value(item, None, rules) for item in value]
    if isinstance(value, str) and category is not None:
        try:
            return mask(value, category)
        except Exception:  # noqa: BLE001 - 见上：失败 ⇒ 全掩码，绝不回退原文
            return FULL_MASK
    return value


def mask_log_record(record: MutableMapping[str, Any]) -> None:
    """loguru **patcher**：对 ``record["extra"]`` 按登记表脱敏（接线点 ②）。

    只处理 ``extra``：``message`` 是已格式化的正文，要在那里脱敏就只能"猜值"
    （Non-goal 10）⇒ **本批不覆盖**，登记为已知缺口。

    脱敏器自身绝不允许把日志打崩：每个值都在 :func:`_mask_value` 里 fail-closed，
    这里只做结构性判空，不做二次兜底（静默吞异常会让人以为脱敏成功了）。
    """
    extra = record.get("extra")
    if isinstance(extra, Mapping) and extra:
        record["extra"] = _mask_mapping(extra, SENSITIVE_DETAIL_FIELDS)


__all__ = [
    "BANK_ACCOUNT",
    "CATEGORIES",
    "CONTRACT_AMOUNT",
    "FILENAME",
    "FULL_MASK",
    "ID_CARD",
    "INVOICE_NO",
    "LEGAL_PERSON",
    "PHONE",
    "SENSITIVE_DETAIL_FIELDS",
    "TAX_NO",
    "mask",
    "mask_log_record",
    "mask_mapping",
]
