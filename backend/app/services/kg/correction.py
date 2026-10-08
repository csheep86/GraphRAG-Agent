"""M6 §3.2 **三校正动作**（merge / split / rename）的服务层（P5-G 批次 B'）。

**为什么单独成文件**：这三个动作是「人工校正 → 新版本」这条链的**入口**，
而它们的**出口**（增量重算）已经是 `app/services/kg/incremental.py`。
两者职责不同、失效方向相反：本文件管「变换语义对不对」，incremental 管
「有没有只重写受影响子图」。混在一个文件里会互相掩护。

**顺序即纪律**（登记 **P5G-1**）：

```text
1. 读 PG active（= ready）版本作 base          ← 无 ⇒ 409 KG_VERSION_NOT_ACTIVE
2. probe：目标实体**存在且属于本 org**          ← 跨 org ⇒ 403 FORBIDDEN（不降级！）
                                                  缺失   ⇒ 404 ENTITY_NOT_FOUND
3. 落 ontology_actions（拿 action_id）          ← 审计先于变更
4. rebuild_incrementally(受影响集, base) → 新版本 ← 旧版本**一条不动**
5. 在**新版本**上施加校正变换                    ← 不回写旧版本（ADR-0002）
6. merge：把 entity_merge_candidates 对应行置 applied
```

**为什么变换落在新版本而不是旧版本**（P5G-1）：spec §3.2 验收 3 的文本顺序是
「更新 `:Entity` 节点 → 触发增量重算」，照字面实现会去改**旧版本**的节点，
直接违反 ADR-0002「历史版本不删不改」与 P5-F 的「旧版本一条不动」判据。
且 split 拆出的 N 个新节点**在 base 里根本不存在**——先改图的话，
incremental 的 probe 会把它们判成 `ENTITY_NOT_FOUND`。
⇒ 唯一的自洽顺序是「先产新版本、再在新版本上变换」。

**不做**（属后续批次，逐条登记）：

- **新版本图的完整性**（P5F-4 / D9）：新版本仍只承载受影响子图，
  未受影响节点不在新版本下 ⇒ 消费侧会只看到被校正的那一小撮节点。
  本批**不**把全图复制进新版本（那会打掉 P5F-3「增量重写节点数 = 校正节点数」
  的机械判据），改为做成显式断言 + 缺口登记。
- **`source_doc_ids`**（P5G-2）：校正是**实体级**动作，本批不做「实体 → 文档」
  反查，新版本行的 `source_doc_ids` 留空数组。
- **变换失败后的半成品版本处置**（P5G-6）：变换在增量重算**成功之后**执行，
  此时 `ontology_actions.result_kg_version` 已有值；变换失败时本模块**只抛错**
  （端点随之报错），**不**回滚 / **不**置 `failed` —— 那需要一套补偿语义，
  本批没有判据覆盖它，故不写。

**为什么受影响集要带上 1 跳邻居**（P5G-7）：`incremental` 只迁移「两端都在
受影响集内」的关系。若受影响集只有被校正的那一个节点，新版本里的该节点
**一条边都不会有** ⇒ merge 会把它的外部关系全丢掉、split 更是无从迁移。
故本模块把「被校正实体 ∪ 其 1 跳同 org 邻居」交给增量重算——1 跳**仍然**
远小于全图（`≠ N`），"不重建全图"的判据依旧成立。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.db.models import EntityMergeCandidate, OntologyAction
from app.services.kg.incremental import IncrementalRebuildError, rebuild_incrementally
from app.services.kg.versioning import KgVersioningService

__all__ = [
    "CorrectionResult",
    "OntologyCorrectionError",
    "merge_entities",
    "rename_entity",
    "split_entity",
]

#: 三个动作在 `ontology_actions.action_type` 里的取值（与 models.py 的
#: CheckConstraint 逐字一致，改一处必须改另一处）。
ACTION_MERGE = "merge"
ACTION_SPLIT = "split"
ACTION_RENAME = "rename"

#: m6 §4.5：拆分后原节点置 `status='split'`（该属性取值只有 `active` / `split`）。
_SPLIT_STATUS = "split"


# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #

#: 1 跳邻居（P5G-7）：关系迁移要求**两端都在新版本里**，故邻居必须一并重写。
#: ``org_id`` 过滤是应用层常设防线（DR-B5）——他 org 的邻居不得被带进本租户的新版本。
_CYPHER_NEIGHBORS = """
MATCH (a:Entity {id: $id, kg_version: $version})-[r:RELATION]-(b:Entity {kg_version: $version})
WHERE b.org_id = $org_id AND b.id <> $id
RETURN DISTINCT b.id AS id
"""

#: 目标实体**是否存在**、以及是否属于本 org。
#: 刻意用 ``OPTIONAL MATCH`` + 回读 ``org_id``：缺失与跨租户是两种**不同**的失败。
_CYPHER_PROBE_ENTITIES = """
UNWIND $ids AS eid
OPTIONAL MATCH (n:Entity {id: eid, kg_version: $version})
RETURN eid AS id, n.org_id AS org_id
"""

#: 读单个实体（``org_id`` 过滤是**应用层常设防线**，DR-B5：图谱侧永远没有 RLS 可依赖）。
_CYPHER_READ_ENTITY = """
MATCH (n:Entity {id: $id, kg_version: $version})
WHERE n.org_id = $org_id
RETURN properties(n) AS props
"""

#: 整体重写一个节点（``MERGE`` 幂等键 = ``(id, kg_version)``，ADR-0002 §3.1）。
_CYPHER_WRITE_ENTITY = """
MERGE (n:Entity {id: $id, kg_version: $version})
SET n = $props
"""

#: 出边（对端不在排除集内）。
_CYPHER_OUT_RELATIONS = """
MATCH (a:Entity {id: $id, kg_version: $version})-[r:RELATION]->(b:Entity {kg_version: $version})
WHERE NOT b.id IN $exclude_ids
RETURN properties(r) AS props, b.id AS other_id, b.canonical_name AS other_name
"""

#: 入边（同上）。方向与出边**分开**取，是为了迁移时能**保住原方向**——
#: 把 ``other -> r`` 改挂成 ``l -> other`` 会把关系语义反过来。
_CYPHER_IN_RELATIONS = """
MATCH (b:Entity {kg_version: $version})-[r:RELATION]->(a:Entity {id: $id, kg_version: $version})
WHERE NOT b.id IN $exclude_ids
RETURN properties(r) AS props, b.id AS other_id, b.canonical_name AS other_name
"""

#: 写一条关系（沿用 ``incremental._CYPHER_WRITE_RELATIONS`` 的幂等键口径
#: ``:RELATION {id, kg_version}``，真实语义在 ``relation_type`` 属性上）。
_CYPHER_WRITE_RELATION = """
MATCH (a:Entity {id: $source_id, kg_version: $version})
MATCH (b:Entity {id: $target_id, kg_version: $version})
MERGE (a)-[r:RELATION {id: $rid, kg_version: $version}]->(b)
SET r = $props
"""

#: 删一条关系（按幂等键定位；**迁移** = 搬走，不是复制）。
_CYPHER_DELETE_RELATION = """
MATCH (a:Entity {kg_version: $version})-[r:RELATION {id: $rid, kg_version: $version}]->()
DELETE r
"""

#: merge 后删除被并入侧（它已不再独立存在，见契约 description）。
_CYPHER_DETACH_DELETE_ENTITY = """
MATCH (n:Entity {id: $id, kg_version: $version})
DETACH DELETE n
"""


# --------------------------------------------------------------------------- #
# 异常与结果
# --------------------------------------------------------------------------- #


class OntologyCorrectionError(RuntimeError):
    """校正动作的**前置 / 执行**失败，带要映射到 HTTP 的错误码。

    与 `incremental.IncrementalRebuildError` 的分工：后者只在「一行版本都没落」
    的前置失败时抛，本异常覆盖本模块自己的全部失败面（含图谱不可用）。
    """

    def __init__(self, *, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    """一次校正动作的结果（`ontology_actions` 已被就地回填）。"""

    action_id: uuid.UUID
    action_type: str
    #: 操作时的 active 版本（= 动作行的 `kg_version`，用于回放）
    base_version: str
    #: 增量重算产出的新版本（= 响应体的 `kg_version`）
    kg_version: str
    #: 动作行记录的 `target_entities`
    target_entity_ids: tuple[str, ...]


# --------------------------------------------------------------------------- #
# 三个公开入口
# --------------------------------------------------------------------------- #


def merge_entities(
    *,
    db: Session,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    trace_id: uuid.UUID,
    left_entity_id: str,
    right_entity_id: str,
    graph_service: Any = None,
    session_factory: Any = None,
) -> CorrectionResult:
    """把 `right_entity_id` **并入** `left_entity_id`，产出新 `kg_version`。

    M6 §3.2 验收 3 / §4.5。落在新版本上的变换（P5G-4）：

    - 左侧吸收右侧：`aliases` 追加右规范名 + 右别名，`confidence` 取两侧较大；
    - 右侧的关系按**原方向**重挂到左侧（指向左 / 右自身的边丢弃，不成自环）；
    - 右侧节点 `DETACH DELETE`（契约 description：「合并后不再独立存在」）；
    - `entity_merge_candidates` 对应行 `human_review` → **`applied`**（M2 §4.5）。
    """
    if left_entity_id == right_entity_id:
        raise OntologyCorrectionError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="左右实体 id 相同 ⇒ 无从合并（合并需要两个不同实体）",
        )

    result = _run_action(
        db=db,
        org_id=org_id,
        actor_id=actor_id,
        trace_id=trace_id,
        action_type=ACTION_MERGE,
        target_entity_ids=(left_entity_id, right_entity_id),
        affected_entity_ids=(left_entity_id, right_entity_id),
        target_entities={
            "entity_ids": [left_entity_id, right_entity_id],
        },
        transform=lambda *, run, version: _merge_transform(
            run=run,
            org_id=org_id,
            version=version,
            left_entity_id=left_entity_id,
            right_entity_id=right_entity_id,
        ),
        graph_service=graph_service,
        session_factory=session_factory,
    )

    _mark_merge_candidate_applied(
        db=db,
        org_id=org_id,
        left_entity_id=left_entity_id,
        right_entity_id=right_entity_id,
    )
    return result


def split_entity(
    *,
    db: Session,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    trace_id: uuid.UUID,
    entity_id: str,
    new_canonical_names: Sequence[str],
    graph_service: Any = None,
    session_factory: Any = None,
) -> CorrectionResult:
    """把一个实体拆成 N 个（`new_canonical_names` **至少 2 个**），产出新 `kg_version`。

    M6 §3.2 验收 4 / §4.5。落在新版本上的变换（P5G-3）：

    - 创建 N 个新 `:Entity`（id = ``<原 id>--split-<序号>``，其余属性沿用原节点）；
    - 关系迁移取 spec 的**默认同名**规则：对端实体的 `canonical_name` **等于**
      某个新实体的规范名 ⇒ 迁到那个新实体（**保方向**、原边删除）；
      **匹配不上 ⇒ 留在原节点**（不丢、不猜）；
    - 原节点置 `status='split'`。
    """
    names = [str(name) for name in new_canonical_names]
    if len(names) < 2:
        raise OntologyCorrectionError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=f"拆分至少要 2 个新实体（实际 {len(names)}）：只拆 1 个等于改名，应走 rename",
        )

    new_ids = tuple(f"{entity_id}--split-{index}" for index in range(1, len(names) + 1))
    return _run_action(
        db=db,
        org_id=org_id,
        actor_id=actor_id,
        trace_id=trace_id,
        action_type=ACTION_SPLIT,
        target_entity_ids=(entity_id, *new_ids),
        affected_entity_ids=(entity_id,),
        target_entities={
            "entity_ids": [entity_id],
            "new_entity_ids": list(new_ids),
        },
        transform=lambda *, run, version: _split_transform(
            run=run,
            org_id=org_id,
            version=version,
            entity_id=entity_id,
            new_ids=new_ids,
            new_names=names,
        ),
        graph_service=graph_service,
        session_factory=session_factory,
    )


def rename_entity(
    *,
    db: Session,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    trace_id: uuid.UUID,
    entity_id: str,
    new_canonical_name: str,
    graph_service: Any = None,
    session_factory: Any = None,
) -> CorrectionResult:
    """改实体的规范名，产出新 `kg_version`。

    M6 §3.2 验收 5。落在新版本上的变换：`canonical_name` 换新，
    **旧名写入 `aliases`**（沿用 M2 §4.3）——规范名进抽取词表与消解键，
    旧名丢了会让历史证据对不上人。
    """
    return _run_action(
        db=db,
        org_id=org_id,
        actor_id=actor_id,
        trace_id=trace_id,
        action_type=ACTION_RENAME,
        target_entity_ids=(entity_id,),
        affected_entity_ids=(entity_id,),
        target_entities={
            "entity_ids": [entity_id],
            "new_canonical_name": new_canonical_name,
        },
        transform=lambda *, run, version: _rename_transform(
            run=run,
            org_id=org_id,
            version=version,
            entity_id=entity_id,
            new_canonical_name=new_canonical_name,
        ),
        graph_service=graph_service,
        session_factory=session_factory,
    )


# --------------------------------------------------------------------------- #
# 共用编排
# --------------------------------------------------------------------------- #


def _run_action(
    *,
    db: Session,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    trace_id: uuid.UUID,
    action_type: str,
    target_entity_ids: Sequence[str],
    affected_entity_ids: Sequence[str],
    target_entities: dict[str, Any],
    transform: Callable[..., None],
    graph_service: Any = None,
    session_factory: Any = None,
) -> CorrectionResult:
    """一次校正动作的骨架：**校验 → 审计 → 增量重算 → 变换**（顺序即纪律）。"""
    versioning = KgVersioningService(db)
    active = versioning.get_active(org_id=org_id)
    if active is None:
        raise OntologyCorrectionError(
            error_code=ErrorCode.KG_VERSION_NOT_ACTIVE,
            message="PG kg_versions 无 ready 版本 ⇒ 没有可校正的基线",
        )
    base_version = active.version

    factory = session_factory or _default_session_factory(graph_service)

    def run(cypher: str, params: dict[str, Any]) -> list[Any]:
        with factory() as session:
            return list(session.run(cypher, params))

    # ① 作用域校验：**先于任何写入** —— 跨租户必须既报错又零变更（判据 7）
    _probe_scope(
        run=run,
        org_id=org_id,
        version=base_version,
        entity_ids=list(affected_entity_ids),
    )
    # 受影响集 = 被校正实体 ∪ 其 1 跳邻居（P5G-7：关系的两端都得在新版本里）
    affected = [
        *affected_entity_ids,
        *_neighbor_ids(
            run=run,
            org_id=org_id,
            version=base_version,
            entity_ids=list(affected_entity_ids),
        ),
    ]

    # ② 审计先于变更：先拿 action_id（增量重算要读这一行校验 org 与基线）
    action = OntologyAction(
        org_id=org_id,
        action_type=action_type,
        target_entities=target_entities,
        actor_id=actor_id,
        kg_version=base_version,
        trace_id=trace_id,
    )
    db.add(action)
    db.commit()

    # ③ 增量重算：只重写受影响子图 → 新版本（旧版本一条不动）
    try:
        result = rebuild_incrementally(
            db=db,
            org_id=org_id,
            action_id=action.id,
            affected_entity_ids=affected,
            trace_id=trace_id,
            session_factory=factory,
        )
    except IncrementalRebuildError as exc:
        raise OntologyCorrectionError(
            error_code=exc.error_code, message=exc.message
        ) from exc
    if result.status != "ready":
        # **不**回落全量重建（Non-goal 9）：把失败码原样交给路由层
        raise OntologyCorrectionError(
            error_code=ErrorCode(result.error_code or ErrorCode.INTERNAL_ERROR),
            message="增量重算失败 ⇒ 校正未生效（没有回落全量重建）",
        )

    # ④ 在**新版本**上施加变换（P5G-1）
    try:
        transform(run=run, version=result.new_version)
    except OntologyCorrectionError:
        raise
    except Exception as exc:  # noqa: BLE001 - 图谱故障统一按基础设施不可用报
        raise OntologyCorrectionError(
            error_code=ErrorCode.NOT_IMPLEMENTED,
            message=f"校正变换写入失败: {type(exc).__name__}",
        ) from exc

    logger.bind(
        trace_id=str(trace_id),
        org_id=str(org_id),
        action_id=str(action.id),
        action_type=action_type,
        base_version=base_version,
        new_version=result.new_version,
    ).info("ontology_correction_applied")

    return CorrectionResult(
        action_id=action.id,
        action_type=action_type,
        base_version=base_version,
        kg_version=result.new_version,
        target_entity_ids=tuple(target_entity_ids),
    )


def _neighbor_ids(
    *, run: Any, org_id: uuid.UUID, version: str, entity_ids: list[str]
) -> list[str]:
    """取被校正实体的 **1 跳同 org 邻居**（P5G-7）。

    为什么必须带上它们：`incremental` 只迁移「两端都在受影响集内」的关系。
    只给被校正的那一个节点 ⇒ 新版本里它**一条边都没有** —— merge 会把外部
    关系全丢掉，split 更是无从迁移。带上 1 跳邻居后，被校正节点的边才能在
    新版本里被重建 / 迁移。1 跳**仍然**远小于全图，「不重建全图」判据不变。
    """
    found: list[str] = []
    for entity_id in entity_ids:
        for record in run(
            _CYPHER_NEIGHBORS,
            {"id": entity_id, "version": version, "org_id": str(org_id)},
        ):
            neighbor = str(record["id"])
            if neighbor not in found and neighbor not in entity_ids:
                found.append(neighbor)
    return found


def _default_session_factory(graph_service: Any) -> Any:
    """取 Neo4j 会话工厂（与 ``incremental._make_runner`` 同款：复用其连接）。"""
    from app.services.graphs import GraphService

    service = graph_service or GraphService.instance()
    return service._session  # noqa: SLF001 - 与 builder._run 同款，不自建驱动


def _probe_scope(
    *, run: Any, org_id: uuid.UUID, version: str, entity_ids: list[str]
) -> None:
    """目标实体必须**存在且属于本 org**；否则显式失败，**不**静默跳过。

    与 incremental 的同名函数**刻意不复用**：这里要的是「前端可见」的语义
    （跨 org ⇒ 403 `FORBIDDEN`，m6 §5.5 明文），而 incremental 用的是
    `KG_TENANT_LEAK`（图谱侧事故码）——两者都是 403，但归因不同。
    """
    try:
        records = run(_CYPHER_PROBE_ENTITIES, {"ids": entity_ids, "version": version})
    except Exception as exc:  # noqa: BLE001 - 图谱不可用 ⇒ 501，不伪装成数据问题
        raise OntologyCorrectionError(
            error_code=ErrorCode.NOT_IMPLEMENTED,
            message=f"图谱不可用（校正作用域校验失败）: {type(exc).__name__}",
        ) from exc

    org_value = str(org_id)
    leaked: list[str] = []
    missing: list[str] = []
    for record in records:
        node_org = record.get("org_id")
        if node_org is None:
            missing.append(str(record["id"]))
        elif str(node_org) != org_value:
            leaked.append(str(record["id"]))

    if leaked:
        raise OntologyCorrectionError(
            error_code=ErrorCode.FORBIDDEN,
            message=(
                f"目标实体不属于本 org（org_id={org_value}）: count={len(leaked)} "
                "—— 跨租户校正是数据污染，已拒绝（不降级为「只处理同租户的那个」）"
            ),
        )
    if missing:
        raise OntologyCorrectionError(
            error_code=ErrorCode.ENTITY_NOT_FOUND,
            message=(
                f"目标实体在 kg_version={version} 中不存在: count={len(missing)} "
                f"（{', '.join(missing[:5])}）"
            ),
        )


def _mark_merge_candidate_applied(
    *, db: Session, org_id: uuid.UUID, left_entity_id: str, right_entity_id: str
) -> None:
    """把 `entity_merge_candidates` 对应该pair 的行置 `applied`（M2 §4.5 / M6 §4.4）。

    左右**不区分方向**地匹配（消解候选的左右顺序取决于打分时的输入顺序）；
    没有对应行 ⇒ 什么都不做（合并也可以不经候选队列直接发起）。
    """
    row = db.scalar(
        select(EntityMergeCandidate)
        .where(
            EntityMergeCandidate.org_id == org_id,
            or_(
                (EntityMergeCandidate.left_entity_id == left_entity_id)
                & (EntityMergeCandidate.right_entity_id == right_entity_id),
                (EntityMergeCandidate.left_entity_id == right_entity_id)
                & (EntityMergeCandidate.right_entity_id == left_entity_id),
            ),
        )
        .order_by(EntityMergeCandidate.created_at.asc())
        .limit(1)
    )
    if row is None:
        return
    row.status = "applied"
    db.commit()


# --------------------------------------------------------------------------- #
# 三个变换（都作用在**新版本**上）
# --------------------------------------------------------------------------- #


def _merge_transform(
    *,
    run: Any,
    org_id: uuid.UUID,
    version: str,
    left_entity_id: str,
    right_entity_id: str,
) -> None:
    left = _read_entity(
        run=run, org_id=org_id, version=version, entity_id=left_entity_id
    )
    right = _read_entity(
        run=run, org_id=org_id, version=version, entity_id=right_entity_id
    )
    if left is None or right is None:
        raise OntologyCorrectionError(
            error_code=ErrorCode.ENTITY_NOT_FOUND,
            message="合并的两侧实体在新版本中缺失 ⇒ 增量重算结果被外部改动",
        )

    merged = dict(left)
    merged["id"] = left_entity_id
    merged["kg_version"] = version
    merged["org_id"] = str(org_id)
    merged["aliases"] = _merge_aliases(left, right)
    merged["confidence"] = max(
        _as_float(left.get("confidence")), _as_float(right.get("confidence"))
    )
    run(
        _CYPHER_WRITE_ENTITY,
        {"id": left_entity_id, "version": version, "props": merged},
    )

    # 关系：右侧的每条边按**原方向**重挂到左侧（两端都是合并参与方的边丢弃）
    _migrate_relations(
        run=run,
        version=version,
        from_id=right_entity_id,
        to_id=left_entity_id,
        exclude_ids=[left_entity_id, right_entity_id],
    )
    run(_CYPHER_DETACH_DELETE_ENTITY, {"id": right_entity_id, "version": version})


def _split_transform(
    *,
    run: Any,
    org_id: uuid.UUID,
    version: str,
    entity_id: str,
    new_ids: Sequence[str],
    new_names: Sequence[str],
) -> None:
    original = _read_entity(
        run=run, org_id=org_id, version=version, entity_id=entity_id
    )
    if original is None:
        raise OntologyCorrectionError(
            error_code=ErrorCode.ENTITY_NOT_FOUND,
            message="要拆分的实体在新版本中缺失 ⇒ 增量重算结果被外部改动",
        )

    inherited_aliases = _str_list(original.get("aliases"))
    for new_id, name in zip(new_ids, new_names, strict=True):
        props = dict(original)
        props["id"] = new_id
        props["kg_version"] = version
        props["org_id"] = str(org_id)
        props["canonical_name"] = str(name)
        props["aliases"] = list(inherited_aliases)
        run(_CYPHER_WRITE_ENTITY, {"id": new_id, "version": version, "props": props})

    # 关系迁移：**默认同名**（P5G-3）—— 对端 canonical_name 命中某个新实体 ⇒ 迁过去
    by_name = {
        str(name): new_id for new_id, name in zip(new_ids, new_names, strict=True)
    }
    for cypher, flip in (
        (_CYPHER_OUT_RELATIONS, False),
        (_CYPHER_IN_RELATIONS, True),
    ):
        for record in run(
            cypher, {"id": entity_id, "version": version, "exclude_ids": [entity_id]}
        ):
            moved_to = by_name.get(str(record["other_name"] or ""))
            if moved_to is None:
                # 匹配不上 ⇒ **留在原节点**：不删、不猜该挂给谁
                continue
            props = dict(record["props"])
            props["kg_version"] = version
            other_id = str(record["other_id"])
            rid = str(props.get("id") or f"{entity_id}->{other_id}")
            # ⚠️ **必须先删后建**：`_CYPHER_DELETE_RELATION` 只按 ``rid`` 定位，
            # 先建的话它会把刚挂到新节点上的那条一起删掉（迁移变成"搬丢了"）。
            run(_CYPHER_DELETE_RELATION, {"version": version, "rid": rid})
            source_id, target_id = (
                (moved_to, other_id) if not flip else (other_id, moved_to)
            )
            run(
                _CYPHER_WRITE_RELATION,
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "version": version,
                    "rid": rid,
                    "props": props,
                },
            )

    retired = dict(original)
    retired["status"] = _SPLIT_STATUS
    run(_CYPHER_WRITE_ENTITY, {"id": entity_id, "version": version, "props": retired})


def _rename_transform(
    *,
    run: Any,
    org_id: uuid.UUID,
    version: str,
    entity_id: str,
    new_canonical_name: str,
) -> None:
    props = _read_entity(run=run, org_id=org_id, version=version, entity_id=entity_id)
    if props is None:
        raise OntologyCorrectionError(
            error_code=ErrorCode.ENTITY_NOT_FOUND,
            message="要改名的实体在新版本中缺失 ⇒ 增量重算结果被外部改动",
        )

    old_name = str(props.get("canonical_name") or "").strip()
    updated = dict(props)
    updated["kg_version"] = version
    updated["org_id"] = str(org_id)
    updated["canonical_name"] = str(new_canonical_name)

    aliases = _str_list(props.get("aliases"))
    # 旧名入别名（M2 §4.3）；同名 / 空名不加 —— 否则别名里会塞进新名自己
    if old_name and old_name != str(new_canonical_name) and old_name not in aliases:
        aliases = [*aliases, old_name]
    updated["aliases"] = aliases
    run(_CYPHER_WRITE_ENTITY, {"id": entity_id, "version": version, "props": updated})


# --------------------------------------------------------------------------- #
# 内部小工具
# --------------------------------------------------------------------------- #


def _migrate_relations(
    *, run: Any, version: str, from_id: str, to_id: str, exclude_ids: list[str]
) -> None:
    """把 `from_id` 的关系按**原方向**重挂到 `to_id`（边 id 沿用，幂等键不变）。"""
    for cypher, flip in (
        (_CYPHER_OUT_RELATIONS, False),
        (_CYPHER_IN_RELATIONS, True),
    ):
        for record in run(
            cypher, {"id": from_id, "version": version, "exclude_ids": exclude_ids}
        ):
            props = dict(record["props"])
            props["kg_version"] = version
            other_id = str(record["other_id"])
            source_id, target_id = (to_id, other_id) if not flip else (other_id, to_id)
            run(
                _CYPHER_WRITE_RELATION,
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "version": version,
                    "rid": str(props.get("id") or f"{from_id}->{other_id}"),
                    "props": props,
                },
            )


def _read_entity(
    *, run: Any, org_id: uuid.UUID, version: str, entity_id: str
) -> dict[str, Any] | None:
    records = run(
        _CYPHER_READ_ENTITY,
        {"id": entity_id, "version": version, "org_id": str(org_id)},
    )
    return dict(records[0]["props"]) if records else None


def _merge_aliases(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    """左侧别名 ∪ 右规范名 ∪ 右别名（保序去重；空值不入列）。"""
    merged: list[str] = []
    for value in [
        *_str_list(left.get("aliases")),
        str(right.get("canonical_name") or ""),
        *_str_list(right.get("aliases")),
    ]:
        text = str(value).strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _str_list(value: Any) -> list[str]:
    """取字符串数组；脏值一律当空数组（**不**因此抛错中断变换）。"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _as_float(value: Any) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
