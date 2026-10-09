"""M6 §3.4 **成本仪表盘**路由（`specs/m6-ontology-incremental.md` §5.5）。

**P6-V（2026-10-09）：不再是占位**。数据源是本批新建的 ``cost_metrics`` 表
（M6 §4.3，带 RLS 的租户表），写入侧见 :mod:`app.services.cost_metrics`——
M3 问答每次真实 LLM 调用会累加到当日那一行上去。

⚠️ **X-5：装饰器里的 ``summary`` / ``description`` 仍是占位期原文**
（写着"占位骨架，恒返回 501"）。**为什么不顺手改**：

- 它们是 **Contract** 的一部分（`contracts/openapi.yaml` 由本仓库 export 生成，
  前端 `npm run gen:api` 再把它变成 `frontend/src/types/api.d.ts`）；
- CI 有一条"前端生成物零 diff"的闸门，而按角色隔离 `frontend/` 只能由前端开发改；
- ⇒ 本批**严守与非改契约**，把描述文本更新登记到下一批（含 `export_openapi.py` +
  `npm run gen:api` 双生成物一起提交），**不偷偷独立改一半**。

实现侧的三条口径（都在 :mod:`app.services.cost_metrics` 里，路由只做组装）：

1. **默认区间**：``date_from`` / ``date_to`` 都缺省 ⇒ 服务端按 **UTC** 取
   "今天往前 29 天"（共 30 天），不依赖前端时区；
2. **空区间返回全 0 + 空 by_date** 并打 warning（X-4：契约没有为"无数据"准备语义，
   本批不改契约）——这与占位期的 501 **不是**一回事：那时**根本没有落点**；
3. **超阈值只写日志**（spec §6），不改响应、不改契约。

**错误语义**：跨租户 → 403 `FORBIDDEN`（依赖链保证）；未实现 → 501
（原声明保留，占位 infra 级失败路径使用，**不再是日常路径**）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import PLACEHOLDER_NOT_IMPLEMENTED, TENANT_ERROR_RESPONSES
from app.schemas.cost import CostByDateItem, CostDashboardResponse
from app.services.cost_metrics import build_dashboard

router = APIRouter(prefix="/cost", tags=["cost"])

#: 默认窗口长度（天，含今天）——理由见模块 docstring 第 1 条
_DEFAULT_WINDOW_DAYS = 30


def _utc_today() -> date:
    """今天的 UTC 自然日（与 :func:`cost_metrics.utc_day` 同口径）。"""
    return datetime.now(UTC).date()


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
    session: DbSession,
    trace_id: TraceId,
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
    """按日期区间返回成本总览（真实组装，不再 501）。

    **X-5（2026-10-09）**：上面的 ``summary`` / ``description`` 与原占位期逐字相同
    ——它们是契约文本，改了就要连 ``contracts/openapi.yaml`` 与前端 TS 生成物一起
    提，属下一批（详见模块 docstring）。**实现已经是真的**，别被那句"占位骨架"
    误导，也别以此为由宣称"契约已 update"。
    """
    today = _utc_today()
    start = date_from or (today - timedelta(days=_DEFAULT_WINDOW_DAYS - 1))
    end = date_to or today
    if start > end:  # 前端传反了 ⇒ 换成有序区间，而不是回一个空盘让人猜
        start, end = end, start

    payload = build_dashboard(
        db=session,
        org_id=identity.org_id,
        date_from=start,
        date_to=end,
        trace_id=trace_id,
    )
    return CostDashboardResponse(
        token_usage_total=payload["token_usage_total"],
        single_doc_cost=payload["single_doc_cost"],
        cost_ratio=payload["cost_ratio"],
        by_date=[CostByDateItem(**row) for row in payload["by_date"]],
    )
