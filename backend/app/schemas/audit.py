"""审计留痕的对外契约模型（Sprint 8.1 批次 A，M5 §4.4 / §3 验收 7）。

契约事实上的真源是**本文件的 Pydantic 模型**（`backend/CODEBUDDY.md` §3 铁律）：
先改这里 → `uv run python scripts/export_openapi.py` 重导出 → `npm run gen:api`。

字段来自 `specs/m5-permission-audit.md` §4.4（`audit_log` 字段表，权威），
**不进契约的字段：无**（本表没有 ADR-0004 预留字段，全部为既有实现消费）。

**本批次边界（明确不做，见 proposal「M5 §3 边界确认」表）**：
- ❌ RBAC 三粒度过滤 —— 仅按 `org_id` 租户隔离（S11）；
- ❌ 敏感字段脱敏器 —— 以「`detail` 不写原文」规避（S11）；
- ❌ `alert` 表、限流 `rate_limit.triggered` —— 批次 B；
- ❌ RLS —— 数据库层租户隔离未启用，应用层 `org_id` 过滤兜底（ADR-0003）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: 审计状态（M5 §4.4）：`failure` 覆盖 4xx 与 5xx，与 HTTP 状态码族无关
AuditStatus = Literal["success", "failure"]


class AuditLogItem(BaseModel):
    """一条审计记录（`audit_log` 行的契约投影）。

    `detail` 只含**结构化字段**（`status_code` / `method` / `path` / 路径参数），
    **不含**响应体原文——本批次不引入脱敏器，故以「不写原文」守住不新增泄露面
    （决策 **A5**）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "6d1e3f9a-4b2c-4a8b-8c2d-5e7f0a1b3c5d",
                "ts": "2026-09-24T10:16:12Z",
                "action": "document.upload",
                "actor_id": "00000000-0000-4000-8000-000000000001",
                "actor_ip": "127.0.0.1",
                "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                "resource": "POST /api/v1/documents/upload",
                "status": "success",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
                "detail": {"status_code": 200, "method": "POST"},
            }
        }
    )

    id: UUID = Field(description="审计记录 id（`audit_log.id`）")
    ts: datetime = Field(description="落库时间（UTC）")
    action: str = Field(
        description=(
            "操作类型。已登记路由取业务名（`document.upload` / `agent.query` / "
            "`affiliation.review` …）；未登记路由回落 `http.<method>.<path>`"
            "（决策 A2：宁可 action 丑，不可无记录）"
        )
    )
    actor_id: UUID | None = Field(
        default=None, description="操作者 id（系统触发时为 `null`，不编造）"
    )
    actor_ip: str | None = Field(default=None, description="客户端 IP")
    doc_id: UUID | None = Field(
        default=None, description="关联文档 id；与文档无关的请求为 `null`"
    )
    resource: str = Field(
        description="资源标识（`<METHOD> <实际请求路径>`，不含 query string）"
    )
    status: AuditStatus = Field(description="`success` / `failure`")
    trace_id: str = Field(description="与响应头 X-Trace-Id 一致的全链路 trace_id")
    detail: dict[str, Any] | None = Field(
        default=None, description="结构化明细；**不含**响应体原文"
    )


class AuditLogListResponse(BaseModel):
    """`GET /api/v1/audit` 响应（M5 §3 验收 7：按租户隔离 + `ts DESC` + 页大小 50）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 1,
                "items": [
                    {
                        "id": "6d1e3f9a-4b2c-4a8b-8c2d-5e7f0a1b3c5d",
                        "ts": "2026-09-24T10:16:12Z",
                        "action": "document.upload",
                        "actor_id": "00000000-0000-4000-8000-000000000001",
                        "actor_ip": "127.0.0.1",
                        "doc_id": None,
                        "resource": "POST /api/v1/documents/upload",
                        "status": "success",
                        "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
                        "detail": {"status_code": 200},
                    }
                ],
                "page": 1,
                "page_size": 50,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    total: int = Field(ge=0, description="当前租户下满足过滤条件的记录总数")
    items: list[AuditLogItem] = Field(description="当前页结果（按 `ts DESC`）")
    page: int = Field(ge=1, description="当前页码（1-based）")
    page_size: int = Field(ge=1, description="每页条目数（请求参数回显）")
    trace_id: str = Field(description="本次查询请求的 trace_id")


class AuditTraceResponse(BaseModel):
    """`GET /api/v1/audit/trace/{trace_id}` 响应。

    **不支持分页**：同一 trace 的记录条数天然有界（一次 HTTP 请求一条），
    引入无消费者的 `page` / `page_size` 属范围蔓延。
    查不到时返回 `items = []`（**空态不是错误**），跨租户亦为空集。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
                "total": 1,
                "items": [
                    {
                        "id": "6d1e3f9a-4b2c-4a8b-8c2d-5e7f0a1b3c5d",
                        "ts": "2026-09-24T10:16:12Z",
                        "action": "agent.query",
                        "actor_id": "00000000-0000-4000-8000-000000000001",
                        "actor_ip": "127.0.0.1",
                        "doc_id": None,
                        "resource": "POST /api/v1/agent/query",
                        "status": "success",
                        "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
                        "detail": {"status_code": 200},
                    }
                ],
            }
        }
    )

    trace_id: str = Field(description="被查询的 trace_id（请求参数回显）")
    total: int = Field(ge=0, description="该 trace 下、当前租户可见的记录条数")
    items: list[AuditLogItem] = Field(description="按 `ts ASC` 排列的记录列表")


__all__ = [
    "AuditLogItem",
    "AuditLogListResponse",
    "AuditStatus",
    "AuditTraceResponse",
]
