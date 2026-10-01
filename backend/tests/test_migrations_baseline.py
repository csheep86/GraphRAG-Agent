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

from pathlib import Path

from alembic import command
from alembic.config import Config
from pg_scratch import database_url_for, scratch_database
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

#: 临时库名前缀（实际库名后面再拼一段 uuid）
SCRATCH_PREFIX = "graphrag_mig"


def _make_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


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
