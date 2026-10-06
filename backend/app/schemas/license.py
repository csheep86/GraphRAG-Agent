"""License 相关契约模型（ADR-0006 §2.2 / §2.4）。

⚠️ **契约纯净纪律**：``licenses.raw_payload`` / ``signature`` / 公钥
**一律不进契约**（前端拿到了也没有合法用途，反而成为泄漏面）。
本 Schema 只暴露「够用即可」的状态字段 —— 够运维自检，不够伪造 License。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.errors import ErrorCode


class LicenseLimits(BaseModel):
    """授权维度上限（ADR-0006 §2.4 的组合维度 1 / 2）。"""

    max_orgs: int = Field(description="租户数上限（0 = 未授权任何租户）")
    max_seats: int = Field(description="席位数上限（0 = 未授权任何席位）")


class LicenseStatusResponse(BaseModel):
    """``GET /api/v1/license/status`` 的响应。

    **为什么这个端点必须豁免 License 拦截**：它是自检面 ——
    客户现场拿到无效 License 时，若连「为什么不能用」都查不到，就只能提工单。
    """

    has_license: bool = Field(description="是否加载到有效 License")
    enforced: bool = Field(
        description="是否处于强制模式（false = 放行但会落 bypass 审计）"
    )
    code: ErrorCode | None = Field(
        default=None,
        description="无效原因错误码；``has_license=true`` 时为 ``null``",
    )
    license_id: str = Field(default="", description="License 唯一标识（UUID）")
    status: str = Field(
        default="", description="active / expired / revoked / superseded"
    )
    in_grace: bool = Field(description="是否处于过期宽限期（**只读**可用）")
    not_before: datetime | None = Field(default=None, description="生效时间")
    not_after: datetime | None = Field(default=None, description="有效期截止时间")
    grace_days: int = Field(default=0, description="宽限天数")
    limits: LicenseLimits = Field(description="维度上限")
    modules: list[str] = Field(
        default_factory=list,
        description="已授权模块（ADR-0006 §3.3 取值集合）",
    )
    trace_id: str = Field(description="链路追踪 id")
