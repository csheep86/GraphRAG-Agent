#!/usr/bin/env python3
"""交付环境**首账号**开户（F-P7N-2，P7-N 方案 **(a)**）。

**为什么单独一个脚本，而不是复用 `seed_dev_rbac.py`**：后者是 **dev 逃生口**的播种
脚本 —— 它要求 `ALLOW_DEV_ORG_HEADER`（生产本就该为 false，见 P7-C 护栏 G-27），
且只认默认 actor（`install_acceptance.py:538` 明写"只播 dev 默认 org"）
⇒ 交付包里放它既不安全也说不通。

**为什么是"人跑的一次性命令"，而不是安装器里的一步**（方案 (a) 的原文）：
首账号决定的是「**谁能登录客户的生产系统**」，它必须由**人**发起并保管口令；
把它塞进无人值守的安装流程，等于让一个自动化步骤决定这件事。
⇒ 本脚本**刻意不猜测口令**：要么人给（`--password`），要么显式要求生成（`--generate`）。

**为什么要在开户时卡 License 席位**：开户是唯一会消耗席位的动作
（`license/policy.py` 维度 2：席位 = 已激活且未停用的用户）。
纪律是「**卡增量、保存量**」（`policy.py` 模块 docstring）：超限只**拒新增**，
绝不把已有的数据锁死 —— 所以这里超限是拒绝新建，不是锁库。

用法
----
    # 口令由人在现场给（脚本**不回显**）
    uv run python scripts/provision_admin.py --username admin --password <口令>

    # 生成随机口令（**只打印一次**，请当场保存并登录后修改）
    uv run python scripts/provision_admin.py --username admin --generate

    # 已存在时重置口令（**默认不重置** ⇒ 幂等：重跑不会把别人的口令改掉）
    uv run python scripts/provision_admin.py --username admin --password <新> --reset-password

    # 只看看现在有没有这个账号（不写库）
    uv run python scripts/provision_admin.py --username admin --check

退出码
------
0 = 已就绪（新建成功，或已存在且未改动）／1 = 环境不允许开户（License 席位不足等）／2 = 参数不对
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import Role, User, UserRole  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.auth.password import hash_password  # noqa: E402
from app.services.license.policy import is_seat_available  # noqa: E402
from app.services.license.provider import get_license_provider  # noqa: E402
from app.services.rbac.roles import RoleName  # noqa: E402
from app.services.rbac.service import ensure_preset_roles  # noqa: E402

# Windows 控制台默认 GBK：打印非 ASCII 会抛 UnicodeEncodeError ⇒ 强制 stdio 为 UTF-8
# （与 seed_dev_rbac.py 同款；内联而非抽公共模块的原因见那里的注释）。
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _find_user(session, username: str):  # noqa: ANN001 - Session 类型由调用方保证
    """按用户名找（RLS 下自然只查得到本租户的）。"""
    return session.scalars(select(User).where(User.username == username)).first()


def _grant_admin(  # noqa: ANN001
    session, *, org_id: UUID, user_id: UUID
) -> bool:
    """确保该用户有 admin 授权；返回「本次是否新插入」。

    首个用户没有上级 ⇒ ``granted_by`` 取**自己**（与 ``seed_dev_rbac.py`` 的处理一致）。
    """
    ensure_preset_roles(session)
    role_id = session.scalars(
        select(Role.id).where(Role.name == str(RoleName.ADMIN))
    ).one()
    exists = (
        session.scalars(
            select(UserRole.id)
            .where(UserRole.org_id == org_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.role_id == role_id)
        ).first()
        is not None
    )
    if exists:
        return False
    session.add(
        UserRole(
            org_id=org_id,
            user_id=user_id,
            role_id=role_id,
            doc_scope=None,
            scene_scope=None,
            granted_by=user_id,
        )
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="交付环境首账号开户（幂等；一次性命令）"
    )
    parser.add_argument("--username", required=True, help="登录用户名")
    parser.add_argument("--password", help="口令（与 --generate 二选一）")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="生成随机口令并**只打印一次**（请当场保存）",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="用户已存在时也重置口令（默认不重置 ⇒ 幂等）",
    )
    parser.add_argument("--check", action="store_true", help="只检查是否存在，不写库")
    parser.add_argument(
        "--org-id",
        help="租户 id（默认 settings.default_org_id；一家一套部署就是它）",
    )
    args = parser.parse_args(argv)

    if args.check and (args.password or args.generate or args.reset_password):
        print("--check 与建号/改口令参数互斥（--check 不写库）", file=sys.stderr)
        return 2
    if not args.check and not (args.password or args.generate):
        print("必须给 --password 或 --generate：口令不由脚本猜", file=sys.stderr)
        return 2
    if args.password and args.generate:
        print("--password 与 --generate 二选一", file=sys.stderr)
        return 2

    settings = get_settings()
    org_id = UUID(args.org_id) if args.org_id else settings.default_org_id
    init_db()

    with open_session(org_id=org_id) as session:
        existing = _find_user(session, args.username)

        if args.check:
            if existing is None:
                print(f"[NG] 用户 {args.username} 不存在（org={org_id}）")
                return 1
            print(f"[OK] 用户 {args.username} 已存在：id={existing.id}")
            return 0

        if existing is not None and not args.reset_password:
            # 幂等分支：重跑**不改口令**（否则一次手滑就把客户的口令换了）。
            # 但授权要补齐 —— 本脚本的语义是"确保存在一个能登录的管理员"。
            granted = _grant_admin(session, org_id=org_id, user_id=existing.id)
            session.commit()
            print(f"[OK] 用户 {args.username} 已存在 ⇒ 未改动（重跑不会改口令）")
            print(f"     admin 授权：{'本次补上' if granted else '已存在'}")
            return 0

        # 席位校验：**只在真的要新建/启用时卡**（"卡增量、保存量"）。
        state = get_license_provider().current_state()
        if not is_seat_available(session, state):
            print(
                "[NG] 拒绝开户：License 席位不足或无有效 License"
                f"（has_license={state.has_license}, max_seats={state.max_seats}）\n"
                "     ⇒ 先装 License / 确认 max_seats > 0 再开户；"
                "已存在的数据不受影响（超限只卡新增）",
                file=sys.stderr,
            )
            return 1

        password = args.password or secrets.token_urlsafe(24)

        if existing is not None:
            existing.password_hash = hash_password(password)
            session.flush()
            user_id = existing.id
            action = "已重置口令"
        else:
            user = User(
                username=args.username,
                # 复用 `hash_password`：口令实现只允许有一处，漂移过一次
                # （`seed_dev_rbac.py` 踩过），这里不再抄第二份。
                password_hash=hash_password(password),
                org_id=org_id,
                status="active",
            )
            session.add(user)
            session.flush()
            user_id = user.id
            action = "已创建"

        granted = _grant_admin(session, org_id=org_id, user_id=user_id)
        session.commit()

    print(f"[OK] {action}用户 {args.username}（org={org_id}, id={user_id}）")
    print(f"     admin 授权：{'已授予' if granted else '已存在'}")
    if args.generate:
        print(
            f"\n[!] 生成的口令（**只出现这一次**，请当场保存并登录后修改）：\n"
            f"    {password}"
        )
    else:
        # 显式给的口令**不回显**（它可能正被别人看着、也可能进了 shell history）
        print("     口令已按你给的值设置（不回显）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
