"""M5 审计留痕路由（Sprint 8.1 批次 A）：只读查询，按租户隔离。

对应关系：`specs/m5-permission-audit.md` §3 验收 7（`GET /audit` 按 actor / org 隔离、
默认 `ts DESC`、页大小 50）+ plan §7.2 步骤 6（演示路径全程可回看）。

**本批次不做的**（proposal「M5 §3 边界确认」表，显式登记而非静默省略）：
- ❌ RBAC 三粒度：仅按租户隔离，**不**按角色过滤（属 S11）；
- ❌ 敏感字段脱敏器：`detail` 从不写原文，故无需脱敏输出（属 S11）；
- ❌ RLS：数据库层隔离未启用，`org_id` 过滤由应用层保证（ADR-0003）。

写入侧**不在**本文件：唯一写入点是 `app/core/middleware.py::AuditMiddleware`
（决策 **A1**：中间件全量写，不靠路由埋点）。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import TENANT_ERROR_RESPONSES, VALIDATION_ERROR
from app.schemas.audit import AuditLogListResponse, AuditTraceResponse
from app.services.audit import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    list_audit_logs,
    list_audit_logs_by_trace,
)

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "",
    response_model=AuditLogListResponse,
    operation_id="listAuditLogs",
    summary="查询当前租户的审计留痕（M5 §3 验收 7）",
    description=(
        "返回当前租户（`X-Org-Id` / Bearer token 解析出的 `org_id`）可见的审计记录，"
        "**跨租户记录永不出现在结果里**（ADR-0003；RLS 未启用前由应用层过滤兜底）。\n\n"
        "**排序与分页**：默认 `ts DESC`（最新在前），`page` 1-based，`page_size` 默认 **50**、"
        "上限 100（M5 §3 验收 7 原文口径）。\n\n"
        "**过滤**：`action`（精确匹配，取值见各记录的 `action` 列）/ `status`"
        "（`success` / `failure`；非法值 **400** `VALIDATION_ERROR`，**不**静默当全量返回）。\n\n"
        "**写入语义**：每条 **HTTP 请求**一条（成功 = `< 400`，失败 = `>= 400`），"
        "由审计中间件统一写入 `audit_log`；`detail` 只含结构化字段"
        "（`status_code` / `method` / `path`），**不含响应体原文**（本批次无脱敏器）。\n\n"
        "**自举说明**：本接口自身也在 `/api/v1/*` 内，因此每次查询都会写一条"
        "`action=audit.list` 的记录——该条**不会出现在本次响应里**（它在本请求之后才写入）。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR},
)
async def list_audit_logs_endpoint(
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
    action: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
            description="按操作类型精确过滤（如 `document.upload` / `agent.query`）",
        ),
    ] = None,
    status: Annotated[
        str | None,
        Query(description="按结果过滤：`success` / `failure`"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="1-based 页码")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=PAGE_SIZE_MAX,
            description=f"每页条目数（默认 {PAGE_SIZE_DEFAULT}，上限 {PAGE_SIZE_MAX}）",
        ),
    ] = PAGE_SIZE_DEFAULT,
) -> AuditLogListResponse:
    return list_audit_logs(
        session=session,
        identity=identity,
        action=action,
        status=status,
        page=page,
        page_size=page_size,
        trace_id=trace_id,
    )


@router.get(
    "/trace/{trace_id}",
    response_model=AuditTraceResponse,
    operation_id="listAuditLogsByTrace",
    summary="按 trace_id 回看一次调用链的审计记录（M5 §3 验收 6）",
    description=(
        "返回该 `trace_id` 下**当前租户**可见的全部审计记录，按 `ts ASC` 排列，"
        "用于把一个 HTTP 请求的来龙去脉串起来回看（plan §7.2 步骤 6）。\n\n"
        "**不支持分页**：同一 trace 的记录条数天然有界（一次请求一条），"
        "不引入无消费者的分页参数。\n\n"
        "**空集语义**：查不到 / 该 trace 属于别的租户 → `items = []` 且 `total = 0`，"
        "**不是错误**（既不泄露资源存在性，也不假装查到了数据）。\n\n"
        "**口径提示（proposal 风险 7）**：后端异步任务另有自己的 `trace_id`"
        "（`app/tasks/manager.py` 在任务侧生成），因此**不要**指望「同一个 trace_id 下"
        "有全部 7 条」——本接口对应的是**单次 HTTP 请求**的留痕。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR},
)
async def list_audit_logs_by_trace_endpoint(
    trace_id: UUID,
    identity: CurrentIdentity,
    session: DbSession,
) -> AuditTraceResponse:
    # ``trace_id`` 是**被查询**的目标 trace（也是响应体的回显字段）；本次请求自身的
    # trace_id 不在响应体里 —— 契约没有这个字段，故不引入无消费者的依赖。
    return list_audit_logs_by_trace(
        session=session,
        identity=identity,
        trace_id=str(trace_id),
    )
