"""交付首账号开户命令（F-P7N-2，方案 (a)）的机械保障。

只钉**最危险的两条**，不为凑数写：

1. **幂等**：重跑**不得**改掉已经存在的口令 —— 这条最容易出事，因为它读起来
   像"再跑一次开户"，实际后果是**把客户正在用的口令换掉**（而客户那边没人知道）；
2. **席位不足 ⇒ 拒绝**：开户是唯一会消耗 License 席位的动作
   （``license/policy.py`` 维度 2），超限必须是**拒新增**，而不是照建不误。

其余（建号成功 / 授 admin / 能登录）由集成日志里的真跑读数承担：那些需要起后端，
放到单测里反而会把"开户"和"登录端点"两件事耦成一个用例。
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load(name: str, path: Path):
    """按需加载 CLI 脚本（``scripts/`` 不是包，与既有做法一致）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PROVISION = _load("provision_admin", BACKEND_ROOT / "scripts" / "provision_admin.py")

from app.core.config import get_settings  # noqa: E402
from app.db.models import User, UserRole  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402


def _hash_of(session, username: str) -> str | None:
    user = session.scalars(select(User).where(User.username == username)).first()
    return None if user is None else str(user.password_hash)


def _remove(session, username: str) -> None:
    """删掉探测账号（连同授权），不留残渣给后面的用例。"""
    user = session.scalars(select(User).where(User.username == username)).first()
    if user is None:
        return
    session.query(UserRole).filter(UserRole.user_id == user.id).delete()
    session.delete(user)
    session.commit()


@pytest.fixture
def probe_username() -> str:
    return f"provision-probe-{uuid.uuid4().hex[:10]}"


def test_rerun_never_changes_an_existing_password(probe_username: str) -> None:
    """**本批最要紧的一条**：重跑开户 ≠ 换口令。

    给了 ``--reset-password`` 才允许改 —— 那是"我知道我在做什么"的显式声明。
    """
    settings = get_settings()
    init_db()
    org_id = settings.default_org_id

    with open_session(org_id=org_id) as session:
        try:
            assert (
                PROVISION.main(
                    ["--username", probe_username, "--password", "first-pass"]
                )
                == 0
            )
            first_hash = _hash_of(session, probe_username)
            assert first_hash, "开户后应能查到 password_hash"

            # 重跑：显式给了**另一个**口令，但没有 --reset-password ⇒ 不得改动
            assert (
                PROVISION.main(
                    ["--username", probe_username, "--password", "second-pass"]
                )
                == 0
            )
            assert _hash_of(session, probe_username) == first_hash, (
                "重跑把口令改掉了 ⇒ 客户会在不知情的情况下被登出"
            )

            # 给了 --reset-password 才允许改
            assert (
                PROVISION.main(
                    [
                        "--username",
                        probe_username,
                        "--password",
                        "third-pass",
                        "--reset-password",
                    ]
                )
                == 0
            )
            assert _hash_of(session, probe_username) != first_hash
        finally:
            _remove(session, probe_username)


def test_seat_limit_refuses_to_create(
    probe_username: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """席位不足 ⇒ **拒绝新建**（"卡增量、保存量"），且不许留下半个用户。"""
    monkeypatch.setattr(PROVISION, "is_seat_available", lambda *_a, **_k: False)

    settings = get_settings()
    init_db()
    org_id = settings.default_org_id

    with open_session(org_id=org_id) as session:
        try:
            assert (
                PROVISION.main(["--username", probe_username, "--password", "whatever"])
                == 1
            )
            assert _hash_of(session, probe_username) is None
        finally:
            _remove(session, probe_username)
