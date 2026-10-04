"""M4 四源 CSV → Neo4j 摄入 + 主体对齐（Sprint 9.11 批次 C1）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/ingest_affiliation_sources.py --dry-run  # 只解析 + 对齐，不写库
    uv run python scripts/ingest_affiliation_sources.py            # 摄入 + 对齐 + 落 PG
    uv run python scripts/ingest_affiliation_sources.py --purge    # 先清同版本（本版本专用，安全）

承接 ``specs/m4-affiliation-detection.md`` §3 验收 1 与 **§4.6**（schema 唯一真源）
与登记号 **S7.2-1**（``unaligned_subjects`` 空表）。

四条纪律（改动前先读）:

1. **schema 先冻结、后写算法**（plan §20 R14）——本批次只做「摄入 + 对齐」，
   **一行算法代码都不写**：三类算法与 ``amount_mismatch`` 属 **批次 C2**；
2. **确定性、不经 LLM**——结构化数据用 LLM 抽取是错配（``demo/attendance/mapping.yaml``
   同款纪律），全程 ¥0；
3. **双标签** ``:Entity:Subject`` / ``:Entity:Invoice`` / ``:Entity:Voucher``：
   ``:Subject`` 等是 §4.1 的语义标签（算法 Cypher 只认它），而真机读侧
   （``graphs.py`` / ``/graph/overview``）与疑点证据回溯（``_QUERY_AFFILIATION_EVIDENCE``）
   **只认 ``:Entity``** ⇒ 只打语义标签会重演「进得了库、查不出来」的老伤；
4. **独立 org + 独立 ``kg_version``**——合成数据写在 ``affiliation-demo-v1``，
   **不碰**演示库的 ``attendance-demo-v1``（无不可逆代价）。

**对齐率低不是靠调阈值凑出来的**：合成语料刻意植入 4 条必然未对齐的行
（见 ``demo/affiliation/README.md``），率 = 86/90 = 95.56%，判据线 0.95。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.models import EntityMergeCandidate, UnalignedSubject  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.kg.entity_resolution import (  # noqa: E402
    MergeCandidate,
    SubjectProfile,
    generate_candidates,
)
from app.services.kg.versioning import KgVersioningService  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
CORPUS_DIR = REPO_ROOT / "demo" / "affiliation"
DEFAULT_KG_VERSION = "affiliation-demo-v1"

#: 合成数据专用租户（uuid5 ⇒ 稳定可复现；**不是**演示库的 default_org_id）
AFFILIATION_DEMO_ORG_ID = uuid.uuid5(
    uuid.NAMESPACE_URL, "graphrag/affiliation/demo-org"
)

#: ``specs/m4-affiliation-detection.md`` §4.6 的对齐成功率判据
MIN_ALIGNMENT_RATE = 0.95

BATCH_SIZE = 800

# -- schema（逐字照 §4.6.1 / §4.6.2 + §4.6.6 增补）-----------------------
SUPPLIER_COLUMNS = (
    "supplier_id",
    "tax_id",
    "name",
    "address",
    # §4.6.6 增补：shared_phone / shared_legal_rep 的输入（入库即哈希，见下方）
    "phone",
    "legal_rep_name",
    "legal_rep_id",
)
SOURCE_COLUMNS = (
    "counterparty_tax_id",
    "counterparty_name",
    "counterparty_address",
    "amount",
    # §4.6.6 增补：三方金额比对的配对键（空 = 不参与比对）
    "trade_ref",
)
INVOICE_COLUMNS = ("invoice_no", *SOURCE_COLUMNS, "issue_date")
VOUCHER_COLUMNS = ("voucher_no", *SOURCE_COLUMNS, "posting_date")
#: §4.6.6 增补：合同（三方比对的第三方；**合成 CSV 替身**，见 §4.6.6 的偏离登记）
CONTRACT_COLUMNS = (
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
)
#: §4.6.6 增补：持股（``cycle`` 的输入）
SHAREHOLDER_COLUMNS = ("holder_tax_id", "held_tax_id", "share_pct", "since")

#: GB32100-2015 字符集（去 I / O / S / V / Z），**只验格式、不验校验位**——
#: 校验位会让合成语料为「看起来合法」而凑数（§4.6.1 已登记为已知限制）。
TAX_ID_PATTERN = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: 地址规范化要剔除的标点（全角经 NFKC 归一后再剔）
_ADDRESS_PUNCTUATION = re.compile(
    r"[.,;:!?'\"/\\|()\[\]{}<>、，。；：！？“”‘’（）【】《》\-—_]"
)


class CorpusError(Exception):
    """语料（CSV）不符合 §4.6 schema：逐条报出并终止，不静默跳过。"""


class IngestError(Exception):
    """入图 / 对齐流程的业务错误。"""


# --------------------------------------------------------------------------- #
# 规范化（三级对齐的判据，纯函数 ⇒ 可被单测直接钉死）
# --------------------------------------------------------------------------- #
#: 名称后缀（**长在前**，循环剥离到不再变化）
_NAME_SUFFIXES = ("有限责任公司", "有限公司", "股份", "公司")


def normalize_tax_id(raw: Any) -> str | None:
    """税号 → 规范形（大写、去空白）；格式非法返回 ``None``（**不**猜测补全）。"""
    text = str(raw or "").strip().upper()
    return text if TAX_ID_PATTERN.fullmatch(text) else None


def normalize_name(raw: Any) -> str:
    """名称 → 规范形：NFKC（全角→半角）+ 去空白 + 剥后缀。

    「北京恒信达科技有限公司」/「北京恒信达科技股份有限公司」都会落到
    「北京恒信达科技」⇒ 二者构成**多候选**，由调用方决定是否人工介入
    （宁可留人工，不猜）。
    """
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = re.sub(r"\s+", "", text)
    changed = True
    while changed:
        changed = False
        for suffix in _NAME_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)]
                changed = True
                break
    return text


def normalize_address(raw: Any) -> str:
    """地址 → 规范形：NFKC + 去空白 + 去标点。

    **不**做「省市区裁剪」：那会把同市不同区的两家并成一家（假合并比漏合并危险）。
    """
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = re.sub(r"\s+", "", text)
    return _ADDRESS_PUNCTUATION.sub("", text)


# --------------------------------------------------------------------------- #
# §4.6.6：共享节点的 id（**只存哈希**，spec §4.1 对 :Phone / :LegalPerson 的硬要求）
# --------------------------------------------------------------------------- #
def _digest(raw: str) -> str:
    """→ sha256 前 16 位 hex（确定性、跨库一致；**不可逆**，原值不出库）。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def address_node_id(raw: Any) -> str:
    """规范化地址 → ``:Address`` 节点 id（同址 ⇒ 同一节点 ⇒ shared_address 命中）。"""
    return f"ADDRESS:{_digest(normalize_address(raw))}"


def legal_person_node_id(name: Any, id_number: Any) -> str:
    """法人「姓名 + 证件号」→ ``:LegalPerson`` 节点 id。

    **两个字段一起哈希**：只按姓名会让同名不同人并成一个（假合并）；
    只按证件号则姓名变了就断链。证件号**不落库**（只留哈希）。
    """
    key = f"{normalize_name(name)}|{str(id_number or '').strip().upper()}"
    return f"LEGALPERSON:{_digest(key)}"


def phone_node_id(raw: Any) -> str:
    """电话 → ``:Phone`` 节点 id（号码**不落库**）。"""
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = re.sub(r"[\s\-()（）]", "", text)
    return f"PHONE:{_digest(text)}"


# --------------------------------------------------------------------------- #
# 语料读取与校验
# --------------------------------------------------------------------------- #
def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise CorpusError(f"CSV 不存在: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_optional(path: Path) -> list[dict[str, str]]:
    """§4.6.6 增补的两张表**允许缺失**：缺了就当空表（三类算法无输入，但不报错）。"""
    if not path.is_file():
        return []
    return read_csv(path)


def _require_columns(
    rows: list[dict[str, str]],
    *,
    file_name: str,
    columns: tuple[str, ...],
    unique: str | None,
    nullable: tuple[str, ...] = (),
) -> None:
    """校验「列必须存在 + 非可空列的值必须非空」。

    ``nullable`` 内的列**允许空值**——例如 ``counterparty_tax_id`` 缺失是 §4.5 明列
    的真实业务情形（退到名称 / 地址级），把它当语料错误会掩盖真实场景。
    但**有值却格式非法**仍属错误，由 :func:`validate_corpus` 报出。
    """
    if not rows:
        raise CorpusError(f"{file_name}: 空表")
    missing = [col for col in columns if col not in rows[0]]
    if missing:
        raise CorpusError(f"{file_name} 缺少列 {missing}（schema 见 m4 §4.6）")
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):  # +1 = 表头
        for col in columns:
            if col in nullable:
                continue
            if not str(row.get(col) or "").strip():
                raise CorpusError(f"{file_name} 第 {index} 行：必填列 {col} 为空")
        if unique is not None:
            value = str(row[unique]).strip()
            if value in seen:
                raise CorpusError(f"{file_name} 第 {index} 行：{unique} 重复 {value}")
            seen.add(value)


def _parse_amount(raw: Any, *, where: str) -> float:
    text = str(raw or "").strip()
    try:
        value = float(text)
    except ValueError as exc:
        raise CorpusError(f"{where}: amount 非数值 {text!r}") from exc
    if value <= 0:
        raise CorpusError(f"{where}: amount 必须 > 0，实际 {value}")
    return value


def validate_corpus(
    suppliers: list[dict[str, str]],
    invoices: list[dict[str, str]],
    vouchers: list[dict[str, str]],
    contracts: list[dict[str, str]] | None = None,
    shareholders: list[dict[str, str]] | None = None,
) -> None:
    """逐条校验：任何一条不合规都**报出并终止**（不静默跳过脏数据）。

    后两张表（``contracts`` / ``shareholders``）是 §4.6.6 增补，**允许缺省**——
    Sprint 9.11 的语料没有它们，不该因为跑旧语料就报错。
    """
    _require_columns(
        suppliers,
        file_name="suppliers.csv",
        columns=SUPPLIER_COLUMNS,
        unique="supplier_id",
    )
    _require_columns(
        invoices,
        file_name="invoices.csv",
        columns=INVOICE_COLUMNS,
        unique="invoice_no",
        nullable=("counterparty_tax_id", "trade_ref"),
    )
    _require_columns(
        vouchers,
        file_name="vouchers.csv",
        columns=VOUCHER_COLUMNS,
        unique="voucher_no",
        nullable=("counterparty_tax_id", "trade_ref"),
    )
    if contracts is not None:
        _require_columns(
            contracts,
            file_name="contracts.csv",
            columns=CONTRACT_COLUMNS,
            unique="contract_no",
            nullable=("trade_ref",),
        )
        for row in contracts:
            where = f"contracts.csv[{row['contract_no']}]"
            _parse_amount(row["amount"], where=where)
            if not DATE_PATTERN.fullmatch(str(row["signed_date"]).strip()):
                raise CorpusError(f"{where}: signed_date 非 YYYY-MM-DD")
    if shareholders is not None:
        # 持股表**无单列主键**（同一家可以持多家）⇒ 唯一性按组合键查
        _require_columns(
            shareholders,
            file_name="shareholders.csv",
            columns=SHAREHOLDER_COLUMNS,
            unique=None,
        )
        seen_pairs: set[tuple[str, str]] = set()
        for index, row in enumerate(shareholders, start=2):
            pair = (
                str(row["holder_tax_id"]).strip(),
                str(row["held_tax_id"]).strip(),
            )
            if pair in seen_pairs:
                raise CorpusError(
                    f"shareholders.csv 第 {index} 行：持股关系重复 {pair}"
                )
            seen_pairs.add(pair)
            for field_name in ("holder_tax_id", "held_tax_id"):
                if normalize_tax_id(row[field_name]) is None:
                    raise CorpusError(
                        f"shareholders.csv 第 {index} 行：{field_name} 格式非法 "
                        f"{row[field_name]!r}"
                    )
            if not DATE_PATTERN.fullmatch(str(row["since"]).strip()):
                raise CorpusError(
                    f"shareholders.csv 第 {index} 行：since 非 YYYY-MM-DD"
                )
            try:
                pct = float(str(row["share_pct"]).strip())
            except ValueError as exc:
                raise CorpusError(
                    f"shareholders.csv 第 {index} 行：share_pct 非数值"
                ) from exc
            if not 0 < pct <= 100:
                raise CorpusError(
                    f"shareholders.csv 第 {index} 行：share_pct 须 (0, 100]，实际 {pct}"
                )

    for row in suppliers:
        where = f"suppliers.csv[{row['supplier_id']}]"
        if normalize_tax_id(row["tax_id"]) is None:
            raise CorpusError(f"{where}: tax_id 格式非法 {row['tax_id']!r}")

    for file_name, rows, key, date_key in (
        ("invoices.csv", invoices, "invoice_no", "issue_date"),
        ("vouchers.csv", vouchers, "voucher_no", "posting_date"),
    ):
        for row in rows:
            where = f"{file_name}[{row[key]}]"
            tax_raw = str(row["counterparty_tax_id"] or "").strip()
            # 空 = 「税号缺失」这一**真实业务情形**（可走名称/地址级）；
            # 有值却格式非法 = 语料错误，必须报出来，不能当缺失蒙混。
            if tax_raw and normalize_tax_id(tax_raw) is None:
                raise CorpusError(f"{where}: counterparty_tax_id 格式非法 {tax_raw!r}")
            _parse_amount(row["amount"], where=where)
            if not DATE_PATTERN.fullmatch(str(row[date_key]).strip()):
                raise CorpusError(
                    f"{where}: {date_key} 非 YYYY-MM-DD {row[date_key]!r}"
                )


# --------------------------------------------------------------------------- #
# 对齐（三级递减，先命中者胜）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AlignmentMatch:
    """一次对齐的结果。

    ``subject_id`` 为 ``None`` ⇒ 未对齐，此时 ``reason`` 必非空，
    取值逐字照 §4.6.4（``tax_id_missing`` / ``name_mismatch`` / ``multiple_candidates``）。
    """

    subject_id: str | None
    level: str | None = None
    reason: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MasterIndex:
    """canonical 主体（供应商主数据）的三级索引。"""

    by_tax_id: dict[str, list[str]] = field(default_factory=dict)
    by_name: dict[str, list[str]] = field(default_factory=dict)
    by_address: dict[str, list[str]] = field(default_factory=dict)
    #: ``subject_id -> {name, address, phone, legal_rep, tax_id, supplier_id}``
    #: （写节点 / 打印明细 / **S9.13 实体消解的结构信号**三处共用）
    subjects: dict[str, dict[str, str]] = field(default_factory=dict)


def build_master_index(suppliers: list[dict[str, str]]) -> MasterIndex:
    index = MasterIndex()
    for row in suppliers:
        tax_id = normalize_tax_id(row["tax_id"])
        if tax_id is None:  # 已由 validate_corpus 拦截，这里只做防御
            raise CorpusError(f"suppliers.csv[{row['supplier_id']}]: tax_id 非法")
        subject_id = f"SUBJECT:{tax_id}"
        index.subjects[subject_id] = {
            "name": str(row["name"]).strip(),
            "address": str(row["address"]).strip(),
            "supplier_id": str(row["supplier_id"]).strip(),
            "tax_id": tax_id,
            # S9.13：消解的结构信号（共享电话 / 共享法人）——**原值只在此处**，
            # 入图即哈希（spec §4.1）；比较用规范化后的字符串，不碰哈希
            "phone": str(row.get("phone") or "").strip(),
            "legal_rep": str(row.get("legal_rep_name") or "").strip(),
        }
        for bucket, key in (
            (index.by_tax_id, tax_id),
            (index.by_name, normalize_name(row["name"])),
            (index.by_address, normalize_address(row["address"])),
        ):
            bucket.setdefault(key, []).append(subject_id)
    return index


def align_counterparty(row: dict[str, str], index: MasterIndex) -> AlignmentMatch:
    """一条发票 / 凭证行的抬头 → canonical 主体（税号 → 名称 → 地址）。"""
    tax_id = normalize_tax_id(row.get("counterparty_tax_id"))
    levels = (
        ("tax_id", index.by_tax_id, tax_id or ""),
        ("name", index.by_name, normalize_name(row.get("counterparty_name"))),
        (
            "address",
            index.by_address,
            normalize_address(row.get("counterparty_address")),
        ),
    )
    for level, bucket, key in levels:
        if not key:
            continue
        hits = bucket.get(key) or []
        if len(hits) > 1:
            # 多候选**不自动合并**：并错两家比漏并一家危险得多
            return AlignmentMatch(
                subject_id=None,
                reason="multiple_candidates",
                candidates=tuple(sorted(hits)),
            )
        if len(hits) == 1:
            return AlignmentMatch(subject_id=hits[0], level=level)
    return AlignmentMatch(
        subject_id=None,
        reason="tax_id_missing" if tax_id is None else "name_mismatch",
    )


@dataclass
class AlignmentStats:
    total: int = 0
    aligned: int = 0
    unaligned: int = 0
    by_level: dict[str, int] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)
    unaligned_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.aligned / self.total if self.total else 0.0


def align_sources(
    invoices: list[dict[str, str]],
    vouchers: list[dict[str, str]],
    index: MasterIndex,
) -> tuple[dict[str, AlignmentMatch], dict[str, AlignmentMatch], AlignmentStats]:
    """对齐全部发票 / 凭证行。

    :returns: ``(invoice_matches, voucher_matches, stats)``，key = 业务主键。
    """
    stats = AlignmentStats()
    invoice_matches: dict[str, AlignmentMatch] = {}
    voucher_matches: dict[str, AlignmentMatch] = {}

    for file_name, rows, key, matches in (
        ("invoices.csv", invoices, "invoice_no", invoice_matches),
        ("vouchers.csv", vouchers, "voucher_no", voucher_matches),
    ):
        for row in rows:
            business_key = str(row[key]).strip()
            match = align_counterparty(row, index)
            matches[business_key] = match
            stats.total += 1
            if match.subject_id is not None:
                stats.aligned += 1
                stats.by_level[str(match.level)] = (
                    stats.by_level.get(str(match.level), 0) + 1
                )
                continue
            stats.unaligned += 1
            stats.by_reason[str(match.reason)] = (
                stats.by_reason.get(str(match.reason), 0) + 1
            )
            stats.unaligned_rows.append(
                {
                    "file": file_name,
                    "key": business_key,
                    "raw_name": str(row["counterparty_name"]).strip(),
                    # S9.13：消解的 **N1 税号冲突**判据要用（缺失 = 不参与否决）
                    "raw_tax_id": normalize_tax_id(row.get("counterparty_tax_id")),
                    "reason": str(match.reason),
                    "candidates": list(match.candidates),
                    "source_doc_id": _evidence_doc_id(file_name),
                }
            )

    return invoice_matches, voucher_matches, stats


# --------------------------------------------------------------------------- #
# 实体消解（Sprint 9.13 批次 C3）
#
# 判据**不在本文件**——冻结在 ``specs/m2-extract-kg.md`` §4.5.1。本段只做编排：
# 组装 profile → 调 ``generate_candidates`` → 把自动合并的结果**回写对齐结果**
# （于是建图时边就指向 canonical 节点 = 「摄入时归一」，不是事后改写图）。
# --------------------------------------------------------------------------- #
def _raw_profile(row: dict[str, Any]) -> SubjectProfile:
    """未对齐主体 → 消解输入。

    ``subject_id`` 用**稳定合成 id** ``RAW:<file>:<key>``：候选表要落这一列，
    用行号 / 随机 uuid 会让「这条候选是哪一行来的」无法回查。
    """
    return SubjectProfile(
        subject_id=f"RAW:{row['file']}:{row['key']}",
        norm_name=normalize_name(row["raw_name"]),
        raw_name=str(row["raw_name"]),
        tax_id=row.get("raw_tax_id"),
    )


def _canonical_profiles(index: MasterIndex) -> list[SubjectProfile]:
    """canonical 主体 → 消解输入（含结构信号：地址 / 电话 / 法人）。"""
    return sorted(
        (
            SubjectProfile(
                subject_id=subject_id,
                norm_name=normalize_name(attrs["name"]),
                raw_name=attrs["name"],
                tax_id=attrs.get("tax_id"),
                address=normalize_address(attrs.get("address")) or None,
                phone=attrs.get("phone") or None,
                legal_rep=attrs.get("legal_rep") or None,
            )
            for subject_id, attrs in index.subjects.items()
        ),
        key=lambda profile: profile.subject_id,
    )


def resolve_unaligned(
    *,
    index: MasterIndex,
    stats: AlignmentStats,
    invoice_matches: dict[str, AlignmentMatch],
    voucher_matches: dict[str, AlignmentMatch],
) -> tuple[list[MergeCandidate], list[dict[str, Any]]]:
    """对未对齐主体跑消解，并把 ``auto_merged`` 的结果回写进对齐结果。

    :returns: ``(candidates, resolved_rows)``——``resolved_rows`` 是被自动合并掉的
        未对齐行，落库时写 ``status='aligned'``（留痕：它曾经未对齐过）。
    """
    raw_rows = list(stats.unaligned_rows)
    resolution = generate_candidates(
        _canonical_profiles(index), [_raw_profile(row) for row in raw_rows]
    )

    raw_by_id = {f"RAW:{row['file']}:{row['key']}": row for row in raw_rows}
    resolved_rows: list[dict[str, Any]] = []
    merged_ids: set[str] = set()
    for raw_id, canonical_id in sorted(resolution.auto_merges.items()):
        row = raw_by_id[raw_id]
        matches = invoice_matches if row["file"] == "invoices.csv" else voucher_matches
        matches[str(row["key"])] = AlignmentMatch(
            subject_id=canonical_id, level="resolution"
        )
        stats.aligned += 1
        stats.unaligned -= 1
        stats.by_level["resolution"] = stats.by_level.get("resolution", 0) + 1
        reason = str(row["reason"])
        if stats.by_reason.get(reason):
            stats.by_reason[reason] -= 1
        merged_ids.add(raw_id)
        resolved_rows.append({**row, "merged_into": canonical_id})

    if merged_ids:
        stats.unaligned_rows = [
            row
            for row in stats.unaligned_rows
            if f"RAW:{row['file']}:{row['key']}" not in merged_ids
        ]
    return resolution.candidates, resolved_rows


# --------------------------------------------------------------------------- #
# 建节点 / 关系
# --------------------------------------------------------------------------- #
def build_graph_rows(
    suppliers: list[dict[str, str]],
    invoices: list[dict[str, str]],
    vouchers: list[dict[str, str]],
    invoice_matches: dict[str, AlignmentMatch],
    voucher_matches: dict[str, AlignmentMatch],
    contracts: list[dict[str, str]] | None = None,
    shareholders: list[dict[str, str]] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """产出 ``(subject_rows, invoice_rows, voucher_rows, extra_rows, relation_rows)``。

    ``extra_rows`` 是 §4.6.6 增补的 **共享节点**（``:Address`` / ``:LegalPerson`` /
    ``:Phone``）与 ``:Contract``，按 ``label`` 字段分派 Cypher。后两张表缺省时
    （旧语料）这两类为空 ⇒ 不产出三类算法所需的节点——**有输入才有输出**。
    """
    subject_rows: list[dict[str, Any]] = []
    invoice_rows: list[dict[str, Any]] = []
    voucher_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    #: ``subject_id -> [可回溯的 :Entity id]``（供 ``_QUERY_AFFILIATION_EVIDENCE`` 用）
    source_entity_ids: dict[str, list[str]] = {}
    #: 共享节点 id -> 持有它的主体 id（共享节点的证据**只能**借主体的 chunk）
    shared_source_ids: dict[str, list[str]] = {}

    def _remember_shared(node_id: str, props: dict[str, Any], holder: str) -> None:
        if not any(row["id"] == node_id for row in extra_rows):
            extra_rows.append({**props, "id": node_id, "source_entity_ids": []})
        shared_source_ids.setdefault(node_id, []).append(holder)

    for row in suppliers:
        subject_id = f"SUBJECT:{normalize_tax_id(row['tax_id'])}"
        subject_rows.append(
            {
                "id": subject_id,
                "canonical_name": str(row["name"]).strip(),
                "tax_id": normalize_tax_id(row["tax_id"]),
                # §4.1 未列 address：此处为三级对齐留可核留痕（§4.6.5 已登记）
                "address": str(row["address"]).strip(),
                "source_entity_ids": [],
            }
        )
        # ---- §4.6.6：共享节点（同址 / 同法人 / 同号 ⇒ 同一节点 ⇒ 疑点命中）----
        address_id = address_node_id(row["address"])
        _remember_shared(
            address_id,
            {
                "label": "Address",
                "canonical_name": str(row["address"]).strip(),
                "full_address": str(row["address"]).strip(),
            },
            subject_id,
        )
        relation_rows.append(
            {
                "id": f"REGISTERED_AT:{subject_id}->{address_id}",
                "kind": "REGISTERED_AT",
                "head": subject_id,
                "tail": address_id,
            }
        )
        person_id = legal_person_node_id(row["legal_rep_name"], row["legal_rep_id"])
        _remember_shared(
            person_id,
            {
                "label": "LegalPerson",
                # 只留姓名做展示名；**证件号不落库**（spec §4.1：仅哈希）
                "canonical_name": str(row["legal_rep_name"]).strip(),
                "id_hash": person_id.split(":", 1)[1],
                "id_type": "ID_CARD",
            },
            subject_id,
        )
        relation_rows.append(
            {
                "id": f"LEGAL_REP:{subject_id}->{person_id}",
                "kind": "LEGAL_REP",
                "head": subject_id,
                "tail": person_id,
            }
        )
        phone_id = phone_node_id(row["phone"])
        _remember_shared(
            phone_id,
            {
                "label": "Phone",
                "canonical_name": "联系电话",
                "number_hash": phone_id.split(":", 1)[1],
            },
            subject_id,
        )
        relation_rows.append(
            {
                "id": f"CONTACT_PHONE:{subject_id}->{phone_id}",
                "kind": "CONTACT_PHONE",
                "head": subject_id,
                "tail": phone_id,
            }
        )

    for row in invoices:
        key = str(row["invoice_no"]).strip()
        node_id = f"INVOICE:{key}"
        invoice_rows.append(
            {
                "id": node_id,
                "canonical_name": f"发票 {key}",
                "invoice_no": key,
                "amount": _parse_amount(row["amount"], where=f"invoices.csv[{key}]"),
                "issue_date": str(row["issue_date"]).strip(),
                "issuer_tax_id": str(row["counterparty_tax_id"] or "").strip() or None,
                "counterparty_name": str(row["counterparty_name"]).strip(),
                # §4.6.6：三方金额比对的配对键（空 = 不参与比对）
                "trade_ref": str(row.get("trade_ref") or "").strip() or None,
                # 自指：发票行自己的 chunk 经 MENTIONS 指向本节点 ⇒ 证据可回溯
                "source_entity_ids": [node_id],
            }
        )
        match = invoice_matches[key]
        if match.subject_id is not None:
            relation_rows.append(
                {
                    "id": f"ISSUED:{match.subject_id}->{node_id}",
                    "kind": "ISSUED",
                    "head": match.subject_id,
                    "tail": node_id,
                }
            )
            source_entity_ids.setdefault(match.subject_id, []).append(node_id)

    for row in vouchers:
        key = str(row["voucher_no"]).strip()
        node_id = f"VOUCHER:{key}"
        voucher_rows.append(
            {
                "id": node_id,
                "canonical_name": f"凭证 {key}",
                "voucher_no": key,
                "amount": _parse_amount(row["amount"], where=f"vouchers.csv[{key}]"),
                "posting_date": str(row["posting_date"]).strip(),
                "issuer_tax_id": str(row["counterparty_tax_id"] or "").strip() or None,
                "counterparty_name": str(row["counterparty_name"]).strip(),
                "trade_ref": str(row.get("trade_ref") or "").strip() or None,
                "source_entity_ids": [node_id],
            }
        )
        match = voucher_matches[key]
        if match.subject_id is not None:
            # spec §4.2：``:POSTED_IN`` 的端点是 ``:Voucher → :Subject``（**方向照抄**）
            relation_rows.append(
                {
                    "id": f"POSTED_IN:{node_id}->{match.subject_id}",
                    "kind": "POSTED_IN",
                    "head": node_id,
                    "tail": match.subject_id,
                }
            )
            source_entity_ids.setdefault(match.subject_id, []).append(node_id)

    # ---- §4.6.6：合同（三方比对的第三方）+ 当事人关系 ----
    for row in contracts or []:
        contract_no = str(row["contract_no"]).strip()
        node_id = f"CONTRACT:{contract_no}"
        extra_rows.append(
            {
                "id": node_id,
                "label": "Contract",
                "canonical_name": f"合同 {contract_no}",
                "contract_no": contract_no,
                "amount": _parse_amount(
                    row["amount"], where=f"contracts.csv[{contract_no}]"
                ),
                "signed_date": str(row["signed_date"]).strip(),
                "trade_ref": str(row.get("trade_ref") or "").strip() or None,
                "source_entity_ids": [node_id],
            }
        )
        for role in ("a", "b"):
            tax_id = normalize_tax_id(row[f"party_{role}_tax_id"])
            if tax_id is None:
                # 合同当事人的税号**必填**（合同不是"待对齐源"，无需三级回退）
                raise CorpusError(
                    f"contracts.csv[{contract_no}]: party_{role}_tax_id 非法"
                )
            party_id = f"SUBJECT:{tax_id}"
            if not any(str(item["id"]) == party_id for item in subject_rows):
                # 我方主体不在供应商主数据里：照建 :Subject（合同当事人必须是主体），
                # 但**不写 unaligned**——未对齐只统计发票 / 凭证（§4.6.3）。
                subject_rows.append(
                    {
                        "id": party_id,
                        "canonical_name": str(row[f"party_{role}_name"]).strip(),
                        "tax_id": tax_id,
                        "address": str(row[f"party_{role}_address"]).strip(),
                        "source_entity_ids": [],
                    }
                )
            relation_rows.append(
                {
                    "id": f"PARTY_TO:{party_id}->{node_id}:{role.upper()}",
                    "kind": "PARTY_TO",
                    "head": party_id,
                    "tail": node_id,
                    "role": role.upper(),
                }
            )

    # ---- §4.6.6：持股（``cycle`` 的输入；端点必须都是已建主体）----
    known_subjects = {str(item["id"]) for item in subject_rows}
    for row in shareholders or []:
        holder_id = f"SUBJECT:{normalize_tax_id(row['holder_tax_id'])}"
        held_id = f"SUBJECT:{normalize_tax_id(row['held_tax_id'])}"
        missing = [item for item in (holder_id, held_id) if item not in known_subjects]
        if missing:
            # 持股指向主数据外的主体 ⇒ 环会断 ⇒ 宁可报出来，不静默丢边
            raise CorpusError(f"shareholders.csv: 持股端点不在供应商主数据 {missing}")
        relation_rows.append(
            {
                "id": f"SHARES_HOLDER:{holder_id}->{held_id}",
                "kind": "SHARES_HOLDER",
                "head": holder_id,
                "tail": held_id,
                "share_pct": float(str(row["share_pct"]).strip()),
                "since": str(row["since"]).strip(),
            }
        )

    for subject_row in subject_rows:
        ids = sorted(set(source_entity_ids.get(str(subject_row["id"]), [])))
        subject_row["source_entity_ids"] = ids

    # 共享节点（地址 / 法人 / 电话）自己没有 chunk ⇒ 证据**借**持有它的主体
    for extra_row in extra_rows:
        node_id = str(extra_row["id"])
        if node_id not in shared_source_ids:
            # :Contract 自己就是源实体（自指，建行时已填）——**不能**被下面的
            # 共享节点收尾覆盖成 []，否则金额比对命中也取不到证据（真机实测：
            # 3 条命中全因 src=[] 被「无证据不产疑点」丢弃）。
            continue
        extra_row["source_entity_ids"] = sorted(set(shared_source_ids[node_id]))

    return subject_rows, invoice_rows, voucher_rows, extra_rows, relation_rows


# --------------------------------------------------------------------------- #
# 证据层（R14 + R16）：CSV 原文行 → :Document + :Chunk + MENTIONS
# --------------------------------------------------------------------------- #
def _evidence_doc_id(file_name: str) -> uuid.UUID:
    """CSV → ``:Document`` id（uuid5 ⇒ 同表恒同一 id，重跑幂等）。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"graphrag/affiliation/csv/{file_name}")


def _evidence_chunk_id(file_name: str, business_key: str) -> str:
    """一行 → ``:Chunk`` id。

    **形态必须是 ``chunk-<12 hex>``**（Sprint 9.5 真机事故，R16）：
    ``app/services/agents.py::_CITATION_ID_PATTERN`` 只认 ``chunk-[0-9A-Za-z]``，
    冒号形态的 id 抠不出来 ⇒ 引用被静默丢弃 ⇒ 问答以 ``no_grounded_evidence`` 拒答。
    """
    seed = uuid.uuid5(
        uuid.NAMESPACE_URL, f"graphrag/affiliation/chunk/{file_name}/{business_key}"
    )
    return f"chunk-{seed.hex[:12]}"


def build_evidence(
    suppliers: list[dict[str, str]],
    invoices: list[dict[str, str]],
    vouchers: list[dict[str, str]],
    contracts: list[dict[str, str]] | None = None,
    shareholders: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """把各表的**原文行**落为可引用证据（供应商主数据同样落一份，便于回溯）。

    ``shareholders.csv`` 一行涉及**两个**主体 ⇒ 一条 chunk 挂 **两条** MENTIONS——
    否则 ``cycle`` 疑点回溯时只能看到一半当事人（§3 验收 4：引用必须具体到凭证）。
    """
    doc_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    mention_rows: list[dict[str, Any]] = []

    def _subject(tax_id: Any) -> str:
        return f"SUBJECT:{normalize_tax_id(tax_id)}"

    tables: list[tuple[str, list[dict[str, str]], Any, Any]] = [
        (
            "suppliers.csv",
            suppliers,
            lambda r: r["supplier_id"],
            lambda r: [_subject(r["tax_id"])],
        ),
        (
            "invoices.csv",
            invoices,
            lambda r: r["invoice_no"],
            lambda r: [f"INVOICE:{str(r['invoice_no']).strip()}"],
        ),
        (
            "vouchers.csv",
            vouchers,
            lambda r: r["voucher_no"],
            lambda r: [f"VOUCHER:{str(r['voucher_no']).strip()}"],
        ),
    ]
    if contracts:
        tables.append(
            (
                "contracts.csv",
                contracts,
                lambda r: r["contract_no"],
                lambda r: [f"CONTRACT:{str(r['contract_no']).strip()}"],
            )
        )
    if shareholders:
        tables.append(
            (
                "shareholders.csv",
                shareholders,
                lambda r: f"{r['holder_tax_id']}->{r['held_tax_id']}",
                lambda r: [_subject(r["holder_tax_id"]), _subject(r["held_tax_id"])],
            )
        )

    for file_name, rows, key_fn, entity_fn in tables:
        if not rows:
            continue
        header = ",".join(str(col) for col in rows[0].keys())
        lines = [header] + [",".join(str(v) for v in row.values()) for row in rows]
        full_text = "\n".join(lines)
        doc_id = _evidence_doc_id(file_name)
        doc_rows.append({"id": str(doc_id), "title": file_name})

        for index, row in enumerate(rows, start=1):
            line = lines[index]
            business_key = str(key_fn(row)).strip()
            text = line
            char_start = max(full_text.find(line), 0)
            chunk_id = _evidence_chunk_id(file_name, business_key)
            chunk_rows.append(
                {
                    "id": chunk_id,
                    "doc_id": str(doc_id),
                    "text": text,
                    "char_start": char_start,
                    "char_end": char_start + len(text),
                    "page": None,  # CSV 无页码 ⇒ null（严禁伪造）
                }
            )
            for entity_id in entity_fn(row):
                mention_rows.append(
                    {
                        "id": f"{chunk_id}:mentions:{entity_id}",
                        "chunk_id": chunk_id,
                        "entity_id": entity_id,
                    }
                )

    return doc_rows, chunk_rows, mention_rows


# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #
_CYPHER_CONSTRAINTS = (
    "CREATE CONSTRAINT entity_id_version_unique IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE (n.id, n.kg_version) IS UNIQUE",
    "CREATE CONSTRAINT kg_version_unique IF NOT EXISTS "
    "FOR (v:KgVersion) REQUIRE v.version IS UNIQUE",
)

_CYPHER_MERGE_KG_VERSION = """
MERGE (v:KgVersion {version: $kg_version})
SET v.status = $status, v.scope = $scope, v.trace_id = $trace_id, v.updated_at = $now
RETURN v.status AS status
"""

_CYPHER_SET_VERSION_STATUS = """
MATCH (v:KgVersion {version: $kg_version})
SET v.status = $status, v.updated_at = $now,
    v.error_code = $error_code, v.error_detail = $error_detail,
    v.entity_count = $entity_count, v.relation_count = $relation_count
RETURN v.status AS status
"""

#: ``name`` 与 ``canonical_name`` **都写**：spec §4.1 的属性名是 ``name``（算法
#: Cypher 认它），而真机读侧（``graphs.py`` / ``/graph/overview``）只认
#: ``canonical_name``。只写前者 ⇒ 概览里主体名为空；只写后者 ⇒ 疑点里主体名恒为
#: ``null``（真机实测 names=['None', 'None']，S9.12 修的就是这个）。
_CYPHER_MERGE_SUBJECTS = """
UNWIND $rows AS row
MERGE (n:Entity:Subject {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'SUBJECT',
    n.name = row.canonical_name,
    n.tax_id = row.tax_id, n.address = row.address,
    n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

_CYPHER_MERGE_INVOICES = """
UNWIND $rows AS row
MERGE (n:Entity:Invoice {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'INVOICE',
    n.invoice_no = row.invoice_no, n.amount = row.amount,
    n.issue_date = row.issue_date, n.issuer_tax_id = row.issuer_tax_id,
    n.trade_ref = row.trade_ref,
    n.counterparty_name = row.counterparty_name,
    n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

_CYPHER_MERGE_VOUCHERS = """
UNWIND $rows AS row
MERGE (n:Entity:Voucher {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'VOUCHER',
    n.voucher_no = row.voucher_no, n.amount = row.amount,
    n.posting_date = row.posting_date, n.issuer_tax_id = row.issuer_tax_id,
    n.trade_ref = row.trade_ref,
    n.counterparty_name = row.counterparty_name,
    n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

# -- §4.6.6 增补的共享节点与合同节点（**双标签**理由同 §4.6.5）------------
_CYPHER_MERGE_ADDRESS = """
UNWIND $rows AS row
MERGE (n:Entity:Address {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'ADDRESS',
    n.full_address = row.full_address, n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

#: ``name`` 双写的理由同 :Subject——``_QUERY_SHARED_LEGAL_REP`` 读的是 ``l.name``，
#: 只写 ``canonical_name`` ⇒ 疑点里法人名恒为 null（真机实测 names 末位为 'None'）。
#: **证件号仍然只存哈希**（spec §4.1 硬要求），展示名只取姓名。
_CYPHER_MERGE_LEGAL_PERSON = """
UNWIND $rows AS row
MERGE (n:Entity:LegalPerson {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'LEGAL_PERSON',
    n.name = row.canonical_name,
    n.id_hash = row.id_hash, n.id_type = row.id_type,
    n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

_CYPHER_MERGE_PHONE = """
UNWIND $rows AS row
MERGE (n:Entity:Phone {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'PHONE',
    n.number_hash = row.number_hash, n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

_CYPHER_MERGE_CONTRACT = """
UNWIND $rows AS row
MERGE (n:Entity:Contract {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name, n.entity_type = 'CONTRACT',
    n.contract_no = row.contract_no, n.amount = row.amount,
    n.signed_date = row.signed_date, n.trade_ref = row.trade_ref,
    n.source_entity_ids = row.source_entity_ids,
    n.org_id = $org_id, n.trace_id = $trace_id
RETURN count(n) AS merged
"""

_CYPHER_MERGE_ISSUED = """
UNWIND $rows AS row
MATCH (s:Subject {id: row.head, kg_version: $kg_version})
MATCH (i:Invoice {id: row.tail, kg_version: $kg_version})
MERGE (s)-[r:ISSUED {id: row.id, kg_version: $kg_version}]->(i)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_POSTED_IN = """
UNWIND $rows AS row
MATCH (v:Voucher {id: row.head, kg_version: $kg_version})
MATCH (s:Subject {id: row.tail, kg_version: $kg_version})
MERGE (v)-[r:POSTED_IN {id: row.id, kg_version: $kg_version}]->(s)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

# -- §4.6.6 增补的关系（端点方向逐字照 §4.2）-------------------------------
_CYPHER_MERGE_REGISTERED_AT = """
UNWIND $rows AS row
MATCH (s:Subject {id: row.head, kg_version: $kg_version})
MATCH (a:Address {id: row.tail, kg_version: $kg_version})
MERGE (s)-[r:REGISTERED_AT {id: row.id, kg_version: $kg_version}]->(a)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_LEGAL_REP = """
UNWIND $rows AS row
MATCH (s:Subject {id: row.head, kg_version: $kg_version})
MATCH (l:LegalPerson {id: row.tail, kg_version: $kg_version})
MERGE (s)-[r:LEGAL_REP {id: row.id, kg_version: $kg_version}]->(l)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_CONTACT_PHONE = """
UNWIND $rows AS row
MATCH (s:Subject {id: row.head, kg_version: $kg_version})
MATCH (p:Phone {id: row.tail, kg_version: $kg_version})
MERGE (s)-[r:CONTACT_PHONE {id: row.id, kg_version: $kg_version}]->(p)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_SHARES_HOLDER = """
UNWIND $rows AS row
MATCH (a:Subject {id: row.head, kg_version: $kg_version})
MATCH (b:Subject {id: row.tail, kg_version: $kg_version})
MERGE (a)-[r:SHARES_HOLDER {id: row.id, kg_version: $kg_version}]->(b)
SET r.share_pct = row.share_pct, r.since = row.since,
    r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_PARTY_TO = """
UNWIND $rows AS row
MATCH (s:Subject {id: row.head, kg_version: $kg_version})
MATCH (c:Contract {id: row.tail, kg_version: $kg_version})
MERGE (s)-[r:PARTY_TO {id: row.id, kg_version: $kg_version}]->(c)
SET r.role = row.role, r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_MERGE_DOCUMENTS = """
UNWIND $rows AS row
MERGE (d:Document {id: row.id, kg_version: $kg_version})
SET d.title = row.title, d.org_id = $org_id, d.trace_id = $trace_id
RETURN count(d) AS merged
"""

_CYPHER_MERGE_CHUNKS = """
UNWIND $rows AS row
MATCH (d:Document {id: row.doc_id, kg_version: $kg_version})
MERGE (c:Chunk {id: row.id, kg_version: $kg_version})
SET c.text = row.text, c.page = row.page,
    c.char_start = row.char_start, c.char_end = row.char_end,
    c.org_id = $org_id, c.trace_id = $trace_id
MERGE (d)-[:HAS_CHUNK]->(c)
RETURN count(c) AS merged
"""

_CYPHER_MERGE_MENTIONS = """
UNWIND $rows AS row
MATCH (c:Chunk {id: row.chunk_id, kg_version: $kg_version})
MATCH (e:Entity {id: row.entity_id, kg_version: $kg_version})
MERGE (c)-[r:MENTIONS {id: row.id, kg_version: $kg_version}]->(e)
SET r.org_id = $org_id, r.trace_id = $trace_id
RETURN count(r) AS merged
"""

#: 本版本**专用**（无 M2 抽取产物混住）⇒ 可以按整个版本清理
_CYPHER_PURGE_VERSION = "MATCH (n {kg_version: $kg_version}) DETACH DELETE n"

_CYPHER_COUNT_ENTITIES_BY_IDS = """
UNWIND $ids AS id
MATCH (n:Entity {id: id, kg_version: $kg_version})
RETURN count(DISTINCT n) AS entity_count
"""

_CYPHER_COUNT_RELATIONS_BY_IDS = """
UNWIND $ids AS id
MATCH ()-[r {id: id, kg_version: $kg_version}]->()
RETURN count(DISTINCT r) AS relation_count
"""

_CYPHER_ROLLBACK_ENTITIES = """
UNWIND $ids AS id
MATCH (n:Entity {id: id, kg_version: $kg_version})
DETACH DELETE n
"""

_CYPHER_ROLLBACK_RELATIONS = """
UNWIND $ids AS id
MATCH ()-[r {id: id, kg_version: $kg_version}]->()
DELETE r
"""

# --- 可用性回读（入图 ≠ 可查）-------------------------------------------
_CYPHER_VERIFY = {
    "subjects": "MATCH (n:Entity:Subject {kg_version: $kg}) RETURN count(n) AS c",
    "invoices": "MATCH (n:Entity:Invoice {kg_version: $kg}) RETURN count(n) AS c",
    "vouchers": "MATCH (n:Entity:Voucher {kg_version: $kg}) RETURN count(n) AS c",
    "issued": (
        "MATCH (:Subject)-[r:ISSUED {kg_version: $kg}]->(:Invoice) RETURN count(r) AS c"
    ),
    "posted_in": (
        "MATCH (:Voucher)-[r:POSTED_IN {kg_version: $kg}]->(:Subject) RETURN count(r) AS c"
    ),
    "chunks": "MATCH (c:Chunk {kg_version: $kg}) RETURN count(c) AS c",
    "mentions": (
        "MATCH (:Chunk)-[r:MENTIONS {kg_version: $kg}]->(:Entity) RETURN count(r) AS c"
    ),
    # ---- §4.6.6 增补（三类算法的输入是否真的落进去了）----
    "addresses": "MATCH (n:Entity:Address {kg_version: $kg}) RETURN count(n) AS c",
    "legal_persons": (
        "MATCH (n:Entity:LegalPerson {kg_version: $kg}) RETURN count(n) AS c"
    ),
    "phones": "MATCH (n:Entity:Phone {kg_version: $kg}) RETURN count(n) AS c",
    "contracts": "MATCH (n:Entity:Contract {kg_version: $kg}) RETURN count(n) AS c",
    "registered_at": (
        "MATCH (:Subject)-[r:REGISTERED_AT {kg_version: $kg}]->(:Address) "
        "RETURN count(r) AS c"
    ),
    "legal_rep": (
        "MATCH (:Subject)-[r:LEGAL_REP {kg_version: $kg}]->(:LegalPerson) "
        "RETURN count(r) AS c"
    ),
    "contact_phone": (
        "MATCH (:Subject)-[r:CONTACT_PHONE {kg_version: $kg}]->(:Phone) "
        "RETURN count(r) AS c"
    ),
    "shares_holder": (
        "MATCH (:Subject)-[r:SHARES_HOLDER {kg_version: $kg}]->(:Subject) "
        "RETURN count(r) AS c"
    ),
    "party_to": (
        "MATCH (:Subject)-[r:PARTY_TO {kg_version: $kg}]->(:Contract) "
        "RETURN count(r) AS c"
    ),
}


def _batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _by_label(rows: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    """``extra_rows`` 按语义标签分派 Cypher（Neo4j 无动态标签 ⇒ 一类一条语句）。"""
    return [row for row in rows if row.get("label") == label]


# --------------------------------------------------------------------------- #
# 写入（ADR-0002 三段式）
# --------------------------------------------------------------------------- #
def import_graph(
    *,
    driver: Any,
    database: str,
    kg_version: str,
    subject_rows: list[dict[str, Any]],
    invoice_rows: list[dict[str, Any]],
    voucher_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
    org_id: str,
    trace_id: str,
    purge: bool,
    now: str,
    evidence: tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]],
    extra_rows: list[dict[str, Any]] | None = None,
) -> None:
    extras = list(extra_rows or [])
    entity_rows = [*subject_rows, *invoice_rows, *voucher_rows, *extras]
    started = time.perf_counter()

    with driver.session(database=database) as session:
        for cypher in _CYPHER_CONSTRAINTS:
            try:
                session.run(cypher).consume()
            except Exception as exc:  # noqa: BLE001 - 约束非阻断
                print(f"  [warn] 约束创建失败（忽略）: {exc}", file=sys.stderr)

        session.run(
            _CYPHER_MERGE_KG_VERSION,
            kg_version=kg_version,
            status="writing",
            scope="domain:affiliation",
            trace_id=trace_id,
            now=now,
        ).consume()
        print(f"  [1/3] KgVersion {kg_version} -> writing")

        if purge:
            session.run(_CYPHER_PURGE_VERSION, kg_version=kg_version).consume()
            print("  [purge] 已清理同版本历史数据（本版本为合成数据专用）")

        try:
            for cypher, rows in (
                (_CYPHER_MERGE_SUBJECTS, subject_rows),
                (_CYPHER_MERGE_INVOICES, invoice_rows),
                (_CYPHER_MERGE_VOUCHERS, voucher_rows),
                (_CYPHER_MERGE_ADDRESS, _by_label(extras, "Address")),
                (_CYPHER_MERGE_LEGAL_PERSON, _by_label(extras, "LegalPerson")),
                (_CYPHER_MERGE_PHONE, _by_label(extras, "Phone")),
                (_CYPHER_MERGE_CONTRACT, _by_label(extras, "Contract")),
            ):
                for batch in _batched(rows, BATCH_SIZE):
                    session.run(
                        cypher,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
            print(
                f"  [2/3] MERGE 主体 {len(subject_rows)} / 发票 {len(invoice_rows)}"
                f" / 凭证 {len(voucher_rows)} / 共享与合同 {len(extras)}"
            )

            def _by_kind(kind: str) -> list[dict[str, Any]]:
                return [row for row in relation_rows if row["kind"] == kind]

            for cypher, rows in (
                (_CYPHER_MERGE_ISSUED, _by_kind("ISSUED")),
                (_CYPHER_MERGE_POSTED_IN, _by_kind("POSTED_IN")),
                (_CYPHER_MERGE_REGISTERED_AT, _by_kind("REGISTERED_AT")),
                (_CYPHER_MERGE_LEGAL_REP, _by_kind("LEGAL_REP")),
                (_CYPHER_MERGE_CONTACT_PHONE, _by_kind("CONTACT_PHONE")),
                (_CYPHER_MERGE_SHARES_HOLDER, _by_kind("SHARES_HOLDER")),
                (_CYPHER_MERGE_PARTY_TO, _by_kind("PARTY_TO")),
            ):
                for batch in _batched(rows, BATCH_SIZE):
                    session.run(
                        cypher,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
            print(f"  [2/3] MERGE 关系 {len(relation_rows)} 条（五类 + 三类增补）")

            # ---- 写入自检：回读**本次提交的 id**，防"静默丢失" ----
            record = session.run(
                _CYPHER_COUNT_ENTITIES_BY_IDS,
                ids=[str(row["id"]) for row in entity_rows],
                kg_version=kg_version,
            ).single()
            actual_entities = int(record["entity_count"]) if record else 0
            record = session.run(
                _CYPHER_COUNT_RELATIONS_BY_IDS,
                ids=[str(row["id"]) for row in relation_rows],
                kg_version=kg_version,
            ).single()
            actual_relations = int(record["relation_count"]) if record else 0
            if actual_entities != len(entity_rows) or actual_relations != len(
                relation_rows
            ):
                raise IngestError(
                    "写入自检失败: 期望 "
                    f"Entity={len(entity_rows)} Relation={len(relation_rows)}，"
                    f"实际 Entity={actual_entities} Relation={actual_relations}"
                )
            print(
                f"  [self-check] 回读 Entity={actual_entities} / Relation={actual_relations}"
            )

            # ---- 2.5/3：证据层 ----
            doc_rows, chunk_rows, mention_rows = evidence
            for cypher, rows in (
                (_CYPHER_MERGE_DOCUMENTS, doc_rows),
                (_CYPHER_MERGE_CHUNKS, chunk_rows),
                (_CYPHER_MERGE_MENTIONS, mention_rows),
            ):
                for batch in _batched(rows, BATCH_SIZE):
                    session.run(
                        cypher,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
            print(
                f"  [evidence] Document {len(doc_rows)} / Chunk {len(chunk_rows)}"
                f" / MENTIONS {len(mention_rows)}"
            )

            session.run(
                _CYPHER_SET_VERSION_STATUS,
                kg_version=kg_version,
                status="active",
                now=now,
                error_code=None,
                error_detail=None,
                entity_count=len(entity_rows),
                relation_count=len(relation_rows),
            ).consume()
            print("  [3/3] KgVersion -> active")

        except Exception as exc:  # noqa: BLE001 - 三段式失败补偿
            detail = f"{type(exc).__name__}: {exc}"[:500]
            print(f"  [3b] 失败，回滚并置 failed: {detail}", file=sys.stderr)
            try:
                session.run(
                    _CYPHER_ROLLBACK_RELATIONS,
                    ids=[str(row["id"]) for row in relation_rows],
                    kg_version=kg_version,
                ).consume()
                session.run(
                    _CYPHER_ROLLBACK_ENTITIES,
                    ids=[str(row["id"]) for row in entity_rows],
                    kg_version=kg_version,
                ).consume()
                session.run(
                    _CYPHER_SET_VERSION_STATUS,
                    kg_version=kg_version,
                    status="failed",
                    now=now,
                    error_code="INGEST_FAILED",
                    error_detail=detail,
                    entity_count=0,
                    relation_count=0,
                ).consume()
            except Exception as cleanup_exc:  # noqa: BLE001
                print(f"  [3b] 补偿本身失败: {cleanup_exc}", file=sys.stderr)
            raise IngestError(detail) from exc

    print(f"  耗时 {int((time.perf_counter() - started) * 1000)} ms")


def verify_graph(session: Any, *, kg_version: str) -> None:
    """回读确认「查得出来」——入图不等于可用。"""
    print("\n----- 可用性回读 -----")
    for name, cypher in _CYPHER_VERIFY.items():
        record = session.run(cypher, kg=kg_version).single()
        print(f"  {name:<10}: {int(record['c']) if record else 0}")


# --------------------------------------------------------------------------- #
# PG：unaligned_subjects（偿还 S7.2-1）+ kg_versions 真源
# --------------------------------------------------------------------------- #
def persist_unaligned(rows: list[dict[str, Any]], *, org_id: uuid.UUID) -> int:
    """把未对齐主体写进 PG ``unaligned_subjects``。

    幂等：先按 ``(org_id, source_doc_id)`` 定向删除**本语料**上次产出的行，
    再插入——重跑不会翻倍（否则对齐率会被历史行污染）。

    ``row["status"]``（缺省 ``pending``）：S9.13 被消解合并掉的行写 ``aligned``——
    它**曾经**未对齐（留痕保留），但终态已并入 canonical 主体 ⇒ 不该继续显示成
    "待处理"。

    **必须一次调用写完全部行**：本函数按 ``doc_id`` 先删后插，分两次调用
    （先写 pending 再写 aligned）会让后一次把前一次刚插的行删掉。
    """
    init_db()
    doc_ids = {row["source_doc_id"] for row in rows}
    # A4：写哪个 org 的语料就绑哪个 org（来自 ``--org-id`` 入参）
    with open_session(org_id=org_id) as db:
        if doc_ids:
            (
                db.query(UnalignedSubject)
                .filter(
                    UnalignedSubject.org_id == org_id,
                    UnalignedSubject.source_doc_id.in_(list(doc_ids)),
                )
                .delete(synchronize_session=False)
            )
            db.commit()
        for row in rows:
            db.add(
                UnalignedSubject(
                    org_id=org_id,
                    raw_name=row["raw_name"],
                    source_doc_id=row["source_doc_id"],
                    reason=row["reason"],
                    candidates=list(row["candidates"]) or None,
                    status=str(row.get("status") or "pending"),
                )
            )
        db.commit()
    return len(rows)


def persist_merge_candidates(
    candidates: list[MergeCandidate], *, org_id: uuid.UUID, trace_id: str
) -> int:
    """把消解候选写进 PG ``entity_merge_candidates``（**偿还 S6.2-2**）。

    幂等：按 ``org_id`` 先删后插——重跑不翻倍，否则三档分布会被历史行污染，
    「误并 0」这种判据也就不再可信。

    只写**判据产生的**行：``< 0.70`` 的候选**根本不落表**（§4.5.1 第 5 条）。
    """
    init_db()
    # A4：写哪个 org 的语料就绑哪个 org（来自 ``--org-id`` 入参）
    with open_session(org_id=org_id) as db:
        (
            db.query(EntityMergeCandidate)
            .filter(EntityMergeCandidate.org_id == org_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        for item in candidates:
            db.add(
                EntityMergeCandidate(
                    org_id=org_id,
                    left_entity_id=item.left_id,
                    right_entity_id=item.right_id,
                    similarity=float(item.similarity),
                    status=item.status,
                    signals=dict(item.signals),
                    trace_id=uuid.UUID(trace_id),
                )
            )
        db.commit()
    return len(candidates)


def register_pg_kg_version(
    *, org_id: uuid.UUID, version: str, entity_count: int, relation_count: int
) -> None:
    """登记 PG ``kg_versions``——**PG 才是 kg_version 的真源**。

    只写 Neo4j 的 ``:KgVersion`` 会导致读侧（``fetch_active_kg_version`` 传 ``db`` 时
    只认 PG 的 ready 行）**查不到**本版本（Sprint 9.5 已栽过一次：
    Neo4j 里躺着 2954 个实体，读侧却返回 ``nodes = 0``）。
    """
    init_db()
    # A4：写哪个 org 的语料就绑哪个 org（来自 ``--org-id`` 入参）
    with open_session(org_id=org_id) as db:
        svc = KgVersioningService(db)
        existing = svc.get_by_version(org_id=org_id, version=version)
        if existing is None:
            existing = svc.create_pending(
                org_id=org_id,
                version=version,
                source_doc_ids=[],
                trace_id=uuid.uuid4(),
            )
            print(f"  [PG] 新建版本行 {version}（pending）")
        else:
            print(f"  [PG] 复用已存在版本行 {version}（status={existing.status}）")
        version_id = uuid.UUID(str(existing.id))
        svc.mark_building(version_id)
        svc.mark_ready(
            version_id, entity_count=entity_count, relation_count=relation_count
        )
    print(f"  [PG] {version} -> ready（实体 {entity_count} / 关系 {relation_count}）")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if (
            stream
            and stream.encoding
            and stream.encoding.lower() not in ("utf-8", "utf8")
        ):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(
        description="M4 四源 CSV 摄入 + 主体对齐（Sprint 9.11 批次 C1）"
    )
    parser.add_argument("--corpus-dir", default=str(CORPUS_DIR))
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument("--org-id", default=str(AFFILIATION_DEMO_ORG_ID))
    parser.add_argument("--dry-run", action="store_true", help="只解析 + 对齐，不写库")
    parser.add_argument(
        "--purge", action="store_true", help="先清理同 kg_version（合成数据专用）"
    )
    args = parser.parse_args(argv)

    corpus = Path(args.corpus_dir).resolve()
    org_id = uuid.UUID(args.org_id)
    kg_version = args.kg_version
    trace_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    print("===== ingest_affiliation_sources =====")
    print(f"语料       : {corpus}")
    print(f"kg_version : {kg_version}")
    print(f"org_id     : {org_id}")

    suppliers = read_csv(corpus / "suppliers.csv")
    invoices = read_csv(corpus / "invoices.csv")
    vouchers = read_csv(corpus / "vouchers.csv")
    # §4.6.6 增补的两张表**允许缺失**（旧语料没有 ⇒ 三类算法无输入，但不报错）
    contracts = _read_optional(corpus / "contracts.csv")
    shareholders = _read_optional(corpus / "shareholders.csv")
    validate_corpus(suppliers, invoices, vouchers, contracts, shareholders)
    print(
        f"语料规模   : 供应商 {len(suppliers)} / 发票 {len(invoices)} / 凭证 {len(vouchers)}"
        f" / 合同 {len(contracts)} / 持股 {len(shareholders)}"
    )

    index = build_master_index(suppliers)
    invoice_matches, voucher_matches, stats = align_sources(invoices, vouchers, index)

    print("\n----- 四源主体对齐（税号 → 名称 → 地址）-----")
    print(
        f"  待对齐 {stats.total} 行：命中 {stats.aligned} / 未对齐 {stats.unaligned}"
        f" ⇒ 成功率 {stats.rate:.4f}（判据 ≥ {MIN_ALIGNMENT_RATE}）"
    )
    print(f"  命中级别 : {stats.by_level}")
    print(f"  未对齐因 : {stats.by_reason}")
    for row in stats.unaligned_rows:
        extra = f" 候选 {row['candidates']}" if row["candidates"] else ""
        print(
            f"    - {row['file']}[{row['key']}] {row['raw_name']} → {row['reason']}{extra}"
        )

    if stats.rate < MIN_ALIGNMENT_RATE:
        print(
            f"[FAIL] 对齐成功率 {stats.rate:.4f} < {MIN_ALIGNMENT_RATE}"
            "——不达标就是**未通过**，不做「调阈值凑数」",
            file=sys.stderr,
        )
        return 1

    # ---- S9.13 批次 C3：实体消解（判据 specs/m2 §4.5.1）----
    candidates, resolved_rows = resolve_unaligned(
        index=index,
        stats=stats,
        invoice_matches=invoice_matches,
        voucher_matches=voucher_matches,
    )
    by_status: dict[str, int] = {}
    for item in candidates:
        by_status[item.status] = by_status.get(item.status, 0) + 1

    print("\n----- 实体消解（S9.13；判据 specs/m2 §4.5.1）-----")
    print(f"  候选 {len(candidates)} 条：{by_status or '（无）'}")
    print(
        f"  终态对齐 : 命中 {stats.aligned}（含消解合并 {len(resolved_rows)}）"
        f" / 未对齐 {stats.unaligned} ⇒ 率 {stats.rate:.4f}"
    )
    for row in resolved_rows:
        print(
            f"    - auto_merged {row['file']}[{row['key']}] {row['raw_name']}"
            f" → {row['merged_into']}"
        )
    for item in candidates:
        if item.status != "auto_merged":
            print(
                f"    - {item.status} {item.left_id} ↔ {item.right_id}"
                f" (sim={item.similarity:.4f}, {item.signals})"
            )
    # **误并 0** 的机械判据：税号不同的两个 canonical 主体**不得**被自动合并
    illegal = [
        item
        for item in candidates
        if item.status == "auto_merged"
        and item.left_id.startswith("SUBJECT:")
        and item.right_id.startswith("SUBJECT:")
    ]
    if illegal:
        print(
            f"[FAIL] N1 失效：{len(illegal)} 条候选把两个税号不同的主体自动合并了",
            file=sys.stderr,
        )
        return 1
    if stats.rate < MIN_ALIGNMENT_RATE:
        print(
            f"[FAIL] 终态对齐成功率 {stats.rate:.4f} < {MIN_ALIGNMENT_RATE}",
            file=sys.stderr,
        )
        return 1

    subject_rows, invoice_rows, voucher_rows, extra_rows, relation_rows = (
        build_graph_rows(
            suppliers,
            invoices,
            vouchers,
            invoice_matches,
            voucher_matches,
            contracts,
            shareholders,
        )
    )
    evidence = build_evidence(suppliers, invoices, vouchers, contracts, shareholders)
    print(
        f"\n规范化结果 : 主体 {len(subject_rows)} / 发票 {len(invoice_rows)}"
        f" / 凭证 {len(voucher_rows)} / 共享与合同 {len(extra_rows)}"
        f" / 关系 {len(relation_rows)}"
    )
    print(
        f"证据层     : Document {len(evidence[0])} / Chunk {len(evidence[1])}"
        f" / MENTIONS {len(evidence[2])}"
    )

    if args.dry_run:
        print("[dry-run] 未连接 Neo4j / 未写 PG，退出。")
        return 0

    settings = get_settings()
    if not settings.neo4j_password:
        print("[FAIL] NEO4J_PASSWORD 未配置，请检查 backend/.env", file=sys.stderr)
        return 1

    from neo4j import GraphDatabase  # type: ignore[import-not-found]

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        driver.verify_connectivity()
        print(f"Neo4j 连接 : {settings.neo4j_uri} (db={settings.neo4j_database})")
        import_graph(
            driver=driver,
            database=settings.neo4j_database,
            kg_version=kg_version,
            subject_rows=subject_rows,
            invoice_rows=invoice_rows,
            voucher_rows=voucher_rows,
            relation_rows=relation_rows,
            org_id=str(org_id),
            trace_id=trace_id,
            purge=args.purge,
            now=now,
            evidence=evidence,
            extra_rows=extra_rows,
        )
        with driver.session(database=settings.neo4j_database) as session:
            verify_graph(session, kg_version=kg_version)
        all_unaligned_rows = [
            *stats.unaligned_rows,
            *({**row, "status": "aligned"} for row in resolved_rows),
        ]
        written = persist_unaligned(all_unaligned_rows, org_id=org_id)
        print(
            f"  [PG] unaligned_subjects 写入 {written} 行（S7.2-1 偿还；"
            f"其中 {len(resolved_rows)} 行经消解合并 ⇒ status=aligned）"
        )
        written_candidates = persist_merge_candidates(
            candidates, org_id=org_id, trace_id=trace_id
        )
        print(
            f"  [PG] entity_merge_candidates 写入 {written_candidates} 行"
            "（S6.2-2 偿还）"
        )
        register_pg_kg_version(
            org_id=org_id,
            version=kg_version,
            entity_count=len(subject_rows)
            + len(invoice_rows)
            + len(voucher_rows)
            + len(extra_rows),
            relation_count=len(relation_rows),
        )
    except Exception as exc:  # noqa: BLE001 - CLI 统一兜底
        print(f"[FAIL] 入图失败: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()

    print("\n===== 完成 =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
