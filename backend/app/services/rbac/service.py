"""RBAC 判定与审计落痕（DR-B9 / `specs/m5-permission-audit.md` §3 验收 1）。

三粒度在这里合流：

- **角色**：``user_roles.role_id → roles.name``；
- **文档**：``user_roles.doc_scope = {"doc_ids": [...], "tags": [...]}``；
- **场景**：``user_roles.scene_scope = ["affiliation", "qa", ...]``。

**默认 fail-closed**：查不到任何授权 ⇒ 拒绝（``no_role_assignment``）。
「没配权限」必须表现为**打不开**，而不是"反正库里没数据就放行"——后者一旦
有数据就是静默越权（与 `agent_fail_closed` 同一条纪律，见 DR-B12 / G-17）。

**拒绝必须留痕**（§3 验收 1 的显式要求）：本模块是
`app/services/audit.py` 登记集合里的**第 4 个**写入方，写
``action = permission.denied``。只返 403 不留痕 = 未完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.models import Role, UserRole
from app.services.audit import record_audit_entry
from app.services.rbac.policy import allowed_actions, scene_of
from app.services.rbac.roles import PRESET_ROLES

#: 拒绝时写入 `audit_log.action` 的值（spec §3 验收 1 原文）
PERMISSION_DENIED_ACTION = "permission.denied"

#: 拒绝原因（``detail.reason``）。按 **角色 → 资源 × 操作 → 场景 → 文档** 的次序判定，
#: 第一个命中的原因即拒绝原因（``resource`` 与 ``action`` 的取值来自路由层声明）。
REASON_NO_ROLE = "no_role_assignment"
REASON_ACTION_NOT_PERMITTED = "action_not_permitted"
REASON_SCENE_NOT_IN_SCOPE = "scene_not_in_scope"
REASON_DOCUMENT_NOT_IN_SCOPE = "document_not_in_scope"

_DENIAL_MESSAGES: dict[str, str] = {
    REASON_NO_ROLE: "当前主体在本租户内没有任何角色授权",
    REASON_ACTION_NOT_PERMITTED: "当前角色在该资源上没有该操作的权限",
    REASON_SCENE_NOT_IN_SCOPE: "授权的场景范围不含本次请求的场景",
    REASON_DOCUMENT_NOT_IN_SCOPE: "授权的文档范围不含本次请求的文档",
}


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """一条授权记录（`user_roles` 的一行 + 角色名）。"""

    role: str
    doc_scope: dict | None
    scene_scope: list | None


@dataclass(frozen=True, slots=True)
class PermissionContext:
    """一次请求的权限上下文（由 :func:`build_permission_context` 从库里读出）。

    ``doc_scope`` / ``scene_scope`` 为 ``None`` 表示**不限**（授权未收窄）；
    空元组表示"明确限定为零个"——本模块的合并语义里不会出现后者
    （任一授权不限即整体不限，见 :func:`_merge_scope`）。
    """

    roles: tuple[str, ...]
    doc_scope: tuple[str, ...] | None
    scene_scope: tuple[str, ...] | None


def ensure_preset_roles(session: Session) -> int:
    """补齐 spec §4.2 的 4 种系统预置角色（**幂等**：已存在的不覆盖）。

    ``roles`` 是**全局字典表**，系统没有它就谈不上授权；测试环境走 ``create_all``
    （不执行迁移），所以播种逻辑必须**在应用侧**有一份，不能只写在迁移里。
    """
    existing = set(session.scalars(select(Role.name)).all())
    added = 0
    for name, description in PRESET_ROLES:
        if name in existing:
            continue
        session.add(Role(name=name, description=description))
        added += 1
    if added:
        session.commit()
    return added


def load_role_grants(
    session: Session, *, org_id: UUID, user_id: UUID
) -> tuple[RoleGrant, ...]:
    """读出该主体**在本租户内**的全部授权（跨租户授权记录**永不**被读到）。

    ``org_id`` 来自认证态（ADR-0003 §3.3），不来自请求参数。
    """
    rows = session.execute(
        select(UserRole, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.org_id == org_id)
        .where(UserRole.user_id == user_id)
    ).all()
    return tuple(
        RoleGrant(role=name, doc_scope=row.doc_scope, scene_scope=row.scene_scope)
        for row, name in rows
    )


def build_permission_context(
    session: Session, *, org_id: UUID, user_id: UUID
) -> PermissionContext:
    """把授权记录折叠成一次请求可用的权限上下文（多角色**取并集**）。"""
    grants = load_role_grants(session, org_id=org_id, user_id=user_id)
    return PermissionContext(
        roles=tuple(sorted({grant.role for grant in grants})),
        doc_scope=_merge_scope([_doc_scope_of(grant) for grant in grants]),
        scene_scope=_merge_scope([grant.scene_scope for grant in grants]),
    )


def evaluate(
    context: PermissionContext,
    *,
    resource: str,
    action: str,
    scene: str | None = None,
    document_id: UUID | None = None,
) -> str | None:
    """判定是否放行。返回 ``None`` = 放行；否则返回 :data:`REASON_*` 之一。

    次序是刻意的：**先判有没有主体（角色），再判资源 × 操作，最后收窄到场景 / 文档**——
    先判细粒度会得到「你有这个文档的权限但没有角色」这种无法解释的拒绝原因。
    """
    if not context.roles:
        return REASON_NO_ROLE

    permitted: set[str] = set()
    for role in context.roles:
        permitted |= allowed_actions(role, resource)
    if action not in permitted:
        return REASON_ACTION_NOT_PERMITTED

    resolved_scene = scene if scene is not None else scene_of(resource)
    if (
        resolved_scene is not None
        and context.scene_scope is not None
        and resolved_scene not in context.scene_scope
    ):
        return REASON_SCENE_NOT_IN_SCOPE

    if (
        document_id is not None
        and context.doc_scope is not None
        and str(document_id) not in context.doc_scope
    ):
        return REASON_DOCUMENT_NOT_IN_SCOPE

    return None


def permission_denied_error(
    *, resource: str, action: str, reason: str, roles: tuple[str, ...]
) -> AppError:
    """构造 403 `FORBIDDEN`（**复用契约里已有的错误码**，不新增）。"""
    return AppError(
        ErrorCode.FORBIDDEN,
        _DENIAL_MESSAGES.get(reason, "Permission denied"),
        detail={
            "resource": resource,
            "action": action,
            "reason": reason,
            "roles": list(roles),
        },
    )


def record_permission_denied(
    session: Session,
    *,
    org_id: UUID,
    actor_id: UUID | None,
    resource: str,
    action: str,
    reason: str,
    trace_id: UUID | str,
    actor_ip: str | None = None,
    method: str = "",
    path: str = "",
) -> bool:
    """拒绝时写一条 `audit_log(action=permission.denied)`（§3 验收 1 的另一半）。

    **写失败只记日志、不抛异常**（审计纪律：审计缺陷不得变成全站 500）。
    返回是否入 session 成功。
    """
    try:
        ok = record_audit_entry(
            session,
            org_id=org_id,
            action=PERMISSION_DENIED_ACTION,
            actor_id=actor_id,
            actor_ip=actor_ip,
            resource=f"{resource}:{action}",
            status="failure",
            trace_id=trace_id,
            # 只写结构化字段，绝不写响应体 / 请求体原文（决策 **A5** 同口径）
            detail={
                "reason": reason,
                "status_code": 403,
                "method": method,
                "path": path,
            },
        )
        # 本写入点没有业务事务可依附（拒绝发生在路由体之前），必须显式提交，
        # 否则会话关闭时这条审计会被回滚掉——**留痕变没痕**正是 §3 验收 1 要防的。
        session.commit()
    except Exception as exc:  # noqa: BLE001 - 审计写失败绝不上抛
        logger.bind(resource=resource, action=action, reason=str(exc)).warning(
            "permission_denied_audit_write_failed"
        )
        return False
    return ok


def _doc_scope_of(grant: RoleGrant) -> list | None:
    """取授权的文档范围（``doc_scope.doc_ids``）。

    ``None`` = 该授权**未收窄**（不限）；空列表 = **明确限定为零个文档**
    （与"不限"语义相反，不许合并成一个意思——那会让「授权为零」退化成「全放开」）。
    """
    if not isinstance(grant.doc_scope, dict):
        return None
    doc_ids = grant.doc_scope.get("doc_ids")
    return doc_ids if isinstance(doc_ids, list) else None


def _merge_scope(values: list[list | None]) -> tuple[str, ...] | None:
    """多角色授权**取并集**；**任一授权不限 ⇒ 整体不限**（权限是加法，不是交集）。

    返回 ``None`` 表示不限；返回空元组表示"并集为零"（每个授权都限定成零个）。
    """
    if not values:
        return None
    merged: set[str] = set()
    for value in values:
        if value is None:
            return None
        merged.update(str(item) for item in value)
    return tuple(sorted(merged))


__all__ = [
    "PERMISSION_DENIED_ACTION",
    "REASON_ACTION_NOT_PERMITTED",
    "REASON_DOCUMENT_NOT_IN_SCOPE",
    "REASON_NO_ROLE",
    "REASON_SCENE_NOT_IN_SCOPE",
    "PermissionContext",
    "RoleGrant",
    "build_permission_context",
    "ensure_preset_roles",
    "evaluate",
    "load_role_grants",
    "permission_denied_error",
    "record_permission_denied",
]
