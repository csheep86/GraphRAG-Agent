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
from app.services.kg.version_scope import version_scope
from app.services.kg.version_view import VersionReadView

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

#: Cypher 返回的候选路径上限。
#:
#: **2026-09-28（Sprint 9.6 G2）把排序口径推进 Cypher**——此前「排序在 Python
#: 侧做」的前提是候选**全量**返回，但真机数据下无向 1..3 跳候选有数万条，
#: ``LIMIT``（无 ORDER BY）任意截断 ⇒ 排序器再对也只对「截断后的幸存者」生效，
#: 3 跳条款链（EMPLOYEE→POSITION→WORK_TIME_SYSTEM→POLICY_CLAUSE，R10 连通后
#: 真实存在）被淹没在候选海里，从未进过排序。故 Cypher 侧先排好序再截断。
#:
#: ⚠️ **2026-10-09（P6-V1）订正**：上一段原写「两者口径一致」，**那是过期口径**——
#: Cypher 侧当时只有 3 维，Python 侧 :func:`_select_shortest_path` 是 7 维，且第 1
#: 维两侧当时就**不等价**（Cypher 把 ``LEGAL_PERSON`` 也算优先终点，Python 只认
#: ``POLICY_CLAUSE``）。此后 Cypher 侧是**粗排（保底）**、Python 侧是**精排**，
#: 两者的关系由 :data:`DB_ORDER_BY_DIMENSIONS` 一处登记并机械断言，
#: **不许**再靠注释互相保证。
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

# --------------------------------------------------------------------------- #
# Sprint 10 批次 B（裁决 D-F）：终点类型的**域注册表**
# --------------------------------------------------------------------------- #
#: **关联方域**（M4 `affiliation-demo-v1`）的合法终点：主体与凭证。
#:
#: 为什么要有第二套：真机实测（`changes/Sprint10.1/proposal.md` §1）——
#: `affiliation-demo-v1` 的 176 个实体**一个都不在**考勤白名单里 ⇒ 该域的多跳链
#: **恒为空**，而"公司 → 股东 → 另一家公司的法人"正是 M4 疑点的核心推理形态。
#:
#: **刻意排除 `PHONE`**：电话号码是可核查节点，但没有解释力（落点落在电话上，
#: 答案无从说起）——与考勤域把 `ACCESS_RECORD` 排在最末同源，只是这里干脆不收。
AFFILIATION_TERMINAL_TYPES: tuple[str, ...] = (
    "SUBJECT",
    "LEGAL_PERSON",
    "CONTRACT",
    "INVOICE",
    "VOUCHER",
    "ADDRESS",
)

#: 关联方域里**没有**"人人相连"的枢纽 ⇒ hub 为 ``None``（Cypher 侧
#: ``n.entity_type = $hub`` 对 null 恒不成立 ⇒ 该约束自动失效，**不需要**分支代码）。
AFFILIATION_PRIORITY_TYPE = "LEGAL_PERSON"


#: 登记过的**全部**合法终点类型 = 各域白名单的并集（去重保序）。
#:
#: **为什么是并集，而不是"先判域、再选该域白名单"**：域判定若看**本轮子图**的
#: 类型分布，就会被子图采样带偏——与 R12 真机事故同源（500 截断会把粒度粗的
#: 类型挤出子图 ⇒ 判成"未知域" ⇒ 明明有链却交白卷）。而 Cypher 侧本就按
#: ``kg_version`` + ``org_id`` 隔离：考勤图里没有 ``SUBJECT``、关联方图里没有
#: ``EMPLOYEE`` ⇒ 并集**不会**跨域连出链，却能让两个域都出链。
#:
#: **未登记的类型（``POSITION`` / ``DEPARTMENT`` / ``RELATED`` / ``PHONE`` …）
#: 依旧不是合法落点** ⇒ 新业务域没登记时，链自然取不到（``[]``），
#: 而不是"随便走两跳"——这正是纪律 1「零假数据」要的效果。
ALL_TERMINAL_TYPES: tuple[str, ...] = tuple(
    dict.fromkeys(TERMINAL_ENTITY_TYPES + AFFILIATION_TERMINAL_TYPES)
)

#: 各域"最有解释力"的终点（并集）：考勤 = 制度条款；关联方 = 共享法人（疑点的核心落点）。
#:
#: ⚠️ **2026-10-09（P6-V1）订正**：上句原写「终点命中其一 ⇒ 排序优先」，
#: **那是过期口径**——Python 侧精排的第 1 维只认 :data:`TERMINAL_PRIORITY_TYPE`，
#: ``AFFILIATION_PRIORITY_TYPE`` 并不在 :data:`_TERMINAL_RANK` 里 ⇒ 它**从未**
#: 拿到过排序优先权；Cypher 侧却把它当优先终点 ⇒ 两侧第 1 维**不等价**。
#: P6-V1 修的方向是**Cypher 侧向 Python 侧对齐**，不是反过来改 Python 侧——
#: 那会动 P6-V 刚接线的关联方域既有排序结果。
#: 本常量保留给探针 / 排障脚本取用（``changes/P6-U/probe_as_of_ranking.py`` 等
#: 历史探针仍在引用它），生产排序不再读它。
PRIORITY_TERMINAL_TYPES: tuple[str, ...] = (
    TERMINAL_PRIORITY_TYPE,
    AFFILIATION_PRIORITY_TYPE,
)


# --------------------------------------------------------------------------- #
# 两侧排序口径的**唯一事实源**（2026-10-09 P6-V1）
# --------------------------------------------------------------------------- #
#: Python 侧精排键的**具名维**（顺序即优先级）——见
#: :func:`_select_shortest_path` 里同序的 sort key。
#:
#: 它就是"两侧逐维比对"那一栏的左边：改排序口径前先看
#: :data:`DB_ORDER_BY_DIMENSIONS`，DB 侧必须是本元组的**连续前缀**。
PATH_SORT_DIMENSIONS: tuple[str, ...] = (
    "terminal_priority",  # 终点 == TERMINAL_PRIORITY_TYPE ⇒ 0（只有 POLICY_CLAUSE）
    "terminal_rank",  # _TERMINAL_RANK 次级档；不在表内 ⇒ len(_TERMINAL_RANK)
    "hops",  # size(rels)
    "temporal_verdict",  # 整链时序三值档（consistent / unknown / inconsistent）
    "as_of_evidence",  # 最后一跳是否被 as_of 证实（R5）
    "path_ids",  # tuple(ids)：整链 id 元组
    "position",  # 原始位次（确定性同解）
)

#: DB 侧（Cypher ``ORDER BY``）真正参与排序的维。
#:
#: **必须是 :data:`PATH_SORT_DIMENSIONS` 的连续前缀**——Cypher 侧 ``LIMIT`` 是
#: **截断**，Python 侧精排只对「截断后的幸存者」生效。只要 DB 侧是前缀，被截掉的
#: 候选就一定排在保留者之后（排序的加粗/coarsening），真胜者不会被截；一旦
#: **跳维**（如做 1,2,3,5 而漏掉 4）⇒ 截断会丢真胜者，**比不做更糟**。
#:
#: 为什么停在第 3 维而不是把 7 维全搬：搬第 4 维就得把 ``_temporal_verdict`` 的
#: max/min 三值语义在 Cypher 里**再写一遍**，那与 :func:`_cypher_paths` docstring
#: 记着的「同一判断散写成多份」是同款事故（初版写错 ⇒ 图上同时出现两位"当前法定
#: 代表人"）。第 5 维又排在第 4 维之后，跳过第 4 维搬它 ⇒ 破坏前缀 ⇒ 不许。
#:
#: 残留风险（**不许被读成"已完全对齐"**）：当前 3 维全打平的候选数 > 400 时，
#: DB 侧按 ``ids[-1]`` 截断，仍可能丢掉靠第 4 / 5 维胜出的那条。此时丢的是
#: **同档内的次优**（同样有解释力、同样短），不改变答案的解释力层级；
#: 详见 `changes/P6-V1/proposal.md` §6。
DB_ORDER_BY_DIMENSIONS: tuple[str, ...] = PATH_SORT_DIMENSIONS[:3]

#: DB 侧第 1 维「终点档位」= Python 键第 1 + 2 维的**合并**（字典序与之严格等价：
#: ``POLICY_CLAUSE`` 恒 0，其余 = 1 + rank ∈ [1, 9]）。
#:
#: 类型名**不**硬写在 Cypher 里：``$prio_type`` / ``$terminal_rank`` 由生产代码从
#: :data:`TERMINAL_PRIORITY_TYPE` / :data:`_TERMINAL_RANK` **这同一份常量**传下来
#: ——两侧各抄一份类型表，抄了就必然漂移。
_DB_TERMINAL_TIER_EXPR = (
    "CASE WHEN types[-1] = $prio_type THEN 0 "
    "ELSE 1 + coalesce($terminal_rank[types[-1]], $terminal_rank_default) END"
)

#: **修复前**的口径（P6-V1 之前的样子）：把 ``LEGAL_PERSON`` 也算作优先终点，
#: 与 Python 侧第 1 维不等价；且完全没有 Python 的第 2 维。
#:
#: 它只为**回归对照**而保留：判据 2 要「同一批数据、同一条查询，只换 ``ORDER BY``
#: ⇒ 旧键丢真胜者、新键不丢」。删了它，这条对照就退化成"读代码得出的结论"。
_DB_TERMINAL_TIER_LEGACY_EXPR = "CASE WHEN types[-1] IN $prio_types THEN 0 ELSE 1 END"

_CYPHER_ANCHOR_CANDIDATES = f"""
MATCH (e:Entity {{org_id: $org}})
WHERE {version_scope("e")}
  AND e.canonical_name IS NOT NULL
  AND size(e.canonical_name) >= $min_len
  AND e.id CONTAINS ':'
RETURN e.id AS id, e.canonical_name AS name
LIMIT $limit
"""


#: **边类型刻意不限定**（Sprint 10 批次 B）：考勤域的边是 ``:RELATION``
#: （抽取关系），而关联方域（M4 主体层）的边是 ``LEGAL_REP`` / ``SHARES_HOLDER``
#: / ``REGISTERED_AT`` …——真机实测它们**都带** ``kg_version`` / ``org_id``，
#: 靠下面 ``ALL(r IN rels WHERE ...)`` 做版本 / 租户隔离即可，写死 ``:RELATION``
#: 会让关联方域一条链都取不到（`probe_b1_multihop_affiliation.py` 实测 0 行）。
#:
#: 代價是**中间节点不再天然是 Entity**（变长路径的中间节点本就没有标签约束），
#: 故补 ``ALL(n IN nodes(p) WHERE n:Entity)``——否则会出现
#: ``(Entity)-(Chunk)-(Entity)`` 这种"经过片段"的伪链。
#:
#: 关系名用 ``coalesce(r.relation_type, type(r))``：抽取边有 ``relation_type``
#: 属性，主体层边只有**类型名**；取不到属性就退回类型令牌（L7 同族口径），
#: **不**兜底成 ``MENTIONS`` 这种"看起来有关系"的假名。
def _cypher_paths() -> str:
    """候选路径的 Cypher。

    **为什么它是函数而不是模块级常量**：``as_of`` 的过滤谓词必须**逐字符复用**
    :func:`app.services.graphs._temporal_view`，而本模块被 ``graphs`` 反向依赖
    （``graphs`` 自己在本模块里做延迟导入），牵到模块顶层就成环 ⇒ 谓词只能在
    函数体内延迟导入后再拼装。字符串每次重拼，代价可忽略。

    为什么要复用而不是在本模块另写一份同样的过滤：子图视图（``graphs`` 侧）与
    推理链视图共用同一段判据，"图上看到的当前态"与"链上走出来的当前态"才不可能
    口径漂移——``_temporal_view`` 的 docstring 里记着初版写错导致「两条当前法定
    代表人」的真机事故，那正是把同一判断散写成多份的典型代价。
    """
    from app.services.graphs import _temporal_view  # 延迟导入（见上文）

    return (
        f"""
MATCH p = (a:Entity {{org_id: $org}})
          -[rels*1..{_MAX_HOPS}]-
          (b:Entity {{org_id: $org}})
WHERE {version_scope("a")}
  AND {version_scope("b")}
  AND a.id IN $anchor_ids
  AND b.entity_type IN $terminal_types
  // **变长路径的中间节点也逐一过选中表**：跨越了三个版本的路径，中间那一站
  // 若已被 merge 删掉、或它不是该 id 的最新版本 ⇒ 这条路径不许存在
  // （P5H-1 C 口径：不拼"表象存在、事实已不存在"的幽灵路径）。
  AND ALL(n IN nodes(p) WHERE n:Entity AND {version_scope("n")})
  // 边的版本 ∈ 版本链：两端可能被选中在不同版本上，边本身只要落在链上即可。
  AND ALL(r IN rels WHERE r.kg_version IN $kgs AND r.org_id = $org)
  AND none(n IN nodes(p)[1..-1] WHERE n.entity_type = $hub)
  // as-of 视图（Sprint 10.5 / L2-③）：``$as_of`` 为 NULL ⇒ **不过滤**
  // （缺省行为必须零变化）；给定日期 ⇒ 要求**每一跳**在那日成立。
  // 缺日期的跳由谓词的 NULL 分支放行：只剔除**被日期证伪**的跳，不猜未知。
  AND ($as_of IS NULL OR ALL(r IN rels WHERE TRUE"""
        + _temporal_view("r")
        # ⚠️ 这一段**必须是 f-string**：``ORDER BY`` 里的档位表达式是插值进去的。
        # 原来这里写的是普通字符串（ORDER BY 那句是硬写的，不需要插值）⇒ 2026-10-09
        # 第一次接入 ``{_DB_TERMINAL_TIER_EXPR}`` 时它被当成字面文本下发给了 Neo4j，
        # 是 `tests/test_reasoning_db_order_by.py` 的「Cypher 必须真的用登记表达式」
        # 那条断言当场抓住的——**没有那条断言，这个 bug 在候选 < 400 时永远不显形**。
        + f"""))
RETURN [n IN nodes(p) | n.id] AS ids,
       [n IN nodes(p) | n.canonical_name] AS names,
       [n IN nodes(p) | n.entity_type] AS types,
       [r IN relationships(p) | coalesce(r.relation_type, type(r))] AS rels,
       [r IN relationships(p) | toString(properties(r)['valid_from'])] AS valid_froms,
       [r IN relationships(p) | toString(properties(r)['valid_to'])] AS valid_tos
ORDER BY {_DB_TERMINAL_TIER_EXPR},
         size(rels),
         ids[-1]
LIMIT $limit
"""
    )


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
    version_view: VersionReadView | None = None,
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
            version_view=version_view,
        )
    if not anchors:
        logger.bind(
            kg_version=kg_version, node_count=len(nodes), question_len=len(question)
        ).info("reasoning_path_no_anchor")
    return anchors


# --------------------------------------------------------------------------- #
# 第二 / 三步：沿关系跳转 → 命中条款 / 事实 → 逐跳标注来源
# --------------------------------------------------------------------------- #
def _date_text(value: Any) -> str | None:
    """把 Cypher 回的时间值转成 ``YYYY-MM-DD``；无值 ⇒ ``None``（**不**猜日期）。"""
    return None if value is None else str(value)


def build_reasoning_path(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    question: str,
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge] = (),
    chunks: Sequence[EvidenceChunk] = (),
    as_of: str | None = None,
    version_view: VersionReadView | None = None,
) -> list[ReasoningPathHop]:
    """取出本次问答的多跳推理路径（一跳一个 :class:`ReasoningPathHop`）。

    :param session: Neo4j 会话（由 ``GraphService`` 开，调用方不持有连接）。
    :param question: 原始问句（定位锚点用）。
    :param nodes: 本轮**已检索子图**的节点（锚点来源）。
    :param edges: 本轮已检索子图的边（判定 ``origin = graph`` 用）。
    :param chunks: 本轮**注入 Prompt 的证据片段**（判定 ``origin = document`` 用）。
    :param as_of: 全生命周期 as-of 日期（``YYYY-MM-DD``）；``None`` = 当前视图
        （缺省必须零变化）。它只**剔除被日期证伪**的跳，缺日期的跳照旧保留
        （三值语义：不知道 ≠ 有效），详情见 :func:`_cypher_paths`。
    :param version_view: P5-H **版本继承读**视野；``None`` ⇒ 按单版本
        （``kg_version`` 自身）读，与改之前的行为**完全一致**。
    :returns: 逐跳链（首尾相接）；**零命中返回空列表**（不是 ``None``——
        ``None`` 的语义是「未产出」，留给拒答分支，见契约字段说明）。
    """
    view = version_view or VersionReadView(versions=(kg_version,), selection={})
    anchors = resolve_anchors(
        session=session,
        kg_version=kg_version,
        org_id=org_id,
        question=question,
        nodes=nodes,
        version_view=view,
    )
    if not anchors:
        return []

    rows = list(
        session.run(
            _cypher_paths(),
            org=str(org_id),
            anchor_ids=list(anchors),
            terminal_types=list(ALL_TERMINAL_TYPES),
            hub=HUB_EMPLOYEE_TYPE,
            # 排序口径的**实参**必须与 Python 侧精排读的是同一份常量
            # （详见 :data:`_DB_TERMINAL_TIER_EXPR`）：$prio_type / $terminal_rank
            # 分别来自 TERMINAL_PRIORITY_TYPE / _TERMINAL_RANK。
            prio_type=TERMINAL_PRIORITY_TYPE,
            terminal_rank=dict(_TERMINAL_RANK),
            terminal_rank_default=len(_TERMINAL_RANK),
            limit=_PATH_CANDIDATE_LIMIT,
            as_of=as_of,
            **view.cypher_params(),
        )
    )
    selected = _select_shortest_path(rows, as_of=as_of)
    if selected is None:
        # as_of 非空时"那天没有这条链"是合法结论 ⇒ 日志里必须带上 as_of，
        # 否则无法区分"图上没有"与"那天还没成立"。
        logger.bind(kg_version=kg_version, anchors=list(anchors), as_of=as_of).info(
            "reasoning_path_no_path"
        )
        return []

    ids, names, types, rels, valid_froms, valid_tos = selected
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
        # 时间字段跟着跳一起出（供前端把已失效的跳画成虚线）；
        # 列缺/比 Expect 短 ⇒ 该跳为 None，不补齐、不猜（读侧三值语义）。
        hops.append(
            ReasoningPathHop(
                source=_path_node(ids[index], names[index], types[index]),
                relation=relation,
                target=target,
                origin=origin,
                evidence=evidence,
                valid_from=_date_text(
                    valid_froms[index] if index < len(valid_froms) else None
                ),
                valid_to=_date_text(
                    valid_tos[index] if index < len(valid_tos) else None
                ),
            )
        )
    logger.bind(
        kg_version=kg_version,
        hops=len(hops),
        origin=hops[-1].origin if hops else None,
        as_of=as_of,
    ).info("reasoning_path_built")
    return hops


def _fallback_anchors(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    question: str,
    version_view: VersionReadView | None = None,
) -> tuple[str, ...]:
    """按名字直查**确定性派生**实体作为锚点兜底（只在子图里定位不到时用）。

    **为什么要有它、以及它的边界**：它解决的是「子图采样把锚点类型挤出去了」
    这种**工程性失真**，**不是**允许随意另找一个与本次问答无关的节点——
    筛选条件与 :func:`anchor_ids_for_question` 完全一致（只看确定性派生实体、
    最小名字长度、长名优先、被更长名包含者让位），只是候选来源从「本轮子图」
    换成「图上同版本的同类实体」，且万一命中会打日志:func:`logger` 便于复盘。
    """
    view = version_view or VersionReadView(versions=(kg_version,), selection={})
    rows = list(
        session.run(
            _CYPHER_ANCHOR_CANDIDATES,
            org=str(org_id),
            min_len=_MIN_ANCHOR_NAME_LEN,
            limit=_ANCHOR_FALLBACK_LIMIT,
            **view.cypher_params(),
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


#: 路径时序裁决的名次（小的优先）——见 :func:`_temporal_verdict` 的三值语义
_TEMPORAL_RANK = {"consistent": 0, "unknown": 1, "inconsistent": 2}

#: ADR-0005 §5 R5「as-of 证据位次」的名次（小的优先）。
#: **``unconfirmed`` 同时涵盖两种情形**，它们在这个位次上必须同等待遇：
#: ① 最后一跳压根没有日期（不可判定）；② 有日期但没被该时点证实（那天尚未成立
#: 或已经失效）。理由：两者都**不配称"被该时点证实"**，而本维度管的恰恰是这一
#: 点——"它不成立"与"我不知道它成不成立"在"能不能摆在 as-of 答案里"这件事上
#: 等价。区分它们由 :func:`_temporal_verdict` 的三值语义负责，不在本维度重复。
_AS_OF_EVIDENCE_RANK = {"confirmed": 0, "unconfirmed": 1}


def _last_hop_as_of_evidence(row: Any, as_of: str | None) -> str:  # noqa: ANN401
    """ADR-0005 §5 R5：这条链的**最后一跳**是否被 ``as_of`` 证实。

    只看最后一跳：终点也就是答案的落点。把一份在该时点根本不成立的制度条款摆在
    用户面前，比"中间某一跳有没有日期"更致命。

    比较是**纯字符串比较**（``YYYY-MM-DD`` 字典序 == 日期序），与
    :func:`_temporal_verdict` 同口径，不需要任何领域模型。

    :param as_of: 给定时点；``None`` ⇒ 恒定返回 ``confirmed``——**缺省视图该维度
        恒为 0**（ADR-0005 §5 R5 第 1 条硬要求：缺省必须零变化），
        参与排序时等于不存在这一维。
    """
    if as_of is None:
        return "confirmed"
    keys = row.keys() if hasattr(row, "keys") else ()
    if "valid_froms" not in keys or "valid_tos" not in keys:
        return "unconfirmed"
    froms = list(row["valid_froms"] or [])
    tos = list(row["valid_tos"] or [])
    if not froms or not tos:
        return "unconfirmed"
    valid_from = froms[-1]
    valid_to = tos[-1]
    if valid_from is None:
        # 只有失效日没有施行日 ⇒ 无从判断那天是否"已成立"，不猜（R4）
        return "unconfirmed"
    if str(valid_from) > as_of:
        return "unconfirmed"  # 那天还没开始施行
    if valid_to is not None and str(valid_to) <= as_of:
        return "unconfirmed"  # 那天已经失效
    return "confirmed"


def _row_temporal_verdict(row: Any) -> str:  # noqa: ANN401
    """从一行候选路径里取时序裁决；**该行没有时态列 ⇒ unknown**（不猜）。

    时态列缺失是合法的：``_CYPHER_PATHS`` 之前不返回它们，单测的行也可能不带
    ——此时结论必须是「不可判定」，而不能默认成自洽（那等于说"没日期 = 永远有效"）。
    """
    keys = row.keys() if hasattr(row, "keys") else ()
    if "valid_froms" not in keys:
        return "unknown"
    return _temporal_verdict(row["valid_froms"] or [], row["valid_tos"] or [])


def _temporal_verdict(valid_froms: Sequence[Any], valid_tos: Sequence[Any]) -> str:
    """ADR-0005 §6 L2「路径时序一致性」：**这条链能不能在同一时点同时成立**。

    判定是**纯字符串比较**（``YYYY-MM-DD`` 字典序 == 日期序），不需要任何领域模型，
    也不需要 LLM——与 §5 的 R1–R4 同族：能靠受控 schema 确定性判的，不交给模型。

    三值语义（**没有第四种**）：

    - ``consistent``：每一跳都有 ``valid_from``，且存在一个时点让**所有**跳同时有效
      （``max(valid_from) <= min(valid_to)``；``valid_to`` 空 = 未失效 = ``+∞``）；
    - ``inconsistent``：最晚开始的事实晚于最早失效的事实 ⇒ 这些 hop **不可能**
      同时成立，是一条把不同时点的事实硬串起来的链（事件顺序被倒置了）；
    - ``unknown``：至少一跳没有 ``valid_from``（未纳入时效治理，如 employees.csv
      派生的 ``BELONGS_TO``）⇒ **不可判定**。这里是全域最容易自欺的地方：
      把它当 ``consistent`` 等于默认"没写日期 = 永远有效"，那正是 D-3 要避免的
      （R4 不猜值）。故单独成一档，**不并入**任何一边。

    :returns: ``consistent`` / ``inconsistent`` / ``unknown``
    """
    froms = [str(item) for item in valid_froms if item is not None]
    if not valid_froms or len(froms) != len(valid_froms):
        # 缺日期 ⇒ 不可判定（不猜）
        return "unknown"

    tos = [str(item) for item in valid_tos if item is not None]
    if not tos:
        # 全部未失效 ⇒ 区间右端全是 +∞ ⇒ 必然存在共同成立时点
        return "consistent"
    return "consistent" if max(froms) <= min(tos) else "inconsistent"


def _select_shortest_path(
    rows: Sequence[Any],
    as_of: str | None = None,
) -> (
    tuple[
        list[str],
        list[Any],
        list[Any],
        list[str],
        list[str | None],
        list[str | None],
    ]
    | None
):
    """从候选路径里挑**唯一**一条：**先比终点的解释力，再比跳数**。

    **为什么终点类型优先于跳数**（2026-09-28 真机实测的教训）：纯按跳数最少，
    「张伟的缺卡该怎么处理？」会停在一跳外的 ``ACCESS_RECORD``（门禁记录）上，
    而真正能回答「该怎么处理」的是 ``POLICY_CLAUSE``（自动补卡条款）——
    演示时前者看着像"找到了一条无关记录"，后者才是 proposal §5.5 要的
    「命中条款 / 事实」落点。故排序口径：

    1. 终点是 ``POLICY_CLAUSE``（制度条款）优先：问句问的通常就是"怎么算"；
    2. 再按终点类型的次级次序 ``_TERMINAL_RANK``；
    3. 再按**跳数升序**；
    4. 再按时序裁决（Sprint 10.4 的整链自洽档）；
    5. 再按 ADR-0005 §5 R5 的**as-of 证据位次**（仅 ``as_of`` 非空时起作用）；
    6. 最后才是节点 id 字典序 + 原始位次 ⇒ 确定性同解（可被单测钉死）。

    .. note::
       第 5 维是 2026-09-30 补上的，**不是为了优化而是补一个空缺**：实测
       ``as_of='2025-06-01'`` 时 12 条候选的前四维**全部打平**，胜出者实际由
       第 6 维 id 字典序决定 ⇒ 答案事实随机。这一维必须**排在跳数之后**：
       只为打平的候选裁决，不许为了时点证据去挑一条更长或解释力更弱的链。

    **为什么在 Python 侧排序**：Cypher 不能按 list 排序（``ORDER BY ids`` 非法），
    且把排序规则放在 Python 里可以被单测逐条钉死（同解保证）。

    :param as_of: ADR-0005 §5 R5 的给定时点；``None`` ⇒ 证据位次恒 0（缺省零变化）。
    :returns: ``(ids, names, types, rels, valid_froms, valid_tos)``；无合法候选 ⇒
        ``None``（列长对不上的行是脏数据，**整行丢弃**而非截断补全）。
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
        # Sprint 10.4（ADR-0005 L2）：同等档位下**优先选时序自洽的链**——
        # 它排在 ids 字典序之前、跳数之后 ⇒ 只在"同样短、同样有解释力"的候选之间
        # 起作用，**不会**为了自洽去挑一条更长的链。
        verdict = _row_temporal_verdict(row)
        candidates.append(
            (
                0 if terminal == TERMINAL_PRIORITY_TYPE else 1,
                _TERMINAL_RANK.get(terminal, len(_TERMINAL_RANK)),
                len(rels),
                _TEMPORAL_RANK[verdict],
                # ADR-0005 §5 R5：as-of 证据位次。位置是刻意的——**在字典序之前、
                # 跳数之后** ⇒ 只在前面几维全部打平时接管；as_of 为 None 时恒 0，
                # 因此缺省视图结果完全不变。
                _AS_OF_EVIDENCE_RANK[_last_hop_as_of_evidence(row, as_of)],
                tuple(ids),
                position,
                row,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
            item[3],
            item[4],
            item[5],
            item[6],
        )
    )
    row = candidates[0][7]
    # 行的形状由调用方（Neo4j / 单测桩）决定，时态列可能**不存在**——
    # 缺失必须落到"逐跳 None ⇒ 读侧判不可判定"，不能 KeyError。
    row_keys = row.keys() if hasattr(row, "keys") else ()
    # 必须可观测（日志与可观测性规范）：选中的链在时序上到底算哪档、候选里几成自洽。
    # 只看"选出了一条链"无法回答"这条链是不是把不同时点的事实串起来了"。
    logger.bind(
        candidates=len(candidates),
        verdict=_row_temporal_verdict(row),
        temporal_ranks=sorted({item[3] for item in candidates}),
        # 2026-10-09（P6-V1）：**截断必须可观测**。DB 侧 ``LIMIT`` 一截断，
        # Python 侧精排的范围就只剩幸存者——静默丢候选曾是"答案看着对、其实
        # 换了条链"的温床。达到上限即视为截断（返回值条数恰好等于上限时无法
        # 区分"刚好够"与"被截"，宁可多报）。
        candidate_limit=_PATH_CANDIDATE_LIMIT,
        truncated=len(rows) >= _PATH_CANDIDATE_LIMIT,
    ).info("reasoning_path_temporal_verdict")
    return (
        [str(item) for item in (row["ids"] or [])],
        list(row["names"] or []),
        list(row["types"] or []),
        [str(item) for item in (row["rels"] or [])],
        # 时态列跟着带回（供逐跳标注 valid_from/valid_to）。
        # 旧形状的行（无这两列）⇒ 空列表 ⇒ 逐跳取不到 ⇒ None ⇒ 读侧判不可判定。
        [
            None if item is None else str(item)
            for item in (row["valid_froms"] if "valid_froms" in row_keys else [])
        ],
        [
            None if item is None else str(item)
            for item in (row["valid_tos"] if "valid_tos" in row_keys else [])
        ],
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
