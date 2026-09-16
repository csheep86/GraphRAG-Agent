"""`GET /api/v1/health` 契约模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthCheckStatus(BaseModel):
    database: Literal["up", "down"] = Field(
        description="数据库连通性。SQLite 兜底期间仅探测 `SELECT 1`，不代表 RLS 已生效"
    )


class HealthResponse(BaseModel):
    """健康检查响应。

    **本接口豁免租户上下文**：不要求认证、不返回任何业务数据。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "1.0.0",
                "checks": {"database": "up"},
                "time": "2026-09-16T08:30:00Z",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    status: Literal["ok", "degraded"] = Field(
        description="`ok` = 全部依赖正常；`degraded` = 依赖异常但进程可服务（HTTP 仍为 200）"
    )
    version: str = Field(description="契约版本，与 openapi.yaml 的 info.version 一致")
    checks: HealthCheckStatus
    time: datetime = Field(description="服务端 UTC 时间")
    trace_id: str
