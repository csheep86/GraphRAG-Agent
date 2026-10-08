"""M6 **版本继承读**（P5-H 批次 C'：P5F-4 的消费侧完整性）。

**为什么要有本模块**（本批修的是**功能缺陷**，不是做优化）：

P5-G §2.1 定的校正顺序是「① 读 active 版本 → ④ `rebuild_incrementally`
（受影响子图 ∪ 1 跳邻居）→ 产新版本并置 `ready`」。而
:meth:`~app.services.kg.versioning.KgVersioningService.get_active` 按
``ready_at DESC`` 只取**一条** ⇒ **一次校正之后，active 版本就是那个只含
「受影响子图」的小版本**。消费侧按**单一** `kg_version` 过滤 ⇒ 校正后它们
**几乎读空**。这是 P5-F / P5-G 引入的真实功能缺陷，本模块是它的解药。

**做的两件事**：

1. :func:`resolve_read_versions` —— 从 active 版本起沿 `ontology_actions`
   回溯父链，返回**有序**版本列表（新 → 旧）；
2. :func:`resolve_entity_selection` —— 在版本链上对每个实体 id 选出**唯一**
   可见版本（**选中表**：``{id: version}``）。

三条职责边界（逐条都不要越界）：

- **本模块只读**：既不写 Neo4j 也不写 PG。把全图复制进新版本属
  `correction` / `incremental` 的写侧职责（Non-goal 3：写侧一行不改）；
- **不替换** :meth:`KgVersioningService.get_active`：它照样返回**一条** active
  版本，:func:`resolve_read_versions` 是**并列**的另一个入口（Non-goal 4）；
- **不引入缓存**（D7）：版本链是一次 PG 查询 + 一次图查询；加缓存只会换来
  「读到过期版本链」这种更坏的失败。

**⚠️ 版本链的真源是 `ontology_actions`，不是 `kg_versions`**（D4 / ADR-0008）：

``kg_versions`` 表**没有** ``parent_version`` 列（2026-10-08 实读
`models.py:283-306`），而父链的完整信息**只在** `ontology_actions` 里：
一行动作的 ``result_kg_version``（产出版本）指向它的 ``kg_version``（基线版本）。
故本模块以 `ontology_actions` 为真源反推父链 —— 这是**无迁移**前提下的取法，
不是设计意图；长远要不要给 ``kg_versions`` 加列另行裁决（属下一批，要动
**G-6 迁移等价性**护栏）。

**链长上限 16 是防环的工程兜底，不是语义保证**：超过上限时链被截断
（更老的版本不再参与继承），**不报错**，只打 ``warning``（见 ADR-0008 §6）。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OntologyAction

# re-export：``version_scope`` 的真身在零依赖的 ``version_scope`` 模块里
# （为什么必须拆出去，见那个模块的 docstring），这里只是让调用方不必记住两个名字。
from app.services.kg.version_scope import version_scope
from app.services.kg.versioning import KgVersioningService

__all__ = [
    "DEFAULT_MAX_CHAIN_DEPTH",
    "VersionReadView",
    "build_read_view",
    "resolve_action_scopes",
    "resolve_entity_selection",
    "resolve_read_versions",
    "version_scope",
]

#: 版本链的**最大长度**（含 active 版本自身）。
#: 取 16 而不是「不设限」：链长由连续校正次数决定，而环（A 的父是 B、B 的父是 A）
#: 在数据异常时并非不可能 —— 没有上限会把一次读请求变成一次死循环。
DEFAULT_MAX_CHAIN_DEPTH = 16

#: **一条不存在的版本链**（既没有 active 版本，也没有可读的父链）。
_EMPTY_VERSIONS: tuple[str, ...] = ()

#: 枚举版本链上的 ``(id, version)`` 组合。
#: ``org_id`` 是**应用层常设防线**（DR-B5：图谱侧永远没有 RLS 可依赖）——
#: 传 ``None`` 表示调用方处在「无租户上下文」的内部路径，与既有 Cypher 的
#: ``$org_id IS NULL OR ...`` 三重判断同口径（不加租户过滤）。
_CYPHER_VERSION_INDEX = """
MATCH (n:Entity)
WHERE n.kg_version IN $kgs
  AND ($org_id IS NULL OR n.org_id = $org_id)
RETURN n.id AS id, n.kg_version AS ver
"""


# --------------------------------------------------------------------------- #
# 读视图
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class VersionReadView:
    """一次读请求的**版本视野**：有序版本链 + 每个实体 id 的选中版本。

    :param versions: 版本链，**新 → 旧**有序；首元素即 active 版本（``head``）
    :param selection: ``{实体 id: 该 id 的可见版本}``；Cypher 侧靠它过滤，见
        :meth:`cypher_params`
    """

    versions: tuple[str, ...]
    selection: Mapping[str, str]

    @property
    def head(self) -> str:
        """active 版本（版本链的首元素）；空链 ⇒ 空串。"""
        return self.versions[0] if self.versions else ""

    @property
    def inherits_history(self) -> bool:
        """是否存在**版本继承**（链长 > 1 ⇒ 图上发生过至少一次校正）。

        单版本时 selection 恒为空 ⇒ Cypher 退化为「按只有 head 的 ``$kgs`` 过滤」，
        与改之前的 ``= $kg`` **完全等价**（缺省零变化）。
        """
        return len(self.versions) > 1

    def cypher_params(self) -> dict[str, Any]:
        """给下游 Cypher 的参数：``$kgs``（版本列表）+ ``$sel``（选中表）。

        Cypher 侧的**统一谓词**（三条读路径共用，见 ADR-0008 §4）：

        ```cypher
        WHERE n.kg_version IN $kgs
          AND ($sel[n.id] IS NULL OR $sel[n.id] = n.kg_version)
        ```

        为什么写成这样：

        - **缺省**（链长 1、selection 空）⇒ ``$sel[...]`` 取到 null ⇒ 第二项恒真
          ⇒ 等价于原来的 ``n.kg_version = $kg``，**行为零变化**；
        - **发生继承** ⇒ 每个 id 只允许命中它**被选中的那一个**版本。
        """
        return {"kgs": list(self.versions), "sel": dict(self.selection)}


# --------------------------------------------------------------------------- #
# ① 版本链（纯 PG）
# --------------------------------------------------------------------------- #
def resolve_read_versions(
    *,
    db: Session,
    org_id: uuid.UUID,
    active_version: str | None = None,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> tuple[str, ...]:
    """从 active 版本起沿 `ontology_actions` 回溯父链 → **有序**版本列表（新 → 旧）。

    **不吞错**：无 active 版本返回空元组（三条读路径都由
    :meth:`GraphService.fetch_active_kg_version` 先抛 ``NoActiveKgVersionError``，
    正常链路走不到这个分支）。

    :param active_version: 已解析出的 active 版本；``None`` ⇒ 本函数自己查 PG
    :param max_depth: 链长上限（含 active 自身）；超过 ⇒ 截断 + ``warning``，不报错
    """
    if max_depth <= 0:
        raise ValueError(f"max_depth 必须为正整数（实际={max_depth}）")

    head = active_version
    if head is None:
        record = KgVersioningService(db).get_active(org_id=org_id)
        head = record.version if record is not None else None
    if not head:
        return _EMPTY_VERSIONS

    chain: list[str] = [str(head)]
    seen: set[str] = {chain[0]}
    cursor = chain[0]
    for _ in range(max_depth - 1):
        parent = _parent_version(db=db, org_id=org_id, result_version=cursor)
        if parent is None or parent in seen:
            break
        chain.append(parent)
        seen.add(parent)
        cursor = parent
    else:
        # 达上限（**不是**正常出口）：链被截断 ⇒ 更老的版本不再参与继承。
        # 它是工程兜底，不是语义保证 —— 行为已登记在 ADR-0008 §6。
        logger.bind(org_id=str(org_id), head=chain[0], max_depth=max_depth).warning(
            "kg_version_chain_truncated"
        )

    logger.bind(org_id=str(org_id), head=chain[0], depth=len(chain)).debug(
        "kg_version_chain_resolved"
    )
    return tuple(chain)


def _parent_version(
    *, db: Session, org_id: uuid.UUID, result_version: str
) -> str | None:
    """产出 ``result_version`` 的那行动作的**基线版本**；无父 ⇒ ``None``。

    三处刻意的设计：

    1. **``org_id`` 常设过滤**（DR-B5）：他 org 的动作行即便 ``result_kg_version``
       撞名，也**不得**串进本租户的链 —— 这是 G-9 T1 越权面的第二道防线；
    2. **``kg_version IS NOT NULL``**：只有确实带基线版本的行才算父跳
       （``confirm`` 之类的行会给不出父链，混进来会把链拐到别的语义上）；
    3. **同 ``result_kg_version`` 多行时取最新一行**：正常一个版本只由一个动作产出，
       这里是防异常数据的兜底（取最新 = 以最后一次重写为准）。
    """
    row = db.scalar(
        select(OntologyAction)
        .where(
            OntologyAction.org_id == org_id,
            OntologyAction.result_kg_version == result_version,
            OntologyAction.kg_version.is_not(None),
        )
        .order_by(OntologyAction.created_at.desc())
        .limit(1)
    )
    return str(row.kg_version) if row is not None and row.kg_version else None


def resolve_action_scopes(
    *, db: Session, org_id: uuid.UUID, versions: tuple[str, ...]
) -> dict[str, frozenset[str]]:
    """版本 → 该版本的**动作作用域**（``target_entities`` 里的实体 id）。

    **为什么要它**（= P5H-2，本模块最容易被误解的一块）：
    ``merge`` 是 ``DETACH DELETE`` 掉被并入侧（P5-G ``_merge_transform``），
    图上**没有墓碑**。若只看「链上最新出现版本」，被合并掉的节点会从旧版本里
    **被继承回来** —— 那等于宣布这次 merge 从未发生过。

    判定的唯一依据是**写侧自己落的审计字段**：某个版本对应的那行动作**承诺要处理**
    这些 id（``target_entities.entity_ids``），而它们**不在**该版本的节点集里
    ⇒ 只可能被那次动作删掉了。这不是猜：改写侧 ∈ Non-goal 3，加墓碑列
    ∈ Non-goal 5，``target_entities`` 是唯一剩下的真源。
    """
    if not versions:
        return {}
    rows = db.scalars(
        select(OntologyAction).where(
            OntologyAction.org_id == org_id,
            OntologyAction.result_kg_version.in_(list(versions)),
        )
    ).all()
    scopes: dict[str, frozenset[str]] = {}
    for row in rows:
        result = row.result_kg_version
        if not result:
            continue
        # 同一产出版本若有多行（异常数据）⇒ 取并集（宁可多管，不可漏判删除）
        scopes[result] = scopes.get(result, frozenset()) | _target_ids(
            row.target_entities
        )
    return scopes


def _target_ids(target_entities: Any) -> frozenset[str]:
    """从 ``target_entities`` (JSON) 里取出本次动作**承诺处理**的 id 集合。

    shape 随动作而变（`models.py:1060-1064` 明写「不对不同动作硬套同一形状」）：

    - ``merge`` / ``rename`` ⇒ ``{"entity_ids": [...]}``；
    - ``split`` ⇒ ``{"entity_ids": [...], "new_entity_ids": [...]}``。

    两种键**都**收：前者可能包含被删除者；后者是新节点（正常情况下它们一定在
    新版本里），收进来不会误判，只在异常缺失时让判定更保守。
    """
    if not isinstance(target_entities, dict):
        return frozenset()
    collected: list[str] = []
    for key in ("entity_ids", "new_entity_ids"):
        values = target_entities.get(key)
        if isinstance(values, list):
            collected.extend(str(item) for item in values if item)
    return frozenset(collected)


# --------------------------------------------------------------------------- #
# ② 选中表（图查询 + Python 侧裁决）
# --------------------------------------------------------------------------- #
def resolve_entity_selection(
    *,
    session: Any,
    org_id: uuid.UUID | None,
    versions: tuple[str, ...],
    scopes: Mapping[str, frozenset[str]],
) -> dict[str, str]:
    """在版本链上对每个实体 id 选出**唯一**可见版本。

    **三条裁决规则**（按序应用；见 ADR-0008 §4）：

    1. **链上最新者胜**：自上而下（新 → 旧）遍历，先被选中的版本即为该 id 的可见
       版本 ⇒ 校正在新版本上的改动（改名、合并后左侧的新属性）**接管**旧版本的值；
    2. **删除不再继承**：某版本的动作作用域里的 id **不在**该版本的节点集里
       ⇒ 判为该动作删掉了它 ⇒ **停止**向更旧版本继承（P5H-2）；
    3. **已选中者优先于删除判定**：若某 id 已经在更**新**的版本里出现过，即便它
       同时被某个更旧版本的作用域判为「缺失」，也以新版本为准 —— 新的版本说了算。

    :param session: Neo4j 会话
    :param org_id: 租户；``None`` ⇒ 不加租户过滤（仅内部 / 脚本路径）
    """
    if not versions:
        return {}

    rows = list(
        session.run(
            _CYPHER_VERSION_INDEX,
            kgs=list(versions),
            org_id=str(org_id) if org_id is not None else None,
        )
    )
    present: dict[str, set[str]] = {version: set() for version in versions}
    for row in rows:
        version = str(row["ver"])
        if version in present:
            present[version].add(str(row["id"]))

    selected: dict[str, str] = {}
    deleted: set[str] = set()
    for version in versions:  # 新 → 旧
        ids = present[version]
        for entity_id in sorted(ids):
            if entity_id in deleted:
                continue
            selected.setdefault(entity_id, version)
        for entity_id in scopes.get(version, ()):
            # 「不在本版本」+「还没被更新的版本选中」⇒ 本次动作把它删了
            if entity_id not in ids and entity_id not in selected:
                deleted.add(entity_id)

    logger.bind(
        versions=len(versions), selected=len(selected), deleted=len(deleted)
    ).debug("kg_version_selection_resolved")
    return selected


# --------------------------------------------------------------------------- #
# ③ 组装
# --------------------------------------------------------------------------- #
def build_read_view(
    *,
    db: Session,
    session: Any,
    org_id: uuid.UUID | None,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> VersionReadView:
    """一次读请求的完整版本视野（版本链 + 选中表）。

    :param db: PG 会话（版本链与动作作用域的真源）
    :param session: Neo4j 会话（``driver.session(...)``，由调用方持有，本模块不开连接）
    :param org_id: 租户；``None`` ⇒ 无从给版本链做隔离过滤 ⇒ **不继承**，退回
        空链（调用方看到空链时应按单版本口径处理，见
        :func:`app.services.graphs.GraphService._read_view`）
    """
    if org_id is None:
        # 无租户上下文 ⇒ 宁可不继承，也不许在这条路径上放宽隔离键。
        logger.warning("kg_version_view_without_org_id")
        return VersionReadView(versions=_EMPTY_VERSIONS, selection={})

    versions = resolve_read_versions(db=db, org_id=org_id, max_depth=max_depth)
    if not versions:
        return VersionReadView(versions=_EMPTY_VERSIONS, selection={})
    if len(versions) == 1:
        # 缺省（没有校正历史）：**不做**任何额外图查询，selection 为空
        # ⇒ Cypher 退化到 ``= $kg`` 的既有语义（零变化 = 既有全部用例的基线）。
        return VersionReadView(versions=versions, selection={})

    scopes = resolve_action_scopes(db=db, org_id=org_id, versions=versions)
    selection = resolve_entity_selection(
        session=session, org_id=org_id, versions=versions, scopes=scopes
    )
    return VersionReadView(versions=versions, selection=selection)
