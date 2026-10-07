"""P5-C：新建 `ontology_actions` 表（M6 §4.2）+ **同文件落 RLS**。

**为什么 RLS 必须在本迁移里自己落**（而不是追加到既有的两张 RLS 迁移）：
G-26 的 `test_g26_migration_table_list_matches_metadata` 会 glob `*_rls_*.py`
并把各文件声明的 `TENANT_TABLES` 取**并集**去和 metadata 推导结果核对 ⇒
本迁移**必须**被那个 glob 命中（文件名里带 `rls`），否则少了 `ontology_actions`
那条断言必红；而既有的 `8210590e76a5` / `b7c4e1f9a2d3` 跑在历史更早的位置，
把它们的表清单加上本表会让 `alembic upgrade head` 在**尚未建表**时就
`ALTER TABLE ontology_actions` ⇒ 直接炸。故各写各的：**建表与本表的策略同源落地**。

谓词用 `nullif(..., '')`（不是裸 `::uuid`）：理由与 `b7c4e1f9a2d3` 同——
自定义 GUC 被 ``SET LOCAL`` 用过之后会还原成空串（不是"未设置"），
裸转换会抛 `22P02` ⇒ 第二次请求起 500（P3-C，2026-10-04 实测）。

两处偏离登记同 `app/db/models.py::ONTOLOGY_ACTION_TYPES`（X-2a / X-2b）：
`action_type` 多一个 `confirm`；`kg_version` 只允许 `confirm` 行为 NULL。

Revision ID: 3f7c1b90ad24
Revises: c5d8a3f17e42
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f7c1b90ad24"
down_revision: str | None = "c5d8a3f17e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 本迁移负责的租户表（G-26 取并集的核对入口点）：只写自己建的这一张——
#: 写成多张会把"谁是这张表的主人"搞丢，也会误导后来人以为清单是全局的。
TENANT_TABLES: tuple[str, ...] = ("ontology_actions",)

POLICY_NAME = "tenant_isolation"
#: 与 `app/db/rls.py::_policy_predicate()` 逐字一致
PREDICATE = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"


def upgrade() -> None:
    """建表 + 索引 + CHECK + **RLS**（ENABLE / FORCE / 策略）。"""
    op.create_table(
        "ontology_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=16), nullable=False),
        sa.Column("target_entities", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        # X-2b：confirm 场景还没有图谱 ⇒ 允许 NULL（其余三动作由 CHECK 兜住）
        sa.Column("kg_version", sa.String(length=64), nullable=True),
        sa.Column("result_kg_version", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('merge', 'split', 'rename', 'confirm')",
            name="ck_ontology_actions_action_type",
        ),
        sa.CheckConstraint(
            "action_type = 'confirm' OR kg_version IS NOT NULL",
            name="ck_ontology_actions_kg_version_required_except_confirm",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ADR-0003 §3.1：复合索引以 org_id 打头；单列索引用于跨表溯源
    op.create_index(
        "ix_ontology_actions_org_id_action_type",
        "ontology_actions",
        ["org_id", "action_type"],
    )
    op.create_index(
        "ix_ontology_actions_org_id_created_at",
        "ontology_actions",
        ["org_id", "created_at"],
    )
    op.create_index("ix_ontology_actions_org_id", "ontology_actions", ["org_id"])
    op.create_index("ix_ontology_actions_actor_id", "ontology_actions", ["actor_id"])
    op.create_index("ix_ontology_actions_trace_id", "ontology_actions", ["trace_id"])
    op.create_index(
        "ix_ontology_actions_result_kg_version",
        "ontology_actions",
        ["result_kg_version"],
    )

    # RLS：新增租户表**没有**策略 = 整表跨租户可见且不报错（需求基线 §226 第 1 条）
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # ⚠️ 不可漏：不 FORCE 则表 owner 绕过策略（ADR-0003 §3.2 要求 1）
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
        )


def downgrade() -> None:
    """整表删除（**有损**：审计行随之丢失）——与其"降一半"，不如登记为降级即有损。"""
    op.drop_index("ix_ontology_actions_result_kg_version", table_name="ontology_actions")
    op.drop_index("ix_ontology_actions_trace_id", table_name="ontology_actions")
    op.drop_index("ix_ontology_actions_actor_id", table_name="ontology_actions")
    op.drop_index("ix_ontology_actions_org_id", table_name="ontology_actions")
    op.drop_index("ix_ontology_actions_org_id_created_at", table_name="ontology_actions")
    op.drop_index("ix_ontology_actions_org_id_action_type", table_name="ontology_actions")
    op.drop_table("ontology_actions")
