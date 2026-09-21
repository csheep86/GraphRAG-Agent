"""认证服务域（接缝 1：AuthProvider 抽象 + LocalAuthProvider 实现）。"""

from __future__ import annotations

from app.services.auth.base import AuthProvider
from app.services.auth.local import LocalAuthProvider, get_auth_provider

__all__ = ["AuthProvider", "LocalAuthProvider", "get_auth_provider"]
