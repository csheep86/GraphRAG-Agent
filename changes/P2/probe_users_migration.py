"""P2-A 探针：`users` 表迁移的**真机**验证。

为何不靠推断：迁移是一条**会被真正执行的生产路径**（`docs/deployment-spec.md` §7.2），
「模型改好了」不等于「现场执行的迁移对」。本脚本在 PG 16 的临时库上实测三件事：

1. ``alembic upgrade head`` 后 `users` **真的存在**，且**列 / 索引 / 约束**与 ORM 一致；
2. ``downgrade b3e5a1c70d42``（**只退一步**）后 `users` 消失、其余表**不受影响**
   ——`test_migrations_baseline.py` 只验了 ``downgrade base``，退一步的安全性没人验；
3. 再 ``upgrade head`` 能**重放回来**（幂等，不是单行道）。

跑法（须先起 PG：`docker run --rm -d --name graphrag-pg -e POSTGRES_USER=graphrag
-e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag -p 5432:5432 postgres:16-alpine`）：

    cd backend && uv run python ../changes/P2/probe_users_migration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
for path in (BACKEND_ROOT, BACKEND_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from pg_scratch import database_url_for, scratch_database  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
PREV_REVISION = "b3e5a1c70d42"  # 本批之前的 head


def _make_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _users_shape(engine) -> dict:
    inspector = inspect(engine)
    return {
        "columns": [col["name"] for col in inspector.get_columns("users")],
        "indexes": [
            entry["column_names"] for entry in inspector.get_indexes("users")
        ],
        "uniques": [
            entry["column_names"] for entry in inspector.get_unique_constraints("users")
        ],
        "checks": [
            entry["sqltext"] for entry in inspector.get_check_constraints("users")
        ],
    }


def main() -> None:
    with scratch_database("graphrag_p2users") as name:
        url = database_url_for(name)
        cfg = _make_config(url)
        engine = create_engine(url)
        try:
            print("[1] upgrade head")
            command.upgrade(cfg, "head")
            shape = _users_shape(engine)
            print(f"    users 列      = {sorted(shape['columns'])}")
            print(f"    users 索引    = {shape['indexes']}")
            print(f"    users 唯一约束= {shape['uniques']}")
            print(f"    users 检查约束= {shape['checks']}")
            assert len(shape["columns"]) == 7, shape["columns"]
            assert ["org_id", "status"] in shape["indexes"], shape["indexes"]
            assert ["username"] in shape["uniques"], shape["uniques"]
            # 版本号必须真的写进 alembic_version
            revision = engine.connect().execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            print(f"    alembic_version = {revision}")
            assert revision == "a1f3c9d27b08", revision

            print(f"[2] downgrade {PREV_REVISION}（只退一步）")
            command.downgrade(cfg, PREV_REVISION)
            tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
            print(f"    剩余表 {len(tables)} 张，含 users? {'users' in tables}")
            assert "users" not in tables, "退一步后 users 未消失 ⇒ drop_table 没写对"
            assert len(tables) == 12, tables

            print("[3] 再 upgrade head（重放）")
            command.upgrade(cfg, "head")
            tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
            print(f"    剩余表 {len(tables)} 张，含 users? {'users' in tables}")
            assert "users" in tables and len(tables) == 13, tables
        finally:
            engine.dispose()

    print("\n[OK] users 迁移三步实测全通过")


if __name__ == "__main__":
    main()
