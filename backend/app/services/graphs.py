"""图谱服务：封装 Neo4j 连接与 Cypher 查询（ADR-0002 / M2 §5.4）。

公开面：
- :class:`GraphService`：通过 ``GraphService.instance()`` 取单例；
- :class:`GraphUnavailableError`：连接失败 / 查询失败时抛，路由层捕获后转
  ``501 NOT_IMPLEMENTED``（阶段九契约未实装）；
- :func:`fetch_active_kg_version` / :func:`fetch_document_subgraph`：业务层常用
  的两条 Cypher 入口。

设计要点：
1. **懒加载 driver**：模块导入时不连接 Neo4j；第一次调用 ``instance()`` 时
   才尝试建连接，避免 pytest / 启动失败被外部依赖绑架。
2. **kg_version 强制 active**：所有 Cypher 都带 ``WHERE n.kg_version = $kg_version``
   且 ``kg_version`` 由 :func:`fetch_active_kg_version` 给出，**严禁**调用方传入
   ``writing`` / ``failed`` / ``superseded`` 版本。
3. **MERGE 幂等**：写入路径使用 ``MERGE``，以 ``(id, kg_version)`` 为幂等键
   （ADR-0002 §3.3），支持 Saga 重放。
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


@dataclass(frozen=True, slots=True)
class KgVersion:
    """当前 active ``kg_version`` 投影。"""

    version: str
    scope: str  # "doc:<uuid>" 或 "global"


#: Cypher 查询：当前 active kg_version。
#: 阶段九骨架：从 Neo4j 取最近一次写入的 ``kg_version``（视为 active）。
#: Sprint 3 后段接入 ``kg_versions`` ORM 后改为 PG 真源查询，
#: 并按 ADR-0002 §3.2 仅返回 ``status = 'active'``。
_QUERY_ACTIVE_KG_VERSION = """
OPTIONAL MATCH (n:Document)
WHERE n.kg_version IS NOT NULL
RETURN n.kg_version AS version
ORDER BY n.kg_version DESC
LIMIT 1
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

    _instance: "GraphService | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._driver = None

    @classmethod
    def instance(cls) -> "GraphService":
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

    # ------------------------------------------------------------------ queries

    def health_check(self) -> bool:
        """探测 Neo4j 连通性；连接失败返回 ``False``（**不**抛）。"""
        try:
            self._ensure_driver()
            return True
        except GraphUnavailableError:
            return False

    def fetch_active_kg_version(self) -> KgVersion:
        """读 Neo4j 返回**唯一** active 版本（骨架实现）。"""
        self._ensure_driver()
        try:
            with self._driver.session() as session:  # type: ignore[union-attr]
                result = session.run(_QUERY_ACTIVE_KG_VERSION).single()
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"读取 active kg_version 失败: {exc}") from exc

        version = result["version"] if result else None
        if not version:
            raise GraphUnavailableError("Neo4j 中尚无任何 kg_version（未写入数据）")
        return KgVersion(version=version, scope="global")

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

        self._ensure_driver()
        try:
            with self._driver.session() as session:  # type: ignore[union-attr]
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

        nodes: list[GraphNode] = []
        truncated = False

        # Document 节点
        document_record = result.get("d")
        if document_record is not None:
            nodes.append(_to_node(document_record, kg_version=kg_version, label="Document"))

        for record in result.get("chunks") or []:
            nodes.append(_to_node(record, kg_version=kg_version, label="Chunk"))
        for record in result.get("entities") or []:
            nodes.append(_to_node(record, kg_version=kg_version, label="Entity"))

        if len(nodes) > node_limit:
            nodes = nodes[:node_limit]
            truncated = True

        edges: list[GraphEdge] = []
        for record in result.get("mentions") or []:
            edges.append(
                GraphEdge(
                    id=str(record.get("id", "")),
                    type=_relation_type(record.get("type")),
                    source=str(record.get("source", "")),
                    target=str(record.get("target", "")),
                    properties=_sanitize_properties(record.get("properties") or {}),
                )
            )

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


def _relation_type(raw: Any) -> RelationType:
    """把 Cypher ``type(r)`` 的字符串映射为契约枚举，未知则降级为 ``HAS_CHUNK``。"""
    mapping = {
        "HAS_CHUNK": "HAS_CHUNK",
        "MENTIONS": "MENTIONS",
        "SUPPORTED_BY": "SUPPORTED_BY",
        "AFFILIATED_WITH": "AFFILIATED_WITH",
        "SUPPLIES_TO": "SUPPLIES_TO",
        "PARTY_TO": "PARTY_TO",
    }
    return mapping.get(str(raw), "HAS_CHUNK")  # type: ignore[return-value]


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
]
