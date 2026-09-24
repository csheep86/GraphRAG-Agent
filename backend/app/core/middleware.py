"""请求级中间件：trace_id 贯通（M1 验收 7 / M5 §5.3）+ 审计留痕（M5 §3 验收 2）。

采用纯 ASGI 中间件而非 `BaseHTTPMiddleware`，保证**任何**响应（含 500）
都会带上 `X-Trace-Id` 回显，且审计能捕获到 unhandled exception 的 5xx 响应。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID, uuid4

from loguru import logger

TRACE_ID_HEADER = "X-Trace-Id"

#: 开发环境脚手架头（ADR-0003 §3.3 限期兜底；M5 登录后改为 token 主体）
ACTOR_ID_HEADER = "X-Actor-Id"
ORG_ID_HEADER = "X-Org-Id"

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


class AuditMiddleware:
    """审计留痕中间件（M5 §3 验收 2；决策 **A1**：中间件全量写 + allowlist）。

    **挂载位置**：必须在 :class:`TraceIdMiddleware` **之内**（拿到 trace_id），
    又必须在路由之前 —— `main.py` 的 ``add_middleware`` 是「后加者在外层」，
    所以本中间件要**先于** TraceId 添加。

    **allowlist**（A1）：只对 ``/api/v1/*`` 且**非 health** 的请求写一条。
    排除 health 是避免探针噪声把演示页撑爆（探针 / 负载均衡每秒打一次，
    而每次一个 CVE 延迟的重链并不重要）。

    **两条硬纪律**：

    1. **写失败只记日志、不抛异常** —— 审计缺陷不得变成全站 500（proposal 风险 2）；
    2. **`detail` 只写结构化字段** —— 绝不写响应体原文（决策 **A5**，本批次无脱敏器）。
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http" or not self._is_auditable(scope):
            await self.app(scope, receive, send)
            return

        captured: dict[str, Any] = {"status_code": 500}

        async def send_with_capture(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                captured["status_code"] = message["status"]
                # 路由匹配完成后 Starlette 才把 endpoint / path_params 写进 scope
                # （starlette/routing.py:253 / 338）；响应开始前捕获是最早可得的时机
                captured["endpoint"] = scope.get("endpoint")
                captured["path_params"] = dict(scope.get("path_params") or {})
            await send(message)

        try:
            await self.app(scope, receive, send_with_capture)
        finally:
            # 无论成功 / 失败 / 被中断都要留痕；这里再抛异常就是全站 500
            self._write(scope, captured)

    # ------------------------------------------------------------------ internals

    def _is_auditable(self, scope: dict[str, Any]) -> bool:
        """allowlist 判定：``/api/v1/*`` 且非 health。"""
        from app.core.config import get_settings

        path = scope.get("path", "")
        prefix = get_settings().api_prefix
        if not path.startswith(f"{prefix}/"):
            return False
        return path[len(prefix) :] != "/health"

    def _write(self, scope: dict[str, Any], captured: dict[str, Any]) -> None:
        """写一条 `audit_log`；任何异常都吞掉并记日志。"""
        method = scope.get("method", "")
        path = scope.get("path", "")
        status_code = int(captured.get("status_code") or 500)

        try:
            self._write_inner(
                scope, captured, method=method, path=path, status_code=status_code
            )
        except Exception as exc:  # noqa: BLE001 - 审计写失败绝不上抛
            logger.bind(method=method, path=path, reason=str(exc)).warning(
                "audit_log_write_failed"
            )

    def _write_inner(
        self,
        scope: dict[str, Any],
        captured: dict[str, Any],
        *,
        method: str,
        path: str,
        status_code: int,
    ) -> None:
        from app.core.config import get_settings
        from app.db.session import SessionLocal
        from app.services.audit import record_audit_entry, resolve_action
        from app.services.auth import get_auth_provider

        settings = get_settings()
        trace_id = get_trace_id_value()
        if trace_id is None:  # TraceIdMiddleware 未挂载：宁可不写，也不编 trace_id
            logger.bind(method=method, path=path).warning(
                "audit_log_skipped_no_trace_id"
            )
            return

        identity = self._resolve_identity(scope, settings, get_auth_provider)
        if identity is None:
            # 401 / 匿名请求拿不到 org_id，而 org_id 是隔离键（不可伪造、不可填空）⇒ 不写。
            # 已知缺口（S11 RBAC 落地时一并收）：`permission.denied` 类事件需脱离身份也存在。
            logger.bind(method=method, path=path, status_code=status_code).warning(
                "audit_log_skipped_no_identity"
            )
            return

        endpoint = captured.get("endpoint")
        resource = f"{method} {path}"
        # `failure` 覆盖 4xx 与 5xx——审计语义是「这次调用有没有成功」，
        # 与 HTTP 状态码族无关；真正的错误码在响应体里。
        with SessionLocal() as session:
            record_audit_entry(
                session,
                org_id=identity.org_id,
                action=resolve_action(endpoint=endpoint, method=method, path=path),
                actor_id=identity.actor_id,
                actor_ip=self._client_ip(scope),
                doc_id=self._document_id(captured),
                resource=resource,
                status="success" if status_code < 400 else "failure",
                trace_id=trace_id,
                detail={"status_code": status_code, "method": method, "path": path},
            )
            # 中间件里**没有**业务事务可依附（决策 A10 的「同 session 范式」在此不适用），
            # 故必须显式提交——否则 ``finally`` 关闭会话时这条审计会被回滚掉。
            session.commit()

    @staticmethod
    def _resolve_identity(
        scope: dict[str, Any], settings: Any, auth_provider_factory: Any
    ) -> Any:
        """复用接缝 1 ``AuthProvider`` 解析身份——**不另起一套解析口径**（决策 A6）。"""
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        bearer_token: str | None = None
        for key, value in headers.items():
            if key == "authorization" and value.lower().startswith("bearer "):
                bearer_token = value[7:].strip()
                break

        try:
            return auth_provider_factory().authenticate(
                settings=settings,
                bearer_token=bearer_token,
                org_id_header=headers.get(ORG_ID_HEADER.lower()),
                actor_id_header=headers.get(ACTOR_ID_HEADER.lower()),
            )
        except Exception:  # noqa: BLE001 - 401 语义由依赖层决定，审计侧无权判定
            return None

    @staticmethod
    def _client_ip(scope: dict[str, Any]) -> str | None:
        """客户端 IP（ASGI scope 的 ``client`` 元组；缺失则不填，不猜）。"""
        client = scope.get("client")
        if isinstance(client, (list, tuple)) and client:
            return str(client[0])
        return None

    @staticmethod
    def _document_id(captured: dict[str, Any]) -> UUID | None:
        """从路径参数里取文档 id；非 UUID（如 chunk_id）返回 ``None``。"""
        raw = captured.get("path_params", {}).get("document_id")
        if raw is None:
            return None
        try:
            return UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            return None
