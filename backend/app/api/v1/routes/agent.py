"""M3 图谱问答路由（阶段九 9.3：由 501 占位替换为真实调用链路）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    KG_TENANT_LEAK,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
    VALIDATION_ERROR,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.agent import AgentQueryRequest, AgentQueryResponse
from app.services.agents import (
    AgentService,
    AgentTenantLeakError,
    AgentUnavailableError,
)
from app.services.graphs import GraphService, GraphUnavailableError

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/query",
    response_model=AgentQueryResponse,
    operation_id="queryAgent",
    summary="图谱问答",
    description=(
        "单轮问答 + 可溯源引用。每个事实句必须能回溯到 `citations[]`，"
        "引用覆盖率不足时**必须拒答**（`refused = true`），严禁编造引用（M3 验收 3）。\n\n"
        "`refused = true` 时 `answer` 恒为 `无法回答`。\n\n"
        "**版本一致性（ADR-0002 §3.2）**：显式传入非 active 的 `kg_version` 时一律返回 "
        "**409** `KG_VERSION_NOT_ACTIVE`，**严禁静默降级**。\n\n"
        "**实现状态**：已实装——由 `AgentService.query`（`app/services/agents.py`）执行"
        "「取 active 版本 → 拉取相关子图 → 加载 `kg_qa` Prompt → LLM 调用与解析」单轮链路，"
        "返回 `AgentQueryResponse`。\n\n"
        "**501 `NOT_IMPLEMENTED` 的真实语义**：LLM 未配置（`LLM_API_KEY` 缺失）/ "
        "LangChain 装配失败 / Neo4j 不可用时返回 501，表示**基础设施不可用**，"
        "**不**表示「接口未实现」。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **VALIDATION_ERROR,
        **KG_VERSION_NOT_ACTIVE,
        **KG_TENANT_LEAK,
        **NOT_IMPLEMENTED,
    },
)
async def query_agent(
    payload: AgentQueryRequest,
    identity: CurrentIdentity,
    trace_id: TraceId,
    db: DbSession,
) -> AgentQueryResponse:
    # 1) 显式指定 kg_version 时校验 active（ADR-0002 §3.2，严禁静默降级）
    if payload.kg_version is not None:
        await _assert_active_kg_version(requested=payload.kg_version, trace_id=trace_id)

    # 2) 执行问答（org_id 只来自认证态，严禁取自 body / query —— ADR-0003 §3.3）
    try:
        return await AgentService.instance().query(
            request=payload,
            org_id=identity.org_id,
            trace_id=trace_id,
            db=db,
        )
    except AgentTenantLeakError as exc:
        # 必须先于 AgentUnavailableError（它是其子类）——数据质量事故 ≠ 基础设施故障
        raise AppError(
            ErrorCode.KG_TENANT_LEAK,
            detail={
                "org_id": str(identity.org_id),
                "blocked_by": "fail-closed 跨租户子图校验（ADR-0003 §4）",
                "reason": str(exc),
                "trace_id": trace_id,
            },
        ) from exc
    except AgentUnavailableError as exc:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "Agent pipeline is unavailable",
            detail={
                "scope": payload.scope,
                "blocked_by": "LLM（DeepSeek）或 Neo4j 未就绪",
                "reason": str(exc),
            },
        ) from exc


async def _assert_active_kg_version(*, requested: str, trace_id: str) -> None:
    """请求显式指定版本时，非 ``active`` 一律 409；Neo4j 不可用则 501。

    **必须区分**「版本不合法（409）」与「图谱不可用（501）」——
    前者是调用方的错，后者是本服务的基础设施故障，不可混为一谈。
    """
    try:
        status = GraphService.instance().fetch_kg_version_status(requested)
    except GraphUnavailableError as exc:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "Graph store is unavailable",
            detail={
                "kg_version": requested,
                "blocked_by": "Neo4j 不可用，无法校验 kg_version 状态",
                "reason": str(exc),
            },
        ) from exc

    if status != "active":
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={
                "kg_version": requested,
                "status": status or "unknown",
                "hint": "仅 status='active' 的版本可被检索，严禁静默降级",
                "trace_id": trace_id,
            },
        )
