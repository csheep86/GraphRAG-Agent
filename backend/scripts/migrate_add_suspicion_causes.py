"""``affiliation_suspicions`` 加 ``causes`` 列 + 放宽类型约束（Sprint 9.5 批次 D3）。

**为什么必须有这个脚本**：本项目**无 Alembic**（``app/db/models.py`` 模块头：
建表靠启动时的 ``create_all``）。而 ``create_all`` 对**已存在**的表**不做任何 ALTER**
——所以 C2 产出 ``causes`` 之后，线上库会一直停在旧结构上，代码写不进去、读出来
永远是 ``None``。加列与改约束只能靠一次显式 DDL。

用法（工作目录 = ``backend/``）::

    uv run python scripts/migrate_add_suspicion_causes.py           # 执行迁移
    uv run python scripts/migrate_add_suspicion_causes.py --check    # 只检查（CI 用）

退出码：**0** = 已迁移 / 无需迁移；**1** = 迁移失败；**2** = ``--check`` 发现未迁移。

**兼容性（如实登记，不静默降级）**：

- **PostgreSQL（真机）**：加列 + ``DROP CONSTRAINT`` / ``ADD CONSTRAINT``，完整执行；
- **SQLite（开发兜底）**：**只能加列**。SQLite 不支持 ``ALTER TABLE DROP CONSTRAINT``，
  约束变更**显式跳过并打印 WARN**——开发库请删库后由 ``create_all`` 重建，
  或忽略（SQLite 开发库本就不承担约束校验职责）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402

TABLE = "affiliation_suspicions"
COLUMN = "causes"
CONSTRAINT = "ck_affiliation_suspicions_type"
#: 与 ``app/db/models.py::SUSPICION_TYPE_VALUES`` 逐字一致
NEW_CHECK = (
    "suspicion_type IN ('shared_legal_rep', 'shared_address', 'missing_check_in')"
)


def _table_exists(conn: object, name: str) -> bool:
    return name in inspect(conn).get_table_names()


def _has_column(conn: object, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspect(conn).get_columns(table)}


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]
    dialect = engine.dialect.name
    print(f"方言      : {dialect}")
    print(f"目标表    : {TABLE}")

    with engine.begin() as conn:
        if not _table_exists(conn, TABLE):
            print(
                f"[SKIP] 表 {TABLE} 不存在（尚未建库），由 create_all 建表时自带新结构"
            )
            return 0

        if _has_column(conn, TABLE, COLUMN):
            print(f"[OK  ] 列 {COLUMN} 已存在，跳过加列")
            missing_column = False
        elif check_only:
            print(f"[FAIL] 列 {COLUMN} 缺失（--check：未迁移）", file=sys.stderr)
            return 2
        else:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} JSON"))
            print(f"[OK  ] 已加列 {COLUMN} JSON（可空：金融域疑点无归因）")
            missing_column = False

        if dialect == "postgresql":
            current = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
                    "WHERE conname = :name"
                ),
                {"name": CONSTRAINT},
            ).scalar()
            if current is not None and "missing_check_in" in str(current):
                print(f"[OK  ] 约束 {CONSTRAINT} 已含 missing_check_in，跳过")
            elif check_only:
                print(
                    f"[FAIL] 约束 {CONSTRAINT} 未放宽（--check：未迁移）",
                    file=sys.stderr,
                )
                return 2
            else:
                conn.execute(
                    text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
                )
                conn.execute(
                    text(
                        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} "
                        f"CHECK ({NEW_CHECK})"
                    )
                )
                print(f"[OK  ] 约束 {CONSTRAINT} 已放宽为 {NEW_CHECK}")
        else:
            print(
                f"[WARN] {dialect} 不支持 ALTER TABLE DROP CONSTRAINT："
                f"约束 {CONSTRAINT} **未变更**（列已加，写入考勤疑点前需删库重建）",
                file=sys.stderr,
            )

    if missing_column:  # pragma: no cover - 占位，逻辑上不会为真
        return 1
    print(f"\n迁移完成：{TABLE}.{COLUMN} 就位（{dialect}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
