"""给 **dev 主体**播一份 `admin` 授权（P2-B 收尾项，实测驱动）。

用法（工作目录 = `backend/`）：

    uv run python scripts/seed_dev_rbac.py           # 播种（幂等，可重复跑）
    uv run python scripts/seed_dev_rbac.py --check   # 只报告当前状态，不写

**为什么需要它**（实测证据见 `changes/P2/probe_rbac_dev_actor.py`）：

P2-B 给 10 个端点挂上了 RBAC 强制校验，而测试库那份 admin 授权是由
**conftest 夹具**播的、**只落在 `graphrag_test`**。演示库 `graphrag` 里的
`user_roles` 是空的 ⇒ dev 主体一上来就 `403 no_role_assignment`
（三个端点实测全 403）⇒ **演示直接打不开**。

**它的作用域被两道锁钉死，不是"后门"**：

1. **`ALLOW_DEV_ORG_HEADER` 必须为 `true`** 才允许执行，否则直接拒绝退出（非 0）。
   dev token / dev header 本来就是 dev 逃生口，本脚本是它的**配套**；
   生产环境关掉该开关 ⇒ 本脚本自动不可用 ⇒ 生产库不会因此多出授权记录。
2. **只授默认 org**（`DEFAULT_ORG_ID`）。演示场景只有一个租户；
   测试库需要的"跨租户 org 也授权"由 `tests/conftest.py` 的夹具负责，
   **两者互不复用**——把测试脚手架搬进产品脚本是最容易埋雷的动作。

**不做什么**：

- **不播 `user_roles` 到迁移里** —— 迁移会跑到客户库，那是真的编造授权数据（**红线**）；
- 不写任何业务数据，只写 `roles`（4 种预置）+ 一条 `(org, user, admin)` 授权；
- 不修改矩阵、不绕过校验——校验照常执行，这里只补「这个主体是谁」。

真实账号与授权管理界面归 **P2-C**；在那之前，本脚本是"让演示能打开"的最小手段。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import Role, UserRole  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.rbac.roles import PRESET_ROLES, RoleName  # noqa: E402
from app.services.rbac.service import ensure_preset_roles  # noqa: E402


def _report(session, org_id, actor_id) -> bool:
    """打印当前状态；返回「dev 主体是否已有 admin 授权」。"""
    roles = session.scalars(select(Role.name).order_by(Role.name)).all()
    grants = session.scalars(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.org_id == org_id)
        .where(UserRole.user_id == actor_id)
    ).all()
    print(
        f"roles            = {len(roles)} 种 {list(roles)}（预置 {len(PRESET_ROLES)} 种）"
    )
    print(f"dev 主体已有授权 = {list(grants)}")
    return str(RoleName.ADMIN) in {str(name) for name in grants}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check_only = "--check" in argv
    settings = get_settings()

    print(f"DATABASE_URL         = {settings.database_url}")
    print(f"ALLOW_DEV_ORG_HEADER = {settings.allow_dev_org_header}")

    if not settings.allow_dev_org_header:
        print(
            "[NG] 拒绝执行：`ALLOW_DEV_ORG_HEADER` 未开启。\n"
            "     本脚本只服务于 dev token / dev header 这条 dev 逃生口；\n"
            "     生产环境该开关本就应为 false —— 若确需，请先确认你在做什么。"
        )
        return 1

    init_db()
    org_id = settings.default_org_id
    actor_id = settings.default_actor_id
    print(f"org_id               = {org_id}")
    print(f"actor_id             = {actor_id}")

    # A4：脚本没有请求身份 ⇒ org 只能显式给（本脚本只授默认 org）
    with open_session(org_id=org_id) as session:
        already = _report(session, org_id, actor_id)
        if check_only:
            print("\n[--] --check 模式：未写入")
            return 0 if already else 1

        ensure_preset_roles(session)
        role_id = session.scalars(
            select(Role.id).where(Role.name == str(RoleName.ADMIN))
        ).one()
        exists = (
            session.scalars(
                select(UserRole.id)
                .where(UserRole.org_id == org_id)
                .where(UserRole.user_id == actor_id)
                .where(UserRole.role_id == role_id)
            ).first()
            is not None
        )
        if exists:
            session.commit()
            print("\n[OK] 已存在，未重复插入（幂等）")
            return 0

        session.add(
            UserRole(
                org_id=org_id,
                user_id=actor_id,
                role_id=role_id,
                doc_scope=None,
                scene_scope=None,
                granted_by=actor_id,
            )
        )
        session.commit()
        print("\n[OK] 已给 dev 主体授 admin（默认 org）")
        _report(session, org_id, actor_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
