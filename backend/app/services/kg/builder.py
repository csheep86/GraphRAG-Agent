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

Sprint 7.1 批次 A 新增的主体层（`specs/m4-affiliation-detection.md` §4.1 / §4.2 的
增量建模，**同样是可跳过段**：抽取产物里没有 ``LEGAL_PERSON`` / ``ADDRESS`` 时
一段都不跑）：

2.6. **stage-2.6 affiliation LOAD**——``:Subject`` / ``:Address`` / ``:LegalPerson``
     三类节点，``id`` 由**规范化名称的 sha256** 决定（同名跨文档天然合成同一节点，
     M4 的共享法人 / 共享地址两跳算法就建立在这个「合并」上，见
     :func:`build_affiliation_rows`）；
3.2. **stage-3.2 affiliation links**——``(:Subject)-[:LEGAL_REP]->(:LegalPerson)``
     与 ``(:Subject)-[:REGISTERED_AT]->(:Address)``。

设计边界（批次 A，超出部分一律留给后续 Sprint）：
- **不与 ``:Entity`` 桥接**：三类节点 / 两条边只按 M2 抽取产物生成，不额外补节点、
  也不往 ``:Entity`` 上打补丁（``changes/Sprint7.1/tasks.md`` §2.2「不桥接」决策）——
  两套坐标混用会让"同一家公司到底在图里是几个点"失去确定性；M4 算法只查这三类
  节点，不受 M2 通用图干扰。
- **缺失即 ``null``，严禁兜底生成**：``tax_id`` / ``region_code`` / ``id_hash``
  在分销材料里拿不到就写 ``null``（**不**拿名字凑哈希、不猜行政区划），
  否则「同名不同组织机构」会被伪造的统一信用代码误合并。
- 新节点一律带 ``kg_version``（ADR-0002：与 M2 共享同一 active 版本，不分裂）；
  ``acl_scope`` 沿用 :class:`KgDocumentRef` 口径从文档继承，为 S11 的 RLS 穿透留属性。

设计边界：
- **不**做内层事务——Neo4j 事务 + PG 事务分离（ADR-0002 §3.1 跨库一致性靠
  ``kg_versions`` 状态机 + 回填校验）；
- Neo4j driver **复用** :class:`GraphService` 懒加载的连接（``GraphService.instance()._ensure_driver()``），
  **不**自建驱动；
- ``kg_build_batch_size`` 上限保护 stage-2 / stage-3 内存峰值。
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from loguru import logger

from app.core.config import get_settings
from app.services.graphs import GraphService, GraphUnavailableError
from app.services.kg.temporal import (
    PolicyLookup,
    TemporalRelation,
    always_append_only,
    plan_expiries,
)


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
    #: Sprint 7.1 批次 A（M4）：``:Subject`` 节点数（无 affiliation 数据时为 0）
    subject_count: int = 0
    #: Sprint 7.1 批次 A（M4）：``:Address`` 节点数
    address_count: int = 0
    #: Sprint 7.1 批次 A（M4）：``:LegalPerson`` 节点数
    legal_person_count: int = 0
    #: Sprint 7.1 批次 A（M4）：``LEGAL_REP`` + ``REGISTERED_AT`` 边数
    affiliation_edge_count: int = 0
    #: Sprint 9 批次 B（ADR-0005 L1）：本次构建被**仲裁封掉**的旧边数。
    #: 它必须能被观测——仲裁静默封对了不算好，封错了要能从统计里先看见异常。
    expired_edge_count: int = 0


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
    # Sprint 7.1 批次 A（M4 增量建模）：三类主体节点的幂等 MERGE 前提。
    # 写法与 Entity 一致——社区版只能要复合唯一约束（见上方实测反哺）。
    "CREATE CONSTRAINT subject_id_version IF NOT EXISTS "
    "FOR (n:Subject) REQUIRE (n.id, n.kg_version) IS UNIQUE",
    "CREATE CONSTRAINT address_id_version IF NOT EXISTS "
    "FOR (n:Address) REQUIRE (n.id, n.kg_version) IS UNIQUE",
    "CREATE CONSTRAINT legalperson_id_version IF NOT EXISTS "
    "FOR (n:LegalPerson) REQUIRE (n.id, n.kg_version) IS UNIQUE",
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

#: stage-2.6（Sprint 7.1 批次 A，M4 §4.1）：分批 MERGE ``:Subject`` 主体节点。
#: ``tax_id`` 缺失即 ``null``——**不**拿名字凑统一社会信用代码（那会让不同机构误合并）。
_CYPHER_STAGE2C_LOAD_SUBJECTS = """
UNWIND $batch AS s
MERGE (n:Subject {id: s.id, kg_version: $kg_version})
ON CREATE SET n.name = s.name,
              n.tax_id = s.tax_id,
              n.type = s.type,
              n.source_entity_ids = s.source_entity_ids,
              n.org_id = $org_id,
              n.acl_scope = $acl_scope,
              n.trace_id = $trace_id
ON MATCH SET n.name = s.name,
             n.tax_id = s.tax_id,
             n.type = s.type,
             n.source_entity_ids = reduce(
                 acc = coalesce(n.source_entity_ids, []),
                 x IN s.source_entity_ids |
                 CASE WHEN x IN acc THEN acc ELSE acc + x END
             ),
             n.org_id = $org_id,
             n.acl_scope = $acl_scope
"""

#: stage-2.6（Sprint 7.1 批次 A，M4 §4.1）：分批 MERGE ``:Address`` 地址节点。
#: ``region_code`` 缺失即 ``null``（不猜行政区划）。
#: ``source_entity_ids`` 的 ON MATCH 用 ``reduce`` 累加去重（社区版无 apoc.coll.toSet）：
#: 同一法人 / 地址会在多份文档里被抽到，**每份贡献不同的源实体 id**，直接覆盖会丢溯源。
_CYPHER_STAGE2D_LOAD_ADDRESSES = """
UNWIND $batch AS a
MERGE (n:Address {id: a.id, kg_version: $kg_version})
ON CREATE SET n.full_address = a.full_address,
              n.region_code = a.region_code,
              n.source_entity_ids = a.source_entity_ids,
              n.org_id = $org_id,
              n.acl_scope = $acl_scope,
              n.trace_id = $trace_id
ON MATCH SET n.full_address = a.full_address,
             n.region_code = a.region_code,
             n.source_entity_ids = reduce(
                 acc = coalesce(n.source_entity_ids, []),
                 x IN a.source_entity_ids |
                 CASE WHEN x IN acc THEN acc ELSE acc + x END
             ),
             n.org_id = $org_id,
             n.acl_scope = $acl_scope
"""

#: stage-2.6（Sprint 7.1 批次 A，M4 §4.1）：分批 MERGE ``:LegalPerson`` 法人节点。
#: ``id_type`` / ``id_hash`` 缺失即 ``null``——**严禁兜底生成哈希**：
#: 分销材料里没有证件号，拿名字造 id_hash 会让"同名不同人"被误合并（比缺失更危险）。
_CYPHER_STAGE2E_LOAD_LEGAL_PERSONS = """
UNWIND $batch AS p
MERGE (n:LegalPerson {id: p.id, kg_version: $kg_version})
ON CREATE SET n.name = p.name,
              n.id_type = p.id_type,
              n.id_hash = p.id_hash,
              n.source_entity_ids = p.source_entity_ids,
              n.org_id = $org_id,
              n.acl_scope = $acl_scope,
              n.trace_id = $trace_id
ON MATCH SET n.name = p.name,
             n.id_type = p.id_type,
             n.id_hash = p.id_hash,
             n.source_entity_ids = reduce(
                 acc = coalesce(n.source_entity_ids, []),
                 x IN p.source_entity_ids |
                 CASE WHEN x IN acc THEN acc ELSE acc + x END
             ),
             n.org_id = $org_id,
             n.acl_scope = $acl_scope
"""

#: stage-3.2（Sprint 7.1 批次 A，M4 §4.2）：``(:Subject)-[:LEGAL_REP]->(:LegalPerson)``。
#: 两端有一端 MATCH 不到就**不造**——与 stage-3 的 MATCH-MERGE 纪律一致：没有证据不写边。
_CYPHER_STAGE3B_LEGAL_REP = """
UNWIND $batch AS r
MATCH (s:Subject {id: r.source_id, kg_version: $kg_version})
MATCH (p:LegalPerson {id: r.target_id, kg_version: $kg_version})
MERGE (s)-[rel:LEGAL_REP {id: r.id, kg_version: $kg_version}]->(p)
ON CREATE SET rel.org_id = $org_id,
              rel.trace_id = $trace_id,
              rel.valid_from = r.valid_from,
              rel.valid_to = r.valid_to,
              rel.created_at = datetime(),
              rel.source_document_id = r.source_document_id
ON MATCH SET rel.valid_from = coalesce(rel.valid_from, r.valid_from),
             rel.source_document_id = coalesce(rel.source_document_id, r.source_document_id)
"""

#: stage-3.2（Sprint 7.1 批次 A，M4 §4.2）：``(:Subject)-[:REGISTERED_AT]->(:Address)``
_CYPHER_STAGE3C_REGISTERED_AT = """
UNWIND $batch AS r
MATCH (s:Subject {id: r.source_id, kg_version: $kg_version})
MATCH (a:Address {id: r.target_id, kg_version: $kg_version})
MERGE (s)-[rel:REGISTERED_AT {id: r.id, kg_version: $kg_version}]->(a)
ON CREATE SET rel.org_id = $org_id,
              rel.trace_id = $trace_id,
              rel.valid_from = r.valid_from,
              rel.valid_to = r.valid_to,
              rel.created_at = datetime(),
              rel.source_document_id = r.source_document_id
ON MATCH SET rel.valid_from = coalesce(rel.valid_from, r.valid_from),
             rel.source_document_id = coalesce(rel.source_document_id, r.source_document_id)
"""

#: ---- stage-3.3（Sprint 9 批次 B，ADR-0005 L1）：仲裁用的查询 / 封边 ----
#:
#: **为什么不写动态 Cypher**（把 relation_type 拼进字符串）：Neo4j 不支持参数化
#: 关系类型，社区版也没有 apoc 可用 ⇒ 只有两类 typed 边，就写两段常量。
#: 宁愿多写一遍也不拼字符串：拼出来的类型若不存在只会静默"查不到"，
#: 还顺带开了注入的口子。
#:
#: **跨 ``kg_version`` 查询**（``s.id`` 稳定，见 :func:`_stable_node_id`）是刻意的：
#: 图谱每次构建一套新版本节点，而仲裁的语义是「跨文档」——限定当前版本
#: 就等于永远看不见上一次构建写的事实，R1 形同虚设。
_CYPHER_QUERY_ALIVE_LEGAL_REP = """
UNWIND $heads AS head
MATCH (s:Subject {id: head})-[r:LEGAL_REP]->(p:LegalPerson)
WHERE r.org_id = $org_id AND r.valid_to IS NULL
RETURN head AS head_id,
       p.id AS tail_id,
       r.valid_from AS valid_from,
       r.source_document_id AS source_document_id
"""

_CYPHER_EXPIRE_LEGAL_REP = """
UNWIND $batch AS x
MATCH (s:Subject {id: x.head_id})-[r:LEGAL_REP]->(p:LegalPerson {id: x.tail_id})
WHERE r.org_id = $org_id AND r.valid_to IS NULL AND r.valid_from = x.valid_from
SET r.valid_to = x.valid_to,
    r.expired_at = datetime(),
    r.invalidated_reason = x.reason
"""

_CYPHER_QUERY_ALIVE_REGISTERED_AT = """
UNWIND $heads AS head
MATCH (s:Subject {id: head})-[r:REGISTERED_AT]->(a:Address)
WHERE r.org_id = $org_id AND r.valid_to IS NULL
RETURN head AS head_id,
       a.id AS tail_id,
       r.valid_from AS valid_from,
       r.source_document_id AS source_document_id
"""

_CYPHER_EXPIRE_REGISTERED_AT = """
UNWIND $batch AS x
MATCH (s:Subject {id: x.head_id})-[r:REGISTERED_AT]->(a:Address {id: x.tail_id})
WHERE r.org_id = $org_id AND r.valid_to IS NULL AND r.valid_from = x.valid_from
SET r.valid_to = x.valid_to,
    r.expired_at = datetime(),
    r.invalidated_reason = x.reason
"""

#: stage-2：单批 LOAD entities（M2 通用实体，**不与 M4 主体层桥接**）
_CYPHER_STAGE2_LOAD_ENTITIES = """
UNWIND $batch AS e
MERGE (n:Entity {id: e.id, kg_version: $kg_version})
ON CREATE SET n.canonical_name = e.canonical_name,
              n.entity_type = e.entity_type,
              n.mention = e.mention,
              n.confidence = e.confidence,
              n.char_start = e.char_start,
              n.char_end = e.char_end,
              n.org_id = $org_id,
              n.trace_id = $trace_id
ON MATCH SET n.canonical_name = e.canonical_name,
             n.entity_type = e.entity_type,
             n.mention = e.mention,
             n.confidence = e.confidence,
             n.char_start = e.char_start,
             n.char_end = e.char_end,
             n.org_id = $org_id
"""

#: Sprint 10 批次 A（裁决 D-D）：``char_start`` / ``char_end`` 是实体在**文档全文**中的
#: 字符区间，来自抽取侧 ``ExtractedEntity``（Sprint 6 起就有值，**此前入图时被丢弃**）。
#: CSV 派生的结构化实体（如考勤域）**天然没有 span** ⇒ ``e.char_start`` 缺失时
#: Cypher 写入 ``null``（Neo4j 不存 null 属性）⇒ 读侧回退为整段引用——**不造 span**。
#: 读侧 :meth:`GraphService.fetch_evidence_chunks` 用它把引用从"指到哪一段"
#: 精确到"指到哪一句"；换算只在 ``agents._to_citation`` 一处（D-B）。

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


# ------------------------------------------------------------------------------
# Sprint 7.1 批次 A：M4 主体层行构造（纯函数，**不触 Neo4j**，便于单测）
# ------------------------------------------------------------------------------

#: 能当 M4 ``:Subject`` 的抽取类型（``specs/m4-affiliation-detection.md`` §4.1：
#: 主体 = 公司 / 个体工商户 / 个人；分销材料里能落到位的是 ``ORG``）
_SUBJECT_ENTITY_TYPE: Final[str] = "ORG"
_LEGAL_PERSON_ENTITY_TYPE: Final[str] = "LEGAL_PERSON"
_ADDRESS_ENTITY_TYPE: Final[str] = "ADDRESS"
_RELATION_LEGAL_REP: Final[str] = "LEGAL_REP"
_RELATION_REGISTERED_AT: Final[str] = "REGISTERED_AT"


def _stable_node_id(prefix: str, key: str) -> str:
    """按**规范化名称**生成稳定节点 id。

    M4 的共享法人 / 共享地址是**两跳**查询（``s1 -[:LEGAL_REP]-> p <-[:LEGAL_REP]- s2``），
    它能否成立完全取决于「不同文档里同名的法人必须合成同一个节点」——所以这里用
    拿 SHA-256(**name.strip()**) 当 id，而不是 LLM 给的 ``ent_<uuid>``（那份 id 每次抽取
    都不同，**跨文档必然连不上**）。

    :param prefix: 节点前缀（``sub`` / ``adr`` / ``lpr``），避免三类撞 namespaces。
    """
    normalized = key.strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _target_position(entity: Mapping[str, Any]) -> int | None:
    """取 target 实体的字符偏移——**R2 的判据**（ADR-0005 §5）。

    用实体的 ``char_start`` 而不是「名字在全文里最后出现的位置」（PoC 的写法）：
    后者会被同名干扰（正文别处的"张三"会让偏移变大），前者是该实体在原文里的
    真实位置。拿不到就返回 ``None`` ⇒ R2 整组跳过（宁可不判）。
    """
    value = entity.get("char_start")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _earliest_fact(
    previous: dict[str, Any] | None, candidate: dict[str, Any]
) -> dict[str, Any]:
    """同一条事实（同端点）在**多份文档**里被抽到 ⇒ 合并成一行，``valid_from`` 取**最早**。

    为什么不是"后来者赢"（dict 直接覆盖）：那会把 2023 年披露的事实改成 2025 年
    那份里的 ``valid_from``——等于悄悄改写历史。``valid_from`` 的语义是事实**开始**
    成立的日期，取最早证据既保守又正确。血缘跟着最早那条走（它是该生效日的出处）；
    ``valid_to`` 取**任一非空值**——有一份文档说它失效就够了，信息不丢。
    """
    if previous is None:
        return candidate
    old_from = previous.get("valid_from")
    new_from = candidate.get("valid_from")
    if isinstance(old_from, str) and isinstance(new_from, str) and new_from < old_from:
        return {
            **candidate,
            "valid_to": previous.get("valid_to") or candidate.get("valid_to"),
        }
    return {
        **previous,
        "valid_to": previous.get("valid_to") or candidate.get("valid_to"),
    }


@dataclass(frozen=True, slots=True)
class AffiliationRows:
    """由抽取产物算出的 M4 主体层写入行（全部去重、id 稳定）。"""

    subjects: list[dict[str, Any]] = field(default_factory=list)
    addresses: list[dict[str, Any]] = field(default_factory=list)
    legal_persons: list[dict[str, Any]] = field(default_factory=list)
    legal_rep_edges: list[dict[str, Any]] = field(default_factory=list)
    registered_at_edges: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.subjects or self.addresses or self.legal_persons)


def _upsert(
    target: dict[str, dict[str, Any]],
    node_id: str,
    row: dict[str, Any],
    *,
    source_entity_id: str,
) -> None:
    """登记一行主体层数据，并把它**源自哪个 M2 实体**累加进 ``source_entity_ids``。

    ``source_entity_ids`` 是本批次在 spec §4.1 属性之外**新增的溯源字段**，用途单一：
    M4 的疑点必须能回原文（§3 验收 4「引用覆盖率 = 100%」），而 ``:Chunk`` 只
    ``MENTIONS`` 到 ``:Entity``——没有这层溯源，疑点就没有任何可点击的证据。
    **它不构成 ``:Entity`` ↔ ``:Subject`` 的图桥接**（只存 id 字符串，不建关系）。
    """
    if node_id not in target:
        target[node_id] = {**row, "source_entity_ids": []}
    ids = target[node_id]["source_entity_ids"]
    if source_entity_id and source_entity_id not in ids:
        ids.append(source_entity_id)


def _register_subject(
    subjects: dict[str, dict[str, Any]], source: dict[str, Any]
) -> str:
    """按需把 source 登记为 :Subject——**只有真要落一条边时才登记**。

    先登记再判目标类型会产出「没有任何关系边的孤儿 :Subject」，既污染 M4 算法的
    分母，也让本函数对无关关系（``PARTY_TO`` 等）产出垃圾行。
    """
    name = str(source.get("canonical_name") or "").strip()
    identifier = _stable_node_id("sub", name)
    _upsert(
        subjects,
        identifier,
        {
            "id": identifier,
            "name": name,
            "tax_id": None,
            "type": str(source.get("entity_type")),
        },
        source_entity_id=str(source.get("id") or ""),
    )
    return identifier


def build_affiliation_rows(
    entities: Sequence[dict[str, Any]],
    relations: Sequence[dict[str, Any]],
    *,
    version: str,
    source_document_id: str | None = None,
) -> AffiliationRows:
    """把 M2 抽取产物翻译成 M4 三类节点 + 两条边；**不是**就不写。

    只有当关系两侧的抽取类型都对得上（``ORG`` → ``LEGAL_PERSON`` / ``ADDRESS``）
    才产出一行；类型不匹配（如 ``PERSON`` 当 source）直接丢弃——M4 算法的分母是
    ``:Subject``，塞错实体会让"共享法人"结论失去意义。

    ``tax_id`` / ``region_code`` / ``id_type`` / ``id_hash`` 一律写 ``None``：
    分销材料里没有这些主数据字段，**缺失就 null**（内部纪律：严禁兜底生成）。

    Sprint 9 批次 B（ADR-0005 L1）新增 ``source_document_id`` 与时态字段：这两条边
    要为上层仲裁提供「事实何时成立 + 出自哪份文档」。
    ``relations`` 里没有 ``valid_from`` 时**保留 ``None``** ——不猜、不补（R4）；
    上层仲裁见到 ``None`` 会把该边排除出时效比较，而不是替它编一个日期。
    """
    by_id: dict[str, dict[str, Any]] = {}
    for entity in entities:
        entity_id = entity.get("id")
        if entity_id is not None:
            by_id[str(entity_id)] = entity

    subjects: dict[str, dict[str, Any]] = {}
    addresses: dict[str, dict[str, Any]] = {}
    legal_persons: dict[str, dict[str, Any]] = {}
    legal_rep_edges: dict[str, dict[str, Any]] = {}
    registered_at_edges: dict[str, dict[str, Any]] = {}

    for relation in relations:
        relation_type = relation.get("relation_type")
        source = by_id.get(str(relation.get("source_entity_id")))
        target = by_id.get(str(relation.get("target_entity_id")))
        if source is None or target is None:
            continue  # 悬空端点：与其在 Neo4j 里 MATCH 不到，不如这里就丢掉

        source_type = source.get("entity_type")
        target_type = target.get("entity_type")
        # 事实维 + 血缘（ADR-0005 §4）。缺失即 None：上层仲裁见到 None 会把该边
        # 排除出时效比较，而不是替它编一个日期（R4 不猜值）。
        temporal = {
            "valid_from": relation.get("valid_from"),
            "valid_to": relation.get("valid_to"),
            "source_document_id": source_document_id,
            "tail_position": _target_position(target),
        }
        if source_type != _SUBJECT_ENTITY_TYPE:
            # M4 的 :Subject 只收 ORG：把 PERSON / DATE 之类硬塞进来会让
            # "共享法人"的两跳查询分母失真
            continue

        if relation_type == _RELATION_LEGAL_REP and (
            target_type == _LEGAL_PERSON_ENTITY_TYPE
        ):
            target_name = str(target.get("canonical_name") or "").strip()
            if not target_name:
                continue
            person_id = _stable_node_id("lpr", target_name)
            _upsert(
                legal_persons,
                person_id,
                {
                    "id": person_id,
                    "name": target_name,
                    "id_type": None,
                    "id_hash": None,
                },
                source_entity_id=str(target.get("id") or ""),
            )
            subject_node_id = _register_subject(subjects, source)
            # 边 id **按端点生成**（与节点 id 同源），而**不用抽取侧的 relation id**：
            # "甲公司法人是张三"是一条**事实**，在 6 份文档里被抽到 3 次就该是 3 条
            # ``source_entity_ids`` 溯源 + **1 条边**；用 relation id 会 MERGE 出 3 条
            # 并行边，直接后果是 M4 两跳按路径匹配 → 同一疑点重复出 3 遍（真机踩到）。
            rep_key = f"{subject_node_id}->{person_id}"
            legal_rep_edges[rep_key] = _earliest_fact(
                legal_rep_edges.get(rep_key),
                {
                    "id": f"{version}:lr:{subject_node_id}:{person_id}",
                    "source_id": subject_node_id,
                    "target_id": person_id,
                    **temporal,
                },
            )
        elif relation_type == _RELATION_REGISTERED_AT and (
            target_type == _ADDRESS_ENTITY_TYPE
        ):
            full_address = str(target.get("canonical_name") or "").strip()
            if not full_address:
                continue
            address_id = _stable_node_id("adr", full_address)
            _upsert(
                addresses,
                address_id,
                {
                    "id": address_id,
                    "full_address": full_address,
                    "region_code": None,
                },
                source_entity_id=str(target.get("id") or ""),
            )
            subject_node_id = _register_subject(subjects, source)
            address_key = f"{subject_node_id}->{address_id}"
            registered_at_edges[address_key] = _earliest_fact(
                registered_at_edges.get(address_key),
                {
                    "id": f"{version}:ra:{subject_node_id}:{address_id}",
                    "source_id": subject_node_id,
                    "target_id": address_id,
                    **temporal,
                },
            )

    return AffiliationRows(
        subjects=list(subjects.values()),
        addresses=list(addresses.values()),
        legal_persons=list(legal_persons.values()),
        legal_rep_edges=list(legal_rep_edges.values()),
        registered_at_edges=list(registered_at_edges.values()),
    )


class ThreeStageKgBuilder:
    """ADR-0002 三段式 Neo4j 写入器（Sprint 6 批次 A-3 扩为五段式）。"""

    def __init__(
        self,
        *,
        graph_service: GraphService | None = None,
        batch_size: int | None = None,
        version_strategy: str | None = None,
        session_factory: Any = None,
        policy_lookup: PolicyLookup | None = None,
    ) -> None:
        """``session_factory`` 留给测试注入（默认 None ⇒ 用真实 ``GraphService.instance()``）。

        :param policy_lookup: ``relation_type → 是否唯一当前``（ADR-0005 §6 L1）。
            由调用方从策略表读出后注入（:func:`app.services.kg.policies.load_expiry_policies`），
            **builder 不碰数据库**——保持它对 PG 的零依赖，测试才能只桩 Neo4j。
            缺省即「一律并存」⇒ 仲裁跳过所有类型，**行为与接入前完全一致**
            （既有调用方与单测不受影响，这是分阶段接入的前提）。
        """
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
        self._policy_lookup = policy_lookup or always_append_only

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

        # Sprint 7.1 批次 A：M4 主体层（无 affiliation 数据时一段都不跑）
        affiliation = build_affiliation_rows(
            request.entities,
            request.relations,
            version=request.version,
            # 血缘：这批事实出自哪份文档。单文档构建即该文档 id；没有 document
            # （旧调用方 / 单测）时为 None ⇒ 该批所有边同源，R3「同批不互封」照常生效。
            source_document_id=(
                str(request.document.doc_id) if request.document else None
            ),
        )
        affiliation_stats = self._stage_affiliation(request, affiliation)

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
            subject_count=affiliation_stats[0],
            address_count=affiliation_stats[1],
            legal_person_count=affiliation_stats[2],
            affiliation_edge_count=affiliation_stats[3],
            expired_edge_count=affiliation_stats[4],
        ).info("kg_build_done")

        return BuildStats(
            entity_count=entity_count,
            relation_count=relation_count,
            batch_count=batch_count,
            chunk_count=chunk_count,
            evidence_edge_count=evidence_edge_count,
            subject_count=affiliation_stats[0],
            address_count=affiliation_stats[1],
            legal_person_count=affiliation_stats[2],
            affiliation_edge_count=affiliation_stats[3],
            expired_edge_count=affiliation_stats[4],
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

    # ------------------------------------------------------- M4 主体层

    def _stage_affiliation(
        self, request: KgBuildRequest, rows: AffiliationRows
    ) -> tuple[int, int, int, int, int]:
        """stage-2.6 + stage-3.2 + stage-3.3：写 M4 三类节点、两条边，**再**跑仲裁。

        .. note:: 顺序不能颠倒：**先写后封**。封边依赖新事实已经在图里
           （R2 封的是本次刚写入的旧值边），反过来做会一封一个空。

        :returns: ``(subject_count, address_count, legal_person_count,
            affiliation_edge_count, expired_edge_count)``
            ``rows.is_empty`` 时**一段都不跑**（保持既有调用方与单测观察到的行为）。
        """
        if rows.is_empty:
            return (0, 0, 0, 0, 0)

        acl_scope = request.document.acl_scope if request.document else None
        common_params = {
            "kg_version": request.version,
            "org_id": str(request.org_id),
            "acl_scope": acl_scope,
            "trace_id": str(request.trace_id),
        }
        try:
            written = {"subjects": 0, "addresses": 0, "persons": 0}
            for cypher, batch, key in (
                (_CYPHER_STAGE2C_LOAD_SUBJECTS, rows.subjects, "subjects"),
                (_CYPHER_STAGE2D_LOAD_ADDRESSES, rows.addresses, "addresses"),
                (_CYPHER_STAGE2E_LOAD_LEGAL_PERSONS, rows.legal_persons, "persons"),
            ):
                for chunk in _chunks_by_batches(batch, self._batch_size):
                    self._run(cypher, {"batch": list(chunk), **common_params})
                    written[key] += len(chunk)

            edges = 0
            for cypher, batch in (
                (_CYPHER_STAGE3B_LEGAL_REP, rows.legal_rep_edges),
                (_CYPHER_STAGE3C_REGISTERED_AT, rows.registered_at_edges),
            ):
                for chunk in _chunks_by_batches(batch, self._batch_size):
                    self._run(cypher, {"batch": list(chunk), **common_params})
                    edges += len(chunk)

            # stage-3.3：先写后封（顺序见 docstring 的 note）
            expired = self._arbitrate_affiliation_edges(request, rows)

            return (
                written["subjects"],
                written["addresses"],
                written["persons"],
                edges,
                expired,
            )
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(f"stage-2.6/3.2/3.3 失败: {exc}") from exc

    def _arbitrate_affiliation_edges(
        self, request: KgBuildRequest, rows: AffiliationRows
    ) -> int:
        """stage-3.3：按 R1 / R2 把被取代的旧边 ``valid_to`` 封掉，返回封掉条数。

        判定**全部**在 :func:`plan_expiries`（纯函数）里，这里只做三件事：
        取现状 → 交给仲裁 → 按结论执行 ``SET``。
        仲裁失败照其它 stage 的纪律**抛错**（由外层判任务失败 + PG 状态），
        不静默跳过——静默跳过的后果是"答案里两个法定代表人同时在位"且无人知晓。

        **为什么只对 M4 主体层做**：这里的 head / tail 是 ``sha256(name)`` 稳定 id，
        跨文档可对齐；M2 的 ``:Entity`` id 是 ``ent_<uuid>``，每次抽取都变，
        跨文档匹配要先解决实体消解（属 M4 完整化，见 ``changes/Sprint9/proposal.md``）。
        """
        expired_total = 0
        for query_cypher, expire_cypher, batch, relation_type in (
            (
                _CYPHER_QUERY_ALIVE_LEGAL_REP,
                _CYPHER_EXPIRE_LEGAL_REP,
                rows.legal_rep_edges,
                _RELATION_LEGAL_REP,
            ),
            (
                _CYPHER_QUERY_ALIVE_REGISTERED_AT,
                _CYPHER_EXPIRE_REGISTERED_AT,
                rows.registered_at_edges,
                _RELATION_REGISTERED_AT,
            ),
        ):
            if not batch or not self._policy_lookup(relation_type):
                continue  # 策略未配 single_current ⇒ 多值并存，不仲裁

            heads = sorted({str(row["source_id"]) for row in batch})
            alive_rows = self._run(
                query_cypher, {"heads": heads, "org_id": str(request.org_id)}
            )
            existing = [
                TemporalRelation(
                    head_id=str(row["head_id"]),
                    tail_id=str(row["tail_id"]),
                    relation_type=relation_type,
                    valid_from=row["valid_from"],
                    source_document_id=row["source_document_id"],
                )
                for row in alive_rows or []
            ]
            incoming = [
                TemporalRelation(
                    head_id=str(row["source_id"]),
                    tail_id=str(row["target_id"]),
                    relation_type=relation_type,
                    valid_from=row.get("valid_from"),
                    valid_to=row.get("valid_to"),
                    source_document_id=row.get("source_document_id"),
                    tail_position=row.get("tail_position"),
                )
                for row in batch
            ]
            plans = plan_expiries(
                existing=existing,
                incoming=incoming,
                is_single_current=self._policy_lookup,
            )
            if not plans:
                continue

            payload = [
                {
                    "head_id": plan.relation.head_id,
                    "tail_id": plan.relation.tail_id,
                    "valid_from": plan.relation.valid_from,
                    "valid_to": plan.valid_to,
                    "reason": plan.reason,
                }
                for plan in plans
            ]
            self._run(expire_cypher, {"batch": payload, "org_id": str(request.org_id)})
            expired_total += len(payload)
            # 必须可观测：封了哪类、封了几条、封之前还剩多少条活的
            logger.bind(
                trace_id=str(request.trace_id),
                org_id=str(request.org_id),
                relation_type=relation_type,
                alive_before=len(existing),
                expired=len(payload),
                reasons=sorted({plan.reason for plan in plans}),
            ).info("kg_arbitration_expired")
        return expired_total

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
    "AffiliationRows",
    "BuildStats",
    "KgBuildRequest",
    "KgBuilder",
    "KgDocumentRef",
    "ThreeStageKgBuilder",
    "build_affiliation_rows",
]
