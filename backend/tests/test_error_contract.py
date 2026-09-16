"""统一错误响应结构测试（F 节验收 4：错误体四字段齐全）。"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

ERROR_BODY_KEYS = {"code", "message", "detail", "trace_id"}


def test_unknown_route_returns_unified_error(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == ERROR_BODY_KEYS
    assert body["code"] == "NOT_FOUND"
    assert body["trace_id"] == response.headers["X-Trace-Id"]


def test_missing_authentication_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert set(response.json()) == ERROR_BODY_KEYS


def test_unsupported_mime_returns_415(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """M1 验收 3：MIME 白名单外一律 415，且不得落库。"""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=dev_headers,
    )

    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert set(body) == ERROR_BODY_KEYS
    assert "notes.txt" not in str(body)  # 文件名原文禁止出现在响应中


def test_validation_error_is_400_not_422(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/agent/query",
        json={"question": "A 公司的股东是谁？", "scope": "single_doc"},
        headers=dev_headers,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert set(body) == ERROR_BODY_KEYS
    assert isinstance(body["detail"]["errors"], list)


def test_graph_endpoint_contract_only(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`/graph` 契约已定稿但实现留待 Sprint 3 → 501。"""
    response = client.get(f"/api/v1/documents/{uuid4()}/graph", headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_agent_query_endpoint_contract_only(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/agent/query",
        json={"question": "A 与 B 是什么关系？"},
        headers=dev_headers,
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"
