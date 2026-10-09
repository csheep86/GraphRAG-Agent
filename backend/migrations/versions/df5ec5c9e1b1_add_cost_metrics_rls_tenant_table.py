"""add cost_metrics rls tenant table

P6-V（2026-10-09）：M6 §4.3 的成本日聚合表长期缺席 ⇒ ``GET /cost/dashboard``
只能占位 501。本迁移把它建起来（字段逐个照 ``app/db/models.py::CostMetric``），
并按 ADR-0003 §3.1 给这张租户表挂上 RLS。

**为什么凡是带 ``org_id`` 的表必须在本文件里显式建 RLS**：G-26 有一条机械断言
``test_g26_migration_table_list_matches_metadata`` —— 它从
``backend/migrations/versions/*rls*.py`` 里抽出 ``TENANT_TABLES`` 集合，要求与
``Base.metadata`` 里的租户表**逐字相等**。漏登记 ⇒ CI 直接红。

**为什么要在 CREATE TABLE 之后才 ENABLE**：顺序写反的话，插入期间会短暂豁开。

落库 Replication / 回滚：</br>
- 升级：``alembic upgrade head``（生产按 ``docs/deployment-spec.md`` §7.2 手动执行）；
- 回滚：``DROP POLICY`` → ``DROP TABLE``（本迁移的 ``downgrade()`` 负责）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "df5ec5c9e1b1"
down_revision: str | None = "3f7c1b90ad24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES: tuple[str, ...] = ("cost_metrics",)

POLICY_NAME = "tenant_isolation"
#: 与 ``app/db/rls.py::_policy_predicate()`` 逐字一致 —— 用 ``nullif(..., '')``
#: 而不是裸 ``::uuid``：自定义 GUC 被 ``SET LOCAL`` 用过之后会还原成**空串**
#: （不是"未设置"），裸转换会抛 ``22P02`` ⇒ 第二次请求起 500（P3-C 实测）。
PREDICATE = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"

_TABLE = "cost_metrics"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("token_usage_input", sa.BigInteger(), nullable=False),
        sa.Column("token_usage_output", sa.BigInteger(), nullable=False),
        sa.Column("token_usage_total", sa.BigInteger(), nullable=False),
        sa.Column("doc_count", sa.Integer(), nullable=False),
        # X-3：跨请求去重用的文档 id 清单
        sa.Column("counted_doc_ids", sa.JSON(), nullable=False),
        sa.Column("single_doc_cost", sa.Float(), nullable=False),
        sa.Column("incremental_cost", sa.Float(), nullable=True),
        sa.Column("full_rebuild_cost", sa.Float(), nullable=True),
        sa.Column("cost_ratio", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_metrics")),
        sa.UniqueConstraint("org_id", "metric_date", name="uq_cost_metrics_org_date"),
        sa.CheckConstraint(
            "token_usage_input >= 0 AND token_usage_output >= 0 AND doc_count >= 0",
            name=op.f("ck_cost_metrics_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_cost_metrics_org_id_metric_date"),
        _TABLE,
        ["org_id", "metric_date"],
        unique=False,
    )
    op.create_index(op.f("ix_cost_metrics_org_id"), _TABLE, ["org_id"], unique=False)

    # ---- RLS（ADR-0003 §3.1：策略必须 org_id 隔离 + FORCE） ---------------- #
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    # ⚠️ 不可漏：不 FORCE 则表 owner 绕过策略（ADR-0003 §3.2 要求 1）
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {_TABLE}")
    op.execute(
        f"CREATE POLICY {POLICY_NAME} ON {_TABLE} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_cost_metrics_org_id"), table_name=_TABLE)
    op.drop_index(op.f("ix_cost_metrics_org_id_metric_date"), table_name=_TABLE)
    op.drop_table(_TABLE)
