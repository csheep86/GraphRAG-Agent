"""考勤域 CSV → Neo4j 入图器（Sprint 9.5 批次 B1）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/ingest_attendance_csv.py
    uv run python scripts/ingest_attendance_csv.py --kg-version attendance-demo-v1
    uv run python scripts/ingest_attendance_csv.py --dry-run   # 只解析，不写库
    uv run python scripts/ingest_attendance_csv.py --purge-csv # 只清 CSV 派生节点（**推荐**）
    uv run python scripts/ingest_attendance_csv.py --purge     # 清整个版本（含 M2 抽取产物）

设计要点：

1. **确定性映射，不经过 LLM**——结构化数据用 LLM 抽取是错配；
   映射规则全部来自 ``demo/attendance/mapping.yaml``。
2. **沿用真机图谱模型**（与 ``kg/builder.py`` 逐字一致）：
   节点统一 ``:Entity`` + ``entity_type`` 属性，关系统一 ``:RELATION``
   + ``relation_type`` 属性。**不**用多标签——那会导致数据进得了库、
   却查不出来、前端渲染不出（``graphs.py`` 全部查询只读 ``:Entity``）。
3. **ADR-0002 三段式写入**：``:KgVersion`` 落 ``writing`` → MERGE 数据
   → 置 ``active``；失败则清理并置 ``failed``。
   幂等键 ``(id, kg_version)``，重复执行安全可重放。
4. **写入自检**：回读真实计数，与期望不符即失败回滚——防止"静默丢失"
   （例如端点 id 拼错导致关系全部匹配不到）。

**清理范围（2026-09-28 修）**：本脚本与 ``ingest_attendance_policies.py``（M2 抽取）
共用同一 ``kg_version``，后者产物为 ``ent_*`` span 实体。因此——

- 自检与失败补偿**只针对本次提交的 id**，不按整个版本计数 / 删除：
  否则 span 会被算进实际计数（恒报自检失败），失败补偿还会**连带删掉** span
  （重跑抽取要重烧 MinerU + LLM）；
- ``--purge-csv`` 只清本 mapping 派生前缀（``<ENTITY_TYPE>:``），``--purge`` 清整个版本。

**知识时效（2026-09-30 Sprint 10.4 批次 A 追加，ADR-0005 §4）**：
关系写入 ``valid_from``，取值 = ``mapping.yaml`` 里该关系声明的 ``valid_from_column``
（源行自带的日期列：排班 ``date``、请假 ``start_date``、工单 ``dispatched_at`` …）。
三点纪律：

1. **只写事实维的 ``valid_from``**，不写 ``valid_to`` / ``expired_at``——CSV 里
   **没有**任何"这条记录何时失效"的字段，写它们就得编；缺失 ⇒ 该属性不存在，
   读侧 ``_temporal_view`` 的谓词对此恒真，语义正是"未纳入失效治理"；
2. **列未声明 / 取不到 ⇒ None**：不做默认值兜底（R4 不猜值）；
3. 这是演示语料里**唯一真实存在**的时间源：确定性旁路、零 LLM、可复算——
   比"事后给语料补一个假日期"可靠得多。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# **为什么两个目录都要塞**：以脚本方式跑（``python scripts/x.py``）时，解释器
# 会把 ``scripts/`` 自动放到 ``sys.path[0]``，故同目录模块可以直接 import；
# 但被 pytest 以 ``scripts.x`` 包路径导入时，``sys.path[0]`` 是 repo 根，
# ``scripts/`` **不在**其中 ⇒ ``_bridge_window`` 解析失败（2026-09-30 实测：
# ``tests/test_ingest_temporal.py`` 收集期就 ModuleNotFoundError，CI 必红）。
# 显式补上 ⇒ 两种运行方式同解，不再依赖"脚本被怎么调用"。
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import yaml  # noqa: E402

# 派生边窗口继承（ADR-0005 §4 增补）：两处 Rule-generated 桥接边共用同一份口径，
# 避免「同形状的边一边有日期一边没有」。见 changes/P6-U/11-derived-window-inheritance.md
from _bridge_window import (  # noqa: E402
    DEFAULT_SCOPE_STORE,
    apply_clause_window,
    clause_windows,
    load_document_scopes,
)

from app.core.config import get_settings  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.kg.versioning import KgVersioningService  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
CORPUS_DIR = REPO_ROOT / "demo" / "attendance" / "corpus"
DEFAULT_MAPPING = REPO_ROOT / "demo" / "attendance" / "mapping.yaml"
DEFAULT_KG_VERSION = "attendance-demo-v1"

#: UNWIND 分批大小
BATCH_SIZE = 800


class IngestError(Exception):
    """入图流程的业务错误。"""


@dataclass
class IngestStats:
    kg_version: str = ""
    entity_count: int = 0
    relation_count: int = 0
    entity_types: dict[str, int] = field(default_factory=dict)
    relation_types: dict[str, int] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    version_status: str = "unknown"


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def load_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "nodes" not in data:
        raise IngestError(f"映射文件格式错误: {path}")
    return data


def _derived_prefixes(mapping: dict[str, Any]) -> tuple[str, ...]:
    """本 mapping 会产生的实体类型 ⇒ CSV 派生节点的 **id 前缀**集合。

    id 规则见 ``mapping.yaml`` 注释：``<ENTITY_TYPE>:<业务主键值>``。
    定向清理据此区分「CSV 派生」与「M2 抽取的 span（``ent_*``）」。
    """
    return tuple(sorted({str(node["entity_type"]) for node in mapping["nodes"]}))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise IngestError(f"CSV 不存在: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _coerce(value: str) -> Any:
    """CSV 全字符串：数字字段转成数值，便于规则引擎直接算（C1 依赖）。"""
    text = value.strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _canonical_name(
    entity_type: str,
    row: dict[str, str],
    node_id: str,
    *,
    key_value: str | None = None,
) -> str:
    """给节点一个可视化用的名字（前端按 ``canonical_name`` 渲染）。

    **派生节点的名字必须来自自己的键列**（2026-09-27 修正）：``DEPARTMENT`` /
    ``POSITION`` / ``WORK_TIME_SYSTEM`` 由 ``employees.csv`` 去重派生，而该表本身就
    有 ``name`` 列（员工姓名）⇒ 原先会拿**第一个员工的名字**当部门 / 岗位 / 工时制
    的名字（图上会出现「张伟」既是员工、又是部门）。优先级因此改为：
    ``key_value``（派生节点的键列） > ``name`` 列 > 类型模板 > ``node_id``。
    """
    if key_value:
        return key_value
    if row.get("name"):
        return str(row["name"])
    templates = {
        "SHIFT": lambda r: f"{r.get('date', '')} {r.get('shift_type', '')}",
        "ATTENDANCE_RECORD": lambda r: f"{r.get('date', '')} {r.get('status', '')}",
        "BUSINESS_TRIP": lambda r: (
            f"{r.get('destination', '')} {r.get('start_date', '')}"
            f"~{r.get('end_date', '')}"
        ),
        "WORK_ORDER": lambda r: f"{r.get('order_id', '')} {r.get('customer', '')}",
        "LOCATION_RECORD": lambda r: (
            f"{r.get('date', '')} {r.get('time', '')} {r.get('site', '')}"
        ),
        "ACCESS_RECORD": lambda r: f"{r.get('date', '')} {r.get('gate', '')}",
        "LEAVE": lambda r: f"{r.get('leave_type', '')} {r.get('start_date', '')}",
        "OVERTIME": lambda r: f"{r.get('date', '')} {r.get('hours', '')}h",
    }
    build = templates.get(entity_type)
    return build(row) if build else node_id


# --------------------------------------------------------------------------- #
# 构建节点
# --------------------------------------------------------------------------- #
def build_nodes(mapping: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    """按 mapping 生成节点行。

    :returns: ``(rows, node_ids)``
    """
    rows: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for spec in mapping["nodes"]:
        etype = str(spec["entity_type"])
        file_name = str(spec["file"])
        key = str(spec["id_from"])
        props = list(spec.get("properties") or [])
        source = read_csv(CORPUS_DIR / file_name)

        seen: set[str] = set()
        for raw in source:
            value = str(raw.get(key) or "").strip()
            if not value:
                continue
            node_id = f"{etype}:{value}"
            if node_id in seen:
                continue  # derive: distinct 去重
            seen.add(node_id)

            attributes = {p: _coerce(raw.get(p, "")) for p in props if p in raw}
            attributes = {k: v for k, v in attributes.items() if v is not None}

            # derive: distinct ⇒ 名字取自己的键列值（否则会被表的 name 列污染）
            rows.append(
                {
                    "id": node_id,
                    "entity_type": etype,
                    "canonical_name": _canonical_name(
                        etype,
                        raw,
                        node_id,
                        key_value=value if spec.get("derive") == "distinct" else None,
                    ),
                    "props": attributes,
                }
            )
            node_ids.add(node_id)

    return rows, node_ids


# --------------------------------------------------------------------------- #
# 构建关系
# --------------------------------------------------------------------------- #
#: ``YYYY-MM-DD``（可选跟随 `` HH:MM``——``dispatched_at`` 就是这种）
_DATE_VALUE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[\sT].*)?$")


def _fact_date(row: Mapping[str, str], spec: Mapping[str, Any]) -> str | None:
    """取本行自身的事实日期；取不到就 ``None``（R4 不猜值）。

    ``valid_from`` 的取值口径：**源记录里明写的那一天**（排班的 ``date``、考勤的
    ``date``、请假的 ``start_date``、工单的 ``dispatched_at``…），由 ``mapping.yaml``
    的 ``valid_from_column`` 逐关系声明 ⇒ **不是代码猜的**，也不是默认值补齐。
    列不存在 / 值为空 ⇒ ``None``（该关系未纳入时效判定，读侧谓词对恒真）。
    """
    column = spec.get("valid_from_column")
    if not column:
        return None
    value = str(row.get(str(column)) or "").strip()
    if not value:
        return None
    matched = _DATE_VALUE.match(value)
    # 认不出就 None——不改写、不"就近修正"（同一条纪律：编日期比没日期危险）
    return matched.group(1) if matched else None


def _index_rows(
    file_name: str, keys: list[str]
) -> dict[tuple[str, ...], list[dict[str, str]]]:
    """按指定列组合建立索引，供 ``match.by`` 跨表匹配。"""
    index: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in read_csv(CORPUS_DIR / file_name):
        k = tuple(str(row.get(c) or "").strip() for c in keys)
        index.setdefault(k, []).append(row)
    return index


def _in_date_window(closed_at: str, start: str, end: str) -> bool:
    date_part = str(closed_at).strip()[:10]
    return bool(date_part) and start <= date_part <= end


def build_relations(
    mapping: dict[str, Any], node_ids: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """按 mapping 生成关系行。

    :returns: ``(rows, unresolved)``
    """
    rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for spec in mapping["relationships"]:
        rtype = str(spec["relation_type"])
        head_spec, tail_spec = spec["from"], spec["to"]
        head_file, tail_file = str(head_spec["file"]), str(tail_spec["file"])
        head_etype, tail_etype = (
            str(head_spec["entity_type"]),
            str(tail_spec["entity_type"]),
        )
        head_key, tail_key = str(head_spec["key"]), str(tail_spec["key"])

        # -- 模式 A：同一张表内，按行的两列直接连（如 EMPLOYEE.department）----
        if head_file == tail_file and "match" not in spec:
            for raw in read_csv(CORPUS_DIR / head_file):
                hv = str(raw.get(head_key) or "").strip()
                tv = str(raw.get(tail_key) or "").strip()
                if not hv or not tv:
                    continue
                head_id, tail_id = f"{head_etype}:{hv}", f"{tail_etype}:{tv}"
                if head_id not in node_ids or tail_id not in node_ids:
                    unresolved.append(f"{rtype}: {head_id} -> {tail_id}")
                    continue
                key = (rtype, head_id, tail_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "id": f"{rtype}:{head_id}->{tail_id}",
                        "relation_type": rtype,
                        "head": head_id,
                        "tail": tail_id,
                        "valid_from": _fact_date(raw, spec),
                    }
                )
            continue

        # -- 模式 B：跨表，按 match.by 匹配 -------------------------------
        match = spec.get("match") or {}
        by = list(match.get("by") or [])
        if not by:
            unresolved.append(f"{rtype}: 缺少 match.by，跳过")
            continue

        tail_index = _index_rows(tail_file, by)
        for raw in read_csv(CORPUS_DIR / head_file):
            hv = str(raw.get(head_key) or "").strip()
            if not hv:
                continue
            head_id = f"{head_etype}:{hv}"
            if head_id not in node_ids:
                continue
            k = tuple(str(raw.get(c) or "").strip() for c in by)
            for cand in tail_index.get(k, []):
                tv = str(cand.get(tail_key) or "").strip()
                if not tv:
                    continue
                tail_id = f"{tail_etype}:{tv}"
                if tail_id not in node_ids:
                    continue
                # 日期窗口过滤（TRIP_FOR_ORDER：工单须落在出差期间）
                if rtype == "TRIP_FOR_ORDER" and not _in_date_window(
                    str(cand.get("closed_at") or ""),
                    str(raw.get("start_date") or ""),
                    str(raw.get("end_date") or ""),
                ):
                    continue
                key = (rtype, head_id, tail_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "id": f"{rtype}:{head_id}->{tail_id}",
                        "relation_type": rtype,
                        "head": head_id,
                        "tail": tail_id,
                        # 跨表关系的事实落在哪一侧由 mapping 声明（``valid_from_from``）；
                        # 缺省取 head 行。TRIP_FOR_ORDER 取 tail（工单）侧的派单日。
                        "valid_from": _fact_date(
                            cand if spec.get("valid_from_from") == "tail" else raw,
                            spec,
                        ),
                    }
                )

    return rows, unresolved


# --------------------------------------------------------------------------- #
# Cypher（与 kg/builder.py 同款：:Entity + :RELATION）
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

_CYPHER_MERGE_ENTITIES = """
UNWIND $rows AS row
MERGE (n:Entity {id: row.id, kg_version: $kg_version})
SET n.canonical_name = row.canonical_name,
    n.entity_type = row.entity_type,
    n.org_id = $org_id,
    n.trace_id = $trace_id
WITH n, row
SET n += row.props
RETURN count(n) AS merged
"""

_CYPHER_MERGE_RELATIONS = """
UNWIND $rows AS row
MATCH (a:Entity {id: row.head, kg_version: $kg_version})
MATCH (b:Entity {id: row.tail, kg_version: $kg_version})
MERGE (a)-[r:RELATION {id: row.id, kg_version: $kg_version}]->(b)
SET r.relation_type = row.relation_type,
    r.valid_from = coalesce(r.valid_from, row.valid_from),
    // valid_to 同理：桥接边按 ADR-0005 §4 增补继承所指条款的窗口；
    // 普通 CSV 事实边的 row.valid_to 恒为 null ⇒ 不为它们凭空补值。
    r.valid_to = coalesce(r.valid_to, row.valid_to),
    r.org_id = $org_id,
    r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_PURGE_VERSION = "MATCH (n:Entity {kg_version: $kg_version}) DETACH DELETE n"

#: **定向清理**：只删本 mapping 派生的节点（id 形如 ``<ENTITY_TYPE>:<主键>``）。
#:
#: 为什么不能只用 ``--purge``：同一 ``kg_version`` 里还混着 **M2 抽取的 span 实体**
#: （``ent_*``，如 ``POLICY_CLAUSE``——规则值解析的图谱侧来源）。``--purge`` 按
#: ``:Entity{kg_version}`` 全删，**会连带删掉 210 个 span**，重建需要重跑 MinerU + LLM。
#: 只改 CSV 语料时，用 ``--purge-csv`` 清派生节点、保住抽取产物。
_CYPHER_PURGE_CSV = """
MATCH (n:Entity {kg_version: $kg_version})
WHERE split(n.id, ':')[0] IN $prefixes
DETACH DELETE n
"""

_CYPHER_COUNT_VERSION_GRAPH = """
MATCH (n:Entity {kg_version: $kg_version})
WITH count(n) AS entity_count
MATCH ()-[r:RELATION {kg_version: $kg_version}]->()
RETURN entity_count AS entity_count, count(r) AS relation_count
"""

#: 写入自检按**本次提交的 id** 计数，而不是按整个 ``kg_version``：
#: 同一版本里还混着 M2 抽取的 span 实体（``ent_*``）——按版本计数会把它们算进来，
#: 在「CSV 与抽取结果同版本共存」的场景下**必然**误报「写入自检失败」。
_CYPHER_COUNT_ENTITIES_BY_IDS = """
UNWIND $ids AS id
MATCH (n:Entity {id: id, kg_version: $kg_version})
RETURN count(DISTINCT n) AS entity_count
"""

_CYPHER_COUNT_RELATIONS_BY_IDS = """
UNWIND $ids AS id
MATCH ()-[r:RELATION {id: id, kg_version: $kg_version}]->()
RETURN count(DISTINCT r) AS relation_count
"""

#: 失败补偿同样**只删本次写入**的行。
#:
#: 原实现按 ``:Entity{kg_version}`` 全删——而同版本还住着 M2 抽取的 span 实体，
#: 一次自检失败就会把它们**连带清空**（重跑 B2 要重烧 MinerU + LLM）。
#: 补偿的正确语义是"撤销我这次写的东西"，不是"清空这个版本"。
_CYPHER_ROLLBACK_ENTITIES = """
UNWIND $ids AS id
MATCH (n:Entity {id: id, kg_version: $kg_version})
DETACH DELETE n
"""

_CYPHER_ROLLBACK_RELATIONS = """
UNWIND $ids AS id
MATCH ()-[r:RELATION {id: id, kg_version: $kg_version}]->()
DELETE r
"""

# --------------------------------------------------------------------------- #
# B3 汇合：WORK_TIME_SYSTEM -GOVERNED_BY-> POLICY_CLAUSE（R10 / Sprint 9.6 G1）
# --------------------------------------------------------------------------- #
#:
#: mapping.yaml 尾部**预留的 B3 设计**在此落地：CSV 派生的工时制节点连到
#: M2 抽取的条款节点，让「员工 → 岗位 → 工时制 → 条款」3 跳可达
#: （``reasoning.py`` 的 ``*1..3`` 变长遍历即可把推理链落到条款）。
#:
#: **三条纪律**（由 2026-09-28 真机探针钉死，见 ``changes/Sprint9.6/proposal.md`` §1）：
#:
#: 1. 只连 **CSV 派生**的 ``WORK_TIME_SYSTEM:<名>``（id 前缀圈定）——
#:    M2 span 里同名类型有 17 个噪声节点（「系统」「核心在岗时段」…），一律不参与；
#: 2. 匹配文本源是**条款的 MENTIONS chunk 文本**——条款 ``canonical_name``
#:    多为碎片（「第七条」「2026 年 1 月 1 日」），按属性匹配必失败，
#:    完整句子只在 chunk 里；CSV 证据 chunk（R14）只 MENTIONS 到 EMPLOYEE，
#:    被该模式天然排除；
#: 3. 纯 Python 包含匹配，**不经 LLM**；产出的边**并入 relation_rows**
#:    ⇒ 复用写入自检与失败回滚，不另起写入通道。


def fetch_policy_context(session: Any, *, kg_version: str) -> list[dict[str, Any]]:
    """读「条款 + 其 MENTIONS chunk 文本」作为匹配语料。

    按 ``id`` 升序 ⇒ 同库多次调用**同解**（确定性纪律）。
    """
    rows = list(
        session.run(
            "MATCH (p:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg}) "
            "OPTIONAL MATCH (c:Chunk {kg_version: $kg})-[:MENTIONS]->(p) "
            "WITH p, reduce(t = '', x IN collect(c.text) | t + coalesce(x, '')) AS text "
            "RETURN p.id AS id, p.canonical_name AS name, text "
            "ORDER BY p.id",
            kg=kg_version,
        )
    )
    return [
        {"id": str(row["id"]), "name": row["name"] or "", "text": row["text"] or ""}
        for row in rows
    ]


def build_governed_by_relations(
    wts_rows: list[dict[str, Any]],
    policy_context: list[dict[str, Any]],
    windows: Mapping[str, tuple[str | None, str | None]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """把工时制节点连到正文含其名称的条款。

    :param wts_rows: **CSV 派生**的工时制实体行（来自 ``build_nodes``，
        id 形如 ``WORK_TIME_SYSTEM:<名>``）。
    :param policy_context: :func:`fetch_policy_context` 的产物。
    :param windows: 条款窗口表（:func:`_bridge_window.clause_windows`）。本边是
        **派生边**：它的有效期定义上等于所指条款的有效期 ⇒ 继承条款窗口。
        条款窗口不唯一或缺失 ⇒ 不写（``None``）。传 ``None`` 表示不继承（旧行为）。
    :returns: ``(relation_rows, misses)``——``misses`` 是未命中任何条款的
        工时制名，调用方必须让它**可见**（连通失败不得静默）。
    """
    rows: list[dict[str, Any]] = []
    misses: list[str] = []
    seen: set[tuple[str, str]] = set()

    for wts in sorted(wts_rows, key=lambda r: str(r["id"])):
        wts_id = str(wts["id"])
        # 纪律 1 的防御断言：span 噪声（ent_*）绝不允许出现在边端点
        if not wts_id.startswith("WORK_TIME_SYSTEM:"):
            misses.append(f"[skipped-non-csv] {wts_id}")
            continue
        name = str(wts.get("canonical_name") or "").strip()
        if not name:
            misses.append(f"[skipped-empty-name] {wts_id}")
            continue
        hit = 0
        for ctx in policy_context:  # 已按 id 升序 ⇒ 边行顺序确定
            clause_id = str(ctx["id"])
            if not ctx["text"] or name not in ctx["text"]:
                continue
            key = (wts_id, clause_id)
            if key in seen:
                continue
            seen.add(key)
            hit += 1
            row = {
                "id": f"GOVERNED_BY:{wts_id}->{clause_id}",
                "relation_type": "GOVERNED_BY",
                "head": wts_id,
                "tail": clause_id,
            }
            # 派生边继承所指条款的窗口（ADR-0005 §4 增补）。窗口缺失/多义时
            # apply_clause_window 原样返回 ⇒ 边保持无日期，绝不补值。
            rows.append(
                apply_clause_window(row, windows=windows or {}, tail_id=clause_id)
            )
        if hit == 0:
            misses.append(name)

    return rows, misses


# --------------------------------------------------------------------------- #
# 证据层：结构化事实 → :Document + :Chunk + MENTIONS（R14，2026-09-28）
# --------------------------------------------------------------------------- #
#:
# **为什么要有这一段**：CSV 派生的事实节点此前**没有任何证据边**——实测
# ``EMPLOYEE:E002`` 的 ``MENTIONS`` 入边为 0，22 个 ``OVERTIME:`` 节点带 chunk 边的
# 也是 0（全图仅 33 个 ``:Chunk``，只覆盖制度文档）。于是 M3 守 F3
# 「无溯源即拒答」在考勤域**恒为真**：真机问答 100% 拒答
# （``refused=true / citations=0``），政策问答页演示时只会显示"无法回答"。
#
# 修法（三选一中的①，取舍见 ``docs/dev-doc-status.md`` **R14**）：
# 把 **CSV 原文本身**当作可引用材料——每张表落一个 ``:Document``，
# 按员工切 ``:Chunk``（chunk 文本 = 该员工在该表里的**原始行**），
# 再建 ``(:Chunk)-[:MENTIONS]->(:Entity)``。要点：
#
# - 引用指向**真实原文**（CSV 行），不是模型生成、也不是我们编的措辞；
# - 契约**不动**：``Citation.doc_id`` 仍是合法 UUID（指向该表文档），
#   前端抽屉高亮复用现成链路（``_QUERY_EVIDENCE_CHUNKS_BY_ENTITIES``）；
# - 未来接第三方（EHR 等）时，同步结果同样**物化为快照**即可复用这一段，
#   所以它不是只为演示打的补丁。
#
# **MENTIONS 只连 ``EMPLOYEE``**：语义上 chunk 也"提到"了具体的 SHIFT / OVERTIME
# 节点，但连全部会让边数翻约 20 倍（每员工每表约 20 行），并**加剧 R12**
# （子图采样挤掉锚点）。引用命中路径由员工锚点保证：锚点 ``EMPLOYEE:E002``
# ⇒ 反查到该员工在各表中的 chunk ⇒ 答案可引回原始行。

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

#: 重跑幂等：先删**本脚本产出**的文档及其 chunk（按 doc_id 定向，
#: 不动 M2 抽取产物——与 ``_CYPHER_PURGE_CSV`` 同一条纪律）。
_CYPHER_PURGE_EVIDENCE = """
UNWIND $doc_ids AS doc_id
MATCH (d:Document {id: doc_id, kg_version: $kg_version})
OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk {kg_version: $kg_version})
DETACH DELETE c, d
"""

#: B3 汇合边的**链路验收**（G2）：李静 3 跳可达条款——
#: 「员工 → 岗位 → 工时制 → 条款」是 R10 的目标链。
_CYPHER_CASE_LI_CLAUSE = """
MATCH (:Entity {id: 'EMPLOYEE:E002', kg_version: $kg_version})
      -[:RELATION {relation_type: 'HAS_POSITION'}]->(:Entity {entity_type: 'POSITION'})
      -[:RELATION {relation_type: 'APPLIES_WORK_TIME'}]->(:Entity {entity_type: 'WORK_TIME_SYSTEM'})
      -[:RELATION {relation_type: 'GOVERNED_BY'}]->(p:Entity {entity_type: 'POLICY_CLAUSE'})
RETURN count(p) AS clauses, collect(p.canonical_name)[..3] AS names
"""


def _evidence_doc_id(file_name: str) -> str:
    """CSV → ``:Document`` id（``uuid5`` ⇒ 同一张表永远同一个 id，重跑幂等）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"graphrag/attendance/csv/{file_name}"))


def _evidence_chunk_id(file_name: str, employee_id: str) -> str:
    """一行组 → ``:Chunk`` id。

    **形态必须与 M2 抽取产物一致：``chunk-<12 hex>``**（2026-09-28 真机事故）。
    初版用了可读的 ``chunk:attendance:<表>:<员工>``（冒号），结果——
    ``app/services/agents.py::_CITATION_ID_PATTERN`` 只认 ``chunk-[0-9A-Za-z]``，
    抠不出 id ⇒ 引用**全部被丢弃** ⇒ 问答以 ``no_grounded_evidence`` 拒答。
    症状极具迷惑性：证据明明注入了 15 个 chunk（日志可查），答案却说
    「资料中没有…信息」——像是模型不懂，实则是 id 形态不合规。
    可读性由 ``text`` 与 ``title`` 承载，不靠 id 字面。
    """
    seed = uuid.uuid5(
        uuid.NAMESPACE_URL, f"graphrag/attendance/chunk/{file_name}/{employee_id}"
    )
    return f"chunk-{seed.hex[:12]}"


def build_evidence(
    mapping: dict[str, Any], node_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """把 CSV **原文行**落为可引用证据（R14）。

    :returns: ``(doc_rows, chunk_rows, mention_rows)``
    """
    doc_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    mention_rows: list[dict[str, Any]] = []

    for spec in mapping["nodes"]:
        if spec.get("derive") == "distinct":
            # 部门 / 岗位 / 工时制由 employees.csv 的列值派生，**没有自己的行原文**
            continue
        file_name = str(spec["file"])
        rows = read_csv(CORPUS_DIR / file_name)
        if not rows:
            continue

        header = ",".join(str(key) for key in rows[0].keys())
        lines = [header] + [
            ",".join(str(value) for value in row.values()) for row in rows
        ]
        full_text = "\n".join(lines)

        doc_id = _evidence_doc_id(file_name)
        doc_rows.append({"id": doc_id, "title": file_name})

        # 按员工分组：一个员工在这张表里的全部原始行 = 一个 chunk
        grouped: dict[str, list[str]] = {}
        for index, raw in enumerate(rows, start=1):
            employee_id = str(raw.get("employee_id") or "").strip()
            grouped.setdefault(employee_id or "_ALL", []).append(lines[index])

        for employee_id, chunk_lines in sorted(grouped.items()):
            text = "\n".join(chunk_lines)
            # char 偏移按**整表文本**定位（行文本含主键，故 find 唯一）；
            # 取不到就退化为 0，绝不伪造一个"看起来对"的偏移。
            char_start = max(full_text.find(chunk_lines[0]), 0)
            chunk_id = _evidence_chunk_id(file_name, employee_id)
            chunk_rows.append(
                {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "text": text,
                    "char_start": char_start,
                    "char_end": char_start + len(text),
                    "page": None,  # CSV 无页码 ⇒ null（沿用「严禁伪造」纪律）
                }
            )
            target = f"EMPLOYEE:{employee_id}"
            if employee_id != "_ALL" and target in node_ids:
                mention_rows.append(
                    {
                        "id": f"{chunk_id}:mentions:{target}",
                        "chunk_id": chunk_id,
                        "entity_id": target,
                    }
                )

    return doc_rows, chunk_rows, mention_rows


def _batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# --------------------------------------------------------------------------- #
# 演示用例可用性验证（入图 ≠ 可用：必须证明查得出来）
# --------------------------------------------------------------------------- #
_CYPHER_CASE_ZHANG = """
MATCH (e:Entity {id: 'EMPLOYEE:E001', kg_version: $kg_version})-[r:RELATION]->(t)
RETURN r.relation_type AS rt, t.entity_type AS et, count(*) AS c ORDER BY c DESC
"""

_CYPHER_CASE_ZHANG_GATE = """
MATCH (e:Entity {id: 'EMPLOYEE:E001', kg_version: $kg_version})
      -[:RELATION {relation_type: 'SWIPED_AT'}]->(a:Entity {entity_type: 'ACCESS_RECORD'})
WHERE a.date IN ['2026-10-15', '2026-10-16']
RETURN a.date AS d, count(a) AS c ORDER BY d
"""

_CYPHER_CASE_LI = """
MATCH (e:Entity {id: 'EMPLOYEE:E002', kg_version: $kg_version})
      -[:RELATION {relation_type: 'HAS_SHIFT'}]->(s:Entity {entity_type: 'SHIFT'})
RETURN count(s) AS shifts, sum(s.planned_hours) AS total_hours
"""

_CYPHER_CASE_WANG = """
MATCH (e:Entity {id: 'EMPLOYEE:E003', kg_version: $kg_version})
      -[:RELATION {relation_type: 'HAS_ATTENDANCE'}]->(a)
WHERE a.core_hours_present < 6.0
RETURN count(a) AS core_absent
"""

_CYPHER_CASE_CHEN = """
MATCH (e:Entity {id: 'EMPLOYEE:E004', kg_version: $kg_version})
      -[:RELATION {relation_type: 'ACCUMULATED_OVERTIME'}]->(o)
RETURN sum(o.hours) AS ot_hours, sum(o.comp_off_used_hours) AS used_hours
"""

_CYPHER_CASE_CROSS_DOMAIN = """
MATCH (t:Entity {entity_type: 'BUSINESS_TRIP', kg_version: $kg_version})
      -[r:RELATION {relation_type: 'TRIP_FOR_ORDER'}]->(w:Entity {entity_type: 'WORK_ORDER'})
RETURN count(r) AS cross_edges
"""


def verify_cases(session: Any, *, kg_version: str) -> None:
    """回读四个演示用例，确认数据在图里**查得出来**。

    只入图不验证，等于埋雷：节点写进去了，但端点 id 拼错 / 属性名写错，
    照样查不出结果——而这类错误在写入阶段是静默的。
    """
    print("\n----- 演示用例可用性验证 -----")

    zhang = list(session.run(_CYPHER_CASE_ZHANG, kg_version=kg_version))
    kinds = {rec["et"]: rec["c"] for rec in zhang}
    ok = {"BUSINESS_TRIP", "WORK_ORDER", "LOCATION_RECORD"} <= kinds.keys()
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E001 张伟证据链："
        f"出差 {kinds.get('BUSINESS_TRIP', 0)} / 工单 {kinds.get('WORK_ORDER', 0)} / "
        f"定位 {kinds.get('LOCATION_RECORD', 0)}"
    )

    # 门禁必须**按日**看：总数不为 0 才正常（他在总部办公日有刷卡），
    # 关键是他 10-16 出差当天**没有**、而前一日**有**——缺失才构成证据。
    gates = {
        str(rec["d"]): int(rec["c"])
        for rec in session.run(_CYPHER_CASE_ZHANG_GATE, kg_version=kg_version)
    }
    ok = gates.get("2026-10-16", 0) == 0 and gates.get("2026-10-15", 0) > 0
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E001 张伟门禁按日："
        f"10-15 有 {gates.get('2026-10-15', 0)} 条 / 10-16 出差当天 "
        f"{gates.get('2026-10-16', 0)} 条 → 缺卡日的缺失才构成证据"
        f"（门禁总数 {kinds.get('ACCESS_RECORD', 0)} 条，不能按总数判断）"
    )

    li = session.run(_CYPHER_CASE_LI, kg_version=kg_version).single()
    hours = float(li["total_hours"] or 0)
    ot = hours - 174.0
    ok = ot > 36.0
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E002 李静：排班 {li['shifts']} 条、"
        f"累计 {hours:.0f}h → 加班 {ot:.0f}h（>36h 才触发预警）"
    )

    wang = session.run(_CYPHER_CASE_WANG, kg_version=kg_version).single()
    absent = int(wang["core_absent"])
    print(
        f"  [{'OK ' if absent > 5 else 'FAIL'}] E003 王强：核心时段未在岗 {absent} 次（阈值 5）"
    )

    chen = session.run(_CYPHER_CASE_CHEN, kg_version=kg_version).single()
    ot_hours = float(chen["ot_hours"] or 0)
    used = float(chen["used_hours"] or 0)
    print(
        f"  [{'OK ' if ot_hours > 0 and used == 0 else 'FAIL'}] E004 陈敏："
        f"加班 {ot_hours:.0f}h / 已调休 {used:.0f}h"
    )

    cross = session.run(_CYPHER_CASE_CROSS_DOMAIN, kg_version=kg_version).single()
    n = int(cross["cross_edges"])
    print(
        f"  [{'OK ' if n > 0 else 'FAIL'}] 跨域边 TRIP_FOR_ORDER {n} 条"
        "（出差 ↔ 工单按日期窗口匹配，非外键）"
    )

    # R10（Sprint 9.6 G2）：李静 3 跳可达条款——事实与条款本体连通的验收用例
    clause = session.run(_CYPHER_CASE_LI_CLAUSE, kg_version=kg_version).single()
    clause_count = int(clause["clauses"])
    names = [str(x) for x in (clause["names"] or [])]
    print(
        f"  [{'OK ' if clause_count > 0 else 'FAIL'}] E002 李静 → 岗位 → 工时制 → "
        f"POLICY_CLAUSE：{clause_count} 条可达（样例 {names}）"
        "——R10 事实↔条款连通"
    )


def import_graph(
    *,
    driver: Any,
    database: str,
    kg_version: str,
    entity_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
    org_id: str,
    trace_id: str,
    purge: bool,
    now: str,
    purge_csv_prefixes: Sequence[str] = (),
    evidence: tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
    | None = None,
) -> IngestStats:
    """ADR-0002 三段式写入。"""
    stats = IngestStats(kg_version=kg_version)
    started = time.perf_counter()

    with driver.session(database=database) as session:
        for cypher in _CYPHER_CONSTRAINTS:
            try:
                session.run(cypher).consume()
            except Exception as exc:  # noqa: BLE001 - 约束非阻断
                print(f"  [warn] 约束创建失败（忽略）: {exc}", file=sys.stderr)

        # ---- 1/3：KgVersion -> writing ----
        session.run(
            _CYPHER_MERGE_KG_VERSION,
            kg_version=kg_version,
            status="writing",
            scope="domain:attendance",
            trace_id=trace_id,
            now=now,
        ).consume()
        print(f"  [1/3] KgVersion {kg_version} -> writing")

        if purge:
            session.run(_CYPHER_PURGE_VERSION, kg_version=kg_version).consume()
            print("  [purge] 已清理同版本历史数据（**含 M2 抽取的 span 实体**）")
        elif purge_csv_prefixes:
            result = session.run(
                _CYPHER_PURGE_CSV,
                kg_version=kg_version,
                prefixes=list(purge_csv_prefixes),
            ).consume()
            deleted = result.counters.nodes_deleted
            print(
                f"  [purge-csv] 已清理 {deleted} 个 CSV 派生节点"
                f"（前缀 {len(purge_csv_prefixes)} 类；M2 span 实体保留）"
            )

        try:
            # ---- 2/3：MERGE 节点 ----
            for batch in _batched(entity_rows, BATCH_SIZE):
                session.run(
                    _CYPHER_MERGE_ENTITIES,
                    rows=batch,
                    kg_version=kg_version,
                    org_id=org_id,
                    trace_id=trace_id,
                ).consume()
            print(f"  [2/3] MERGE 实体 {len(entity_rows)} 个")

            # ---- 2.2/3：B3 汇合边（R10 / Sprint 9.6 G1）----
            # 必须在实体 MERGE **之后**（工时制节点要先在库内）；
            # 产出的边并入 relation_rows ⇒ 写入自检与失败回滚自动覆盖。
            wts_rows = [
                row
                for row in entity_rows
                if row.get("entity_type") == "WORK_TIME_SYSTEM"
            ]
            if wts_rows:
                context = fetch_policy_context(session, kg_version=kg_version)
                # 派生边窗口继承（ADR-0005 §4 增补）：先算条款窗口表，再连边。
                # 三项计数必须可见 —— 继承了多少、放弃了多少，不得静默。
                windows, wstats = clause_windows(session, kg_version=kg_version)
                print(
                    "  [governed-by] 条款窗口：可继承 "
                    f"{wstats['one']} / 多义弃用 {wstats['many']} / 无窗口 "
                    f"{wstats['none']}"
                )
                # **R4-b 兜底**：本脚本不读制度原文 ⇒ 无从知道每个条款出自哪份
                # 文档，改从登记册取（登记侧是制度入图器，它知道）。
                # ``setdefault`` ⇒ **条款自身窗口优先**，文档窗口只补缺口，不覆盖。
                doc_scopes = load_document_scopes(DEFAULT_SCOPE_STORE)
                filled = 0
                for clause_id, window in doc_scopes.items():
                    if clause_id in windows:
                        continue
                    windows[clause_id] = (window[0], window[1])
                    filled += 1
                print(
                    f"  [governed-by] R4-b 文档级兜底：登记 {len(doc_scopes)}"
                    f" / 本次补位 {filled}"
                    + ("" if doc_scopes else "（登记册为空 ⇒ 未兜底，边保持无日期）")
                )
                governed_rows, misses = build_governed_by_relations(
                    wts_rows, context, windows
                )
                relation_rows.extend(governed_rows)
                print(
                    f"  [governed-by] 工时制 {len(wts_rows)} 类 × 条款语料 "
                    f"{len(context)} 条 ⇒ 连边 {len(governed_rows)} 条"
                )
                if misses:
                    print(
                        f"  [governed-by][warn] {len(misses)} 项未命中（可见，不静默）:",
                        file=sys.stderr,
                    )
                    for item in misses:
                        print(f"       - {item}", file=sys.stderr)
                if not governed_rows:
                    if context:
                        raise IngestError(
                            "GOVERNED_BY 连边为 0——事实与条款未连通（R10 目标未达），"
                            "拒绝以 active 收场"
                        )
                    #: **引导阶段（P6-D 2026-10-05）**：条款语料为 0 = 制度文档**还没入图**
                    #: （`ingest_attendance_policies.py` 未跑），而不是"连不上"——
                    #: 原写法在此处同样硬失败 ⇒ 与制度入图器互相等待（它要 WORK_TIME_SYSTEM，
                    #: 本脚本要条款）⇒ **死锁，演示图永远建不起来**。
                    #: 护栏的**本意**是抓"条款明明在却连不上"；条款根本不存在时不该由它拦。
                    #: ⇒ 此处跳过自检但**大声提示**，且**不谎报成功**：版本仍会置 active，
                    #: 但汇合边为 0 ⇒ 补跑制度入图器之前，R10 目标**仍未达成**。
                    print(
                        "  [governed-by][bootstrap] 条款语料为 0 ⇒ 制度文档尚未入图，"
                        "本轮不建汇合边（引导步骤，非连通性失败）；"
                        "下一步跑 scripts/ingest_attendance_policies.py 完成汇合",
                        file=sys.stderr,
                    )

            for batch in _batched(relation_rows, BATCH_SIZE):
                session.run(
                    _CYPHER_MERGE_RELATIONS,
                    rows=batch,
                    kg_version=kg_version,
                    org_id=org_id,
                    trace_id=trace_id,
                ).consume()
            print(f"  [2/3] MERGE 关系 {len(relation_rows)} 条")

            # ---- 写入自检：回读**本次提交的 id**，防"静默丢失" ----
            # 不按 kg_version 全量计数：同版本还有 M2 抽取的 span，全量会误报。
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

            # ---- 2.5/3：证据层（R14）----
            # 放在自检**之后**：MENTIONS 依赖实体先落库；放在 active 之前：
            # 证据写失败也要让版本停在 failed，不能对外声称"这个版本可用"。
            if evidence is not None:
                doc_rows, chunk_rows, mention_rows = evidence
                session.run(
                    _CYPHER_PURGE_EVIDENCE,
                    doc_ids=[str(row["id"]) for row in doc_rows],
                    kg_version=kg_version,
                ).consume()
                for batch in _batched(doc_rows, BATCH_SIZE):
                    session.run(
                        _CYPHER_MERGE_DOCUMENTS,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
                for batch in _batched(chunk_rows, BATCH_SIZE):
                    session.run(
                        _CYPHER_MERGE_CHUNKS,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
                for batch in _batched(mention_rows, BATCH_SIZE):
                    session.run(
                        _CYPHER_MERGE_MENTIONS,
                        rows=batch,
                        kg_version=kg_version,
                        org_id=org_id,
                        trace_id=trace_id,
                    ).consume()
                print(
                    f"  [evidence] Document {len(doc_rows)} / Chunk {len(chunk_rows)}"
                    f" / MENTIONS {len(mention_rows)}"
                )

            # ---- 3/3：-> active ----
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
            stats.version_status = "active"
            print("  [3/3] KgVersion -> active")

        except Exception as exc:  # noqa: BLE001 - 三段式失败补偿
            detail = f"{type(exc).__name__}: {exc}"[:500]
            print(f"  [3b] 失败，回滚并置 failed: {detail}", file=sys.stderr)
            try:
                # 只撤销本次写入（**不清空整个版本**，否则会连带删掉 M2 抽取的 span）
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
            stats.version_status = "failed"
            stats.elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise IngestError(detail) from exc

    stats.entity_count = len(entity_rows)
    stats.relation_count = len(relation_rows)
    stats.entity_types = _count_by(entity_rows, "entity_type")
    stats.relation_types = _count_by(relation_rows, "relation_type")
    stats.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return stats


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[str(row[key])] = out.get(str(row[key]), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def register_pg_kg_version(
    *, org_id: Any, version: str, entity_count: int, relation_count: int
) -> None:
    """把版本登记进 PG ``kg_versions`` —— **PG 才是 kg_version 的真源**。

    **为什么必须补这一步**：本脚本原先只写 Neo4j 的 ``:KgVersion`` 节点。
    但 Sprint 6.3 已收口「PG 真源 / Neo4j 只是镜像」（``graphs.py`` 的
    ``fetch_active_kg_version`` 传入 ``db`` 时**只认 PG 的 ready 行**）
    ⇒ 只落 Neo4j 的版本在 PG 里**根本不存在**，读侧按 PG 给出的 active 版本
    查 Neo4j 就会**什么都查不到**（2026-09-27 实测：``nodes = 0``，
    而 Neo4j 里明明躺着 2954 个考勤实体）。

    "写进去了却查不出来"是本项目的老伤（2026-09-26 同族错配已致一次演示事故），
    故在此收口：**入图 ≠ 可查，必须两边都登记**。

    幂等：同 ``version`` 已存在则复用，不重复 insert；重跑会刷新 ``ready_at``
    ⇒ ``get_active``（取 ``ready_at`` 最新）稳定选中本版本。
    """
    init_db()
    # A4：org 来自脚本入参（操作员显式给）
    with open_session(org_id=org_id) as db:
        svc = KgVersioningService(db)
        existing = svc.get_by_version(org_id=org_id, version=version)
        if existing is None:
            existing = svc.create_pending(
                org_id=org_id,
                version=version,
                source_doc_ids=[],  # 结构化 CSV 入图，无源文档
                trace_id=uuid.uuid4(),
            )
            print(f"  [PG] 新建版本行 {version}（pending）")
        else:
            print(f"  [PG] 复用已存在版本行 {version}（status={existing.status}）")

        version_id = uuid.UUID(str(existing.id))
        svc.mark_building(version_id)
        svc.mark_ready(
            version_id,
            entity_count=entity_count,
            relation_count=relation_count,
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
        description="考勤域 CSV → Neo4j 入图（ADR-0002 三段式）"
    )
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING))
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument("--dry-run", action="store_true", help="只解析，不写库")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="先清理同 kg_version 的**全部**实体（含 M2 抽取的 span，慎用）",
    )
    parser.add_argument(
        "--purge-csv",
        action="store_true",
        help="只清理本 mapping 派生的节点（id 前缀 <ENTITY_TYPE>:），保留 M2 抽取产物",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    mapping = load_mapping(Path(args.mapping).resolve())
    kg_version = args.kg_version
    trace_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    print("===== ingest_attendance_csv =====")
    print(f"mapping    : {args.mapping}")
    print(f"kg_version : {kg_version}")

    entity_rows, node_ids = build_nodes(mapping)
    relation_rows, unresolved = build_relations(mapping, node_ids)
    print(f"规范化结果 : 实体 {len(entity_rows)} / 关系 {len(relation_rows)}")
    # 证据层（R14）：CSV 原文行 → Document / Chunk / MENTIONS
    evidence = build_evidence(mapping, node_ids)
    print(
        f"证据层     : Document {len(evidence[0])} / Chunk {len(evidence[1])}"
        f" / MENTIONS {len(evidence[2])}"
    )
    if unresolved:
        print(
            f"[warn] {len(unresolved)} 条关系端点无法解析（已跳过）:",
            file=sys.stderr,
        )
        for item in unresolved[:10]:
            print(f"       - {item}", file=sys.stderr)

    if args.dry_run:
        print("[dry-run] 未连接 Neo4j，退出。")
        return 0

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
        stats = import_graph(
            driver=driver,
            database=settings.neo4j_database,
            kg_version=kg_version,
            entity_rows=entity_rows,
            relation_rows=relation_rows,
            org_id=str(settings.default_org_id),
            trace_id=trace_id,
            purge=args.purge,
            now=now,
            purge_csv_prefixes=_derived_prefixes(mapping) if args.purge_csv else (),
            evidence=evidence,
        )
        with driver.session(database=settings.neo4j_database) as session:
            verify_cases(session, kg_version=kg_version)
        # 入图 ≠ 可查：Neo4j 侧就绪后，还必须登记 PG 真源，否则读侧查不到
        register_pg_kg_version(
            org_id=settings.default_org_id,
            version=kg_version,
            entity_count=stats.entity_count,
            relation_count=stats.relation_count,
        )
    except Exception as exc:  # noqa: BLE001 - CLI 统一兜底
        print(f"[FAIL] 入图失败: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()

    print("\n===== 入图结果 =====")
    print(f"kg_version : {stats.kg_version}")
    print(f"版本状态   : {stats.version_status}")
    print(f"实体数     : {stats.entity_count}")
    print(f"关系数     : {stats.relation_count}")
    print(
        "实体分布   : " + ", ".join(f"{k}={v}" for k, v in stats.entity_types.items())
    )
    print(
        "关系分布   : " + ", ".join(f"{k}={v}" for k, v in stats.relation_types.items())
    )
    print(f"耗时       : {stats.elapsed_ms} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
