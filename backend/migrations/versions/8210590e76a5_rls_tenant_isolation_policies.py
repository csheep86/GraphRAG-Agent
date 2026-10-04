"""rls_tenant_isolation_policies（DR-B4 / ADR-0003 §3.2）

对**每一张租户表**落 RLS：``ENABLE`` + ``FORCE`` + ``tenant_isolation`` 策略
（``USING`` / ``WITH CHECK`` 同为 ``org_id = current_setting('app.current_org',
true)::uuid``）。

为什么必须 ``FORCE``：不 FORCE 则**表 owner 默认绕过策略** ⇒ RLS 形同虚设
（ADR-0003 §3.2 要求 1）。

为什么未设 org 时是安全的：``current_setting(..., true)`` 在未设置时返回 NULL，
与 ``org_id`` 比较的结果为 NULL ⇒ **一行都不命中**（fail-closed）。

⚠️ **表清单写死在迁移里，不 import 应用代码**：迁移是会被反复重放的历史产物，
让它读运行时模块会导致「同一份迁移在不同代码版本下落出不同结果」。
与 ``app/db/rls.py::TENANT_TABLES`` 的一致性由 **G-26 的漂移断言**机械盯住
（新增带 ``org_id`` 的表而没改这里 ⇒ 那条断言必红）。

Revision ID: 8210590e76a5
Revises: 7d2e91f4ab35
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8210590e76a5"
down_revision: Union[str, Sequence[str], None] = "7d2e91f4ab35"
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

#: 唯一豁免（全局字典表，无租户维度）——**不得扩大**（G-24 三条断言）
RLS_EXEMPT_TABLES: tuple[str, ...] = ("roles",)

POLICY_NAME = "tenant_isolation"
PREDICATE = "org_id = current_setting('app.current_org', true)::uuid"


def upgrade() -> None:
    """逐张表：ENABLE → FORCE →（幂等重建）策略。**可重复执行**。"""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # ⚠️ 不可漏：不 FORCE 则表 owner 绕过策略（ADR-0003 §3.2 要求 1）
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
        )

    # 豁免表**显式**保持无策略：downgrade 之后若有人误给它加策略，
    # 「豁免集合没变」这条断言照样绿，只有真的写一遍才算数。
    for table in RLS_EXEMPT_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")


def downgrade() -> None:
    """删策略 + 关 RLS（**不留半成品**）。"""
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
