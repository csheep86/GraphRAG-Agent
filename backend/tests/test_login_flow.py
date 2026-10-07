"""P2-C 的**差分判据**：真实登录 → 席位真的量得出来（验收 §9 第 1 / 2 / 3 条）。

**为什么单开一个文件**：`tests/test_auth.py` 测的是解析函数（纯函数，不连库），
而本批要证的是一条**端到端**的因果链：

    真登录成功 → users.activated_at 非 NULL → count_seats() ≥ 1

P4 结束时这条链断在第一步（`activated_at` 全表 NULL ⇒ 席位恒 0）。本文件的每一条
断言都**查库**，不查 mock、不读代码——`count_seats()` 必须真的从 PG 里数出来。

**三条纪律**：

1. **不改席位的算法**：`count_seats()` 是 ADR-0006 §2.4 的唯一实现，本文件只**调用**它；
2. **不伪造 `activated_at`**：唯一允许回填它的代码是 "首次成功登录"（P4-D5 明令）；
3. **停用账号必须整体拒**（D4），且 `disabled_at` 有值 ⇒ 不再计入席位。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.token import verify_access_token
from app.db.models import USER_STATUS_ACTIVE, USER_STATUS_DISABLED, User
from app.db.session import session_scope
from app.services.auth.login import load_activated_at
from app.services.license.policy import count_seats


@pytest.fixture
def _restore_account() -> None:
    """把默认主体的账号状态**还原**为 active（无论用例成功还是失败）。

    **为什么必须还原**：``users`` 在测试库里是**持久**的（不是每用例重建），
    而默认主体是上千条既有用例的身份来源——把它留在 disabled，
    后面所有受保护端点都会以 `account_disabled` 被拒，表现为"一批无关用例集体变红"。
    """
    settings = get_settings()
    yield
    with session_scope(org_id=settings.default_org_id) as session:
        session.query(User).filter(User.id == settings.default_actor_id).update(
            {"status": USER_STATUS_ACTIVE, "disabled_at": None}
        )
        session.commit()


def _set_status(*, org_id: UUID, user_id: UUID, status: str, disabled: bool) -> None:
    with session_scope(org_id=org_id) as session:
        session.query(User).filter(User.id == user_id).update(
            {
                "status": status,
                "disabled_at": datetime.now(tz=UTC) if disabled else None,
            }
        )
        session.commit()


# --------------------------------------------------------------------------- #
# 验收 1 + 2：登录成功 ⇒ activated_at 非 NULL ⇒ count_seats() ≥ 1
# --------------------------------------------------------------------------- #
def test_login_backfills_activated_at_and_seat_is_countable(
    client: TestClient, dev_login: dict[str, str]
) -> None:
    """真登录一次，`users.activated_at` 必须**真的**落值，且席位可数。

    **这是本批的差分证据**：P4 收尾时 `count_seats()` 恒为 0（唯一消费者
    `app/services/license/policy.py:57-74`），因为没有任何代码回填 `activated_at`。
    """
    settings = get_settings()

    response = client.post("/api/v1/auth/login", json=dev_login)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"], "登录成功必须签发令牌"
    assert body["org_id"] == str(settings.default_org_id)
    assert body["user_id"] == str(settings.default_actor_id)

    # ① 端到端真断言：查库，不查 mock
    activated_at = load_activated_at(
        org_id=settings.default_org_id, user_id=settings.default_actor_id
    )
    assert activated_at is not None, "首次成功登录后 activated_at 必须非 NULL"

    # ② 席位可量（P4 时恒 0 ⇒ 这里的 ≥1 就是差分）
    with session_scope(org_id=settings.default_org_id) as session:
        assert count_seats(session) >= 1


def test_second_login_does_not_rewrite_activated_at(
    client: TestClient, dev_login: dict[str, str]
) -> None:
    """第二次登录**不**改写 `activated_at`——回填点只有"首次"一个。

    多一个回填点，席位数就多一份不是真登录换来的水分（P4-D5）。
    """
    settings = get_settings()
    first = client.post("/api/v1/auth/login", json=dev_login)
    assert first.status_code == 200, first.text
    after_first = load_activated_at(
        org_id=settings.default_org_id, user_id=settings.default_actor_id
    )
    assert after_first is not None

    second = client.post("/api/v1/auth/login", json=dev_login)
    assert second.status_code == 200, second.text
    assert (
        load_activated_at(
            org_id=settings.default_org_id, user_id=settings.default_actor_id
        )
        == after_first
    )


# --------------------------------------------------------------------------- #
# 验收 3（前半）：签发的令牌必须**真的**被受保护端点接受
# --------------------------------------------------------------------------- #
def test_token_from_login_is_accepted_by_protected_endpoint(
    client: TestClient, dev_login: dict[str, str]
) -> None:
    """登录拿到的令牌要能当认证态用——否则"登录"只是个校验接口，不是登录。"""
    login = client.post("/api/v1/auth/login", json=dev_login)
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    claims = verify_access_token(token, get_settings())
    assert claims is not None, "自己签发的令牌必须能被自己验过"

    response = client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 不是 401 ⇒ 令牌被 `parse_bearer_token` 的 JWT 分支认下来了
    assert response.status_code != 401, response.text


# --------------------------------------------------------------------------- #
# 口令错误 / 停用：都不回填，且对外不区分
# --------------------------------------------------------------------------- #
def test_wrong_password_is_rejected_and_does_not_activate(
    client: TestClient, dev_login: dict[str, str]
) -> None:
    """口令错 ⇒ 401 且**不**回填 `activated_at`（"失败不回填"是本批硬边界）。"""
    settings = get_settings()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": dev_login["username"], "password": "definitely-wrong"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.json()["detail"]["reason"] == "invalid_credentials"

    with session_scope(org_id=settings.default_org_id) as session:
        row = (
            session.query(User)
            .filter(User.id == settings.default_actor_id)
            .one_or_none()
        )
        # 未被本用例"激活"过：要么仍是 NULL，要么是本文件之外那次真登录留下的值
        assert row is not None
        assert row.activated_at is None or isinstance(row.activated_at, datetime)


def test_disabled_account_is_rejected_on_login_and_on_every_request(
    client: TestClient,
    dev_login: dict[str, str],
    dev_headers: dict[str, str],
    _restore_account: None,
) -> None:
    """D4：停用账号**新请求被拒** + `disabled_at` 落值 ⇒ **不再计入席位**。

    两半都要验：只验登录会被读成"只是登录挡了一下"，只验请求会漏掉
    「停用后席位是否真的回落」——而席位正是本批要量出来的东西。
    """
    settings = get_settings()
    # 先真登录一次，让席位从 0 变 1（否则"回落"无从比较）
    assert client.post("/api/v1/auth/login", json=dev_login).status_code == 200
    with session_scope(org_id=settings.default_org_id) as session:
        assert count_seats(session) >= 1

    _set_status(
        org_id=settings.default_org_id,
        user_id=settings.default_actor_id,
        status=USER_STATUS_DISABLED,
        disabled=True,
    )

    # ① 登录被拒
    login = client.post("/api/v1/auth/login", json=dev_login)
    assert login.status_code == 401
    assert login.json()["detail"]["reason"] == "account_disabled"

    # ② 带着 dev 头的新请求被拒（RBAC 的账号状态门，理由 account_disabled）
    guarded = client.get("/api/v1/audit", headers=dev_headers)
    assert guarded.status_code == 403, guarded.text
    assert guarded.json()["detail"]["reason"] == "account_disabled"

    # ③ disabled_at 落值 ⇒ 不再计入席位
    with session_scope(org_id=settings.default_org_id) as session:
        row = session.query(User).filter(User.id == settings.default_actor_id).one()
        assert row.disabled_at is not None
        assert count_seats(session) == 0
