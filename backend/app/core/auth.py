"""认证态解析（Sprint 1 临时实现）。

依据 `ADR-0003` §3.3：
- `org_id` **只能**来自认证态，**严禁**从请求 body / query 读取；
- Sprint 1 尚无 M5 `POST /auth/login`，因此提供两条**限期**兜底路径：
  1. `Bearer dev.<org_id>.<actor_id>` —— 无签名的开发态 token；
  2. `X-Org-Id` / `X-Actor-Id` 请求头 —— 仅 `ALLOW_DEV_ORG_HEADER=true` 且非生产时生效。
- **Sprint 3 必须替换为 M5 签发的 JWT 解析，并删除以上兜底。**

**2026-10-07（P2-C）：JWT 分支已落地，dev 兜底**尚未**删除。**
`POST /auth/login` 自本批起签发 JWT（HS256，见 `app/core/token.py`），
:func:`parse_bearer_token` 在 dev 格式之后增加了 JWT 验签分支 ⇒ dev 兜底从
「唯一的认证态来源」降级为「**并存的**开发态来源」。它**仍在**——上千条既有用例
的身份来源就是它，删掉等于一次性改掉全部测试的主体，那是另一批的事
（见 `changes/archive/2026-10-07-P2-C/proposal.md` §5「不许外推」；该批已于 2026-10-07 归档）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.token import verify_access_token

IdentitySource = Literal["bearer_token", "dev_org_header", "jwt"]

DEV_TOKEN_PREFIX = "dev"


@dataclass(frozen=True, slots=True)
class Identity:
    """当前请求的租户上下文。`org_id` 是后续所有查询的强制过滤键（ADR-0003）。"""

    org_id: UUID
    actor_id: UUID
    roles: tuple[str, ...] = field(default_factory=tuple)
    source: IdentitySource = "bearer_token"


def parse_bearer_token(raw_token: str, settings: Settings) -> Identity:
    """解析认证 token（**两条**来源，顺序固定）。

    1. 开发态格式 `dev.<org_id>.<actor_id>`（生产环境一律拒绝）；
    2. `POST /auth/login` 签发的 JWT（HS256，验签见 :mod:`app.core.token`）。

    两者都不是 ⇒ 401，不提供任何绕过路径。

    **为什么 dev 格式排在前**：它有一个 `dev.` 前缀可**零成本**判别；JWT 分支要跑
    HMAC。把它放前面，既有的上千条 dev 用例一微秒都不多花。
    """
    token = raw_token.strip()
    if token.startswith(f"{DEV_TOKEN_PREFIX}."):
        if settings.is_production:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Development token is not accepted in production",
                detail={"reason": "dev_token_disabled"},
            )
        parts = token.split(".")
        if len(parts) != 3:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Malformed development token",
                detail={"expected_format": "dev.<org_id>.<actor_id>"},
            )
        try:
            return Identity(org_id=UUID(parts[1]), actor_id=UUID(parts[2]))
        except ValueError as exc:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Development token carries malformed UUIDs",
                detail={"expected_format": "dev.<org_id>.<actor_id>"},
            ) from exc

    claims = verify_access_token(token, settings)
    if claims is not None:
        # 角色**不**从令牌取：唯一真源是 user_roles 表（core/token.py 模块 docstring）。
        return Identity(org_id=claims.org_id, actor_id=claims.user_id, source="jwt")

    raise AppError(
        ErrorCode.UNAUTHORIZED,
        "Unsupported bearer token",
        detail={
            "reason": "token_is_neither_dev_token_nor_valid_jwt",
            "expected": "POST /auth/login 签发的 JWT",
        },
    )


def identity_from_dev_headers(
    *,
    settings: Settings,
    org_id_header: str | None,
    actor_id_header: str | None,
) -> Identity | None:
    """开发态请求头兜底。未启用或未提供时返回 `None`（由调用方决定是否 401）。"""
    if not settings.dev_org_header_enabled:
        return None
    if org_id_header is None and actor_id_header is None:
        return None
    try:
        org_id = UUID(org_id_header) if org_id_header else settings.default_org_id
        actor_id = (
            UUID(actor_id_header) if actor_id_header else settings.default_actor_id
        )
    except ValueError as exc:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "Malformed X-Org-Id / X-Actor-Id header",
            detail={"expected_format": "UUID"},
        ) from exc
    return Identity(org_id=org_id, actor_id=actor_id, source="dev_org_header")
