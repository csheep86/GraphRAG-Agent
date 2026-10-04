"""**受控语料生成器**（A8 扩标，2026-10-04）——`demo/affiliation/generated/`。

**为什么是"生成器"而不是"再手写一批 CSV"**：spec §3 验收 6 要
**200 合同 / 500 发票 / 100 凭证 / 20 组植入**，手写既不可复核、也改不动规模。
生成器是**受控**的（固定 seed ⇒ 字节级可复现），换规模只改常量。

**三条硬约束（来自 `AffiliationService.detect()` 的真实读图口径）**：

1. **噪声必须全局唯一**：地址 / 电话 / 法定代表人（姓名+证件号）一旦在非植入主体间
   碰撞 ⇒ 立刻变成一条**误报**，而 C2-b 要求误报**必须 0 条**（上界 ≤ 0.15）
   ⇒ 噪声是判据的一部分，不是背景板；
2. **`cycle` 只能来自植入**：噪声持股边一律 `i → j 且 i < j`（按索引，DAG）⇒
   不可能成有向环；植入环涉及的主体的**所有**其他持股边都被排除（否则同一组主体
   会产出多条不同 `cycle_ids` ⇒ 与 gold 单条不匹配，多出的计误报）；
3. **三方金额**：`amount_mismatch` 的判据是 `NOT (c.amount = i.amount AND i.amount = v.amount)`
   （**严格相等、无容差**）⇒ 一个 `trade_ref` 只对应 **1 合同 / 1 发票 / 1 凭证**
   （否则笛卡尔积会产出额外组合，每个组合都是一条独立疑点 ⇒ 计误报），
   且**未植入**的那些三方金额必须**逐字符相同**。

**文本证据（A8 裁决 3）**：现有 9 组 gold 是"从 CSV 结构化字段推导"的，算法读的
正是同一批字段 ⇒ 命中是必然 ⇒ 测的是"推导一致性"而非"发现隐藏关联"。
故本生成器给三张单据表加正文列（`contract_text` / `invoice_text` / `voucher_text`）；
`ingest_affiliation_sources.py::build_evidence` 用 `",".join(row.values())` 生成
`:Chunk.text` ⇒ **正文自动进入证据链**，无需改 ingest 的证据逻辑。

用法（工作目录 = `backend/`）：

```bash
uv run python scripts/gen_affiliation_corpus.py            # 写语料 + gold
uv run python scripts/gen_affiliation_corpus.py --check    # 只自检，不写盘
```
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "demo" / "affiliation" / "generated"
DEFAULT_GOLD_FILE = REPO_ROOT / "backend" / "data" / "eval" / "gold-affiliation-v2.json"

#: 固定 seed ⇒ **字节级可复现**（换语料必须换这个值，并同步换 `CORPUS_VERSION`）
SEED = 20261004
CORPUS_VERSION = "v2-2026-10-04"

N_SUPPLIERS = 120
N_CONTRACTS = 200
N_INVOICES = 500
N_VOUCHERS = 100
#: 五类 × 每类 4 组 = **20 组**（spec §3 验收 6；"每类 ≥4" 取等号即可）
N_PLANTED_PER_TYPE = 4

KG_VERSION = "affiliation-demo-v2"
#: 与 `ingest_affiliation_sources.py::AFFILIATION_DEMO_ORG_ID` 同一个 uuid5
ORG_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "graphrag/affiliation/demo-org"))

#: 税号字符集（**不含** I / O / S / V / Z，照抄 ingest 的校验正则）
_TAX_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"

_CITIES = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "成都",
    "武汉",
    "西安",
    "南京",
    "天津",
]
_NAME_A = "华信恒达瑞泰中科联通昌盛宏远金诚"
_NAME_B = "机械制造贸易科技发展实业电子商务"
_ROADS = ["科技园", "中山", "人民", "建设", "复兴", "和平", "解放", "长江"]
_SURNAMES = "赵钱孙李周吴郑王冯陈褚卫"
_GIVEN = ["建国", "志强", "晓明", "丽华", "国强", "秀英", "海燕", "文博"]

#: 植入的金额不一致形态（**三方各异**，覆盖 spec 的三类方向）
_MISMATCH_SHAPES = (
    ("凭证少记", 1.0, 1.0, 0.92),
    ("合同多记", 1.15, 1.0, 1.0),
    ("发票多记", 1.0, 1.08, 1.0),
    ("三方各异", 1.0, 0.94, 0.88),
)


@dataclass
class Supplier:
    index: int
    supplier_id: str
    tax_id: str
    name: str
    address: str
    phone: str
    legal_rep_name: str
    legal_rep_id: str
    #: 文本证据用：本主体参与植入关系时追加到发票正文的话术
    notes: list[str] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        return f"SUBJECT:{self.tax_id}"


def _tax_ids(rng: random.Random, count: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        value = "91" + "".join(rng.choice(_TAX_CHARS) for _ in range(16))
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _names(rng: random.Random, count: int) -> list[str]:
    """唯一公司名（`normalize_name` 会剥「有限公司」后缀 ⇒ 前缀本身也必须唯一）。"""
    combos = [a + b for a in _NAME_A for b in _NAME_B]
    picked = rng.sample(combos, count)
    return [
        f"{_CITIES[i % len(_CITIES)]}{core}有限公司" for i, core in enumerate(picked)
    ]


def _legal_reps(rng: random.Random, count: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    while len(out) < count:
        name = rng.choice(_SURNAMES) + rng.choice(_GIVEN)
        id_no = f"11010119800101{rng.randrange(1000, 9999):04d}"
        if (name, id_no) not in seen:
            seen.add((name, id_no))
            out.append((name, id_no))
    return out


def build_suppliers(rng: random.Random) -> list[Supplier]:
    tax_ids = _tax_ids(rng, N_SUPPLIERS)
    names = _names(rng, N_SUPPLIERS)
    reps = _legal_reps(rng, N_SUPPLIERS)
    return [
        Supplier(
            index=i,
            supplier_id=f"S{i + 1:03d}",
            tax_id=tax_ids[i],
            name=names[i],
            address=f"{_CITIES[i % len(_CITIES)]}市{_ROADS[i % len(_ROADS)]}路{1000 + i}号",
            phone=f"010-{80000000 + i}",
            legal_rep_name=reps[i][0],
            legal_rep_id=reps[i][1],
        )
        for i in range(N_SUPPLIERS)
    ]


def _plant(
    suppliers: list[Supplier],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], set[int]]:
    """植入 **20 组**（五类 × 4）隐藏关联；返回（描述, 已占用的主体下标）。"""
    pool = list(range(N_SUPPLIERS))
    rng.shuffle(pool)
    cursor = iter(pool)
    used: set[int] = set()
    planted: list[dict[str, Any]] = []

    def take(n: int) -> list[int]:
        picked = [next(cursor) for _ in range(n)]
        used.update(picked)
        return picked

    # --- shared_legal_rep / shared_address / shared_phone：各 4 对 ---
    for kind, attr, tmpl in (
        ("shared_legal_rep", "legal_rep", "与 {other} 的法定代表人为同一人（{rep}）"),
        ("shared_address", "address", "与 {other} 的注册地址相同（{addr}）"),
        ("shared_phone", "phone", "与 {other} 的联系电话相同（{phone}）"),
    ):
        for _ in range(N_PLANTED_PER_TYPE):
            a, b = take(2)
            donor, taker = suppliers[a], suppliers[b]
            if attr == "legal_rep":
                taker.legal_rep_name = donor.legal_rep_name
                taker.legal_rep_id = donor.legal_rep_id
                extra = {"rep": f"{donor.legal_rep_name} / {donor.legal_rep_id}"}
            elif attr == "address":
                taker.address = donor.address
                extra = {"addr": donor.address}
            else:
                taker.phone = donor.phone
                extra = {"phone": donor.phone}
            clause = tmpl.format(other=donor.name, **extra)
            donor.notes.append(clause)
            taker.notes.append(clause)
            planted.append(
                {
                    "type": kind,
                    "members": [donor, taker],
                    "evidence": f"suppliers.csv：{attr} 与 {donor.supplier_id} 相同"
                    f"（{taker.supplier_id} 复制自 {donor.supplier_id}）",
                    "text_evidence": clause,
                }
            )

    # --- cycle：4 组（2 环 / 3 环 / 4 环 ×2）---
    ring_sizes = (2, 3, 4, 4)
    for size in ring_sizes:
        members = [suppliers[i] for i in take(size)]
        for member in members:
            others = "、".join(m.name for m in members if m is not member)
            member.notes.append(f"本公司与 {others} 之间存在循环持股（{size} 环）")
        planted.append(
            {
                "type": "cycle",
                "members": members,
                "evidence": f"shareholders.csv：{size} 环"
                + " → ".join(m.supplier_id for m in members)
                + f" → {members[0].supplier_id}",
                "text_evidence": members[0].notes[-1],
                "ring": size,
            }
        )

    return planted, used


def build_shareholders(
    suppliers: list[Supplier],
    planted: list[dict[str, Any]],
    used: set[int],
    rng: random.Random,
) -> list[dict[str, str]]:
    """持股边：**植入环 + 噪声 DAG**（噪声边一律 `i → j 且 i < j` ⇒ 不可能成环）。"""
    rows: list[dict[str, str]] = []

    # 植入环（按顺序首尾相接）
    for group in planted:
        if group["type"] != "cycle":
            continue
        members: list[Supplier] = group["members"]
        for i, holder in enumerate(members):
            held = members[(i + 1) % len(members)]
            rows.append(
                {
                    "holder_tax_id": holder.tax_id,
                    "held_tax_id": held.tax_id,
                    "share_pct": f"{rng.randrange(15, 45)}.0",
                    "since": "2026-01-01",
                }
            )

    # 噪声：DAG（**排除**已植入主体 ⇒ 不会叠加出新环 / 新路径）
    noise = [i for i in range(N_SUPPLIERS) if i not in used]
    pairs: set[tuple[int, int]] = set()
    for i in noise:
        for _ in range(2):
            j = rng.randrange(N_SUPPLIERS)
            if j in used or j <= i or (i, j) in pairs:
                continue
            pairs.add((i, j))
            rows.append(
                {
                    "holder_tax_id": suppliers[i].tax_id,
                    "held_tax_id": suppliers[j].tax_id,
                    "share_pct": f"{rng.randrange(5, 60)}.0",
                    "since": "2026-02-01",
                }
            )
    return rows


def build_documents(
    suppliers: list[Supplier],
    planted: list[dict[str, Any]],
    rng: random.Random,
) -> dict[str, list[dict[str, str]]]:
    """合同 200 / 发票 500 / 凭证 100（**含正文列**）+ 4 组金额不一致。"""
    # 先定 100 个三方交易号（= 凭证数）：每个号恰好 1 合同 / 1 发票 / 1 凭证
    refs = [f"TR-{i + 1:04d}" for i in range(N_VOUCHERS)]
    mismatch_refs = rng.sample(refs, N_PLANTED_PER_TYPE)
    mismatch_by_ref = dict(zip(mismatch_refs, _MISMATCH_SHAPES, strict=True))

    base_amounts = {ref: float(rng.randrange(50, 900) * 100) for ref in refs}

    def money(value: float) -> str:
        return f"{value:.2f}"

    # --- 凭证（100）：每号一条 ---
    vouchers: list[dict[str, str]] = []
    for i, ref in enumerate(refs):
        holder = suppliers[i % N_SUPPLIERS]
        amount = base_amounts[ref]
        if ref in mismatch_by_ref:
            amount = amount * mismatch_by_ref[ref][3]
        vouchers.append(
            {
                "voucher_no": f"PZ2026-{i + 1:04d}",
                "counterparty_tax_id": holder.tax_id,
                "counterparty_name": holder.name,
                "counterparty_address": holder.address,
                "amount": money(amount),
                "posting_date": f"2026-{4 + (i % 8):02d}-{(i % 28) + 1:02d}",
                "trade_ref": ref,
                "voucher_text": (
                    f"记账凭证 PZ2026-{i + 1:04d}，交易参考号 {ref}，"
                    f"往来单位 {holder.name}（税号 {holder.tax_id}），"
                    f"发生额 {money(amount)} 元。"
                    + (
                        "备注：本凭证金额与同交易参考号的合同 / 发票不一致。"
                        if ref in mismatch_by_ref
                        else ""
                    )
                ),
            }
        )

    # --- 发票（500）：前 100 条带 trade_ref（与凭证一一对应），其余为空 ---
    invoices: list[dict[str, str]] = []
    for i in range(N_INVOICES):
        holder = suppliers[i % N_SUPPLIERS]
        ref = refs[i] if i < N_VOUCHERS else ""
        amount = base_amounts[ref] if ref else float(rng.randrange(20, 900) * 100)
        if ref in mismatch_by_ref:
            amount = amount * mismatch_by_ref[ref][2]
        text = (
            f"增值税专用发票 FP2026-{i + 1:04d}，"
            + (f"交易参考号 {ref}，" if ref else "")
            + f"销方 {holder.name}（税号 {holder.tax_id}），金额 {money(amount)} 元，"
            f"开票日期 2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}。"
        )
        if ref in mismatch_by_ref:
            text += "备注：本发票金额与同交易参考号的合同 / 凭证不一致。"
        text += "".join(f"｜{note}" for note in holder.notes)
        invoices.append(
            {
                "invoice_no": f"FP2026-{i + 1:04d}",
                "counterparty_tax_id": holder.tax_id,
                "counterparty_name": holder.name,
                "counterparty_address": holder.address,
                "amount": money(amount),
                "issue_date": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "trade_ref": ref,
                "invoice_text": text,
            }
        )

    # --- 合同（200）：前 100 条带 trade_ref，其余为空 ---
    contracts: list[dict[str, str]] = []
    for i in range(N_CONTRACTS):
        ref = refs[i] if i < N_VOUCHERS else ""
        party_a = suppliers[(i * 7) % N_SUPPLIERS]
        party_b = suppliers[(i * 13 + 5) % N_SUPPLIERS]
        amount = base_amounts[ref] if ref else float(rng.randrange(100, 900) * 100)
        if ref in mismatch_by_ref:
            amount = amount * mismatch_by_ref[ref][1]
        text = (
            f"采购合同 HT2026-{i + 1:04d}，"
            + (f"交易参考号 {ref}，" if ref else "")
            + f"甲方 {party_a.name}（税号 {party_a.tax_id}），"
            f"乙方 {party_b.name}（税号 {party_b.tax_id}），"
            f"合同金额 {money(amount)} 元，签署日期 2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}。"
        )
        if ref in mismatch_by_ref:
            text += f"备注：三方金额不一致（{mismatch_by_ref[ref][0]}）。"
        contracts.append(
            {
                "contract_no": f"HT2026-{i + 1:04d}",
                "trade_ref": ref,
                "party_a_tax_id": party_a.tax_id,
                "party_a_name": party_a.name,
                "party_a_address": party_a.address,
                "party_b_tax_id": party_b.tax_id,
                "party_b_name": party_b.name,
                "party_b_address": party_b.address,
                "amount": money(amount),
                "signed_date": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "contract_text": text,
            }
        )

    # --- 金额不一致的 gold 描述（三单据 id）---
    for i, ref in enumerate(refs):
        if ref not in mismatch_by_ref:
            continue
        planted.append(
            {
                "type": "amount_mismatch",
                "members": [
                    f"CONTRACT:HT2026-{i + 1:04d}",
                    f"INVOICE:FP2026-{i + 1:04d}",
                    f"VOUCHER:PZ2026-{i + 1:04d}",
                ],
                "evidence": (
                    f"{ref}：合同 {contracts[i]['amount']} / 发票 {invoices[i]['amount']}"
                    f" / 凭证 {vouchers[i]['amount']} ⇒ {mismatch_by_ref[ref][0]}"
                ),
                "text_evidence": contracts[i]["contract_text"],
                "trade_ref": ref,
            }
        )

    return {"contracts": contracts, "invoices": invoices, "vouchers": vouchers}


def build_gold(
    suppliers: list[Supplier], planted: list[dict[str, Any]]
) -> dict[str, Any]:
    """gold v2：**20 组**，`node_ids` 走**图节点 id 空间**（成员规则同 v1）。"""
    findings: list[dict[str, Any]] = []
    for group in planted:
        members = group["members"]
        if group["type"] == "amount_mismatch":
            node_ids = list(members)  # type: ignore[arg-type]
            entity_ids = [group["trade_ref"]]
            tax_ids: list[str] = []
        else:
            node_ids = [m.node_id for m in members]  # type: ignore[union-attr]
            entity_ids = [m.supplier_id for m in members]  # type: ignore[union-attr]
            tax_ids = [m.tax_id for m in members]  # type: ignore[union-attr]
        finding: dict[str, Any] = {
            "type": group["type"],
            "node_ids": node_ids,
            "entity_ids": entity_ids,
            "tax_ids": tax_ids,
            "evidence": group["evidence"],
            "text_evidence": group["text_evidence"],
            "expected_count": 1,
        }
        if group["type"] == "amount_mismatch":
            finding["trade_ref"] = group["trade_ref"]
        findings.append(finding)

    findings.sort(key=lambda item: (item["type"], item["node_ids"]))
    return {
        "id": "gold-affiliation-v2",
        "purpose": "C2-a 隐性关联召回 / C2-b 误报率的 gold 标注（**A8 扩标版**）",
        "source": {
            "implanted_groups": "由 scripts/gen_affiliation_corpus.py 生成（seed=20261004）",
            "corpus": "demo/affiliation/generated/（contracts 200 / invoices 500 / vouchers 100）",
            "corpus_layer": "L1",
            "corpus_layer_note": (
                "**L1 算法层**：合成语料，直接由 scripts/ingest_affiliation_sources.py 入图，"
                "不经过 M2 抽取链路 ⇒ 只验证算法判据，**未经端到端验证**（A8 裁决 4 / G5 声明）"
            ),
            "text_evidence": (
                "植入关系在**单据正文**里也有体现（contract_text / invoice_text / voucher_text）；"
                "CSV 行的逗号拼接即 :Chunk.text ⇒ 正文自动进证据链"
            ),
            "why_not_derived": (
                "v1 的 9 组是「从 CSV 结构化字段推导」的，算法读的正是同一批字段 ⇒ 命中必然 ⇒ "
                "测的是推导一致性，不是发现隐藏关联 ⇒ 本版保留结构字段的同时补文本证据"
            ),
        },
        "unit": "组（finding group）",
        "version": CORPUS_VERSION,
        "kg_version": KG_VERSION,
        "org_id": ORG_ID,
        "entity_id_space": {
            "space": "graph_node_id",
            "human_readable_key": "supplier_id（S001–S120）**仅用于人工标注 / 复核**，不参与比对",
            "subject_id_form": "SUBJECT:<tax_id>",
            "document_id_form": "CONTRACT:<contract_no> / INVOICE:<invoice_no> / VOUCHER:<voucher_no>",
            "member_prefixes": ["SUBJECT:", "CONTRACT:", "INVOICE:", "VOUCHER:"],
            "non_member_prefixes": ["ADDRESS:", "PHONE:", "LEGALPERSON:"],
            "member_rule": (
                "共享节点（ADDRESS / PHONE / LEGALPERSON）不计入成员 ⇒ shared_* 的成员恒为 2 个主体"
            ),
            "verified_against_live_output": False,
            "verified_at": None,
            "verification_note": (
                "**待实测核对**：生成器产出后必须真跑一次 "
                "`AffiliationService.detect(kg_version=affiliation-demo-v2)`，"
                "逐组比对通过后才可置 true（未核对就比对会把「全不命中」读成「召回 0」⇒ 误触发 F2）"
            ),
        },
        "findings": findings,
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate() -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    rng = random.Random(SEED)
    suppliers = build_suppliers(rng)
    planted, used = _plant(suppliers, rng)
    shareholders = build_shareholders(suppliers, planted, used, rng)
    documents = build_documents(suppliers, planted, rng)
    documents["suppliers"] = [
        {
            "supplier_id": s.supplier_id,
            "tax_id": s.tax_id,
            "name": s.name,
            "address": s.address,
            "phone": s.phone,
            "legal_rep_name": s.legal_rep_name,
            "legal_rep_id": s.legal_rep_id,
        }
        for s in suppliers
    ]
    documents["shareholders"] = shareholders
    return documents, build_gold(suppliers, planted)


def self_check(
    documents: dict[str, list[dict[str, str]]], gold: dict[str, Any]
) -> list[str]:
    """生成器自检（**不写盘也能跑**）：规模 / 植入组 / 噪声唯一性 / 文本体现。"""
    problems: list[str] = []
    if len(documents["contracts"]) != N_CONTRACTS:
        problems.append(f"合同 {len(documents['contracts'])} ≠ {N_CONTRACTS}")
    if len(documents["invoices"]) != N_INVOICES:
        problems.append(f"发票 {len(documents['invoices'])} ≠ {N_INVOICES}")
    if len(documents["vouchers"]) != N_VOUCHERS:
        problems.append(f"凭证 {len(documents['vouchers'])} ≠ {N_VOUCHERS}")

    by_type: dict[str, int] = {}
    for finding in gold["findings"]:
        by_type[finding["type"]] = by_type.get(finding["type"], 0) + 1
        if not finding.get("text_evidence"):
            problems.append(f"{finding['type']} 组缺文本证据（A8 裁决 3）")
    if len(gold["findings"]) != 20:
        problems.append(f"植入组 {len(gold['findings'])} ≠ 20")
    for kind in (
        "shared_legal_rep",
        "shared_address",
        "shared_phone",
        "cycle",
        "amount_mismatch",
    ):
        if by_type.get(kind, 0) < N_PLANTED_PER_TYPE:
            problems.append(
                f"{kind} 只有 {by_type.get(kind, 0)} 组（须 ≥{N_PLANTED_PER_TYPE}）"
            )

    # 噪声唯一性：**除植入对外**不得有重复（重复即误报源）
    planted_pairs = {
        tuple(sorted(finding["tax_ids"]))
        for finding in gold["findings"]
        if finding["type"].startswith("shared_")
    }
    for attr in ("address", "phone", "legal_rep_id"):
        seen: dict[str, int] = {}
        for row in documents["suppliers"]:
            seen[row[attr]] = seen.get(row[attr], 0) + 1
        for value, count in seen.items():
            owners = [r["tax_id"] for r in documents["suppliers"] if r[attr] == value]
            if count > 1 and tuple(sorted(owners)) not in planted_pairs:
                problems.append(
                    f"{attr} 在非植入主体间重复 {count} 次 ⇒ 会变成误报：{value}"
                )

    # 三方金额：未植入的 trade_ref 三方必须相等
    by_ref: dict[str, dict[str, str]] = {}
    for table in ("contracts", "invoices", "vouchers"):
        for row in documents[table]:
            ref = row.get("trade_ref") or ""
            if not ref:
                continue
            by_ref.setdefault(ref, {})[table] = row["amount"]
    planted_refs = {
        f["trade_ref"] for f in gold["findings"] if f["type"] == "amount_mismatch"
    }
    for ref, amounts in by_ref.items():
        if len(amounts) != 3:
            problems.append(f"{ref} 三方不齐（{sorted(amounts)}）⇒ 或产生额外组合")
            continue
        equal = len(set(amounts.values())) == 1
        if ref in planted_refs and equal:
            problems.append(f"{ref} 是植入组却三方相等 ⇒ 不会被检出")
        if ref not in planted_refs and not equal:
            problems.append(f"{ref} 未植入却三方不等 ⇒ 会变成误报：{amounts}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="A8 扩标语料生成器（受控、可复现）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="语料输出目录")
    parser.add_argument(
        "--gold-file", default=str(DEFAULT_GOLD_FILE), help="gold 输出路径"
    )
    parser.add_argument("--check", action="store_true", help="只自检，不写盘")
    args = parser.parse_args()

    documents, gold = generate()
    problems = self_check(documents, gold)
    if problems:
        print("[FAIL] 生成器自检未过：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"[OK] 自检通过：合同 {len(documents['contracts'])} / 发票 {len(documents['invoices'])}"
        f" / 凭证 {len(documents['vouchers'])} / 主体 {len(documents['suppliers'])}"
        f" / 持股边 {len(documents['shareholders'])} / 植入 {len(gold['findings'])} 组"
    )
    if args.check:
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("suppliers", "shareholders", "contracts", "invoices", "vouchers"):
        _write_csv(out_dir / f"{name}.csv", documents[name])
    gold_path = Path(args.gold_file)
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    gold_path.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] 语料已写入 {out_dir}")
    print(f"[OK] gold 已写入 {gold_path}（verified=false ⇒ 实测核对后再置 true）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
