"""Sprint 9.7 H2：迁移基线与 ORM 元数据的**等价性测试**（D-2 的验收核心）。

``create_all``（dev / 测试兜底）与 ``alembic upgrade head``（生产升级路径）
必须建出**同一套 schema**——对临时空 SQLite 跑迁移，再与
``Base.metadata``（create_all 的真源）比对表集合与列集合：

- **今后加表 / 加列忘写迁移 ⇒ 本测试必红**（这是 D-2 要根治的事故形态：
  旧库缺列、运行时才炸）；
- 顺带验证 ``downgrade base`` 可回（迁移不是单行道）。

启动行为刻意不变：不在 lifespan 里跑迁移（多实例并发风险），
生产升级按 ``docs/deployment-spec.md`` §7.2 由运维手动执行。
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _make_config(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _schema_of(engine: Engine) -> tuple[set[str], dict[str, set[str]]]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    columns = {
        table: {col["name"] for col in inspector.get_columns(table)} for table in tables
    }
    return tables, columns


def test_upgrade_head_matches_metadata(tmp_path: Path) -> None:
    db = tmp_path / "migrated.db"
    cfg = _make_config(db)

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    migrated_tables, migrated_columns = _schema_of(engine)

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
    engine.dispose()


def test_downgrade_base_clears_schema(tmp_path: Path) -> None:
    db = tmp_path / "downgraded.db"
    cfg = _make_config(db)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    tables, _ = _schema_of(engine)
    assert tables == set(), "downgrade base 后仍有残留表——迁移必须可回滚"
    engine.dispose()
