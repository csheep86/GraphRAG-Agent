#!/usr/bin/env python3
"""建 RLS 角色 / 受控系统函数 / 落策略（DR-B4 / ADR-0003 §3.2）。

**为什么必须单独一个脚本**：RLS 的前提是「应用账号**不是**表 owner、没有
``BYPASSRLS``」（ADR-0003 §3.2 要求 2），而这个前提**只能由超级用户**一次性
建立——应用自己建不出来（也不该建得出来）。本脚本就是这个「一次性」动作：

1. 建 **owner**（``app_owner``：建表 / 跑迁移，仍受 FORCE RLS 约束）；
2. 建 **受限业务角色**（``app_rls``：``NOBYPASSRLS``，应用与业务测试用它连库）；
3. 建 A6 / A7 的**受控系统函数**（属主 ``rls_probe``：``NOLOGIN`` + ``BYPASSRLS``）；
4. 把业务表的 CURD 授权给 ``app_rls``，并对 owner 设 ``DEFAULT PRIVILEGES``；
5. 对每张租户表落 ``ENABLE`` / ``FORCE`` / 策略（幂等，可重复跑）。

用法
----
    # 超级用户连串（CI / 本地）
    uv run python scripts/init_rls_roles.py \
        --admin-url postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test

    # 顺带建表（开发库第一次初始化时）
    uv run python scripts/init_rls_roles.py --admin-url <superuser-url> --create-tables

口令
----
``APP_OWNER_PASSWORD`` / ``APP_RLS_PASSWORD`` 环境变量覆盖；默认口令仅供
**本地与 CI**（测试库）。生产必须经 Secrets / KMS 注入（CODEBUDDY.md 密钥管理规则）。

退出码
------
0 = 成功；非 0 = 失败（连不上 / 权限不足会原样抛错，不静默降级）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:  # 允许以脚本方式直接跑
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import Base  # noqa: E402
from app.db.rls import (  # noqa: E402
    APP_ROLE,
    OWNER_ROLE,
    PROBE_ROLE,
    apply_tenant_rls,
    ensure_exempt_tables_unprotected,
    system_function_statements,
)

DEFAULT_OWNER_PASSWORD = "app_owner"
DEFAULT_APP_PASSWORD = "app_rls"


def _role_statements() -> tuple[str, ...]:
    """建两个业务角色（幂等）。"""
    owner_password = os.environ.get("APP_OWNER_PASSWORD", DEFAULT_OWNER_PASSWORD)
    app_password = os.environ.get("APP_RLS_PASSWORD", DEFAULT_APP_PASSWORD)
    common = "NOSUPERUSER NOCREATEROLE NOBYPASSRLS"
    return (
        f"DO $$ BEGIN\n"
        f"    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{OWNER_ROLE}') THEN\n"
        f"        CREATE ROLE {OWNER_ROLE} LOGIN PASSWORD '{owner_password}' "
        f"{common} CREATEDB;\n"
        f"    ELSE\n"
        f"        ALTER ROLE {OWNER_ROLE} LOGIN PASSWORD '{owner_password}' "
        f"{common} CREATEDB;\n"
        f"    END IF;\n"
        f"END $$;",
        # ⚠️ app_rls **必须** NOBYPASSRLS：否则 RLS 对它形同虚设（G-26 判据 4）
        f"DO $$ BEGIN\n"
        f"    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN\n"
        f"        CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{app_password}' "
        f"{common} NOCREATEDB;\n"
        f"    ELSE\n"
        f"        ALTER ROLE {APP_ROLE} LOGIN PASSWORD '{app_password}' "
        f"{common} NOCREATEDB;\n"
        f"    END IF;\n"
        f"END $$;",
    )


def _grant_statements(database: str) -> tuple[str, ...]:
    """**不依赖表是否存在**的授权：连接库 / schema / owner 未来建的表。"""
    return (
        f"GRANT CONNECT ON DATABASE {database} TO {OWNER_ROLE}, {APP_ROLE}",
        # ⚠️ owner 还须能在 public 里**建表**：PG 15 起 public schema 不再对
        # PUBLIC 开放 CREATE，而 owner 通常**不是**库属主（库是超级用户建的）
        # ⇒ 少了这条，空库首次建表时 owner 直接 `permission denied`。
        f"GRANT CREATE, USAGE ON SCHEMA public TO {OWNER_ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        # owner 之后新建的表**自动**带上授权：漏了这条，下次加表 app_rls 立刻看不见
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
    )


def _table_grant_statements() -> tuple[str, ...]:
    """**表已存在之后**才能给的授权（``ALL TABLES IN SCHEMA`` 只对现有表生效）。"""
    return (
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-url",
        required=True,
        help="超级用户连接串（建角色 / 建受控函数需要它）",
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="顺带以 owner 身份跑 create_all（开发库首次初始化用）",
    )
    parser.add_argument(
        "--owner-url",
        default=None,
        help="owner 连接串；缺省由 --admin-url 换用户名/口令推导",
    )
    args = parser.parse_args(argv)

    admin_url = make_url(args.admin_url)
    database = admin_url.database or "postgres"
    owner_url = args.owner_url
    if owner_url is None:
        password = os.environ.get("APP_OWNER_PASSWORD", DEFAULT_OWNER_PASSWORD)
        owner_url = admin_url.set(
            username=OWNER_ROLE, password=password
        ).render_as_string(hide_password=False)

    admin_engine = create_engine(admin_url.render_as_string(hide_password=False))
    owner_engine = create_engine(owner_url)
    created_tables = False
    try:
        # --- 阶段 1（**超级用户**）：角色 + 不依赖表的授权 ----------------------
        with admin_engine.begin() as connection:
            for statement in _role_statements():
                connection.execute(text(statement))
            for statement in _grant_statements(database):
                connection.execute(text(statement))

        # --- 阶段 2（**owner**）：空库 ⇒ 先建表 --------------------------------
        # ⚠️ **顺序不能反**（2026-10-04 实测踩到）：受控函数体引用了 ``documents`` /
        # ``affiliation_tasks``，而 PG 在 ``CREATE FUNCTION`` / ``GRANT`` 时就会
        # **解析到真实的表** ⇒ 空库上先建函数 / 授权会直接 ``UndefinedTable``，
        # 整个 init 失败（部署与 CI 两边都是"空库先跑 init"）。
        with owner_engine.begin() as connection:
            existing = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            if args.create_tables or not existing:
                Base.metadata.create_all(bind=connection)
                created_tables = True

        # --- 阶段 3（**超级用户**）：受控函数 + 表级授权 + 属主归并 ------------
        with admin_engine.begin() as connection:
            # 见阶段 2 的说明：函数体引用的表可能尚未存在（元数据与库不一致时），
            # 关掉建函数时的表名校验；函数**调用**时表必须存在，那是另一回事。
            connection.execute(text("SET LOCAL check_function_bodies = off"))
            # A6 / A7 的受控系统函数（含 BYPASSRLS 属主角色 rls_probe）
            for statement in system_function_statements():
                connection.execute(text(statement))
            for statement in _table_grant_statements():
                connection.execute(text(statement))
            # 既有表的属主统一归 owner：否则迁移（以 owner 跑）改不动超级用户的表
            # tenant_tables() 只含「有 org_id」的表；字典表（roles）同样要归 owner
            existing = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            for table in sorted(set(Base.metadata.tables) & existing):
                connection.execute(
                    text(f"ALTER TABLE public.{table} OWNER TO {OWNER_ROLE}")
                )

        # --- 阶段 4（**owner**）：落策略 ---------------------------------------
        with owner_engine.begin() as connection:
            applied = apply_tenant_rls(connection)
            ensure_exempt_tables_unprotected(connection)
    finally:
        admin_engine.dispose()
        owner_engine.dispose()

    print(f"[OK] 角色：{OWNER_ROLE}（owner）/ {APP_ROLE}（受限，NOBYPASSRLS）")
    print(
        f"[OK] 受控系统函数属主：{PROBE_ROLE}（NOLOGIN + BYPASSRLS，唯一 bypass 口子）"
    )
    print(
        f"[INFO] 建表：{'已执行（空库或带 --create-tables）' if created_tables else '跳过（表已存在）'}"
    )
    print(f"[OK] 已对 {len(applied)} 张租户表落 ENABLE + FORCE + 策略：")
    for table in applied:
        print(f"       - {table}")
    print("[HINT] 应用侧连接串请用受限角色：")
    print(
        "       DATABASE_URL="
        + admin_url.set(
            username=APP_ROLE,
            password=os.environ.get("APP_RLS_PASSWORD", DEFAULT_APP_PASSWORD),
        ).render_as_string(hide_password=False)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
