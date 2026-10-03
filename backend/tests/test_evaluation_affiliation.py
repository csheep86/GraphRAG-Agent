"""M4 真机输出 → 评测 `Finding` 的归一化（`app/evaluation/affiliation.py`）。

这里钉的是**最容易错、错了最安静**的一条规则：
``shared_*`` 疑点的 entities 是 ``[主体A, 主体B, 共享节点]``，而 gold 的成员是
**2 个主体**。共享节点（``ADDRESS:`` / ``PHONE:`` / ``LEGALPERSON:``）若被算进成员，
gold 与真机**永远对不上** ⇒ 召回恒为 0 ⇒ 看起来像"检测器坏了"。
2026-10-03 就是靠真机取样才发现 gold 初版连 id 空间都写错了（supplier_id）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.evaluation.affiliation import (
    DEFAULT_NON_MEMBER_PREFIXES,
    findings_from_suspicions,
    is_member,
    to_finding,
)
from app.evaluation.dataset import load_affiliation_gold
from app.evaluation.metrics import (
    Finding,
    findings_false_positive_rate,
    findings_recall,
)


@dataclass(frozen=True)
class _FakeSuspicion:
    """鸭子类型替身（评测侧**不该** import 业务层的 ``Suspicion``）。"""

    suspicion_type: str
    entities: tuple[str, ...]


def test_shared_node_is_not_a_member() -> None:
    assert is_member("SUBJECT:91440106MA03Q7J4MX", DEFAULT_NON_MEMBER_PREFIXES)
    for node_id in (
        "ADDRESS:3aac4fb8a88367b1",
        "PHONE:c1ef0a73c55ec858",
        "LEGALPERSON:c9979ca1e21ad98e",
    ):
        assert not is_member(node_id, DEFAULT_NON_MEMBER_PREFIXES)


def test_shared_suspicion_collapses_to_two_subjects() -> None:
    """真机返回 3 个 id ⇒ 归一化后成员只剩 2 个主体（共享节点被滤掉）。"""
    finding = to_finding(
        suspicion_type="shared_legal_rep",
        entities=(
            "SUBJECT:91440106MA03Q7J4MX",
            "SUBJECT:91610113MA09H1C7EX",
            "LEGALPERSON:c9979ca1e21ad98e",
        ),
    )
    assert finding.members() == (
        "SUBJECT:91440106MA03Q7J4MX",
        "SUBJECT:91610113MA09H1C7EX",
    )


def test_amount_mismatch_members_are_documents_not_subjects() -> None:
    """``amount_mismatch`` 的成员是**三张单据**（合同 / 发票 / 凭证），不是主体。"""
    finding = to_finding(
        suspicion_type="amount_mismatch",
        entities=("CONTRACT:HT2026-0002", "INVOICE:FP2026-0002", "VOUCHER:PZ2026-0002"),
    )
    assert finding.members() == (
        "CONTRACT:HT2026-0002",
        "INVOICE:FP2026-0002",
        "VOUCHER:PZ2026-0002",
    )


def test_findings_from_suspicions_uses_duck_typing() -> None:
    items = (
        _FakeSuspicion("cycle", ("SUBJECT:A", "SUBJECT:B")),
        _FakeSuspicion("shared_phone", ("SUBJECT:A", "SUBJECT:B", "PHONE:x")),
    )
    assert findings_from_suspicions(items) == (
        Finding("cycle", ("SUBJECT:A", "SUBJECT:B")),
        Finding("shared_phone", ("SUBJECT:A", "SUBJECT:B")),
    )


def test_findings_from_suspicions_rejects_malformed_input() -> None:
    """形状不对 ⇒ 报错（静默跳过会让"检测没跑起来"变成"没有疑点"）。"""
    with pytest.raises(TypeError):
        findings_from_suspicions([object()])


# ---------------------------------------------------------------------------
# 真机输出快照（2026-10-03，kg_version=affiliation-demo-v1）
# ---------------------------------------------------------------------------
#: **不是构造数据**：这是 ``AffiliationService.detect()`` 当天的真实返回，逐条抄录。
#: 作用：gold 或归一化规则任何一方漂移 ⇒ 这里变红（召回 1.00 的依据就是它）。
_LIVE_SNAPSHOT = (
    _FakeSuspicion(
        "shared_legal_rep",
        (
            "SUBJECT:91440106MA03Q7J4MX",
            "SUBJECT:91610113MA09H1C7EX",
            "LEGALPERSON:c9979ca1e21ad98e",
        ),
    ),
    _FakeSuspicion(
        "shared_address",
        (
            "SUBJECT:91330106MA05N5G2JX",
            "SUBJECT:91500112MA13D6X3AX",
            "ADDRESS:3aac4fb8a88367b1",
        ),
    ),
    _FakeSuspicion(
        "shared_phone",
        (
            "SUBJECT:91110108MA01T2W4XX",
            "SUBJECT:91320506MA12E7Y4BX",
            "PHONE:c1ef0a73c55ec858",
        ),
    ),
    _FakeSuspicion(
        "cycle", ("SUBJECT:91310115MA02R8K5NX", "SUBJECT:91440305MA04P6H3KX")
    ),
    _FakeSuspicion(
        "cycle",
        (
            "SUBJECT:91120116MA10G9B6DX",
            "SUBJECT:91320106MA06M4F1HX",
            "SUBJECT:91420111MA08J2D8FX",
        ),
    ),
    _FakeSuspicion(
        "cycle",
        (
            "SUBJECT:91320506MA12E7Y4BX",
            "SUBJECT:91430104MA14C5W2YX",
            "SUBJECT:91340104MA16A3T9WX",
            "SUBJECT:91370102MA18X1Q7TX",
        ),
    ),
    _FakeSuspicion(
        "amount_mismatch",
        ("CONTRACT:HT2026-0002", "INVOICE:FP2026-0002", "VOUCHER:PZ2026-0002"),
    ),
    _FakeSuspicion(
        "amount_mismatch",
        ("CONTRACT:HT2026-0003", "INVOICE:FP2026-0003", "VOUCHER:PZ2026-0003"),
    ),
    _FakeSuspicion(
        "amount_mismatch",
        ("CONTRACT:HT2026-0004", "INVOICE:FP2026-0004", "VOUCHER:PZ2026-0004"),
    ),
)


def test_gold_matches_live_snapshot_nine_over_nine() -> None:
    """gold 9 组 ⇄ 真机 9 条 **逐组命中**（这是 C2-a = 1.00 的依据）。"""
    gold = load_affiliation_gold()
    detected = findings_from_suspicions(_LIVE_SNAPSHOT)

    recall = findings_recall(gold, detected)
    fpr = findings_false_positive_rate(detected, gold)
    assert recall.value == 1.0
    assert fpr.value == 0.0


def test_gold_and_snapshot_have_the_same_type_profile() -> None:
    by_type: dict[str, int] = {}
    for item in _LIVE_SNAPSHOT:
        by_type[item.suspicion_type] = by_type.get(item.suspicion_type, 0) + 1
    gold_by_type: dict[str, int] = {}
    for finding in load_affiliation_gold():
        gold_by_type[finding.type] = gold_by_type.get(finding.type, 0) + 1
    assert (
        gold_by_type
        == by_type
        == {
            "shared_legal_rep": 1,
            "shared_address": 1,
            "shared_phone": 1,
            "cycle": 3,
            "amount_mismatch": 3,
        }
    )
