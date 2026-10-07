"""RLS（行级安全）：租户表清单、策略 DDL 与受控系统函数（DR-B4 / ADR-0003 §3.2）。

**为什么单独一个模块**：RLS 的落点有三处（Alembic 迁移 / 测试建库 / 运维脚本），
三处各写一份 DDL 必然漂移——而漂移的表现是「某张表忘了建策略 ⇒ 整表跨租户可见」，
且**不会有任何报错**（需求基线 §226 第 1 条）。故 DDL 只在这里生成。

**表清单不手工抄**：:data:`TENANT_TABLES` 由 ``Base.metadata`` 推导——带
``org_id`` 列且不在 :data:`RLS_EXEMPT_TABLES` 里的表即为租户表。新增一张带
``org_id`` 的表 ⇒ 它**自动**进入清单（漏建策略会立即被 G-26 判红）。

**三条硬约束**（ADR-0003 §3.2 / §3.3）：

1. ``ENABLE`` **且** ``FORCE``：不 ``FORCE`` 则表 owner 绕过策略 ⇒ RLS 形同虚设；
2. 策略表达式不得为 ``USING (true)``（那是「假装有隔离」，比没有更危险）；
3. 未设 ``app.current_org`` ⇒ 比较为 NULL ⇒ **一行都查不到**（fail-closed）。
      ⚠️ **"未设"有两种形态，两种都必须退化为 NULL**（2026-10-04 P3-C 实测修正）：
      - 从未设置过 ⇒ ``current_setting(..., true)`` 返回 **NULL**；
      - **跑过一次 ``SET LOCAL`` 之后** ⇒ 事务结束时自定义 GUC 被还原到 **reset 值**，
        那是**空串 ``''``**（不是"未设置"）。若谓词直接 ``::uuid``，空串会抛
        ``22P02 invalid input syntax for type uuid: ""`` ⇒ **500**，且只在"该连接跑过
        一次绑 org 的事务之后"才出现（首次正常、第二次起崩）。
      故谓词用 ``nullif(..., '')`` 把**两者统一**成 NULL。**不要**改回裸 ``::uuid``。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import RLS_EXEMPT_TABLES, Base

#: 事务级 GUC 名（ADR-0003 §3.2 要求 3：必须 ``SET LOCAL``，即事务作用域）
ORG_GUC = "app.current_org"

#: 策略名。所有租户表**同名**，便于机械核对「每张表都建了」
POLICY_NAME = "tenant_isolation"

#: A7 受控存在性探测的**表白名单**。
#:
#: 为什么需要这条旁路：契约 ``openapi.yaml`` 明文要求跨租户 = **403 而非 404**
#: （2026-10-04 裁决 1），服务层必须能区分「不存在」与「存在但不属于本租户」。
#: RLS 生效后应用账号看不到别租户的行 ⇒ 该判定只能走一条**受控**通道。
#:
#: 约束（每条均由 G-26 独立断言）：
#:   - 只返回 boolean，**不返回** ``org_id`` 或任何行数据；
#:   - 表白名单（防被当成任意表的 bypass）；
#:   - ``SECURITY DEFINER`` + 收紧 ``search_path``。
#: 表白名单由**契约**决定（不是随手扩）：RLS 生效前，服务层曾用「不带 org 的
#: 存在性查询」区分 404 / 403；RLS 生效后这条查询恒为空 ⇒ 只能走本通道。
#: 逐条依据：
#:   - ``documents``          —— openapi.yaml:2867 / 3121（文档详情、状态）
#:   - ``affiliation_tasks``  —— openapi.yaml:3193（任务详情）
#:   - ``affiliation_suspicions`` —— openapi.yaml:3055（疑点复核：404 / **403**）
#: 三者**都**明文写「跨租户 = 403 而非 404」⇒ 少一个就是契约破坏性变更。
PROBE_TABLES: frozenset[str] = frozenset(
    {"documents", "affiliation_tasks", "affiliation_suspicions"}
)

#: A6 启动回收的租户枚举：孤儿任务只可能落在两张任务载体表上
#: （``documents`` / ``affiliation_tasks``，ADR-0001 第 73 行）
ORG_ENUMERATION_TABLES: frozenset[str] = frozenset({"documents", "affiliation_tasks"})

#: 受控系统函数所在的 schema（与业务表隔离，避免被当成业务对象）
SYSTEM_SCHEMA = "app"

#: A7 存在性探测函数名
PROBE_FUNCTION = "tenant_row_exists"

#: A6 租户枚举函数名
ORG_ENUMERATION_FUNCTION = "list_tenant_orgs"

#: **P2-C 登录查找**函数名（受控旁路第 3 个）
LOGIN_LOOKUP_FUNCTION = "find_login_user"

#: 登录查找**唯一**允许触及的表。
#:
#: 为什么登录必须走旁路：登录时**还没有认证态** ⇒ 没有 org ⇒ 策略谓词为 NULL ⇒
#: 一行都查不到。这与 A7 ``tenant_row_exists`` 是同一形态（"看不见"不是"绕过"）：
#: 函数体只认这一张表、只按 ``username`` 取一行、属主仍是 ``rls_probe``。
#:
#: ⚠️ **它返回 ``password_hash``，这是受控通道里唯一一次返回列数据**（A7 只返回 boolean）。
#: 代价评估：能调用它的只有 ``app_rls``，且只能按**精确 username** 取一行 ⇒ 它把
#: "任意口令的在线猜测"从"不可能"放宽到"受 60/min 限流约束"。这是登录功能**不可分**的
#: 一部分（不取哈希就无处校验），故按 A7 同款流程登记：**先登记、再改门禁**。
LOGIN_LOOKUP_TABLE = "users"

#: 逐函数的表白名单（G-26 判据 6 由「全局一个白名单」改为**逐函数**核对，
#: 判据强度不变——每个函数仍然只能碰自己被点名的那几张表）。
FUNCTION_TABLE_WHITELIST: dict[str, frozenset[str]] = {
    PROBE_FUNCTION: PROBE_TABLES,
    ORG_ENUMERATION_FUNCTION: ORG_ENUMERATION_TABLES,
    LOGIN_LOOKUP_FUNCTION: frozenset({LOGIN_LOOKUP_TABLE}),
}


def tenant_tables() -> tuple[str, ...]:
    """租户表名（**由元数据推导**，不手工维护）。

    判据：表上有 ``org_id`` 列，且不在 :data:`RLS_EXEMPT_TABLES` 里。
    """
    return tuple(
        sorted(
            name
            for name, table in Base.metadata.tables.items()
            if "org_id" in table.columns and name not in RLS_EXEMPT_TABLES
        )
    )


#: 模块导入即定格的快照（供护栏断言与测试使用）
TENANT_TABLES: frozenset[str] = frozenset(tenant_tables())


def _policy_predicate() -> str:
    """策略谓词：**未设 org ⇒ 一行不命中**（fail-closed），且不抛错。

    ``nullif(..., '')`` 是**必须的**，不是防御性冗余（P3-C，2026-10-04 实测）：

    - 从未设置的连接 ⇒ ``current_setting(..., true)`` 为 NULL ⇒ 比较 NULL ⇒ 0 行；
    - **跑过一次 ``SET LOCAL`` 的连接** ⇒ 事务结束后 GUC 被还原成 **空串** ⇒
      裸 ``::uuid`` 会抛 ``22P02``（**500**），且只在第二次起才出现，极难复现。

    空串与 NULL 在这里**语义相同**（都表示"当前没有租户上下文"）⇒ 统一退化成 NULL，
    两种形态都回到「0 行」而不是「报错」。
    """
    return f"org_id = nullif(current_setting('{ORG_GUC}', true), '')::uuid"


def enable_statements(table: str) -> tuple[str, ...]:
    """建 ``ENABLE`` / ``FORCE`` / 策略（**幂等**：先 ``DROP POLICY IF EXISTS**）。"""
    predicate = _policy_predicate()
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # ⚠️ 不可漏：不 FORCE 则表 owner 绕过策略（ADR-0003 §3.2 要求 1）
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        (
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        ),
    )


def disable_statements(table: str) -> tuple[str, ...]:
    """``downgrade()`` 用：删策略 + 关 RLS（**不留半成品**）。"""
    return (
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    )


def apply_tenant_rls(connection: Any) -> tuple[str, ...]:
    """对 :data:`TENANT_TABLES` 逐张落策略（幂等，可重复执行）。"""
    tables = tenant_tables()
    for table in tables:
        for statement in enable_statements(table):
            connection.execute(text(statement))
    return tables


def drop_tenant_rls(connection: Any) -> tuple[str, ...]:
    """撤销 RLS（``downgrade`` / 测试隔离用）。"""
    tables = tenant_tables()
    for table in tables:
        for statement in disable_statements(table):
            connection.execute(text(statement))
    return tables


def ensure_exempt_tables_unprotected(connection: Any) -> None:
    """豁免表**不得**被装 RLS：``roles`` 是全局字典表（G-24 三条断言盯住本边界）。

    为什么显式做一遍：``downgrade`` 之后若有人误给 ``roles`` 加策略，
    「豁免集合没变」这条断言照样绿——只有真的查一次库才算数。
    """
    for table in sorted(RLS_EXEMPT_TABLES):
        connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        connection.execute(text(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}"))


# --------------------------------------------------------------------------- #
# 受控系统函数（A6 / A7）—— **须以超级用户**执行（要建 BYPASSRLS 属主角色）
# --------------------------------------------------------------------------- #

#: 属主角色：``NOLOGIN`` + ``BYPASSRLS``。
#:
#: ⚠️ 这是全案**唯一**的 BYPASSRLS 口子，且**只**为两个受控函数存在：
#: ADR-0003 §3.2 要求 ``FORCE ROW LEVEL SECURITY``，而 FORCE 会让**表 owner
#: 同样受策略约束** ⇒ ``SECURITY DEFINER`` 若挂在普通角色下，函数体内依然
#: 查不到别租户的行，403 语义无从判定。故必须由一个**极窄**的 BYPASSRLS
#: 角色持有这两个函数（NOLOGIN ⇒ 无人能以它连库；它名下也只有这两个函数）。
#: 应用账号（``app_rls``）仍然是 NOBYPASSRLS——G-26 判据 4 机械断言。
PROBE_ROLE = "rls_probe"

#: 应用（业务查询）角色——受限角色，见 ``scripts/init_rls_roles.py``
APP_ROLE = "app_rls"

#: 建表 / 迁移角色（owner）
OWNER_ROLE = "app_owner"


def _probe_body() -> str:
    """``app.tenant_row_exists``：只返回 boolean，表名走白名单。"""
    branches = "\n".join(
        f"    IF p_table = '{table}' THEN\n"
        f"        RETURN EXISTS (SELECT 1 FROM public.{table} WHERE id = p_id);\n"
        f"    END IF;"
        for table in sorted(PROBE_TABLES)
    )
    return f"""
CREATE OR REPLACE FUNCTION {SYSTEM_SCHEMA}.{PROBE_FUNCTION}(p_table text, p_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
{branches}
    RAISE EXCEPTION
        '{SYSTEM_SCHEMA}.{PROBE_FUNCTION}: 表 % 不在白名单内', p_table;
END;
$$;
"""


def _org_enumeration_body() -> str:
    """``app.list_tenant_orgs``：只返回 org_id 集合（A6 逐租户回收的枚举源）。"""
    union = "\n    UNION\n".join(
        f"    SELECT org_id FROM public.{table}"
        for table in sorted(ORG_ENUMERATION_TABLES)
    )
    return f"""
CREATE OR REPLACE FUNCTION {SYSTEM_SCHEMA}.{ORG_ENUMERATION_FUNCTION}()
RETURNS SETOF uuid
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
{union}
$$;
"""


def _login_lookup_body() -> str:
    """``app.find_login_user``：按 ``username`` 取一行登录凭据（P2-C）。

    **为什么只能用 ``LANGUAGE sql`` + 精确等值**：函数体里出现的每一张表都会被
    G-26 判据 6 从源码里正则抓出来核对，写成动态 SQL 就会绕过那道核对。
    """
    return f"""
CREATE OR REPLACE FUNCTION {SYSTEM_SCHEMA}.{LOGIN_LOOKUP_FUNCTION}(p_username text)
RETURNS TABLE(
    id uuid,
    org_id uuid,
    password_hash text,
    status text,
    activated_at timestamp with time zone,
    disabled_at timestamp with time zone
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT u.id, u.org_id, u.password_hash, u.status, u.activated_at, u.disabled_at
    FROM public.{LOGIN_LOOKUP_TABLE} AS u
    WHERE u.username = p_username
$$;
"""


def system_function_statements() -> tuple[str, ...]:
    """建受控系统函数并收紧权限（幂等）。**须以超级用户**连库执行。"""
    return (
        f"CREATE SCHEMA IF NOT EXISTS {SYSTEM_SCHEMA}",
        # 业务角色要能**调用**这两个函数（不是去读 schema 里的对象）
        f"GRANT USAGE ON SCHEMA {SYSTEM_SCHEMA} TO {APP_ROLE}",
        f"DO $$ BEGIN\n"
        f"    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN\n"
        f"        CREATE ROLE {PROBE_ROLE} NOLOGIN BYPASSRLS;\n"
        f"    END IF;\n"
        f"END $$;",
        _probe_body(),
        _org_enumeration_body(),
        # P2-C：登录查找（它是唯一会返回列数据的受控函数，理由见 :data:`LOGIN_LOOKUP_TABLE`）
        _login_lookup_body(),
        f"ALTER FUNCTION {SYSTEM_SCHEMA}.{PROBE_FUNCTION}(text, uuid) "
        f"OWNER TO {PROBE_ROLE}",
        f"ALTER FUNCTION {SYSTEM_SCHEMA}.{ORG_ENUMERATION_FUNCTION}() "
        f"OWNER TO {PROBE_ROLE}",
        f"ALTER FUNCTION {SYSTEM_SCHEMA}.{LOGIN_LOOKUP_FUNCTION}(text) "
        f"OWNER TO {PROBE_ROLE}",
        # ``BYPASSRLS`` 只免**行级策略**，不免**表权限** ⇒ 属主仍需显式 SELECT。
        # 范围**只有白名单这几张表**（它是 NOLOGIN，只能通过上面几个函数被间接使用）。
        *(
            f"GRANT SELECT ON public.{table} TO {PROBE_ROLE}"
            for table in sorted(
                PROBE_TABLES | ORG_ENUMERATION_TABLES | {LOGIN_LOOKUP_TABLE}
            )
        ),
        f"REVOKE ALL ON FUNCTION {SYSTEM_SCHEMA}.{PROBE_FUNCTION}(text, uuid) FROM PUBLIC",
        f"REVOKE ALL ON FUNCTION {SYSTEM_SCHEMA}.{ORG_ENUMERATION_FUNCTION}() FROM PUBLIC",
        f"REVOKE ALL ON FUNCTION {SYSTEM_SCHEMA}.{LOGIN_LOOKUP_FUNCTION}(text) FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {SYSTEM_SCHEMA}.{PROBE_FUNCTION}(text, uuid) "
        f"TO {APP_ROLE}",
        f"GRANT EXECUTE ON FUNCTION {SYSTEM_SCHEMA}.{ORG_ENUMERATION_FUNCTION}() "
        f"TO {APP_ROLE}",
        f"GRANT EXECUTE ON FUNCTION {SYSTEM_SCHEMA}.{LOGIN_LOOKUP_FUNCTION}(text) "
        f"TO {APP_ROLE}",
    )


def tenant_row_exists(session: Session, *, table: str, row_id: UUID) -> bool:
    """A7：**只回答「存在 / 不存在」**，不返回 ``org_id`` 或任何行数据。

    用途唯一：服务层区分「404 不存在」与「403 跨租户」（契约要求 403 而非 404）。
    表白名单在**两侧**各卡一次（Python 侧 + 函数体内），任一侧被改宽都会被
    G-26 判据 6 叫住。
    """
    if table not in PROBE_TABLES:
        raise ValueError(
            f"tenant_row_exists 的表名 {table!r} 不在白名单 {sorted(PROBE_TABLES)} 内"
        )
    # 参数化调用（非字符串拼接）：``text()`` 只承载绑定参数，不走业务裸 SQL 的口子
    return bool(
        session.execute(
            text(f"SELECT {SYSTEM_SCHEMA}.{PROBE_FUNCTION}(:table_name, :row_id)"),
            {"table_name": table, "row_id": row_id},
        ).scalar()
    )


def list_tenant_orgs(session: Session) -> tuple[UUID, ...]:
    """A6：枚举当前存在的租户 org_id（启动回收逐租户设 org 的枚举源）。"""
    rows: Sequence[Any] = (
        session.execute(text(f"SELECT {SYSTEM_SCHEMA}.{ORG_ENUMERATION_FUNCTION}()"))
        .scalars()
        .all()
    )
    return tuple(row for row in rows if row is not None)


def find_login_user(session: Session, *, username: str) -> dict[str, Any] | None:
    """P2-C：按 ``username`` 取一行登录凭据；查不到返回 ``None``。

    **调用方必须传 `system_session()`**：登录时还没有认证态，绑了 org 反而会让
    「另一个租户的同名账号」变成一场静默的串租户事故（虽然这里走的是旁路，但语义上
    登录查找**不属于任何租户**，就该用无租户的会话）。

    **为什么返回整行 dict 而不是只返回 id**：调用方要拿 ``password_hash`` 做校验、
    拿 ``org_id`` 绑会话、拿 ``status`` 判停用——分三次查只会把"取凭据"这件事
    拆成三个可以各自漂移的口子。

    ⚠️ 返回值含 ``password_hash`` ⇒ **严禁**落日志 / 进响应体 / 进契约。
    """
    row = (
        session.execute(
            text(
                "SELECT id, org_id, password_hash, status, activated_at, disabled_at "
                f"FROM {SYSTEM_SCHEMA}.{LOGIN_LOOKUP_FUNCTION}(:username)"
            ),
            {"username": username},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


__all__ = [
    "APP_ROLE",
    "FUNCTION_TABLE_WHITELIST",
    "LOGIN_LOOKUP_FUNCTION",
    "LOGIN_LOOKUP_TABLE",
    "ORG_ENUMERATION_FUNCTION",
    "ORG_ENUMERATION_TABLES",
    "ORG_GUC",
    "OWNER_ROLE",
    "POLICY_NAME",
    "PROBE_FUNCTION",
    "PROBE_ROLE",
    "PROBE_TABLES",
    "SYSTEM_SCHEMA",
    "TENANT_TABLES",
    "apply_tenant_rls",
    "disable_statements",
    "drop_tenant_rls",
    "enable_statements",
    "ensure_exempt_tables_unprotected",
    "find_login_user",
    "list_tenant_orgs",
    "system_function_statements",
    "tenant_row_exists",
    "tenant_tables",
]
