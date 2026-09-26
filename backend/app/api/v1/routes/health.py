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
        "避免负载均衡因单实例依赖抖动直接摘除全部流量。\n\n"
        "同时**豁免限流**（名单见 `core/limiter.py::EXEMPT_ROUTE_NAMES`）："
        "探针可达 1 次/秒，贴着默认限（60/min）跑，被 429 会直接把实例摘除"
        "（M5 §3 验收 5 的限流口径面向业务接口）。"
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
