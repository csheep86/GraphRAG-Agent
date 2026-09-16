"""请求级中间件：trace_id 贯通（M1 验收 7 / M5 §5.3）。

采用纯 ASGI 中间件而非 `BaseHTTPMiddleware`，保证**任何**响应（含 500）
都会带上 `X-Trace-Id` 回显。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import UUID, uuid4

TRACE_ID_HEADER = "X-Trace-Id"

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """生成 UUIDv4 字符串（M1 验收 7 要求的格式）。"""
    return str(uuid4())


def get_trace_id_value() -> str | None:
    return _trace_id_var.get()


def set_trace_id(value: str) -> Token[str | None]:
    return _trace_id_var.set(value)


def reset_trace_id(token: Token[str | None]) -> None:
    _trace_id_var.reset(token)


def is_valid_trace_id(value: str) -> bool:
    """透传的 trace_id 必须是可解析的 UUID，避免脏值污染全链路。"""
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


class TraceIdMiddleware:
    """透传 / 生成 trace_id，并写入 contextvar 与响应头。"""

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == TRACE_ID_HEADER.lower():
                incoming = value.decode("latin-1").strip()
                break

        trace_id = (
            incoming if incoming and is_valid_trace_id(incoming) else new_trace_id()
        )
        token = set_trace_id(trace_id)
        header_bytes = (
            TRACE_ID_HEADER.lower().encode("latin-1"),
            trace_id.encode("latin-1"),
        )

        async def send_with_trace_id(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append(header_bytes)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            reset_trace_id(token)
