"""`GET /api/v1/health`——唯一豁免租户上下文的接口。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import TraceId
from app.core.config import get_settings
from app.db.session import check_database
from app.schemas.health import HealthCheckStatus, HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="健康检查（豁免租户上下文）",
    description=(
        "不要求认证、不返回任何业务数据。\n\n"
        "依赖异常时仍返回 **200**，仅把 `status` 降级为 `degraded`，"
        "避免负载均衡因单实例依赖抖动直接摘除全部流量。"
    ),
)
async def get_health(trace_id: TraceId) -> HealthResponse:
    settings = get_settings()
    database_up = check_database()
    return HealthResponse(
        status="ok" if database_up else "degraded",
        version=settings.app_version,
        checks=HealthCheckStatus(database="up" if database_up else "down"),
        time=datetime.now(UTC),
        trace_id=trace_id,
    )
