"""slowapi 限流装配（M5 §3 验收 5，Sprint 8.1 批次 B，决策 A11 / A14）。

全部结论来自**本地实测**（slowapi 0.1.10 + fastapi 0.141.1 源码逐行核对）：

1. **不能直接用 :class:`slowapi.middleware.SlowAPIMiddleware`**：FastAPI ≥0.141
   的 ``include_router`` 不再摊平路由，而是包一层 ``_IncludedRouter``
   （fastapi/routing.py:1586）——它没有 ``endpoint`` 属性，slowapi 的
   ``_find_route_handler`` 永远返回 ``None`` ⇒ **全部路由被当豁免、限流失效**
   （本批次真机复现：第 N 次请求仍 200）。故本模块自带
   :class:`RateLimitMiddleware`，路由解析走公开 ``route.matches(scope)``：
   ``_IncludedRouter.matches`` 内部会调 ``original_router.matches(scope)``，
   Starlette ``Router.matches`` **就地回填** ``scope["endpoint"]``——这正是
   Starlette 路由器分发前写下的事实，读它不算新造口径。
2. **429 handler 必须是同步函数**：slowapi 的中间件对 async handler 会
   **静默回落**到它的默认 handler（``{"error": ...}``，不合 H3 且无
   ``Retry-After``，slowapi/middleware.py:59-77）。我们不再用它的中间件，
   但 handler 依旧保持同步（见 ``core/exception_handlers.py``）。
3. **health 豁免**：探针可达 1 次/秒，贴着默认限跑；用
   :meth:`slowapi.Limiter.exempt` 标记（``_exempt_routes`` 按函数全名匹配）。
4. **存储**：单进程演示用 ``memory://``；多进程部署换 ``redis://`` 只改这里。

限流检查本身仍复用 slowapi 的 ``Limiter._check_request_limit``（与
SlowAPIMiddleware 同一入口），只有"找路由"这一步是本仓自有实现。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache
from inspect import iscoroutinefunction
from typing import Any

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from app.core.config import get_settings

#: include 嵌套下钻上限（演示结构：app → api_router → 6 个子 router，2 层足够）
_MAX_INCLUDE_DEPTH = 4

#: 限流豁免路由（endpoint 函数全名）。health 探针可达 1 次/秒，贴着默认限跑，
#: 被 429 会直接把实例摘除——豁免口径与审计 A1 的"探针噪声"一致。
#: **集中声明**而不用 ``@limiter.exempt`` 装饰器：装饰器在**导入时**注册到当时的
#: Limiter 单例上，任何换例（测试 cache_clear / 重建 app）都会把名单弄丢。
EXEMPT_ROUTE_NAMES = frozenset({"app.api.v1.routes.health.get_health"})

#: ASGI 三件套别名（避免每处都写 ``Any``）
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


@lru_cache(maxsize=1)
def get_limiter() -> Limiter:
    """构造（进程内单例）Limiter。

    每分钟每 IP 每接口 ``rate_limit_per_minute`` 次（M5 §3 验收 5 原文：
    "默认 N=60，可配置"）；配置项唯一消费点在这里（无消费者配置不得提交）。
    """
    settings = get_settings()
    return Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    )


def _resolve_endpoint(routes: list[Any], scope: Scope) -> Any:
    """从路由表解析当前请求的 endpoint 函数（FastAPI 0.141 兼容）。

    两级解析：
    1. ``route.matches(scope)`` → ``child_scope["endpoint"]``（普通 Route 直接命中）；
    2. FastAPI ≥0.141 的 ``_IncludedRouter.matches`` **只回 match、丢弃
       child_scope**（routing.py:1771-1772），其 ``_match``（同文件 :1728）才带
       ``child_scope["endpoint"]`` ⇒ FULL 而无 endpoint 时回落 ``_match``；
       且 ``_match`` 命中的可能仍是**嵌套** ``_IncludedRouter``（子 router 也是
       ``include_router`` 进来的）⇒ 沿返回的 ``inner_route`` 继续下钻。

    ``_match`` 虽是下划线方法，但同仓锁定的 fastapi 0.141.1 上它就是
    ``_IncludedRouter.handle`` 的实际分发路径（:1785），属**路由器写下的事实**
    而非投机；升级 FastAPI 时由本文件集中承担兼容成本。
    """
    for route in routes:
        try:
            match, child_scope = route.matches(scope)
        except Exception:  # noqa: BLE001 - 路由匹配失败不阻断限流判定
            continue
        if match != Match.FULL:
            continue

        endpoint = child_scope.get("endpoint") or getattr(route, "endpoint", None)
        if endpoint is not None:
            return endpoint

        current = route
        for _ in range(_MAX_INCLUDE_DEPTH):
            inner_match = getattr(current, "_match", None)
            if not callable(inner_match):
                break
            try:
                inner_match_result, inner_child, inner_route, effective_context = (
                    inner_match(scope)
                )
            except Exception:  # noqa: BLE001 - 同上
                break
            if inner_match_result != Match.FULL:
                break
            endpoint = (
                inner_child.get("endpoint")
                or getattr(inner_route, "endpoint", None)
                or getattr(
                    getattr(effective_context, "original_route", None),
                    "endpoint",
                    None,
                )
            )
            if endpoint is not None:
                return endpoint
            if inner_route is None or inner_route is current:
                break
            current = inner_route
    return None


class RateLimitMiddleware:
    """纯 ASGI 限流中间件（决策 A11；替代与 FastAPI 0.141 不兼容的 SlowAPIMiddleware）。

    **挂载位置**：审计（AuditMiddleware）**之内**、CORS 之内——429 响应必须
    流经审计（记一条 failure）与 TraceId（回显头）才出栈。

    行为对齐 ``SlowAPIMiddleware.dispatch``（slowapi/middleware.py:116-139）：
    豁免判定同 ``_should_exempt``（exempt_routes / 装饰器路由跳过），
    超限异常交由 ``app.exception_handlers`` 里登记的 handler（同步）出响应。
    """

    def __init__(self, app: Any) -> None:  # noqa: ANN001 - ASGI callable
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app = scope.get("app")
        limiter: Limiter | None = getattr(app, "state", None) and app.state.limiter
        if limiter is None or not limiter.enabled:
            await self.app(scope, receive, send)
            return

        endpoint = _resolve_endpoint(app.routes, scope)
        if self._should_exempt(limiter, endpoint):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            limiter._check_request_limit(request, endpoint, True)
        except RateLimitExceeded as exc:
            handler = app.exception_handlers.get(type(exc))
            if handler is None:  # 未登记：交给上层兜底（不应发生，main.py 已登记）
                raise
            response: Response = (
                await handler(request, exc)
                if iscoroutinefunction(handler)
                else handler(request, exc)
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _should_exempt(limiter: Limiter, endpoint: Any) -> bool:
        """豁免判定：本仓集中名单 + slowapi 自身口径（middleware.py:98-113）。"""
        if endpoint is None:
            return True
        name = f"{endpoint.__module__}.{endpoint.__name__}"
        return (
            name in EXEMPT_ROUTE_NAMES
            or name in limiter._exempt_routes
            or name in limiter._route_limits
        )


__all__ = ["RateLimitMiddleware", "get_limiter"]
