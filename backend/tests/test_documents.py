"""上传 / 状态查询行为测试（Sprint 1 真实实现部分；Sprint 5 批次 A 增补落盘）。"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings

#: 默认用 docx：解析跳过（S10 承接）→ BackgroundTasks 快速推进 completed，
#: 避免 PDF 路径触发无 token 的 MinerU 重试。
DOCX = (
    "合同.docx",
    b"PK\x03\x04 docx bytes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
PDF = ("合同.pdf", b"%PDF-1.4 minimal", "application/pdf")


def _upload(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/documents/upload", files={"file": DOCX}, headers=headers
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
    # BackgroundTasks 在 TestClient.post 返回前已执行（骨架版 no-op），
    # status 可能推进到 completed / processing / 仍为 pending；
    # 测试只关心字段被持久化为合法枚举值。
    assert body["status"] in {"pending", "processing", "completed"}
    assert 0.0 <= body["progress"] <= 1.0
    assert body["error"] is None


def test_background_task_drives_status_to_completed(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """阶段九验收：上传 → BackgroundTasks 在请求内执行 → status=completed。

    docx 跳过结构化解析（S10 承接），状态机从 pending 一路推进到 completed。
    PDF 的真实 MinerU 路径由 ``test_document_parse_executor.py`` 覆盖。
    """
    task_id = _upload(client, dev_headers)["task_id"]

    response = client.get(f"/api/v1/documents/{task_id}/status", headers=dev_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_upload_persists_file_to_storage(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Sprint 5 批次 A：上传文件真实落盘到存储抽象层（M1 §4.3 验收 6 前半）。"""
    task_id = _upload(client, dev_headers)["task_id"]

    storage_root = get_settings().storage_root
    matches = list(storage_root.glob(f"*/{task_id}/*"))
    assert len(matches) == 1, (
        f"应恰好落一个对象 {{org}}/{task_id}/{{hash}}，实际 {matches}"
    )
    assert matches[0].read_bytes() == DOCX[1]


def test_upload_pdf_persists_original_bytes(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """PDF 上传同样真实落盘（后台解析失败与否不影响文件本体存在）。"""
    response = client.post(
        "/api/v1/documents/upload", files={"file": PDF}, headers=dev_headers
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]

    storage_root = get_settings().storage_root
    matches = list(storage_root.glob(f"*/{task_id}/*"))
    stored = [p for p in matches if p.name != "parse"]
    assert len(stored) == 1
    assert stored[0].read_bytes() == PDF[1]
    # 文件名原文不得出现在对象键中（ADR-0003 §3.5）
    assert "合同.pdf" not in str(stored[0])


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
