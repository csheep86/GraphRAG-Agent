"""权限服务域（DR-B9 / RBAC 三粒度）。

分层（改之前先看是哪一层，别把字典改到矩阵里去）：

- :mod:`app.services.rbac.roles` —— 角色**字典**（spec §4.2 的封闭四档）；
- :mod:`app.services.rbac.policy` —— **角色 × 资源 × 操作**矩阵 + 契约端点登记；
- :mod:`app.services.rbac.service` —— 判定（含文档 / 场景两粒度）与拒绝留痕；
- :mod:`app.services.rbac.deps` —— 路由层**强制校验入口**（G-24 判据的另一半）。
"""

from __future__ import annotations

from app.services.rbac.deps import require_permission
from app.services.rbac.service import (
    PERMISSION_DENIED_ACTION,
    build_permission_context,
    ensure_preset_roles,
    evaluate,
)

__all__ = [
    "PERMISSION_DENIED_ACTION",
    "build_permission_context",
    "ensure_preset_roles",
    "evaluate",
    "require_permission",
]
