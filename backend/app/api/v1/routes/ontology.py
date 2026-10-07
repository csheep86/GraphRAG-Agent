"""M6 **本体增量演进**路由（`specs/m6-ontology-incremental.md` §5.5）。

⚠️ **P5-C（2026-10-07）进度**：`cold-start` / `confirm` / `active` 三个端点**已接线**
（`status='active'` 的唯一写入入口是 `confirm`）；
`merge` / `split` / `rename` **仍是 501 占位**——它们依赖尚不存在的增量重算。

剩下四个占位端点的语义不变（契约先行批次 F2）：

- **为什么占位不返回 200**：返回 200 空结果会让前端以为接口可用 —— 业务未实现
  却报成功，是本项目反复拦的那种"假做"；
- ``merge`` / ``split`` / ``rename`` 都要产新 ``kg_version``、都要依赖**增量重算**，
  而增量重算本身还不存在 ⇒ 三个端点整体留给后续批次。

**RBAC**：已实现的三个端点挂 `require_permission(RESOURCE_ONTOLOGY, read/write)`
（2026-10-07：这三个从"没有数据可动"变成"真会写库"，不挂等于给租户内任意主体
开一个写入口）；三个占位端点归实现批次随同批补登记。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    PLACEHOLDER_NOT_IMPLEMENTED,
    SCHEMA_VERSION_NOT_ACTIVE,
    TENANT_ERROR_RESPONSES,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.ontology import (
    OntologyActionResponse,
    OntologyActiveResponse,
    OntologyColdStartRequest,
    OntologyColdStartResponse,
    OntologyConfirmRequest,
    OntologyConfirmResponse,
    OntologyMergeRequest,
    OntologyRenameRequest,
    OntologySplitRequest,
)
from app.services.ontology import (
    OntologySuggestError,
    OntologyVersionConflictError,
    confirm_ontology_schema,
    load_active_ontology,
    suggest_ontology_types,
)
from app.services.rbac.deps import require_permission
from app.services.rbac.policy import ACTION_READ, ACTION_WRITE, RESOURCE_ONTOLOGY

router = APIRouter(prefix="/ontology", tags=["ontology"])

#: 501 的统一出处（**唯一消费点**在此，7 个端点共用）
_BLOCKED_BY = "实现归 P5-M6 批次（Sprint 12）；本批只落契约与占位骨架"
_SPEC = "specs/m6-ontology-incremental.md §5.5"


def _placeholder(endpoint: str, real_entry: str) -> AppError:
    """构造占位端点的 501。

    **为什么复用 `NOT_IMPLEMENTED` 而不新增错误码**：HTTP 501 本义即 Not Implemented，
    新增一个只用 7 次、实现时必删的错误码，会让 `ErrorCode` 枚举背上临时债。
    代价是与既有口径（501 = 基础设施不可用）重叠 ⇒ 靠 `detail.blocked_by` 区分，
    并已登记为定稿增补项（F3 裁决，见 `responses.PLACEHOLDER_NOT_IMPLEMENTED`）。
    """
    return AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Endpoint is a placeholder: business logic not implemented yet",
        detail={
            "blocked_by": _BLOCKED_BY,
            "endpoint": endpoint,
            "real_entry": real_entry,
            "spec": _SPEC,
        },
    )


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
    summary="合并两个实体（M6 §3.2 三动作之一，占位骨架）",
    description=(
        "把 `right_entity_id` 并入 `left_entity_id`，产出**新的** `kg_version`。\n\n"
        "**跨 org → 403** `FORBIDDEN`：两个实体必须同属当前租户，"
        "跨租户合并是数据污染，**不**降级为「只合并同租户的那个」。\n\n"
        "**当前状态**：占位骨架，恒返回 501。\n\n"
        "**错误语义**：跨租户 → 403；未实现 → 501。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **PLACEHOLDER_NOT_IMPLEMENTED},
)
async def merge_ontology_entities(
    identity: CurrentIdentity,
    payload: OntologyMergeRequest,
) -> OntologyActionResponse:
    raise _placeholder("POST /api/v1/ontology/merge", "图谱实体合并 + 增量重算")


@router.post(
    "/split",
    response_model=OntologyActionResponse,
    operation_id="splitOntologyEntity",
    summary="拆分一个实体（M6 §3.2 三动作之一，占位骨架）",
    description=(
        "把一个实体拆成多个新实体（`new_entities[]` **至少 2 个**——只拆出 1 个等于改名，"
        "应走 `POST /ontology/rename`），产出**新的** `kg_version`。\n\n"
        "⚠️ `new_entities[]` 每项目前**只有 `canonical_name`**：spec §5.5 写的是 "
        "`{canonical_name, ...}`，省略号部分本批**不自行展开**（功能预留原则），"
        "待 M6 实现批次按真实需求补字段并同步契约。\n\n"
        "**当前状态**：占位骨架，恒返回 501。\n\n"
        "**错误语义**：跨租户 → 403；未实现 → 501。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **PLACEHOLDER_NOT_IMPLEMENTED},
)
async def split_ontology_entity(
    identity: CurrentIdentity,
    payload: OntologySplitRequest,
) -> OntologyActionResponse:
    raise _placeholder("POST /api/v1/ontology/split", "图谱实体拆分 + 增量重算")


@router.post(
    "/rename",
    response_model=OntologyActionResponse,
    operation_id="renameOntologyEntity",
    summary="改实体规范名（M6 §3.2 三动作之一，占位骨架）",
    description=(
        "改实体的规范名，产出**新的** `kg_version`。\n\n"
        "**为什么改名也算本体动作**：规范名进入抽取词表与消解键，改名等价于"
        "重跑一段图谱——所以它**必须**产新版本，而不是原地 UPDATE。\n\n"
        "**当前状态**：占位骨架，恒返回 501。\n\n"
        "**错误语义**：跨租户 → 403；未实现 → 501。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **PLACEHOLDER_NOT_IMPLEMENTED},
)
async def rename_ontology_entity(
    identity: CurrentIdentity,
    payload: OntologyRenameRequest,
) -> OntologyActionResponse:
    raise _placeholder("POST /api/v1/ontology/rename", "图谱实体改名 + 增量重算")


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
