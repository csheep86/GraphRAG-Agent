"""统一业务错误码与异常类型。

约束来源：
- `CODEBUDDY.md`「错误响应规范」：所有异常统一返回 `{code, message, detail, trace_id}`，
  HTTP 状态码与业务错误码分离。
- `ADR-0001`：`TASK_INTERRUPTED`（进程重启回收孤儿任务）。
- `ADR-0002`：`KG_VERSION_NOT_ACTIVE`（显式指定非 active 版本必须拒绝，禁止静默降级）。
- `ADR-0003`：`FORBIDDEN`（跨租户访问）。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """统一业务错误码。新增错误码必须先更新 `contracts/openapi.yaml` 与人类可读规格。"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    KG_VERSION_NOT_ACTIVE = "KG_VERSION_NOT_ACTIVE"
    KG_TENANT_LEAK = "KG_TENANT_LEAK"
    TASK_INTERRUPTED = "TASK_INTERRUPTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    HTTP_ERROR = "HTTP_ERROR"


#: 每个错误码的默认 HTTP 状态码（HTTP 状态码与业务错误码分离）
ERROR_HTTP_STATUS: Mapping[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.DOCUMENT_NOT_FOUND: 404,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.KG_VERSION_NOT_ACTIVE: 409,
    ErrorCode.KG_TENANT_LEAK: 403,
    ErrorCode.TASK_INTERRUPTED: 409,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.HTTP_ERROR: 500,
}

#: 默认 human-readable 消息（英文短句，便于日志检索；面向用户的中文说明见人类可读规格）
DEFAULT_MESSAGES: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "Request validation failed",
    ErrorCode.UNAUTHORIZED: "Authentication required",
    ErrorCode.FORBIDDEN: "Cross-tenant access denied",
    ErrorCode.NOT_FOUND: "Resource not found",
    ErrorCode.DOCUMENT_NOT_FOUND: "Document not found",
    ErrorCode.FILE_TOO_LARGE: "Uploaded file exceeds the size limit",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Unsupported media type",
    ErrorCode.KG_VERSION_NOT_ACTIVE: "Requested kg_version is not active",
    ErrorCode.KG_TENANT_LEAK: "Cross-tenant subgraph detected",
    ErrorCode.TASK_INTERRUPTED: "Task interrupted by process restart",
    ErrorCode.NOT_IMPLEMENTED: "Infrastructure unavailable",
    ErrorCode.INTERNAL_ERROR: "Internal server error",
    ErrorCode.HTTP_ERROR: "Unmapped HTTP error",
}

#: 错误码语义 + 决策依据（写入 OpenAPI 枚举描述，供前端与人工阅读）
ERROR_CODE_DESCRIPTIONS: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "请求体 / 查询参数 / 路径参数未通过 Pydantic 校验。",
    ErrorCode.UNAUTHORIZED: "缺少或无法解析认证态（Bearertoken / 开发态请求头）。",
    ErrorCode.FORBIDDEN: "跨租户访问被拒（ADR-0003：org_id 不符），非本租户资源一律拒绝。",
    ErrorCode.NOT_FOUND: "通用资源不存在（含未注册路由）。",
    ErrorCode.DOCUMENT_NOT_FOUND: "文档不存在或未在本租户可见范围内。",
    ErrorCode.FILE_TOO_LARGE: "上传文件超过 MAX_UPLOAD_SIZE_MB（默认 100MB，M1 验收 2）。",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "上传文件 MIME 不在白名单（M1 验收 3）。",
    ErrorCode.KG_VERSION_NOT_ACTIVE: (
        "请求显式指定了非 active 的 kg_version（writing / failed / superseded），"
        "按 ADR-0002 §3.2 一律拒绝，严禁静默降级到最新版。"
    ),
    ErrorCode.KG_TENANT_LEAK: (
        "跨租户子图泄漏检测到（ADR-0003 §4，Sprint 5 批次 B）。"
        "active kg_version 内任一 Entity 节点 org_id 与当前 org_id 不一致——"
        "属数据质量事故伪装为正常结论，由 /agent/query 路由层转 403。"
    ),
    ErrorCode.TASK_INTERRUPTED: (
        "进程重启导致在途任务被 TaskManager.recover() 回收置 failed（ADR-0001 §3.2）。"
    ),
    ErrorCode.NOT_IMPLEMENTED: (
        "基础设施不可用（Neo4j 图谱存储不可用（连不上 / 查询失败）"
        "/ LLM 未配置或装配失败）时返回 501，**不**表示「接口未实现」。"
    ),
    ErrorCode.INTERNAL_ERROR: "未预期的服务端异常，已记录日志（含 trace_id）。",
    ErrorCode.HTTP_ERROR: "未在错误码表中登记的 HTTP 状态兜底，保留原始 HTTP 状态语义。",
}

#: 错误码 -> 决策来源（ADR / 规格），用于追溯
ERROR_CODE_SOURCES: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "CODEBUDDY.md 错误响应规范",
    ErrorCode.UNAUTHORIZED: "M5 §3 验收 1",
    ErrorCode.FORBIDDEN: "ADR-0003 §3.3 / M5 §3 验收 1",
    ErrorCode.NOT_FOUND: "CODEBUDDY.md 错误响应规范",
    ErrorCode.DOCUMENT_NOT_FOUND: "M1 §5.4",
    ErrorCode.FILE_TOO_LARGE: "M1 §3 验收 2",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "M1 §3 验收 3",
    ErrorCode.KG_VERSION_NOT_ACTIVE: "ADR-0002 §3.2 / M3 §4.1",
    ErrorCode.KG_TENANT_LEAK: "ADR-0003 §4 / Sprint 5 批次 B",
    ErrorCode.TASK_INTERRUPTED: "ADR-0001 §3.2",
    ErrorCode.NOT_IMPLEMENTED: "backend/CODEBUDDY.md §1.1 故障语义边界 / ADR-0002 §3.2",
    ErrorCode.INTERNAL_ERROR: "CODEBUDDY.md 错误响应规范",
    ErrorCode.HTTP_ERROR: "CODEBUDDY.md 错误响应规范",
}

#: HTTP 状态码 -> 错误码（用于拦截框架自身抛出的 HTTPException）
HTTP_STATUS_TO_ERROR_CODE: Mapping[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.HTTP_ERROR,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    501: ErrorCode.NOT_IMPLEMENTED,
}


def resolve_error_code(http_status: int) -> ErrorCode:
    """把任意 HTTP 状态码映射为已登记的错误码，未登记则兜底 `HTTP_ERROR`。"""
    return HTTP_STATUS_TO_ERROR_CODE.get(http_status, ErrorCode.HTTP_ERROR)


class AppError(Exception):
    """业务异常基类。所有业务错误必须抛本异常，禁止直接返回裸 JSON。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
        http_status: int | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.code = ErrorCode(code)
        self.message = message or DEFAULT_MESSAGES[self.code]
        self.detail = detail
        self.http_status = http_status or ERROR_HTTP_STATUS[self.code]
        self.headers = dict(headers or {})
        super().__init__(f"{self.code.value}: {self.message}")

    def to_body(self, trace_id: str) -> dict[str, Any]:
        """构造统一错误响应体 `{code, message, detail, trace_id}`。"""
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": self.detail,
            "trace_id": trace_id,
        }
