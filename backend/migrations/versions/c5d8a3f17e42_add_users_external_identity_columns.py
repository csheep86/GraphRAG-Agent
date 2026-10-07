"""add users external identity columns (P2-C / 子任务 ② / 预留)

Revision ID: c5d8a3f17e42
Revises: f3a91c2d6b70
Create Date: 2026-10-07 12:10:00.000000

**P2-C 批次**：给 ``users`` 补 ``issuer`` / ``subject`` 两列 —— 外部身份源的查找键。

**两列当前 0 消费者**（必须写在迁移里，否则半年后没人知道它为什么存在）：
本地登录按 ``username`` 查（`app/services/auth/login.py`），**不**读这两列。
它们是为「接缝 1 第二实现（AD / LDAP / OIDC）」留的：启用后查找键由
``username`` 改为 ``(issuer, subject)``，``LocalAuthProvider`` 即 ``issuer='local'``。

两列**均可空**（功能预留原则第 4 条：预留字段一律 nullable 且不进 API 契约）：
- 可空 ⇒ 存量行不需要回填；
- 不进契约 ⇒ ``export_openapi.py --check`` 必须仍是零 diff；
- 启用条件登记在 ``docs/adr/0004-integration-seams.md``（功能预留原则第 5 条）。

**不做的事**：不建索引、不加唯一约束 —— 它们还没有任何读取方，
加了就是"看起来被用着、实际没人查"的假差异（预留纪律第 6 条，
历史病例 ``task_retry_multiplier``）。等查找键真的切换过去，索引随那一批再建。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d8a3f17e42"
down_revision: Union[str, Sequence[str], None] = "f3a91c2d6b70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("issuer", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("subject", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "subject")
    op.drop_column("users", "issuer")
