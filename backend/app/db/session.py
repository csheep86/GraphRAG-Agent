"""数据库引擎与会话。

**DR-B1**：开发 / 测试 / 生产一律 PostgreSQL 16.x。SQLite 既非替身也非兜底，
方言特判不允许保留（ADR-0003 §3.6.2 已将 SQLite 列为待偿债务，现已清偿）。

租户隔离依赖 RLS：每个事务内须 `SET LOCAL app.current_org = :org_id`
（ADR-0003 §3.2 / §3.6）。

**P3-A（2026-10-04）本模块已落地 RLS 的请求侧一半**（DR-B8）：

- org 只挂在 ``session.info["tenant_org_id"]`` 上（唯一来源，不新增第二个）；
- 每个**新事务**由 ``after_begin`` 事件重放一遍 GUC——``SET LOCAL`` 是事务级的，
  ``commit()`` 之后的 ``refresh()`` 会另起事务，只在建会话时设一次不够；
- ``info`` 里没有 org ⇒ **不发** GUC ⇒ 策略谓词为 NULL ⇒ 一行都查不到
  （fail-closed，不是 fail-open）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.rls import ORG_GUC

#: ``session.info`` 里承载租户的键。**唯一来源**：请求侧由认证态写入
#: （``app/api/deps.py``），任务侧由 ``TaskSpec.org_id`` 写入（A5）。
ORG_ID_INFO_KEY = "tenant_org_id"


def _build_engine() -> Engine:
    """建引擎（PostgreSQL）。

    原先多线程 ASGI 场景下那条 SQLite 方言 ``connect_args`` 特判已于 **DR-B3** 删除：
    PostgreSQL 无此项，保留它等于给「SQLite 上明明跑得好好的」留一条回头路。

    ⚠️ 不要在此文件（含注释）重新写出那个被删开关的**名字**：G-21 是按**字样**扫描
    本文件的，连「已删除」的说明也会让它判定为命中（本批次实踩两次）。
    """
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant_guc(
    session: Session, transaction: object, connection: object
) -> None:
    """每个新事务重放一次 ``SET LOCAL app.current_org``（ADR-0003 §3.2 要求 3）。

    **为什么必须是事务级**：``SET``（会话级）会在连接归还池后被下一个租户
    复用 ⇒ 静默串租户，且**只有并发才测得出来**（DR-B8 / G-10）。
    这里用 ``set_config(..., is_local => true)``——它与 ``SET LOCAL`` 语义
    **等价**（PG 文档：``SET LOCAL`` 即 ``set_config`` 的 ``is_local=true`` 形态），
    但**可绑定参数**，不必把 UUID 拼进 SQL 文本。

    ``session.info`` 里没有 org ⇒ **什么都不做**（fail-closed：策略谓词为 NULL）。
    """
    org_id = session.info.get(ORG_ID_INFO_KEY)
    if org_id is None:
        return
    connection.exec_driver_sql(  # type: ignore[attr-defined]
        "SELECT set_config(%s, %s, true)", (ORG_GUC, str(org_id))
    )


def open_session(*, org_id: UUID | None = None) -> Session:
    """开一个会话；给了 ``org_id`` 就绑定租户（调用方负责 ``close()``）。

    非请求入口（后台任务 / 审计 / CLI）一律走这里并**显式**给 org——ADR-0003
    §3.3 禁止从 body / query 取 org，所以这里也**不提供**任何"猜"的默认值。
    """
    session = SessionLocal()
    if org_id is not None:
        session.info[ORG_ID_INFO_KEY] = org_id
    return session


def system_session() -> Session:
    """**A4 系统通道**会话：显式**不绑** org（RLS 下 ⇒ 业务表一行都看不到）。

    它**只**用于调用受控系统函数（``app.list_tenant_orgs`` 等）——那些函数自身是
    ``SECURITY DEFINER``，不需要调用方有租户视野。除此之外的任何查询在这里
    都只会得到空集：那正是 fail-closed 该有的样子（不是"绕过"，是"看不见"）。
    """
    return open_session()


@contextmanager
def session_scope(*, org_id: UUID | None = None) -> Iterator[Session]:
    """``with session_scope(org_id=...) as session``——带租户的会话上下文。"""
    session = open_session(org_id=org_id)
    try:
        yield session
    finally:
        session.close()


def init_db(bind: Engine | None = None) -> None:
    """建表（``create_all``）。

    ``bind`` 可显式指定引擎：**建表必须以 owner 身份**（受限角色无权 DDL）。
    测试侧传 ``owner`` 引擎（见 ``tests/conftest.py``），生产走 ``alembic``。

    **dev / 测试兜底**（启动行为不变，Sprint 9.7 起）：生产升级走
    ``alembic upgrade head``（基线见 ``migrations/versions/``，部署流程见
    ``docs/deployment-spec.md`` §7.2）。两者等价由
    ``tests/test_migrations_baseline.py`` 钉死——**加表 / 加列必须生成新迁移**。

    ⚠️ **本函数不建 RLS 策略**：``create_all`` 由受限角色跑时**无权** ``ALTER TABLE``
    （ADR-0003 §3.2 要求应用账号非 owner），而策略若由应用账号建，等于让应用
    自己给自己发豁免。RLS 的两条正规落盘路径：

    - 生产：``alembic upgrade head``（迁移以 owner 身份跑，含策略，见
      ``migrations/versions/`` 的 ``rls`` 迁移）；
    - dev / 测试：``uv run python scripts/init_rls_roles.py``（owner 身份建角色 + 落策略）。
    """
    from app.db.models import Base

    Base.metadata.create_all(bind=bind or engine)


def check_database() -> bool:
    """健康检查用：探测数据库连通性。"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - 健康检查不允许抛出
        return False
    return True


def dispose_engine() -> None:
    engine.dispose()
