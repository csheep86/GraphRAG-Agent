"""考勤域 CSV → Neo4j 入图器（Sprint 9.5 批次 B1）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/ingest_attendance_csv.py
    uv run python scripts/ingest_attendance_csv.py --kg-version attendance-demo-v1
    uv run python scripts/ingest_attendance_csv.py --dry-run   # 只解析，不写库
    uv run python scripts/ingest_attendance_csv.py --purge     # 先清同版本残留

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
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import yaml  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
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
    r.org_id = $org_id,
    r.trace_id = $trace_id
RETURN count(r) AS merged
"""

_CYPHER_PURGE_VERSION = "MATCH (n:Entity {kg_version: $kg_version}) DETACH DELETE n"

_CYPHER_COUNT_VERSION_GRAPH = """
MATCH (n:Entity {kg_version: $kg_version})
WITH count(n) AS entity_count
MATCH ()-[r:RELATION {kg_version: $kg_version}]->()
RETURN entity_count AS entity_count, count(r) AS relation_count
"""


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
            print("  [purge] 已清理同版本历史数据")

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

            for batch in _batched(relation_rows, BATCH_SIZE):
                session.run(
                    _CYPHER_MERGE_RELATIONS,
                    rows=batch,
                    kg_version=kg_version,
                    org_id=org_id,
                    trace_id=trace_id,
                ).consume()
            print(f"  [2/3] MERGE 关系 {len(relation_rows)} 条")

            # ---- 写入自检：回读真实计数，防"静默丢失" ----
            record = session.run(
                _CYPHER_COUNT_VERSION_GRAPH, kg_version=kg_version
            ).single()
            actual_entities = int(record["entity_count"]) if record else 0
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
                session.run(_CYPHER_PURGE_VERSION, kg_version=kg_version).consume()
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
    with SessionLocal() as db:
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
    parser.add_argument("--purge", action="store_true", help="先清理同 kg_version 残留")
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
