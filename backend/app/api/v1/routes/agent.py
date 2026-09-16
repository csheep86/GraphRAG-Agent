"""M3 图谱问答路由（契约已定稿，实现留待 Sprint 3）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentIdentity, TraceId
from app.api.v1.responses import (
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
    VALIDATION_ERROR,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.agent import AgentQueryRequest, AgentQueryResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/query",
    response_model=AgentQueryResponse,
    operation_id="queryAgent",
    summary="图谱问答（契约已定稿，Sprint 3 实现）",
    description=(
        "单轮问答 + 可溯源引用。每个事实句必须能回溯到 `citations[]`，"
        "引用覆盖率不足时**必须拒答**（`refused = true`），严禁编造引用（M3 验收 3）。\n\n"
        "`refused = true` 时 `answer` 恒为 `无法回答`。\n\n"
        "**版本一致性（ADR-0002 §3.2）**：显式传入非 active 的 `kg_version` 时一律返回 "
        "**409** `KG_VERSION_NOT_ACTIVE`，**严禁静默降级**。\n\n"
        "**当前实现状态**：返回 **501** `NOT_IMPLEMENTED`（M3 检索链路为 Sprint 3 范围）。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **VALIDATION_ERROR,
        **KG_VERSION_NOT_ACTIVE,
        **NOT_IMPLEMENTED,
    },
)
async def query_agent(
    payload: AgentQueryRequest,
    identity: CurrentIdentity,
    trace_id: TraceId,
) -> AgentQueryResponse:
    raise AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Agent query is not implemented in Sprint 1",
        detail={
            "scope": payload.scope,
            "planned_sprint": "3",
            "blocked_by": "M3 意图路由 + 引用生成链路",
        },
    )
