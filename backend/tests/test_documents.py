"""上传 / 状态查询行为测试（Sprint 1 真实实现部分；Sprint 5 批次 A 增补落盘）。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.tasks.registry as registry
from app.core.config import get_settings
from app.services.parsing import MineruParseResult

#: 上传样例。**docx 自 Sprint 9.5 批次 B2 起也会真正走 MinerU**（后缀决定解析器），
#: 因此本模块用模块级 fixture 把 MinerU 换成假实现，避免无 token 的测试环境
#: 把文档推到 failed（这正是「云原生 / 外部依赖不得影响用例」的老教训）。
DOCX = (
    "合同.docx",
    b"PK\x03\x04 docx bytes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
PDF = ("合同.pdf", b"%PDF-1.4 minimal", "application/pdf")


class _FakeMineruClient:
    """不需要网络 / token 的假解析器（PDF 与 docx 走同一分支）。"""

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def parse_document(
        self, *, content: bytes, display_name: str
    ) -> MineruParseResult:
        return MineruParseResult(markdown="# 假解析", content_list_json="[]")


@pytest.fixture(scope="module", autouse=True)
def _stub_parser() -> object:
    """模块级打桩：让上传的 PDF / docx 都能确定性地推进到 completed。"""
    patcher = pytest.MonkeyPatch()
    patcher.setattr(registry, "MineruClient", _FakeMineruClient)
    yield
    patcher.undo()


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

    PDF / docx 的真实 MinerU 路径由 ``test_document_parse_executor.py`` 覆盖；
    这里只关心状态机从 pending 一路推进到 completed。
    """
    task_id = _upload(client, dev_headers)["task_id"]

    response = client.get(f"/api/v1/documents/{task_id}/status", headers=dev_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_upload_persists_file_to_storage(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Sprint 5 批次 A：上传文件真实落盘到存储抽象层（M1 §4.3 验收 6 前半）。

    docx 自 Sprint 9.5 批次 B2 起也会产出 ``parse/`` 产物（与 PDF 同链路），
    故按 PDF 用例的口径把产物排除后再断言"源文件恰好一份"。
    """
    task_id = _upload(client, dev_headers)["task_id"]

    storage_root = get_settings().storage_root
    matches = list(storage_root.glob(f"*/{task_id}/*"))
    stored = [p for p in matches if p.name != "parse"]
    assert len(stored) == 1, (
        f"应恰好落一个对象 {{org}}/{task_id}/{{hash}}，实际 {stored}"
    )
    assert stored[0].read_bytes() == DOCX[1]
    # docx 现在与 PDF 同链路 ⇒ **必须**有解析产物（没有就说明又被跳过了）
    assert [p for p in matches if p.name == "parse"]


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
