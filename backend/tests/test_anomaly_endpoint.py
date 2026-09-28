"""`GET /attendance/anomalies` 与 `/anomalies/explain` 路由测试（Sprint 9.5 批次 C4）。

打桩约定同 `test_compliance_scan_endpoint.py`：
- `NEO4J_URI` 指向不可达端口（`conftest.py`）⇒ GraphService 确定性抛
  :class:`GraphUnavailableError`；
- 需要「图谱可用」的用例 monkeypatch 对应的服务层方法。

**本文件验的是路由层契约**（字段集 / 错误码映射 / 参数透传 / 未命中项保留），
归因权重与置信度算式本身由 `test_rules_attribution.py` 覆盖，不重复。
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.schemas.anomaly import AnomalyExplainResponse
from app.services.graphs import GraphService, GraphUnavailableError
from app.services.rules import (
    AnomalyCase,
    AnomalyCaseList,
    AnomalyNotFoundError,
    AttributionResult,
    Cause,
)

LIST_PATH = "/api/v1/attendance/anomalies"
EXPLAIN_PATH = "/api/v1/attendance/anomalies/explain"

LIST_KEYS = {"kg_version", "items", "total", "trace_id"}
EXPLAIN_KEYS = {
    "kg_version",
    "employee_id",
    "employee_name",
    "date",
    "anomaly_type",
    "causes",
    "confidence",
    "conclusion",
    "action",
    "policy_refs",
    "trace_id",
}


def _listing() -> AnomalyCaseList:
    return AnomalyCaseList(
        kg_version="attendance-demo-v1",
        cases=(
            AnomalyCase(
                employee_id="E001",
                employee_name="张伟",
                day="2026-10-16",
                status="missing_check_in",
            ),
            AnomalyCase(
                employee_id="E003",
                employee_name="王强",
                day="2026-10-05",
                status="absent",
            ),
        ),
    )


def _result() -> AttributionResult:
    """四项证据**只命中三项**的归因（置信度 0.87，对齐 proposal §5.4 示例值）。"""
    return AttributionResult(
        employee_id="E001",
        employee_name="张伟",
        date="2026-10-16",
        anomaly_type="missing_check_in",
        causes=(
            Cause(
                code="trip_approved",
                reason="出差审批覆盖当日（武汉 2026-10-16~2026-10-18）",
                weight=0.35,
                matched=True,
                evidence=("BUSINESS_TRIP:BT-2026-0017",),
            ),
            Cause(
                code="order_closed",
                reason="当日工单已闭环 1 条",
                weight=0.30,
                matched=True,
                evidence=("WORK_ORDER:SO-2026-0912",),
            ),
            Cause(
                code="location_match",
                reason="定位与出差目的地一致 2 条（武汉光谷）",
                weight=0.22,
                matched=True,
                evidence=("LOCATION_RECORD:L00001",),
            ),
            # **未命中项照样返回**：演示时要能说清「哪一项没对上」
            Cause(
                code="access_contrast",
                reason="门禁对比不成立（当日 1 条 / 前一日 1 条）",
                weight=0.13,
                matched=False,
                evidence=(),
            ),
        ),
        confidence=0.87,
        conclusion="外勤出勤成立",
        action="系统自动补卡",
        policy_refs=("document:doc:fieldwork-attendance-rules:L27",),
    )


def test_list_returns_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.get(LIST_PATH, headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_list_returns_contract_fields(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        GraphService.instance(),
        "list_attendance_anomalies",
        lambda **_kwargs: _listing(),
    )

    response = client.get(LIST_PATH, headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == LIST_KEYS
    assert body["kg_version"] == "attendance-demo-v1"
    assert body["total"] == 2
    assert body["items"][0]["employee_name"] == "张伟"
    assert body["items"][0]["status"] == "missing_check_in"


def test_list_passes_employee_filter(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        GraphService.instance(),
        "list_attendance_anomalies",
        lambda **kwargs: (seen.update(kwargs), _listing())[1],
    )

    response = client.get(
        LIST_PATH, headers=dev_headers, params={"employee_id": "E001"}
    )

    assert response.status_code == 200
    assert seen["employee_id"] == "E001"


def test_explain_returns_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.get(
        EXPLAIN_PATH, headers=dev_headers, params={"employee_id": "E001"}
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_explain_returns_contract_fields_and_keeps_misses(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常路径：字段集齐全，**未命中的原因不隐藏**，置信度是确定性值的透传。"""
    monkeypatch.setattr(
        GraphService.instance(),
        "explain_attendance_anomaly",
        lambda **_kwargs: ("attendance-demo-v1", _result()),
    )

    response = client.get(
        EXPLAIN_PATH,
        headers=dev_headers,
        params={"employee_id": "E001", "date": "2026-10-16"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPLAIN_KEYS
    assert body["employee_name"] == "张伟"
    assert body["confidence"] == 0.87
    assert body["conclusion"] == "外勤出勤成立"
    assert body["policy_refs"] == ["document:doc:fieldwork-attendance-rules:L27"]

    codes = [item["code"] for item in body["causes"]]
    assert codes == [
        "trip_approved",
        "order_closed",
        "location_match",
        "access_contrast",
    ]
    miss = next(item for item in body["causes"] if item["code"] == "access_contrast")
    assert miss["matched"] is False
    assert miss["evidence"] == []


def test_explain_passes_date_to_service(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        GraphService.instance(),
        "explain_attendance_anomaly",
        lambda **kwargs: (seen.update(kwargs), ("attendance-demo-v1", _result()))[1],
    )

    response = client.get(
        EXPLAIN_PATH,
        headers=dev_headers,
        params={"employee_id": "E001", "date": "2026-10-16"},
    )

    assert response.status_code == 200
    assert seen["employee_id"] == "E001"
    assert seen["day"] == date(2026, 10, 16)


def test_explain_returns_404_when_anomaly_missing(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """员工不在图上 / 该日无异常 → 404，**不是**零证据的 200。

    零证据会被算成置信度 0%，看起来像「系统判断他不成立」，
    而真实情况是根本没查到这个人——二者语义相反。
    """

    def _raise(**_kwargs: object) -> tuple[str, AttributionResult]:
        raise AnomalyNotFoundError("employee E999 not in graph")

    monkeypatch.setattr(GraphService.instance(), "explain_attendance_anomaly", _raise)

    response = client.get(
        EXPLAIN_PATH,
        headers=dev_headers,
        params={"employee_id": "E999", "date": "2026-10-16"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["detail"]["employee_id"] == "E999"


def test_explain_wraps_unexpected_graph_error_as_501(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(**_kwargs: object) -> tuple[str, AttributionResult]:
        raise GraphUnavailableError("Neo4j 查询失败: 内部细节")

    monkeypatch.setattr(GraphService.instance(), "explain_attendance_anomaly", _raise)

    response = client.get(
        EXPLAIN_PATH, headers=dev_headers, params={"employee_id": "E001"}
    )

    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert set(body["detail"]) == {"blocked_by", "hint", "reason"}


def test_explain_requires_employee_id(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`employee_id` 是必填（没有「给所有人归因」这种模糊语义）。

    校验失败由全局处理器统一转成 **400** `VALIDATION_ERROR`
    （`CODEBUDDY.md` §错误响应规范：HTTP 状态码与业务错误码分离），
    不是 FastAPI 默认的 422。
    """
    response = client.get(EXPLAIN_PATH, headers=dev_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_response_model_rejects_weight_out_of_range() -> None:
    """权重必须落在 0~1：契约枚举 / 区间是硬约束，前端类型才可靠。"""
    with pytest.raises(ValueError):
        AnomalyExplainResponse(
            kg_version="v",
            employee_id="E001",
            employee_name="张伟",
            date="2026-10-16",
            anomaly_type="missing_check_in",
            causes=[
                {
                    "code": "trip_approved",
                    "reason": "x",
                    "weight": 3.5,
                    "matched": True,
                    "evidence": [],
                }
            ],
            confidence=1.0,
            conclusion="x",
            action="x",
            policy_refs=[],
            trace_id="t",
        )
