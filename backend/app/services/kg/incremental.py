"""M6 §3.3 **增量重算**（P5-F 批次 C）：只重写受影响子图，产出新的文档级 `kg_version`。

**为什么单独成文件**：增量重算是「校正动作 → 新版本」这条链的**唯一**落点，
消费者是 M6 §3.2 的三个校正动作（merge / split / rename）。它的两侧依赖
（PG 版本状态机 + Neo4j 子图重写）都已有真源，本模块只负责**编排**，不重造任何一个。

**三条硬纪律**（对应 proposal §3 Non-goals）：

1. **不重建全图**：只把**受影响实体**及其内部关系按 ``{id, kg_version}`` 幂等键
   MERGE 到**新**版本上；旧版本节点一条不动（ADR-0002 §3.1）。
2. **版本状态机复用** :class:`~app.services.kg.versioning.KgVersioningService`，
   **不另起一套**。spec §3.3 验收 6 写的 ``writing → active`` 与代码的
   ``pending → building → ready`` 是**同一状态机的两套命名**（``ready`` 即
   PG 真源的 active 语义，见 :meth:`KgVersioningService.activate_by_version`），
   本模块沿用代码真源，不改语义（登记 **P5F-1**）。
3. **失败显式失败**：增量重写失败 ⇒ 落 ``error_code`` / ``error_detail`` 并把
   版本行置 ``failed``，**绝不**静默回落全量重建——那会让「增量 / 全量成本比」
   永远测不出来（M6 §3.4 的 C3 取证字段直接失效）。

**不做**（属后续批次）：Neo4j 镜像的**全局**激活（把其它版本置 ``superseded``）。
本批只同步本版本自己的 ``:KgVersionMirror`` 状态——新版本目前只承载受影响子图，
把它置为全局 active 会让读侧**只看到被校正的那一小撮节点**；「新版本如何包含
未受影响节点」须与三端点语义同批裁决（登记 **P5F-4**）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import KgVersion, OntologyAction
from app.services.kg.versioning import KgVersioningService

__all__ = [
    "IncrementalRebuildError",
    "IncrementalRebuildResult",
    "rebuild_incrementally",
]

# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #

#: 诊断：受影响的实体**是否存在**、以及是否属于本 org。
#: 刻意用 ``OPTIONAL MATCH`` + 回读 ``org_id``：缺失与跨租户是两种**不同**的失败，
#: 合并成一句「查不到」会让「别的租户的节点被当成本租户的重写」这种事故静默发生。
_CYPHER_PROBE_ENTITIES = """
UNWIND $ids AS eid
OPTIONAL MATCH (n:Entity {id: eid, kg_version: $base})
RETURN eid AS id, n.org_id AS org_id
"""

#: 读旧版本的受影响节点（``org_id`` 过滤是**应用层常设防线**，DR-B5：
#: 图谱侧永远不会有 RLS 可依赖）。
_CYPHER_READ_ENTITIES = """
UNWIND $ids AS eid
MATCH (n:Entity {id: eid, kg_version: $base})
WHERE n.org_id = $org_id
RETURN eid AS id, properties(n) AS props
"""

#: 重写到新版本：``MERGE`` 幂等键 = ``(id, kg_version)``（ADR-0002 §3.1）。
#: ``SET m = row.props`` 整体覆盖，``kg_version`` / ``org_id`` 已在 Python 侧改好
#: （Cypher 里再 ``SET`` 一次同一属性属重复键，故不留第二句）。
_CYPHER_WRITE_ENTITIES = """
UNWIND $rows AS row
MERGE (m:Entity {id: row.id, kg_version: $new})
SET m = row.props
"""

#: 受影响子图的**内部**关系（两端都在受影响集合内）。
_CYPHER_READ_RELATIONS = """
MATCH (a:Entity {kg_version: $base})-[r]->(b:Entity {kg_version: $base})
WHERE a.id IN $ids AND b.id IN $ids
  AND a.org_id = $org_id AND b.org_id = $org_id
RETURN a.id AS source_id, b.id AS target_id, properties(r) AS props
"""

#: 关系重写：沿用 ``builder.py::_CYPHER_STAGE3_LOAD_RELATIONS`` 的幂等键口径
#: ``:RELATION {id, kg_version}``（真实语义写在 ``relation_type`` 属性上，
#: 真机实测如此——不在 Cypher 里拼关系类型，避免动态类型注入）。
_CYPHER_WRITE_RELATIONS = """
UNWIND $rows AS row
MATCH (a:Entity {id: row.source_id, kg_version: $new})
MATCH (b:Entity {id: row.target_id, kg_version: $new})
MERGE (a)-[rel:RELATION {id: row.rid, kg_version: $new}]->(b)
SET rel = row.props
"""

#: 版本镜像：**只写本版本自己**，不把其它版本置 ``superseded``（见文件头第 3 条）。
_CYPHER_MIRROR_VERSION = """
MERGE (v:KgVersionMirror {version: $version, org_id: $org_id})
ON CREATE SET v.status = $status,
              v.trace_id = $trace_id,
              v.created_at = datetime()
ON MATCH SET v.status = $status,
             v.trace_id = $trace_id
"""


# --------------------------------------------------------------------------- #
# 异常与结果
# --------------------------------------------------------------------------- #


class IncrementalRebuildError(RuntimeError):
    """增量重算的**前置**不成立（调用方错误）⇒ **不**落 `kg_versions` 行。

    与「重写过程中失败」区分：后者是**已开工**的失败，必须留一条 ``failed``
    版本行供审计回放（spec §3.3 验收 6 的 ``NULL = 未完成或失败`` 语义）。
    """

    def __init__(self, *, error_code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True, slots=True)
class IncrementalRebuildResult:
    """一次增量重算的结果（`ontology_actions` 已被就地回填）。"""

    action_id: uuid.UUID
    #: 基线版本（重算前的 active 版本）
    base_version: str
    #: 产出的新版本；前置不成立时为 ``None``（那种情况抛异常，不会走到这里）
    new_version: str
    #: ``ready`` / ``failed``（PG 真源口径；``ready`` 即 active 语义）
    status: str
    entity_count: int
    relation_count: int
    batch_count: int
    error_code: str | None
    error_detail: str | None


class _RebuildFailure(Exception):
    """重写过程中的失败（内部用）：带要落库的 `error_code` / `error_detail`。"""

    def __init__(self, *, error_code: ErrorCode, error_detail: str) -> None:
        super().__init__(error_detail)
        self.error_code = str(error_code)
        self.error_detail = error_detail


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #


def rebuild_incrementally(
    *,
    db: Session,
    org_id: uuid.UUID,
    action_id: uuid.UUID,
    affected_entity_ids: Sequence[str],
    source_doc_ids: Sequence[uuid.UUID] = (),
    trace_id: uuid.UUID | None = None,
    graph_service: Any = None,
    session_factory: Any = None,
    batch_size: int | None = None,
) -> IncrementalRebuildResult:
    """按受影响的实体集**增量**重算，产出新的文档级 `kg_version` 并回填动作行。

    M6 §3.3 验收 6 / 7。三件事在同一个调用里做完：

    1. **建新版本行**：``create_pending → mark_building``（状态机复用
       :class:`KgVersioningService`）；
    2. **只重写受影响子图**：受影响节点 + 其内部关系按幂等键 MERGE 到新版本，
       **旧版本一条不动**；
    3. **回填** ``ontology_actions.result_kg_version``（成功）/ ``error_code``
       + ``error_detail``（失败，且 ``result_kg_version`` 保持 ``NULL``）。

    :param action_id: 触发本次重算的 `ontology_actions.id`（**必须是本 org 的行**）。
    :param affected_entity_ids: 受影响的实体 id。由调用方从动作行的
        ``target_entities`` 给出——本模块**不猜**它的形状（形状随动作而变）。
    :param source_doc_ids: 受影响文档。**仅文档级**：新版本行的 ``source_doc_ids``
        只含这批文档（P5F-2），不把全量文档挂上去。
    :param graph_service: 注入图谱服务（测试指向真 Neo4j）；缺省单例。
    :param session_factory: 注入 Neo4j 会话工厂（测试用）；优先于 ``graph_service``。
    :param batch_size: 覆盖 ``settings.increment_rebuild_batch_size``。
    :raises IncrementalRebuildError: 前置不成立（动作行不存在 / 无 active 版本 /
        基线版本漂移 / 受影响集为空）⇒ 一行 `kg_versions` 都不会落。
    """
    settings = get_settings()
    size = (
        batch_size if batch_size is not None else settings.increment_rebuild_batch_size
    )
    if size <= 0:
        raise IncrementalRebuildError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=f"increment_rebuild_batch_size 必须为正整数（实际={size}）",
        )

    entity_ids = [str(item) for item in affected_entity_ids]
    if not entity_ids:
        raise IncrementalRebuildError(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="受影响实体集为空 ⇒ 无可重算子图（调用方须给出 target_entities）",
        )

    action = db.scalar(
        select(OntologyAction).where(
            OntologyAction.id == action_id,
            # 应用层 org 过滤是常设防线（DR-B5）：RLS 生效也不拆
            OntologyAction.org_id == org_id,
        )
    )
    if action is None:
        raise IncrementalRebuildError(
            error_code=ErrorCode.NOT_FOUND,
            message=f"ontology_actions 无该行: action_id={action_id} org_id={org_id}",
        )

    versioning = KgVersioningService(db)
    active = versioning.get_active(org_id=org_id)
    if active is None:
        raise IncrementalRebuildError(
            error_code=ErrorCode.KG_VERSION_NOT_ACTIVE,
            message="PG kg_versions 无 ready 版本 ⇒ 没有可增量的基线",
        )
    base_version = active.version
    if action.kg_version and action.kg_version != base_version:
        # 不静默按当前版本重算：动作行记录的基线与现状不一致 ⇒ 有人改过图，
        # 硬算会把「基于陈旧版本的重算」伪装成正常结论（plan §4.4 纪律）。
        raise IncrementalRebuildError(
            error_code=ErrorCode.KG_VERSION_NOT_ACTIVE,
            message=(
                f"动作行记录的基线 kg_version={action.kg_version} 与当前 active "
                f"{base_version} 不一致 ⇒ 拒绝增量重算"
            ),
        )

    trace = trace_id or action.trace_id
    new_version = _next_version(db=db, org_id=org_id)
    record = versioning.create_pending(
        org_id=org_id,
        version=new_version,
        source_doc_ids=list(source_doc_ids),
        trace_id=trace,
    )
    versioning.mark_building(record.id)

    run = _make_runner(graph_service=graph_service, session_factory=session_factory)
    try:
        entity_count, relation_count, batch_count = _rewrite_subgraph(
            run=run,
            org_id=org_id,
            base_version=base_version,
            new_version=new_version,
            entity_ids=entity_ids,
            batch_size=size,
        )
        _mirror_version(
            run=run,
            org_id=org_id,
            version=new_version,
            status="building",
            trace_id=trace,
        )
    except _RebuildFailure as exc:
        return _fail(
            db=db,
            versioning=versioning,
            action=action,
            version_id=record.id,
            base_version=base_version,
            new_version=new_version,
            error_code=exc.error_code,
            error_detail=exc.error_detail,
        )
    except Exception as exc:  # noqa: BLE001 - 统一兜底：任何图侧故障都不得静默
        return _fail(
            db=db,
            versioning=versioning,
            action=action,
            version_id=record.id,
            base_version=base_version,
            new_version=new_version,
            # 基础设施不可用的项目既有口径 = 501（NOT_IMPLEMENTED），见 errors.py
            error_code=str(ErrorCode.NOT_IMPLEMENTED),
            error_detail=f"增量重写失败: {type(exc).__name__}",
        )

    versioning.mark_ready(
        record.id, entity_count=entity_count, relation_count=relation_count
    )
    try:
        _mirror_version(
            run=run,
            org_id=org_id,
            version=new_version,
            status="ready",
            trace_id=trace,
        )
    except Exception as exc:  # noqa: BLE001 - 镜像是冗余，失败不推翻 PG 真源
        logger.bind(
            version=new_version, org_id=str(org_id), reason=type(exc).__name__
        ).warning("incremental_rebuild_mirror_failed")

    action.result_kg_version = new_version
    action.error_code = None
    action.error_detail = None
    db.commit()

    logger.bind(
        trace_id=str(trace),
        org_id=str(org_id),
        action_id=str(action_id),
        base_version=base_version,
        new_version=new_version,
        entity_count=entity_count,
        relation_count=relation_count,
        batch_count=batch_count,
    ).info("ontology_incremental_rebuild_done")

    return IncrementalRebuildResult(
        action_id=action_id,
        base_version=base_version,
        new_version=new_version,
        status="ready",
        entity_count=entity_count,
        relation_count=relation_count,
        batch_count=batch_count,
        error_code=None,
        error_detail=None,
    )


# --------------------------------------------------------------------------- #
# 内部
# --------------------------------------------------------------------------- #


def _fail(
    *,
    db: Session,
    versioning: KgVersioningService,
    action: OntologyAction,
    version_id: uuid.UUID,
    base_version: str,
    new_version: str,
    error_code: str,
    error_detail: str,
) -> IncrementalRebuildResult:
    """失败落库：版本行置 ``failed`` + 动作行落错误码，**不**回填新版本。

    ⚠️ **不回落全量重建**（proposal Non-goal 9）：这里如果悄悄重跑一次全量导入，
    「增量 vs 全量成本比」这个 C3 取证字段（M6 §3.4）就永远测不出来。
    """
    versioning.mark_failed(version_id, error_code=error_code, error_detail=error_detail)
    action.error_code = error_code
    action.error_detail = error_detail
    # result_kg_version 保持 NULL（spec §4.2：NULL = 未完成或失败）
    db.commit()

    # error_detail **敏感**（spec §4.2 标注）⇒ 日志只落错误码，不落原文（P5-E 口径）
    logger.bind(
        org_id=str(action.org_id),
        action_id=str(action.id),
        base_version=base_version,
        new_version=new_version,
        error_code=error_code,
    ).warning("ontology_incremental_rebuild_failed")

    return IncrementalRebuildResult(
        action_id=action.id,
        base_version=base_version,
        new_version=new_version,
        status="failed",
        entity_count=0,
        relation_count=0,
        batch_count=0,
        error_code=error_code,
        error_detail=error_detail,
    )


def _rewrite_subgraph(
    *,
    run: Any,
    org_id: uuid.UUID,
    base_version: str,
    new_version: str,
    entity_ids: list[str],
    batch_size: int,
) -> tuple[int, int, int]:
    """只重写受影响子图；返回 ``(节点数, 关系数, 批数)``。"""
    _probe_scope(
        run=run, org_id=org_id, base_version=base_version, entity_ids=entity_ids
    )

    entity_count = 0
    batch_count = 0
    for batch in _batches(entity_ids, batch_size):
        rows = [
            {
                "id": str(record["id"]),
                "props": _with_ownership(
                    dict(record["props"]), org_id=org_id, version=new_version
                ),
            }
            for record in run(
                _CYPHER_READ_ENTITIES,
                {"ids": batch, "base": base_version, "org_id": str(org_id)},
            )
        ]
        if rows:
            run(_CYPHER_WRITE_ENTITIES, {"rows": rows, "new": new_version})
        entity_count += len(rows)
        batch_count += 1

    relation_rows: list[dict[str, Any]] = []
    for record in run(
        _CYPHER_READ_RELATIONS,
        {"ids": entity_ids, "base": base_version, "org_id": str(org_id)},
    ):
        props = _with_ownership(
            dict(record["props"]), org_id=org_id, version=new_version
        )
        relation_rows.append(
            {
                "source_id": str(record["source_id"]),
                "target_id": str(record["target_id"]),
                "rid": str(props.get("id") or _relation_key(record, props)),
                "props": props,
            }
        )

    for batch in _batches(relation_rows, batch_size):
        run(_CYPHER_WRITE_RELATIONS, {"rows": batch, "new": new_version})
        batch_count += 1

    return entity_count, len(relation_rows), batch_count


def _probe_scope(
    *,
    run: Any,
    org_id: uuid.UUID,
    base_version: str,
    entity_ids: list[str],
) -> None:
    """受影响实体必须**存在且属于本 org**；否则显式失败（不静默跳过）。

    两种失败分开设码：跨租户是**数据污染**（KG_TENANT_LEAK，比"没找到"严重得多），
    ``NOT_FOUND`` 只是输入错。混用会让前者被当成后者轻轻放过。
    """
    org_value = str(org_id)
    leaked: list[str] = []
    missing: list[str] = []
    for record in run(
        _CYPHER_PROBE_ENTITIES, {"ids": entity_ids, "base": base_version}
    ):
        node_org = record.get("org_id")
        if node_org is None:
            missing.append(str(record["id"]))
        elif str(node_org) != org_value:
            leaked.append(str(record["id"]))

    if leaked:
        raise _RebuildFailure(
            error_code=ErrorCode.KG_TENANT_LEAK,
            error_detail=(
                f"受影响实体不属于本 org（org_id={org_value}）: "
                f"count={len(leaked)} —— 跨租户重算是数据污染，已拒绝"
            ),
        )
    if missing:
        raise _RebuildFailure(
            error_code=ErrorCode.ENTITY_NOT_FOUND,
            error_detail=(
                f"受影响实体在 kg_version={base_version} 中不存在: count={len(missing)}"
            ),
        )


def _with_ownership(
    props: dict[str, Any], *, org_id: uuid.UUID, version: str
) -> dict[str, Any]:
    """副本上**钉死** ``kg_version`` / ``org_id``（幂等键与隔离键不容继承旧值）。"""
    props["kg_version"] = version
    props["org_id"] = str(org_id)
    return props


def _relation_key(record: Any, props: dict[str, Any]) -> str:
    """关系缺 ``id`` 属性时的**稳定**幂等键（同端点 + 同语义 ⇒ 同一条边）。"""
    return "{}->{}:{}".format(
        record["source_id"],
        record["target_id"],
        props.get("relation_type") or "",
    )


def _mirror_version(
    *, run: Any, org_id: uuid.UUID, version: str, status: str, trace_id: uuid.UUID
) -> None:
    """同步 Neo4j 的冗余镜像（**只写本版本**，不置其它版本为 superseded）。"""
    run(
        _CYPHER_MIRROR_VERSION,
        {
            "version": version,
            "org_id": str(org_id),
            "status": status,
            "trace_id": str(trace_id),
        },
    )


def _next_version(*, db: Session, org_id: uuid.UUID) -> str:
    """生成同 org 唯一的增量版本号 ``<%Y%m%dT%H%M%SZ>-inc-<8hex>``（**恒 29 字符**）。

    ⚠️ **为什么不能把 base 拼进来**（2026-10-08 实测反哺，P5-I0）：

    旧写法是 ``f"{base}-inc-{uuid4hex6}"`` —— 每级 **+11 字符**，而 base 自己又是
    更早的版本拼出来的。基线号格式见 ``scripts/import_to_neo4j.py::_default_kg_version``
    （``YYYYMMDDTHHMMSSZ-<8hex>`` = 25 字符），于是：

    ```
    1 级 36 ✓ ／ 2 级 47 ✓ ／ 3 级 58 ✓ ／ 4 级 69 ✗
    ```

    而 ``kg_versions.version`` 是 ``String(64)``（``app/db/models.py:286``）⇒
    **连续第 4 次校正必然抛 PG 「value too long」**，形态是 **500**，
    走不到任何既有业务错误码（不是 404 / 409 / 501），前端只能显示"未知错误"。
    这不是推算：P5-H 写多级版本链用例时撞的就是它（当时被迫用最短后缀绕过）。

    **版本号不承载父子关系**：某个版本"从哪个版本校正而来"的唯一真源是
    ``ontology_actions.kg_version`` / ``result_kg_version`` 两列
    （**ADR-0008 §3**），版本号字符串从来不是它的消费者；运营侧溯源查该表即可，
    本模块完成日志本来就同时打了 ``base_version`` 与 ``new_version`` 两个字段。
    ⇒ 丢掉 base 拼接**不丢任何语义**，换来的是"版本号长度与校正次数无关"。
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(8):
        candidate = f"{stamp}-inc-{uuid.uuid4().hex[:8]}"
        exists = db.scalar(
            select(KgVersion.id).where(
                KgVersion.org_id == org_id, KgVersion.version == candidate
            )
        )
        if exists is None:
            return candidate
    raise IncrementalRebuildError(
        error_code=ErrorCode.INTERNAL_ERROR,
        message="连续 8 次未生成唯一增量版本号",
    )


def _batches(items: Sequence[Any], size: int) -> Iterator[list[Any]]:
    """按批切片（与 ``builder._chunks_by_batches`` 同口径）。"""
    return (list(items[index : index + size]) for index in range(0, len(items), size))


def _make_runner(*, graph_service: Any, session_factory: Any) -> Any:
    """造一个 ``(cypher, params) -> list[record]`` 执行器。

    会话来源二选一：注入的 ``session_factory`` 优先（测试用），否则走
    ``GraphService`` **懒加载的那条连接**（与 ``builder._run`` 同口径，不自建驱动）。
    """
    factory = session_factory
    if factory is None:
        from app.services.graphs import GraphService

        service = graph_service or GraphService.instance()
        factory = service._session  # noqa: SLF001 - 与 builder._run 同款：复用其连接

    def _run(cypher: str, params: dict[str, Any]) -> list[Any]:
        with factory() as session:
            return list(session.run(cypher, params))

    return _run
