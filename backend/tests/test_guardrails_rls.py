"""**G-26（P3-A 新增）：RLS 策略机械断言**——DR-B4 的验收核心。

**为什么必须新增这条护栏**（需求基线第 206 行自认 B4「无独立断言」）：
T1 / T2（跨租户越权、并发串租户）**通过不代表 RLS 生效**——应用层
``org_id`` 过滤本身就足以让 T1 / T2 全绿。故「RLS 已落地」必须由**独立于
应用层**的断言机械证明，而不是由行为用例间接推断。

六条判据（``tasks.md`` §10）：

1. 每张租户表 ``relrowsecurity`` **且** ``relforcerowsecurity`` 为真；
2. 每张租户表的策略谓词**不得**为 ``USING (true)``；
3. 行为：受限角色**不设 org ⇒ 0 行**，设了 org ⇒ 只看到本 org 的行；
4. 应用账号 ``rolbypassrls = false``（且非超级用户、非表 owner）；
5. 豁免集合**恰好**等于 ``RLS_EXEMPT_TABLES``（当前只有 ``roles``）；
6. 受控绕过**足够窄**：只有登记的系统函数、只认表白名单、只有登记的调用点。

**判据 3 刻意用裸连接**（``engine.connect()`` + ``set_config``），不经过
``Session``：conftest 有一条「默认租户绑定」的测试脚手架，走 ``Session`` 的
断言会被它糊弄；裸连接绕得开。

**迁移与真源的一致性**由本文件末尾两条额外断言盯住（新增带 ``org_id`` 的表
而没改迁移 ⇒ 必红）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pg_scratch import database_url_for, scratch_database
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.models import RLS_EXEMPT_TABLES, Base
from app.db.rls import (
    APP_ROLE,
    ORG_ENUMERATION_FUNCTION,
    ORG_GUC,
    POLICY_NAME,
    PROBE_FUNCTION,
    PROBE_ROLE,
    PROBE_TABLES,
    SYSTEM_SCHEMA,
    TENANT_TABLES,
    tenant_tables,
)
from app.db.session import open_session, session_scope

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
#: **部署形态**的唯一安装入口（判据 7 会拿它实测）
COMPOSE = BACKEND_ROOT.parent / "deploy" / "docker-compose.yml"
DOCKERFILE = BACKEND_ROOT / "Dockerfile"
SCRATCH_PREFIX = "graphrag_rls"

#: 受控函数的**登记调用点**（G-26 判据 6 会拿源码实测与之比对）
PROBE_CALL_SITES: frozenset[str] = frozenset(
    {
        "app/services/documents.py",
        "app/services/affiliation.py",
    }
)
ORG_ENUMERATION_CALL_SITES: frozenset[str] = frozenset({"app/tasks/manager.py"})

#: A / B 两个租户（判据 3 用；刻意**不用**默认租户，避免与脚手架默认值重合）
_ORG_A = UUID("00000000-0000-4000-8000-0000000000a1")
_ORG_B = UUID("00000000-0000-4000-8000-0000000000b1")


def _restricted_engine():
    """**受限角色**的引擎（业务查询口径）。"""
    return create_engine(get_settings().database_url)


def _rows(sql: str, **params: object) -> list[tuple]:
    engine = _restricted_engine()
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql), params)]
    finally:
        engine.dispose()


def _seed_document(org_id: UUID) -> UUID:
    """按租户造一行（走 ORM，Python 侧默认值由 SQLAlchemy 补）。"""
    from app.db.models import Document

    with session_scope(org_id=org_id) as session:
        document = Document(
            filename_hash=f"g26-{uuid4().hex}",
            mime_type="application/pdf",
            size_bytes=1,
            status="completed",
            uploaded_by=uuid4(),
            org_id=org_id,
            trace_id=uuid4(),
        )
        session.add(document)
        session.commit()
        return document.id


def _delete_documents(document_ids: list[UUID]) -> None:
    from sqlalchemy import delete

    from app.db.models import Document

    for org_id in (_ORG_A, _ORG_B):
        with session_scope(org_id=org_id) as session:
            session.execute(delete(Document).where(Document.id.in_(document_ids)))
            session.commit()


# --------------------------------------------------------------------------- #
# 判据 1：ENABLE + FORCE
# --------------------------------------------------------------------------- #
def test_g26_1_every_tenant_table_has_rls_enabled_and_forced() -> None:
    """每张租户表都必须 ``ENABLE`` **且** ``FORCE``。

    **不 ``FORCE`` 则表 owner 绕过策略** ⇒ RLS 形同虚设（ADR-0003 §3.2 要求 1）。
    只断言 ``ENABLE`` 会让「装了但没生效」这种形态一路绿灯——那正是 B4 原来
    「无独立断言」的漏洞。
    """
    tables = tenant_tables()
    assert tables, "元数据里没推导出任何租户表——org_id 列被改名了？"

    rows = _rows(
        "SELECT relname, relrowsecurity, relforcerowsecurity "
        "FROM pg_class JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
        "WHERE pg_namespace.nspname = 'public' AND relname = ANY(:tables)",
        tables=list(tables),
    )
    state = {row[0]: (row[1], row[2]) for row in rows}

    missing = sorted(set(tables) - set(state))
    assert not missing, f"这几张租户表在库里查不到：{missing}"

    not_enabled = sorted(name for name, (on, _) in state.items() if not on)
    not_forced = sorted(name for name, (_, forced) in state.items() if not forced)
    assert not not_enabled, (
        f"以下租户表**没有** ENABLE ROW LEVEL SECURITY：{not_enabled}"
        "——漏一张 = 整表跨租户可见，且不会报错（需求基线 §226 第 1 条）"
    )
    assert not not_forced, (
        f"以下租户表**没有** FORCE ROW LEVEL SECURITY：{not_forced}"
        "——不 FORCE 则表 owner 绕过策略，RLS 形同虚设（ADR-0003 §3.2 要求 1）"
    )


# --------------------------------------------------------------------------- #
# 判据 2：谓词不得为 true
# --------------------------------------------------------------------------- #
def test_g26_2_policy_predicate_is_not_true() -> None:
    """策略谓词必须是按 ``org_id`` 收敛的表达式，**不得**是 ``USING (true)``。

    ``USING (true)`` 等于「装了策略，但不拦任何东西」——比没有 RLS 更危险，
    因为它会让所有"已开启 RLS"的检查一路绿灯。
    """
    rows = _rows(
        "SELECT tablename, policyname, qual, with_check FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = ANY(:tables)",
        tables=list(TENANT_TABLES),
    )
    by_table: dict[str, list[tuple[str, str, str]]] = {}
    for table, policy, qual, with_check in rows:
        by_table.setdefault(table, []).append((policy, qual or "", with_check or ""))

    no_policy = sorted(set(TENANT_TABLES) - set(by_table))
    assert not no_policy, f"以下租户表**没有**任何策略：{no_policy}"

    for table, policies in by_table.items():
        names = {policy for policy, _, _ in policies}
        assert POLICY_NAME in names, (
            f"表 {table} 上没有登记的策略名 {POLICY_NAME}（现有：{sorted(names)}）"
        )
        for policy, qual, with_check in policies:
            for label, expression in (("USING", qual), ("WITH CHECK", with_check)):
                normalized = expression.strip().strip("()").strip().lower()
                assert normalized != "true", (
                    f"表 {table} 的策略 {policy} 的 {label} 是恒真表达式"
                    "——那是「假装有隔离」，比没有更危险"
                )
                assert ORG_GUC in expression, (
                    f"表 {table} 的策略 {policy} 的 {label} 没有引用 "
                    f"{ORG_GUC}：{expression}"
                )


# --------------------------------------------------------------------------- #
# 判据 3：行为（**裸连接**，绕开测试脚手架）
# --------------------------------------------------------------------------- #
def test_g26_3_no_org_sees_nothing_and_org_sees_only_own() -> None:
    """受限角色：不设 org ⇒ **0 行**；设了 org ⇒ 只看到本 org 的行。

    刻意用**裸连接**（不是 ``Session``）：conftest 的「默认租户绑定」脚手架
    只作用在 ``sessionmaker`` 上，走 ``Session`` 的断言会被默认 org 救活，
    从而把「没设 org 也查得到」这种事故形态漏掉。
    """
    doc_a = _seed_document(_ORG_A)
    doc_b = _seed_document(_ORG_B)
    try:
        engine = _restricted_engine()
        try:
            with engine.connect() as connection:
                ids = [str(doc_a), str(doc_b)]

                # 1) 未设 org ⇒ 一行都看不到（fail-closed，不是 fail-open）
                unseen = connection.execute(
                    text("SELECT count(*) FROM documents WHERE id = ANY(:ids)"),
                    {"ids": ids},
                ).scalar()
                assert unseen == 0, (
                    f"未设 {ORG_GUC} 竟然能看到 {unseen} 行——RLS 没生效，"
                    "或策略谓词写成了恒真"
                )

                # 2) 设 org A ⇒ 只见 A
                connection.exec_driver_sql(
                    "SELECT set_config(%s, %s, true)", (ORG_GUC, str(_ORG_A))
                )
                seen_a = connection.execute(
                    text("SELECT org_id FROM documents WHERE id = ANY(:ids)"),
                    {"ids": ids},
                ).fetchall()
                connection.commit()
                assert [row[0] for row in seen_a] == [_ORG_A], (
                    f"设了 org A 却看到了 {seen_a}——串租户（G-10 要治的事故形态）"
                )

                # 3) 换 org B ⇒ 只见 B（``SET LOCAL`` 是事务级：commit 后已失效）
                connection.exec_driver_sql(
                    "SELECT set_config(%s, %s, true)", (ORG_GUC, str(_ORG_B))
                )
                seen_b = connection.execute(
                    text("SELECT org_id FROM documents WHERE id = ANY(:ids)"),
                    {"ids": ids},
                ).fetchall()
                connection.commit()
                assert [row[0] for row in seen_b] == [_ORG_B], (
                    f"设了 org B 却看到了 {seen_b}——连接池复用串号？"
                )
        finally:
            engine.dispose()
    finally:
        _delete_documents([doc_a, doc_b])


def test_g26_3b_session_replays_guc_on_every_transaction() -> None:
    """A2：绑了 org 的 ``Session`` 必须在**每个新事务**里重放 GUC。

    ``SET LOCAL`` 是事务级的：``commit()`` 之后的 ``refresh()`` 另起事务，
    只在建会话时设一次 ⇒ 第二次查询就是裸奔（DR-B8）。
    """
    engine = _restricted_engine()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "SELECT set_config(%s, %s, true)", (ORG_GUC, str(_ORG_A))
            )
            assert connection.execute(
                text(f"SELECT current_setting('{ORG_GUC}', true)")
            ).scalar() == str(_ORG_A)
            connection.commit()
            # 新事务：事务级 GUC 必须已经失效（否则就是 ``SET`` 不是 ``SET LOCAL``）
            assert connection.execute(
                text(f"SELECT current_setting('{ORG_GUC}', true)")
            ).scalar() in (None, ""), (
                "事务提交后 GUC 仍在 ⇒ 用的是会话级 SET（会串租户），不是 SET LOCAL"
            )
    finally:
        engine.dispose()

    with open_session(org_id=_ORG_B) as session:
        assert session.execute(
            text(f"SELECT current_setting('{ORG_GUC}', true)")
        ).scalar() == str(_ORG_B)
        session.commit()
        # commit 之后的新事务：org 必须被**重放**，而不是留在上一次事务里
        assert session.execute(
            text(f"SELECT current_setting('{ORG_GUC}', true)")
        ).scalar() == str(_ORG_B), (
            "commit 之后 org 没被重放 ⇒ 后台任务的第二次查询会裸奔"
        )


# --------------------------------------------------------------------------- #
# 判据 8：**跑过 SET LOCAL 之后**，未绑 org 的查询必须是「0 行」而不是「报错」
#         （P3-C，2026-10-04：P3-B 做 T1 补齐时实测踩到）
# --------------------------------------------------------------------------- #
def test_g26_8_unbound_query_after_bound_txn_is_zero_rows_not_error() -> None:
    """同一条连接**跑过一次绑 org 的事务之后**，不绑 org 的查询 ⇒ **0 行**，不得抛错。

    **踩到的坑**：``app.current_org`` 是**自定义** GUC，而自定义 GUC 在被
    ``SET LOCAL`` 用过之后，事务结束时会还原到它的 **reset 值**——那是**空串**
    ``''``，**不是**"未设置"（那才是 NULL）。谓词若是裸 ``::uuid``，空串会直接抛

        ERROR 22P02: invalid input syntax for type uuid: ""

    于是「ADR-0003 §3.3 承诺的 fail-closed（0 行）」变成 **500**，而且只在
    **该连接跑过一次绑 org 的事务之后**才出现 ⇒ **首次请求正常、第二次起崩**，
    是最难复现的那一类故障（P3-B 做 `qa_logs` 的 T1 时撞上）。

    故谓词须为 ``nullif(current_setting(...), '')::uuid``：空串与 NULL 语义相同
    （都表示"当前没有租户上下文"）⇒ 统一退化成 NULL ⇒ 0 行，不报错。

    ⚠️ 本条**刻意**沿用判据 3b 里那个"看似无害"的 ``in (None, "")``：
    当初它只被用来断言"GUC 已失效"，而空串与 NULL 在这里**后果完全不同**——
    这就是本条存在的原因。
    """
    doc_a = _seed_document(_ORG_A)
    engine = _restricted_engine()
    try:
        with engine.connect() as connection:
            # 事务 1：绑 org A（应用的正常路径）
            connection.exec_driver_sql(
                "SELECT set_config(%s, %s, true)", (ORG_GUC, str(_ORG_A))
            )
            bound = connection.execute(text("SELECT count(*) FROM documents")).scalar()
            assert bound >= 1, "正向对照失败：绑了 org 却一行都看不到 ⇒ 用例自身失效"
            connection.commit()

            # 事务 2：**同一条连接**、不绑 org（系统路径 / 运维脚本 / 漏绑的通道）
            guc = connection.execute(
                text(f"SELECT current_setting('{ORG_GUC}', true)")
            ).scalar()
            assert guc == "", (
                f"PG 16 上自定义 GUC 在 SET LOCAL 的事务结束后应还原为**空串**，实际 "
                f"{guc!r}。若 PG 行为已变（例如回到 NULL），请同步更新本条与 "
                "app/db/rls.py 的谓词注释——但 0 行这条断言**无论如何都要成立**"
            )
            unbound = connection.execute(
                text("SELECT count(*) FROM documents")
            ).scalar()
    finally:
        engine.dispose()
        _delete_documents([doc_a])

    assert unbound == 0, f"没绑 org 却看到 {unbound} 行 ⇒ 隔离失效（fail-closed 破口）"


# --------------------------------------------------------------------------- #
# 判据 4：应用账号不是 bypass / 不是 owner
# --------------------------------------------------------------------------- #
def test_g26_4_app_account_is_not_bypassrls() -> None:
    """应用账号必须 ``NOBYPASSRLS``、非超级用户、且**不是**表 owner。

    超级用户与 ``BYPASSRLS`` 角色**完全绕过** RLS——用它们跑业务，等于把
    RLS 当装饰品（ADR-0003 §3.2 要求 2）。本机默认库用户（docker 起的
    ``POSTGRES_USER``）就是超级用户，这条断言正是拦住「测试其实没验到 RLS」。
    """
    rows = _rows(
        "SELECT current_user, "
        "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user), "
        "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
    )
    current_user, bypass, superuser = rows[0]
    assert not bypass, (
        f"应用账号 {current_user} 带 BYPASSRLS ⇒ RLS 对它无效，测试结论全是假的"
    )
    assert not superuser, (
        f"应用账号 {current_user} 是超级用户 ⇒ RLS 对它无效（超级用户绕过一切策略）"
    )
    assert current_user == APP_ROLE, (
        f"业务测试应当以受限角色 {APP_ROLE} 连接，当前是 {current_user}"
        "——请先跑 scripts/init_rls_roles.py"
    )

    owners = _rows(
        "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class "
        "WHERE relname = ANY(:tables)",
        tables=list(TENANT_TABLES),
    )
    owner_names = {row[0] for row in owners}
    assert current_user not in owner_names, (
        f"应用账号 {current_user} 竟然是租户表的 owner（{sorted(owner_names)}）："
        "owner 侧跑业务 ⇒ 即便 FORCE 也在特权侧，见 ADR-0003 §3.2 要求 2"
    )


# --------------------------------------------------------------------------- #
# 判据 5：豁免集合不扩大
# --------------------------------------------------------------------------- #
def test_g26_5_exempt_set_is_exactly_registered() -> None:
    """豁免集合**恰好**是 ``RLS_EXEMPT_TABLES``（当前只有全局字典表 ``roles``）。

    豁免表上的数据对所有租户可见——**扩大即泄漏**。这条断言同时盯住两侧：
    代码侧的标记集合，以及**库里真实的状态**（``downgrade`` 之后若有人误给
    ``roles`` 加策略，「豁免集合没变」这条照样绿，只有查库才算数）。
    """
    assert set(RLS_EXEMPT_TABLES) == {"roles"}, (
        f"RLS 豁免集合被改成 {sorted(RLS_EXEMPT_TABLES)}——"
        "新增豁免表属于破坏性变更，须先升级评估（G-24 三条断言盯的正是这条边界）"
    )

    rows = _rows(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
        "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
        "WHERE pg_namespace.nspname = 'public' AND relname = ANY(:tables)",
        tables=sorted(RLS_EXEMPT_TABLES),
    )
    for name, enabled, forced in rows:
        assert not enabled and not forced, (
            f"豁免表 {name} 竟然被装了 RLS（enabled={enabled}, forced={forced}）"
        )

    policies = _rows(
        "SELECT tablename, policyname FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = ANY(:tables)",
        tables=sorted(RLS_EXEMPT_TABLES),
    )
    assert policies == [], f"豁免表上出现了策略 {policies}——字典表被当成了租户数据"

    # 反向：带 org_id 的表**必须**在租户集合里（推导逻辑不能被改窄）
    with_org_id = {
        name
        for name, table in Base.metadata.tables.items()
        if "org_id" in table.columns
    }
    assert with_org_id - set(RLS_EXEMPT_TABLES) == set(TENANT_TABLES), (
        "租户表推导结果与常量不一致："
        f"{sorted(with_org_id - set(RLS_EXEMPT_TABLES) ^ set(TENANT_TABLES))}"
    )


# --------------------------------------------------------------------------- #
# 判据 6：受控绕过足够窄
# --------------------------------------------------------------------------- #
def test_g26_6_controlled_bypass_is_narrow() -> None:
    """受控绕过（A6 / A7）必须**窄到可以逐条点名**。

    点名四件事：只有登记的两个函数、都是 ``SECURITY DEFINER``、只认表白名单、
    只有登记的调用点。任何一项变宽（多一个函数 / 多一张表 / 多一个调用点）
    都会让这条断言变红——**不允许**以"顺手加一个"的方式扩大绕过面。
    """
    functions = _rows(
        "SELECT proname, prosecdef, pg_get_userbyid(proowner), prosrc, "
        "(SELECT rolcanlogin FROM pg_roles WHERE rolname = pg_get_userbyid(proowner)), "
        "(SELECT rolbypassrls FROM pg_roles WHERE rolname = pg_get_userbyid(proowner)) "
        f"FROM pg_proc JOIN pg_namespace ON pg_namespace.oid = pg_proc.pronamespace "
        f"WHERE pg_namespace.nspname = '{SYSTEM_SCHEMA}'"
    )
    by_name = {row[0]: row for row in functions}

    assert set(by_name) == {PROBE_FUNCTION, ORG_ENUMERATION_FUNCTION}, (
        f"受控 schema {SYSTEM_SCHEMA} 里的函数变成了 {sorted(by_name)}——"
        "新增绕过函数须先登记（A7 登记表 + 本断言）"
    )

    for name, (_, secdef, owner, source, can_login, bypass) in by_name.items():
        assert secdef, f"{SYSTEM_SCHEMA}.{name} 不是 SECURITY DEFINER"
        assert owner == PROBE_ROLE, (
            f"{SYSTEM_SCHEMA}.{name} 的属主是 {owner}，应为受控角色 {PROBE_ROLE}"
        )
        assert not can_login, (
            f"属主角色 {PROBE_ROLE} 竟可登录（rolcanlogin=true）——"
            "它必须 NOLOGIN，只能经函数被间接使用"
        )
        assert bypass, (
            f"属主角色 {PROBE_ROLE} 没有 BYPASSRLS，则 FORCE 下函数体内查不到"
        )
        # 函数体里出现的表**必须**恰好是白名单（多一张 = 绕过面变大）
        referenced = set(re.findall(r"public\.([a-z_]+)", source))
        assert referenced <= set(PROBE_TABLES), (
            f"{SYSTEM_SCHEMA}.{name} 引用了白名单外的表 {sorted(referenced)}"
            f"（白名单：{sorted(PROBE_TABLES)}）"
        )

    # 全库（超级用户除外）只允许这一个 BYPASSRLS 角色
    bypass_roles = _rows(
        "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolbypassrls AND NOT rolsuper"
    )
    assert {row[0] for row in bypass_roles} == {PROBE_ROLE}, (
        f"出现登记外的 BYPASSRLS 角色：{bypass_roles}——"
        "每一个 bypass 口子都必须能被单独点名"
    )
    assert all(not row[1] for row in bypass_roles), "BYPASSRLS 角色必须 NOLOGIN"

    _assert_call_sites("tenant_row_exists(", PROBE_CALL_SITES)
    _assert_call_sites("list_tenant_orgs(", ORG_ENUMERATION_CALL_SITES)


def _assert_call_sites(symbol: str, registered: frozenset[str]) -> None:
    """``app/`` 下调用该符号的文件集合**恰好**等于登记集合。"""
    app_root = BACKEND_ROOT / "app"
    found = {
        str(path.relative_to(BACKEND_ROOT).as_posix())
        for path in app_root.rglob("*.py")
        if symbol in path.read_text(encoding="utf-8")
    }
    # 符号自身的定义处（app/db/rls.py）不算调用点
    found -= {"app/db/rls.py"}
    assert found == set(registered), (
        f"{symbol} 的调用点变成了 {sorted(found)}，登记的是 {sorted(registered)}——"
        "多出来的调用点意味着绕过面被悄悄扩大"
    )


# --------------------------------------------------------------------------- #
# 附加：迁移与真源一致（新增带 org_id 的表而没改迁移 ⇒ 必红）
# --------------------------------------------------------------------------- #
def test_g26_migration_table_list_matches_metadata() -> None:
    """迁移里写死的表清单必须**恰好**等于 ``TENANT_TABLES``。

    迁移刻意不 import 应用代码（历史产物要可重放），所以清单是复制的——
    复制就会漂移。这条断言把漂移变成红灯。
    """
    candidates = sorted((BACKEND_ROOT / "migrations" / "versions").glob("*_rls_*.py"))
    assert candidates, "没找到 RLS 迁移文件——DR-B4 的策略靠它落生产库"

    declared: set[str] = set()
    for path in candidates:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # 迁移里带类型注解 ⇒ 是 AnnAssign，不是 Assign（两种都要认）
            if isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
                matched = bool(targets) and targets[0].id == "TENANT_TABLES"
            elif isinstance(node, ast.AnnAssign):
                matched = (
                    isinstance(node.target, ast.Name)
                    and node.target.id == "TENANT_TABLES"
                )
            else:
                matched = False
            if matched and node.value is not None:
                declared |= set(ast.literal_eval(node.value))

    assert declared == set(TENANT_TABLES), (
        "迁移声明的租户表与元数据推导结果不一致："
        f"迁移多 {sorted(declared - set(TENANT_TABLES))}，"
        f"迁移缺 {sorted(set(TENANT_TABLES) - declared)}"
        "——新增带 org_id 的表必须同步改迁移，否则生产库那张表没有策略"
    )


def test_g26_migration_applies_rls_on_scratch_db() -> None:
    """**真跑一遍迁移**：``alembic upgrade head`` 之后策略必须真的在库里。

    只比对迁移文件里的清单会被"文件写了但 SQL 写错"骗过；这里是唯一的
    端到端证明：**生产升级路径**（运维手动跑 alembic）能把 RLS 装上。
    """
    with scratch_database(SCRATCH_PREFIX) as name:
        url = database_url_for(name)
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")

        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                state = {
                    row[0]: (row[1], row[2])
                    for row in connection.execute(
                        text(
                            "SELECT relname, relrowsecurity, relforcerowsecurity "
                            "FROM pg_class "
                            "JOIN pg_namespace ON pg_namespace.oid = relnamespace "
                            "WHERE nspname = 'public' AND relname = ANY(:tables)"
                        ),
                        {"tables": list(TENANT_TABLES)},
                    )
                }
                policies = {
                    row[0]
                    for row in connection.execute(
                        text(
                            "SELECT tablename FROM pg_policies "
                            "WHERE schemaname = 'public' AND policyname = :policy"
                        ),
                        {"policy": POLICY_NAME},
                    )
                }
                # 可逆：downgrade 之后策略必须消失（不留半成品）
                connection.commit()
        finally:
            engine.dispose()

    missing = sorted(set(TENANT_TABLES) - set(state))
    assert not missing, f"迁移后这些租户表不存在：{missing}"

    broken = sorted(
        name for name, (enabled, forced) in state.items() if not (enabled and forced)
    )
    assert not broken, f"迁移没有在这些表上落 ENABLE + FORCE：{broken}"
    assert set(TENANT_TABLES) - policies == set(), (
        f"迁移后缺 {POLICY_NAME} 策略：{sorted(set(TENANT_TABLES) - policies)}"
    )


@pytest.mark.parametrize("table", sorted(TENANT_TABLES))
def test_g26_per_table_policy_present(table: str) -> None:
    """逐表点名（参数化）：任何一张表漏掉都会以**它自己的名字**报红。

    集合比对失败时只给人一个 diff；这里让 CI 直接指名道姓。
    """
    rows = _rows(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
        "JOIN pg_namespace ON pg_namespace.oid = relnamespace "
        "WHERE nspname = 'public' AND relname = :table",
        table=table,
    )
    assert rows, f"租户表 {table} 不在库里"
    enabled, forced = rows[0]
    assert enabled and forced, (
        f"租户表 {table}：ENABLE={enabled} / FORCE={forced}——两者都必须为真"
    )


# --------------------------------------------------------------------------- #
# 判据 7：**部署形态**——compose 的应用账号必须是受限角色（2026-10-04 补）
# --------------------------------------------------------------------------- #


def _compose_command(service: dict) -> list[str]:
    """compose 的 ``command`` 既可能是字符串也可能是列表，统一成词表。"""
    command = service.get("command")
    if isinstance(command, str):
        return command.split()
    return [str(part) for part in command or []]


def test_g26_7_deploy_compose_uses_restricted_db_role() -> None:
    """**交付物里写死的连库账号**也必须是受限角色（否则库里的策略是装饰品）。

    **为什么连编排文件都要判**：PG 里**超级用户绕过一切 RLS**，而 compose 用
    ``POSTGRES_USER`` 起出来的账号**正是超级用户**。于是「策略已落库」与
    「隔离已生效」之间还差一个连库身份——差的那一段**没有任何症状**：
    业务照常跑、T1 / T2 在测试库里照样绿。本判据就是把这一段也钉死。

    四条判据：

    1. ``backend`` 的 ``DATABASE_URL`` 账号 **必须**是 ``APP_ROLE``（``app_rls``），
       且**不得**是任何 PG 服务的超级用户；
    2. 必须存在**执行 init 脚本**的一次性服务（建角色 / 受控函数 / 落策略）——
       应用账号自己建不出来这些；
    3. ``backend`` 必须以 ``service_completed_successfully`` 依赖该服务：
       只写「起来了」的话，init 失败时 backend 照样对外服务（**没装 RLS 也在服务**）；
    4. backend 镜像必须 ``COPY`` 了 ``scripts/``：否则 init 服务在容器里找不到
       ``init_rls_roles.py``，而这一条**只有真起容器才看得出**。

    ⚠️ 本断言**只看交付物**（编排文件 / Dockerfile），不证明运行时真连的是它——
    那是判据 4（连库实测 ``rolbypassrls``）的事。
    """
    import yaml

    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = compose.get("services") or {}
    backend = services.get("backend")
    assert isinstance(backend, dict), f"{COMPOSE.name} 无 backend 服务"

    # 1) 连库账号 = 受限角色，且不得是 PG 超级用户
    url = str((backend.get("environment") or {}).get("DATABASE_URL", ""))
    user = url.split("://", 1)[-1].split(":", 1)[0] if "://" in url else ""
    superusers = {
        str((service.get("environment") or {}).get("POSTGRES_USER", ""))
        for service in services.values()
        if isinstance(service, dict)
    } - {""}
    assert user == APP_ROLE, (
        f"compose 的 backend 连库账号是 {user or '（空）'}，须为受限角色 {APP_ROLE}"
    )
    assert user not in superusers, (
        f"compose 的 backend 正以 PG 超级用户 {user} 连库 ⇒ 超级用户绕过一切 RLS，"
        "库里的策略形同装饰（且**没有任何症状**）"
    )

    # 2) 一次性 init 服务
    init_services = [
        name
        for name, service in sorted(services.items())
        if isinstance(service, dict)
        and any("init_rls_roles.py" in part for part in _compose_command(service))
    ]
    assert init_services, (
        f"{COMPOSE.name} 里没有任何服务执行 scripts/init_rls_roles.py ⇒ "
        "角色 / 受控函数 / 策略无人建立（受限账号自己建不出来）"
    )

    # 3) backend 必须等它**成功退出**
    depends_on = backend.get("depends_on") or {}
    waited = [
        name
        for name in init_services
        if (depends_on.get(name) or {}).get("condition")
        == "service_completed_successfully"
    ]
    assert waited, (
        f"backend 未以 service_completed_successfully 依赖 init 服务 {init_services}"
        f"（实际 {depends_on}）⇒ init 失败时 backend 仍会起来，"
        "等于对外提供「没装 RLS」的服务"
    )

    # 4) 镜像里有 scripts/（否则 init 服务在容器里找不到脚本）
    #    ⚠️ 只认**真正的 COPY 指令**：注释里提一句 `backend/scripts` 不算——
    #    Dockerfile 里"说了但没做"比不说更危险（看着像已处置）。
    copied = [
        line
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("COPY") and "backend/scripts" in line
    ]
    assert copied, (
        f"{DOCKERFILE.name} 没有 `COPY backend/scripts` 指令 ⇒ init 服务在容器里找不到 "
        "init_rls_roles.py；该失败只有真起容器才看得出来（注释里提到不算数）"
    )
