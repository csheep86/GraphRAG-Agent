"""add cost_metrics stage column (X-6)

P6-V2（2026-10-09）：``cost_metrics`` 此前**只有 M3 问答在写**，M2 抽取侧的 token
只在日志里打点 ⇒ ``single_doc_cost`` 的分子缺一半（偏离 **X-6** 的起因）。

本迁移做两件事，**少一件都不成立**：

1. 加 ``stage`` 列（``extraction`` / ``answer``），既有行回填 ``answer`` ——
   它们本来就是问答侧写的，回填不是"猜"，是**把已知事实落到新列上**；
2. 把唯一约束从 ``(org_id, metric_date)`` 换成 ``(org_id, metric_date, stage)``。
   **只加列不改约束**是最容易漏的一处：第二次写同日不同 stage 会撞 ``UNIQUE``，
   症状是抽取侧**静默写不进去**（``cost_metrics`` 表看起来一切正常）。

**名字里刻意不含 ``_rls_``**：``test_g26_migration_table_list_matches_metadata``
会 glob ``*_rls_*.py`` 并与租户表清单比对，本迁移改的是**列**不是租户表集合，
不该被那条断言收编（误改名会让 G-26 的警戒范围失真）。

回滚语义：**``stage <> 'answer'`` 的行会被删掉** —— 旧形状装不下它们
（``UNIQUE (org_id, metric_date)`` 无法表示同日两个 stage）。这是**有意**的数据
取舍，不是漏写，代价在此显式交代：抽取侧记的账在重新评审之前不保留。

落库 Replication / 回滚：</br>
- 升级：``alembic upgrade head``（生产按 ``docs/deployment-spec.md`` §7.2 手动执行）；
- 回滚：``alembic downgrade -1``。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1f7c2b93d04"
down_revision: str | None = "df5ec5c9e1b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "cost_metrics"
#: 与 ``app/db/models.py`` 的 ``COST_STAGE_*`` 逐字一致（这里不能 import 应用代码）
_STAGE_ANSWER = "answer"
_OLD_UNIQUE = "uq_cost_metrics_org_date"
_NEW_UNIQUE = "uq_cost_metrics_org_date_stage"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "stage",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text(f"'{_STAGE_ANSWER}'"),
        ),
    )
    # server_default 已经把既有行填好；这条 UPDATE 是**显式交代**意图——
    # 万一将来 server_default 被摘掉，回填仍然发生。
    op.execute(f"UPDATE {_TABLE} SET stage = '{_STAGE_ANSWER}' WHERE stage IS NULL")

    op.drop_constraint(_OLD_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(_NEW_UNIQUE, _TABLE, ["org_id", "metric_date", "stage"])


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE stage <> '{_STAGE_ANSWER}'")
    op.drop_constraint(_NEW_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(_OLD_UNIQUE, _TABLE, ["org_id", "metric_date"])
    op.drop_column(_TABLE, "stage")
