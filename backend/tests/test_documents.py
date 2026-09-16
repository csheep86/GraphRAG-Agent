"""上传 / 状态查询行为测试（Sprint 1 真实实现部分）。"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

PDF = ("合同.pdf", b"%PDF-1.4 minimal", "application/pdf")


def _upload(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/documents/upload", files={"file": PDF}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_returns_pending_task_id(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    body = _upload(client, dev_headers)

    assert body["status"] == "pending"
    UUID(body["task_id"])
    # 文件名原文不得回显（M1 §4.1）
    assert "合同.pdf" not in str(body)


def test_status_reflects_persisted_record(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    task_id = _upload(client, dev_headers)["task_id"]

    response = client.get(f"/api/v1/documents/{task_id}/status", headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["status"] == "pending"
    assert body["progress"] == 0.0
    assert body["error"] is None


def test_unknown_document_returns_404(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.get(f"/api/v1/documents/{uuid4()}/status", headers=dev_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


def test_cross_tenant_access_returns_403(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
) -> None:
    """ADR-0003 / M5 §3 验收 1：跨租户一律 403，而非 404。"""
    task_id = _upload(client, dev_headers)["task_id"]

    response = client.get(
        f"/api/v1/documents/{task_id}/status", headers=cross_tenant_headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
