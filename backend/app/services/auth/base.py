"""AuthProvider 接口（接缝 1，ADR-0004 §2.1 第 1 行）。

企业身份源（LDAP / OIDC / SAML）接入时新增实现类并在 ADR-0004 §2.1
扩写登记行；**当前登记集合恰好一个**：``LocalAuthProvider``（本地开发档，
包装现有 Bearer dev token / dev header 逻辑）。实现集合「不多不少」由
``scripts/check_seams.py`` 接缝 1 判据机械校验。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.auth import Identity
from app.core.config import Settings


class AuthProvider(ABC):
    """认证提供方抽象。"""

    @abstractmethod
    def authenticate(
        self,
        *,
        settings: Settings,
        bearer_token: str | None,
        org_id_header: str | None,
        actor_id_header: str | None,
    ) -> Identity | None:
        """解析当前请求身份。

        Returns:
            Identity: 认证成功；
            None: 本 provider 无法从给定输入解析出身份
            （由依赖层决定 401，避免 provider 越权决定错误响应形态）。
        """
