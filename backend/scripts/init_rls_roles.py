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
    """授权：连接库 / schema / 现有表 / owner 未来建的表。"""
    return (
        f"GRANT CONNECT ON DATABASE {database} TO {OWNER_ROLE}, {APP_ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        # owner 之后新建的表**自动**带上授权：漏了这条，下次加表 app_rls 立刻看不见
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
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
    try:
        with admin_engine.begin() as connection:
            for statement in _role_statements():
                connection.execute(text(statement))
            # A6 / A7 的受控系统函数（含 BYPASSRLS 属主角色 rls_probe）
            for statement in system_function_statements():
                connection.execute(text(statement))
            for statement in _grant_statements(database):
                connection.execute(text(statement))
            # 既有表的属主统一归 owner：否则迁移（以 owner 跑）改不动超级用户的表
            # tenant_tables() 只含「有 org_id」的表；字典表（roles）同样要归 owner
            tables = sorted(Base.metadata.tables)
            existing = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            for table in sorted(set(tables) & existing):
                connection.execute(
                    text(f"ALTER TABLE public.{table} OWNER TO {OWNER_ROLE}")
                )
    finally:
        admin_engine.dispose()

    owner_engine = create_engine(owner_url)
    try:
        with owner_engine.begin() as connection:
            if args.create_tables:
                Base.metadata.create_all(bind=connection)
            applied = apply_tenant_rls(connection)
            ensure_exempt_tables_unprotected(connection)
    finally:
        owner_engine.dispose()

    print(f"[OK] 角色：{OWNER_ROLE}（owner）/ {APP_ROLE}（受限，NOBYPASSRLS）")
    print(
        f"[OK] 受控系统函数属主：{PROBE_ROLE}（NOLOGIN + BYPASSRLS，唯一 bypass 口子）"
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
