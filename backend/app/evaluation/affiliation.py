"""M4 疑点输出 → 评测 `Finding` 的**归一化**（真机 id 空间的适配层）。

为什么单开这一层：**gold 与真机输出的 id 空间必须逐字对得上，否则召回恒为 0**。
2026-10-03 真机取样（`AffiliationService.detect(kg_version=affiliation-demo-v1)`）
确认了三件事，本模块就是它们的落点：

1. 成员 id 是**图节点 id**：``SUBJECT:<税号>`` / ``CONTRACT:<合同号>`` /
   ``INVOICE:<发票号>`` / ``VOUCHER:<凭证号>``；
2. ``shared_*`` 三类返回的 entities 是 ``[主体A, 主体B, 共享节点]`` ——
   共享节点（``ADDRESS:`` / ``PHONE:`` / ``LEGALPERSON:``）是「**为什么命中**」的证据，
   **不是**「谁被牵连」的成员 ⇒ **必须滤掉**，否则 gold（2 个成员）与真机（3 个）
   永远对不上；
3. ``amount_mismatch`` 的成员是**三张单据**，不是主体（gold 初版写主体 ⇒ 同病）。

滤除规则由数据集自己声明（``gold-affiliation-v1.json`` 的
``non_member_prefixes``），**不写死在本模块**——换语料时改数据不改代码。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.evaluation.metrics import Finding

#: 兜底默认值（仅当数据集未声明时使用；数据集已声明 ⇒ 以数据为准）。
DEFAULT_NON_MEMBER_PREFIXES: tuple[str, ...] = (
    "ADDRESS:",
    "PHONE:",
    "LEGALPERSON:",
)


def is_member(node_id: str, non_member_prefixes: Sequence[str]) -> bool:
    """该节点是否算**成员**（共享证据节点 ⇒ 否）。"""
    return not node_id.startswith(tuple(non_member_prefixes))


def to_finding(
    *,
    suspicion_type: str,
    entities: Iterable[str],
    non_member_prefixes: Sequence[str] = DEFAULT_NON_MEMBER_PREFIXES,
) -> Finding:
    """一条真机疑点 → 评测用的组级 `Finding`（过滤共享节点 + 去重排序）。"""
    members = tuple(str(e) for e in entities if is_member(str(e), non_member_prefixes))
    return Finding(type=str(suspicion_type), entity_ids=members)


def findings_from_suspicions(
    suspicions: Iterable[object],
    *,
    non_member_prefixes: Sequence[str] = DEFAULT_NON_MEMBER_PREFIXES,
) -> tuple[Finding, ...]:
    """真机疑点列表 → `Finding` 元组。

    用 ``object`` + 属性取值（``suspicion_type`` / ``entities``）而非具体类型：
    评测侧**不该** import 业务层的 ``Suspicion`` —— 那是耦合，且会让"纯函数"变味。
    """
    findings: list[Finding] = []
    for item in suspicions:
        suspicion_type = getattr(item, "suspicion_type", None)
        entities = getattr(item, "entities", None)
        if suspicion_type is None or entities is None:
            raise TypeError(f"疑点对象缺少 suspicion_type / entities: {item!r}")
        findings.append(
            to_finding(
                suspicion_type=str(suspicion_type),
                entities=(str(e) for e in entities),
                non_member_prefixes=non_member_prefixes,
            )
        )
    return tuple(findings)
