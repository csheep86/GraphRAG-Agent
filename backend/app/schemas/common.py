"""通用契约模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode


class ErrorResponse(BaseModel):
    """统一错误响应体（**所有** 4xx / 5xx 均使用本结构）。

    来源：`CODEBUDDY.md`「错误响应规范」。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "KG_VERSION_NOT_ACTIVE",
                "message": "Requested kg_version is not active",
                "detail": {
                    "kg_version": "20260320T1430Z-01H9X9",
                    "version_status": "writing",
                },
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    code: ErrorCode = Field(
        description="业务错误码（HTTP 状态码与业务错误码分离）",
        examples=["VALIDATION_ERROR", "FORBIDDEN", "KG_VERSION_NOT_ACTIVE"],
    )
    message: str = Field(description="面向调用方的简短英文摘要，便于日志检索")
    detail: dict[str, Any] | None = Field(
        default=None,
        description="结构化补充信息；敏感字段（文件名原文 / error_detail / pii_flags）严禁出现在此",
    )
    trace_id: str = Field(description="与响应头 X-Trace-Id 一致，贯穿 M1–M5 全链路")
