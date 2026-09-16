"""认证态解析（Sprint 1 临时实现）。

依据 `ADR-0003` §3.3：
- `org_id` **只能**来自认证态，**严禁**从请求 body / query 读取；
- Sprint 1 尚无 M5 `POST /auth/login`，因此提供两条**限期**兜底路径：
  1. `Bearer dev.<org_id>.<actor_id>` —— 无签名的开发态 token；
  2. `X-Org-Id` / `X-Actor-Id` 请求头 —— 仅 `ALLOW_DEV_ORG_HEADER=true` 且非生产时生效。
- **Sprint 3 必须替换为 M5 签发的 JWT 解析，并删除以上兜底。**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

IdentitySource = Literal["bearer_token", "dev_org_header"]

DEV_TOKEN_PREFIX = "dev"


@dataclass(frozen=True, slots=True)
class Identity:
    """当前请求的租户上下文。`org_id` 是后续所有查询的强制过滤键（ADR-0003）。"""

    org_id: UUID
    actor_id: UUID
    roles: tuple[str, ...] = field(default_factory=tuple)
    source: IdentitySource = "bearer_token"


def parse_bearer_token(raw_token: str, settings: Settings) -> Identity:
    """解析认证 token。

    Sprint 1 仅支持开发态格式 `dev.<org_id>.<actor_id>`；
    生产环境（或格式不匹配）一律 401，不提供任何绕过路径。
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

    raise AppError(
        ErrorCode.UNAUTHORIZED,
        "Unsupported bearer token",
        detail={
            "reason": "token_parser_not_available_in_sprint_1",
            "planned": "M5 POST /auth/login 签发 JWT 后由本函数解析（Sprint 3）",
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
