"""角色字典（DR-B9 / `specs/m5-permission-audit.md` §4.2）。

**角色集合是封闭的**：``admin / auditor / analyst / viewer`` 四档，逐字取自 spec §4.2。
P2-B 边界明确写了「**不得新增**角色名」——要加第五个角色，顺序是
**先改 spec §4.2 → 再改本文件与 `app/db/models.py::ROLE_NAME_VALUES`**，
最后由 G-24 的机械断言复核（模型层的 ``ck_roles_name`` 也会在 DB 侧拦住）。

本模块只放**字典**，不放权限矩阵（矩阵在 :mod:`app.services.rbac.policy`）——
两者分开是因为变更频率不同：角色名几乎不动，权限矩阵会随端点增删反复调。
"""

from __future__ import annotations

from enum import StrEnum


class RoleName(StrEnum):
    """系统预置角色（spec §4.2 的封闭集合）。"""

    ADMIN = "admin"
    AUDITOR = "auditor"
    ANALYST = "analyst"
    VIEWER = "viewer"


#: 与 :class:`RoleName` 同源的字符串元组（`app/db/models.py::ROLE_NAME_VALUES` 的镜像，
#: 用于迁移播种与断言；两处由 `tests/test_guardrails_compliance.py` 的 G-24 组核对）
ROLE_NAME_VALUES: tuple[str, ...] = tuple(RoleName)

#: 预置角色的说明（``(name, description)``）。迁移播种与测试夹具共用，
#: 保证「库里的角色」与「代码认的角色」永远同一套。
PRESET_ROLES: tuple[tuple[str, str], ...] = (
    ("admin", "系统管理员：全部资源的读与写（含授权、kg_version 激活）"),
    ("auditor", "审计员：只读，且覆盖审计 / 合规 / 疑点等需要留痕的对象"),
    ("analyst", "分析师：业务读 + 文档上传、疑点复核等写操作"),
    ("viewer", "观察者：最小只读集（文档 / 图谱 / 问答 / 合规）"),
)


__all__ = ["PRESET_ROLES", "ROLE_NAME_VALUES", "RoleName"]
