"""考勤异常归因单测（Sprint 9.5 批次 C2）。

**为什么测**：置信度是**会被写进演示口径**的百分数。它必须是「确定性加权」的结果，
一旦实现里混进任何随温度 / 顺序漂移的东西，演示就变成编数。故这里把
**权重的分子分母**、**零证据即 0%**、**门禁对比的反向情形**全部钉死。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.rules import (
    ATTENDANCE_SUSPICION_TYPES,
    FINANCE_SUSPICION_TYPES,
    attribute_absence,
    find_anomaly_days,
    suspicion_types_for_domain,
)
from app.services.rules.attribution import (
    CONFIDENCE_ACCEPT,
    EVIDENCE_WEIGHTS,
    search_policy_sentences,
)
from app.services.rules.policy_values import _TextSegment


class _AttrSession:
    """按 Cypher 关键字分派的假会话（门禁按 ``$day`` 参数返回，验证对比逻辑）。"""

    def __init__(
        self,
        *,
        trips: list[dict] | None = None,
        orders: list[dict] | None = None,
        locations: list[dict] | None = None,
        access: dict[str, list[dict]] | None = None,
        anomaly: list[dict] | None = None,
    ) -> None:
        self.trips = trips or []
        self.orders = orders or []
        self.locations = locations or []
        self.access = access or {}
        self.anomaly = anomaly or []

    def run(self, cypher: str, **params: Any) -> list[dict]:
        if "ON_BUSINESS_TRIP" in cypher:
            return self.trips
        if "HANDLED_ORDER" in cypher:
            return self.orders
        if "LOCATED_AT" in cypher:
            return self.locations
        if "SWIPED_AT" in cypher:
            return self.access.get(str(params.get("day")), [])
        if "HAS_ATTENDANCE" in cypher:
            return self.anomaly
        return []


def _trip(status: str = "approved") -> dict:
    return {
        "node_id": "BUSINESS_TRIP:BT-1",
        "destination": "武汉",
        "site": "武汉光谷",
        "status": status,
        "start_date": "2026-10-16",
        "end_date": "2026-10-18",
    }


def _order(closed: bool = True) -> dict:
    return {
        "node_id": "WORK_ORDER:SO-1",
        "dispatched_at": "2026-10-16 09:40",
        "closed_at": "2026-10-16 10:22" if closed else "",
        "site": "武汉光谷",
        "status": "closed" if closed else "dispatched",
    }


def _location(site: str = "武汉光谷") -> dict:
    return {
        "node_id": "LOCATION_RECORD:L1",
        "time": "09:58",
        "site": site,
    }


def _access() -> dict:
    return {"node_id": "ACCESS_RECORD:AC1", "in_time": "08:50", "gate": "东门"}


# --------------------------------------------------------------------------- #
# 域化类型
# --------------------------------------------------------------------------- #
def test_suspicion_types_domain_aware_and_keeps_finance() -> None:
    """域化：考勤域给考勤类型，金融域**保留原有两个**（只加不改）。"""
    assert suspicion_types_for_domain("finance") == FINANCE_SUSPICION_TYPES
    assert suspicion_types_for_domain(None) == FINANCE_SUSPICION_TYPES
    assert suspicion_types_for_domain("attendance") == ATTENDANCE_SUSPICION_TYPES
    with pytest.raises(ValueError):
        suspicion_types_for_domain("unknown-domain")


# --------------------------------------------------------------------------- #
# 置信度 = 确定性加权
# --------------------------------------------------------------------------- #
def test_all_evidence_hits_gives_full_confidence() -> None:
    """四项全命中 ⇒ 1.0（且每项权重都出自 ``EVIDENCE_WEIGHTS``，非模型给分）。"""
    session = _AttrSession(
        trips=[_trip()],
        orders=[_order()],
        locations=[_location()],
        access={"2026-10-15": [_access()]},  # 当日无门禁、前一日有
    )
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E001",
        day="2026-10-16",
        # 「自动补卡」是**制度动作**：结论要声称它，就得给得出制度原句（守 F3）。
        # 本用例走的正是有制度的场景；无出处时的行为由
        # `test_boundary_numeric_provenance.py` 的守卫钉死。
        policy_clauses=[
            _TextSegment(
                text="第九条 缺卡经跨域证据自动取证的，系统自动补卡。",
                source="document",
                reference="doc:attendance:L9",
                order=("attendance", 9),
            ),
        ],
    )
    assert result.confidence == 1.0
    assert result.conclusion == "外勤出勤成立"
    assert result.action == "系统自动补卡"
    assert sum(
        cause.weight for cause in result.causes if cause.matched
    ) == pytest.approx(sum(EVIDENCE_WEIGHTS.values()))


def test_three_main_evidence_hits_gives_87_percent() -> None:
    """三项主证据命中（无门禁对比）⇒ 0.87，对齐 proposal §5.4 的示例值。"""
    session = _AttrSession(
        trips=[_trip()],
        orders=[_order()],
        locations=[_location()],
        access={"2026-10-15": [], "2026-10-16": [_access()]},  # 当日**有**门禁
    )
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E001",
        day="2026-10-16",
    )
    assert result.confidence == pytest.approx(0.87, abs=1e-4)
    assert result.confidence >= CONFIDENCE_ACCEPT
    assert result.causes[-1].matched is False  # 门禁对比不成立


def test_no_evidence_gives_zero_confidence() -> None:
    """零证据 ⇒ 0% 且「不成立」——**不**给一个凑合的中间分。"""
    session = _AttrSession()
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E009",
        day="2026-10-16",
    )
    assert result.confidence == 0.0
    assert result.conclusion == "外勤出勤不成立"
    assert all(not cause.matched for cause in result.causes)


def test_unapproved_trip_does_not_count() -> None:
    """未审批的出差单不算证据（否则"提了申请"就能洗白缺卡）。"""
    session = _AttrSession(trips=[_trip(status="pending")])
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E001",
        day="2026-10-16",
    )
    assert result.causes[0].matched is False
    assert result.confidence == 0.0


def test_unclosed_order_does_not_count() -> None:
    """未闭环的工单不算证据（派单不等于到场）。"""
    session = _AttrSession(trips=[_trip()], orders=[_order(closed=False)])
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E001",
        day="2026-10-16",
    )
    assert result.causes[1].matched is False


def test_location_mismatch_does_not_count() -> None:
    """定位与出差目的地不符 ⇒ 该条不命中（防"人在别处也算外勤"）。"""
    session = _AttrSession(trips=[_trip()], locations=[_location(site="厦门集美")])
    result = attribute_absence(
        session=session,
        kg_version="v",
        org_id="org",
        employee_id="E001",
        day="2026-10-16",
    )
    assert result.causes[2].matched is False


def test_find_anomaly_days_returns_sorted_dates() -> None:
    session = _AttrSession(
        anomaly=[
            {"date": "2026-10-20", "status": "absent"},
            {"date": "2026-10-16", "status": "absent"},
        ]
    )
    assert find_anomaly_days(
        session=session, kg_version="v", org_id="org", employee_id="E001"
    ) == ("2026-10-20", "2026-10-16")


# --------------------------------------------------------------------------- #
# 制度原句溯源
# --------------------------------------------------------------------------- #
def test_search_policy_sentences_returns_source_and_text() -> None:
    """结论文案必须有出处（2025 手工补卡 / 2026 自动补卡 ⇒ 命中多条是**预期**）。"""
    hits = search_policy_sentences(
        keyword="自动补卡",
        documents=(
            _TextSegment(
                text="（2026 版修订）自动补卡不占用月度补卡次数",
                source="document",
                reference="doc:fieldwork:L27",
                order=("fieldwork", 27),
            ),
            _TextSegment(
                text="2025 版要求员工手工提交补卡申请",
                source="document",
                reference="doc:fieldwork:L25",
                order=("fieldwork", 25),
            ),
        ),
    )
    assert len(hits) == 1
    assert hits[0].reference == "doc:fieldwork:L27"
    assert "自动补卡" in hits[0].text
