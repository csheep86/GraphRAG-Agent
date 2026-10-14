#!/usr/bin/env python3
"""建 RLS 角色 / 受控系统函数，并把**建表交给 Alembic 迁移**（DR-B4 / ADR-0003 §3.2）。

**为什么必须单独一个脚本**：RLS 的前提是「应用账号**不是**表 owner、没有
``BYPASSRLS``」（ADR-0003 §3.2 要求 2），而这个前提**只能由超级用户**一次性
建立——应用自己建不出来（也不该建得出来）。本脚本就是这个「一次性」动作：

1. 建 **owner**（``app_owner``：建表 / 跑迁移，仍受 FORCE RLS 约束）；
2. 建 **受限业务角色**（``app_rls``：``NOBYPASSRLS``，应用与业务测试用它连库）；
3. **以 owner 跑 ``alembic upgrade head``** —— 交付形态**唯一**的建表途径；
4. 建 A6 / A7 的**受控系统函数**（属主 ``rls_probe``：``NOLOGIN`` + ``BYPASSRLS``）；
5. 把业务表的 CURD 授权给 ``app_rls``，并对 owner 设 ``DEFAULT PRIVILEGES``。

> RLS 策略**由迁移**落（``8210590e76a5`` / ``b7c4e1f9a2d3`` …），本脚本只**校验**
> 不落（理由见 :func:`_assert_policies_present`）。

**P7-Q（2026-10-14）：为什么不再用 ``create_all`` 建交付库**（F-P7H-1）
此前首次部署由 ``--create-tables``（``Base.metadata.create_all``）建表，且**从不 stamp**
⇒ 客户按 `docs/deployment-spec.md` §7.2 升级时，``alembic upgrade head`` 在**第一个**
迁移就撞 ``DuplicateTable``（实测把版本号拨到哪一段都会撞）⇒ **升级路径是断的**。
根因不是某条迁移写错，而是 ``create_all`` 与 Alembic 是**两套并行**的建表机制，
混用必断（v1.6.0 → 1.7.0 之间新增 9 个迁移 / 761 行）。
⇒ 交付形态改为只走迁移；``--create-tables`` 保留给 dev / 测试兜底，**交付编排禁止使用**。

**遗留库（无 ``alembic_version`` 但表已存在）怎么归位**：那是旧版 ``create_all`` 建的库。
此类库**跑不了**那批"追平模型"的迁移（它们要建的表 / 列库里早就有了）⇒
先**机械比对**库 schema 与 ``Base.metadata``：一致 ⇒ ``alembic stamp head``
（一次性归位，此后迁移照常真跑）；不一致 ⇒ **报错退出**并列出差异。
绝不把一个已经漂移的库"stamp 成 head"当作修好了。

用法
----
    # 交付形态（compose 的 db-init 就是这么跑的）：迁移建表 / 升级
    uv run python scripts/init_rls_roles.py \
        --admin-url postgresql+psycopg://graphrag:<pwd>@postgres:5432/graphrag \
        --run-migrations

    # dev / 测试兜底：create_all（交付编排禁止）
    uv run python scripts/init_rls_roles.py --admin-url <superuser-url> --create-tables

    # CI / 本地：只建角色与受控函数，**不碰 schema**
    # （业务测试库由 conftest 自建表 + 自落策略）
    uv run python scripts/init_rls_roles.py \
        --admin-url postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test

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
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:  # 允许以脚本方式直接跑
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import Base  # noqa: E402
from app.db.rls import (  # noqa: E402
    APP_ROLE,
    OWNER_ROLE,
    POLICY_NAME,
    PROBE_ROLE,
    apply_tenant_rls,
    ensure_exempt_tables_unprotected,
    system_function_statements,
    tenant_tables,
)

# Windows 控制台默认 GBK：打印非 ASCII 会抛 UnicodeEncodeError ⇒ 强制 stdio 为 UTF-8。
# 内联而非抽公共模块：脚本被测试按文件路径 import 时 scripts/ 不在 sys.path 上
# ⇒ 公共模块本身会 ImportError（兜底反成新崩溃源）；漏加由门禁测试拦。
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_OWNER_PASSWORD = "app_owner"
DEFAULT_APP_PASSWORD = "app_rls"

#: 迁移配置（与 ``tests/test_migrations_baseline.py`` 同一真源：镜像里已 COPY）
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _alembic_config(url: str) -> Config:
    """⚠️ ``%`` 必须转义：``ConfigParser`` 走 BasicInterpolation，口令里一个裸
    ``%`` 会让 ``set_main_option`` 直接抛 ``ValueError: invalid interpolation
    syntax``（2026-10-14 实测）⇒ 交付现场一个带 ``%`` 的口令会当场打断部署。"""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _upgrade_head(url: str) -> None:
    """建表 / 升级——**唯一**的 schema 演进途径（P7-Q / F-P7H-1）。"""
    command.upgrade(_alembic_config(url), "head")


def _stamp_head(url: str) -> None:
    """遗留库一次性归位。**只在** :func:`_schema_gaps` 比对通过后才可调。"""
    command.stamp(_alembic_config(url), "head")


def _stamped_revision(connection: Any) -> str | None:
    """当前 ``alembic_version``；连这张表都没有 ⇒ ``None``（从未跑过迁移）。

    用 ``to_regclass`` 而不是查 ``pg_tables``：前者对"不存在"返回 NULL，
    不需要先假定表在（本脚本恰恰要区分"有没有"）。
    """
    if (
        connection.execute(
            text("SELECT to_regclass('public.alembic_version')")
        ).scalar()
        is None
    ):
        return None
    return str(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    )


def _public_tables(connection: Any) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    } - {"alembic_version"}


def _schema_gaps(engine: Any) -> tuple[set[str], dict[str, tuple[set[str], set[str]]]]:
    """库 schema 相对 ``Base.metadata`` **缺什么**（**多**出来的不算缺口）。

    只看"缺"是刻意的：库里多一张表 / 多一列（例如跑过更新版代码）**不影响**
    "把版本号归位到 head"这个动作的正确性；而"缺"意味着有迁移**必须**真跑
    ⇒ 那种情况下 stamp 会静默吞掉一条迁移，属伪造历史。
    """
    inspector = inspect(engine)
    existing = set(inspector.get_table_names()) - {"alembic_version"}
    missing_tables = set(Base.metadata.tables) - existing
    missing_columns: dict[str, tuple[set[str], set[str]]] = {}
    for table in sorted(set(Base.metadata.tables) & existing):
        in_db = {col["name"] for col in inspector.get_columns(table)}
        in_metadata = {column.name for column in Base.metadata.tables[table].columns}
        if not in_metadata <= in_db:
            missing_columns[table] = (in_metadata - in_db, in_db - in_metadata)
    return missing_tables, missing_columns


def _ensure_schema_via_migrations(engine: Any, owner_url: str) -> str:
    """交付形态的建表 / 升级入口；返回一段人类可读的动作说明（进部署日志）。

    三种初始状态，三种处置（**顺序即判定顺序**，别调换）：

    1. **已 stamp** ⇒ 真跑 ``upgrade head``（正常升级路径）；
    2. **空库** ⇒ 真跑 ``upgrade head``（首次部署：表由迁移建，不再是 create_all）；
    3. **有表但未 stamp**（旧版 ``create_all`` 的库）⇒ 先比对，一致才 stamp。
    """
    with engine.begin() as connection:
        revision = _stamped_revision(connection)
        tables = _public_tables(connection)

    if revision is not None:
        print(f"[INFO] 迁移：当前 {revision} ⇒ alembic upgrade head")
        _upgrade_head(owner_url)
        return f"upgrade head：{revision} → head（迁移真跑）"

    if not tables:
        print("[INFO] 空库 ⇒ 由迁移建表（首次部署；建表只此一条路）")
        _upgrade_head(owner_url)
        return "空库：由迁移建表（14 个迁移真跑）"

    missing_tables, missing_columns = _schema_gaps(engine)
    if missing_tables or missing_columns:
        detail = "\n".join(
            [
                *(f"  - 缺表 {name}" for name in sorted(missing_tables)),
                *(
                    f"  - 表 {name} 缺列 {sorted(missing)}"
                    for name, (missing, _extra) in missing_columns.items()
                ),
            ]
        )
        raise RuntimeError(
            "遗留库（无 alembic_version 但表已存在）与当前模型**不等价** ⇒ "
            "不敢 stamp（那会把「缺表 / 缺列」伪造成为已迁移）。差异：\n"
            f"{detail}\n"
            "处置：先把库补到与模型一致（或按"
            " changes/P7-Q/proposal.md §5 第 2 条另立批次补迁移），再重跑本脚本。"
        )
    print(
        "[WARN] 遗留库（无 alembic_version 但表已存在）⇒ 与当前模型等价，"
        "stamp head 一次性归位（这些迁移是追平模型的，跑不动）"
    )
    _stamp_head(owner_url)
    return "遗留库：比对通过 ⇒ stamp head（未真跑迁移，原因见上）"


def _assert_policies_present(engine: Any) -> tuple[str, ...]:
    """策略**由迁移**落 ⇒ 本脚本只**校验**不落（P7-Q）。

    为什么不顺手落一遍（此前是落的）：策略一旦被"当前代码版本"重述，库里的
    策略就**不再对应任何一条迁移**——而回滚只改 tag，旧镜像的 db-init 会把
    新库的策略改回旧口径。⇒ 迁移是唯一落点，这里只负责把「漏了策略」
    从**零症状**（RLS 失效不会报错）变成**部署期硬失败**。
    """
    tables = tuple(tenant_tables())
    with engine.begin() as connection:
        forced = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "JOIN pg_namespace ON pg_namespace.oid = relnamespace "
                    "WHERE nspname = 'public' "
                    "  AND relrowsecurity AND relforcerowsecurity"
                )
            )
        }
        with_policy = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT tablename FROM pg_policies "
                    "WHERE schemaname = 'public' AND policyname = :policy"
                ),
                {"policy": POLICY_NAME},
            )
        }
    broken = sorted(set(tables) - (forced & with_policy))
    if broken:
        raise RuntimeError(
            f"迁移跑完仍有 {len(broken)} 张租户表没有 {POLICY_NAME} 策略 / 未 ENABLE+FORCE："
            f"{broken} ⇒ **跨租户可见且不会有任何报错**。"
            "新增带 org_id 的表必须同时补 RLS 迁移（G-26 判据盯住清单漂移）"
        )
    return tables


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
        help="顺带以 owner 身份跑 create_all（**dev / 测试兜底；交付编排禁止**）",
    )
    parser.add_argument(
        "--run-migrations",
        action="store_true",
        help="以 owner 跑 alembic upgrade head（交付形态**唯一**的建表途径）",
    )
    parser.add_argument(
        "--owner-url",
        default=None,
        help="owner 连接串；缺省由 --admin-url 换用户名/口令推导",
    )
    args = parser.parse_args(argv)
    if args.create_tables and args.run_migrations:
        parser.error(
            "--create-tables 与 --run-migrations 互斥：它们正是 F-P7H-1 的那两套"
            "并行建表机制，同一次部署里只能走一条"
        )

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
    schema_note = "跳过（未指定建表方式 ⇒ 只建角色 / 受控函数 / 授权）"
    applied: tuple[str, ...] = ()
    try:
        # --- 阶段 1（**超级用户**）：角色 + 不依赖表的授权 ----------------------
        with admin_engine.begin() as connection:
            for statement in _role_statements():
                connection.execute(text(statement))
            for statement in _grant_statements(database):
                connection.execute(text(statement))

        # --- 阶段 2（**owner**）：建表 —— 只认显式指定的那一条途径 -----------
        # ⚠️ **顺序不能反**（2026-10-04 实测踩到）：受控函数体引用了 ``documents`` /
        # ``affiliation_tasks``，而 PG 在 ``CREATE FUNCTION`` / ``GRANT`` 时就会
        # **解析到真实的表** ⇒ 空库上先建函数 / 授权会直接 ``UndefinedTable``，
        # 整个 init 失败（部署与 CI 两边都是"空库先跑 init"）。
        #
        # ⚠️ **不再有「空库就自动 create_all」**（P7-Q / F-P7H-1）：那条隐式分支
        # 正是"交付库由 create_all 建、却从不 stamp"的成因 ⇒ 客户升级时
        # `alembic upgrade head` 第一个迁移就撞 DuplicateTable。现在建表**只能**
        # 显式指定：交付形态 `--run-migrations`，dev 兜底 `--create-tables`。
        # 两条途径**都必须在阶段 3 之前**完成：阶段 3 里有
        # ``GRANT SELECT ON public.documents TO rls_probe``——它要解析到**真实的表**
        # （``check_function_bodies = off`` 只豁免函数体，不豁免 GRANT）
        # ⇒ 空库上先跑阶段 3 会直接 ``UndefinedTable``。
        if args.create_tables:
            with owner_engine.begin() as connection:
                Base.metadata.create_all(bind=connection)
                # dev 库从不跑迁移 ⇒ 策略只能在这里落（交付形态由迁移落）
                applied = apply_tenant_rls(connection)
                ensure_exempt_tables_unprotected(connection)
            schema_note = "create_all（dev / 测试兜底；交付编排禁止）"
        elif args.run_migrations:
            schema_note = _ensure_schema_via_migrations(owner_engine, owner_url)
            # 策略由迁移落 ⇒ 这里只校验齐备（见 :func:`_assert_policies_present`）
            applied = _assert_policies_present(owner_engine)

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

    finally:
        admin_engine.dispose()
        owner_engine.dispose()

    print(f"[OK] 角色：{OWNER_ROLE}（owner）/ {APP_ROLE}（受限，NOBYPASSRLS）")
    print(
        f"[OK] 受控系统函数属主：{PROBE_ROLE}（NOLOGIN + BYPASSRLS，唯一 bypass 口子）"
    )
    print(f"[INFO] 建表 / 升级：{schema_note}")
    if applied:
        print(
            f"[OK] {len(applied)} 张租户表的 {POLICY_NAME} 策略已就位（ENABLE+FORCE）："
        )
        for table in applied:
            print(f"       - {table}")
    else:
        print(
            "[INFO] 未触碰 schema ⇒ 不校验策略（业务测试库由 conftest 自建表 + 自落策略）"
        )
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
