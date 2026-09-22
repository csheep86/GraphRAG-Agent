"""KG 构建器（ADR-0002 §3.1 三段式写入 Neo4j，Sprint 5 批次 B）。

公开面：
- :class:`KgBuilder`：抽象协议（``Protocol``）——调用方依赖协议而非实现，便于测试
  注入与未来扩展（接缝 3 模型层内档，**不**进 ``check_seams`` 登记：单实现不构成接缝）；
- :class:`ThreeStageKgBuilder`：唯一实现，对齐 ``scripts/import_to_neo4j.py`` 实战口径。

三段式契约：
1. **stage-1 schema MERGE**——``(:KgVersionMirror {version, org_id, status, trace_id})``
   与所有节点 / 关系类型索引约束（idempotent）；
2. **stage-2 batch LOAD**——``UNWIND $batch AS e MERGE (:Entity {...})`` 分批写入实体；
3. **stage-3 cross-batch links**——``UNWIND $batch AS r MATCH (a) MATCH (b) MERGE (a)-[rel]->(b)``
   分批写入关系。

设计边界：
- **不**做内层事务——Neo4j 事务 + PG 事务分离（ADR-0002 §3.1 跨库一致性靠
  ``kg_versions`` 状态机 + 回填校验）；
- Neo4j driver **复用** :class:`GraphService` 懒加载的连接（``GraphService.instance()._ensure_driver()``），
  **不**自建驱动；
- ``kg_build_batch_size`` 上限保护 stage-2 / stage-3 内存峰值。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from app.core.config import get_settings
from app.services.graphs import GraphService, GraphUnavailableError


@dataclass(frozen=True, slots=True)
class BuildStats:
    """KG 构建统计。"""

    entity_count: int
    relation_count: int
    batch_count: int


@dataclass(frozen=True, slots=True)
class KgBuildRequest:
    """一次三段式构建的输入。"""

    org_id: uuid.UUID
    version: str
    entities: Sequence[dict[str, Any]]
    relations: Sequence[dict[str, Any]]
    trace_id: uuid.UUID


class KgBuilder(Protocol):
    """KG 构建器协议。"""

    def build(self, request: KgBuildRequest) -> BuildStats:
        """执行三段式写入，返回统计。"""
        ...


# ------------------------------------------------------------------------------
# Cypher 三段式（与 import_to_neo4j.py 实战口径对齐）
# ------------------------------------------------------------------------------

#: stage-1a：MERGE :KgVersionMirror（冗余镜像，PG ``kg_versions`` 为真源）
_CYPHER_STAGE1A_VERSION_MIRROR = """
MERGE (v:KgVersionMirror {version: $version, org_id: $org_id})
ON CREATE SET v.status = $status,
              v.trace_id = $trace_id,
              v.created_at = datetime()
ON MATCH SET v.status = $status,
             v.trace_id = $trace_id
RETURN v
"""

#: stage-1b：实体类型索引约束（幂等）
_CYPHER_STAGE1B_INDEXES = (
    "CREATE CONSTRAINT entity_id_version IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE (n.id, n.kg_version) IS NODE KEY",
    "CREATE INDEX entity_org_id IF NOT EXISTS FOR (n:Entity) ON (n.org_id)",
)

#: stage-2：单批 LOAD entities
_CYPHER_STAGE2_LOAD_ENTITIES = """
UNWIND $batch AS e
MERGE (n:Entity {id: e.id, kg_version: $kg_version})
ON CREATE SET n.canonical_name = e.canonical_name,
              n.entity_type = e.entity_type,
              n.mention = e.mention,
              n.confidence = e.confidence,
              n.org_id = $org_id,
              n.trace_id = $trace_id
ON MATCH SET n.canonical_name = e.canonical_name,
             n.entity_type = e.entity_type,
             n.mention = e.mention,
             n.confidence = e.confidence,
             n.org_id = $org_id
"""

#: stage-3：单批 MATCH-MERGE relations
_CYPHER_STAGE3_LOAD_RELATIONS = """
UNWIND $batch AS r
MATCH (a:Entity {id: r.source_entity_id, kg_version: $kg_version})
MATCH (b:Entity {id: r.target_entity_id, kg_version: $kg_version})
MERGE (a)-[rel:RELATION {id: r.id, kg_version: $kg_version}]->(b)
ON CREATE SET rel.relation_type = r.relation_type,
              rel.evidence = r.evidence,
              rel.confidence = r.confidence,
              rel.org_id = $org_id,
              rel.trace_id = $trace_id
"""


def _chunks_by_batches(
    items: Sequence[Any], batch_size: int
) -> Iterator[Sequence[Any]]:
    """按 ``batch_size`` 切片（保护 Neo4j 内存峰值）。"""
    if batch_size <= 0:
        raise ValueError(f"batch_size 必须为正整数（实际={batch_size}）")
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


class ThreeStageKgBuilder:
    """ADR-0002 三段式 Neo4j 写入器。"""

    def __init__(
        self,
        *,
        graph_service: GraphService | None = None,
        batch_size: int | None = None,
        version_strategy: str | None = None,
        session_factory: Any = None,
    ) -> None:
        """``session_factory`` 留给测试注入（默认 None ⇒ 用真实 ``GraphService.instance()``）。"""
        settings = get_settings()
        if version_strategy is None:
            version_strategy = settings.kg_version_strategy
        if version_strategy != "per_org":
            # 与 llm_provider / extraction_provider 同策略：未知档显式报错
            raise ValueError(
                f"未知 kg_version_strategy={version_strategy!r}（当前仅支持 'per_org'）"
            )

        self._graph_service = graph_service or GraphService.instance()
        self._batch_size = (
            batch_size if batch_size is not None else settings.kg_build_batch_size
        )
        self._session_factory = session_factory

    # -------------------------------------------------------------- 主入口

    def build(self, request: KgBuildRequest) -> BuildStats:
        """按 stage-1 / stage-2 / stage-3 顺序写入；任一段失败即抛 GraphUnavailableError。"""
        if not request.entities and not request.relations:
            return BuildStats(entity_count=0, relation_count=0, batch_count=0)

        self._stage1(
            version=request.version,
            org_id=request.org_id,
            trace_id=request.trace_id,
        )
        entity_count = self._stage2(request)
        relation_count = self._stage3(request)

        batch_count = sum(
            1
            for _ in (
                list(_chunks_by_batches(request.entities, self._batch_size))
                + list(_chunks_by_batches(request.relations, self._batch_size))
            )
        )

        logger.bind(
            trace_id=str(request.trace_id),
            org_id=str(request.org_id),
            version=request.version,
            entity_count=entity_count,
            relation_count=relation_count,
        ).info("kg_build_done")

        return BuildStats(
            entity_count=entity_count,
            relation_count=relation_count,
            batch_count=batch_count,
        )

    # -------------------------------------------------------------- 阶段实现

    def _stage1(self, *, version: str, org_id: uuid.UUID, trace_id: uuid.UUID) -> None:
        """stage-1：MERGE :KgVersionMirror + 确保索引约束。"""
        try:
            self._run(
                _CYPHER_STAGE1A_VERSION_MIRROR,
                {
                    "version": version,
                    "org_id": str(org_id),
                    "status": "building",
                    "trace_id": str(trace_id),
                },
            )
            for cypher in _CYPHER_STAGE1B_INDEXES:
                self._run(cypher, {})
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-1 失败: {exc}") from exc

    def _stage2(self, request: KgBuildRequest) -> int:
        """stage-2：分批 LOAD entities；返回写入条数。"""
        if not request.entities:
            return 0
        try:
            written = 0
            for batch in _chunks_by_batches(request.entities, self._batch_size):
                self._run(
                    _CYPHER_STAGE2_LOAD_ENTITIES,
                    {
                        "batch": list(batch),
                        "kg_version": request.version,
                        "org_id": str(request.org_id),
                        "trace_id": str(request.trace_id),
                    },
                )
                written += len(batch)
            return written
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-2 失败: {exc}") from exc

    def _stage3(self, request: KgBuildRequest) -> int:
        """stage-3：分批 MATCH-MERGE relations；返回写入条数。"""
        if not request.relations:
            return 0
        try:
            written = 0
            for batch in _chunks_by_batches(request.relations, self._batch_size):
                self._run(
                    _CYPHER_STAGE3_LOAD_RELATIONS,
                    {
                        "batch": list(batch),
                        "kg_version": request.version,
                        "org_id": str(request.org_id),
                        "trace_id": str(request.trace_id),
                    },
                )
                written += len(batch)
            return written
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-3 失败: {exc}") from exc

    # -------------------------------------------------------------- 内部

    def _run(self, cypher: str, params: dict[str, Any]) -> Any:  # noqa: ANN401
        """跑一段 Cypher；测试可通过 ``session_factory`` 注入桩。"""
        if self._session_factory is not None:
            with self._session_factory() as session:
                return session.run(cypher, **params).data()
        # 生产路径：复用 GraphService 懒加载的 driver
        with self._graph_service._session() as session:  # type: ignore[attr-defined]
            return session.run(cypher, **params).data()


__all__ = ["BuildStats", "KgBuildRequest", "KgBuilder", "ThreeStageKgBuilder"]
