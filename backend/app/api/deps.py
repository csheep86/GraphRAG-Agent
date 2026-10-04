"""FastAPI 依赖：trace_id / 认证态（含 org_id）/ 数据库会话。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.middleware import get_trace_id_value, new_trace_id
from app.db.session import open_session
from app.services.auth import get_auth_provider

#: 契约中登记的认证方案名，前端代码生成后即为 `bearerAuth`
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    description=(
        "认证态来源。Sprint 1 支持 `Bearer dev.<org_id>.<actor_id>`；"
        "Sprint 3 起由 M5 `POST /auth/login` 签发的 JWT 取代。"
    ),
)

DEV_ORG_HEADER_DESCRIPTION = (
    "【仅开发态兜底】租户 id。仅当 ALLOW_DEV_ORG_HEADER=true 且非生产环境时生效；"
    "Sprint 3 接入 M5 登录后必须移除"
    "（ADR-0003 §3.3：org_id 严禁来自 body / query）。"
)

DEV_ACTOR_HEADER_DESCRIPTION = (
    "【仅开发态兜底】操作者 id，缺省取 DEFAULT_ACTOR_ID；Sprint 3 起由认证态提供。"
)


async def get_trace_id() -> str:
    """取当前请求的 trace_id（中间件已保证存在）。"""
    return get_trace_id_value() or new_trace_id()


async def get_current_identity(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    x_org_id: Annotated[
        str | None, Header(alias="X-Org-Id", description=DEV_ORG_HEADER_DESCRIPTION)
    ] = None,
    x_actor_id: Annotated[
        str | None, Header(alias="X-Actor-Id", description=DEV_ACTOR_HEADER_DESCRIPTION)
    ] = None,
) -> Identity:
    """解析当前租户上下文（经接缝 1 ``AuthProvider`` 分发）。

    优先级：`Authorization: Bearer <token>` > 开发态请求头 > 401。
    两者都不可用时返回 401 `UNAUTHORIZED`，**不提供任何匿名路径**
    （`/api/v1/health` 不使用本依赖，因此天然豁免）。
    当前唯一实现 ``LocalAuthProvider``；企业身份源接入时扩展工厂。
    """
    settings = get_settings()

    identity = get_auth_provider().authenticate(
        settings=settings,
        bearer_token=(credentials.credentials if credentials is not None else None),
        org_id_header=x_org_id,
        actor_id_header=x_actor_id,
    )
    if identity is not None:
        return identity

    raise AppError(
        ErrorCode.UNAUTHORIZED,
        detail={
            "expected": "Authorization: Bearer <token>",
            "dev_fallback_enabled": settings.dev_org_header_enabled,
        },
    )


def get_tenant_session(identity: CurrentIdentity) -> Iterator[Session]:
    """每请求一个会话，**且**已绑定认证态解析出的 org（A3 / ADR-0003 §3.3）。

    org 只来自 ``identity.org_id``（认证态）——**不**读 header / body / query 的
    租户字段。取不到 org 则由 :func:`open_session` 之前的身份解析先抛 401。
    """
    session = open_session(org_id=identity.org_id)
    try:
        yield session
    finally:
        session.close()


CurrentIdentity = Annotated[Identity, Depends(get_current_identity)]

#: **A3（P3-A）：``DbSession`` 必须依赖 ``CurrentIdentity``**——两个独立依赖
#: 串成一条链，org 在**路由体执行之前**就绑到会话上。
#:
#: 为什么不能保持互相独立（坑 1）：RBAC（``app/services/rbac/deps.py``）在
#: 路由体**之前**就用这个 session 去查 ``user_roles``；若在路由体里才设 org，
#: RBAC 那次查询已经在「无 org」状态下跑完了（RLS 下 = 查不到任何角色 ⇒ 一律拒绝）。
#: ⇒ 依赖图顺序即安全顺序，这里不许拆回两个独立依赖。
DbSession = Annotated[Session, Depends(get_tenant_session)]
TraceId = Annotated[str, Depends(get_trace_id)]
