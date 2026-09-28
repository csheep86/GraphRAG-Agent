"""`GET /attendance/compliance/scan` 路由测试（Sprint 9.5 批次 C3）。

打桩约定同 `test_graph_overview_and_entity.py`：
- `NEO4J_URI` 指向不可达端口（`conftest.py`）⇒ GraphService 确定性抛
  :class:`GraphUnavailableError`；
- 需要「图谱可用」的用例一律 monkeypatch `scan_attendance_compliance`。

**为什么打在服务层方法上而不是更深处**：本测试验的是**路由层契约**
（字段集 / 过滤语义 / 错误码映射），规则引擎本身的数值由
`test_rules_engine.py` 覆盖——两层各司其职，不重复也不越界。
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.schemas.compliance import ComplianceScanResponse
from app.services.graphs import GraphService, GraphUnavailableError
from app.services.rules import (
    ComplianceReport,
    ComplianceScanError,
    RiskFinding,
    RuleValue,
    RuleValueBook,
)

PATH = "/api/v1/attendance/compliance/scan"

#: 契约字段集（`contracts/openapi.yaml::ComplianceScanResponse`）
RESPONSE_KEYS = {
    "kg_version",
    "as_of",
    "employee_count",
    "rule_values",
    "unresolved",
    "skipped_rules",
    "findings",
    "total",
    "trace_id",
}


def _report() -> ComplianceReport:
    """一个含 2 条风险（不同员工 / 不同规则 / 不同等级）的报告。"""
    return ComplianceReport(
        kg_version="attendance-demo-v1",
        as_of=date(2026, 10, 31),
        employee_count=40,
        findings=(
            RiskFinding(
                rule="monthly_overtime_exceeded",
                employee_id="E002",
                employee_name="李静",
                department="生产部",
                level="high",
                title="月加班超限",
                observed=42.0,
                threshold=36.0,
                unit="小时",
                calculation="月排班 216h − 月标准 174h = 加班 42h > 上限 36h",
                evidence=("SHIFT:S00023",),
                policy_refs=("graph:clause:ent_c974307a4bd5",),
                work_time_system="综合计算工时制",
            ),
            RiskFinding(
                rule="core_window_absence",
                employee_id="E003",
                employee_name="王强",
                department="研发部",
                level="medium",
                title="弹性时段越界",
                observed=7.0,
                threshold=5.0,
                unit="次",
                calculation="核心时段未在岗 7 次 > 阈值 5 次",
                evidence=("ATTENDANCE_RECORD:A00046",),
                policy_refs=("document:doc:worktime-system-rules:L45",),
                work_time_system="标准工时制",
            ),
        ),
        rule_values=RuleValueBook(
            values=(
                RuleValue(
                    key="monthly_overtime_cap",
                    label="月加班上限",
                    value=36.0,
                    unit="小时",
                    source="graph",
                    reference="clause:ent_d165867ab6e8",
                    evidence="每月加班时间不得超过 36 小时",
                ),
            ),
            unresolved=("weekly_hours_cap",),
        ),
        skipped_rules=("weekly_hours_exceeded",),
    )


def _patch_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        GraphService.instance(),
        "scan_attendance_compliance",
        lambda **_kwargs: _report(),
    )


def test_scan_returns_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Neo4j 不可达 → 501 `NOT_IMPLEMENTED`（库都连不上，不是「没有风险」）。"""
    response = client.get(PATH, headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_scan_returns_409_when_no_attendance_facts(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """版本里没有考勤事实 → 409 `COMPLIANCE_NO_FACTS`（**不是** 501，也不是 200 空清单）。

    语义差别很关键：200 + 空清单会被前端读成「全员合规」，
    而真实情况是「根本没数据可算」——必须让调用方看得见这个区别。
    """

    def _raise(**_kwargs: object) -> ComplianceReport:
        raise ComplianceScanError("no EMPLOYEE nodes")

    monkeypatch.setattr(GraphService.instance(), "scan_attendance_compliance", _raise)

    response = client.get(PATH, headers=dev_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "COMPLIANCE_NO_FACTS"


def test_scan_200_returns_contract_fields(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常路径：契约字段集 + 规则值带出处 + 未解析 / 跳过规则显式可见。"""
    _patch_report(monkeypatch)

    response = client.get(PATH, headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_KEYS
    assert body["kg_version"] == "attendance-demo-v1"
    assert body["as_of"] == "2026-10-31"
    assert body["employee_count"] == 40
    assert body["total"] == 2

    value = body["rule_values"][0]
    assert value["key"] == "monthly_overtime_cap"
    assert value["source"] == "graph"
    assert "36" in value["evidence"]

    # 无判据即跳过 —— 必须在响应里看得见，而不是悄悄少算一条
    assert body["unresolved"] == ["weekly_hours_cap"]
    assert body["skipped_rules"] == ["weekly_hours_exceeded"]

    finding = body["findings"][0]
    assert finding["rule"] == "monthly_overtime_exceeded"
    assert finding["rule_label"] == "月加班超限"
    assert finding["level"] == "high"
    assert finding["observed"] == 42.0
    assert finding["threshold"] == 36.0
    assert finding["evidence"] == ["SHIFT:S00023"]


def test_scan_filters_findings_but_keeps_rule_values(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`employee_id` / `rule` / `level` 只过滤 `findings`；`rule_values[]` 始终全量。

    判据不因过滤而消失——否则前端在「只看某人」时就没法解释阈值从哪来。
    """
    _patch_report(monkeypatch)

    response = client.get(PATH, headers=dev_headers, params={"level": "high"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["employee_id"] for item in body["findings"]] == ["E002"]
    assert len(body["rule_values"]) == 1  # 判据全量保留

    response = client.get(PATH, headers=dev_headers, params={"employee_id": "E003"})
    assert response.json()["total"] == 1
    assert response.json()["findings"][0]["rule"] == "core_window_absence"

    response = client.get(
        PATH, headers=dev_headers, params={"rule": "consecutive_attendance"}
    )
    assert response.json()["total"] == 0


def test_scan_accepts_as_of(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`as_of` 必须透传到服务层（它决定调休「临期升级」的判据）。"""
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        GraphService.instance(),
        "scan_attendance_compliance",
        lambda **kwargs: (seen.update(kwargs), _report())[1],
    )

    response = client.get(PATH, headers=dev_headers, params={"as_of": "2026-12-15"})

    assert response.status_code == 200
    assert seen["as_of"] == date(2026, 12, 15)


def test_scan_wraps_unexpected_graph_error_as_501(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """图查询异常统一映射为 501，且与 `routes/graph.py` 的 detail 结构一致。

    `detail` 只含 `blocked_by` / `hint` / `reason` 三个结构化字段，
    **不含**连接串 / 凭据（CODEBUDDY.md 安全底线）。
    """

    def _raise(**_kwargs: object) -> ComplianceReport:
        raise GraphUnavailableError("Neo4j 查询失败: 内部细节")

    monkeypatch.setattr(GraphService.instance(), "scan_attendance_compliance", _raise)

    response = client.get(PATH, headers=dev_headers)

    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert set(body["detail"]) == {"blocked_by", "hint", "reason"}
    assert "Neo4j" in body["detail"]["blocked_by"]


def test_response_model_rejects_unknown_rule() -> None:
    """契约枚举是硬约束：未登记的规则进不了响应（前端类型才可靠）。"""
    with pytest.raises(ValueError):
        ComplianceScanResponse(
            kg_version="v",
            as_of=date(2026, 10, 31),
            employee_count=1,
            rule_values=[],
            unresolved=[],
            skipped_rules=[],
            findings=[
                {
                    "rule": "some_unregistered_rule",
                    "rule_label": "x",
                    "employee_id": "E1",
                    "employee_name": "x",
                    "department": "x",
                    "work_time_system": "x",
                    "level": "high",
                    "title": "x",
                    "observed": 1.0,
                    "threshold": 0.0,
                    "unit": "x",
                    "calculation": "x",
                    "policy_refs": [],
                    "evidence": [],
                }
            ],
            total=1,
            trace_id="t",
        )
