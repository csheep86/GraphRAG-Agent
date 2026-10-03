"""DR-B9 / G-24 行为侧：RBAC 三粒度**真的在拦**（不是"库里有两列"）。

分工：

- `tests/test_guardrails_compliance.py` 的 G-24 组只做**静态**判据
  （矩阵存在 + 强制校验入口存在 + `roles` 豁免合规）——按 P2-B 边界，
  它**不断言具体权限值**；
- 本文件补**行为**判据：同一端点换不同角色 / 不同范围 ⇒ 放行与拒绝**真的不同**，
  且拒绝**真的落审计**（M5 §3 验收 1）。

⚠️ 关键前提：conftest 给**默认 dev 主体**授了 `admin`（见
`rbac_default_actor_is_admin`），所以本文件的拒绝分支一律用**别的 actor id**
构造——用默认主体去测拒绝，测出来的会是 200。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog, Role, UserRole
from app.db.session import SessionLocal
from app.services.rbac.policy import (
    ACTION_READ,
    ACTION_WRITE,
    ACTIONS,
    CONTRACT_PATH_RESOURCE,
    RESOURCES,
    ROLE_PERMISSIONS,
)
from app.services.rbac.roles import PRESET_ROLES, ROLE_NAME_VALUES, RoleName
from app.services.rbac.service import (
    PERMISSION_DENIED_ACTION,
    REASON_ACTION_NOT_PERMITTED,
    REASON_DOCUMENT_NOT_IN_SCOPE,
    REASON_NO_ROLE,
    REASON_SCENE_NOT_IN_SCOPE,
    ensure_preset_roles,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"

#: 契约里**唯一**不登记资源的路径（探针，不承载业务对象）
HEALTH_PATH = "/api/v1/health"

#: **受 RBAC 强制校验的端点**（模块内相对路径；与路由声明逐字对应，
#: 新增 / 删除受保护端点必须同步这里）
PROTECTED_PATHS = {
    "/affiliation/detect",
    "/affiliation/suspicions/{suspicion_id}",
    "/audit",
    "/audit/trace/{trace_id}",
    "/documents",
    "/documents/upload",
    "/documents/{document_id}/chunks/{chunk_id}",
    "/documents/{document_id}/graph",
    "/documents/{document_id}/status",
    "/graph/versions/{version}/activate",
}


def _iter_api_routes(router):
    """摊平路由树，只吐 ``APIRoute``。

    FastAPI ≥ 0.141 的 ``include_router`` 会把子路由包成内部的 ``_IncludedRouter``，
    ``app.routes`` / ``api_router.routes`` 里**直接看不到** ``APIRoute``——
    所以这里递归进 ``original_router`` 取，而不是假设一层就能拿到。
    """
    for item in getattr(router, "routes", ()):
        if isinstance(item, APIRoute):
            yield item
        else:
            yield from _iter_api_routes(getattr(item, "original_router", item))


@pytest.fixture
def empty_audit() -> None:
    """清空 `audit_log`——否则"本次拒绝"的断言会被历史行污染。"""
    with SessionLocal() as session:
        session.query(AuditLog).delete()
        session.commit()


@pytest.fixture
def grant_role():
    """给指定 actor 授一个角色（用例结束清理**自己**建的那些行）。"""
    created: list[UUID] = []
    settings = get_settings()

    def _grant(*, actor: UUID, role: str, doc_scope=None, scene_scope=None) -> UserRole:
        with SessionLocal() as session:
            ensure_preset_roles(session)
            role_id = session.scalars(select(Role.id).where(Role.name == role)).one()
            row = UserRole(
                org_id=settings.default_org_id,
                user_id=actor,
                role_id=role_id,
                doc_scope=doc_scope,
                scene_scope=scene_scope,
                granted_by=settings.default_actor_id,
            )
            session.add(row)
            session.commit()
            created.append(row.id)
            return row

    yield _grant

    with SessionLocal() as session:
        session.query(UserRole).filter(UserRole.id.in_(created)).delete(
            synchronize_session=False
        )
        session.commit()


def _headers(actor: UUID) -> dict[str, str]:
    """以**指定 actor**、默认租户发起请求（默认 actor 是 admin，测拒绝不能用它）。"""
    return {
        "X-Org-Id": str(get_settings().default_org_id),
        "X-Actor-Id": str(actor),
    }


def _denied_rows(actor: UUID) -> list[AuditLog]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.actor_id == actor)
                .where(AuditLog.action == PERMISSION_DENIED_ACTION)
            ).all()
        )


# --------------------------------------------------------------------------- #
# 1) 资源清单：**只能**来自契约里已存在的端点
# --------------------------------------------------------------------------- #


def test_contract_paths_are_all_registered() -> None:
    """契约里的每条路径都必须登记资源（`/health` 除外），且**不许**登记契约外的路径。

    这条是「不得凭空造资源类型」的机械锁：加端点忘登记 ⇒ 红；
    登记了契约里没有的路径 ⇒ 红（防手写资源清单时顺手加一个）。
    """
    paths = set(yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"])
    registered = set(CONTRACT_PATH_RESOURCE)

    assert paths - {HEALTH_PATH} == registered, (
        "契约端点与资源登记不一致："
        f"契约有但未登记 {sorted(paths - {HEALTH_PATH} - registered)}；"
        f"登记了但契约没有 {sorted(registered - paths)}"
    )
    assert HEALTH_PATH not in registered, "`/health` 是探针，不承载业务资源"


def test_resources_are_exactly_the_registered_ones() -> None:
    assert RESOURCES == tuple(sorted(set(CONTRACT_PATH_RESOURCE.values())))


# --------------------------------------------------------------------------- #
# 2) 矩阵：形状完整（**不断言具体取值**——取值属实现决策）
# --------------------------------------------------------------------------- #


def test_matrix_covers_every_role_and_resource() -> None:
    """每个角色 × 每个资源都**显式**有格子（空集 = 刻意不给，与"忘了配"区分开）。"""
    assert set(ROLE_PERMISSIONS) == set(ROLE_NAME_VALUES), (
        "矩阵里的角色集合必须逐字等于 spec §4.2 的四档"
    )
    for role, per_resource in ROLE_PERMISSIONS.items():
        assert set(per_resource) == set(RESOURCES), (
            f"{role} 的资源覆盖不全：{sorted(set(RESOURCES) - set(per_resource))}"
        )
        for resource, actions in per_resource.items():
            assert actions <= set(ACTIONS), (
                f"{role}/{resource} 含未登记操作 {sorted(actions - set(ACTIONS))}"
            )


def test_preset_roles_match_the_role_enum() -> None:
    """库里播的 4 种角色 == 代码认的 4 种角色（改一端必须改另一端）。"""
    assert [name for name, _ in PRESET_ROLES] == list(ROLE_NAME_VALUES)
    assert set(ROLE_NAME_VALUES) == {str(role) for role in RoleName}


# --------------------------------------------------------------------------- #
# 3) 强制校验入口：真的挂在这些端点上
# --------------------------------------------------------------------------- #


def test_protected_routes_declare_the_enforcement_entry() -> None:
    """按**路由对象**核对：受保护端点集合必须逐字等于 :data:`PROTECTED_PATHS`。

    静态扫源码（G-24 那条）只能证明"存在一个入口"，证明不了"挂在了哪儿"——
    有人把 `dependencies=[...]` 从某个端点删掉，静态判据依旧绿。这条补上。
    """
    from app.api.v1.router import api_router

    enforced = {
        route.path
        for route in _iter_api_routes(api_router)
        if any(
            getattr(dep.call, "__name__", "") == "enforce_rbac"
            for dep in route.dependant.dependencies
        )
    }
    assert enforced == PROTECTED_PATHS, (
        f"受 RBAC 校验的端点与登记不一致：多 {sorted(enforced - PROTECTED_PATHS)}，"
        f"缺 {sorted(PROTECTED_PATHS - enforced)}"
    )


# --------------------------------------------------------------------------- #
# 4) 行为：拒绝 ⇒ 403 `FORBIDDEN` + `permission.denied` 留痕
# --------------------------------------------------------------------------- #


def test_denied_request_is_403_and_leaves_audit_trace(
    client: TestClient, grant_role, empty_audit: None
) -> None:
    """§3 验收 1：`viewer` 读审计 ⇒ 403 `FORBIDDEN` **且**写 `permission.denied`。

    **只返 403 不留痕 = 未完成**——所以这条同时断言两个半边。
    """
    actor = uuid4()
    grant_role(actor=actor, role=RoleName.VIEWER)

    response = client.get("/api/v1/audit", headers=_headers(actor))

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "FORBIDDEN"
    assert body["detail"]["reason"] == REASON_ACTION_NOT_PERMITTED

    rows = _denied_rows(actor)
    assert len(rows) == 1, "一次拒绝恰好写一条 permission.denied"
    assert rows[0].status == "failure"
    assert rows[0].resource == "audit:read"
    assert rows[0].detail["reason"] == REASON_ACTION_NOT_PERMITTED


def test_admin_actor_passes_the_same_endpoint(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """同一端点换 admin ⇒ 放行（证明上一条的 403 来自 RBAC，不是端点坏了）。"""
    assert client.get("/api/v1/audit", headers=dev_headers).status_code == 200


def test_unassigned_actor_is_denied_fail_closed(
    client: TestClient, empty_audit: None
) -> None:
    """**没有任何授权** ⇒ 拒绝（fail-closed）："没配"必须表现为打不开。"""
    actor = uuid4()

    response = client.get("/api/v1/audit", headers=_headers(actor))

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == REASON_NO_ROLE
    assert _denied_rows(actor)[0].detail["reason"] == REASON_NO_ROLE


def test_write_endpoint_discriminates_roles(
    client: TestClient, grant_role, empty_audit: None
) -> None:
    """写端点：`viewer` ⇒ 403；`analyst` ⇒ **不再**是 403（落到 404 业务分支）。"""
    viewer = uuid4()
    analyst = uuid4()
    grant_role(actor=viewer, role=RoleName.VIEWER)
    grant_role(actor=analyst, role=RoleName.ANALYST)

    unknown = f"/api/v1/affiliation/suspicions/{uuid4()}"

    denied = client.patch(
        unknown, json={"status": "confirmed"}, headers=_headers(viewer)
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["reason"] == REASON_ACTION_NOT_PERMITTED

    allowed = client.patch(
        unknown, json={"status": "confirmed"}, headers=_headers(analyst)
    )
    assert allowed.status_code == 404, "过了 RBAC 就该进业务分支（疑点不存在 → 404）"


# --------------------------------------------------------------------------- #
# 5) 第二 / 第三粒度：场景与文档
# --------------------------------------------------------------------------- #


def test_scene_scope_narrows_affiliation_access(
    client: TestClient, grant_role, empty_audit: None
) -> None:
    """`analyst` 有 affiliation 写权限，但**场景范围不含它** ⇒ 仍被拒。"""
    wrong_scene = uuid4()
    right_scene = uuid4()
    grant_role(actor=wrong_scene, role=RoleName.ANALYST, scene_scope=["qa"])
    grant_role(actor=right_scene, role=RoleName.ANALYST, scene_scope=["affiliation"])

    unknown = f"/api/v1/affiliation/suspicions/{uuid4()}"

    denied = client.patch(
        unknown, json={"status": "confirmed"}, headers=_headers(wrong_scene)
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["reason"] == REASON_SCENE_NOT_IN_SCOPE

    allowed = client.patch(
        unknown, json={"status": "confirmed"}, headers=_headers(right_scene)
    )
    assert allowed.status_code == 404


def test_document_scope_narrows_document_access(
    client: TestClient, grant_role, empty_audit: None
) -> None:
    """`viewer` 有 document 读权限，但**文档范围不含该文档** ⇒ 被拒。"""
    in_scope = uuid4()
    out_of_scope = uuid4()
    actor = uuid4()
    grant_role(
        actor=actor, role=RoleName.VIEWER, doc_scope={"doc_ids": [str(in_scope)]}
    )

    denied = client.get(
        f"/api/v1/documents/{out_of_scope}/status", headers=_headers(actor)
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["reason"] == REASON_DOCUMENT_NOT_IN_SCOPE

    allowed = client.get(
        f"/api/v1/documents/{in_scope}/status", headers=_headers(actor)
    )
    assert allowed.status_code == 404, "范围命中 ⇒ 进业务分支（文档不存在 → 404）"


def test_audit_entry_is_written_for_scope_denials_too(
    client: TestClient, grant_role, empty_audit: None
) -> None:
    """场景 / 文档级拒绝**同样**留痕——§3 验收 1 没说"只有角色级拒绝才留"。"""
    actor = uuid4()
    grant_role(actor=actor, role=RoleName.VIEWER, doc_scope={"doc_ids": []})

    client.get(f"/api/v1/documents/{uuid4()}/status", headers=_headers(actor))

    rows = _denied_rows(actor)
    assert len(rows) == 1
    assert rows[0].detail["reason"] == REASON_DOCUMENT_NOT_IN_SCOPE
    assert rows[0].resource == "document:read"


def test_enforcement_uses_read_and_write_only() -> None:
    """操作只有 `read` / `write` 两档——多一档就得先改 spec 与矩阵。"""
    assert set(ACTIONS) == {ACTION_READ, ACTION_WRITE}


# --------------------------------------------------------------------------- #
# 6) 迁移：PG 上真跑（DR-E1：可幂等 + 禁手工改客户库）
# --------------------------------------------------------------------------- #

_ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
#: 本批之前的 head（P2-A）
_PREV_REVISION = "a1f3c9d27b08"


def test_migration_seeds_preset_roles_and_is_replayable() -> None:
    """在临时 PG 库上真跑迁移：建表 + 播 4 种预置角色 + 退一步 + 重放。

    为什么单独验「退一步 + 重放」：`tests/test_migrations_baseline.py` 只验了
    ``downgrade base``（退到零），而**现场回滚是退一步**；不重放就不能叫幂等。
    """
    from alembic import command
    from alembic.config import Config
    from pg_scratch import database_url_for, scratch_database
    from sqlalchemy import create_engine, inspect, text

    def _cfg(url: str) -> Config:
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", url)
        return cfg

    with scratch_database("graphrag_rbac") as name:
        url = database_url_for(name)
        cfg = _cfg(url)
        engine = create_engine(url)
        try:
            command.upgrade(cfg, "head")

            with engine.connect() as connection:
                names = {
                    row[0] for row in connection.execute(text("SELECT name FROM roles"))
                }
            assert names == {name for name, _ in PRESET_ROLES}, (
                f"迁移播的角色与 PRESET_ROLES 不一致：{names}"
            )

            command.downgrade(cfg, _PREV_REVISION)
            after_down = set(inspect(engine).get_table_names())
            assert not {"roles", "user_roles"} & after_down, "退一步后两张表仍在"

            command.upgrade(cfg, "head")
            command.upgrade(cfg, "head")  # 重放：幂等，不得报 already exists
            after_up = set(inspect(engine).get_table_names())
            assert {"roles", "user_roles"} <= after_up

            with engine.connect() as connection:
                count = connection.execute(
                    text("SELECT COUNT(*) FROM roles")
                ).scalar_one()
            assert count == len(PRESET_ROLES), "重放不得把预置角色插重"
        finally:
            engine.dispose()
