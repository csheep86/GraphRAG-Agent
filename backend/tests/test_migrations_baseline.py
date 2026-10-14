"""Sprint 9.7 H2：迁移基线与 ORM 元数据的**等价性测试**（D-2 的验收核心）。

``create_all``（dev / 测试兜底）与 ``alembic upgrade head``（生产升级路径）
必须建出**同一套 schema**——在 PostgreSQL 上起一个**临时库**跑迁移，再与
``Base.metadata``（create_all 的真源）比对表集合与列集合：

- **今后加表 / 加列忘写迁移 ⇒ 本测试必红**（这是 D-2 要根治的事故形态：
  旧库缺列、运行时才炸）；
- 顺带验证 ``downgrade base`` 可回（迁移不是单行道）。

启动行为刻意不变：不在 lifespan 里跑迁移（多实例并发风险），
生产升级按 ``docs/deployment-spec.md`` §7.2 由运维手动执行。

**P1-C（2026-10-01）：为什么把「临时 SQLite 文件」换成「临时 PG 库」**
原实现是跑在一个 SQLite 临时文件上——那意味着这条验收结论**只在 SQLite 上成立**，
而客户现场跑的是 PostgreSQL。迁移是一条**会被真正执行的生产路径**，
在与生产不同的方言上验证，等于没验证（DR-B2 要治的正是这种方言债）。
临时库由 ``tests/pg_scratch.py`` 负责建 / 删，**必须走 scratch 上下文**，
否则每次跑测都会在服务器上留一个孤儿库。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pg_scratch import database_url_for, scratch_database
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
#: 交付 / 开发两份编排（判据 3 的静态部分）
DELIVERY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.delivery.yml"
DEV_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
DB_INIT_SCRIPT = BACKEND_ROOT / "scripts" / "init_rls_roles.py"

#: 临时库名前缀（实际库名后面再拼一段 uuid）
SCRATCH_PREFIX = "graphrag_mig"


def _make_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _load_db_init():
    """按文件路径加载 ``scripts/init_rls_roles.py``（与 test_delivery_images 同一手法）。"""
    spec = importlib.util.spec_from_file_location("init_rls_roles", DB_INIT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["init_rls_roles"] = module
    spec.loader.exec_module(module)
    return module


def _head_revision() -> str:
    """当前 head（**不写死**版本号：写死会在下次加迁移时变成假红灯）。"""
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()


def _schema_of(engine: Engine) -> tuple[set[str], dict[str, set[str]]]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    columns = {
        table: {col["name"] for col in inspector.get_columns(table)} for table in tables
    }
    return tables, columns


def test_upgrade_head_matches_metadata() -> None:
    with scratch_database(SCRATCH_PREFIX) as name:
        cfg = _make_config(database_url_for(name))

        command.upgrade(cfg, "head")

        engine = create_engine(database_url_for(name))
        try:
            migrated_tables, migrated_columns = _schema_of(engine)
        finally:
            engine.dispose()

    meta_tables = set(Base.metadata.tables)
    assert migrated_tables == meta_tables, (
        "迁移结果与 ORM 元数据不一致："
        f"多 {migrated_tables - meta_tables}，缺 {meta_tables - migrated_tables}"
        "——加表 / 加列后必须生成新迁移（alembic revision --autogenerate），"
        "否则客户现场旧库缺列、运行时才炸（deployment-spec D-2）"
    )

    for table in meta_tables:
        meta_columns = {col.name for col in Base.metadata.tables[table].columns}
        assert migrated_columns[table] == meta_columns, (
            f"表 {table} 的列集合不一致："
            f"多 {migrated_columns[table] - meta_columns}，"
            f"缺 {meta_columns - migrated_columns[table]}"
        )


def test_downgrade_base_clears_schema() -> None:
    with scratch_database(SCRATCH_PREFIX) as name:
        cfg = _make_config(database_url_for(name))

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        engine = create_engine(database_url_for(name))
        try:
            tables, _ = _schema_of(engine)
        finally:
            engine.dispose()

    assert tables == set(), "downgrade base 后仍有残留表——迁移必须可回滚"


# --------------------------------------------------------------------------- #
# P7-Q（F-P7H-1）：**首次部署也走迁移** —— 交付形态的 db-init 路径
# --------------------------------------------------------------------------- #
#
# 缺陷回放：此前 `db-init` 用 `--create-tables`（`create_all`）建交付库且**从不 stamp**
# ⇒ 客户按 deployment-spec §7.2 升级时，`alembic upgrade head` 在**第一个**迁移就撞
# `DuplicateTable`（把版本号拨到哪一段都会撞）⇒ 升级路径是断的。
# 下面三条把它钉住：空库由迁移建表（判据 1）、再跑一次不撞（判据 2）、编排不许退回
# `create_all`（防回退）。


def test_db_init_fresh_db_builds_schema_via_migrations() -> None:
    """**判据 1**：空库走 db-init 的迁移路径 ⇒ schema 与 `Base.metadata` 完全一致。

    跑的是 ``scripts/init_rls_roles.py`` 里那个**真函数**（不是复刻一遍逻辑），
    否则"脚本改了、测试照样绿"。
    """
    db_init = _load_db_init()
    head = _head_revision()

    with scratch_database(SCRATCH_PREFIX) as name:
        url = database_url_for(name)
        engine = create_engine(url)
        try:
            note = db_init._ensure_schema_via_migrations(engine, url)
            # 策略由迁移落 ⇒ 脚本只校验；这里顺带证明"迁移落完了"
            policies = db_init._assert_policies_present(engine)
            with engine.connect() as connection:
                revision = db_init._stamped_revision(connection)
            migrated_tables, migrated_columns = _schema_of(engine)
        finally:
            engine.dispose()

    assert "空库" in note, f"空库应当走迁移建表，实际：{note}"
    assert revision == head, (
        f"首次部署后 alembic_version 应等于 head {head}，实际 {revision}"
    )
    assert policies, "迁移跑完竟然没有一张租户表带策略"

    meta_tables = set(Base.metadata.tables)
    assert migrated_tables == meta_tables, (
        f"迁移建的表与元数据不一致：多 {migrated_tables - meta_tables}，"
        f"缺 {meta_tables - migrated_tables}"
    )
    for table in meta_tables:
        meta_columns = {col.name for col in Base.metadata.tables[table].columns}
        assert migrated_columns[table] == meta_columns, (
            f"表 {table} 的列集合不一致：多 {migrated_columns[table] - meta_columns}，"
            f"缺 {meta_columns - migrated_columns[table]}"
        )


def test_db_init_migrated_db_survives_a_second_upgrade_head() -> None:
    """**判据 2**：由迁移建出来的库，再跑一次 `alembic upgrade head` ⇒ 不撞 DuplicateTable。

    这正是 F-P7H-1 的爆点形态（客户升级时在这里炸），且 `current` 必须等于 head。
    """
    db_init = _load_db_init()
    head = _head_revision()

    with scratch_database(SCRATCH_PREFIX) as name:
        url = database_url_for(name)
        engine = create_engine(url)
        try:
            db_init._ensure_schema_via_migrations(engine, url)
        finally:
            engine.dispose()

        cfg = _make_config(url)
        command.upgrade(cfg, "head")  # 不得抛 DuplicateTable / DuplicateColumn

        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                revision = db_init._stamped_revision(connection)
        finally:
            engine.dispose()

    assert revision == head, f"二次 upgrade head 后应为 {head}，实际 {revision}"


def _db_init_command(compose_path: Path) -> list[str]:
    import yaml

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    service = (compose.get("services") or {}).get("db-init") or {}
    raw = service.get("command")
    return raw.split() if isinstance(raw, str) else [str(part) for part in raw or []]


def test_delivery_db_init_builds_tables_via_migrations() -> None:
    """**防回退**：交付编排的 `db-init` 必须 `--run-migrations`，**不得** `--create-tables`。

    只看编排文件（静态）：真跑一遍由上面两条 + P7-Q 的升级演练负责。
    """
    parts = _db_init_command(DELIVERY_COMPOSE)
    assert parts, f"{DELIVERY_COMPOSE.name} 的 db-init 没有 command"
    assert "--run-migrations" in parts, (
        f"交付编排的 db-init 没有 `--run-migrations`（实际 {parts}）⇒ "
        "交付库又会回到 `create_all` 建表 + 从不 stamp ⇒ 客户升级时第一个迁移就撞 "
        "DuplicateTable（F-P7H-1）"
    )
    assert "--create-tables" not in parts, (
        f"交付编排的 db-init 又带上了 `--create-tables`（实际 {parts}）⇒ "
        "F-P7H-1 原样回归：两套并行的建表机制，混用必断"
    )


def test_dev_db_init_keeps_create_tables() -> None:
    """**Non-goal 1**：dev 路径刻意不动（`--create-tables` 兜底），改了就是动它。"""
    assert "--create-tables" in _db_init_command(DEV_COMPOSE)
