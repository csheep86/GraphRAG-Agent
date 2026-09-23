"""KG 构建器（ADR-0002 §3.1 三段式写入 Neo4j，Sprint 5 批次 B）。

公开面：
- :class:`KgBuilder`：抽象协议（``Protocol``）——调用方依赖协议而非实现，便于测试
  注入与未来扩展（接缝 3 模型层内档，**不**进 ``check_seams`` 登记：单实现不构成接缝）；
- :class:`ThreeStageKgBuilder`：唯一实现，对齐 ``scripts/import_to_neo4j.py`` 实战口径。

三段式契约（Sprint 6 批次 A-3 扩为五段式，stage-1 / 2 / 3 语义**不变**）：
1. **stage-1 schema MERGE**——``(:KgVersionMirror {version, org_id, status, trace_id})``
   与所有节点 / 关系类型索引约束（idempotent）；
2. **stage-2 batch LOAD**——``UNWIND $batch AS e MERGE (:Entity {...})`` 分批写入实体；
3. **stage-3 cross-batch links**——``UNWIND $batch AS r MATCH (a) MATCH (b) MERGE (a)-[rel]->(b)``
   分批写入关系。

Sprint 6 批次 A-3 新增的证据层（**均为可跳过段**：无 ``document`` / ``chunks`` 时
行为与 v1.1.0 完全一致）：

1.5. **stage-1.5 document MERGE**——``MERGE (:Document {id, kg_version})``，
     ``acl_scope`` 从 ``documents.acl_scope`` 继承；
2.5. **stage-2.5 chunk LOAD**——``UNWIND $batch AS c MERGE (:Chunk {id, kg_version})``
     分批写入证据节点（``char_start`` / ``char_end`` / ``page`` / ``text``）；
4.   **stage-4 evidence links**——``(:Document)-[:HAS_CHUNK]->(:Chunk)`` 与
     ``(:Chunk)-[:MENTIONS]->(:Entity)``（实体按字符区间归属，见
     :func:`_assign_entities_to_chunks`）。读侧 ``graphs.py::_QUERY_DOCUMENT_SUBGRAPH``
     自 Sprint 4 起就是按这条链路查的——**读侧等写侧两年，本批次补齐**。

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
    #: Sprint 6 批次 A-3：写入的 ``:Chunk`` 节点数（无 Chunk 层时为 0）
    chunk_count: int = 0
    #: Sprint 6 批次 A-3：写入的 ``HAS_CHUNK`` + ``MENTIONS`` 边数
    evidence_edge_count: int = 0


@dataclass(frozen=True, slots=True)
class KgDocumentRef:
    """文档节点引用（Sprint 6 批次 A-3：``:Document`` / ``:Chunk`` 的写侧输入）。

    ``acl_scope`` 来自 ``documents.acl_scope``（ADR-0004 已登记的预留字段，
    **不进契约**）；为 ``None`` 时节点上该属性同样为 ``None``（Neo4j 存 null）。
    """

    doc_id: uuid.UUID
    acl_scope: str | None = None


@dataclass(frozen=True, slots=True)
class KgBuildRequest:
    """一次三段式构建的输入。"""

    org_id: uuid.UUID
    version: str
    entities: Sequence[dict[str, Any]]
    relations: Sequence[dict[str, Any]]
    trace_id: uuid.UUID
    #: Sprint 6 批次 A-1 产物（``chunks.json`` 的 ``chunks`` 列表）
    chunks: Sequence[dict[str, Any]] = ()
    #: ``document`` 为 ``None`` 时跳过 stage-1.5 / stage-4（保持 S5 行为，兼容旧调用方）
    document: KgDocumentRef | None = None


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
#:
#: **实测反哺（Sprint 6 批次 A 真机）**：原写法 ``IS NODE KEY`` 在 **Neo4j 社区版**
#: 直接报 ``Neo.DatabaseError.Schema.ConstraintCreationFailed``——
#: ``Node Key constraint requires Neo4j Enterprise Edition``（本机容器 ``neo4j:latest``
#: 即社区版，kg_build 因此 stage-1 即失败）。降级为社区版可用的**复合唯一约束**：
#: 唯一性（幂等 MERGE 的前提）保留，NODE KEY 额外要求的「属性必存在」由写入段保证
#: （stage-2 的 ``MERGE`` 必然写入 ``id`` / ``kg_version``）。
_CYPHER_STAGE1B_INDEXES = (
    "CREATE CONSTRAINT entity_id_version IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE (n.id, n.kg_version) IS UNIQUE",
    "CREATE INDEX entity_org_id IF NOT EXISTS FOR (n:Entity) ON (n.org_id)",
)

#: stage-1.5（Sprint 6 批次 A-3）：MERGE ``:Document`` 节点。
#: 读侧 ``graphs.py::_QUERY_DOCUMENT_SUBGRAPH`` 正是按 ``(:Document {id, kg_version})``
#: 起查 ``-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity)``——**读侧早已就位，本段补齐写侧**。
#: ``acl_scope`` 从 ``documents.acl_scope`` 继承（预留字段，不进契约，ADR-0004）。
_CYPHER_STAGE1C_DOCUMENT = """
MERGE (d:Document {id: $doc_id, kg_version: $kg_version})
ON CREATE SET d.org_id = $org_id,
              d.acl_scope = $acl_scope,
              d.trace_id = $trace_id,
              d.created_at = datetime()
ON MATCH SET d.org_id = $org_id,
             d.acl_scope = $acl_scope
RETURN d
"""

#: stage-2.5（Sprint 6 批次 A-3）：分批 MERGE ``:Chunk`` 证据节点。
#: ``page`` 允许为 ``null``（``PageIndex`` 失配时不伪造页码）；``text`` 直接落库，
#: 供批次 B 的引用回查（前端高亮）消费——**不**塞进 ``Citation`` 契约字段。
_CYPHER_STAGE2B_LOAD_CHUNKS = """
UNWIND $batch AS c
MERGE (n:Chunk {id: c.id, kg_version: $kg_version})
ON CREATE SET n.char_start = c.char_start,
              n.char_end = c.char_end,
              n.page = c.page,
              n.text = c.text,
              n.org_id = $org_id,
              n.acl_scope = $acl_scope,
              n.trace_id = $trace_id
ON MATCH SET n.char_start = c.char_start,
             n.char_end = c.char_end,
             n.page = c.page,
             n.text = c.text,
             n.org_id = $org_id,
             n.acl_scope = $acl_scope
"""

#: stage-4a（Sprint 6 批次 A-3）：``(:Document)-[:HAS_CHUNK]->(:Chunk)``
_CYPHER_STAGE4A_LINK_CHUNKS = """
UNWIND $batch AS c
MATCH (d:Document {id: $doc_id, kg_version: $kg_version})
MATCH (c2:Chunk {id: c.id, kg_version: $kg_version})
MERGE (d)-[r:HAS_CHUNK {id: $kg_version + ':hc:' + c.id, kg_version: $kg_version}]->(c2)
ON CREATE SET r.org_id = $org_id,
              r.trace_id = $trace_id
"""

#: stage-4b（Sprint 6 批次 A-3）：``(:Chunk)-[:MENTIONS]->(:Entity)``
#: ``entity_ids`` 由 :func:`_assign_entities_to_chunks` 在 Python 侧按字符区间算好——
#: 归属逻辑放 Cypher 会让「为什么这个实体属于这个 chunk」无法单测。
_CYPHER_STAGE4B_MENTIONS = """
UNWIND $batch AS c
MATCH (c2:Chunk {id: c.id, kg_version: $kg_version})
UNWIND c.entity_ids AS eid
MATCH (e:Entity {id: eid, kg_version: $kg_version})
MERGE (c2)-[r:MENTIONS {id: $kg_version + ':m:' + c.id + ':' + eid, kg_version: $kg_version}]->(e)
ON CREATE SET r.org_id = $org_id,
              r.trace_id = $trace_id
"""

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


def _normalize_chunk_row(chunk: Any) -> dict[str, Any]:
    """把一条 chunk 记录归一为写库形状：**位置字段一律整型**。

    真机教训（2026-09-22 批次 B 冒烟）：真机 ``:Chunk`` 的 ``page`` / ``char_start`` /
    ``char_end`` 落库后是**字符串**（``'1'`` / ``'0'`` / ``'764'``）。读侧虽已 ``int()``
    归一，但 Neo4j 里类型是 string 时区间筛选与排序语义都会变，且「字符串区间参与
    比较」是隐性雷区（S10 才做真实引用，越晚越贵）。写侧一次性 cast；``page`` 缺失
    仍写 ``null``（PageIndex 失配时不伪造页码）。
    """
    row = dict(chunk)
    for key in ("char_start", "char_end"):
        value = row.get(key)
        row[key] = int(value) if value is not None else 0
    page = row.get("page")
    row["page"] = int(page) if page is not None else None
    return row


def _assign_entities_to_chunks(
    chunks: Sequence[dict[str, Any]], entities: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """按**字符区间**把实体归属到 chunk：``entity.char_start ∈ [chunk.char_start, chunk.char_end)``。

    - 只归属到**第一个**命中的 chunk（chunk 区间互不重叠，故归属唯一）；
    - 实体 ``char_start`` 不落在任何 chunk 区间内时**不归属**（该实体无 chunk 证据）。
      **不**退化为「最近的 chunk」——把实体挂到错误的证据上，比没有证据更危险。

    :returns: ``[{"id": chunk_id, "entity_ids": [...]}, ...]``（仅含非空归属）
    """
    ranges: list[tuple[str, int, int]] = []
    for chunk in chunks:
        chunk_id = str(chunk.get("id") or "")
        ranges.append(
            (
                chunk_id,
                int(chunk.get("char_start") or 0),
                int(chunk.get("char_end") or 0),
            )
        )

    assignment: dict[str, list[str]] = {chunk_id: [] for chunk_id, _, _ in ranges}
    for entity in entities:
        entity_id = entity.get("id")
        if entity_id is None:
            continue
        position = int(entity.get("char_start") or 0)
        for chunk_id, start, end in ranges:
            if start <= position < end:
                assignment[chunk_id].append(str(entity_id))
                break

    return [
        {"id": chunk_id, "entity_ids": entity_ids}
        for chunk_id, entity_ids in assignment.items()
        if entity_ids
    ]


class ThreeStageKgBuilder:
    """ADR-0002 三段式 Neo4j 写入器（Sprint 6 批次 A-3 扩为五段式）。"""

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
        """按 stage-1 → 1.5 → 2 → 2.5 → 3 → 4 顺序写入；任一段失败即抛 GraphUnavailableError。

        stage-1.5 / 2.5 / 4 属 Sprint 6 批次 A-3 的证据层；``request.document is None``
        或 ``request.chunks`` 为空时自动跳过（保持 S5 的三段式行为，兼容既有调用方与单测）。
        """
        if not request.entities and not request.relations and not request.chunks:
            return BuildStats(entity_count=0, relation_count=0, batch_count=0)

        self._stage1(
            version=request.version,
            org_id=request.org_id,
            trace_id=request.trace_id,
        )
        document_written = self._stage1_document(request)
        entity_count = self._stage2(request)
        chunk_count = self._stage2_chunks(request)
        relation_count = self._stage3(request)
        evidence_edge_count = self._stage4(request)

        batch_count = sum(
            1
            for _ in (
                list(_chunks_by_batches(request.entities, self._batch_size))
                + list(_chunks_by_batches(request.relations, self._batch_size))
                + list(_chunks_by_batches(request.chunks, self._batch_size))
            )
        )

        logger.bind(
            trace_id=str(request.trace_id),
            org_id=str(request.org_id),
            version=request.version,
            entity_count=entity_count,
            relation_count=relation_count,
            chunk_count=chunk_count,
            evidence_edge_count=evidence_edge_count,
            document_written=document_written,
        ).info("kg_build_done")

        return BuildStats(
            entity_count=entity_count,
            relation_count=relation_count,
            batch_count=batch_count,
            chunk_count=chunk_count,
            evidence_edge_count=evidence_edge_count,
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

    def _stage1_document(self, request: KgBuildRequest) -> bool:
        """stage-1.5：MERGE ``:Document`` 节点；返回是否写入（无 document 引用则跳过）。"""
        if request.document is None:
            return False
        try:
            self._run(
                _CYPHER_STAGE1C_DOCUMENT,
                {
                    "doc_id": str(request.document.doc_id),
                    "kg_version": request.version,
                    "org_id": str(request.org_id),
                    "acl_scope": request.document.acl_scope,
                    "trace_id": str(request.trace_id),
                },
            )
            return True
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-1.5 失败: {exc}") from exc

    def _stage2_chunks(self, request: KgBuildRequest) -> int:
        """stage-2.5：分批 MERGE ``:Chunk`` 证据节点；返回写入条数。"""
        if not request.chunks:
            return 0
        acl_scope = request.document.acl_scope if request.document else None
        try:
            written = 0
            for batch in _chunks_by_batches(request.chunks, self._batch_size):
                self._run(
                    _CYPHER_STAGE2B_LOAD_CHUNKS,
                    {
                        # 写侧归一：位置字段转整型（真机曾落库成字符串，见上方注释）
                        "batch": [_normalize_chunk_row(chunk) for chunk in batch],
                        "kg_version": request.version,
                        "org_id": str(request.org_id),
                        "acl_scope": acl_scope,
                        "trace_id": str(request.trace_id),
                    },
                )
                written += len(batch)
            return written
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-2.5 失败: {exc}") from exc

    def _stage4(self, request: KgBuildRequest) -> int:
        """stage-4：``(:Document)-[:HAS_CHUNK]->(:Chunk)`` + ``(:Chunk)-[:MENTIONS]->(:Entity)``。

        返回写入的**边**条数（两条类型的合计）。``document`` 缺失或无 chunk 时直接跳过
        ——证据层不完整时**不**静默造边：宁可没有 ``MENTIONS``，也不把实体挂到错误的 chunk 上。
        """
        if request.document is None or not request.chunks:
            return 0

        assignments = _assign_entities_to_chunks(request.chunks, request.entities)
        link_batch = [{"id": chunk.get("id")} for chunk in request.chunks]

        try:
            written = 0
            for batch in _chunks_by_batches(link_batch, self._batch_size):
                self._run(
                    _CYPHER_STAGE4A_LINK_CHUNKS,
                    {
                        "batch": list(batch),
                        "doc_id": str(request.document.doc_id),
                        "kg_version": request.version,
                        "org_id": str(request.org_id),
                        "trace_id": str(request.trace_id),
                    },
                )
                written += len(batch)
            for batch in _chunks_by_batches(assignments, self._batch_size):
                self._run(
                    _CYPHER_STAGE4B_MENTIONS,
                    {
                        "batch": list(batch),
                        "kg_version": request.version,
                        "org_id": str(request.org_id),
                        "trace_id": str(request.trace_id),
                    },
                )
                written += sum(len(item["entity_ids"]) for item in batch)
            return written
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-4 失败: {exc}") from exc

    # -------------------------------------------------------------- 内部

    def _run(self, cypher: str, params: dict[str, Any]) -> Any:  # noqa: ANN401
        """跑一段 Cypher；测试可通过 ``session_factory`` 注入桩。"""
        if self._session_factory is not None:
            with self._session_factory() as session:
                return session.run(cypher, **params).data()
        # 生产路径：复用 GraphService 懒加载的 driver
        with self._graph_service._session() as session:  # type: ignore[attr-defined]
            return session.run(cypher, **params).data()


__all__ = [
    "BuildStats",
    "KgBuildRequest",
    "KgBuilder",
    "KgDocumentRef",
    "ThreeStageKgBuilder",
]
