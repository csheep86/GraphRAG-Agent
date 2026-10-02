"""M6 **本体增量演进**路由（`specs/m6-ontology-incremental.md` §5.5）。

⚠️ **本批全部是占位骨架，一律 501**（`changes/archive/2026-10-02-P0-m6-finalization` F2，契约先行）：

- **为什么先落骨架再谈实现**：契约由 `scripts/export_openapi.py` **从 app 导出**
  （后端模型是唯一真源）⇒ 要让 7 个端点进 `contracts/openapi.yaml` 并让前端
  `gen:api` 拿到类型，**必须**先有路由。否则 spec §10 ④「契约漂移核验」永远勾不上。
- **什么是"占位"**：路由存在、schema 存在、错误语义声明齐全，**业务逻辑为零**，
  调用即 501 + `detail.blocked_by`。**不**返回 200 空结果 —— 那会让前端以为接口可用
  （业务未实现却报成功，是本项目反复拦的那种"假做"）。
- **实现归 P5-M6 批次**（Sprint 12），不在本批（Non-goals）。

六个端点：冷启动建议 / 确认生效 / 合并 / 拆分 / 改名 / 读 active。
**只有 `/confirm` 会写 `ontology_schemas(status='active')`** —— 其余五个都不改生效状态，
这是 M6 §3.5 验收 12 与 GAP-F2「严禁 LLM 自动修改本体」的落点。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentIdentity, TraceId
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
    summary="本体冷启动建议（M6 §3.1，占位骨架）",
    description=(
        "给一段业务域描述，**建议**一组实体 / 关系类型（LLM 调用）。\n\n"
        "**仅建议、未生效**：本端点**不**写 `ontology_schemas`；要生效必须再调 "
        "`POST /ontology/confirm`（M6 §3.1 验收 1 / §3.5 验收 12）。\n\n"
        "**当前状态**：占位骨架，恒返回 501。PoC 已在应用层跑通"
        "（`app.services.ontology.suggest_ontology_types`，真机产出 12 实体 + 12 关系类型），"
        "**但未接线到本端点**——接线属实现，归 P5-M6。\n\n"
        "**错误语义**：跨租户 → 403 `FORBIDDEN`；未实现 → 501。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **PLACEHOLDER_NOT_IMPLEMENTED},
)
async def cold_start_ontology(
    identity: CurrentIdentity,
    trace_id: TraceId,
    payload: OntologyColdStartRequest,
) -> OntologyColdStartResponse:
    raise _placeholder(
        "POST /api/v1/ontology/cold-start", "suggest_ontology_types（F1 PoC 已跑通）"
    )


@router.post(
    "/confirm",
    response_model=OntologyConfirmResponse,
    operation_id="confirmOntology",
    summary="确认本体 schema 生效（M6 §3.1，占位骨架）",
    description=(
        "把（人工在校正 GUI 上确认过的）类型集写入 `ontology_schemas`，置 "
        "`status='active'`。\n\n"
        "**唯一会写生效状态的端点**：冷启动只建议、merge / split / rename 产新 "
        "`kg_version` 但**不改本体**——GAP-F2「严禁 LLM 自动修改本体」的落点。\n\n"
        "**重复确认 → 409** `SCHEMA_VERSION_NOT_ACTIVE`：同一 `version` 二次确认一律拒绝，"
        "**不**静默复用旧版本（与 `KG_VERSION_NOT_ACTIVE` 同一纪律）。\n\n"
        "**当前状态**：占位骨架，恒返回 501。\n\n"
        "**错误语义**：重复确认 / 版本冲突 → 409；跨租户 → 403；未实现 → 501。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **SCHEMA_VERSION_NOT_ACTIVE,
        **PLACEHOLDER_NOT_IMPLEMENTED,
    },
)
async def confirm_ontology(
    identity: CurrentIdentity,
    payload: OntologyConfirmRequest,
) -> OntologyConfirmResponse:
    raise _placeholder(
        "POST /api/v1/ontology/confirm", "写 ontology_schemas(status='active')"
    )


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
    summary="读取当前生效的本体 schema（M6 §3.1，占位骨架）",
    description=(
        "读当前租户**生效中**的本体 schema（版本 + 实体 / 关系类型集）。\n\n"
        "**无 active → 409** `SCHEMA_VERSION_NOT_ACTIVE`：**严禁**静默返回一份默认的"
        "内置 schema —— 那会让用户以为自己配过（与 ADR-0002 §3.2 同款纪律）。\n\n"
        "**当前状态**：占位骨架，恒返回 501。读取侧应用层**已具备**"
        "（`app.services.ontology.load_active_ontology`），接线归 P5-M6。\n\n"
        "**错误语义**：无 active → 409；跨租户 → 403；未实现 → 501。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **SCHEMA_VERSION_NOT_ACTIVE,
        **PLACEHOLDER_NOT_IMPLEMENTED,
    },
)
async def get_active_ontology(
    identity: CurrentIdentity,
) -> OntologyActiveResponse:
    raise _placeholder(
        "GET /api/v1/ontology/active", "load_active_ontology（应用层已具备）"
    )
