"""路由层**强制校验入口**（G-24 判据的另一半）。

矩阵只存在于库里 / 字典里时，权限就是「一列装饰」——必须有一条**每个受保护端点
都会经过**的路径去查它。本模块提供 :func:`require_permission`，用法：

    @router.post("/detect", dependencies=[require_permission("affiliation", "write")])

**为什么挂在路由装饰器上而不是写在路由体里**：写在体里就会有人漏写，而"漏写"
比"多校验"难发现得多（与审计中间件 A1「全量写、不靠埋点」同一条纪律）。

**为什么不改契约**：本依赖**不引入任何请求参数**（不读 query / header / body 的
权限字段），403 `FORBIDDEN` 复用契约里已有的错误码 ⇒ `export_openapi.py --check`
保持零漂移。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, Request

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.services.rbac.policy import ACTION_READ, ACTION_WRITE
from app.services.rbac.service import (
    build_permission_context,
    evaluate,
    permission_denied_error,
    record_permission_denied,
)

#: 路径参数里承载文档 id 的键（命中即做**文档级**粒度校验）
_DOCUMENT_ID_PARAM = "document_id"


def path_document_id(request: Request) -> UUID | None:
    """从路径参数里取 `document_id`；不是合法 UUID 则视为「本次无文档粒度」。

    **不猜**：路径参数可能带非 UUID 形态（契约里 `chunk_id` 就是字符串），
    解析不出来就返回 ``None``（不做文档级收窄），而不是拿原始字符串去比对——
    那会把"格式不对"变成"没有权限"，两种拒绝理由混在一起审计就废了。
    """
    raw = request.path_params.get(_DOCUMENT_ID_PARAM)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def require_permission(resource: str, action: str) -> Any:
    """声明「本端点需要 ``resource`` 上的 ``action`` 权限」的路由依赖。

    判定顺序：角色 → 资源 × 操作 → 场景（由资源推导）→ 文档（路径参数）。
    拒绝时**先落审计**（``action=permission.denied``）**再**抛 403 `FORBIDDEN`。
    """
    if action not in (ACTION_READ, ACTION_WRITE):  # pragma: no cover - 配置期错误
        raise ValueError(f"未知操作：{action}")

    async def enforce_rbac(
        request: Request,
        identity: CurrentIdentity,
        session: DbSession,
        trace_id: TraceId,
    ) -> None:
        context = build_permission_context(
            session, org_id=identity.org_id, user_id=identity.actor_id
        )
        reason = evaluate(
            context,
            resource=resource,
            action=action,
            document_id=path_document_id(request),
        )
        if reason is None:
            return

        record_permission_denied(
            session,
            org_id=identity.org_id,
            actor_id=identity.actor_id,
            resource=resource,
            action=action,
            reason=reason,
            trace_id=trace_id,
            actor_ip=_client_ip(request),
            method=request.method,
            path=request.url.path,
        )
        raise permission_denied_error(
            resource=resource,
            action=action,
            reason=reason,
            roles=context.roles,
        )

    return Depends(enforce_rbac)


def _client_ip(request: Request) -> str | None:
    """客户端 IP（与审计中间件同口径：取不到就不填，不猜）。"""
    return request.client.host if request.client else None


__all__ = ["path_document_id", "require_permission"]
