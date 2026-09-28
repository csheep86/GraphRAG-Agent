"""考勤域**异常归因**的契约模型（Sprint 9.5 批次 C4 / 前端 E3 消费）。

**与 C2 服务层的关系**：本模块**不重新定义**归因语义，只是把
:class:`app.services.rules.attribution.AttributionResult` 原样投影到 HTTP：
原因项直接复用 M4 的 ``AffiliationCauseItem``（同一份结构，不复制第二份——
复制就会出现「两处 causes，改一处漏一处」）。

**置信度不出 LLM**：``confidence`` 是 ``Σ命中权重 / Σ全部权重`` 的确定性结果，
每个 ``weight`` 都是常量、命中与否由图谱证据说话。前端展示的是这个算式的结果，
不是模型的自我感觉。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.affiliation import AffiliationCauseItem

__all__ = [
    "AnomalyCaseItem",
    "AnomalyExplainResponse",
    "AnomalyListResponse",
]


class AnomalyCaseItem(BaseModel):
    """一条待归因的异常（谁 / 哪天 / 什么状态）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2026-10-16",
                "employee_id": "E001",
                "employee_name": "张伟",
                "status": "absent",
            }
        }
    )

    employee_id: str = Field(description="员工工号（如 `E001`）")
    employee_name: str = Field(description="员工姓名")
    date: str = Field(description="异常日（ISO 日期）")
    status: str = Field(
        description="考勤状态：`absent`（缺勤）/ `missing_check_in`（缺卡）"
    )


class AnomalyListResponse(BaseModel):
    """``GET /attendance/anomalies`` 响应：当前图谱里有哪些缺卡 / 缺勤待归因。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "kg_version": "attendance-demo-v1",
                "total": 12,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    kg_version: str = Field(description="扫描所基于的图谱版本（只读 active 版本）")
    items: list[AnomalyCaseItem] = Field(description="异常清单（按工号 / 日期排序）")
    total: int = Field(description="异常条数（与 `len(items)` 一致）")
    trace_id: str = Field(description="本次请求的 trace_id")


class AnomalyExplainResponse(BaseModel):
    """``GET /attendance/anomalies/explain`` 响应：一条异常的归因结论。

    **未命中的原因照样返回**（``matched=false``）：演示时要能说清「哪一项没对上」，
    只给命中项会让用户误以为证据齐备。

    ``policy_refs`` 是结论文案（如「自动补卡」）的**制度出处**——话术不是硬编码的，
    取不到时该数组为空，此时**不得**声称结论有制度依据。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "系统自动补卡",
                "anomaly_type": "absent",
                "causes": [
                    {
                        "code": "trip_approved",
                        "evidence": ["BUSINESS_TRIP:BT-2026-0017"],
                        "matched": True,
                        "reason": "出差审批覆盖当日（武汉 10-16~10-18）",
                        "weight": 0.35,
                    }
                ],
                "conclusion": "外勤出勤成立",
                "confidence": 1,
                "date": "2026-10-16",
                "employee_id": "E001",
                "employee_name": "张伟",
                "kg_version": "attendance-demo-v1",
                "policy_refs": ["document:doc:fieldwork-attendance-rules:L12"],
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    kg_version: str = Field(description="归因所基于的图谱版本（只读 active 版本）")
    employee_id: str = Field(description="员工工号")
    employee_name: str = Field(description="员工姓名")
    date: str = Field(description="被归因的异常日（ISO 日期）")
    anomaly_type: str = Field(description="异常类型（`absent` / `missing_check_in`）")
    causes: list[AffiliationCauseItem] = Field(
        description="原因排序（含未命中项）；置信度 = Σ命中权重 / Σ全部权重"
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="确定性加权置信度（**禁止 LLM 生成**）；0 表示证据零命中",
    )
    conclusion: str = Field(
        description="结论：`外勤出勤成立` / `证据不足，需人工复核` / `外勤出勤不成立`"
    )
    action: str = Field(description="建议动作（如「系统自动补卡」）")
    policy_refs: list[str] = Field(
        description="结论文案的制度出处；为空表示**没有**制度依据，不得声称"
    )
    trace_id: str = Field(description="本次请求的 trace_id")
