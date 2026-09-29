"""Sprint 9.12 语料增补器（**确定性、可重跑、¥0**）。

用法（工作目录 = 仓库根）::

    uv run python changes/archive/2026-09-29-Sprint9.12/gen_corpus.py

做什么（逐条对应 `specs/m4-affiliation-detection.md` §4.6.6 / §4.7）：

1. ``suppliers.csv`` 追加 ``phone`` / ``legal_rep_name`` / ``legal_rep_id`` 三列
   （``shared_phone`` / ``shared_legal_rep`` 的输入；**原值只在此处，入库即哈希**）；
2. ``invoices.csv`` / ``vouchers.csv`` 追加 ``trade_ref`` 列，并**覆盖**参与三方比对的
   金额为期望值（让"相等 / 不等 / 缺一方"三种情形确定可控）；
3. 生成 ``contracts.csv``（8 份，含 2 份不带 ``trade_ref`` 的对照）与
   ``shareholders.csv``（持股：2 环 / 3 环 / 4 环 + 1 条非环对照）。

**不改**既有列的语义 ⟹ §4.6.1 / §4.6.2 的冻结不被推翻；
**不改**税号 / 名称 / 地址三级对齐用到的任何字段（对齐率仍是 C1 测出的 86/90）。

植入清单（真机验收按此逐条核对，见 ``integration-log.md``）：

- ``shared_address``：S006 与 S014 **同址**（新地址，不占用现有地址级命中）；
- ``shared_legal_rep``：S004 与 S010 **同法人**（同姓名 + 同身份证号 ⇒ 同哈希）；
- ``shared_phone``：S002 与 S013 **同号**；
- ``cycle``：2 环 S003↔S005、3 环 S007→S009→S011→S007、4 环 S013→S015→S017→S019→S013；
  对照（**不**成环）S001→S002；
- ``amount_mismatch``：TR-0002 / TR-0003 / TR-0004 **三方不等 ⇒ 命中**；
  TR-0001 / TR-0005 三方相等（对照，**不**产出）；TR-0006 **缺发票 ⇒ 不产出**
  （spec §4.7.2：不拿两方冒充三方）。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "demo" / "affiliation"

#: 本方（我方）主体：不在供应商主数据里，只作为合同当事人存在
SELF_TAX_ID = "91110108MA00LFX8XX"
SELF_NAME = "华信智造集团股份有限公司"
SELF_ADDRESS = "北京市朝阳区建国路88号"

#: 同址植入（**新**地址——避免改动现有地址，从而影响 §4.6.3 的对齐率）
SHARED_ADDRESS = "北京市昌平区科技园路8号"
SHARED_ADDRESS_HOLDERS = ("S006", "S014")

#: 同法人植入
SHARED_LEGAL_REP_HOLDERS = ("S004", "S010")
SHARED_LEGAL_REP_NAME = "李强"
SHARED_LEGAL_REP_ID = "110101199001010004"

#: 同号植入
SHARED_PHONE_HOLDERS = ("S002", "S013")
SHARED_PHONE = "010-88886666"

_SURNAMES = ("王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴")
_GIVEN_NAMES = ("伟", "芳", "娜", "强", "磊", "静", "军", "敏", "杰", "涛")

#: 发票 / 凭证 → 交易引用（**只**这几行参与三方比对，其余为空）
INVOICE_TRADE_REF = {
    "FP2026-0001": "TR-0001",
    "FP2026-0002": "TR-0002",
    "FP2026-0003": "TR-0003",
    "FP2026-0004": "TR-0004",
    "FP2026-0006": "TR-0005",
}
VOUCHER_TRADE_REF = {
    "PZ2026-0001": "TR-0001",
    "PZ2026-0002": "TR-0002",
    "PZ2026-0003": "TR-0003",
    "PZ2026-0004": "TR-0004",
    "PZ2026-0005": "TR-0005",
    "PZ2026-0006": "TR-0006",  # 无发票配偶 ⇒ 三方不齐，不产出
}

#: 三方金额的期望值（``{trade_ref: (contract, invoice, voucher)}``）
TRADE_AMOUNTS: dict[str, tuple[float, float | None, float]] = {
    "TR-0001": (120_000.00, 120_000.00, 120_000.00),  # 相等（对照）
    "TR-0002": (96_000.00, 96_000.00, 91_500.00),  # 凭证少 4500 ⇒ 命中
    "TR-0003": (143_000.00, 119_000.00, 119_000.00),  # 合同多 24000 ⇒ 命中
    "TR-0004": (72_000.00, 76_000.00, 72_000.00),  # 发票多 4000 ⇒ 命中
    "TR-0005": (58_000.00, 58_000.00, 58_000.00),  # 相等（对照）
    "TR-0006": (66_000.00, None, 66_000.00),  # 缺发票 ⇒ 不产出
}

#: 持股（``holder, held, share_pct, since``）
SHAREHOLDERS: list[tuple[str, str, float, str]] = [
    # 对照组：单向持股，不成环 ⇒ 不产出 cycle
    ("S001", "S002", 60.0, "2021-05-11"),
    # 2 环：交叉持股（A→B→A）
    ("S003", "S005", 30.0, "2022-03-08"),
    ("S005", "S003", 25.0, "2022-03-08"),
    # 3 环：S007 → S009 → S011 → S007
    ("S007", "S009", 40.0, "2021-11-02"),
    ("S009", "S011", 35.0, "2021-11-02"),
    ("S011", "S007", 20.0, "2021-11-02"),
    # 4 环：S013 → S015 → S017 → S019 → S013（验证长度上限 4）
    ("S013", "S015", 28.0, "2023-01-19"),
    ("S015", "S017", 22.0, "2023-01-19"),
    ("S017", "S019", 18.0, "2023-01-19"),
    ("S019", "S013", 15.0, "2023-01-19"),
]


def _read(name: str) -> list[dict[str, str]]:
    path = CORPUS / name
    if not path.is_file():
        print(f"[FAIL] 缺 {path}——先跑 Sprint 9.11 的语料或检查路径", file=sys.stderr)
        raise SystemExit(1)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(name: str, rows: list[dict[str, str]], columns: list[str]) -> None:
    path = CORPUS / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})
    print(f"  {name}: {len(rows)} 行")


def build_suppliers() -> None:
    rows = _read("suppliers.csv")
    for index, row in enumerate(rows):
        supplier_id = row["supplier_id"]
        if supplier_id in SHARED_ADDRESS_HOLDERS:
            row["address"] = SHARED_ADDRESS
        if supplier_id in SHARED_LEGAL_REP_HOLDERS:
            row["legal_rep_name"] = SHARED_LEGAL_REP_NAME
            row["legal_rep_id"] = SHARED_LEGAL_REP_ID
        else:
            row["legal_rep_name"] = (
                _SURNAMES[index % len(_SURNAMES)] + _GIVEN_NAMES[index % len(_GIVEN_NAMES)]
            )
            row["legal_rep_id"] = f"11010119900101{index + 1:04d}"
        row["phone"] = (
            SHARED_PHONE
            if supplier_id in SHARED_PHONE_HOLDERS
            else f"010-{62000000 + index * 137:08d}"
        )
    _write(
        "suppliers.csv",
        rows,
        [
            "supplier_id",
            "tax_id",
            "name",
            "address",
            "phone",
            "legal_rep_name",
            "legal_rep_id",
        ],
    )


def build_invoices() -> None:
    rows = _read("invoices.csv")
    for row in rows:
        key = row["invoice_no"]
        row["trade_ref"] = INVOICE_TRADE_REF.get(key, "")
        trade = row["trade_ref"]
        if trade in TRADE_AMOUNTS and TRADE_AMOUNTS[trade][1] is not None:
            row["amount"] = f"{TRADE_AMOUNTS[trade][1]:.2f}"
    _write(
        "invoices.csv",
        rows,
        [
            "invoice_no",
            "counterparty_tax_id",
            "counterparty_name",
            "counterparty_address",
            "amount",
            "issue_date",
            "trade_ref",
        ],
    )


def build_vouchers() -> None:
    rows = _read("vouchers.csv")
    for row in rows:
        key = row["voucher_no"]
        row["trade_ref"] = VOUCHER_TRADE_REF.get(key, "")
        trade = row["trade_ref"]
        if trade in TRADE_AMOUNTS:
            row["amount"] = f"{TRADE_AMOUNTS[trade][2]:.2f}"
    _write(
        "vouchers.csv",
        rows,
        [
            "voucher_no",
            "counterparty_tax_id",
            "counterparty_name",
            "counterparty_address",
            "amount",
            "posting_date",
            "trade_ref",
        ],
    )


def build_contracts() -> None:
    """合同：``party_a`` = 该 trade_ref 对应发票的对手方，``party_b`` = 我方。"""
    invoices = {row["invoice_no"]: row for row in _read("invoices.csv")}
    invoice_by_trade = {
        ref: no for no, ref in INVOICE_TRADE_REF.items()
    }
    rows: list[dict[str, str]] = []
    for trade, amounts in TRADE_AMOUNTS.items():
        invoice_no = invoice_by_trade.get(trade)
        invoice = invoices.get(invoice_no or "")
        if invoice is None:
            # TR-0006 无发票：用凭证的对手方（金额比对仍缺发票 ⇒ 不产出）
            voucher_no = next(
                (no for no, ref in VOUCHER_TRADE_REF.items() if ref == trade), None
            )
            voucher = next(
                (row for row in _read("vouchers.csv") if row["voucher_no"] == voucher_no),
                None,
            )
            source = voucher or {}
        else:
            source = invoice
        rows.append(
            {
                "contract_no": f"HT2026-{trade[-4:]}",
                "trade_ref": trade,
                "party_a_tax_id": source.get("counterparty_tax_id", ""),
                "party_a_name": source.get("counterparty_name", ""),
                "party_a_address": source.get("counterparty_address", ""),
                "party_b_tax_id": SELF_TAX_ID,
                "party_b_name": SELF_NAME,
                "party_b_address": SELF_ADDRESS,
                "amount": f"{amounts[0]:.2f}",
                "signed_date": "2026-02-10",
            }
        )
    # 两份不带 trade_ref 的合同（对照：不参与三方比对，只建 :Contract + PARTY_TO）
    for index, invoice_no in enumerate(("FP2026-0008", "FP2026-0009"), start=7):
        invoice = invoices[invoice_no]
        rows.append(
            {
                "contract_no": f"HT2026-000{index}",
                "trade_ref": "",
                "party_a_tax_id": invoice["counterparty_tax_id"],
                "party_a_name": invoice["counterparty_name"],
                "party_a_address": invoice["counterparty_address"],
                "party_b_tax_id": SELF_TAX_ID,
                "party_b_name": SELF_NAME,
                "party_b_address": SELF_ADDRESS,
                "amount": invoice["amount"],
                "signed_date": "2026-02-18",
            }
        )
    _write(
        "contracts.csv",
        rows,
        [
            "contract_no",
            "trade_ref",
            "party_a_tax_id",
            "party_a_name",
            "party_a_address",
            "party_b_tax_id",
            "party_b_name",
            "party_b_address",
            "amount",
            "signed_date",
        ],
    )


def build_shareholders() -> None:
    suppliers = {row["supplier_id"]: row for row in _read("suppliers.csv")}
    rows: list[dict[str, str]] = []
    for holder, held, pct, since in SHAREHOLDERS:
        rows.append(
            {
                "holder_tax_id": suppliers[holder]["tax_id"],
                "held_tax_id": suppliers[held]["tax_id"],
                "share_pct": f"{pct:.2f}",
                "since": since,
            }
        )
    _write(
        "shareholders.csv",
        rows,
        ["holder_tax_id", "held_tax_id", "share_pct", "since"],
    )


def main() -> int:
    # Windows 控制台默认 GBK：含箭头 / 双向箭头的中文会 UnicodeEncodeError
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    print("===== Sprint 9.12 语料增补 =====")
    build_suppliers()
    build_invoices()
    build_vouchers()
    build_contracts()
    build_shareholders()
    print("\n植入清单（真机逐条核对）:")
    print(f"  shared_address   : {SHARED_ADDRESS_HOLDERS} 同址 {SHARED_ADDRESS}")
    print(f"  shared_legal_rep : {SHARED_LEGAL_REP_HOLDERS} 同法人 {SHARED_LEGAL_REP_NAME}")
    print(f"  shared_phone     : {SHARED_PHONE_HOLDERS} 同号 {SHARED_PHONE}")
    print("  cycle            : 2 环 S003↔S005 / 3 环 S007→S009→S011 / 4 环 S013→S015→S017→S019")
    print("  amount_mismatch  : TR-0002 / TR-0003 / TR-0004（TR-0001 / TR-0005 相等，TR-0006 缺发票）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
