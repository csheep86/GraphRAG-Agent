"""Sprint 9.13 批次 C3：新建 `entity_merge_candidates` 表（M2 §4.5 / §3 验收 3）。

**为什么必须显式迁移**：`create_all` 只建**新库**；已存在的库不会自己长出新表，
缺这张表 ⇒ 消解器算出的候选**无处可落**，S6.2-2（实体消解未做）在真机上等于没偿还。

建表要点（逐条对应 `specs/m2-extract-kg.md`）：

1. 字段对齐 §4.5：`id` / `org_id` / `left_entity_id` / `right_entity_id` /
   `similarity` / `status` / `created_at` / `trace_id`；`org_id` 索引**打头**（ADR-0003）；
2. `left/right_entity_id` 为 **TEXT**（偏离 **S9.13-1**）：图侧实体 id 是稳定字符串，
   没有 UUID 可存；
3. `status` CHECK 含 5 值，其中 `applied` 是 **M6 前向预留**（枚举有、运行时不写），
   `pending` / `rejected` 本阶段同样无写入方——**枚举留位 ≠ 已经在使用**；
4. 额外两列：`signals JSON`（判分留痕，审计要能回答"为什么是这一档"）。

Revision ID: b3e5a1c70d42
Revises: 9c1b7d2ae4f3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e5a1c70d42"
down_revision: str | None = "9c1b7d2ae4f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "entity_merge_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("left_entity_id", sa.String(length=255), nullable=False),
        sa.Column("right_entity_id", sa.String(length=255), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'auto_merged', 'human_review', 'rejected', "
            "'applied')",
            name="ck_entity_merge_candidates_status",
        ),
        sa.CheckConstraint(
            "similarity >= 0.0 AND similarity <= 1.0",
            name="ck_entity_merge_candidates_similarity",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_entity_merge_candidates_org_id_status",
        "entity_merge_candidates",
        ["org_id", "status"],
    )
    op.create_index(
        "ix_entity_merge_candidates_org_id_created_at",
        "entity_merge_candidates",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_entity_merge_candidates_org_id",
        "entity_merge_candidates",
        ["org_id"],
    )
    op.create_index(
        "ix_entity_merge_candidates_trace_id",
        "entity_merge_candidates",
        ["trace_id"],
    )


def downgrade() -> None:
    """Downgrade schema.

    **有损**：整表删除 ⇒ 已产出的合并候选（含人工队列）全部丢失。这是「降级即有损」
    的诚实登记——真要回滚先在业务侧导出候选清单。
    """
    op.drop_index(
        "ix_entity_merge_candidates_trace_id", table_name="entity_merge_candidates"
    )
    op.drop_index(
        "ix_entity_merge_candidates_org_id", table_name="entity_merge_candidates"
    )
    op.drop_index(
        "ix_entity_merge_candidates_org_id_created_at",
        table_name="entity_merge_candidates",
    )
    op.drop_index(
        "ix_entity_merge_candidates_org_id_status",
        table_name="entity_merge_candidates",
    )
    op.drop_table("entity_merge_candidates")
