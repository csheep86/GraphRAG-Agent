"""Alembic 迁移环境（D-2，Sprint 9.7 H1）。

**连接串与元数据只认两处真源**，不在本文件重复定义：

- URL：``app.core.config.get_settings().database_url``（与运行时同一份配置，
  dev 默认 SQLite、生产 PG——迁移脚本两侧通用）；
- 元数据：``app.db.models.Base.metadata``（``create_all`` 的同一真源，
  autogenerate 与它对比产生迁移）。

``compare_type=True``：列类型漂移也要能被 autogenerate 检出
（「加列忘写迁移」由 ``tests/test_migrations_baseline.py`` 的等价性测试钉死）。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# env.py 由 alembic CLI 在 backend/ 下执行；测试可能从别的 cwd 调，
# 把 backend/ 挂进 sys.path 保证 `app.*` 可导入（与 pyproject 的 pythonpath 一致）。
_BACKEND_ROOT = str(Path(__file__).resolve().parents[1])
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.core.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串：运行时同一份配置（alembic.ini 里不再维护第二份 URL）
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：不连库，把 DDL 输出为脚本（deployment-spec §7.2 升级预演可用）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
