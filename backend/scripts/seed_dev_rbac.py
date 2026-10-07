"""给 **dev 主体**播一份 `admin` 授权（P2-B 收尾项，实测驱动）。

用法（工作目录 = `backend/`）：

    uv run python scripts/seed_dev_rbac.py           # 播种（幂等，可重复跑）
    uv run python scripts/seed_dev_rbac.py --check   # 只报告当前状态，不写
    uv run python scripts/seed_dev_rbac.py --password=<dev 口令>  # 显式给定口令

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

**2026-10-06 追加（P6-P1 / R29）：顺带补上「主体锚点」** —— `users` 此前是 0 行，
而 `user_roles.user_id` / `documents.uploaded_by` / `audit_log.actor_id` **全都指向它**
⇒ 那三条 seed 出来的授权其实是**挂在库里不存在的人身上**（真机：孤儿 2/2、36/36、2/2）。
本脚本原先只补"授权"，现在先补"被授权的人"：**以 `DEFAULT_ACTOR_ID` 为主键插一行 `users`**，
于是既有数据一行都不用改就全部脱孤。

⚠️ **它不代表账号体系落地**：`app/` 下**仍无一处 `select(User)`**（`users` 依旧 **0 真实读者**）；
本脚本在 `scripts/` 下，**不需要**登记进 `USERS_CONSUMER_MODULES`（那条闸门只盯 `app/`）。

**2026-10-07 追加（P2-C）**：口令哈希的实现已**上移**到 `app/services/auth/password.py`
（`hash_password` / `verify_password`）——登录上线后它就是校验方，两份实现必然漂移，
故本脚本只保留调用。串格式与迭代数**未变**（既有那一行哈希无需重算）。
`--password` 显式给的口令自此可被 `POST /auth/login` 真校验；缺省仍是随机值且**不打印**。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import Role, User, UserRole  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.auth.password import hash_password  # noqa: E402
from app.services.rbac.roles import PRESET_ROLES, RoleName  # noqa: E402
from app.services.rbac.service import ensure_preset_roles  # noqa: E402


def _user_exists(session, actor_id) -> bool:
    """dev 主体在 `users` 里有没有锚点行（RLS 下自然只查得到本租户的）。"""
    return (
        session.scalars(select(User.id).where(User.id == actor_id)).first() is not None
    )


def _ensure_dev_user(session, org_id, actor_id, password: str | None) -> bool:
    """确保 dev 主体在 `users` 里有**一行**（幂等）；返回「是否已存在」。

    主键**刻意取 `DEFAULT_ACTOR_ID`**：既有 `user_roles` / `documents` / 审计里那个 actor_id
    恒为这个值 ⇒ 锚点对上后，**改业务代码这一步全省了**（改了反而会造出第一批需要回填的新数据）。
    """
    username = f"dev-{actor_id}"
    if _user_exists(session, actor_id):
        return True
    session.add(
        User(
            id=actor_id,
            username=username,
            # 不传口令 ⇒ 随机串（**不打印**）：不打印的那条照样登不进来，
            # 打印出来也只是制造一条需要保管的秘密。P2-C 起 ``--password`` 给的口令可被
            # `POST /auth/login` 真校验（哈希算法与格式见 app/services/auth/password.py）。
            password_hash=hash_password(password or secrets.token_urlsafe(24)),
            org_id=org_id,
            status="active",
        )
    )
    session.flush()
    print(f"[OK] 已插入 users 锚点：username={username} / org={org_id}")
    return False


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
    # 显式给口令（缺省 ⇒ 随机值且**不打印**；当前无校验方，登录归 P2-C）
    password = next(
        (arg.split("=", 1)[1] for arg in argv if arg.startswith("--password=")),
        None,
    )
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
        has_user = _user_exists(session, actor_id)
        print(f"dev 主体 users 锚点 = {'已存在' if has_user else '缺失（待补）'}")
        if check_only:
            print("\n[--] --check 模式：未写入")
            # P6-P1：主体锚点与授权**两者齐全**才算 dev 逃生口可用
            return 0 if (already and has_user) else 1

        # P6-P1 / R29：**先有被授权的人**（没有这一步，授权挂在库里不存在的主体上）
        _ensure_dev_user(session, org_id, actor_id, password)
        session.commit()

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
