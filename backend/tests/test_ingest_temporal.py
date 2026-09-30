"""Sprint 10.4 批次 A：确定性旁路（CSV）关系的 ``valid_from`` 取值纪律。

这批用例守三条，都与 ADR-0005 R4「不猜值」同源：

1. **取值来自源行自己的日期列**，由 ``mapping.yaml`` 逐关系声明 ⇒ 不是代码推断、
   更不是默认值兜底；认不出格式 ⇒ ``None``；
2. **声明与语料必须对得上**：声明的列在该 CSV 里**真的存在**（拼错列名是最容易
   静默失效的一类改动——解析出的 ``valid_from`` 全是 ``None``，覆盖率归零而无人报错）；
3. **未声明 ⇒ ``None``**，写入用 ``coalesce`` ⇒ 重跑幂等，不清空已有值。
"""

from __future__ import annotations

import csv
import re
from typing import Any

import yaml

from scripts.ingest_attendance_csv import (
    _CYPHER_MERGE_RELATIONS,
    CORPUS_DIR,
    DEFAULT_MAPPING,
    _fact_date,
    build_nodes,
    build_relations,
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: 只读解析（确定性）：演示语料 + 真机 mapping
MAPPING: dict[str, Any] = yaml.safe_load(DEFAULT_MAPPING.read_text(encoding="utf-8"))
_NODE_ROWS, NODE_IDS = build_nodes(MAPPING)
ROWS, UNRESOLVED = build_relations(MAPPING, NODE_IDS)

_BY_TYPE: dict[str, list[dict[str, Any]]] = {}
for _row in ROWS:
    _BY_TYPE.setdefault(str(_row["relation_type"]), []).append(_row)

#: 声明了日期列的关系
DATED_TYPES = (
    "HAS_SHIFT",
    "HAS_ATTENDANCE",
    "ON_BUSINESS_TRIP",
    "HANDLED_ORDER",
    "LOCATED_AT",
    "SWIPED_AT",
    "SUBMITTED_LEAVE",
    "ACCUMULATED_OVERTIME",
    "TRIP_FOR_ORDER",
    "OCCURRED_ON",
)


# --------------------------------------------------------------------------- #
# 取值：只认源行明写的日期
# --------------------------------------------------------------------------- #
def test_datetime_column_is_normalized_to_date() -> None:
    """``dispatched_at`` = ``2026-10-16 09:40`` ⇒ 取 ``2026-10-16``。"""
    spec = {"valid_from_column": "dispatched_at"}
    assert _fact_date({"dispatched_at": "2026-10-16 09:40"}, spec) == "2026-10-16"


def test_plain_date_column_is_kept() -> None:
    assert _fact_date({"date": "2026-10-01"}, {"valid_from_column": "date"}) == (
        "2026-10-01"
    )


def test_no_column_declared_means_none() -> None:
    """未声明 ⇒ None：**不拿"今天"、不拿文件修改时间兜底**（R4）。"""
    assert _fact_date({"date": "2026-10-01"}, {}) is None


def test_missing_or_blank_value_is_none() -> None:
    spec = {"valid_from_column": "date"}
    assert _fact_date({"other": "2026-10-01"}, spec) is None
    assert _fact_date({"date": "  "}, spec) is None


def test_unrecognized_format_is_none_not_coerced() -> None:
    """``2026/10/01`` 认不出 ⇒ None，**不改写**成 ISO（与 document_date 同纪律）。"""
    assert _fact_date({"date": "2026/10/01"}, {"valid_from_column": "date"}) is None


# --------------------------------------------------------------------------- #
# 声明与语料一致性（防止拼错列名 ⇒ 静默归零）
# --------------------------------------------------------------------------- #
def test_declared_columns_exist_in_corpus() -> None:
    offenders: list[str] = []
    for spec in MAPPING["relationships"]:
        column = spec.get("valid_from_column")
        if not column:
            continue
        file_name = str(spec["from"]["file"])
        if spec.get("valid_from_from") == "tail":
            file_name = str(spec["to"]["file"])
        with (CORPUS_DIR / file_name).open(encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh))
        if str(column) not in header:
            offenders.append(f"{spec['relation_type']}: {file_name} 缺少列 {column}")

    assert offenders == []


# --------------------------------------------------------------------------- #
# 端到端：真机演示语料上的覆盖（¥0 可复算）
# --------------------------------------------------------------------------- #
def test_dated_relations_carry_iso_valid_from() -> None:
    """声明了日期列的关系 ⇒ 每行都拿到 YYYY-MM-DD。"""
    assert ROWS, "演示语料解析出 0 条关系——入图前置条件都不成立"

    for rtype in DATED_TYPES:
        rows = _BY_TYPE.get(rtype) or []
        if not rows:
            continue  # 该关系本批未产出（如 TRIP_FOR_ORDER 依赖日期窗口命中）
        bad = [r["id"] for r in rows if not _ISO_DATE.match(str(r["valid_from"] or ""))]
        assert bad == [], f"{rtype} 有 {len(bad)} 行没拿到合法日期，例：{bad[:3]}"


def test_undeclared_relations_stay_none() -> None:
    """employees.csv 派生的三条关系没有"从哪天成立"的源列 ⇒ 逐行 None，不推断。"""
    for rtype in ("BELONGS_TO", "HAS_POSITION", "APPLIES_WORK_TIME"):
        rows = _BY_TYPE.get(rtype) or []
        assert rows, f"{rtype} 应存在但没有产出"
        assert all(r["valid_from"] is None for r in rows)


def test_write_is_idempotent_by_coalesce() -> None:
    """写入用 coalesce：重跑不清空已有值——否则每次重建都会把时序数据洗掉一次。"""
    assert "r.valid_from = coalesce(r.valid_from, row.valid_from)" in (
        _CYPHER_MERGE_RELATIONS
    )


def test_no_reserved_ingest_dimension_is_written() -> None:
    """CSV 里没有任何"这条记录何时失效"的字段 ⇒ **不写** valid_to / expired_at。"""
    assert "valid_to" not in _CYPHER_MERGE_RELATIONS
    assert "expired_at" not in _CYPHER_MERGE_RELATIONS
