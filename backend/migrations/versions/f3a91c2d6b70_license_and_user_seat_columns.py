"""add licenses + users seat columns (DR-C1 / ADR-0006 §2.4 / §3.1)

Revision ID: f3a91c2d6b70
Revises: b7c4e1f9a2d3
Create Date: 2026-10-06 22:10:00.000000

**P4 批次**：DR-C1 License 控制的存储落点，两件事：

1. 建 ``licenses`` 表 —— 字段逐字照 ``docs/adr/ADR-0006-license-control.md`` §3.1。
   ⚠️ **实例级表，显式豁免 RLS**（ADR-0006 §3.1「与 ``roles`` 全局字典表同理」）：
   - 表内**没有** ``org_id`` ⇒ 按 ``app/db/rls.py`` 的推导口径，它本就不进租户表清单
     （不需要建 ``tenant_isolation`` 策略）；
   - 同时登记进 ``RLS_EXEMPT_TABLES`` 与模型上的 ``__rls_exempt__``
     ⇒ 由 G-24 同款断言双向盯住；新增豁免表属破坏性变更，连带更新了
     ``tests/test_guardrails_rls.py`` 的豁免集合断言。
   - 表内**禁止**写入任何租户业务数据（ADR-0006 §3.1）。

2. ``users`` 补 ``activated_at`` / ``disabled_at`` 两列 —— **席位口径的物质基础**。
   席位 = ``activated_at IS NOT NULL AND disabled_at IS NULL``（ADR-0006 §2.4），
   而这两列此前**根本不存在**（P6-P0 实测）⇒ 不补则 License 算不出席位数。
   两列均可空：``activated_at`` 由**首次成功登录**回填（登录属 P2-C），
   ``disabled_at`` 由停用动作写入 ⇒ 此刻全表为 NULL，即**当前占席位 0 人**。

类型收敛沿用本仓惯例：TEXT → ``String(n)`` / ``Text``，主键 Uuid，
``modules`` 用 ``JSON``（同 ``user_roles.doc_scope`` 的方言中立口径，ADR-0003 §3.7）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a91c2d6b70"
down_revision: Union[str, Sequence[str], None] = "b7c4e1f9a2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: ADR-0006 §3.1：``status`` 四档
_LICENSE_STATUSES = "('active', 'expired', 'revoked', 'superseded')"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "licenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("license_id", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False),
        sa.Column("max_orgs", sa.Integer(), nullable=False),
        sa.Column("max_seats", sa.Integer(), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN {_LICENSE_STATUSES}", name="ck_licenses_status"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_licenses")),
        sa.UniqueConstraint("license_id", name="uq_licenses_license_id"),
    )

    # 席位口径（ADR-0006 §2.4）：两列都可为 NULL，缺省即「未激活 / 未停用」
    op.add_column(
        "users",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "activated_at")
    op.drop_table("licenses")
