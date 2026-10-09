"""M6 **本体增量演进**路由（`specs/m6-ontology-incremental.md` §5.5）。

**进度**：`cold-start` / `confirm` / `active` 由 P5-C（2026-10-07）接线；
`merge` / `split` / `rename` 由 **P5-G（2026-10-08）**接线——增量重算（P5-F）
落地后，这三个端点的最后一个硬前置消失了。

**三端点只做编排，不写 Cypher**（D3）：图操作与增量重算的编排在
`app.services.kg.correction`，路由层只负责「入参 → 服务 → 响应 / 错误映射」。
与 `confirm` 端点的分工同款。

**RBAC**：六个端点全部挂 `require_permission(RESOURCE_ONTOLOGY, read/write)`
（三端点从这一批起**真会写库与写图**，不挂等于给租户内任意主体开一个写入口）。

**为什么此前占位返回 501 而不是 200**：返回 200 空结果会让前端以为接口可用——
业务未实现却报成功，是本项目反复拦的那种"假做"。现在它们返回 200，
且 200 的**前提**是真产出了新 `kg_version`。
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    ENTITY_NOT_FOUND,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    SCHEMA_VERSION_NOT_ACTIVE,
    TENANT_ERROR_RESPONSES,
    VALIDATION_ERROR,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.ontology import (
    OntologyActionResponse,
    OntologyActiveResponse,
    OntologyCandidateListResponse,
    OntologyColdStartRequest,
    OntologyColdStartResponse,
    OntologyConfirmRequest,
    OntologyConfirmResponse,
    OntologyMergeRequest,
    OntologyRenameRequest,
    OntologySplitRequest,
)
from app.services.kg.correction import (
    OntologyCorrectionError,
    merge_entities,
    rename_entity,
    split_entity,
)
from app.services.ontology import (
    CANDIDATE_PAGE_SIZE_DEFAULT,
    CANDIDATE_PAGE_SIZE_MAX,
    OntologySuggestError,
    OntologyVersionConflictError,
    confirm_ontology_schema,
    list_merge_candidates,
    load_active_ontology,
    suggest_ontology_types,
)
from app.services.rbac.deps import require_permission
from app.services.rbac.policy import ACTION_READ, ACTION_WRITE, RESOURCE_ONTOLOGY

router = APIRouter(prefix="/ontology", tags=["ontology"])

#: 三端点共用的错误响应声明（**错误码一个都没新增**，Non-goal 7）
_CORRECTION_ERROR_RESPONSES = {
    **TENANT_ERROR_RESPONSES,
    **ENTITY_NOT_FOUND,
    **KG_VERSION_NOT_ACTIVE,
    **NOT_IMPLEMENTED,
}


def _raise_correction_error(exc: OntologyCorrectionError) -> None:
    """把服务层的失败**原样**转成统一错误体（**不**降级、**不**回落全量重建）。"""
    raise AppError(exc.error_code, exc.message) from exc


@router.post(
    "/cold-start",
    response_model=OntologyColdStartResponse,
    operation_id="coldStartOntology",
    summary="本体冷启动建议（M6 §3.1）",
    description=(
        "给一段业务域描述，**建议**一组实体 / 关系类型（LLM 调用）。\n\n"
        "**仅建议、未生效**：本端点**不**写 `ontology_schemas`；要生效必须再调 "
        "`POST /ontology/confirm`（M6 §3.1 验收 1 / §3.5 验收 12）。\n\n"
        "**错误语义**：跨租户 → 403 `FORBIDDEN`；LLM 建议解析失败 → 500 "
        '`INTERNAL_ERROR`（**不**静默回落内置枚举——悄悄塞一组"看起来合理"的类型，'
        "等于替用户做决策）。"
    ),
    responses={**TENANT_ERROR_RESPONSES},
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)],
)
async def cold_start_ontology(
    identity: CurrentIdentity,
    trace_id: TraceId,
    payload: OntologyColdStartRequest,
) -> OntologyColdStartResponse:
    try:
        suggestion = suggest_ontology_types(
            domain_description=payload.domain_description
        )
    except OntologySuggestError as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "Ontology suggestion failed",
            detail={
                "reason": str(exc),
                "hint": "LLM 未返回可解析的类型集；重试或改写 domain_description",
            },
        ) from exc

    return OntologyColdStartResponse(
        suggested_entity_types=list(suggestion.entity_types),
        suggested_relation_types=list(suggestion.relation_types),
        trace_id=trace_id,
    )


@router.post(
    "/confirm",
    response_model=OntologyConfirmResponse,
    operation_id="confirmOntology",
    summary="确认本体 schema 生效（M6 §3.1 验收 2）",
    description=(
        "把（人工在校正 GUI 上确认过的）类型集写入 `ontology_schemas`，置 "
        "`status='active'`。\n\n"
        "**唯一会写生效状态的端点**：冷启动只建议、merge / split / rename 产新 "
        "`kg_version` 但**不改本体**——GAP-F2「严禁 LLM 自动修改本体」的落点。\n\n"
        "**换域（同租户确认新版本）**：旧 `active` 行置 `superseded`、新行按请求里的 "
        "`version` 落 `active`（§4.6）；历史图谱**不**回溯重算。\n\n"
        "**审计**：同事务写一行 `ontology_actions(action_type='confirm')` —— "
        "「谁确认的」这件事必须与「本体生效」同时成立（§3.5 验收 12）。\n\n"
        "**重复确认 → 409** `SCHEMA_VERSION_NOT_ACTIVE`：同一 `version` 二次确认一律拒绝，"
        "**不**静默复用旧版本（与 `KG_VERSION_NOT_ACTIVE` 同一纪律）。\n\n"
        "**错误语义**：重复确认 / 版本冲突 → 409；跨租户 → 403。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **SCHEMA_VERSION_NOT_ACTIVE,
    },
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)],
)
async def confirm_ontology(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    payload: OntologyConfirmRequest,
) -> OntologyConfirmResponse:
    try:
        row = confirm_ontology_schema(
            db=db,
            org_id=identity.org_id,
            actor_id=identity.actor_id,
            trace_id=uuid.UUID(trace_id),
            version=payload.version,
            entity_types=[
                item.model_dump(exclude_none=True) for item in payload.entity_types
            ],
            relation_types=[
                item.model_dump(exclude_none=True) for item in payload.relation_types
            ],
            # X-2c：契约不带 domain_description，写空串表示"未知"，不替用户编描述
            domain_description="",
            suggested_by_llm=False,
        )
    except OntologyVersionConflictError as exc:
        raise AppError(
            ErrorCode.SCHEMA_VERSION_NOT_ACTIVE,
            "Ontology schema version conflict",
            detail={"version": payload.version, "reason": str(exc)},
        ) from exc

    return OntologyConfirmResponse(version=row.version, status="active")


@router.post(
    "/merge",
    response_model=OntologyActionResponse,
    operation_id="mergeOntologyEntities",
    summary="合并两个实体（M6 §3.2 三动作之一）",
    description=(
        "把 `right_entity_id` 并入 `left_entity_id`，产出**新的** `kg_version`。\n\n"
        "**跨 org → 403** `FORBIDDEN`：两个实体必须同属当前租户，"
        "跨租户合并是数据污染，**不**降级为「只合并同租户的那个」。\n\n"
        "**落点**：右侧属性并入左侧（`aliases` 吸收右名、`confidence` 取较大），"
        "右侧关系按原方向重挂到左侧，右侧节点不再独立存在；"
        "`entity_merge_candidates` 对应行 `human_review` → **`applied`**（M2 §4.5）。\n\n"
        "**错误语义**：跨租户 → 403；实体不存在 / 不在 active 版本 → 404；"
        "无 active `kg_version` → 409；图谱不可用 → 501。"
    ),
    responses=_CORRECTION_ERROR_RESPONSES,
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)],
)
async def merge_ontology_entities(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    payload: OntologyMergeRequest,
) -> OntologyActionResponse:
    try:
        result = merge_entities(
            db=db,
            org_id=identity.org_id,
            actor_id=identity.actor_id,
            trace_id=uuid.UUID(trace_id),
            left_entity_id=payload.left_entity_id,
            right_entity_id=payload.right_entity_id,
        )
    except OntologyCorrectionError as exc:
        _raise_correction_error(exc)
    return OntologyActionResponse(kg_version=result.kg_version, status="applied")


@router.post(
    "/split",
    response_model=OntologyActionResponse,
    operation_id="splitOntologyEntity",
    summary="拆分一个实体（M6 §3.2 三动作之一）",
    description=(
        "把一个实体拆成多个新实体（`new_entities[]` **至少 2 个**——只拆出 1 个等于改名，"
        "应走 `POST /ontology/rename`），产出**新的** `kg_version`。\n\n"
        "⚠️ `new_entities[]` 每项目前**只有 `canonical_name`**：spec §5.5 写的是 "
        "`{canonical_name, ...}`，省略号部分**不自行展开**（功能预留原则）。\n\n"
        "**关系迁移取 spec 的「默认同名」规则**：对端实体的 `canonical_name` 命中某个"
        "新实体 ⇒ 迁过去（保方向）；**命中不上 ⇒ 留在原节点**，不删也不猜。"
        "原节点置 `status='split'`（§4.5）。\n\n"
        "**错误语义**：跨租户 → 403；实体不存在 → 404；无 active `kg_version` → 409；"
        "图谱不可用 / 入参不足 2 个新实体 → 501 / 400。"
    ),
    responses=_CORRECTION_ERROR_RESPONSES,
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)],
)
async def split_ontology_entity(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    payload: OntologySplitRequest,
) -> OntologyActionResponse:
    try:
        result = split_entity(
            db=db,
            org_id=identity.org_id,
            actor_id=identity.actor_id,
            trace_id=uuid.UUID(trace_id),
            entity_id=payload.entity_id,
            new_canonical_names=[item.canonical_name for item in payload.new_entities],
        )
    except OntologyCorrectionError as exc:
        _raise_correction_error(exc)
    return OntologyActionResponse(kg_version=result.kg_version, status="applied")


@router.post(
    "/rename",
    response_model=OntologyActionResponse,
    operation_id="renameOntologyEntity",
    summary="改实体规范名（M6 §3.2 三动作之一）",
    description=(
        "改实体的规范名，产出**新的** `kg_version`。\n\n"
        "**为什么改名也算本体动作**：规范名进入抽取词表与消解键，改名等价于"
        "重跑一段图谱——所以它**必须**产新版本，而不是原地 UPDATE。\n\n"
        "**旧名不丢**：改名后旧 `canonical_name` 写入 `:Entity.aliases`（沿用 M2 §4.3），"
        "否则历史证据会对不上人。\n\n"
        "**错误语义**：跨租户 → 403；实体不存在 → 404；无 active `kg_version` → 409；"
        "图谱不可用 → 501。"
    ),
    responses=_CORRECTION_ERROR_RESPONSES,
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)],
)
async def rename_ontology_entity(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    payload: OntologyRenameRequest,
) -> OntologyActionResponse:
    try:
        result = rename_entity(
            db=db,
            org_id=identity.org_id,
            actor_id=identity.actor_id,
            trace_id=uuid.UUID(trace_id),
            entity_id=payload.entity_id,
            new_canonical_name=payload.new_canonical_name,
        )
    except OntologyCorrectionError as exc:
        _raise_correction_error(exc)
    return OntologyActionResponse(kg_version=result.kg_version, status="applied")


@router.get(
    "/candidates",
    response_model=OntologyCandidateListResponse,
    operation_id="listOntologyCandidates",
    summary="读取本租户的实体消解候选（M6 §1.1 批次 B：GUI 的实体来源）",
    description=(
        "返回当前租户的 `entity_merge_candidates` 候选对，**按 `created_at DESC`**、"
        "分页返回（`page` 1-based，`page_size` 默认 **50**、上限 100）。\n\n"
        "**它是校正 GUI 的实体来源**——m6 §1.1 第 2 条要求 GUI 与该表**绑定**，"
        "因此 GUI **不**另造实体搜索端点：人从候选行上挑出实体，再发 "
        "`POST /ontology/merge` / `/split` / `/rename`。\n\n"
        "**过滤**：`status` 取 `pending` / `auto_merged` / `human_review` / "
        "`rejected` / `applied` 之一；**非法值 → 400** `VALIDATION_ERROR`，"
        "**不**静默当全量返回（与 `GET /audit` 同口径）。\n\n"
        "**跨租户 ⇒ 空集**（`items=[]` 且 `total=0`）：列表类端点泄露不了单条资源的"
        "存在性，返回 403 会让「队列为空」和「无权访问」在 UI 上无法区分。\n\n"
        "**错误语义**：非法 `status` → 400；跨租户 → 403；未认证 → 401。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR},
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_READ)],
)
async def list_ontology_candidates(
    identity: CurrentIdentity,
    db: DbSession,
    status: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=32,
            description=(
                "按处置档位过滤：`pending` / `auto_merged` / `human_review` / "
                "`rejected` / `applied`"
            ),
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="1-based 页码")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=CANDIDATE_PAGE_SIZE_MAX,
            description=(
                f"每页条目数（默认 {CANDIDATE_PAGE_SIZE_DEFAULT}，"
                f"上限 {CANDIDATE_PAGE_SIZE_MAX}）"
            ),
        ),
    ] = CANDIDATE_PAGE_SIZE_DEFAULT,
) -> OntologyCandidateListResponse:
    return list_merge_candidates(
        db=db,
        org_id=identity.org_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/active",
    response_model=OntologyActiveResponse,
    operation_id="getActiveOntology",
    summary="读取当前生效的本体 schema（M6 §3.1）",
    description=(
        "读当前租户**生效中**的本体 schema（版本 + 实体 / 关系类型集）。\n\n"
        "**无 active → 409** `SCHEMA_VERSION_NOT_ACTIVE`：**严禁**静默返回一份默认的"
        "内置 schema —— 那会让用户以为自己配过（与 ADR-0002 §3.2 同款纪律）。\n\n"
        "**未确认的 schema 不会出现在这里**：冷启动只产生建议、不写库（§3.1 验收 1），"
        "本端点读到的每一行都经过 `POST /ontology/confirm`。\n\n"
        "**错误语义**：无 active → 409；跨租户 → 403。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **SCHEMA_VERSION_NOT_ACTIVE,
    },
    dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_READ)],
)
async def get_active_ontology(
    identity: CurrentIdentity,
    db: DbSession,
) -> OntologyActiveResponse:
    row = load_active_ontology(db=db, org_id=identity.org_id)
    if row is None:
        raise AppError(
            ErrorCode.SCHEMA_VERSION_NOT_ACTIVE,
            "No active ontology schema for the current tenant",
            detail={
                "org_id": str(identity.org_id),
                "hint": "先调用 POST /ontology/confirm 落一个 active 版本",
            },
        )

    return OntologyActiveResponse(
        version=row.version,
        entity_types=row.entity_types,
        relation_types=row.relation_types,
        status="active",
    )
