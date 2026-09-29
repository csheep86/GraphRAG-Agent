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
  （属性 + 出边邻居 0–50 条）；
- :meth:`GraphService.fetch_evidence_chunks`：Sprint 6 批次 B 的「证据片段」
  （``:Chunk`` 文本 + 页码 + 字符区间，供引用回查与 Prompt 注入）。

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any
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

if TYPE_CHECKING:  # 仅类型检查：运行时走函数内延迟导入，避免加长依赖链
    from app.schemas.agent import ReasoningPathHop
    from app.services.rules import (
        AnomalyCaseList,
        AttributionResult,
        ComplianceReport,
    )

#: Sprint 6 批次 B：单次问答注入 Prompt 的证据片段上限。
#: 与 ``_GRAPH_NODE_LIMIT`` 同源思路——片段是**全文**，过量会直接撑爆 Prompt token。
_EVIDENCE_CHUNK_LIMIT = 20


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


@dataclass(frozen=True, slots=True)
class EntitySpan:
    """**Sprint 10 批次 A**：实体在该片段所属的**文档全文**中的字符区间。

    ``char_start`` / ``char_end`` 是**全文绝对偏移**（与 ``:Chunk.char_start`` 同一坐标系），
    换算成 ``Citation.char_offset``（片段内相对偏移）的公式由
    :func:`app.services.agents._to_citation` 独家持有——**换算只此一处**，
    避免"同一事实两处算法"。

    来源：抽取侧 ``ExtractedEntity.char_start/char_end``（Sprint 6 起就有值，
    **入图时被丢弃**，本批次补上）。CSV 派生实体天然无 span ⇒ 不进本列表
    （**不造** span，与零假数据铁律一致）。
    """

    mention: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    """Sprint 6 批次 B：证据片段（``:Chunk`` 投影）。

    与契约层 :class:`DocumentChunkResponse` **刻意分离**：本类是服务层内部
    结构（不进契约），``AgentService`` 用它注入 ``kg_qa`` Prompt 的
    ``text_chunks`` 并回查引用；契约只暴露单条回查端点（Q2）。

    ``doc_id`` 为 ``None`` 表示该 chunk 未挂到任何 ``:Document``
    （``HAS_CHUNK`` 缺失）——此时**不能**构造 ``Citation``（``doc_id`` 是必填 UUID），
    调用方须丢弃，严禁回落到 ``UUID(int=0)`` 这类占位。
    """

    chunk_id: str
    doc_id: UUID | None
    text: str
    page: int | None
    char_start: int
    char_end: int
    #: Sprint 10 批次 A：本片段内**带 span 的实体**（全文绝对偏移，见 :class:`EntitySpan`）。
    #: 用途单一：把引用从"指到哪一段"精确到"指到哪一句"。为空 ⇒ 引用回退为整段。
    entity_spans: tuple[EntitySpan, ...] = ()


# --------------------------------------------------------------------------- #
# Sprint 9 批次 B2（ADR-0005 §6 L1）：读侧的**时态视图**
# --------------------------------------------------------------------------- #


def validate_as_of(as_of: str | None) -> str | None:
    """校验 as-of 日期；格式非法**抛错**而不是静默当作"查当前"。

    静默忽略的后果比报错糟得多：调用方以为在查 2024 年的状态，实际拿到的是
    「现在」的数据——它不会报错，只会在答案里表现为"当时的人明明不是他却答了现在的人"。
    """
    if as_of is None:
        return None
    try:
        datetime.strptime(as_of, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"as_of 必须是 YYYY-MM-DD 格式: {as_of!r}") from exc
    return as_of


def _temporal_view(alias: str = "r") -> str:
    """读侧的时态视图谓词：一段可直接拼进 ``WHERE`` 的 AND 条件。

    ``$as_of`` 为 ``NULL`` ⇒ 只取**当前**关系（``valid_to IS NULL``）；非空 ⇒ 把视图
    倒回那一天：该日之前已成立、且那时尚未失效的关系。**两种视图共用同一段判据**，
    是为了让"默认视图"和"as-of 视图"不可能出现口径漂移。

    .. warning::
       第二个条件的"$as_of 为 NULL"分支**不能**写成 ``$as_of IS NULL OR valid_to IS NULL
       OR valid_to > $as_of``（初版就写错了）：那样 ``NULL`` 时整个条件恒真，
       默认视图会变成"什么都查得到"，旧事实统统混进"当前"。真机用例正是这样
       抓到的（读到 ``['张三', '李四']`` 两条"当前"法定代表人）——**单元测试挡不住这类错，
       因为它错的就是"语义"，只有真跑一遍 Cypher 才能暴露**。

    为什么不各处散写一遍：写入侧的判据已经由
    :func:`app.services.kg.temporal.plan_expiries` 独家守着；读侧若再散落五份
    不同的过滤条件，"答案里一半新事实一半旧事实"就只是时间问题。

    用 ``properties(r)['valid_to']`` 而非 ``r.valid_to``：属性键尚不存在时后者
    会触发 Neo4j 的 ``01N52`` 通知（与既有查询同口径）。

    **M2 的 ``:RELATION`` 边没有这两个属性 ⇒ 谓词恒真**（属性缺失即 NULL）。
    这是预期行为：本期只有 M4 主体层的两条 typed 边纳入时效治理，
    其余关系一律视为有效——不会因为"加了治理"就查不到它们。
    """
    # 两条条件的 OR 结构不同，不要为了"对称"而统一：
    # ① 起始日：as_of 为 NULL 时**不设限**（未来才开始生效的关系也算当前已知事实）；
    # ② 失效日：as_of 为 NULL 时**必须是 NULL**（＝当前值），非空时才放宽到"那天还没失效"。
    return f"""
  AND ($as_of IS NULL OR properties({alias})['valid_from'] IS NULL
       OR properties({alias})['valid_from'] <= $as_of)
  AND (properties({alias})['valid_to'] IS NULL
       OR ($as_of IS NOT NULL AND properties({alias})['valid_to'] > $as_of))
"""


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


#: Sprint 6.3：激活 —— 目标版本置 ``active``、其余置 ``superseded``（**Neo4j 镜像侧**）。
#: PG ``kg_versions`` 才是真源（其 active 语义写作 ``ready``）；这里只同步镜像，
#: **不**反过来用镜像判定。真机背景：建图只写到 PG ``ready``，没人同步镜像，
#: 于是读侧一直拿到旧导入版本（`20260917T090000Z-phase09`，无 `:Chunk`）。
_CYPHER_ACTIVATE_KG_VERSION = """
MERGE (v:KgVersion {version: $version})
SET v.status = 'active',
    v.scope = $scope,
    v.org_id = $org_id,
    v.trace_id = $trace_id,
    v.updated_at = $now
RETURN v.version AS version
"""

_CYPHER_SUPERSEDE_OTHER_VERSIONS = """
MATCH (v:KgVersion)
WHERE v.version <> $version
SET v.status = 'superseded',
    v.updated_at = $now
RETURN v.version AS version
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
#:
#: **Sprint 10 批次 C（裁决 D-K）拆成两段**：
#:
#: 1. :data:`_QUERY_SUBGRAPH_NODE_INDEX` —— 只回 ``id / type / degree`` 的**轻量索引**，
#:    选谁由 :func:`select_subgraph_nodes` 在 Python 侧决定；
#: 2. :data:`_QUERY_SUBGRAPH_BY_IDS` —— 按选中 id 取**完整节点 + 边**。
#:
#: 为什么不在 Cypher 里一步做完：选节点要「按类型保底 + 余量按度数补齐」，Cypher
#: 侧得靠 ``reduce`` 叠加 + ``UNWIND`` 排序，而 **``UNWIND`` 空列表会吞掉整行**
#: （余量为 0 时整条查询返回空 ⇒ 空图，把"没数据"伪装成正常结果）。纯函数则
#: 可单测、可读，且索引查询只传三个字段，不比一次全量投影贵。
_QUERY_SUBGRAPH_NODE_INDEX = """
MATCH (n:Entity {kg_version: $kg_version})
// 用 properties(n)['org_id'] 而非 n.org_id：后者在库中尚无该属性键时
// 会触发 ``01N52 property key does not exist`` 通知（噪声日志）。
WITH n
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
RETURN n.id AS id,
       coalesce(n.entity_type, 'UNKNOWN') AS type,
       size([(n)--() | 1]) AS degree
ORDER BY degree DESC, id
"""

_QUERY_SUBGRAPH_BY_IDS = (
    """
MATCH (n:Entity {kg_version: $kg_version})
WHERE n.id IN $ids
WITH n
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
WITH n ORDER BY n.id
WITH collect(n) AS nodes
RETURN
  nodes,
  [(a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids"""
    + _temporal_view("r")
    + """ | {
    id: coalesce(r.id, elementId(r)),
    type: type(r),
    source: a.id,
    target: b.id,
    properties: properties(r)
  }] AS edges
"""
)


def select_subgraph_nodes(
    rows: Sequence[tuple[str, str, int]],
    limit: int,
) -> list[str]:
    """**问答子图该选哪些节点**（Sprint 10 批次 C，裁决 D-I）。

    口径（真机实测得来，见 ``changes/Sprint10.2/proposal.md`` §2）：

    1. 按 ``entity_type`` 分组；
    2. 每组**保底** ``limit // 类型数`` 个 —— 小类型（``LEAVE`` / ``OVERTIME``）
       不被大类型（``ATTENDANCE_RECORD`` 占全图 30%）饿死；
    3. 组内按 **度数降序 + id 升序** 取 —— 保连通性，且同输入必同解；
    4. 名额没用完的部分按全局度数补齐（不浪费 Prompt 预算）。

    反面教材（都实测过，别再走一遍）：

    - **无序截断**（原实现）：锚点召回 **50%**，12 条问句里 6 条锚点全丢 ⇒
      就是 R12 事故——LLM 答「资料中没有此人信息」却带着引用；
    - **全局度数降序**（图谱概览的口径）：``LEAVE`` 掉到 **0**、``OVERTIME`` 只剩 2，
      问"请假 / 加班"时**制度落点没了**，锚点召回仍是 50%（被挤掉的恰恰是
      问句里那些具体的员工 / 工单）。

    :param rows: ``(id, entity_type, degree)`` 三元组
    :param limit: 节点上限（**不放**大——放大即把成本转嫁给 Prompt token）
    :returns: 选中的节点 id（有序、去重）
    """
    if limit <= 0 or not rows:
        return []

    buckets: dict[str, list[tuple[str, int]]] = {}
    for node_id, entity_type, degree in rows:
        buckets.setdefault(entity_type or "UNKNOWN", []).append((node_id, degree))
    for group in buckets.values():
        group.sort(key=lambda item: (-item[1], item[0]))

    floor = max(limit // len(buckets), 1)
    chosen: list[str] = []
    leftovers: list[tuple[str, int]] = []
    for entity_type in sorted(buckets):
        group = buckets[entity_type]
        chosen.extend(node_id for node_id, _degree in group[:floor])
        leftovers.extend(group[floor:])

    if len(chosen) > limit:
        # 类型数 > 名额（极端情形，如 600 种类型 / 上限 500）：保底抬到 1 之后
        # 就已经超额 ⇒ 按**类型名字典序**截断。字典序是任意的，但确定且可复核；
        # 换成"按度数挑类型"会重新饿死小类型——那正是本方案要避免的。
        return chosen[:limit]

    if len(chosen) < limit:
        leftovers.sort(key=lambda item: (-item[1], item[0]))
        chosen.extend(node_id for node_id, _degree in leftovers[: limit - len(chosen)])
    return chosen


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


#: Sprint 6 批次 B：按实体反查证据片段（``(:Chunk)-[:MENTIONS]->(:Entity)``）。
#: 读侧（``_QUERY_DOCUMENT_SUBGRAPH``）早已按证据链查询，本段把 chunk **文本**取出，
#: 注入 ``kg_qa`` Prompt 的 ``text_chunks``——批次 B「子图注入时携带 chunk 文本」的落点。
#: ``OPTIONAL MATCH`` 取 ``:Document``：chunk 未挂文档时 ``doc_id`` 为 ``null``，
#: 由服务层投影为 ``None``（**不**伪造 UUID）。
_QUERY_EVIDENCE_CHUNKS_BY_ENTITIES = """
MATCH (e:Entity {kg_version: $kg_version})
WHERE e.id IN $entity_ids
  AND ($org_id IS NULL OR e.org_id IS NULL OR e.org_id = $org_id)
MATCH (c:Chunk {kg_version: $kg_version})-[:MENTIONS]->(e)
WHERE $org_id IS NULL OR c.org_id IS NULL OR c.org_id = $org_id
OPTIONAL MATCH (d:Document {kg_version: $kg_version})-[:HAS_CHUNK]->(c)
OPTIONAL MATCH (c)-[:MENTIONS]->(e2:Entity {kg_version: $kg_version})
WHERE e2.char_start IS NOT NULL
WITH DISTINCT c, d,
     collect(DISTINCT {mention: e2.mention,
                       char_start: e2.char_start,
                       char_end: e2.char_end}) AS spans
RETURN
  c.id AS chunk_id,
  d.id AS doc_id,
  c.text AS text,
  c.page AS page,
  c.char_start AS char_start,
  c.char_end AS char_end,
  [s IN spans WHERE s.mention IS NOT NULL] AS spans
LIMIT $limit
"""

#: 同上，“scope = single_doc” 分支：直接从 ``:Document`` 出发取全部 chunk（不看实体）。
_QUERY_EVIDENCE_CHUNKS_BY_DOCUMENT = """
MATCH (d:Document {id: $doc_id, kg_version: $kg_version})
      -[:HAS_CHUNK]->(c:Chunk {kg_version: $kg_version})
WHERE $org_id IS NULL OR c.org_id IS NULL OR c.org_id = $org_id
OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity {kg_version: $kg_version})
WHERE e.char_start IS NOT NULL
WITH DISTINCT c, d,
     collect(DISTINCT {mention: e.mention,
                       char_start: e.char_start,
                       char_end: e.char_end}) AS spans
RETURN
  c.id AS chunk_id,
  d.id AS doc_id,
  c.text AS text,
  c.page AS page,
  c.char_start AS char_start,
  c.char_end AS char_end,
  [s IN spans WHERE s.mention IS NOT NULL] AS spans
LIMIT $limit
"""


#: Sprint 7.1 批次 A（M4 §5.4 第 159 行**照抄**）：共享法人 —— ≥ 2 个 :Subject 由同一
#: :LegalPerson 代表。两点偏离 spec 原文，均为纪律要求而非自由发挥：
#: ① ``s1.id < s2.id`` 代替 ``s1 <> s2``（把 (A,B) / (B,A) 对称对压成一条，
#:    否则同一疑点会出两遍）；② 额外加 ``org_id`` 租户过滤（ADR-0003）——
#:    spec 只按 ``kg_version`` 过滤，但 ``kg_version`` 不等于租户边界。
#: 用 ``properties(n)['org_id']`` 而非 ``n.org_id``：属性键不存在时后者会触发
#: ``01N52 property key does not exist`` 通知（与既有查询同口径）。
_QUERY_SHARED_LEGAL_REP = (
    """
MATCH (s1:Subject)-[rep1:LEGAL_REP]->(l:LegalPerson)<-[rep2:LEGAL_REP]-(s2:Subject)
WHERE s1.id < s2.id
  AND s1.kg_version = $kg_version
  AND s2.kg_version = $kg_version
  AND l.kg_version = $kg_version
  AND ($org_id IS NULL OR properties(s1)['org_id'] IS NULL
       OR properties(s1)['org_id'] = $org_id)
  AND ($org_id IS NULL OR properties(s2)['org_id'] IS NULL
       OR properties(s2)['org_id'] = $org_id)"""
    # **这条查询是时态视图真正生效的地方**：共享法人的判据是「现在是否还由同一人
    # 代表」，旧法定代表人早在旧年就被 R1 封了边 ⇒ 不该再算作疑点（否则年年报警）
    + _temporal_view("rep1")
    + _temporal_view("rep2")
    + """
RETURN
  s1.id AS subject_a_id, s1.name AS subject_a_name,
  s2.id AS subject_b_id, s2.name AS subject_b_name,
  l.id AS shared_id, l.name AS shared_name
ORDER BY subject_a_id, subject_b_id
LIMIT $limit
"""
)

#: Sprint 7.1 批次 A（M4 §5.4 第 154 行**照抄**）：共享地址 —— 同上两处同样偏离。
_QUERY_SHARED_ADDRESS = (
    """
MATCH (s1:Subject)-[reg1:REGISTERED_AT]->(a:Address)<-[reg2:REGISTERED_AT]-(s2:Subject)
WHERE s1.id < s2.id
  AND s1.kg_version = $kg_version
  AND s2.kg_version = $kg_version
  AND a.kg_version = $kg_version
  AND ($org_id IS NULL OR properties(s1)['org_id'] IS NULL
       OR properties(s1)['org_id'] = $org_id)
  AND ($org_id IS NULL OR properties(s2)['org_id'] IS NULL
       OR properties(s2)['org_id'] = $org_id)"""
    # 同上：已迁址的旧地址不再构成「两家公司注册在同一处」的疑点
    + _temporal_view("reg1")
    + _temporal_view("reg2")
    + """
RETURN
  s1.id AS subject_a_id, s1.name AS subject_a_name,
  s2.id AS subject_b_id, s2.name AS subject_b_name,
  a.id AS shared_id, a.full_address AS shared_name
ORDER BY subject_a_id, subject_b_id
LIMIT $limit
"""
)

#: Sprint 9.12 批次 C2（spec §4.7.2）：**共享电话** —— 与共享法人 / 地址同构
#: （``s1.id < s2.id`` 对称去重 + ``org_id`` 租户过滤，两处偏离的理由见上）。
_QUERY_SHARED_PHONE = """
MATCH (s1:Subject)-[:CONTACT_PHONE]->(p:Phone)<-[:CONTACT_PHONE]-(s2:Subject)
WHERE s1.id < s2.id
  AND s1.kg_version = $kg_version
  AND s2.kg_version = $kg_version
  AND p.kg_version = $kg_version
  AND ($org_id IS NULL OR properties(s1)['org_id'] IS NULL
       OR properties(s1)['org_id'] = $org_id)
  AND ($org_id IS NULL OR properties(s2)['org_id'] IS NULL
       OR properties(s2)['org_id'] = $org_id)
RETURN s1.id AS subject_a_id, s1.canonical_name AS subject_a_name,
       s2.id AS subject_b_id, s2.canonical_name AS subject_b_name,
       p.id AS shared_id, p.canonical_name AS shared_name
ORDER BY subject_a_id, subject_b_id
LIMIT $limit
"""

#: Sprint 9.12 批次 C2（spec §4.7.2）：**持股环** —— ``SHARES_HOLDER`` 有向环，
#: 长度 **2..4**（2 = 交叉持股，必须算；> 4 路径爆炸且审计难解释，判据里已定）。
#:
#: 去重：同一个环会被环上每个节点各遍历一次 ⇒ 只保留「**起点 = 环上最小 id**」的那次
#: （``reduce`` 求最小值，不用 apoc——社区版不一定装 APOC，且这里不需要）。
_QUERY_SHAREHOLDER_CYCLE = """
MATCH p = (s:Subject {kg_version: $kg_version})-[:SHARES_HOLDER*2..4]->(s)
WHERE ALL(n IN nodes(p) WHERE n.kg_version = $kg_version
      AND ($org_id IS NULL OR properties(n)['org_id'] IS NULL
           OR properties(n)['org_id'] = $org_id))
WITH p, s, [n IN nodes(p) | n.id] AS ids,
     [n IN nodes(p) | coalesce(n.canonical_name, n.id)] AS names
WITH p, s, ids, names,
     reduce(m = ids[0], x IN ids | CASE WHEN x < m THEN x ELSE m END) AS min_id
WHERE s.id = min_id
RETURN DISTINCT ids[0..size(ids) - 1] AS cycle_ids,
       names[0..size(names) - 1] AS cycle_names,
       length(p) AS cycle_length
ORDER BY cycle_length, cycle_ids
LIMIT $limit
"""

#: Sprint 9.12 批次 C2（spec §4.7.2）：**三方金额不一致** —— 同一 ``trade_ref`` 上
#: 合同 / 发票 / 凭证金额**不全相等**。
#:
#: **三方必须齐**：任一方缺失 ⇒ 该 trade_ref 直接不匹配（spec 明写「三方」，
#: 不拿两方不等冒充三方不一致）。``<`` 严格不等号避免 (A,B,A) 这类组合重复。
_QUERY_AMOUNT_MISMATCH = """
MATCH (c:Contract {kg_version: $kg_version}),
      (i:Invoice {kg_version: $kg_version}),
      (v:Voucher {kg_version: $kg_version})
WHERE c.trade_ref IS NOT NULL
  AND c.trade_ref = i.trade_ref
  AND i.trade_ref = v.trade_ref
  AND NOT (c.amount = i.amount AND i.amount = v.amount)
  AND ($org_id IS NULL OR properties(c)['org_id'] IS NULL
       OR properties(c)['org_id'] = $org_id)
  AND ($org_id IS NULL OR properties(i)['org_id'] IS NULL
       OR properties(i)['org_id'] = $org_id)
  AND ($org_id IS NULL OR properties(v)['org_id'] IS NULL
       OR properties(v)['org_id'] = $org_id)
RETURN c.trade_ref AS trade_ref,
       c.id AS contract_id, i.id AS invoice_id, v.id AS voucher_id,
       c.amount AS contract_amount, i.amount AS invoice_amount,
       v.amount AS voucher_amount,
       c.canonical_name AS contract_name,
       i.canonical_name AS invoice_name,
       v.canonical_name AS voucher_name
ORDER BY trade_ref
LIMIT $limit
"""

#: Sprint 7.1 批次 A：疑点证据 —— 由主体层节点（``:Subject`` / ``:LegalPerson`` /
#: ``:Address``）经 ``source_entity_ids`` 溯源到 M2 ``:Entity``，再走 S6 的
#: ``(:Chunk)-[:MENTIONS]->(:Entity)`` 反查原文片段（tasks §2.3 明确要求复用 :Chunk）。
#: **不**回退到「按名字模糊匹配 Entity」——那等于在两层之间偷偷搭了一座文本桥。
#:
#: **Sprint 9.12 扩白名单（理由必须写明）**：新增 ``:Phone`` / ``:Invoice`` /
#: ``:Voucher`` / ``:Contract``。spec §3 验收 4 要求每条疑点都能回溯到**具体合同 /
#: 发票 / 凭证**；而 ``amount_mismatch`` 的三个端点正是 ``:Contract`` / ``:Invoice`` /
#: ``:Voucher``（§4.7.2）——白名单不含它们 ⇒ 该类疑点**必然**取不到证据 ⇒ 被
#: 「无证据不产疑点」规则整类丢弃（**沉默的零产出**，比报错更难查）。
_QUERY_AFFILIATION_EVIDENCE = """
MATCH (n {kg_version: $kg_version})
WHERE n.id IN $node_ids
  AND (n:Subject OR n:LegalPerson OR n:Address OR n:Phone
       OR n:Invoice OR n:Voucher OR n:Contract)
  AND ($org_id IS NULL OR properties(n)['org_id'] IS NULL
       OR properties(n)['org_id'] = $org_id)
UNWIND coalesce(n.source_entity_ids, []) AS eid
MATCH (c:Chunk {kg_version: $kg_version})-[:MENTIONS]->(e:Entity {id: eid, kg_version: $kg_version})
WHERE $org_id IS NULL OR properties(c)['org_id'] IS NULL
   OR properties(c)['org_id'] = $org_id
OPTIONAL MATCH (d:Document {kg_version: $kg_version})-[:HAS_CHUNK]->(c)
RETURN DISTINCT
  n.id AS node_id,
  c.id AS chunk_id,
  d.id AS doc_id,
  c.text AS text,
  c.page AS page,
  c.char_start AS char_start,
  c.char_end AS char_end
ORDER BY node_id, chunk_id
LIMIT $limit
"""

#: 批次 C：全局图谱概览的 Cypher（节点轻量投影 + 全部边）。
#: 与 :data:`_QUERY_SUBGRAPH_BY_IDS`（问答注入用）不同：去掉了 ``total_nodes`` 字段（由服务层算），
#: 投影阶段只取 ``id`` / ``canonical_name`` / ``type`` / ``category`` 4 个字段。
#: 节点选取按**度数降序**（连接数多的枢纽优先，平局按 `id` 保证确定性）：
#: 此前是 `all_nodes[0..$node_limit]` 无序截断——任意前 500 个节点之间几乎没有边
#: （真机实测 500 节点仅 36 边，画出来全是孤点噪云），违背「保护前端渲染」的初衷。
_QUERY_GRAPH_OVERVIEW = (
    """
MATCH (n:Entity {kg_version: $kg_version})
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
WITH n, size([(n)--() | 1]) AS degree
ORDER BY degree DESC, n.id
WITH collect(n) AS all_nodes
WITH all_nodes[0..$node_limit] AS nodes, size(all_nodes) AS total_nodes
RETURN
  nodes,
  total_nodes,
  [(a)-[r]->(b) WHERE a IN nodes AND b IN nodes AND (a <> b)"""
    + _temporal_view("r")
    + """ | {
    id: coalesce(r.id, elementId(r)),
    type: type(r),
    source: a.id,
    target: b.id,
    properties: properties(r)
  }] AS edges
"""
)


#: 批次 C：实体详情 —— 单节点 + 1 跳出边邻居（带方向过滤：仅取指向其它 Entity 的边）。
#: ``has_neighbor_more`` 表示是否还有更多邻居（用于前端分页 / 「展开更多」按钮）。
_QUERY_ENTITY_DETAIL = (
    """
MATCH (e:Entity {id: $entity_id, kg_version: $kg_version})
WHERE $org_id IS NULL
   OR properties(e)['org_id'] IS NULL
   OR properties(e)['org_id'] = $org_id
OPTIONAL MATCH (e)-[r]->(n:Entity {kg_version: $kg_version})
WHERE n <> e
  AND ($org_id IS NULL
       OR properties(n)['org_id'] IS NULL
       OR properties(n)['org_id'] = $org_id)"""
    # r 为 null（OPTIONAL MATCH 无命中）时谓词恒真 ⇒ 行为与加之前一致
    + _temporal_view("r")
    + """
WITH e,
     collect({rel: r, neighbor: n}) AS all_neighbors
WITH e,
     all_neighbors[0..$neighbor_limit] AS first_page,
     size(all_neighbors) > $neighbor_limit AS has_more
RETURN
  e,
  first_page,
  has_more,
  size([(e)-[r2]->(:Entity {kg_version: $kg_version}) | r2]) AS out_degree,
  size([(:Entity {kg_version: $kg_version})-[r3]->(e) | r3]) AS in_degree
"""
)


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

    def fetch_active_kg_version(
        self,
        *,
        scope: str | None = None,
        org_id: UUID | None = None,
        db: Any = None,
    ) -> KgVersion:
        """返回**唯一**可消费版本。

        **真源策略（Sprint 6.3 收口，真机教训）**：
        - 传入 ``db`` + ``org_id`` 时以 **PG ``kg_versions`` 为真源**（``status='ready'``
          即 active 语义，取 ``ready_at`` 最新的一条）；PG 说没有就抛
          ``NoActiveKgVersionError``，**不**回落到 Neo4j 镜像（否则又会把「未激活」
          伪装成「命中旧版本」——真机正是这样拿到无 ``:Chunk`` 的旧版本）。
        - 未传 ``db``（脚本 / 无会话的内部调用）才走 Neo4j ``:KgVersion`` 兜底。

        ``writing`` / ``failed`` 版本一律**不**返回，从源头杜绝脏读。
        """
        if db is not None and org_id is not None:
            # 延迟导入：避免 graphs（被 agents 依赖）在模块级牵上 db 会话依赖
            from app.services.kg.versioning import KgVersioningService

            record = KgVersioningService(db).get_active(org_id=org_id)
            if record is None:
                raise NoActiveKgVersionError(
                    "PG kg_versions 中无 ready 版本（PG 为真源；"
                    "请先建图并调用 POST /graph/versions/{version}/activate）"
                )
            logger.bind(version=record.version, source="pg").debug(
                "kg_version_active_resolved"
            )
            return KgVersion(version=record.version, scope="global")

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

    def activate_kg_version(
        self, *, version: str, org_id: UUID, trace_id: str
    ) -> list[str]:
        """同步 **Neo4j 镜像**：目标版本置 ``active``，其余置 ``superseded``。

        真源判定在 PG（:meth:`KgVersioningService.activate_by_version`）；本方法只做
        镜像写入，供「无 db 会话」的读路径（:meth:`fetch_active_kg_version` 的 Neo4j
        兜底分支、脚本）保持一致。

        :returns: 本次被置 ``superseded`` 的版本号列表（可为空）
        :raises GraphUnavailableError: Neo4j 不可用 / 写入失败
        """
        now = datetime.now(UTC).isoformat()
        try:
            with self._session() as session:
                superseded = [
                    str(record["version"])
                    for record in session.run(
                        _CYPHER_SUPERSEDE_OTHER_VERSIONS, version=version, now=now
                    )
                ]
                session.run(
                    _CYPHER_ACTIVATE_KG_VERSION,
                    version=version,
                    scope="global",
                    org_id=str(org_id),
                    trace_id=trace_id,
                    now=now,
                ).consume()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"激活 kg_version 镜像失败: version={version}: {exc}"
            ) from exc

        logger.bind(version=version, superseded=superseded, trace_id=trace_id).info(
            "kg_version_mirror_activated"
        )
        return superseded

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
        db: Any = None,
        as_of: str | None = None,
    ) -> tuple[list[GraphNode], list[GraphEdge], bool]:
        """取**全部**已导入实体子图，不依赖 PG ``document_id``。

        Sprint 9 批次 B2 新增 ``as_of``：默认只投影**当前**关系；传入日期则把整张
        子图倒回那一天——"三年前这张图长什么样"这个问题从此有确定答案。

        用于 ``bridge_web_demo`` 阶段六产物（``:Entity`` 实体图）的查询与可视化。
        若 ``kg_version`` 为 ``None``，自动取 :meth:`fetch_active_kg_version`
        （**始终**只查 active 版本，ADR-0002 §3.2）。

        :returns: ``(nodes, edges, truncated)``
        """
        if node_limit <= 0:
            raise ValueError("node_limit 必须为正整数")

        version = (
            kg_version or self.fetch_active_kg_version(org_id=org_id, db=db).version
        )

        org_param = str(org_id) if org_id else None
        try:
            with self._session() as session:
                # ① 轻量索引（id / 类型 / 度数）→ ② Python 侧选节点 → ③ 按 id 取节点 + 边
                index = [
                    (row["id"], row["type"], int(row["degree"] or 0))
                    for row in session.run(
                        _QUERY_SUBGRAPH_NODE_INDEX,
                        kg_version=version,
                        org_id=org_param,
                    )
                ]
                selected = select_subgraph_nodes(index, node_limit)
                if not selected:
                    return [], [], False
                result = session.run(
                    _QUERY_SUBGRAPH_BY_IDS,
                    kg_version=version,
                    org_id=org_param,
                    ids=selected,
                    as_of=validate_as_of(as_of),
                ).single()
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询全量实体子图失败: kg_version={version}: {exc}"
            ) from exc

        if result is None:
            return [], [], False

        total_nodes = len(index)
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

    def fetch_evidence_chunks(
        self,
        *,
        kg_version: str,
        org_id: UUID | None = None,
        entity_ids: Sequence[str] = (),
        doc_id: UUID | None = None,
        limit: int = _EVIDENCE_CHUNK_LIMIT,
    ) -> list[EvidenceChunk]:
        """取证据片段（Sprint 6 批次 B）：``:Chunk`` 文本 + 页码 + 字符区间。

        两条取数路径，与 :meth:`AgentService._fetch_subgraph_for_question` 的
        ``scope`` 语义对齐：

        - ``doc_id`` 非空（``scope = single_doc``）→ 从 ``:Document`` 直达；
        - 否则按 ``entity_ids`` 经 ``MENTIONS`` 反查（跨文档）。

        两者都为空 → 返回空列表（**不**全量扫描 chunk，避免把无关原文喂给 LLM）。

        :raises GraphUnavailableError: Neo4j 不可用，或原始数据与投影契约不符
            （沿用设计要点 5：失败即显式暴露，**不**静默返回空列表——
            空片段会让上层误判为「图谱里没有证据」而拒答）。
        """
        if limit <= 0:
            raise ValueError("limit 必须为正整数")

        if doc_id is not None:
            query = _QUERY_EVIDENCE_CHUNKS_BY_DOCUMENT
            params: dict[str, Any] = {
                "kg_version": kg_version,
                "org_id": str(org_id) if org_id else None,
                "doc_id": str(doc_id),
                "limit": limit,
            }
        elif entity_ids:
            query = _QUERY_EVIDENCE_CHUNKS_BY_ENTITIES
            params = {
                "kg_version": kg_version,
                "org_id": str(org_id) if org_id else None,
                "entity_ids": list(entity_ids),
                "limit": limit,
            }
        else:
            return []

        try:
            with self._session() as session:
                records = list(session.run(query, **params))
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询证据片段失败: kg_version={kg_version}: {exc}"
            ) from exc

        projection_context = f"fetch_evidence_chunks kg_version={kg_version}"
        chunks: list[EvidenceChunk] = []
        for index, record in enumerate(records):
            try:
                chunks.append(_to_evidence_chunk(record))
            except Exception as exc:  # noqa: BLE001 - 投影失败必须显式暴露
                logger.bind(
                    context=projection_context, kind="chunk", record_index=index
                ).warning("graph_projection_failed")
                raise GraphUnavailableError(
                    _projection_failure_message(
                        context=projection_context,
                        kind="chunk",
                        label=None,
                        index=index,
                        exc=exc,
                    )
                ) from exc
        return chunks

    # ------------------------------------------------- Sprint 7.1 批次 A（M4）

    def fetch_shared_affiliations(
        self,
        *,
        kg_version: str,
        org_id: UUID | None = None,
        limit: int = 100,
        as_of: str | None = None,
    ) -> list[dict[str, Any]]:
        """M4 两跳查询：**共享法人** + **共享地址**（``specs/m4-affiliation-detection.md`` §5.4）。

        Sprint 9 批次 B2 新增 ``as_of``：共享法人 / 地址的判据是「**现在**是否仍由
        同一人代表 / 同一地址注册」。旧法定代表人早在当年就被 R1 封了边，
        若不过滤有效期，这条疑点会**年复一年地报警**——属 D-3 要防的
        「把历史关系当现状」最典型的形态。

        :returns: ``[{"suspicion_type": "shared_legal_rep"|"shared_address",
            "subject_a_id", "subject_a_name", "subject_b_id", "subject_b_name",
            "shared_id", "shared_name"}, ...]``；先法人后地址，各自按 id 排序。
        :raises GraphUnavailableError: Neo4j 不可用（**不**静默返回 []——
            空列表会被上层误读成「没有疑点」，与「没有跑成」无法区分）。
        """
        records: list[dict[str, Any]] = []
        for suspicion_type, query in (
            ("shared_legal_rep", _QUERY_SHARED_LEGAL_REP),
            ("shared_address", _QUERY_SHARED_ADDRESS),
        ):
            try:
                with self._session() as session:
                    rows = list(
                        session.run(
                            query,
                            kg_version=kg_version,
                            org_id=str(org_id) if org_id else None,
                            limit=limit,
                            as_of=validate_as_of(as_of),
                        )
                    )
            except GraphUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一包装
                raise GraphUnavailableError(
                    f"查询共享{suspicion_type}失败: kg_version={kg_version}: {exc}"
                ) from exc
            for row in rows:
                records.append({"suspicion_type": suspicion_type, **dict(row)})
        return records

    def fetch_algorithm_suspicions(
        self,
        *,
        kg_version: str,
        org_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Sprint 9.12 批次 C2：**三类图算法 + 三方金额不一致**（spec §4.7.2）。

        与 :meth:`fetch_shared_affiliations`（规则型两跳）分开暴露，是因为**形状不同**：
        规则型固定是「主体A + 主体B + 共享节点」，而算法型是「N 个主体」/「三方单据」。
        硬塞进同一个返回结构会让上层靠字段名猜类型——那正是要避免的。

        :returns: ``[{"suspicion_type", "entities": [...], "entity_names": [...],
            "details": {...}|None}, ...]``（``shared_phone`` 走共享节点的三元形状，
            故也归一成 ``entities`` 列表）。
        :raises GraphUnavailableError: Neo4j 不可用（**不**静默返回 []）。
        """
        records: list[dict[str, Any]] = []

        def _run(query: str, **params: Any) -> list[Any]:
            try:
                with self._session() as session:
                    return list(session.run(query, **params))
            except GraphUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一包装
                raise GraphUnavailableError(
                    f"查询算法疑点失败: kg_version={kg_version}: {exc}"
                ) from exc

        org = str(org_id) if org_id else None

        for row in _run(
            _QUERY_SHARED_PHONE, kg_version=kg_version, org_id=org, limit=limit
        ):
            records.append(
                {
                    "suspicion_type": "shared_phone",
                    "entities": [
                        str(row["subject_a_id"]),
                        str(row["subject_b_id"]),
                        str(row["shared_id"]),
                    ],
                    "entity_names": [
                        str(row["subject_a_name"]),
                        str(row["subject_b_name"]),
                        str(row["shared_name"]),
                    ],
                    "details": None,
                }
            )

        for row in _run(
            _QUERY_SHAREHOLDER_CYCLE, kg_version=kg_version, org_id=org, limit=limit
        ):
            cycle_ids = [str(item) for item in row["cycle_ids"]]
            records.append(
                {
                    "suspicion_type": "cycle",
                    "entities": cycle_ids,
                    "entity_names": [str(item) for item in row["cycle_names"]],
                    "details": {"cycle_length": int(row["cycle_length"])},
                }
            )

        for row in _run(
            _QUERY_AMOUNT_MISMATCH, kg_version=kg_version, org_id=org, limit=limit
        ):
            amounts = [
                float(row["contract_amount"]),
                float(row["invoice_amount"]),
                float(row["voucher_amount"]),
            ]
            records.append(
                {
                    "suspicion_type": "amount_mismatch",
                    "entities": [
                        str(row["contract_id"]),
                        str(row["invoice_id"]),
                        str(row["voucher_id"]),
                    ],
                    "entity_names": [
                        str(row["contract_name"]),
                        str(row["invoice_name"]),
                        str(row["voucher_name"]),
                    ],
                    # spec §3 验收 5：必须给出「差额 + 三方各自金额」的明细
                    "details": {
                        "trade_ref": str(row["trade_ref"]),
                        "contract_amount": amounts[0],
                        "invoice_amount": amounts[1],
                        "voucher_amount": amounts[2],
                        "max_diff": round(max(amounts) - min(amounts), 2),
                    },
                }
            )
        return records

    def fetch_affiliation_evidence(
        self,
        *,
        kg_version: str,
        node_ids: Sequence[str],
        org_id: UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """疑点证据：主体层节点 → 源实体 → ``:Chunk`` 原文片段（含 ``node_id`` 归属）。

        ``node_id`` 是区分「这条证据支撑的是哪家公司 / 哪个法人」的关键——没有它，
        证据就退化成一堆无主的原文片段，前端无法做「可点击」。
        """
        if not node_ids:
            return []
        try:
            with self._session() as session:
                rows = list(
                    session.run(
                        _QUERY_AFFILIATION_EVIDENCE,
                        kg_version=kg_version,
                        node_ids=list(node_ids),
                        org_id=str(org_id) if org_id else None,
                        limit=limit,
                    )
                )
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装
            raise GraphUnavailableError(
                f"查询疑点证据失败: kg_version={kg_version}: {exc}"
            ) from exc
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ 批次 C

    def fetch_graph_overview(
        self,
        *,
        org_id: UUID | None = None,
        trace_id: str,
        node_limit: int = _GRAPH_OVERVIEW_NODE_LIMIT,
        db: Any = None,
        as_of: str | None = None,
    ) -> GraphOverviewResponse:
        """全局图谱概览（`GET /graph/overview`，Sprint 5 批次 C）。

        返回 ``(nodes, edges, truncated)`` + ``doc_count`` / ``entity_count`` /
        ``relation_count`` 三个统计值 + active ``kg_version``。统计值与节点
        上限 500 **不同**：统计覆盖**完整** active kg_version（PG ``kg_versions``
        落库时已回填），仅节点 / 边投影按 ``node_limit`` 截断以保护前端渲染。

        :raises GraphUnavailableError: Neo4j 连接 / 查询失败（路由层 501）
        :raises NoActiveKgVersionError: 无 active 版本（路由层 409）
        """
        version = self.fetch_active_kg_version(org_id=org_id, db=db).version
        stats = self._fetch_graph_overview_stats(version=version, org_id=org_id, db=db)

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_GRAPH_OVERVIEW,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    node_limit=node_limit,
                    as_of=validate_as_of(as_of),
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
            categories=_load_entity_type_categories(org_id=org_id, db=db),
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
        self, *, version: str, org_id: UUID | None, db: Any = None
    ) -> dict[str, int]:
        """读取 overview 所需的统计值（doc_count / entity_count / relation_count）。

        **真源策略**：复用 PG ``kg_versions.entity_count`` / ``relation_count``
        （Sprint 5 批次 B 起 PG 为真源，``mark_ready`` 时回填）。**不**通过 Cypher
        ``count(n)`` —— 避免对大图谱做一次额外的全表扫描。

        ``doc_count`` 单独统计：**只数 ``kg_version_id`` 指向当前 active 版本
        （``kg_versions.id``）的文档**——不把历史版本的文档混进 active 视图
        （ADR-0002 §3.2：只读 active、严禁静默降级）。契约描述亦为「当前租户下有
        active kg_version 的文档数」。

        .. note::
           2026-09-26 修复：此前本方法**直接返回三个 0**并注释「实际实现见
           ``GraphOverviewRoute._load_stats_from_pg()``」——而路由层**根本没有**该方法，
           导致 `GET /graph/overview` 的三个计数**恒为 0**（静默假数据：节点 / 边是真的，
           只有计数是假的）。占位必须**显式报错**，绝不能返回 0 冒充统计值。

        :raises ValueError: ``db`` / ``org_id`` 缺失（调用方漏传，属编程错误）
        :raises NoActiveKgVersionError: PG 中查不到该版本的统计行（真源缺失）
        """
        if db is None or org_id is None:
            raise ValueError(
                "overview 统计值必须来自 PG 真源：db / org_id 缺失时禁止返回 0 冒充"
                f"（db={db!r}, org_id={org_id!r}）"
            )

        # 延迟导入：避免 graphs（被 agents 依赖）在模块级牵上 db 会话依赖
        from sqlalchemy import func, select

        from app.db.models import Document
        from app.services.kg.versioning import KgVersioningService

        record = KgVersioningService(db).get_by_version(org_id=org_id, version=version)
        if record is None:
            raise NoActiveKgVersionError(
                f"PG kg_versions 中无 version={version} 的统计行"
                "（统计真源缺失，拒绝返回 0 冒充）"
            )

        doc_count = int(
            db.execute(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.org_id == org_id,
                    Document.kg_version_id == record.id,
                )
            ).scalar_one()
        )

        return {
            "doc_count": doc_count,
            "entity_count": int(record.entity_count),
            "relation_count": int(record.relation_count),
        }

    def fetch_entity_detail(
        self,
        *,
        entity_id: str,
        org_id: UUID | None = None,
        trace_id: str,
        neighbor_limit: int = _ENTITY_NEIGHBOR_LIMIT,
        db: Any = None,
        as_of: str | None = None,
    ) -> EntityDetail:
        """实体详情（`GET /entities/{entity_id}`，Sprint 5 批次 C）。

        查询范围：当前 active kg_version 内、``Entity`` 标签节点 + 1 跳出边邻居。

        Sprint 9 批次 B2 新增 ``as_of``：**默认**只展示未被取代的关系
        （``valid_to IS NULL``）；传入 ``YYYY-MM-DD`` 则把邻居视图倒回那一天。
        不存在（无该实体节点 / org_id 不符）→ 抛 :class:`EntityNotFoundError` 或
        :class:`GraphUnavailableError`，由路由层分别转 ``404 ENTITY_NOT_FOUND`` /
        ``501 NOT_IMPLEMENTED``。

        :raises EntityNotFoundError: 实体不存在（路由层 404）
        :raises GraphUnavailableError: Neo4j 不可用 / Cypher 失败（路由层 501）
        :raises NoActiveKgVersionError: 无 active 版本（路由层 409）
        """
        if neighbor_limit <= 0:
            raise ValueError("neighbor_limit 必须为正整数")

        version = self.fetch_active_kg_version(org_id=org_id, db=db).version

        try:
            with self._session() as session:
                result = session.run(
                    _QUERY_ENTITY_DETAIL,
                    entity_id=entity_id,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    neighbor_limit=neighbor_limit,
                    as_of=validate_as_of(as_of),
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
        # ``EntityDetail.entity_type`` / ``GraphOverviewNode.type`` 契约是 ``str``
        # （非 ``str | None``）⇒ 缺失回落 ""，与改前行为一致。
        entity_type_raw = str(_entity_type_from_properties(properties) or "")
        category = _resolve_category(
            entity_type_raw,
            categories=_load_entity_type_categories(org_id=org_id, db=db),
        )

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
                    relation=_relation_name(rel),
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

    # ------------------------------------------------- Sprint 9.5 批次 D1

    def fetch_reasoning_path(
        self,
        *,
        kg_version: str,
        org_id: Any,
        question: str,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge] = (),
        chunks: Sequence[EvidenceChunk] = (),
    ) -> list[ReasoningPathHop]:
        """M3 多跳推理路径（``reasoning_path`` 的服务层入口）。

        **会话只由本类开**（与 :meth:`scan_attendance_compliance` 同口径）：
        调用方拿不到"私自开连接"的口子，``kg_version`` 由上游
        :meth:`fetch_active_kg_version` 给定，杜绝绕过版本真源。

        **延迟导入** :mod:`app.services.reasoning`：本模块被 ``agents`` 依赖，
        模块级牵上会加长依赖链（且 ``reasoning`` 只依赖 schema，无循环风险）。

        :returns: 逐跳链；零命中为 ``[]``（``None`` 的语义留给拒答分支，见契约）
        :raises GraphUnavailableError: Neo4j 不可用 / 查询失败（**不**静默返回
            ``[]``——空路径会被上层当成"图上没有链"，把故障伪装成正常结论）
        """
        from app.services.reasoning import build_reasoning_path  # 延迟导入

        try:
            with self._session() as session:
                return build_reasoning_path(
                    session=session,
                    kg_version=kg_version,
                    org_id=str(org_id) if org_id is not None else "",
                    question=question,
                    nodes=nodes,
                    edges=edges,
                    chunks=chunks,
                )
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装为图不可用
            raise GraphUnavailableError(
                f"推理路径查询失败: kg_version={kg_version}: {exc}"
            ) from exc

    def fetch_anchor_entity_ids(
        self,
        *,
        kg_version: str,
        org_id: Any,
        question: str,
        nodes: Sequence[GraphNode],
    ) -> tuple[str, ...]:
        """本次问句的锚点实体 id（供**证据注入**与推理路径共用）。

        **为什么要单独开这个入口**（2026-09-28 真机事故）：证据注入的
        ``entity_ids`` 原本只取 ``fetch_all_subgraph(node_limit=500)`` 的节点。
        子图采样会把锚点类型挤掉 ⇒ 问「李静的月加班…」时 ``EMPLOYEE:E002``
        不在那 500 个节点里 ⇒ 注入的只有制度 chunk ⇒ LLM 答
        「资料中没有李静的任何信息」**却带着 1 条引用**（引的是制度条款）。
        答案与引用不符，比拒答更危险。与推理路径共用同一套锚点即可闭合。

        :raises GraphUnavailableError: Neo4j 不可用（**不**返回空——空会让
            上层以为"这个问题没有锚点"，把故障伪装成正常结论）
        """
        from app.services.reasoning import resolve_anchors  # 延迟导入

        try:
            with self._session() as session:
                return resolve_anchors(
                    session=session,
                    kg_version=kg_version,
                    org_id=str(org_id) if org_id is not None else "",
                    question=question,
                    nodes=nodes,
                )
        except GraphUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装为图不可用
            raise GraphUnavailableError(
                f"锚点查询失败: kg_version={kg_version}: {exc}"
            ) from exc

    # ------------------------------------------------- Sprint 9.5 批次 C3

    def scan_attendance_compliance(
        self,
        *,
        org_id: UUID | None = None,
        db: Any = None,
        as_of: date | None = None,
    ) -> ComplianceReport:
        """考勤域合规扫描（``GET /attendance/compliance/scan`` 的服务层入口）。

        **为什么放在这里而不是路由里直接开 driver**：``kg_version`` 必须由
        :meth:`fetch_active_kg_version` 决定（PG 为真源、只读 active），
        而 Neo4j session 只由本类的懒加载 driver 产出。两者都在本类内 ⇒
        路由层拿不到「私自开连接」的口子，杜绝绕过版本真源。

        **延迟导入** ``app.services.rules``：``graphs`` 被 ``agents`` 依赖，
        在模块级牵上规则引擎会加长依赖链；且规则引擎本身不依赖本模块，无循环风险。

        :raises NoActiveKgVersionError: 无 active 版本（路由层 409）
        :raises GraphUnavailableError: Neo4j 不可用（路由层 501）
        :raises ComplianceScanError: 版本里没有考勤事实（路由层 409 ``COMPLIANCE_NO_FACTS``）
        """
        from app.services.rules import (  # 延迟导入：缩短依赖链
            ComplianceScanError,
            scan_compliance,
        )

        version = self.fetch_active_kg_version(org_id=org_id, db=db).version
        try:
            with self._session() as session:
                return scan_compliance(
                    session=session,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    as_of=as_of,
                )
        except NoActiveKgVersionError:
            raise
        except GraphUnavailableError:
            raise
        except ComplianceScanError:
            # **不是**基础设施故障：库是通的、版本是对的，只是这份图里没有考勤数据。
            # 包装成 GraphUnavailableError 会让前端看到 501「服务不可用」——错报。
            raise
        except Exception as exc:  # noqa: BLE001 - 其余一律视为图不可用
            raise GraphUnavailableError(
                f"合规扫描失败: kg_version={version}: {exc}"
            ) from exc

    # ------------------------------------------------- Sprint 9.5 批次 C4

    def list_attendance_anomalies(
        self,
        *,
        org_id: UUID | None = None,
        db: Any = None,
        employee_id: str | None = None,
    ) -> AnomalyCaseList:
        """列出待归因的考勤异常（``GET /attendance/anomalies`` 的服务层入口）。

        **空列表是正常结果**（这份图里没人缺卡），**不是**失败——与合规扫描不同，
        那边「扫不到事实」要显式报错，这边「没有异常」正是想听到的答案。
        """
        from app.services.rules import list_anomaly_cases

        version = self.fetch_active_kg_version(org_id=org_id, db=db).version
        try:
            with self._session() as session:
                return list_anomaly_cases(
                    session=session,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    employee_id=employee_id,
                )
        except (NoActiveKgVersionError, GraphUnavailableError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise GraphUnavailableError(
                f"异常清单查询失败: kg_version={version}: {exc}"
            ) from exc

    def explain_attendance_anomaly(
        self,
        *,
        org_id: UUID | None = None,
        db: Any = None,
        employee_id: str,
        day: date | None = None,
    ) -> tuple[str, AttributionResult]:
        """给一条考勤异常做归因（``GET /attendance/anomalies/explain`` 的服务层入口）。

        返回 ``(kg_version, 归因结论)``——``AttributionResult`` 本身不带版本，
        而响应必须标出「这次归因读的是哪张图」。

        ``day`` 缺省时取该员工的**第一个**异常日（与 CLI 同口径）。

        :raises AnomalyNotFoundError: 员工不在图上 / 该日没有异常记录
            （路由层 404；**不**返回零证据的归因结果冒充「不成立」）
        """
        from app.services.rules import (
            AnomalyNotFoundError,
            attribute_absence,
            employee_name,
            find_anomaly_days,
        )

        version = self.fetch_active_kg_version(org_id=org_id, db=db).version
        try:
            with self._session() as session:
                if day is None:
                    days = find_anomaly_days(
                        session=session,
                        kg_version=version,
                        org_id=str(org_id) if org_id else None,
                        employee_id=employee_id,
                    )
                    if not days:
                        raise AnomalyNotFoundError(
                            f"员工 {employee_id} 在 kg_version={version} 内没有异常记录"
                        )
                    day = date.fromisoformat(days[0])

                result = attribute_absence(
                    session=session,
                    kg_version=version,
                    org_id=str(org_id) if org_id else None,
                    employee_id=employee_id,
                    day=day,
                    # 姓名要显式查：`attribute_absence` 默认空串，不传响应里就是「E001 」
                    employee_name=employee_name(
                        session=session,
                        kg_version=version,
                        org_id=str(org_id) if org_id else None,
                        employee_id=employee_id,
                    ),
                )
                return version, result
        except (NoActiveKgVersionError, GraphUnavailableError, AnomalyNotFoundError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise GraphUnavailableError(
                f"异常归因失败: kg_version={version}: {exc}"
            ) from exc


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
        entity_type=(
            _entity_type_from_properties(dict(record)) if label == "Entity" else None
        ),
        canonical_name=record.get("canonical_name"),
        confidence=_safe_float(record.get("confidence")),
        kg_version=kg_version,
    )


def _to_evidence_chunk(record: Any) -> EvidenceChunk:
    """把证据片段 record 投影为 :class:`EvidenceChunk`（Sprint 6 批次 B）。

    与 :func:`_to_node` 同族：字段非法**抛**而不是兜底——
    ``doc_id`` 不是合法 UUID 时尤其不能静默置 ``None``，
    否则上层会把「数据坏了」当成「这个 chunk 没挂文档」而丢弃证据。
    """
    chunk_id = str(record.get("chunk_id") or "")
    raw_doc_id = record.get("doc_id")
    doc_id: UUID | None = None
    if raw_doc_id:
        try:
            doc_id = UUID(str(raw_doc_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"doc_id 不是合法 UUID: {raw_doc_id!r}") from exc

    raw_page = record.get("page")
    page = (
        int(raw_page)
        if isinstance(raw_page, int) and not isinstance(raw_page, bool)
        else None
    )
    return EvidenceChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=str(record.get("text") or ""),
        page=page,
        char_start=int(record.get("char_start") or 0),
        char_end=int(record.get("char_end") or 0),
        entity_spans=_to_entity_spans(record.get("spans")),
    )


def _to_entity_spans(raw_spans: Any) -> tuple[EntitySpan, ...]:
    """解析片段内的实体 span（Sprint 10 批次 A）。

    **单条 span 坏掉 ⇒ 跳过该条，不整条 chunk 失败**：span 是"引用精度"
    的增强信息，缺失只是让引用回退到整段（语义仍正确）；而 ``doc_id`` /
    ``text`` 坏掉是数据错误，必须抛——两者**不可同等对待**。
    跳过时留 WARNING，避免"引用永远回退"却无人知晓。
    """
    if not raw_spans:
        return ()
    spans: list[EntitySpan] = []
    for raw in raw_spans:
        if not isinstance(raw, Mapping):
            continue
        mention = str(raw.get("mention") or "").strip()
        try:
            char_start = int(raw["char_start"])  # type: ignore[index]
            char_end = int(raw["char_end"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            logger.bind(mention=mention).warning("graph_entity_span_invalid")
            continue
        if not mention or char_end < char_start:
            logger.bind(mention=mention).warning("graph_entity_span_invalid")
            continue
        spans.append(
            EntitySpan(mention=mention, char_start=char_start, char_end=char_end)
        )
    return tuple(spans)


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
        # 语义优先：真机的 type(r) 是通用 RELATION，真实语义在 properties.relation_type
        type=_relation_type(
            record.get("type"),
            semantic=raw_properties.get("relation_type"),
        ),
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


def _relation_name(rel: Any) -> str:
    """实体详情里的关系名：**语义优先**，退化到 Neo4j 的 ``type(r)``。

    2026-09-27 真机发现（与 §7.5.1 同族的「写读口径错配」）：建图侧统一写
    ``:RELATION`` 令牌、真实语义放在 ``properties.relation_type``
    （``kg/builder.py`` stage-3），而详情只读 ``rel.type`` ⇒ 关系名一律显示成
    ``RELATION``（考勤真机实测：员工 50 条出边**全叫 RELATION**，
    ``HAS_SHIFT`` / ``HAS_POSITION`` / ``GOVERNED_BY`` 的真实语义一个都没露出来）。
    这里按 :func:`_edge_from_record` 的同款口径取语义值；**不用** :func:`_relation_type`
    的契约投影——详情是自由 ``str`` 字段，原样透传才能留住域关系名（``HAS_SHIFT`` /
    ``GOVERNED_BY``）；投影会把它们一律兜底成 ``MENTIONS``，属另一种信息失真。
    """
    properties = dict(rel) if hasattr(rel, "items") else {}
    semantic = properties.get("relation_type")
    if semantic:
        return str(semantic)
    return str(getattr(rel, "type", None) or "")


def _relation_type(raw: Any, *, semantic: Any = None) -> RelationType:
    """把 Cypher ``type(r)`` 的字符串映射为契约 ``RelationType`` 枚举。

    **语义优先（2026-09-22 真机修复）**：抽取产物把**真实语义**写在
    ``properties.relation_type``（真机实测 ``PARTY_TO``），而 Neo4j 的 ``type(r)``
    是通用 token ``RELATION``——后者不在契约枚举里，会被兜底成 ``MENTIONS``，
    于是图谱页与 Prompt 里的所有关系都显示成 ``MENTIONS``（真机污染）。
    故取数顺序为：**先语义、后类型**，两者都不命中才兜底。

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

    for candidate in (semantic, raw):
        name = str(candidate)
        if name in contract_enum:
            return name  # type: ignore[return-value]
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


#: 批次 C：基于实体类型字符串推断前端图例分类（4 类）。
#: 两套接词都要认：中文（M4 mock 数据）与**英文枚举**（真实抽取
#: ``app.services.extraction.langextract.ENTITY_TYPES``）。未知类型兜底
#: ``topic``（最常见的演示类）。
_ENTITY_TYPE_TO_CATEGORY: dict[str, GraphCategory] = {
    # -- 中文（M4 mock / 演示数据）--
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
    # -- 英文枚举（真实抽取链路落库值；2026-09-26 真机点验补齐）--
    "ORG": "org",
    "LEGAL_PERSON": "org",
    "REGULATION": "norm",
    "CONTRACT_CLAUSE": "norm",
    # PERSON / MONEY / DATE / PRODUCT / VENUE / ADDRESS 走兜底 ``topic``
}


def _entity_type_from_properties(properties: dict[str, Any]) -> Any:
    """从 Neo4j 节点属性里取实体类型（**属性名以建图侧为准**）。

    2026-09-26 真机点验修的错配：``kg/builder.py`` 写的是 ``n.entity_type``
    （``n.type`` 在真实图谱里**根本不存在**），而读侧三处全读 ``properties["type"]``
    ⇒ ``entity_type`` 恒为空、``category`` 恒兜底 ``topic``（演示第 2 / 3 步：
    类型列空白、节点全一个颜色）。这里 ``entity_type`` 优先、``type`` 仅作旧数据兜底。

    **不做** ``str()`` 强制转换：契约是 ``str | None``，属性里真塞了 int 属**契约不符**，
    由 schema 校验显式报错——静默转字符串正是本项目要拦的"假做"。
    """
    return properties.get("entity_type") or properties.get("type")


def _category_from_entity_type(entity_type: str) -> GraphCategory:
    """按实体类型字符串推断前端图例分类（**仅内置表**，不看本体）。

    保留原语义，供无本体上下文的场景（脚本 / 单测 / 内置默认域）使用；
    走服务方法的链路一律用 :func:`_resolve_category`（**本体优先**）。
    """
    if not entity_type:
        return "topic"
    return _ENTITY_TYPE_TO_CATEGORY.get(entity_type, "topic")


def _load_entity_type_categories(
    *, org_id: UUID | None, db: Any
) -> dict[str, GraphCategory]:
    """取该 org 本体的图例分类表；**任何失败都返回空 dict**。

    图例分类属**展示增强**而非数据正确性 ⇒ 本体缺失、无 ``db`` 会话、查询异常，
    一律降级为「无覆盖」，由 :func:`_resolve_category` 回落内置表，
    **不**阻断图谱查询。但异常必须 warn 留痕——静默吞掉是本项目要拦的"假做"。

    每请求只调一次（解析结果在本次投影内全量复用），**不**逐节点查库。
    """
    if db is None or org_id is None:
        return {}
    try:
        # 延迟导入：避免 graphs（被 agents 依赖）在模块级牵上 db / models 依赖
        from app.services.ontology import entity_type_categories

        return entity_type_categories(db=db, org_id=org_id)
    except Exception as exc:  # noqa: BLE001 - 展示增强，不阻断主链路
        logger.warning(f"读取本体图例分类失败，回落内置表: org_id={org_id}: {exc}")
        return {}


def _resolve_category(
    entity_type: str,
    *,
    categories: Mapping[str, GraphCategory] | None = None,
) -> GraphCategory:
    """推断图例分类：**本体优先 → 内置表 → ``topic`` 兜底**。

    ``categories`` 由 :func:`_load_entity_type_categories` 提供（每请求解析一次）。
    这样换业务域只需换本体数据，**不必改代码、也不动 API 契约**——``category``
    恒为契约那 4 个取值之一（非法值已被 ``ontology.py`` 过滤）。
    """
    if not entity_type:
        return "topic"
    if categories:
        override = categories.get(entity_type)
        if override is not None:
            return override
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


def _project_overview_nodes(
    records: Any,
    *,
    context: str,
    categories: Mapping[str, GraphCategory] | None = None,
) -> list[GraphOverviewNode]:
    """批次 C：把 Neo4j Entity 投影为 ``GraphOverviewNode``（轻量投影）。

    ``categories`` 为本体的图例分类覆盖表（B1-follow），由调用方每请求解析一次
    后传入；``None`` 时按 :func:`_resolve_category` 回落内置表。

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
            entity_type = str(_entity_type_from_properties(properties) or "")
            category = _resolve_category(entity_type, categories=categories)
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
            # 与 :func:`_relation_type` 同款「语义优先」：真机 ``type(r)`` 是通用
            # ``RELATION``，真实语义在 ``properties.relation_type``（如 ``PARTY_TO``）。
            # 不优先取语义，图谱页就会把所有关系都显示成 ``RELATION``（真机实测）。
            rel_name = _relation_type(
                record.get("type"),
                semantic=raw_properties.get("relation_type"),
            )
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
    "EvidenceChunk",
    "GraphService",
    "GraphUnavailableError",
    "EntityNotFoundError",
    "KgVersion",
    "NoActiveKgVersionError",
]
