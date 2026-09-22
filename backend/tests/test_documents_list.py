"""`GET /documents` 列表接口测试（Sprint 5 批次 C）。

行为约束：
- 跨租户隔离（ADR-0003）：非本 org 文档**永不**出现在结果里；
- 过滤维度：`q`（filename_hash 前缀）/ `status`（4 个枚举值之一）/ `page` /
  `page_size`（默认 10，上限 100）；
- `filename` 字段返回 hash 而非原文（M5 §4.5）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

PDF = ("合同.pdf", b"%PDF-1.4 minimal", "application/pdf")
DOCX = (
    "合同.docx",
    b"PK\x03\x04 docx bytes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

#: 契约字段集（与 `contracts/openapi.yaml` 对齐），用于「不多不少」回归断言
DOCUMENT_LIST_ITEM_KEYS = {
    "id",
    "filename",
    "file_type",
    "status",
    "entity_count",
    "uploaded_at",
    "time_label",
    "task_id",
    "trace_id",
}
DOCUMENT_LIST_RESPONSE_KEYS = {
    "total",
    "items",
    "page",
    "page_size",
    "trace_id",
}


def _upload(client: TestClient, headers: dict[str, str], file: tuple = PDF) -> str:
    response = client.post(
        "/api/v1/documents/upload", files={"file": file}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


def test_list_returns_documents_for_current_org_only(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
) -> None:
    """ADR-0003：列表接口严格按 `org_id` 过滤，跨租户资源永不出现。

    注：测试 `client` 是 session-scoped（conftest 约定），其它 case 已上传过
    属于默认 org 的文档；本 case 不再断言 `total == 1`，改为断言**新上传的
    两条**分别命中 / 不命中本租户视图。
    """
    own = _upload(client, dev_headers, PDF)
    other = _upload(client, cross_tenant_headers, PDF)

    response = client.get("/api/v1/documents", headers=dev_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == DOCUMENT_LIST_RESPONSE_KEYS
    task_ids = {item["task_id"] for item in body["items"]}
    # 本租户上传的 must 命中
    assert own in task_ids, f"own upload {own} should be listed"
    # 跨租户上传的 must 永不出现
    assert other not in task_ids, f"cross-tenant upload {other} leaked into org view"
    # 列表内每条都属当前租户（防御性断言）
    for item in body["items"]:
        assert item["task_id"] != other


def test_list_pagination_meta_always_present(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """空表 / 非空表都要回填 `page` / `page_size` / `trace_id` 元数据。

    测试用 client 是 session-scoped（conftest 约定），其它 case 已上传数据，
    本 case 不再断言 total==0；改为对**响应结构**做断言。
    """
    response = client.get("/api/v1/documents", headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert isinstance(body["total"], int) and body["total"] >= 0
    assert isinstance(body["items"], list)
    assert isinstance(body["trace_id"], str) and body["trace_id"]


def test_list_filter_by_status(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """按 `status` 过滤：上传 docx（解析跳过 → completed）。"""
    task_id = _upload(client, dev_headers, DOCX)

    # 默认不过滤 → 看到它
    response = client.get("/api/v1/documents", headers=dev_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any(item["task_id"] == task_id for item in response.json()["items"])

    # status=completed → 仍能看到
    response = client.get("/api/v1/documents?status=completed", headers=dev_headers)
    assert response.status_code == 200
    assert any(item["task_id"] == task_id for item in response.json()["items"])

    # status=pending → 当前无 pending 任务，看到空表
    response = client.get("/api/v1/documents?status=pending", headers=dev_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_list_pagination(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """分页：page=1 / page_size=1 时应只返回 1 条（最新）。"""
    # 至少上传 2 条
    _upload(client, dev_headers, PDF)
    _upload(client, dev_headers, PDF)

    response = client.get(
        "/api/v1/documents?page=1&page_size=1", headers=dev_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["total"] >= 2
    assert len(body["items"]) == 1
    # 字段集合校验（不允许契约外字段偷偷混入）
    assert set(body["items"][0]) == DOCUMENT_LIST_ITEM_KEYS


def test_list_q_prefix_match(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`q` 按 filename_hash 前缀匹配。

    先上传一条拿到 hash，再以前缀过滤——能命中，**不**按文件名原文过滤。
    """
    _upload(client, dev_headers, DOCX)

    # 全列表 → 拿到第一条 filename_hash
    response = client.get(
        "/api/v1/documents?page_size=100", headers=dev_headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    first_hash = items[0]["filename"]
    # SHA-256 hex 长度 64；取前 4 字符做前缀匹配
    prefix = first_hash[:4]

    # q=prefix → 应命中
    response = client.get(
        f"/api/v1/documents?q={prefix}", headers=dev_headers
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    # q=不存在的 hex 前缀 → 命中 0
    response = client.get(
        "/api/v1/documents?q=ffffffff", headers=dev_headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_list_status_validation_returns_400(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """非法 status 触发 400 `VALIDATION_ERROR`。"""
    response = client.get(
        "/api/v1/documents?status=invalid", headers=dev_headers
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_page_size_validation_returns_400(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`page_size` 超 100 触发 400 `VALIDATION_ERROR`。"""
    response = client.get(
        "/api/v1/documents?page_size=999", headers=dev_headers
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_requires_auth(
    client: TestClient,
) -> None:
    """无认证态 → 401 `UNAUTHORIZED`。"""
    response = client.get("/api/v1/documents")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"