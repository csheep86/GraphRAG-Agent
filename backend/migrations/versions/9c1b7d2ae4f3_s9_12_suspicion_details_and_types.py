"""Sprint 9.12 批次 C2：`affiliation_suspicions` 加 `details` 列 + 放宽类型约束。

**为什么必须显式迁移**：`create_all` 对**已存在**的表不做任何 ALTER——线上库会一直
停在旧结构上：代码写 `details` 报 no such column，写入 `cycle` / `amount_mismatch`
被旧 CheckConstraint 拒。**没有迁移 = 功能在真机上根本不生效**。

两件事（顺序不可换——先加列再动约束，回滚时反过来）：

1. 加 `details JSON`（可空）：`amount_mismatch` 的三方金额明细（spec §3 验收 5 要求
   「差额 + 三方各自金额」）。其余类型写 `None`——**不**为了非空而塞 `{}`。
2. `ck_affiliation_suspicions_type` 放宽为 6 类：新增 `shared_phone` / `cycle` /
   `amount_mismatch`（判据已冻结在 `specs/m4-affiliation-detection.md` §4.7.2）。

**方言**：用 `batch_alter_table`——SQLite 不支持 `ALTER TABLE DROP CONSTRAINT`，
batch 会走「建新表 + 搬数据 + 改名」的 recreate 路径，PostgreSQL 则原地 DDL。

Revision ID: 9c1b7d2ae4f3
Revises: 4e7759c33526
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c1b7d2ae4f3"
down_revision: str | None = "4e7759c33526"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TYPE_CHECK = (
    "suspicion_type IN ('shared_legal_rep', 'shared_address', 'missing_check_in', "
    "'shared_phone', 'cycle', 'amount_mismatch')"
)
OLD_TYPE_CHECK = (
    "suspicion_type IN ('shared_legal_rep', 'shared_address', 'missing_check_in')"
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("affiliation_suspicions") as batch_op:
        batch_op.add_column(sa.Column("details", sa.JSON(), nullable=True))
        batch_op.drop_constraint("ck_affiliation_suspicions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_affiliation_suspicions_type", NEW_TYPE_CHECK
        )


def downgrade() -> None:
    """Downgrade schema.

    **有损**：已落库的 `cycle` / `amount_mismatch` / `shared_phone` 疑点在收窄约束后
    **无法再写入**，且 `details` 列被丢弃。这是「降级即有损」的诚实登记，
    不做假装无损的妥协——真要回滚先在业务侧把这些疑点归档。
    """
    with op.batch_alter_table("affiliation_suspicions") as batch_op:
        batch_op.drop_constraint("ck_affiliation_suspicions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_affiliation_suspicions_type", OLD_TYPE_CHECK
        )
        batch_op.drop_column("details")
