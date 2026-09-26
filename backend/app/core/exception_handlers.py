"""全局异常处理器：把一切异常收敛为 `{code, message, detail, trace_id}`。

依据 `CODEBUDDY.md`「错误响应规范」：
1. 所有异常统一由全局异常处理器拦截；
2. HTTP 状态码与业务错误码分离。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode, resolve_error_code
from app.core.middleware import get_trace_id_value, new_trace_id

# 校验错误 detail 中禁止回显的键：可能携带敏感原文（如密码 / Token）
_FORBIDDEN_ERROR_KEYS = {"input", "ctx", "url"}

#: RateLimitItem.granularity -> Retry-After 秒数（fixed-window 语义：等整个窗口滚走）
_RETRY_AFTER_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


def current_trace_id() -> str:
    return get_trace_id_value() or new_trace_id()


def _json_response(
    status_code: int,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        headers=dict(headers) if headers else None,
    )


def _build_body(
    code: ErrorCode,
    message: str,
    detail: dict[str, Any] | None,
    trace_id: str,
) -> dict[str, Any]:
    return {
        "code": code.value,
        "message": message,
        "detail": detail,
        "trace_id": trace_id,
    }


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    """按命中窗口的粒度换算 ``Retry-After``（秒）。未知粒度兜底 60。"""
    granularity = getattr(getattr(exc.limit, "limit", None), "granularity", None)
    return _RETRY_AFTER_SECONDS.get(granularity, 60)


def _record_rate_limit_audit(
    request: Request, exc: RateLimitExceeded, trace_id: str
) -> None:
    """限流触发同步写 ``audit_log(action=rate_limit.triggered)``（决策 **A14**）。

    口径照 ``AuditMiddleware._write_inner``：身份经接缝 1 解析，**拿不到就不写**
    （org_id 是隔离键，不可填空）；任何异常只记日志——审计缺陷不得改变 429 响应。
    ``detail`` 只写结构化字段（A5：绝不写响应体原文）。
    """
    try:
        from app.core.config import get_settings
        from app.core.middleware import ACTOR_ID_HEADER, ORG_ID_HEADER
        from app.db.session import SessionLocal
        from app.services.audit import record_audit_entry
        from app.services.auth import get_auth_provider

        settings = get_settings()
        authorization = request.headers.get("authorization")
        bearer_token = (
            authorization[7:].strip()
            if authorization and authorization.lower().startswith("bearer ")
            else None
        )
        try:
            identity = get_auth_provider().authenticate(
                settings=settings,
                bearer_token=bearer_token,
                org_id_header=request.headers.get(ORG_ID_HEADER),
                actor_id_header=request.headers.get(ACTOR_ID_HEADER),
            )
        except Exception:  # noqa: BLE001 - 401 语义由依赖层决定，审计侧无权判定
            identity = None
        if identity is None:
            logger.bind(path=request.url.path).warning(
                "rate_limit_audit_skipped_no_identity"
            )
            return

        with SessionLocal() as session:
            record_audit_entry(
                session,
                org_id=identity.org_id,
                action="rate_limit.triggered",
                actor_id=identity.actor_id,
                actor_ip=request.client.host if request.client else None,
                resource=f"{request.method} {request.url.path}",
                status="failure",
                trace_id=trace_id,
                detail={
                    "status_code": 429,
                    "method": request.method,
                    "path": request.url.path,
                    "limit": str(exc.limit.limit),
                },
            )
            # 同 AuditMiddleware：handler 无业务事务可依附，须显式提交
            session.commit()
    except Exception as audit_exc:  # noqa: BLE001 - 审计写失败绝不上抛
        logger.bind(reason=str(audit_exc)).warning("rate_limit_audit_write_failed")


def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """slowapi 触发限流：429 + `RATE_LIMITED` + `Retry-After`（M5 §3 验收 5）。

    ⚠️ **必须保持同步函数**：``SlowAPIMiddleware.dispatch`` 走
    ``sync_check_limits``（slowapi/middleware.py:59-77），对 **async handler 会
    静默回落**到 slowapi 默认 handler——那个返回 ``{"error": "Rate limit
    exceeded: ..."}``，不合 H3 统一格式且无 ``Retry-After``（本批次实测确认）。
    """
    trace_id = current_trace_id()
    retry_after = _retry_after_seconds(exc)
    error = AppError(
        ErrorCode.RATE_LIMITED,
        headers={"Retry-After": str(retry_after)},
        detail={"limit": str(exc.limit.limit), "retry_after_seconds": retry_after},
    )
    logger.bind(
        trace_id=trace_id,
        http_method=request.method,
        path=request.url.path,
        error_code=ErrorCode.RATE_LIMITED.value,
        http_status=error.http_status,
        limit=str(exc.limit.limit),
    ).warning("rate_limit_triggered")
    _record_rate_limit_audit(request, exc, trace_id)
    return _json_response(
        error.http_status, error.to_body(trace_id), headers=error.headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册五类处理器：业务 / 校验 / HTTP / 限流 / 未预期异常。"""

    # 限流 handler 必须在 StarletteHTTPException 之前显式登记：
    # RateLimitExceeded 是其子类，FastAPI 按具体类型优先匹配。
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = current_trace_id()
        logger.bind(
            trace_id=trace_id,
            http_method=request.method,
            path=request.url.path,
            error_code=exc.code.value,
            http_status=exc.http_status,
        ).warning("app_error")
        return _json_response(
            exc.http_status, exc.to_body(trace_id), headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = current_trace_id()
        errors: list[dict[str, Any]] = []
        for error in exc.errors():
            errors.append(
                {
                    key: value
                    for key, value in error.items()
                    if key not in _FORBIDDEN_ERROR_KEYS
                }
            )
        logger.bind(
            trace_id=trace_id,
            http_method=request.method,
            path=request.url.path,
            error_code=ErrorCode.VALIDATION_ERROR.value,
            error_count=len(errors),
        ).warning("validation_error")
        return _json_response(
            400,
            _build_body(
                ErrorCode.VALIDATION_ERROR,
                DEFAULT_MESSAGES[ErrorCode.VALIDATION_ERROR],
                {"errors": errors},
                trace_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        trace_id = current_trace_id()
        code = resolve_error_code(exc.status_code)
        detail = {"http_detail": str(exc.detail)} if exc.detail else None
        logger.bind(
            trace_id=trace_id,
            http_method=request.method,
            path=request.url.path,
            error_code=code.value,
            http_status=exc.status_code,
        ).warning("http_exception")
        return _json_response(
            exc.status_code,
            _build_body(code, DEFAULT_MESSAGES[code], detail, trace_id),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        trace_id = current_trace_id()
        logger.bind(
            trace_id=trace_id,
            http_method=request.method,
            path=request.url.path,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            http_status=500,
            exc_type=type(exc).__name__,
        ).exception("unhandled_exception")
        return _json_response(
            500,
            _build_body(
                ErrorCode.INTERNAL_ERROR,
                DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR],
                None,
                trace_id,
            ),
        )
