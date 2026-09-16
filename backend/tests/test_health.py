"""`GET /api/v1/health` 行为测试（F 节验收 2）。"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "up"}
    assert body["version"]
    # trace_id 必须是 UUIDv4 字符串（M1 验收 7）
    UUID(body["trace_id"])


def test_health_is_exempt_from_tenant_context(client: TestClient) -> None:
    """`/health` 不带任何认证头也必须 200（阶段 3.1 决策 3）。"""
    assert client.get("/api/v1/health").status_code == 200


def test_health_echoes_incoming_trace_id(client: TestClient) -> None:
    trace_id = str(uuid4())
    response = client.get("/api/v1/health", headers={"X-Trace-Id": trace_id})

    assert response.headers["X-Trace-Id"] == trace_id
    assert response.json()["trace_id"] == trace_id


def test_health_replaces_malformed_trace_id(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Trace-Id": "not-a-uuid"})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] != "not-a-uuid"
    UUID(response.headers["X-Trace-Id"])
