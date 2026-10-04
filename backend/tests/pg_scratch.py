"""测试用 PostgreSQL 临时库工具（P1-C / DR-B2）。

**为什么需要这个文件**：SQLite 时代每个 pytest 会话一个临时文件，测试库天然是空的，
谁都不用管它的生老病死；切到 PG 后库是**持久**的，建库与回收都得有人负责。

两处共用同一套逻辑，避免各写一遍、各自漂移：

- ``tests/conftest.py``：固定测试库 ``graphrag_test``（C1）
- ``tests/test_migrations_baseline.py``：每条用例一个临时库（C2）

**两条 PG 铁律**（写错的表现分别是"事务里不允许 CREATE DATABASE"和
"database is being accessed by other users"）：

1. 建库 / 删库必须在 **AUTOCOMMIT**（``isolation_level="AUTOCOMMIT"``）下执行；
2. 删库前必须先把残留连接踢掉（``pg_terminate_backend``）。

连接串**不在此另设第二真源**：一律由 :func:`owner_url` 推导，只把**库名**
换成目标（ maintenance 库固定用 ``postgres``）。

**P3-A（2026-10-04）：为什么改成 owner 连接串**（裁决 4「CI 建两个角色」）
``DATABASE_URL`` 现在是**受限业务角色**（``app_rls``，``NOBYPASSRLS``）：它没有
``CREATEDB``，跑不了建库 / 迁移，也不该有——owner 跑业务测试会让 RLS **根本
没被验证**（ADR-0003 §3.2 要求 2）。故建库 / 建表 / 迁移一律走
``DATABASE_URL_OWNER``（``app_owner``），业务查询走 ``DATABASE_URL``。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

#: 建 / 删库时挂靠的 maintenance 库。它一定存在，
#: 而目标测试库本身可能还不存在（不能拿它当跳板去创建它自己）。
MAINTENANCE_DATABASE = "postgres"

#: Postgres 标识符宽松，这里只放行「字母开头 + 字母数字下划线」，
#: 因为库名要**拼进 DDL 文本**（绑定参数对标识符无效），必须自己挡住注入面。
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

#: 连不上时给的可复制命令（与 ``backend/.env.example`` 的示例保持一致）
_START_HINT = (
    "  docker run --rm -d -e POSTGRES_USER=graphrag "
    "-e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag "
    "-p 5432:5432 postgres:16-alpine"
)


def _check_identifier(name: str) -> None:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"非法的数据库名 {name!r}：只允许字母开头、后接字母 / 数字 / 下划线"
            "（它会被拼进 DDL 文本，绑定参数对标识符无效）"
        )


def owner_url() -> str:
    """**owner** 连接串（建库 / 建表 / 迁移用）。

    缺省值指向 ``app_owner``（由 ``scripts/init_rls_roles.py`` 创建）；
    CI / 本地可用 ``DATABASE_URL_OWNER`` 覆盖。**不使用**业务角色跑 DDL。
    """
    from app.db.rls import OWNER_ROLE

    default = (
        f"postgresql+psycopg://{OWNER_ROLE}:{OWNER_ROLE}@localhost:5432/graphrag_test"
    )
    return os.environ.get("DATABASE_URL_OWNER", default)


def _maintenance_url() -> str:
    """把 owner 连接串的库名换成 maintenance 库。"""
    # 延迟导入：本模块被 conftest 在 app.main 之前导入，此时配置尚未被读取。
    url = make_url(owner_url())
    return url.set(database=MAINTENANCE_DATABASE).render_as_string(hide_password=False)


def database_url_for(name: str) -> str:
    """把 owner 连接串的库名换成 ``name``（给 alembic / create_engine 用）。"""
    _check_identifier(name)
    return (
        make_url(owner_url()).set(database=name).render_as_string(hide_password=False)
    )


def database_exists(name: str) -> bool:
    _check_identifier(name)
    engine = create_engine(_maintenance_url())
    try:
        with engine.connect() as connection:
            found = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": name},
            ).first()
    finally:
        engine.dispose()
    return found is not None


def create_database(name: str) -> None:
    """建库；已存在则不动（幂等）。"""
    _check_identifier(name)
    engine = create_engine(_maintenance_url())
    try:
        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": name},
            ).first()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


def drop_database(name: str) -> None:
    """删库；不存在则不动（幂等）。先踢连接再删，否则 PG 会拒绝。"""
    _check_identifier(name)
    engine = create_engine(_maintenance_url())
    try:
        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        engine.dispose()


def ensure_database(name: str) -> None:
    """确保测试库存在；**连不上时给出可复制的指引**，而不是甩一屏堆栈。

    为什么单独包一层：这条报错的使用者是"刚 clone 完、还没起库就来跑测试"的人。
    让他看到 ``OperationalError`` 的原始堆栈，等于要他自己去猜缺的是什么。
    """
    try:
        create_database(name)
    except OperationalError as exc:
        raise RuntimeError(
            f"无法连上 PostgreSQL 以准备测试库 {name!r}。"
            "DR-B2 要求测试必须跑在 PostgreSQL 16.x 上，请先起一个：\n"
            f"{_START_HINT}\n"
            "若库已起而仍连不上：P3-A 起业务测试走**受限角色** app_rls，"
            "须先执行一次 `uv run python scripts/init_rls_roles.py --admin-url "
            "postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test`"
            "（建 app_owner / app_rls / 受控函数并落 RLS 策略）。\n"
            f"原始错误：{exc}"
        ) from exc


@contextmanager
def scratch_database(prefix: str) -> Iterator[str]:
    """临时库上下文：进入即建、退出必删（含用例失败的路径）。

    ``finally`` 而非「成功才删」——迁移跑到一半炸掉时，残留的库最容易在
    下一次跑测时以"名字冲突 / 状态不干净"的形式回来报复。
    """
    name = f"{prefix}_{uuid4().hex[:12]}"
    create_database(name)
    try:
        yield name
    finally:
        drop_database(name)
