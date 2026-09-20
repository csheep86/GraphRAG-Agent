"""图谱服务：封装 Neo4j 连接与 Cypher 查询（ADR-0002 / M2 §5.4）。

公开面：
- :class:`GraphService`：通过 ``GraphService.instance()`` 取单例；
- :class:`GraphUnavailableError`：连接失败 / 查询失败时抛，路由层捕获后转
  ``501 NOT_IMPLEMENTED``（阶段九契约未实装）；
- :meth:`GraphService.fetch_active_kg_version`：取唯一 ``status='active'`` 版本；
- :meth:`GraphService.fetch_kg_version_status`：取指定版本的 ``status``（409 判定依据）；
- :meth:`GraphService.fetch_document_subgraph`：按 PG ``document_id`` 查子图（M2 数据）；
- :meth:`GraphService.fetch_all_subgraph`：查**全部**已导入实体图（桥梁产物，
  不依赖 ``document_id``）。

设计要点：
1. **懒加载 driver**：模块导入时不连接 Neo4j；第一次调用 ``instance()`` 时
   才尝试建连接，避免 pytest / 启动失败被外部依赖绑架。
2. **kg_version 强制 active**：所有 Cypher 都带 ``WHERE n.kg_version = $kg_version``
   且 ``kg_version`` 由 :meth:`fetch_active_kg_version` 给出，**严禁**调用方传入
   ``writing`` / ``failed`` / ``superseded`` 版本。
3. **MERGE 幂等**：写入路径使用 ``MERGE``，以 ``(id, kg_version)`` 为幂等键
   （ADR-0002 §3.3），支持 Saga 重放。
4. **关系类型映射**：见 :func:`_relation_type` —— 命中契约枚举（含桥梁抽取的
   实体↔实体类关系，Sprint 4.10.0.B 扩展）原样直通；**未知类型**兜底投影为
   ``MENTIONS``，真实关系名保留在 ``properties["relation_name"]``。
5. **投影失败显式化**（Sprint 4.10.0.D1 缺口 5）：Neo4j 返回的原始数据与契约
   不符（字段缺失 / 类型非法）时，把 Pydantic 构造异常**包装**为
   :class:`GraphUnavailableError`（路由层转 ``501``），消息中带上
   「上下文 + 第几条 + 字段级明细」；**不**跳过坏记录、**更不**静默返回空图——
   空图会被上层误判为「图谱里没有证据」而返回 ``refused = true``（200），
   把数据质量故障伪装成正常业务结论。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loguru import logger

from app.core.config import get_settings
from app.schemas.document import GraphEdge, GraphNode, RelationType


class GraphUnavailableError(Exception):
    """Neo4j 不可用（连接失败 / 查询超时 / 凭据错误等）。

    路由层捕获后转 ``501 NOT_IMPLEMENTED``（阶段九骨架）或 ``503``。
    """


class NoActiveKgVersionError(GraphUnavailableError):
    """Neo4j **可达**，但不存在 ``status = 'active'`` 的 ``:KgVersion``。

    刻意继承 :class:`GraphUnavailableError`，既有的 ``except GraphUnavailableError``
    仍能兜住它；同时让业务层能**区分**两种截然不同的故障：

    - :class:`NoActiveKgVersionError` → **版本状态问题** → ``409 KG_VERSION_NOT_ACTIVE``
      （契约对 ``GET /documents/{id}/graph`` 的明文要求：「该文档不存在 active 版本时返回 409」）；
    - 其它 :class:`GraphUnavailableError` → **基础设施故障** → ``501``。

    两者若混为一谈，前端就无法区分「数据没准备好」与「后端挂了」——
    前者应提示等待 / 引导导入，后者应触发告警与重试。
    """


@dataclass(frozen=True, slots=True)
class KgVersion:
    """当前 active ``kg_version`` 投影。"""

    version: str
    scope: str  # "doc:<uuid>" 或 "global"


#: Cypher 查询：当前 active kg_version（ADR-0002 §3.2 —— **仅** active 可被消费）。
#: 阶段九由 ``scripts/import_to_neo4j.py`` 在 Neo4j 侧维护 :KgVersion 状态机；
#: Sprint 4 接入 PG ``kg_versions`` 后，PG 为真源、此查询退化为兜底。
_QUERY_ACTIVE_KG_VERSION = """
MATCH (v:KgVersion {status: 'active'})
WHERE $scope IS NULL OR v.scope = $scope
RETURN v.version AS version, v.scope AS scope
ORDER BY v.version DESC
LIMIT 1
"""

#: Cypher 查询：指定 ``kg_version`` 的 status（ADR-0002 §3.2 的 409 判定依据）。
#: 节点不存在时返回空结果集（而非报错），由 Python 侧映射为 ``None``。
_QUERY_KG_VERSION_STATUS = """
MATCH (v:KgVersion {version: $version})
RETURN v.status AS status
LIMIT 1
"""

#: Cypher 查询：**全部**已导入实体子图（不依赖 PG ``document_id``）。
#: 供 ``bridge_web_demo`` 阶段六产物（``:Entity`` + 实体间关系）查询使用。
#: ``elementId`` 用于稳定去重，``id`` 属性作为对外节点标识（与边的 source/target 对齐）。
_QUERY_ALL_ENTITY_SUBGRAPH = """
MATCH (n:Entity {kg_version: $kg_version})
// 用 properties(n)['org_id'] 而非 n.org_id：后者在库中尚无该属性键时
// 会触发 ``01N52 property key does not exist`` 通知（噪声日志）。
WITH n
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
WITH collect(n) AS all_nodes
WITH all_nodes[0..$node_limit] AS nodes, size(all_nodes) AS total_nodes
RETURN
  nodes,
  total_nodes,
  [(a)-[r]->(b) WHERE a IN nodes AND b IN nodes | {
    id: coalesce(r.id, elementId(r)),
    type: type(r),
    source: a.id,
    target: b.id,
    properties: properties(r)
  }] AS edges
"""

#: Cypher 查询：单个文档的子图（节点 + 关系），受 doc_id + kg_version 双重约束。
#: 规模上限 500 节点，超限由 Python 侧裁剪 + ``truncated = true`` 标记。
_QUERY_DOCUMENT_SUBGRAPH = """
MATCH (d:Document {id: $doc_id, kg_version: $kg_version})
OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
WHERE c.kg_version = $kg_version
OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
WHERE e.kg_version = $kg_version
  AND ($org_id IS NULL OR e.org_id = $org_id)
WITH d, collect(DISTINCT c) AS chunks,
     collect(DISTINCT e) AS entities
LIMIT $node_limit
RETURN
  d,
  chunks,
  entities,
  [(c)-[r:MENTIONS]->(e) | {
    id: toString(id(r)),
    type: type(r),
    source: toString(id(c)),
    target: toString(id(e)),
    properties: properties(r)
  }] AS mentions
"""


class GraphService:
    """Neo4j 服务封装（懒加载 + 单例）。"""

    _instance: GraphService | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._driver = None

    @classmethod
    def instance(cls) -> GraphService:
        """取全局单例；第一次调用时尝试建立 Neo4j 连接。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅供测试）。"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    # ------------------------------------------------------------------ driver

    def _ensure_driver(self):  # noqa: ANN202 - 第三方类型
        """懒加载 Neo4j driver；未配置或连接失败抛 :class:`GraphUnavailableError`。"""
        if self._driver is not None:
            return self._driver
        settings = get_settings()
        if not settings.neo4j_password:
            raise GraphUnavailableError(
                "NEO4J_PASSWORD 未配置（请在 .env.development 中填写）"
            )
        try:
            # 局部导入：避免模块导入阶段触发连接
            from neo4j import GraphDatabase  # type: ignore[import-not-found]

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                connection_timeout=settings.neo4j_connection_timeout_seconds,
            )
            # 启动期连通性探针：失败即关闭
            self._driver.verify_connectivity()
            logger.bind(uri=settings.neo4j_uri).info("neo4j_connected")
        except Exception as exc:  # noqa: BLE001 - 连接层吞错并包装
            self._driver = None
            raise GraphUnavailableError(f"Neo4j 连接失败: {exc}") from exc
        return self._driver

    def close(self) -> None:
        """关闭 driver（lifespan shutdown 调用）。"""
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:  # noqa: BLE001 - 关闭失败不影响主流程
                pass
            self._driver = None

    def _session(self):  # noqa: ANN202 - 第三方类型
        """按 ``settings.neo4j_database`` 打开会话（与导入脚本保持一致）。"""
        driver = self._ensure_driver()
        return driver.session(database=get_settings().neo4j_database)

    # ------------------------------------------------------------------ queries

    def health_check(self) -> bool:
        """探测 Neo4j 连通性；连接失败返回 ``False``（**不**抛）。"""
        try:
            self._ensure_driver()
            return True
        except GraphUnavailableError:
            return False

    def fetch_active_kg_version(self, *, scope: str | None = None) -> KgVersion:
        """读 Neo4j ``:KgVersion`` 返回**唯一** active 版本（ADR-0002 §3.2）。

        ``writing`` / ``failed`` 版本一律**不**返回，从源头杜绝脏读。
        """
        try:
            with self._session() as session:
                result = session.run(_QUERY_ACTIVE_KG_VERSION, scope=scope).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"读取 active kg_version 失败: {exc}") from exc

        version = result["version"] if result else None
        if not version:
            # 连接是通的，只是没有 active 版本 → 版本状态问题（路由层转 409），
            # **不是**基础设施故障（501）。见 NoActiveKgVersionError 文档。
            raise NoActiveKgVersionError(
                "Neo4j 中尚无 status='active' 的 KgVersion"
                f"（scope={scope!r}；请先执行 scripts/import_to_neo4j.py）"
            )
        return KgVersion(version=version, scope=result["scope"] or "global")

    def fetch_kg_version_status(self, version: str) -> str | None:
        """返回指定 ``kg_version`` 的 ``status``；节点不存在返回 ``None``。

        供路由层做 **409 ``KG_VERSION_NOT_ACTIVE``** 判定（ADR-0002 §3.2）：
        只要不是 ``active``（``writing`` / ``failed`` / ``superseded`` / 不存在）
        一律拒绝，**严禁静默降级**到最新 active 版本。

        ``Neo4j`` 不可用时抛 :class:`GraphUnavailableError`——这是**基础设施**
        故障而非「版本不合法」，调用方必须区分处理（转 501，**不可**转 409）。
        """
        if not version:
            return None

        try:
            with self._session() as session:
                result = session.run(_QUERY_KG_VERSION_STATUS, version=version).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"读取 kg_version 状态失败: version={version}: {exc}"
            ) from exc

        status = result["status"] if result else None
        return str(status) if status else None

    def fetch_all_subgraph(
        self,
        *,
        kg_version: str | None = None,
        org_id: UUID | None = None,
        node_limit: int = 500,
    ) -> tuple[list[GraphNode], list[GraphEdge], bool]:
        """取**全部**已导入实体子图，不依赖 PG ``document_id``。

        用于 ``bridge_web_demo`` 阶段六产物（``:Entity`` 实体图）的查询与可视化。
        若 ``kg_version`` 为 ``None``，自动取 :meth:`fetch_active_kg_version`
        （**始终**只查 active 版本，ADR-0002 §3.2）。

        :returns: ``(nodes, edges, truncated)``
        """
        if node_limit <= 0:
            raise ValueError("node_limit 必须为正整数")

        version = kg_version or self.fetch_active_kg_version().version

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_ALL_ENTITY_SUBGRAPH,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    node_limit=node_limit,
                ).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询全量实体子图失败: kg_version={version}: {exc}"
            ) from exc

        if result is None:
            return [], [], False

        total_nodes = int(result["total_nodes"] or 0)
        truncated = total_nodes > node_limit

        # 投影段（批次 D1 缺口 5）：Neo4j 原始数据可能与契约不符
        # （如 ``canonical_name`` 是对象、``confidence`` 越界、``properties`` 非 dict）。
        # 任何一条构造失败都抛 GraphUnavailableError（路由层 501），
        # **不可**静默跳过坏记录或返回空图——见模块 docstring 设计要点 5。
        projection_context = f"fetch_all_subgraph kg_version={version}"
        nodes = _project_nodes(
            (result["nodes"] or [])[:node_limit],
            kg_version=version,
            label="Entity",
            context=projection_context,
        )
        edges = _project_edges(result["edges"] or [], context=projection_context)

        return nodes, edges, truncated

    def fetch_document_subgraph(
        self,
        *,
        doc_id: UUID,
        kg_version: str,
        org_id: UUID | None = None,
        node_limit: int = 500,
    ) -> tuple[list[GraphNode], list[GraphEdge], bool]:
        """取文档子图（节点 + 关系），超限时裁剪并返回 ``truncated=True``。

        :returns: ``(nodes, edges, truncated)``
        """
        if node_limit <= 0:
            raise ValueError("node_limit 必须为正整数")

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_DOCUMENT_SUBGRAPH,
                    doc_id=str(doc_id),
                    kg_version=kg_version,
                    org_id=str(org_id) if org_id else None,
                    node_limit=node_limit,
                ).single()
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询文档子图失败: doc_id={doc_id}, kg_version={kg_version}: {exc}"
            ) from exc

        if result is None:
            return [], [], False

        # 投影段（批次 D1 缺口 5）：与 fetch_all_subgraph 同族问题——
        # 构造失败必须显式抛 GraphUnavailableError（501），不得静默降级为空结果。
        projection_context = (
            f"fetch_document_subgraph doc_id={doc_id}, kg_version={kg_version}"
        )
        truncated = False

        # Document 节点：Cypher 用 OPTIONAL MATCH，故文档节点可能缺失（None）
        document_record = result.get("d")
        nodes = _project_nodes(
            [document_record] if document_record is not None else [],
            kg_version=kg_version,
            label="Document",
            context=projection_context,
        )
        nodes += _project_nodes(
            result.get("chunks") or [],
            kg_version=kg_version,
            label="Chunk",
            context=projection_context,
        )
        nodes += _project_nodes(
            result.get("entities") or [],
            kg_version=kg_version,
            label="Entity",
            context=projection_context,
        )

        if len(nodes) > node_limit:
            nodes = nodes[:node_limit]
            truncated = True

        edges = _project_edges(result.get("mentions") or [], context=projection_context)

        return nodes, edges, truncated


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _to_node(record: Any, *, kg_version: str, label: str) -> GraphNode:
    """把 Neo4j Node 投影为契约层 :class:`GraphNode`。"""
    node_id = (
        str(record.get("id"))
        if record.get("id") is not None
        else str(record.id)
        if hasattr(record, "id")
        else ""
    )
    return GraphNode(
        id=node_id,
        label=label,  # type: ignore[arg-type]
        entity_type=record.get("type") if label == "Entity" else None,
        canonical_name=record.get("canonical_name"),
        confidence=_safe_float(record.get("confidence")),
        kg_version=kg_version,
    )


def _project_nodes(
    records: Any,
    *,
    kg_version: str,
    label: str,
    context: str,
) -> list[GraphNode]:
    """逐条把 Neo4j record 投影为 :class:`GraphNode`（批次 D1 缺口 5 兜底）。

    任一条构造失败（Pydantic ``ValidationError`` / 属性缺失 ``AttributeError`` 等）
    都**立即**包装为 :class:`GraphUnavailableError`，消息里带上
    「查询上下文 + 第几条 + 具体字段」，便于定位是哪条脏数据。
    刻意**不**跳过坏记录：图谱问答里「少一条数据」上层完全无法感知，
    只会得到一个看似正常的结论。
    """
    nodes: list[GraphNode] = []
    for index, record in enumerate(records):
        try:
            nodes.append(_to_node(record, kg_version=kg_version, label=label))
        except Exception as exc:  # noqa: BLE001 - 投影失败必须显式暴露，不可静默
            logger.bind(
                context=context, kind="node", label=label, record_index=index
            ).warning("graph_projection_failed")
            raise GraphUnavailableError(
                _projection_failure_message(
                    context=context, kind="node", label=label, index=index, exc=exc
                )
            ) from exc
    return nodes


def _project_edges(records: Any, *, context: str) -> list[GraphEdge]:
    """逐条把 Cypher 关系投影为 :class:`GraphEdge`（与 :func:`_project_nodes` 同策略）。"""
    edges: list[GraphEdge] = []
    for index, record in enumerate(records):
        try:
            edges.append(_edge_from_record(record))
        except Exception as exc:  # noqa: BLE001 - 同上：失败即 501，不静默丢弃
            logger.bind(context=context, kind="edge", record_index=index).warning(
                "graph_projection_failed"
            )
            raise GraphUnavailableError(
                _projection_failure_message(
                    context=context, kind="edge", label=None, index=index, exc=exc
                )
            ) from exc
    return edges


def _edge_from_record(record: Any) -> GraphEdge:
    """把 Cypher ``type(r)`` / 关系属性投影为契约层 :class:`GraphEdge`。

    ``type`` 经 :func:`_relation_type` 做契约投影；``properties`` **必须**是
    dict（Cypher 的 ``properties(r)`` 恒为 map），否则显式报错并指名 ``properties``
    字段，避免 ``AttributeError: 'list' object has no attribute 'items'`` 这类
    无法定位字段的报错。
    """
    raw_properties = record.get("properties") or {}
    if not isinstance(raw_properties, dict):
        raise TypeError(
            f"properties 字段应为 dict，实际为 {type(raw_properties).__name__}"
        )
    return GraphEdge(
        id=str(record.get("id", "")),
        type=_relation_type(record.get("type")),
        source=str(record.get("source", "")),
        target=str(record.get("target", "")),
        properties=_sanitize_properties(raw_properties),
    )


def _projection_failure_message(
    *,
    context: str,
    kind: str,
    label: str | None,
    index: int,
    exc: Exception,
) -> str:
    """拼装「图谱数据与契约不符」的异常消息（含字段级明细，便于排查脏数据）。"""
    where = f"{context}, {kind}[{index}]"
    if label:
        where += f" label={label}"
    return f"图谱数据与契约不符（{where}）: {_describe_projection_error(exc)}"


def _describe_projection_error(exc: Exception) -> str:
    """把 Pydantic ``ValidationError`` 压成「字段: 原因」串；其它异常退化为「类型: 文本」。

    只取前 3 条错误，避免一条脏记录带出一大段消息把日志冲爆。
    """
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
        except Exception:  # noqa: BLE001 - 描述失败不影响上抛语义
            items = None
        if items:
            details = []
            for item in items[:3]:
                location = ".".join(str(part) for part in item.get("loc") or ())
                details.append(f"{location or '<root>'}: {item.get('msg')}")
            return "; ".join(details)
    return f"{type(exc).__name__}: {exc}"


def _relation_type(raw: Any) -> RelationType:
    """把 Cypher ``type(r)`` 的字符串映射为契约 ``RelationType`` 枚举。

    **契约对齐说明（Sprint 4.10.0.B）**：``RelationType`` 已扩展
    ``HAS_FINANCIAL_INDICATOR`` / ``OPERATES_SEGMENT`` / ``RELATED`` 三个
    桥梁抽取的实体↔实体类关系（与 ``scripts/import_to_neo4j.py`` 的
    ``RELATION_TOKEN_MAP`` 白名单 token 逐字一致），桥梁专有类型**原样直通**；
    仅**未知类型**兜底投影为 ``MENTIONS``，真实关系名保留在
    ``properties["relation_name"]``（防未来桥梁新类型再次制造契约缺口）。
    """
    contract_enum = {
        "HAS_CHUNK",
        "MENTIONS",
        "SUPPORTED_BY",
        "AFFILIATED_WITH",
        "SUPPLIES_TO",
        "PARTY_TO",
        "HAS_FINANCIAL_INDICATOR",
        "OPERATES_SEGMENT",
        "RELATED",
    }

    raw_name = str(raw)
    if raw_name in contract_enum:
        return raw_name  # type: ignore[return-value]
    # 未知类型兜底投影：真实关系名由 properties["relation_name"] 承载
    return "MENTIONS"  # type: ignore[return-value]


def _sanitize_properties(props: dict[str, Any]) -> dict[str, Any]:
    """剥离 Neo4j Node / Relationship 自带的系统属性。"""
    forbidden = {"kg_version", "pii_flags"}
    return {key: value for key, value in props.items() if key not in forbidden}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "GraphService",
    "GraphUnavailableError",
    "KgVersion",
    "NoActiveKgVersionError",
]
