"""请求级中间件：trace_id 贯通（M1 验收 7 / M5 §5.3）+ 审计留痕（M5 §3 验收 2）。

采用纯 ASGI 中间件而非 `BaseHTTPMiddleware`，保证**任何**响应（含 500）
都会带上 `X-Trace-Id` 回显，且审计能捕获到 unhandled exception 的 5xx 响应。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:  # 仅类型检查期：``ErrorCode`` 在实现里是**函数内**导入的（延迟引用）
    from app.core.errors import ErrorCode

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

    async def __call__(self, scope, receive, send) -> None:
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
    2. **`detail` 只写结构化字段** —— 绝不写响应体原文（决策 **A5**）。
       **P5-E 起**：`detail` 与日志 `extra` 都在写入前过一遍统一脱敏器
       （`app.core.masking`）——但脱敏只认**登记表里的 key 名**，
       未登记字段照样原样落库，故"只写结构化字段"这条纪律**不因脱敏器而放宽**。
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
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
        from app.db.session import open_session
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
        # A4 登记的系统通道（P3-A）：审计写库绕开请求依赖自建 Session，
        # 但 org **照绑**——它来自接缝 1 解析出的身份（认证态），不是请求参数。
        # 不绑 ⇒ RLS 下这条审计写不进去（WITH CHECK 恒不成立），审计静默丢失。
        with open_session(org_id=identity.org_id) as session:
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


class LicenseMiddleware:
    """License 强制中间件（**纯 ASGI**，DR-C1 / G-23 / ADR-0006 §2.6）。

    **为什么必须纯 ASGI**：每请求都要跑但它极轻，且必须与
    :class:`AuditMiddleware` 同形态（该批首要目标是 P95 增量 **< 1ms**，R-L4）。
    继承 ``BaseHTTPMiddleware`` 会引入额外的 body 缓冲与异常转换开销
    ⇒ `tests/test_guardrails_compliance.py` 直接判其为**不达标**。

    **挂载位置**：``main.py`` 里插在 ``RateLimitMiddleware`` 之后、
    ``AuditMiddleware`` 之前 —— ``add_middleware`` 后加者在外层 ⇒
    实际顺序是 `审计 → License → 限流 → 路由`：审计要能记录 License 的拒绝本身，
    License 在限流之前避免无效 License 消耗配额（§2.6 固定顺序）。

    **豁免**（§2.6 集中声明，与限流 ``EXEMPT_ROUTE_NAMES`` 同款口径）：
    ``/health`` 与 ``/license/status`` —— 自检端点必须可访问，
    否则客户现场拿到一份无效 License 时**连为什么都不知道**。

    **性能**（§2.6）：只做内存判断 —— 有效期比较 + 模块集合 ``in``；
    不读盘、不验签（那些只在重载态时发生）。
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(  # noqa: ANN001 - ASGI callable：参数类型由 ASGI 协议给出
        self, scope, receive, send
    ) -> None:
        if scope["type"] != "http" or self._is_exempt(scope):
            await self.app(scope, receive, send)
            return

        denied = self._decide(scope)
        if denied is None:
            await self.app(scope, receive, send)
            return

        # **一次定值、处处复用**：下面三个去处必须拿到**同一个** trace_id
        # （审计 + 响应体），否则这条拒绝就永远串不进链路，排障时无从反查。
        trace_id = LicenseMiddleware._trace_id(scope)
        self._audit_denied(scope, denied, trace_id)
        await self._send_denied(send, denied, trace_id)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _is_exempt(scope: dict[str, Any]) -> bool:
        """``/health`` 与 ``/license/status`` 永不拦（§2.6 自检端点必须可达）。"""
        from app.core.config import get_settings

        path = str(scope.get("path", ""))
        prefix = get_settings().api_prefix
        return path == f"{prefix}/health" or path.endswith("/license/status")

    def _decide(self, scope: dict[str, Any]) -> ErrorCode | None:
        """返回错误码 = 拒绝；``None`` = 放行。"""
        from app.core.config import get_settings
        from app.core.errors import ErrorCode
        from app.services.license.policy import READ_ONLY_METHODS, required_module
        from app.services.license.provider import get_license_provider

        settings = get_settings()
        state = get_license_provider().current_state()

        if not settings.license_enforce:
            # §2.5 最后一行：不强执时**放行但必须落 license.bypass 审计**——
            # 禁止静默放行（否则没人知道 License 事实上没在工作）。
            self._audit_bypass(scope)
            return None

        if not state.ok:
            return state.code

        # 宽限期内只读（§2.5 第 4 行）
        if state.in_grace and scope.get("method") not in READ_ONLY_METHODS:
            return ErrorCode.LICENSE_EXPIRED

        module = required_module(str(scope.get("path", "")))
        if module is not None and module not in state.modules:
            return ErrorCode.LICENSE_MODULE_DISABLED

        # 维度 1 / 2（租户数 / 席位数）**不在中间件里判** —— §2.5「卡增量、保存量」：
        # 它们只拒绝**新建**动作（新建 org / 启用用户），没有理由拦只读请求。
        # 判据落在 policy.py，由 P2-C 的「新建 / 启用」动作调用。
        return None

    def _audit_denied(
        self, scope: dict[str, Any], code: ErrorCode, trace_id: str
    ) -> None:
        """拒绝必须留痕（§2.5）：``action = license.denied``。

        ``detail`` **只含错误码与维度**，绝不含 License 正文 / 签名（§2.5 明令）。
        """
        self._audit(
            scope, trace_id, action="license.denied", detail={"code": str(code.value)}
        )

    def _audit_bypass(self, scope: dict[str, Any], trace_id: str) -> None:
        """``LICENSE_ENFORCE=false`` ⇒ 放行但留痕（§2.5「禁止静默放行」）。"""
        self._audit(
            scope, trace_id, action="license.bypass", detail={"enforced": False}
        )

    def _audit(
        self,
        scope: dict[str, Any],
        trace_id: str,
        *,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        """写一条审计；任何失败都**只记日志**（License 缺陷不得变成全站 500）。"""
        from app.core.config import DEFAULT_ORG_ID, get_settings
        from app.db.session import open_session
        from app.services.audit import record_audit_entry

        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        try:
            settings = get_settings()
            identity = self._resolve_identity(scope, settings)
            org_id = identity.org_id if identity is not None else DEFAULT_ORG_ID
            actor_id = identity.actor_id if identity is not None else None
            with open_session(org_id=org_id) as session:
                record_audit_entry(
                    session,
                    org_id=org_id,
                    action=action,
                    actor_id=actor_id,
                    resource=f"{method} {path}"[:255],
                    status="failure",
                    trace_id=trace_id,
                    detail=detail,
                )
                session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.bind(action=action, path=path, reason=str(exc)).warning(
                "license_audit_write_failed"
            )

    @staticmethod
    def _trace_id(scope: dict[str, Any]) -> str:
        """**一次定值、审计与响应体复用同一个值**（缺了就是"串不进链路"的假审计）。

        ⚠️ **为什么不能只信 ``get_trace_id_value()``**：本中间件按 §2.6 的顺序挂在
        ``TraceIdMiddleware`` **之外**（审计 → License → 限流 → 路由），
        到达这里时 contextvar **还没被写入** ⇒ 直接读恒为 ``None``。
        ⇒ 优先采信**调用方显式传入**的 ``X-Trace-Id``（这样客户才能把这条拒绝串回自己的链路），
        都没有才自行生成；结果**缓存进 scope**，保证同一请求的三处引用拿到同一个值。
        """
        cached = scope.get("license_trace_id")
        if isinstance(cached, str) and cached:
            return cached
        header = TRACE_ID_HEADER.encode("latin-1")
        value = ""
        for key, raw in scope.get("headers") or ():
            if key.lower() == header:
                value = raw.decode("latin-1")
                break
        resolved = value or get_trace_id_value() or str(uuid4())
        scope["license_trace_id"] = resolved
        return resolved

    @staticmethod
    def _resolve_identity(scope: dict[str, Any], settings: Any) -> Any:
        """与 :class:`AuditMiddleware` **同一套**身份解析（决策 A6：不另起口径）。"""
        from app.services.auth import get_auth_provider

        return AuditMiddleware._resolve_identity(scope, settings, get_auth_provider)

    @staticmethod
    async def _send_denied(  # noqa: ANN001 - send 的类型由 ASGI 协议给出
        send, code: ErrorCode, trace_id: str
    ) -> None:
        """构造 403 响应体：``{code, message, detail, trace_id}``（统一错误响应规范）。

        状态码统一 **403**（§2.5 明写：**不用 402** —— 402 语义未标准化，
        client / 网关处理不一致）。``trace_id`` 由调用方**一次定值**传入，
        保证与落进审计的那一条是同一个值。
        """
        import json

        from app.core.errors import AppError

        body = AppError(code).to_body(trace_id)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})
