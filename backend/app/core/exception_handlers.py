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
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode, resolve_error_code
from app.core.middleware import get_trace_id_value, new_trace_id

# 校验错误 detail 中禁止回显的键：可能携带敏感原文（如密码 / Token）
_FORBIDDEN_ERROR_KEYS = {"input", "ctx", "url"}


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


def register_exception_handlers(app: FastAPI) -> None:
    """注册四类处理器：业务异常 / 校验异常 / HTTP 异常 / 未预期异常。"""

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
