"""M6 §3.4 **成本仪表盘**路由（`specs/m6-ontology-incremental.md` §5.5）。

⚠️ **本批是占位骨架，一律 501**（`changes/P0-m6-finalization` F2，契约先行）。

**为什么它跟本体端点同批进契约**：M6 §8 把它定位为「把『是否可达』从主观判断变成
**实测可证**」的载体（收敛 TBD-7）。Sprint 12 承诺的「增量 / 全量成本比 < 1.00」
**必须先有契约**才能被前端消费、被评测脚本核对——所以契约先行，实现归 P5-M6。

**占位，不返回 200 空盘**：空盘（全 0）会被前端画成一张"成本为 0"的图，
那正是本项目要拦的"假做"（业务没实现却报成功）。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentIdentity
from app.api.v1.responses import PLACEHOLDER_NOT_IMPLEMENTED, TENANT_ERROR_RESPONSES
from app.core.errors import AppError, ErrorCode
from app.schemas.cost import CostDashboardResponse

router = APIRouter(prefix="/cost", tags=["cost"])

_BLOCKED_BY = "实现归 P5-M6 批次（Sprint 12）；本批只落契约与占位骨架"
_SPEC = "specs/m6-ontology-incremental.md §5.5 / §3.4"


@router.get(
    "/dashboard",
    response_model=CostDashboardResponse,
    operation_id="getCostDashboard",
    summary="成本仪表盘（M6 §3.4，占位骨架）",
    description=(
        "按日期区间给出**成本总览**：token 用量、单文档成本、**增量 / 全量成本比**，"
        "以及按天明细。\n\n"
        "**`cost_ratio` 是准入线的载体**：M6 C3 要求「增量 / 全量成本比显著 < 1.00」，"
        "超过告警阈值只**日志告警，不阻断**请求（阈值规范见 spec §6，**尚未落 "
        "`config.py`**）。\n\n"
        "**当前状态**：占位骨架，恒返回 501。成本打点侧 M2 §3 验收 7 的 `token_usage` "
        "**已具备**，聚合与口径实现归 P5-M6。\n\n"
        "**错误语义**：跨租户 → 403 `FORBIDDEN`；未实现 → 501。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **PLACEHOLDER_NOT_IMPLEMENTED},
)
async def get_cost_dashboard(
    identity: CurrentIdentity,
    date_from: Annotated[
        date | None,
        Query(
            alias="date_from",
            description="起始日（ISO，含）；缺省由实现侧定义默认区间（本批未定）",
        ),
    ] = None,
    date_to: Annotated[
        date | None,
        Query(
            alias="date_to",
            description="结束日（ISO，含）；缺省由实现侧定义默认区间（本批未定）",
        ),
    ] = None,
) -> CostDashboardResponse:
    raise AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Endpoint is a placeholder: business logic not implemented yet",
        detail={
            "blocked_by": _BLOCKED_BY,
            "endpoint": "GET /api/v1/cost/dashboard",
            "real_entry": "token_usage 聚合 + 增量 / 全量成本比",
            "spec": _SPEC,
        },
    )
