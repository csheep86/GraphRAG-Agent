"""add roles / user_roles (DR-B9 / M5 §4.2 + §4.3)

Revision ID: 7d2e91f4ab35
Revises: a1f3c9d27b08
Create Date: 2026-10-03 10:00:00.000000

**P2 批次 B**：建 RBAC 三粒度的两张表。

- ``roles``：**全局角色字典表**，按 ADR-0003 §3.1 第 9 行**显式豁免 RLS**
  （豁免声明写在 ``app/db/models.py::Role`` 的 docstring 里；三条机械断言
  在 ``tests/test_guardrails_compliance.py`` 的 G-24 组）。
  ⇒ 本表**刻意不带 ``org_id``**，加了就是「字典表被租户业务污染」，CI 必红。
- ``user_roles``：租户授权表，带 ``org_id`` 且**复合索引以 ``org_id`` 打头**
  （ADR-0003 §3.1 第 1 条）；``doc_scope`` / ``scene_scope`` 承载文档级 / 场景级粒度。

**幂等**：``upgrade`` / ``downgrade`` 均以 ``inspect`` 先判表是否存在，
重复执行（例如现场重放、或两实例并发跑到同一版本）不会报 "already exists"。
**种子**：``roles`` 的 4 种系统预置角色在此播种（按 ``name`` 去重，可重放）。
``user_roles`` **不播种**——真实账号链路归 P2-C，本批不编造授权数据。

⚠️ **本批不做 RLS 策略**（DR-B4 归 **P3**）：这里一行策略都不写，只做豁免**登记**。
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services.rbac.roles import PRESET_ROLES


# revision identifiers, used by Alembic.
revision: str = "7d2e91f4ab35"
down_revision: Union[str, Sequence[str], None] = "a1f3c9d27b08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if not _has_table(bind, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=32), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "name IN ('admin', 'auditor', 'analyst', 'viewer')",
                name="ck_roles_name",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
            sa.UniqueConstraint("name", name="uq_roles_name"),
        )

    if not _has_table(bind, "user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("org_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("role_id", sa.Uuid(), nullable=False),
            sa.Column("doc_scope", sa.JSON(), nullable=True),
            sa.Column("scene_scope", sa.JSON(), nullable=True),
            sa.Column("granted_by", sa.Uuid(), nullable=False),
            sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
            sa.UniqueConstraint(
                "org_id",
                "user_id",
                "role_id",
                name="uq_user_roles_org_user_role",
            ),
        )
        op.create_index(
            op.f("ix_user_roles_org_id"), "user_roles", ["org_id"], unique=False
        )
        op.create_index(
            "ix_user_roles_org_id_user_id",
            "user_roles",
            ["org_id", "user_id"],
            unique=False,
        )
        op.create_index(
            "ix_user_roles_org_id_role_id",
            "user_roles",
            ["org_id", "role_id"],
            unique=False,
        )

    # 种子：4 种系统预置角色（按 name 去重 ⇒ 可重放）。
    # 真源是 ``app/services/rbac/roles.py::PRESET_ROLES``；这里直接用它，
    # 避免迁移里再抄一份字面量——抄了就会有一天和代码不一致。
    existing = {
        row[0] for row in bind.execute(sa.text("SELECT name FROM roles")).all()
    }
    for name, description in PRESET_ROLES:
        if name in existing:
            continue
        bind.execute(
            sa.text("INSERT INTO roles (id, name, description) VALUES (:id, :n, :d)"),
            {"id": uuid.uuid4(), "n": name, "d": description},
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if _has_table(bind, "user_roles"):
        op.drop_index("ix_user_roles_org_id_role_id", table_name="user_roles")
        op.drop_index("ix_user_roles_org_id_user_id", table_name="user_roles")
        op.drop_index(op.f("ix_user_roles_org_id"), table_name="user_roles")
        op.drop_table("user_roles")

    if _has_table(bind, "roles"):
        op.drop_table("roles")
