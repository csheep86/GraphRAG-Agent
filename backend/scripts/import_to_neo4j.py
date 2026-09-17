"""把 Bridge Pipeline 产物（`bridge_web_demo/output.json`）导入 Neo4j。

严格遵循 `docs/adr/ADR-0002-neo4j-postgres-consistency.md` 的三段式写入：

    1) 创建 `:KgVersion` 节点，`status = 'writing'`
    2) Cypher `MERGE` 实体节点 / 关系边（带 `kg_version` 属性）
    3) 成功 → `status = 'active'`；失败 → `status = 'failed'` 并清理本次写入的数据

> **Sprint 3 阶段九的临时取舍（待 Sprint 4 迁移）**：ADR-0002 规定 PostgreSQL
> `kg_versions` 表为 Source of Truth。当前 backend 尚无 `kg_versions` ORM 模型，
> 因此本脚本把版本状态机**落在 Neo4j 的 `:KgVersion` 节点**上，语义（仅 `active`
> 可被查询层消费）与 ADR-0002 §3.1 / §3.2 完全一致；Sprint 4 接入 PG 后，本脚本
> 改为「先 PG `writing` → Neo4j MERGE → PG `active`/`failed`」，Neo4j 侧节点类型
> 与属性保持不变，GraphService 无需改动。

用法（工作目录 = `backend/`）：

    uv run python scripts/import_to_neo4j.py
    uv run python scripts/import_to_neo4j.py --input ../bridge_web_demo/output.json
    uv run python scripts/import_to_neo4j.py --kg-version 20260917T1600Z-abc12345
    uv run python scripts/import_to_neo4j.py --dry-run        # 只解析 + 校验，不写库
    uv run python scripts/import_to_neo4j.py --purge          # 先清理同版本残留再导入

幂等性（ADR-0002 §3.3）：实体 `MERGE (e:Entity {id, kg_version})`、
关系 `MERGE (h)-[r:TYPE {id, kg_version}]->(t)`，以 `(id, kg_version)` 为幂等键，
重复执行不产生重复数据，可安全重放。
"""

from __future__ import annotations

import argparse
import json
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

from tenacity import (  # noqa: E402
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
DEFAULT_INPUT = REPO_ROOT / "bridge_web_demo" / "output.json"

SUPPORTED_SCHEMA_VERSION = "1.0"

# --------------------------------------------------------------------------- #
# 关系类型映射（**显式白名单**，杜绝把外部字符串直接拼进 Cypher）
#
# Neo4j 的关系类型无法参数化，必须字面量写入；因此这里用白名单把 Bridge Pipeline
# 的中文关系名映射为受控的 ASCII token，再拼接进 Cypher —— 不在白名单内的一律
# 落到 `RELATED`，**绝不**透传原始字符串。
#
# ⚠️ 契约对齐提示：`contracts/openapi.yaml` 的 `GraphEdge.type` 枚举仅含
#    HAS_CHUNK / MENTIONS / SUPPORTED_BY / AFFILIATED_WITH / SUPPLIES_TO / PARTY_TO，
#    并未定义「实体↔实体 财务指标」这类关系。本脚本**不改契约**，在 Neo4j 侧保留
#    原始关系名（`relation_name` 属性），由 GraphService 做受控投影。
# --------------------------------------------------------------------------- #
RELATION_TOKEN_MAP: dict[str, str] = {
    "股权持有": "AFFILIATED_WITH",
    "控股": "AFFILIATED_WITH",
    "具有财务指标": "HAS_FINANCIAL_INDICATOR",
    "经营业务板块": "OPERATES_SEGMENT",
    "关联": "RELATED",
}
DEFAULT_RELATION_TOKEN = "RELATED"

#: 允许出现在 Cypher 中的关系类型 token 全集（白名单校验用）
ALLOWED_RELATION_TOKENS: frozenset[str] = frozenset(RELATION_TOKEN_MAP.values()) | {
    DEFAULT_RELATION_TOKEN
}

#: 需要从属性中剔除的字段（M2 §5.3：`pii_flags` 严禁外泄 / 落库）
FORBIDDEN_PROPERTY_KEYS: frozenset[str] = frozenset({"pii_flags"})


class ImportError_(Exception):
    """导入流程的业务错误（供 CLI 捕获后返回非 0 退出码）。"""


class Neo4jTransientError(Exception):
    """可重试的 Neo4j 瞬时错误（网络抖动 / 主从切换 / 死锁）。"""


@dataclass
class ImportStats:
    """导入结果统计。"""

    kg_version: str
    entity_count: int = 0
    relation_count: int = 0
    relation_types: dict[str, int] = field(default_factory=dict)
    elapsed_ms: int = 0
    version_status: str = "unknown"
    input_path: str = ""


# --------------------------------------------------------------------------- #
# 读取与规范化
# --------------------------------------------------------------------------- #
def load_source(path: Path) -> dict[str, Any]:
    """读取并做最小校验（schema_version）。"""
    if not path.is_file():
        raise ImportError_(f"输入文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportError_(f"输入不是合法 JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ImportError_(f"输入顶层必须是对象: {path}")
    schema_version = str(data.get("schema_version", ""))
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ImportError_(
            f"不支持的 schema_version={schema_version!r}（仅支持 {SUPPORTED_SCHEMA_VERSION}）"
        )
    if not isinstance(data.get("entities"), list) or not isinstance(
        data.get("relations"), list
    ):
        raise ImportError_("输入缺少 entities / relations 数组")
    return data


def _json_attr(value: Any) -> str:
    """Neo4j 属性只接受基本类型 / 基本类型数组，复杂结构统一序列化为 JSON 字符串。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _char_positions(char_interval: Any) -> tuple[int | None, int | None]:
    if not isinstance(char_interval, dict):
        return None, None
    start = char_interval.get("start_pos")
    end = char_interval.get("end_pos")
    return (
        int(start) if isinstance(start, int) else None,
        int(end) if isinstance(end, int) else None,
    )


def build_entity_rows(
    data: dict[str, Any], *, org_id: str | None
) -> list[dict[str, Any]]:
    """把 `entities[]` 规范化为 MERGE 参数行。"""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entity in data["entities"]:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("id") or "").strip()
        name = str(entity.get("name") or "").strip()
        if not entity_id or not name:
            continue
        if entity_id in seen:
            continue
        seen.add(entity_id)

        attributes = entity.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        attributes = {
            k: v for k, v in attributes.items() if k not in FORBIDDEN_PROPERTY_KEYS
        }
        start_pos, end_pos = _char_positions(entity.get("char_interval"))

        rows.append(
            {
                "id": entity_id,
                "name": name,
                "type": str(entity.get("type") or "OTHER"),
                "attributes_json": _json_attr(attributes),
                "grounded": bool(entity.get("grounded", False)),
                "auto_created": bool(entity.get("auto_created", False)),
                "alignment_status": entity.get("alignment_status"),
                "evidence": str(entity.get("evidence") or name),
                "char_start": start_pos,
                "char_end": end_pos,
                "org_id": org_id,
            }
        )
    return rows


def build_relation_rows(
    data: dict[str, Any], name_to_id: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """把 `relations[]` 规范化为 MERGE 参数行（含白名单 token）。

    **关键**：`relations[].head / tail` 存的是**实体名**（如「智能制造」），
    不是 `entities[].id`（如 `e1`）。这里必须先经 `name_to_id` 解析成 id，
    否则 MERGE 匹配不到端点，关系会**静默丢失**。

    :returns: ``(rows, unresolved)``；``unresolved`` 为无法解析端点的关系描述。
    """
    rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()

    for index, relation in enumerate(data["relations"], start=1):
        if not isinstance(relation, dict):
            continue
        head = str(relation.get("head") or "").strip()
        tail = str(relation.get("tail") or "").strip()
        relation_name = str(relation.get("relation") or "关联").strip()
        if not head or not tail:
            continue

        head_id = name_to_id.get(head)
        tail_id = name_to_id.get(tail)
        if head_id is None or tail_id is None:
            unresolved.append(
                f"{head}({head_id}) -[{relation_name}]-> {tail}({tail_id})"
            )
            continue

        rel_id = str(relation.get("id") or f"r{index}").strip()
        key = (rel_id, head_id, tail_id, relation_name)
        if key in seen:
            continue
        seen.add(key)

        token = RELATION_TOKEN_MAP.get(relation_name, DEFAULT_RELATION_TOKEN)
        if token not in ALLOWED_RELATION_TOKENS:  # 理论上不可达，作为最后一道闸
            token = DEFAULT_RELATION_TOKEN

        attributes = relation.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        attributes = {
            k: v for k, v in attributes.items() if k not in FORBIDDEN_PROPERTY_KEYS
        }
        start_pos, end_pos = _char_positions(relation.get("char_interval"))

        rows.append(
            {
                "id": rel_id,
                "token": token,
                "relation_name": relation_name,
                "head": head_id,
                "tail": tail_id,
                "head_name": head,
                "tail_name": tail,
                "head_type": str(relation.get("head_type") or ""),
                "tail_type": str(relation.get("tail_type") or ""),
                "derived": bool(relation.get("derived", False)),
                "attributes_json": _json_attr(attributes),
                "alignment_status": relation.get("alignment_status"),
                "evidence": str(relation.get("evidence") or ""),
                "char_start": start_pos,
                "char_end": end_pos,
            }
        )
    return rows, unresolved


# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #
_CYPHER_MERGE_KG_VERSION = """
MERGE (v:KgVersion {version: $kg_version})
SET v.status = $status,
    v.scope = $scope,
    v.source_path = $source_path,
    v.trace_id = $trace_id,
    v.updated_at = $now
RETURN v.status AS status
"""

_CYPHER_SET_VERSION_STATUS = """
MATCH (v:KgVersion {version: $kg_version})
SET v.status = $status,
    v.updated_at = $now,
    v.error_code = $error_code,
    v.error_detail = $error_detail,
    v.entity_count = $entity_count,
    v.relation_count = $relation_count
RETURN v.status AS status
"""

_CYPHER_MERGE_ENTITIES = """
UNWIND $rows AS row
MERGE (e:Entity {id: row.id, kg_version: $kg_version})
SET e.name = row.name,
    e.canonical_name = row.name,
    e.type = row.type,
    e.attributes_json = row.attributes_json,
    e.grounded = row.grounded,
    e.auto_created = row.auto_created,
    e.alignment_status = row.alignment_status,
    e.evidence = row.evidence,
    e.char_start = row.char_start,
    e.char_end = row.char_end,
    e.org_id = row.org_id,
    e.imported_at = $now,
    e.kg_version = $kg_version
RETURN count(e) AS merged
"""


def _cypher_merge_relations(token: str) -> str:
    """按白名单 token 生成关系 MERGE 语句（token 已校验，非用户输入直拼）。"""
    assert token in ALLOWED_RELATION_TOKENS, token  # noqa: S101 - 双重保险
    return f"""
UNWIND $rows AS row
MATCH (h:Entity {{id: row.head, kg_version: $kg_version}})
MATCH (t:Entity {{id: row.tail, kg_version: $kg_version}})
MERGE (h)-[r:{token} {{id: row.id, kg_version: $kg_version}}]->(t)
SET r.relation_name = row.relation_name,
    r.head_type = row.head_type,
    r.tail_type = row.tail_type,
    r.derived = row.derived,
    r.attributes_json = row.attributes_json,
    r.alignment_status = row.alignment_status,
    r.evidence = row.evidence,
    r.char_start = row.char_start,
    r.char_end = row.char_end,
    r.imported_at = $now,
    r.kg_version = $kg_version
RETURN count(r) AS merged
"""


_CYPHER_PURGE_VERSION = """
MATCH (e:Entity {kg_version: $kg_version})
DETACH DELETE e
"""

_CYPHER_CONSTRAINTS = (
    "CREATE CONSTRAINT kg_version_unique IF NOT EXISTS "
    "FOR (v:KgVersion) REQUIRE v.version IS UNIQUE",
    "CREATE CONSTRAINT entity_id_version_unique IF NOT EXISTS "
    "FOR (e:Entity) REQUIRE (e.id, e.kg_version) IS UNIQUE",
)


# --------------------------------------------------------------------------- #
# 写入编排
# --------------------------------------------------------------------------- #
def _is_transient(exc: BaseException) -> bool:
    """Neo4j 瞬时错误判定（网络层 / 事务冲突 / 死锁）。"""
    from neo4j.exceptions import (  # type: ignore[import-not-found]
        DeadlockDetected,
        ServiceUnavailable,
        SessionExpired,
        TransientError,
    )

    return isinstance(
        exc, (ServiceUnavailable, SessionExpired, TransientError, DeadlockDetected)
    )


def _run_with_retry(
    session: Any, cypher: str, params: dict[str, Any], *, what: str
) -> Any:
    """执行单条 Cypher，失败时 tenacity 指数退避重试（≤ 3 次，初始 1s、倍数 2）。

    :returns: Neo4j ``ResultSummary``（可用 ``.counters`` 读取真实写入计数）。
    """
    settings = get_settings()
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(settings.task_retry_max_attempts),
            wait=wait_exponential(multiplier=settings.task_retry_initial_seconds),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    print(
                        f"  [retry] {what} 第 {attempt.retry_state.attempt_number} 次尝试",
                        file=sys.stderr,
                    )
                return session.run(cypher, **params).consume()
    except RetryError as exc:  # pragma: no cover - 防御
        raise ImportError_(f"{what} 重试耗尽: {exc}") from exc
    raise ImportError_(f"{what} 未执行")  # pragma: no cover


def _ensure_constraints(session: Any) -> None:
    """创建唯一约束（幂等）。权限不足时告警但不阻断导入。"""
    for cypher in _CYPHER_CONSTRAINTS:
        try:
            session.run(cypher).consume()
        except Exception as exc:  # noqa: BLE001 - 约束非阻断
            print(f"  [warn] 创建约束失败（忽略）: {exc}", file=sys.stderr)


_CYPHER_COUNT_VERSION_GRAPH = """
MATCH (e:Entity {kg_version: $kg_version})
WITH count(e) AS entity_count
MATCH ()-[r]->()
WHERE r.kg_version = $kg_version
RETURN entity_count AS entity_count, count(r) AS relation_count
"""


def _verify_version_graph(
    session: Any,
    *,
    kg_version: str,
    expected_entities: int,
    expected_relations: int,
) -> tuple[int, int]:
    """回读 Neo4j 真实计数；与期望不一致则抛错，触发三段式失败补偿。"""
    record = session.run(_CYPHER_COUNT_VERSION_GRAPH, kg_version=kg_version).single()
    actual_entities = int(record["entity_count"]) if record else 0
    actual_relations = int(record["relation_count"]) if record else 0

    if actual_entities != expected_entities or actual_relations != expected_relations:
        raise ImportError_(
            "写入自检失败（可能与端点解析 / MERGE 键错位有关）: "
            f"期望 Entity={expected_entities} Relation={expected_relations}，"
            f"实际 Entity={actual_entities} Relation={actual_relations}"
        )
    return actual_entities, actual_relations


def import_graph(
    *,
    driver: Any,
    database: str,
    kg_version: str,
    entity_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
    source_path: str,
    trace_id: str,
    scope: str,
    purge: bool,
    now: str,
) -> ImportStats:
    """执行 ADR-0002 三段式写入。"""
    stats = ImportStats(kg_version=kg_version, input_path=source_path)
    started = time.perf_counter()

    with driver.session(database=database) as session:
        _ensure_constraints(session)

        # ---- 三段式 1/3：PG(此处为 Neo4j :KgVersion) 落 writing ----
        _run_with_retry(
            session,
            _CYPHER_MERGE_KG_VERSION,
            {
                "kg_version": kg_version,
                "status": "writing",
                "scope": scope,
                "source_path": source_path,
                "trace_id": trace_id,
                "now": now,
            },
            what="创建 KgVersion(writing)",
        )
        print(f"  [1/3] KgVersion {kg_version} -> writing")

        if purge:
            _run_with_retry(
                session,
                _CYPHER_PURGE_VERSION,
                {"kg_version": kg_version},
                what="清理同版本残留",
            )
            print("  [purge] 已清理同版本历史数据")

        try:
            # ---- 三段式 2/3：Neo4j MERGE 节点与关系 ----
            if entity_rows:
                entity_summary = _run_with_retry(
                    session,
                    _CYPHER_MERGE_ENTITIES,
                    {"rows": entity_rows, "kg_version": kg_version, "now": now},
                    what="MERGE 实体节点",
                )
                created = entity_summary.counters.nodes_created
                if created < len(entity_rows):
                    print(
                        f"  [2/3] 实体已存在 {len(entity_rows) - created} 条（MERGE 幂等）"
                    )
            print(f"  [2/3] MERGE 实体 {len(entity_rows)} 条")

            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in relation_rows:
                grouped.setdefault(row["token"], []).append(row)

            merged_relations = 0
            for token, rows in grouped.items():
                rel_summary = _run_with_retry(
                    session,
                    _cypher_merge_relations(token),
                    {"rows": rows, "kg_version": kg_version, "now": now},
                    what=f"MERGE 关系 {token}",
                )
                created = rel_summary.counters.relationships_created
                merged_relations += len(rows)
                stats.relation_types[token] = len(rows)
                print(f"  [2/3]   关系 {token}: 期望 {len(rows)} / 新建 {created}")
            print(f"  [2/3] MERGE 关系 {merged_relations} 条（{len(grouped)} 种类型）")

            # ---- 写入自检：读回真实计数，防止「静默丢失」（例如端点解析错位）----
            actual = _verify_version_graph(
                session,
                kg_version=kg_version,
                expected_entities=len(entity_rows),
                expected_relations=len(relation_rows),
            )
            print(
                f"  [self-check] Neo4j 回读：Entity={actual[0]} / Relation={actual[1]}"
            )

            # ---- 三段式 3a：置 active ----
            _run_with_retry(
                session,
                _CYPHER_SET_VERSION_STATUS,
                {
                    "kg_version": kg_version,
                    "status": "active",
                    "now": now,
                    "error_code": None,
                    "error_detail": None,
                    "entity_count": len(entity_rows),
                    "relation_count": len(relation_rows),
                },
                what="置 KgVersion(active)",
            )
            stats.version_status = "active"
            print("  [3/3] KgVersion -> active")

        except Exception as exc:  # noqa: BLE001 - 三段式 3b：失败补偿
            error_detail = f"{type(exc).__name__}: {exc}"[:500]
            print(
                f"  [3b] 写入失败，回滚为 failed 并清理: {error_detail}",
                file=sys.stderr,
            )
            try:
                _run_with_retry(
                    session,
                    _CYPHER_PURGE_VERSION,
                    {"kg_version": kg_version},
                    what="失败清理实体",
                )
                _run_with_retry(
                    session,
                    _CYPHER_SET_VERSION_STATUS,
                    {
                        "kg_version": kg_version,
                        "status": "failed",
                        "now": now,
                        "error_code": "IMPORT_FAILED",
                        "error_detail": error_detail,
                        "entity_count": 0,
                        "relation_count": 0,
                    },
                    what="置 KgVersion(failed)",
                )
            except Exception as cleanup_exc:  # noqa: BLE001
                print(f"  [3b] 补偿本身失败: {cleanup_exc}", file=sys.stderr)
            stats.version_status = "failed"
            stats.elapsed_ms = int((time.perf_counter() - started) * 1000)
            raise ImportError_(f"Neo4j 写入失败已回滚: {error_detail}") from exc

    stats.entity_count = len(entity_rows)
    stats.relation_count = len(relation_rows)
    stats.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return stats


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _default_kg_version() -> str:
    """生成 `YYYYMMDDTHHMMSSZ-<8hex>` 形式的版本号。"""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="把 Bridge Pipeline 产物导入 Neo4j（ADR-0002 三段式写入）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="输入 JSON 路径")
    parser.add_argument(
        "--neo4j-uri", default=settings.neo4j_uri, help="Neo4j bolt URI"
    )
    parser.add_argument(
        "--neo4j-user", default=settings.neo4j_user, help="Neo4j 用户名"
    )
    parser.add_argument(
        "--neo4j-password",
        default=settings.neo4j_password,
        help="Neo4j 密码（缺省取 NEO4J_PASSWORD 环境变量）",
    )
    parser.add_argument(
        "--neo4j-database", default=settings.neo4j_database, help="数据库名"
    )
    parser.add_argument(
        "--kg-version",
        default=None,
        help="图谱版本号；缺省按 UTC 时间戳自动生成",
    )
    parser.add_argument(
        "--scope",
        default="global",
        help="版本作用域（ADR-0002 §3.1；W3 单文档抽取应为 doc:<uuid>）",
    )
    parser.add_argument(
        "--org-id",
        default=None,
        help="租户 id（ADR-0003）；缺省不写入 org_id 属性",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="导入前先清理同 kg_version 的历史数据（默认 MERGE 幂等，不清理）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析与校验输入，不连接 Neo4j、不写库",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，中文统计输出需要显式切 UTF-8
    if (
        sys.stdout
        and sys.stdout.encoding
        and sys.stdout.encoding.lower()
        not in (
            "utf-8",
            "utf8",
        )
    ):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if (
        sys.stderr
        and sys.stderr.encoding
        and sys.stderr.encoding.lower()
        not in (
            "utf-8",
            "utf8",
        )
    ):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    kg_version = args.kg_version or _default_kg_version()
    trace_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    print("===== import_to_neo4j =====")
    print(f"输入文件   : {input_path}")
    print(f"kg_version : {kg_version}")
    print(f"scope      : {args.scope}")
    print(f"trace_id   : {trace_id}")

    try:
        data = load_source(input_path)
        entity_rows = build_entity_rows(data, org_id=args.org_id)
        # relations[].head / tail 是**实体名**，必须先解析成 entity_id
        name_to_id = {row["name"]: row["id"] for row in entity_rows}
        relation_rows, unresolved = build_relation_rows(data, name_to_id)
    except ImportError_ as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    source_stats = data.get("stats", {})
    print(f"源文件统计 : {json.dumps(source_stats, ensure_ascii=False)}")
    print(f"规范化结果 : 实体 {len(entity_rows)} / 关系 {len(relation_rows)}")
    if unresolved:
        print(
            f"[warn] {len(unresolved)} 条关系端点无法解析为实体 id（已跳过）:",
            file=sys.stderr,
        )
        for item in unresolved[:10]:
            print(f"       - {item}", file=sys.stderr)

    if args.dry_run:
        print("[dry-run] 未连接 Neo4j，退出。")
        return 0

    if not args.neo4j_password:
        print("[FAIL] NEO4J_PASSWORD 未配置，请检查 backend/.env", file=sys.stderr)
        return 1

    from neo4j import GraphDatabase  # type: ignore[import-not-found]

    driver = GraphDatabase.driver(
        args.neo4j_uri,
        auth=(args.neo4j_user, args.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        driver.verify_connectivity()
        print(f"Neo4j 连接 : {args.neo4j_uri} (db={args.neo4j_database})")

        stats = import_graph(
            driver=driver,
            database=args.neo4j_database,
            kg_version=kg_version,
            entity_rows=entity_rows,
            relation_rows=relation_rows,
            source_path=str(input_path),
            trace_id=trace_id,
            scope=args.scope,
            purge=args.purge,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 - CLI 统一兜底
        print(f"[FAIL] 导入失败: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()

    print("\n===== 导入结果 =====")
    print(f"kg_version : {stats.kg_version}")
    print(f"版本状态   : {stats.version_status}")
    print(f"实体数     : {stats.entity_count}")
    print(f"关系数     : {stats.relation_count}")
    print(f"关系类型   : {json.dumps(stats.relation_types, ensure_ascii=False)}")
    print(f"耗时       : {stats.elapsed_ms} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
