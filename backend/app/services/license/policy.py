"""License 判定策略（ADR-0006 §2.4 组合维度 + §2.5 分级拒绝）。

**四维度是 AND 关系**，任一不满足即按 §2.5 拒绝：

| # | 维度 | 判定式 | 超限动作 |
|---|---|---|---|
| 1 | 租户数 | ``count(enabled org) > max_orgs`` | 拒绝**新建** org |
| 2 | 席位数 | ``count(activated_at IS NOT NULL AND disabled_at IS NULL) > max_seats`` | 拒绝**新建 / 启用**用户 |
| 3 | 功能模块 | 请求所属模块 ∉ ``modules`` | 拒绝该请求（模块级 403） |
| 4 | 有效期 | ``now`` 越界 | 宽限内只读，超期全量拒绝 |

**"卡增量、保存量"**（§2.5 第 3 行）是本文件最重要的一条纪律：
租户 / 席位超限**只拒新增**，**绝不能锁死只读** —— 拿客户数据当人质
是必然引发交付纠纷的做法。
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import User
from app.services.license.provider import LicenseState

#: 路径前缀 → 功能模块（ADR-0006 §3.3 的 ``modules[]`` 取值）
MODULE_BY_SEGMENT: dict[str, str] = {
    "documents": "m1_ingest",
    "graph": "m2_extract",
    "agent": "m3_graphqa",
    "affiliation": "m4_affiliation",
    "audit": "m5_permission",
    "ontology": "m6_ontology",
    "cost": "m6_ontology",
    "compliance": "m4_affiliation",
}

#: 宽限期内允许的方法（§2.5：只读）
READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def required_module(path: str) -> str | None:
    """请求属于哪个功能模块；``None`` = 不受模块维度约束。

    **为什么未知路径不受约束**：尚未登记模块归属的路径若一律拒绝，
    新增端点会连带被 License 挡住，错误很难定位。宁可**不拦**，也别制造谜题。
    """
    settings = get_settings()
    prefix = settings.api_prefix
    if not path.startswith(prefix):
        return None
    parts = [part for part in path[len(prefix) :].split("/") if part]
    if not parts:
        return None
    return MODULE_BY_SEGMENT.get(parts[0])


def count_seats(session) -> int:  # noqa: ANN001 - Session 类型由调用方保证
    """**席位口径的唯一实现**（ADR-0006 §2.4 维度 2）。

    席位 = 已激活且未停用的用户
    （``activated_at IS NOT NULL AND disabled_at IS NULL``）。

    ⚠️ **当前的边界**：``activated_at`` 由「首次成功登录」回填，而登录属 **P2-C**
    ⇒ 此刻该列全表为 NULL ⇒ **实测占用席位恒为 0**。
    这条只能在 P2-C 之后才具备端到端意义，本批只保证口径正确、可单测。
    """
    return int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.activated_at.is_not(None), User.disabled_at.is_(None))
        )
        or 0
    )


def is_seat_available(session, state: LicenseState) -> bool:  # noqa: ANN001
    """新增一个用户会不会超席位（``+1`` 后仍在 ``max_seats`` 以内才算通过）。"""
    if state.max_seats <= 0:
        return False
    return count_seats(session) + 1 <= state.max_seats


def is_org_available(current_orgs: int, state: LicenseState) -> bool:
    """新增一个租户会不会超上限；预留给 P2-C 的「新建 org」动作调用。"""
    if state.max_orgs <= 0:
        return False
    return current_orgs + 1 <= state.max_orgs
