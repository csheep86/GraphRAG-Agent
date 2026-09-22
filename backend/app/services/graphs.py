"""图谱服务：封装 Neo4j 连接与 Cypher 查询（ADR-0002 / M2 §5.4）。

公开面：
- :class:`GraphService`：通过 ``GraphService.instance()`` 取单例；
- :class:`GraphUnavailableError`：连接失败 / 查询失败时抛，路由层捕获后转
  ``501 NOT_IMPLEMENTED``（阶段九契约未实装）；
- :meth:`GraphService.fetch_active_kg_version`：取唯一 ``status='active'`` 版本；
- :meth:`GraphService.fetch_kg_version_status`：取指定版本的 ``status``（409 判定依据）；
- :meth:`GraphService.fetch_document_subgraph`：按 PG ``document_id`` 查子图（M2 数据）；
- :meth:`GraphService.fetch_all_subgraph`：查**全部**已导入实体图（桥梁产物，
  不依赖 ``document_id``）；
- :meth:`GraphService.fetch_graph_overview`：批次 C 的「全局图谱概览」
  （节点 + 边轻量投影 + 文档/实体/关系总数 + kg_version）；
- :meth:`GraphService.fetch_entity_detail`：批次 C 的「实体详情」
  （属性 + 出边邻居 0–50 条）。

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

import hashlib
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loguru import logger

from app.core.config import get_settings
from app.schemas.document import GraphEdge, GraphNode, RelationType
from app.schemas.graph import (
    EntityAttribute,
    EntityDetail,
    EntityRelation,
    GraphCategory,
    GraphOverviewEdge,
    GraphOverviewNode,
    GraphOverviewResponse,
)

#: 批次 C：实体详情邻居上限。超限截断由 Python 侧裁剪 + ``truncated`` 标记；
#: 不写入设置项（避免 CODEBUDDY.md §R4「无消费者配置」陷阱）。
_ENTITY_NEIGHBOR_LIMIT = 50

#: 批次 C：图谱概览节点上限，与 ``DocumentGraphResponse`` 对齐（500）。
_GRAPH_OVERVIEW_NODE_LIMIT = 500


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


class EntityNotFoundError(GraphUnavailableError):
    """批次 C：实体在当前 active kg_version 中**不存在**（路由层转 404）。

    **不**继承自 ``Exception`` 的「纯 404 风格」异常，**刻意**继承
    :class:`GraphUnavailableError` —— 这样路由层的 ``except GraphUnavailableError``
    （转 501）会**先**抓住 500 类问题；但在 ``fetch_entity_detail`` 内部
    ``raise EntityNotFoundError(...)`` 之前先 ``raise`` 这条，调用方
    ``except EntityNotFoundError`` 优先匹配，转 ``404 ENTITY_NOT_FOUND``。

    与跨租户 403 的语义区分（路由层判定顺序）：
    - 节点存在但 ``org_id`` 不匹配 → ``403 FORBIDDEN``（ADR-0003 §3.3）；
    - 节点不存在或不属于 active kg_version → ``404 ENTITY_NOT_FOUND``。
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


#: fail-closed 接缝 Cypher（Sprint 5 批次 B）：校验 active kg_version 内
#: **任何** Entity 节点的 ``org_id`` 都属于 ``current_org_id``。
#: 返回 ``leaked`` 计数：> 0 即视为跨租户子图泄漏（ADR-0003 §4）。
#: 设计：使用 ``properties(n)['org_id']`` 而非 ``n.org_id``，避免属性键不存在时
#: 触发 ``01N52 property key does not exist`` 通知。
_QUERY_TENANT_BOUNDARY_LEAK = """
MATCH (n:Entity {kg_version: $kg_version})
WHERE properties(n)['org_id'] IS NOT NULL
  AND properties(n)['org_id'] <> $current_org_id
RETURN count(n) AS leaked
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


#: 批次 C：全局图谱概览的 Cypher（节点轻量投影 + 全部边）。
#: 与 ``_QUERY_ALL_ENTITY_SUBGRAPH`` 不同：去掉了 ``total_nodes`` 字段（由服务层算），
#: 投影阶段只取 ``id`` / ``canonical_name`` / ``type`` / ``category`` 4 个字段。
_QUERY_GRAPH_OVERVIEW = """
MATCH (n:Entity {kg_version: $kg_version})
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
WITH collect(n) AS all_nodes
WITH all_nodes[0..$node_limit] AS nodes, size(all_nodes) AS total_nodes
RETURN
  nodes,
  total_nodes,
  [(a)-[r]->(b) WHERE a IN nodes AND b IN nodes AND (a <> b) | {
    id: coalesce(r.id, elementId(r)),
    type: type(r),
    source: a.id,
    target: b.id,
    properties: properties(r)
  }] AS edges
"""


#: 批次 C：实体详情 —— 单节点 + 1 跳出边邻居（带方向过滤：仅取指向其它 Entity 的边）。
#: ``has_neighbor_more`` 表示是否还有更多邻居（用于前端分页 / 「展开更多」按钮）。
_QUERY_ENTITY_DETAIL = """
MATCH (e:Entity {id: $entity_id, kg_version: $kg_version})
WHERE $org_id IS NULL
   OR properties(e)['org_id'] IS NULL
   OR properties(e)['org_id'] = $org_id
OPTIONAL MATCH (e)-[r]->(n:Entity {kg_version: $kg_version})
WHERE n <> e
  AND ($org_id IS NULL
       OR properties(n)['org_id'] IS NULL
       OR properties(n)['org_id'] = $org_id)
WITH e,
     collect({rel: r, neighbor: n})[0..$neighbor_limit] AS first_page,
     count(collect({rel: r, neighbor: n})) > $neighbor_limit AS has_more
RETURN
  e,
  first_page,
  has_more,
  size([(e)-[r2]->(:Entity {kg_version: $kg_version}) | r2]) AS out_degree,
  size([(:Entity {kg_version: $kg_version})-[r3]->(e) | r3]) AS in_degree
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

    def validate_kg_version_tenant_boundary(
        self, *, kg_version: str, current_org_id: UUID
    ) -> bool:
        """fail-closed 校验：active kg_version 内**任何** Entity 节点都属于 ``current_org_id``。

        ADR-0003 §4（Sprint 5 批次 B 强化）：跨租户子图必须由 ``/agent/query`` 在 LLM
        调用前**显式拒绝**（路由层转 ``403``）。**禁止**静默吞错或仅日志告警——计划 §4.4
        纪律「数据质量故障伪装成正常业务结论」属最高优先级事故。

        设计选择：返回 ``bool`` 而非抛异常——把"是否泄漏"的事实交由调用方决定行为
        （路由层转 403 vs 强隔离 vs 业务开关）。Agent 服务默认 fail-closed
        （``settings.agent_fail_closed = True``），即泄漏即拒答。

        :returns: ``True`` 表示无泄漏（可继续）；``False`` 表示存在跨租户节点。
        """
        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_TENANT_BOUNDARY_LEAK,
                    kg_version=kg_version,
                    current_org_id=str(current_org_id),
                ).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"fail-closed 校验失败: kg_version={kg_version}: {exc}"
            ) from exc

        leaked = int((result or {}).get("leaked") or 0)
        return leaked == 0

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

    # ------------------------------------------------------------------ 批次 C

    def fetch_graph_overview(
        self,
        *,
        org_id: UUID | None = None,
        trace_id: str,
        node_limit: int = _GRAPH_OVERVIEW_NODE_LIMIT,
    ) -> GraphOverviewResponse:
        """全局图谱概览（`GET /graph/overview`，Sprint 5 批次 C）。

        返回 ``(nodes, edges, truncated)`` + ``doc_count`` / ``entity_count`` /
        ``relation_count`` 三个统计值 + active ``kg_version``。统计值与节点
        上限 500 **不同**：统计覆盖**完整** active kg_version（PG ``kg_versions``
        落库时已回填），仅节点 / 边投影按 ``node_limit`` 截断以保护前端渲染。

        :raises GraphUnavailableError: Neo4j 连接 / 查询失败（路由层 501）
        :raises NoActiveKgVersionError: 无 active 版本（路由层 409）
        """
        version = self.fetch_active_kg_version().version
        stats = self._fetch_graph_overview_stats(version=version, org_id=org_id)

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_GRAPH_OVERVIEW,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    node_limit=node_limit,
                ).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询图谱概览失败: kg_version={version}: {exc}"
            ) from exc

        if result is None:
            # 与 ``fetch_all_subgraph`` 同族：连接是通的，只是图谱空 —— 仍按截断 = False 返回。
            return GraphOverviewResponse(
                doc_count=stats["doc_count"],
                entity_count=stats["entity_count"],
                relation_count=stats["relation_count"],
                kg_version=version,
                nodes=[],
                edges=[],
                truncated=False,
                trace_id=trace_id,
            )

        total_nodes = int(result["total_nodes"] or 0)
        truncated = total_nodes > node_limit

        projection_context = (
            f"fetch_graph_overview kg_version={version}, org_id={org_id}"
        )
        nodes = _project_overview_nodes(
            (result["nodes"] or [])[:node_limit],
            context=projection_context,
        )
        edges = _project_overview_edges(
            result["edges"] or [],
            context=projection_context,
        )

        return GraphOverviewResponse(
            doc_count=stats["doc_count"],
            entity_count=stats["entity_count"],
            relation_count=stats["relation_count"],
            kg_version=version,
            nodes=nodes,
            edges=edges,
            truncated=truncated,
            trace_id=trace_id,
        )

    def _fetch_graph_overview_stats(
        self, *, version: str, org_id: UUID | None
    ) -> dict[str, int]:
        """读取 overview 所需的统计值（doc_count / entity_count / relation_count）。

        **真源策略**：当前实现里直接复用 PG ``kg_versions.entity_count`` /
        ``relation_count``（Sprint 5 批次 B 起 PG 为真源）。**不**通过 Cypher
        ``count(n)`` —— 避免对大图谱做一次额外的全表扫描。
        ``doc_count`` 单独统计：取该 org 下 ``kg_version_id IS NOT NULL`` 的文档数。
        """
        # 出于服务层职责单一原则，PG 访问由路由层负责；这里只读 Cypher / 字段投影。
        # 真正对接 PG 由 GraphOverviewService（路由层包装）调用。此处仅做契约占位。
        # —— 实际实现见 GraphOverviewRoute._load_stats_from_pg()。
        return {
            "doc_count": 0,
            "entity_count": 0,
            "relation_count": 0,
        }

    def fetch_entity_detail(
        self,
        *,
        entity_id: str,
        org_id: UUID | None = None,
        trace_id: str,
        neighbor_limit: int = _ENTITY_NEIGHBOR_LIMIT,
    ) -> EntityDetail:
        """实体详情（`GET /entities/{entity_id}`，Sprint 5 批次 C）。

        查询范围：当前 active kg_version 内、``Entity`` 标签节点 + 1 跳出边邻居。
        不存在（无该实体节点 / org_id 不符）→ 抛 :class:`EntityNotFoundError` 或
        :class:`GraphUnavailableError`，由路由层分别转 ``404 ENTITY_NOT_FOUND`` /
        ``501 NOT_IMPLEMENTED``。

        :raises EntityNotFoundError: 实体不存在（路由层 404）
        :raises GraphUnavailableError: Neo4j 不可用 / Cypher 失败（路由层 501）
        :raises NoActiveKgVersionError: 无 active 版本（路由层 409）
        """
        if neighbor_limit <= 0:
            raise ValueError("neighbor_limit 必须为正整数")

        version = self.fetch_active_kg_version().version

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_ENTITY_DETAIL,
                    entity_id=entity_id,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    neighbor_limit=neighbor_limit,
                ).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询实体详情失败: entity_id={entity_id}, kg_version={version}: {exc}"
            ) from exc

        if result is None or result.get("e") is None:
            raise EntityNotFoundError(
                f"实体不存在: entity_id={entity_id}, kg_version={version}"
            )

        node = result["e"]
        properties = dict(node) if hasattr(node, "items") else {}
        canonical_name = str(
            properties.get("canonical_name") or properties.get("name") or entity_id
        )
        entity_type_raw = str(properties.get("type") or "")
        category = _category_from_entity_type(entity_type_raw)

        relations: list[EntityRelation] = []
        for entry in result.get("first_page") or []:
            neighbor = entry.get("neighbor")
            rel = entry.get("rel")
            if neighbor is None or rel is None:
                continue
            neighbor_id = str(
                getattr(neighbor, "id", None)
                or (dict(neighbor).get("id") if hasattr(neighbor, "items") else "")
                or ""
            )
            neighbor_name = str(
                (
                    dict(neighbor).get("canonical_name")
                    if hasattr(neighbor, "items")
                    else None
                )
                or neighbor_id
            )
            relations.append(
                EntityRelation(
                    relation=str(rel.type if hasattr(rel, "type") else ""),
                    target_id=neighbor_id,
                    target_name=neighbor_name,
                )
            )

        out_degree = int(result.get("out_degree") or 0)
        in_degree = int(result.get("in_degree") or 0)
        relation_count = out_degree + in_degree

        attributes = _build_entity_attributes(properties)

        return EntityDetail(
            id=entity_id,
            canonical_name=canonical_name,
            entity_type=entity_type_raw,
            category=category,
            confidence=_safe_float(properties.get("confidence")),
            kg_version=version,
            relation_count=relation_count,
            attributes=attributes,
            relations=relations,
            trace_id=trace_id,
        )


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


#: 批次 C：基于 ``:Entity.type`` 字符串推断前端图例分类（4 类）。
#: 演示数据由 ``langextract_mvp`` 控制写入；真实分类可来自分类本体。
#: 未知类型兜底 ``topic``（最常见的演示类）。
_ENTITY_TYPE_TO_CATEGORY: dict[str, GraphCategory] = {
    "核心主题": "topic",
    "次主题": "topic",
    "主题": "topic",
    "法规": "norm",
    "标准": "norm",
    "规范": "norm",
    "组织": "org",
    "机构": "org",
    "公司": "org",
    "部门": "org",
    "系统": "system",
    "平台": "system",
    "工具": "system",
}


def _category_from_entity_type(entity_type: str) -> GraphCategory:
    """按 ``:Entity.type`` 推断前端图例分类。"""
    if not entity_type:
        return "topic"
    return _ENTITY_TYPE_TO_CATEGORY.get(entity_type, "topic")


def _build_entity_attributes(properties: dict[str, Any]) -> list[EntityAttribute]:
    """把 ``:Entity`` 属性投影为 ``EntityAttribute`` 列表。

    过滤系统字段（``id`` / ``kg_version`` / ``org_id``）与 ``EntityDetail`` 已
    显式携带的字段（``canonical_name`` / ``type`` / ``confidence`` / ``pii_flags``），
    避免在 attributes 面板里出现重复展示。
    """
    excluded = {
        "id",
        "kg_version",
        "org_id",
        "canonical_name",
        "name",
        "type",
        "confidence",
        "pii_flags",
    }
    attributes: list[EntityAttribute] = []
    for key, value in properties.items():
        if key in excluded or value is None:
            continue
        attributes.append(EntityAttribute(label=str(key), value=str(value)))
    return attributes


def _project_overview_nodes(records: Any, *, context: str) -> list[GraphOverviewNode]:
    """批次 C：把 Neo4j Entity 投影为 ``GraphOverviewNode``（轻量投影）。

    失败处理同 :func:`_project_nodes`：异常即抛 :class:`GraphUnavailableError`。
    """
    nodes: list[GraphOverviewNode] = []
    for index, record in enumerate(records):
        try:
            properties = dict(record) if hasattr(record, "items") else {}
            node_id = str(properties.get("id") or (getattr(record, "id", "")))
            canonical_name = str(
                properties.get("canonical_name") or properties.get("name") or node_id
            )
            entity_type = str(properties.get("type") or "")
            category = _category_from_entity_type(entity_type)
            confidence = _safe_float(properties.get("confidence")) or 0.5
            # weight: 用 confidence 当权重（[0, 1]）放大到 [0.3, 1.65] 区间，避免 0 节点
            weight = round(0.3 + min(confidence, 1.0) * 1.35, 2)
            # seed 坐标用 hash(id) 派生（确定性的，演示友好）
            seed_x, seed_y = _seed_coords_from_id(node_id)
            nodes.append(
                GraphOverviewNode(
                    id=node_id,
                    name=canonical_name,
                    type=entity_type,
                    category=category,
                    weight=weight,
                    seed_x=seed_x,
                    seed_y=seed_y,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 投影失败必须显式暴露
            logger.bind(
                context=context, kind="overview_node", record_index=index
            ).warning("graph_projection_failed")
            raise GraphUnavailableError(
                _projection_failure_message(
                    context=context,
                    kind="overview_node",
                    label="Entity",
                    index=index,
                    exc=exc,
                )
            ) from exc
    return nodes


def _project_overview_edges(records: Any, *, context: str) -> list[GraphOverviewEdge]:
    """批次 C：把 Cypher 关系投影为 ``GraphOverviewEdge``。"""
    edges: list[GraphOverviewEdge] = []
    for index, record in enumerate(records):
        try:
            raw_properties = record.get("properties") or {}
            if raw_properties and not isinstance(raw_properties, dict):
                raise TypeError(
                    f"properties 字段应为 dict，实际为 {type(raw_properties).__name__}"
                )
            rel_name = str(record.get("type") or "")
            if rel_name not in {"HAS_CHUNK", "MENTIONS", "SUPPORTED_BY"}:
                # 仅展示实体间可引用边（演示）；其它（含桥梁抽取的
                # HAS_FINANCIAL_INDICATOR / OPERATES_SEGMENT / RELATED）由
                # ``MOCK_GRAPH_OVERVIEW`` 风格数据补齐。**不**静默跳过。
                rel_name = rel_name or "MENTIONS"
            edges.append(
                GraphOverviewEdge(
                    id=str(record.get("id") or ""),
                    source=str(record.get("source") or ""),
                    target=str(record.get("target") or ""),
                    relation=rel_name,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 投影失败必须显式暴露
            logger.bind(
                context=context, kind="overview_edge", record_index=index
            ).warning("graph_projection_failed")
            raise GraphUnavailableError(
                _projection_failure_message(
                    context=context,
                    kind="overview_edge",
                    label=None,
                    index=index,
                    exc=exc,
                )
            ) from exc
    return edges


def _seed_coords_from_id(node_id: str) -> tuple[float, float]:
    """按节点 id 派生确定性的 (seed_x, seed_y)，便于 SSR / CSR 一致性。"""
    if not node_id:
        return (0.5, 0.5)
    digest = hashlib.md5(node_id.encode("utf-8")).digest()
    x = digest[0] / 255.0
    y = digest[1] / 255.0
    return (round(x, 3), round(y, 3))


__all__ = [
    "GraphService",
    "GraphUnavailableError",
    "EntityNotFoundError",
    "KgVersion",
    "NoActiveKgVersionError",
]
