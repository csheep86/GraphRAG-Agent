"""LocalAuthProvider（接缝 1 唯一登记实现，Sprint 5 批次 A2）。

包装 ``app.core.auth`` 现有 dev token / dev header 校验逻辑——
批次 A2 的收口动作是「加一层接口」，**不改动任何校验语义**；
``users`` 表按 T10 裁决不建。
"""

from __future__ import annotations

from app.core.auth import Identity, identity_from_dev_headers, parse_bearer_token
from app.core.config import Settings
from app.services.auth.base import AuthProvider


class LocalAuthProvider(AuthProvider):
    """本地开发档认证：Bearer dev token > dev header（优先级同 core.auth）。"""

    def authenticate(
        self,
        *,
        settings: Settings,
        bearer_token: str | None,
        org_id_header: str | None,
        actor_id_header: str | None,
    ) -> Identity | None:
        if bearer_token:
            return parse_bearer_token(bearer_token, settings)
        return identity_from_dev_headers(
            settings=settings,
            org_id_header=org_id_header,
            actor_id_header=actor_id_header,
        )


def get_auth_provider() -> AuthProvider:
    """返回当前认证提供方（接缝 1 工厂）。

    企业身份源接入时按 ADR-0004 §2.1 登记行扩展（先扩写 ADR、再改工厂，
    漏改任一侧 CI 必红）。
    """
    return LocalAuthProvider()


__all__ = ["LocalAuthProvider", "get_auth_provider"]
