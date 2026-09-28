"""M3 问答的**多跳推理路径**（Sprint 9.5 批次 D1，proposal §5.5）。

**做什么**：把「问句 → 定位实体 → 沿关系跳转 → 命中的条款/事实」这条链**确定性**
地取出来，逐跳带「起点 / 终点实体（id + 名称 + 类型）+ 关系类型 + 该跳来源」，
供前端画链（批次 E2）。

**四条硬纪律**：

1. **零假数据（A15）**：每一跳都必须能回溯到**真实查询**
   ——锚点来自本轮已检索子图的节点、跳转来自多跳 Cypher 的返回行。
   定位不到锚点 / 锚点走不到终点 ⇒ 返回**空列表**，**不**填示例路径、
   **更不**"补一跳让链好看"。
2. **数值不出 LLM（纪律 3）**：路径只承载检索到的节点与边，
   :class:`ReasoningPathHop` **没有任何数值字段**——数值结论由规则引擎
   （批次 C1）确定性给出，LLM 只出措辞（批次 D2）。
3. **可核查、不失真**：关系类型取图上真实的 ``relation_type``，
   **不**做契约枚举投影——投影会把域关系一律兜底成 ``MENTIONS``
   （与 L7「关系名只读 ``type(r)`` 令牌」是同族失真）。
4. **确定性**：锚点按「名字长度降序 + id 升序」取、路径按「跳数升序 + 节点 id
   字典序」取第一条 ⇒ 同一问句 + 同一图谱**同解**，可复现。

**与批次 C 的关系**：本模块**不**计算任何数值，也不读制度文本；
它只把「图上这条链存在」这件事取回来。链末端的条款 / 事实若要参与数值判定，
走 :mod:`app.services.rules`。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.schemas.agent import ReasoningHopOrigin, ReasoningPathHop, ReasoningPathNode
from app.schemas.document import GraphEdge, GraphNode

if TYPE_CHECKING:  # 仅类型标注：`graphs` 反向依赖本模块（延迟导入，见 graphs 内注释）
    from app.services.graphs import EvidenceChunk

__all__ = [
    "TERMINAL_ENTITY_TYPES",
    "anchor_ids_for_question",
    "build_reasoning_path",
]

#: 从锚点出发的**最大跳数**。刻意取小：跳数越多越容易连出「看着像推理、
#: 实则八竿子打不着」的链（那是另一种假数据），4 跳以上也没有演示价值。
_MAX_HOPS = 3

#: 一次最多取几个锚点实体（名字越长越优先 ⇒ 「武汉光谷」压过「武汉」）
_MAX_ANCHORS = 3

#: 锚点名字的最小长度：单字（「的」「是」）会命中一堆噪声节点
_MIN_ANCHOR_NAME_LEN = 2

#: 锚点兜底查询的节点上限（**只取 id + 名字**，且已按命名空间过滤掉 span 噪声）
_ANCHOR_FALLBACK_LIMIT = 5000

#: Cypher 返回的候选路径上限（**排序在 Python 侧做**——Cypher 无法按 list 排序，
#: 且 Python 侧排序更容易被单测钉死「同解」）
_PATH_CANDIDATE_LIMIT = 400

#: 路径的**合法终点类型**＝「命中的条款 / 事实」（proposal §5.5）。
#:
#: 取自批次 A 的考勤本体（`demo/attendance/ontology_schema.json`）：
#: ``POLICY_CLAUSE`` 是制度条款，其余 8 类是跨域事实记录。
#: **换业务域时只改本元组**（不进契约、不动前端）：链必须落在「可核查的落点」上，
#: 否则「沿关系随便走两跳」就是编链。
#: **最有解释力的终点**：制度条款。问句通常问的是"怎么算"，落到条款才叫解答；
#: 其余 8 类事实记录是"旁证"落点（详见 :func:`_select_shortest_path` 的排序口径）。
TERMINAL_PRIORITY_TYPE = "POLICY_CLAUSE"

#: **次优终点的排序**（越靠前越优先）：都是条到bayKM会被下游真正拿来判责的
#: **跨域证据**（与批次 C2 归因口径同源）——出差审批 / 工单闭环 / 定位一致 ⇒ 外勤成立。
#:
#: **为什么不能只按跳数**：纯最短路径永远停在 `ACCESS_RECORD`（EMPLOYEE 的
#: 第一跳就是门禁刷卡），而它对「是不是在岗外勤」几乎无解释力——真机实测
#: 每条问句都出同一条「员工 → 门禁记录」，演示上等于没有推理。
#: 门禁排最后是因为它只用于 `access_contrast` 旁证（权重仅 0.13）。
TERMINAL_EVIDENCE_ORDER: tuple[str, ...] = (
    "BUSINESS_TRIP",
    "WORK_ORDER",
    "OVERTIME",
    "LEAVE",
    "SHIFT",
    "ATTENDANCE_RECORD",
    "LOCATION_RECORD",
    "ACCESS_RECORD",
)

TERMINAL_ENTITY_TYPES: tuple[str, ...] = (
    "POLICY_CLAUSE",
    "ATTENDANCE_RECORD",
    "SHIFT",
    "LEAVE",
    "OVERTIME",
    "BUSINESS_TRIP",
    "WORK_ORDER",
    "LOCATION_RECORD",
    "ACCESS_RECORD",
)


#: 多跳 Cypher：**无向**遍历（``-[]-``）——本体里的关系方向按「谁持有谁」写，
#: 而问句的走向常常相反（如「售后工程师算加班吗」的锚点是岗位，链要从岗位往回走）。
#:
#: 三重过滤缺一不可：
#: - 端点带 ``kg_version`` / ``org_id``（ADR-0002 §3.2 / ADR-0003 §3.3）；
#: - ``ALL(r IN rels ...)`` 逐一约束**关系**的 ``kg_version`` / ``org_id``
#:   ——只过滤端点会放进跨版本 / 跨租户的边；
#: - ``b.entity_type IN $terminal_types``：终点必须是条款或事实（纪律 1）。
#: **中途禁止出现的节点类型**：员工。见 :func:`_select_shortest_path` 的说明。
HUB_EMPLOYEE_TYPE = "EMPLOYEE"

_TERMINAL_RANK: dict[str, int] = {
    entity_type: index for index, entity_type in enumerate(TERMINAL_EVIDENCE_ORDER)
}

_CYPHER_ANCHOR_CANDIDATES = """
MATCH (e:Entity {kg_version: $kg, org_id: $org})
WHERE e.canonical_name IS NOT NULL
  AND size(e.canonical_name) >= $min_len
  AND e.id CONTAINS ':'
RETURN e.id AS id, e.canonical_name AS name
LIMIT $limit
"""

_CYPHER_PATHS = f"""
MATCH p = (a:Entity {{kg_version: $kg, org_id: $org}})
          -[rels:RELATION*1..{_MAX_HOPS}]-
          (b:Entity {{kg_version: $kg, org_id: $org}})
WHERE a.id IN $anchor_ids
  AND b.entity_type IN $terminal_types
  AND ALL(r IN rels WHERE r.kg_version = $kg AND r.org_id = $org)
RETURN [n IN nodes(p) | n.id] AS ids,
       [n IN nodes(p) | n.canonical_name] AS names,
       [n IN nodes(p) | n.entity_type] AS types,
       [r IN relationships(p) | r.relation_type] AS rels
LIMIT $limit
"""


# --------------------------------------------------------------------------- #
# 第一步：问句 → 定位实体
# --------------------------------------------------------------------------- #
def _is_deterministic_node_id(node_id: str) -> bool:
    """节点 id 是否**确定性派生**（含命名空间前缀，如 ``EMPLOYEE:E001``）。

    M2 span 抽取的节点 id 形如 ``ent_<12 hex>``、没有命名空间——它们是抽取碎片
    （名称可能是「加班」「第七条」），**不**能当推理起点。
    """
    return ":" in node_id


def anchor_ids_for_question(
    *,
    question: str,
    nodes: Sequence[GraphNode],
    limit: int = _MAX_ANCHORS,
) -> tuple[str, ...]:
    """在本轮已检索子图里定位问句提到的实体（**纯字符串包含，不做语义判断**）。

    **为什么只读子图、不再查一次库**：路径必须和「送进 Prompt 的那份证据」
    同源——另查一次会产出一条答案里根本没用到的链，那是另一种失真。

    :returns: 锚点节点 id（按「名字长度降序 + id 升序」，已去重）；
        一个都没命中 ⇒ 空元组（调用方据此返回 ``[]``，**不** fallback）。
    """
    hits: list[tuple[int, str]] = []
    names: dict[str, str] = {}
    for node in nodes:
        # 只有 `:Entity` 能当锚点：Document / Chunk 不是图谱推理的起点
        if node.label != "Entity":
            continue
        # **锚点只取确定性派生节点**（`NAMESPACE:ID` 形式，如 `EMPLOYEE:E001`
        # / `LOCATION_RECORD:L00001`）——2026-09-28 真机实测逼出来的：同一个
        # `kg_version` 里混住着 M2 span 抽取的噪声节点（id 形如 `ent_<hex>`，
        # 名字是「加班」「第七条」这类断句碎片）。它们与 Ids row 的名字常常相同，
        # 按「长名优先」还会**压过**结构化节点 ⇒ 问「张伟…」却定位到一个抽取碎片，
        # 最终链为空（看着像"图上没有解题"，实则是定位错了）。
        # 与 `rules/attribution.py::list_anomaly_cases` 的 `STARTS WITH 'EMPLOYEE:'`
        # 是同一条纪律：**同版本混住时必须先按 id 形态区分来源**。
        if not _is_deterministic_node_id(node.id):
            continue
        name = (node.canonical_name or "").strip()
        if len(name) < _MIN_ANCHOR_NAME_LEN or name not in question:
            continue
        hits.append((-len(name), node.id))
        names[node.id] = name

    hits.sort()
    anchors: list[str] = []
    kept: list[str] = []
    for _, node_id in hits:
        name = names[node_id]
        if node_id in anchors:
            continue
        # 被**更长命中**包含的短名不再单独成锚（「武汉」被「武汉光谷」吃掉）：
        # 那是同一地点的两种粒度，留着会让同一事实跑出两条平行链——
        # 演示时看起来像"系统找到了两条独立线索"，实则是同一个ēē ē 地点的两种写法。
        if any(name in longer for longer in kept):
            continue
        anchors.append(node_id)
        kept.append(name)
    return tuple(anchors[:limit])


def resolve_anchors(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    question: str,
    nodes: Sequence[GraphNode],
) -> tuple[str, ...]:
    """定位锚点：**先本轮子图，定位不到才按名字直查兜底**。

    抽成独立函数是为了让**推理路径**与**证据注入**吃同一套锚点
    （2026-09-28 真机实测：两者不一致会直接产出错误答案，见下）。

    **为什么允许兜底**：``/agent/query`` 的 ``fetch_all_subgraph`` 有
    ``node_limit``（默认 500），而 CSV 派生的考勤事实（SHIFT / ATTENDANCE_RECORD
    各数百条）会把**数量少但粒度粗**的锚点类型（EMPLOYEE / POSITION / SITE）
    挤出子图 ⇒ 问「张伟…」时 ``EMPLOYEE:E001`` 压根不在 ``nodes`` 里 ⇒ 定位不到。
    零命中会被读成「图上没有这条链 / 这个人」，实际是「起点没进这次的子图采样」
    ——这也是一种失真，故允许按名字直查一次**确定性派生**实体，并记日志。
    """
    anchors = anchor_ids_for_question(question=question, nodes=nodes)
    if not anchors:
        anchors = _fallback_anchors(
            session=session,
            kg_version=kg_version,
            org_id=org_id,
            question=question,
        )
    if not anchors:
        logger.bind(
            kg_version=kg_version, node_count=len(nodes), question_len=len(question)
        ).info("reasoning_path_no_anchor")
    return anchors


# --------------------------------------------------------------------------- #
# 第二 / 三步：沿关系跳转 → 命中条款 / 事实 → 逐跳标注来源
# --------------------------------------------------------------------------- #
def build_reasoning_path(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    question: str,
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge] = (),
    chunks: Sequence[EvidenceChunk] = (),
) -> list[ReasoningPathHop]:
    """取出本次问答的多跳推理路径（一跳一个 :class:`ReasoningPathHop`）。

    :param session: Neo4j 会话（由 ``GraphService`` 开，调用方不持有连接）。
    :param question: 原始问句（定位锚点用）。
    :param nodes: 本轮**已检索子图**的节点（锚点来源）。
    :param edges: 本轮已检索子图的边（判定 ``origin = graph`` 用）。
    :param chunks: 本轮**注入 Prompt 的证据片段**（判定 ``origin = document`` 用）。
    :returns: 逐跳链（首尾相接）；**零命中返回空列表**（不是 ``None``——
        ``None`` 的语义是「未产出」，留给拒答分支，见契约字段说明）。
    """
    anchors = resolve_anchors(
        session=session,
        kg_version=kg_version,
        org_id=org_id,
        question=question,
        nodes=nodes,
    )
    if not anchors:
        return []

    rows = list(
        session.run(
            _CYPHER_PATHS,
            kg=kg_version,
            org=str(org_id),
            anchor_ids=list(anchors),
            terminal_types=list(TERMINAL_ENTITY_TYPES),
            limit=_PATH_CANDIDATE_LIMIT,
        )
    )
    selected = _select_shortest_path(rows)
    if selected is None:
        logger.bind(kg_version=kg_version, anchors=list(anchors)).info(
            "reasoning_path_no_path"
        )
        return []

    ids, names, types, rels = selected
    edge_pairs = _edge_pairs(edges)
    hops: list[ReasoningPathHop] = []
    for index, relation in enumerate(rels):
        target = _path_node(ids[index + 1], names[index + 1], types[index + 1])
        origin, evidence = _hop_origin(
            source_id=ids[index],
            target=target,
            edge_pairs=edge_pairs,
            chunks=chunks,
        )
        hops.append(
            ReasoningPathHop(
                source=_path_node(ids[index], names[index], types[index]),
                relation=relation,
                target=target,
                origin=origin,
                evidence=evidence,
            )
        )
    logger.bind(
        kg_version=kg_version,
        hops=len(hops),
        origin=hops[-1].origin if hops else None,
    ).info("reasoning_path_built")
    return hops


def _fallback_anchors(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    question: str,
) -> tuple[str, ...]:
    """按名字直查**确定性派生**实体作为锚点兜底（只在子图里定位不到时用）。

    **为什么要有它、以及它的边界**：它解决的是「子图采样把锚点类型挤出去了」
    这种**工程性失真**，**不是**允许随意另找一个与本次问答无关的节点——
    筛选条件与 :func:`anchor_ids_for_question` 完全一致（只看确定性派生实体、
    最小名字长度、长名优先、被更长名包含者让位），只是候选来源从「本轮子图」
    换成「图上同版本的同类实体」，且万一命中会打日志:func:`logger` 便于复盘。
    """
    rows = list(
        session.run(
            _CYPHER_ANCHOR_CANDIDATES,
            kg=kg_version,
            org=str(org_id),
            min_len=_MIN_ANCHOR_NAME_LEN,
            limit=_ANCHOR_FALLBACK_LIMIT,
        )
    )

    hits: list[tuple[int, str]] = []
    names: dict[str, str] = {}
    for row in rows:
        # 兜底查询是「尽力而为」：列缺失 / 空值的行**跳过**而不抛
        # （它只决定起点，路径本身另有校验脏行的那一层）。
        try:
            node_id = str(row["id"])
        except (KeyError, TypeError):
            continue
        name = str(row.get("name") or "").strip()
        if not _is_deterministic_node_id(node_id):
            continue
        if len(name) < _MIN_ANCHOR_NAME_LEN or name not in question:
            continue
        hits.append((-len(name), node_id))
        names[node_id] = name

    hits.sort()
    anchors: list[str] = []
    kept: list[str] = []
    for _, node_id in hits:
        name = names[node_id]
        if node_id in anchors:
            continue
        if any(name in longer for longer in kept):
            continue
        anchors.append(node_id)
        kept.append(name)

    result = tuple(anchors[:_MAX_ANCHORS])
    if result:
        logger.bind(kg_version=kg_version, anchors=list(result)).info(
            "reasoning_path_anchor_fallback"
        )
    return result


def _select_shortest_path(
    rows: Sequence[Any],
) -> tuple[list[str], list[Any], list[Any], list[str]] | None:
    """从候选路径里挑**唯一**一条：**先比终点的解释力，再比跳数**。

    **为什么终点类型优先于跳数**（2026-09-28 真机实测的教训）：纯按跳数最少，
    「张伟的缺卡该怎么处理？」会停在一跳外的 ``ACCESS_RECORD``（门禁记录）上，
    而真正能回答「该怎么处理」的是 ``POLICY_CLAUSE``（自动补卡条款）——
    演示时前者看着像"找到了一条无关记录"，后者才是 proposal §5.5 要的
    「命中条款 / 事实」落点。故排序口径：

    1. 终点是 ``POLICY_CLAUSE``（制度条款）优先：问句问的通常就是"怎么算"；
    2. 同档再按**跳数升序 ⇒ 节点 id 字典序**：确定性同解（可被单测钉死）。

    **为什么在 Python 侧排序**：Cypher 不能按 list 排序（``ORDER BY ids`` 非法），
    且把排序规则放在 Python 里可以被单测逐条钉死（同解保证）。

    :returns: ``(ids, names, types, rels)``；无合法候选 ⇒ ``None``
        （列长对不上的行是脏数据，**整行丢弃**而非截断补全）。
    """
    candidates: list[tuple[int, int, tuple[str, ...], int, Any]] = []
    for position, row in enumerate(rows):
        try:
            ids = [str(item) for item in (row["ids"] or [])]
            rels = [str(item) for item in (row["rels"] or [])]
            names = list(row["names"] or [])
            types = list(row["types"] or [])
        except (KeyError, TypeError):
            continue
        if len(ids) < 2 or len(rels) != len(ids) - 1:
            continue
        if len(names) != len(ids) or len(types) != len(ids):
            continue
        # **中途不许串到别的员工**（2026-09-28 真机实测的教训）：
        # 「张伟的缺卡怎么算」曾走出「张伟 → 售后工程师(岗位) → 罗伟(同事)
        # → 郑州出差单」——每一步都是**真的边**，但落到同事头上，
        # 演示台上会被读成"系统回答了别人的问题"。同岗位之类的横向关系是**旁证**，
        # 不是推理主干，故中间节点一律不许出现 `EMPLOYEE`。
        middle_types = [str(item) for item in types[1:-1]]
        if any(item == HUB_EMPLOYEE_TYPE for item in middle_types):
            continue
        terminal = str(types[-1]) if types[-1] else ""
        candidates.append(
            (
                0 if terminal == TERMINAL_PRIORITY_TYPE else 1,
                _TERMINAL_RANK.get(terminal, len(_TERMINAL_RANK)),
                len(rels),
                tuple(ids),
                position,
                row,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
    row = candidates[0][5]
    return (
        [str(item) for item in (row["ids"] or [])],
        list(row["names"] or []),
        list(row["types"] or []),
        [str(item) for item in (row["rels"] or [])],
    )


def _path_node(node_id: str, name: Any, entity_type: Any) -> ReasoningPathNode:
    """把 Cypher 的一列投影成路径节点（**不做任何编造式兜底**）。"""
    return ReasoningPathNode(
        id=node_id,
        name=str(name).strip() if name else node_id,
        entity_type=str(entity_type) if entity_type else None,
    )


def _edge_pairs(edges: Sequence[GraphEdge]) -> set[tuple[str, str]]:
    """子图边集 → 无向端点对（Cypher 遍历本身是无向的，故匹配也不分方向）。"""
    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        pairs.add((edge.source, edge.target))
        pairs.add((edge.target, edge.source))
    return pairs


def _chunk_evidence(name: str, chunks: Sequence[EvidenceChunk]) -> str | None:
    """终点名称出现在哪条证据片段的原文里 ⇒ 返回它的出处（``chunk:<id>``）。

    **只做包含匹配**（与 :func:`search_policy_sentences` 同口径）：命中即返回，
    不做语义判断；命中不到就老实说"没有原文支撑"。
    """
    if not name:
        return None
    for chunk in chunks:
        if name in (chunk.text or ""):
            return f"chunk:{chunk.chunk_id}"
    return None


def _hop_origin(
    *,
    source_id: str,
    target: ReasoningPathNode,
    edge_pairs: set[tuple[str, str]],
    chunks: Sequence[EvidenceChunk],
) -> tuple[ReasoningHopOrigin, str | None]:
    """判定该跳的来源（**按证据强度取最高**，三者互斥）。"""
    evidence = _chunk_evidence(target.name, chunks)
    if evidence is not None:
        return "document", evidence
    if (source_id, target.id) in edge_pairs:
        return "graph", None
    return "cypher", None
