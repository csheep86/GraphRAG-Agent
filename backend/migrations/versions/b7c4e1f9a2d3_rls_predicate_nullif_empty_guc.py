"""rls_predicate_nullif_empty_guc（DR-B4 / ADR-0003 §3.3）

把 14 张租户表的 ``tenant_isolation`` 策略谓词从

    org_id = current_setting('app.current_org', true)::uuid

改成

    org_id = nullif(current_setting('app.current_org', true), '')::uuid

**为什么要改（P3-C，2026-10-04 实测踩到）**：``app.current_org`` 是**自定义** GUC，
而自定义 GUC 在被 ``SET LOCAL`` 用过之后，事务结束时会还原到它的 **reset 值**——
那是**空串 ``''``**，不是"未设置"。于是池化连接上的**第二次**及以后的请求里，
若有一条路径没绑 org 就去查租户表，谓词里的 ``''::uuid`` 会抛

    ERROR 22P02: invalid input syntax for type uuid: ""

也就是 **500**，而不是设计文档（ADR-0003 §3.3 / ``app/db/rls.py`` 第 3 条）承诺的
「比较为 NULL ⇒ 一行都不命中」。且它只在"该连接跑过一次绑 org 的事务之后"才出现
⇒ **首次请求正常、第二次起崩**，是最难复现的那一类故障。

``nullif(..., '')`` 把空串与 NULL 统一退化成 NULL ⇒ 两种形态都回到 **fail-closed（0 行）**，
不再报错。这不是"更宽松"：未绑 org 的查询依然**一行都读不到**，只是不再以 500 的形式暴露。

⚠️ **表清单写死在迁移里，不 import 应用代码**（与 8210590e76a5 同款理由）：迁移是会被
反复重放的历史产物，让它读运行时模块会导致"同一份迁移在不同代码版本下落出不同结果"。
与 ``app/db/rls.py::TENANT_TABLES`` 的漂移由 **G-26** 机械盯住。

Revision ID: b7c4e1f9a2d3
Revises: 8210590e76a5
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c4e1f9a2d3"
down_revision: Union[str, Sequence[str], None] = "8210590e76a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 租户表清单（与 app/db/rls.py::TENANT_TABLES 一致，G-26 漂移断言盯着）
TENANT_TABLES: tuple[str, ...] = (
    "affiliation_suspicions",
    "affiliation_tasks",
    "audit_log",
    "documents",
    "domain_events",
    "entity_merge_candidates",
    "external_refs",
    "kg_versions",
    "ontology_schemas",
    "qa_logs",
    "relation_expiry_policies",
    "unaligned_subjects",
    "user_roles",
    "users",
)

POLICY_NAME = "tenant_isolation"

#: 新谓词：空串与 NULL 都退化为 NULL ⇒ 不命中（fail-closed，不抛 22P02）
PREDICATE = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"

#: 旧谓词（仅 downgrade 用，用于**精确回退**到本迁移之前的状态）
OLD_PREDICATE = "org_id = current_setting('app.current_org', true)::uuid"


def _apply(predicate: str) -> None:
    for table in TENANT_TABLES:
        # ENABLE / FORCE 一并重写一遍：本迁移也可能被跑在"只建了表、没装 RLS"的库上
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def upgrade() -> None:
    """逐张表幂等重建策略（**可重复执行**）。"""
    _apply(PREDICATE)


def downgrade() -> None:
    """回退到本迁移之前的谓词（**不留半成品**：策略仍在，只是换回旧表达式）。"""
    _apply(OLD_PREDICATE)
