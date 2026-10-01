"""add users (DR-B13 / M5 §4.1)

Revision ID: a1f3c9d27b08
Revises: b3e5a1c70d42
Create Date: 2026-10-01 21:05:00.000000

**P2 批次 A**：建 `users` 表——DR-D9(SSO) / DR-B9(RBAC) / DR-C1(License 席位)
三者的**共同前置**（DR-B13，RK-1 裁决：前置到 P2 第一步，不随 M5）。

字段逐字照 ``specs/m5-permission-audit.md`` §4.1 的 7 列；类型按本仓惯例收敛
（spec 的 TEXT → ``String(n)``、主键 Uuid），与 ADR-0003 §3.1 差异表 A9 同源。
索引三点：``username`` 唯一约束（spec §4.1）、``org_id`` 单列索引、
``ix_users_org_id_status``（**复合索引必须 org_id 打头**，ADR-0003 §3.1 第 1 条）。

⚠️ 本批**不**给 ``documents.uploaded_by`` / ``ontology_schemas.confirmed_by_user``
补外键：演示库已有真实数据，加 FK 属不可逆的数据清洗，登记为本批遗留，待 P2-C
首次真实账号链路一并处理。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f3c9d27b08"
down_revision: Union[str, Sequence[str], None] = "b3e5a1c70d42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="ck_users_status"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index(op.f("ix_users_org_id"), "users", ["org_id"], unique=False)
    op.create_index(
        "ix_users_org_id_status", "users", ["org_id", "status"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_org_id_status", table_name="users")
    op.drop_index(op.f("ix_users_org_id"), table_name="users")
    op.drop_table("users")
