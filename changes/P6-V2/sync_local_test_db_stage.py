"""把既有的**持久**测试库 `graphrag_test` 补到与迁移 `a1f7c2b93d04` 同形（P6-V2）。

**为什么需要它（本地才有这个问题）**：CI 每次起**新** PG 容器 ⇒ 表由
``Base.metadata.create_all`` 从零建出，天然带 ``stage`` 列；而本地
``graphrag_test`` 是**持久**库，``create_all`` 不会给既有表加列，
``alembic upgrade head`` 又会从 base 重跑全套 DDL（撞已存在的表）——
两路径皆不可 ⇒ 只能把本批迁移的那段 DDL 原样补上去。

**它不声称自己验证了什么**：生产 / CI 的升级路径由
``tests/test_migrations_baseline.py``（临时库真跑迁移）验证；本脚本只是本地环
境同步工具，与 Storage / 数据无关。

跑法（backend/ 目录，需 owner 才能 ALTER + 改约束）：

```powershell
uv run python ../changes/P6-V2/sync_local_test_db_stage.py
```
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

OWNER_URL = "postgresql+psycopg://app_owner:app_owner@localhost:5432/graphrag_test"

#: 与 ``migrations/versions/a1f7c2b93d04_*.py`` 的 upgrade() 逐句对应
_DDL = (
    "ALTER TABLE cost_metrics ADD COLUMN IF NOT EXISTS stage VARCHAR(16) "
    "NOT NULL DEFAULT 'answer'",
    "ALTER TABLE cost_metrics DROP CONSTRAINT IF EXISTS uq_cost_metrics_org_date",
    "ALTER TABLE cost_metrics DROP CONSTRAINT IF EXISTS uq_cost_metrics_org_date_stage",
    "ALTER TABLE cost_metrics ADD CONSTRAINT uq_cost_metrics_org_date_stage "
    "UNIQUE (org_id, metric_date, stage)",
)

_COLUMNS = (
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name = 'cost_metrics' ORDER BY ordinal_position"
)
_CONSTRAINTS = (
    "SELECT conname FROM pg_constraint "
    "WHERE conrelid = 'cost_metrics'::regclass ORDER BY conname"
)


def main() -> None:
    engine = create_engine(OWNER_URL)
    with engine.begin() as conn:
        for statement in _DDL:
            conn.execute(text(statement))
        columns = [row[0] for row in conn.execute(text(_COLUMNS))]
        constraints = [row[0] for row in conn.execute(text(_CONSTRAINTS))]

    print("columns    :", columns)
    print("constraints:", constraints)
    assert "stage" in columns, "stage 列没加上——本地库与迁移不同形"
    assert "uq_cost_metrics_org_date_stage" in constraints
    assert "uq_cost_metrics_org_date" not in constraints


if __name__ == "__main__":
    main()
