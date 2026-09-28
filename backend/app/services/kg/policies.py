"""有效期策略表的读取（ADR-0005 §6 L1）。

**这是 ``relation_expiry_policies`` 表的唯一消费者**：表存在而无人读，就与那些
"预留了但没人用"的字段没区别——本项目不提交无消费者的东西（check_seams 判据 2
对 ``settings.*`` 的要求，同一种病）。

设计取舍：**一次查询，零 IO 判定**。``load_expiry_policies`` 把该租户的全部策略行
读进来构造闭包，仲裁在逐条关系中调用时不再碰数据库——构建一份图谱要仲裁上千条关系，
逐条查库会把构建拖成 N+1。
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RelationExpiryPolicy

#: 兜底行的 ``relation_type`` 取值：查不到具体类型时用它的策略
FALLBACK_RELATION_TYPE = "*"
#: 唯一当前（新事实封旧事实）。另一档 ``append_only``（多值并存）是**默认行为**：
#: 查不到就按并存处理，不需要在这里再定义一个没人读取的常量
POLICY_SINGLE_CURRENT = "single_current"


def load_expiry_policies(db: Session, *, org_id: UUID) -> Callable[[str], bool]:
    """读出该租户的策略，返回一个 ``relation_type → 是否唯一当前`` 的判定函数。

    判定顺序：具体 ``relation_type`` → 兜底行 ``'*'`` → 保守默认 **并存**。
    默认取并存是有意的：策略没配就封旧边，会让没人确认过的历史静默消失。

    :param db: 只读会话（本函数不提交）。
    :param org_id: 租户 id（ADR-0003 §3.1：所有查询以 org_id 打头）。
    """
    rows = db.execute(
        select(RelationExpiryPolicy.relation_type, RelationExpiryPolicy.policy).where(
            RelationExpiryPolicy.org_id == org_id
        )
    ).all()
    policies = {str(row[0]): str(row[1]) for row in rows}

    def is_single_current(relation_type: str) -> bool:
        policy = policies.get(relation_type) or policies.get(FALLBACK_RELATION_TYPE)
        return policy == POLICY_SINGLE_CURRENT

    return is_single_current
