"""M6 §3.4 **成本仪表盘**契约（`GET /api/v1/cost/dashboard`）。

**本批（`changes/archive/2026-10-02-P0-m6-finalization` F2）只落契约与 501 占位骨架，不含业务逻辑**
（Non-goals）。成本口径的**计算实现**归 P5-M6 批次。

**为什么这个端点必须存在**：M6 §8 把它定位为「把『是否可达』从主观判断变成**实测可证**」
的载体（收敛 TBD-7）——没有它，Sprint 12 承诺的「增量 / 全量成本比 < 1.00」只是口头承诺。
所以**先把契约钉住**，实现随后。

⚠️ **spec §5.5 未定义 `by_date[]` 每项的字段**（只写了 `by_date: [...]`）。
本批按**最小可用**给出 `date` + `token_usage_total` + `single_doc_cost`，
**不**替 spec 发明 `cost_ratio` 等字段——`cost_ratio` 是**区间级**指标（增量 vs 全量），
按天再算一遍会得到意义不明的数字。⇒ 登记为定稿增补项，F3 裁决。
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class CostByDateItem(BaseModel):
    """成本仪表盘的**按天**明细。

    ⚠️ 字段集为 spec §5.5 未定义处的**最小可用推断**（见本模块 docstring）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2026-10-02",
                "token_usage_total": 128_450,
                "single_doc_cost": 0.42,
            }
        }
    )

    #: 字段名 `date` 与 `datetime.date` 同名 ⇒ 用 `dt.date` 标注，
    #: 否则 Pydantic 报「field name clashing with a type annotation」
    date: dt.date = Field(description="统计日（ISO 日期）")
    token_usage_total: int = Field(ge=0, description="当日 token 用量合计")
    single_doc_cost: float = Field(
        ge=0.0,
        description="当日单文档平均成本（口径与响应顶层 `single_doc_cost` 一致）",
    )


class CostDashboardResponse(BaseModel):
    """`GET /api/v1/cost/dashboard` 响应：成本总览（M6 §3.4）。

    **字段逐字照 spec §5.5**：`token_usage_total` / `single_doc_cost` / `cost_ratio` /
    `by_date`。§5.5 未列 `trace_id`，本批按 spec 执行（差异见
    :mod:`app.schemas.ontology` 的模块 docstring）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "token_usage_total": 1_284_500,
                "single_doc_cost": 0.42,
                "cost_ratio": 0.31,
                "by_date": [
                    {
                        "date": "2026-10-02",
                        "token_usage_total": 128450,
                        "single_doc_cost": 0.42,
                    }
                ],
            }
        }
    )

    token_usage_total: int = Field(ge=0, description="区间内 token 用量合计")
    single_doc_cost: float = Field(
        ge=0.0, description="单文档平均成本（全量抽取口径；与增量对比的分母）"
    )
    cost_ratio: float = Field(
        ge=0.0,
        description=(
            "**增量 / 全量成本比**（M6 C3 准入线：显著 < 1.00）。"
            "超阈值**仅日志告警，不阻断**请求（告警阈值规范见 spec §6；"
            "**该配置尚未落 `config.py`**，实现批次须先有消费者再提交）"
        ),
    )
    by_date: list[CostByDateItem] = Field(description="按天明细（供仪表盘画趋势）")
