"""Sprint 6 批次 B：`GET /api/v1/documents/{id}/chunks/{chunk_id}` 端点测试。

覆盖 Q2 落地后的三条关键语义：

1. 命中 → 200，返回真实原文片段（含页码 / 字符区间），供前端高亮；
2. 跨租户 → **403**（非 404，ADR-0003 / M5 §3 验收 1），且先于存储读取；
3. `chunks.json` 缺失或其中无该 `chunk_id` → 404 `NOT_FOUND`，
   **不**返回空串——「没有这段原文」与「原文是空串」必须可区分。

数据源是批次 A 落盘的 `chunks.json`（存储层中间产物），因此本文件**不**依赖 Neo4j。
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.storage import build_extract_artifact_key, get_storage

PDF = ("合同.pdf", b"%PDF-1.4", "application/pdf")

DOC_ID_PLACEHOLDER = UUID("11111111-2222-3333-4444-555555555555")

CHUNKS = [
    {
        "id": "chunk-581e8912827d",
        "char_start": 0,
        "char_end": 764,
        "text": "甲方：北京青云科技有限公司（以下简称甲方）。",
        "page": 1,
    },
    {
        "id": "chunk-9c02aa77b314",
        "char_start": 764,
        "char_end": 1528,
        "text": "第二条 合同金额与支付方式。",
        "page": None,  # 页码失配（Q1：给 null，不伪造）
    },
]

CHUNK_RESPONSE_KEYS = {
    "doc_id",
    "chunk_id",
    "text",
    "page",
    "char_start",
    "char_end",
    "trace_id",
}


def _upload(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/documents/upload", files={"file": PDF}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


def _put_chunks(document_id: str) -> None:
    """按 `registry.py::_do_extract` 的真实键写入 chunk 产物。"""
    key = build_extract_artifact_key(
        org_id=get_settings().default_org_id,
        doc_id=UUID(document_id),
        filename="chunks.json",
    )
    get_storage().put(key, json.dumps(CHUNKS, ensure_ascii=False).encode("utf-8"))


def test_chunk_endpoint_returns_real_text(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    document_id = _upload(client, dev_headers)
    _put_chunks(document_id)

    response = client.get(
        f"/api/v1/documents/{document_id}/chunks/chunk-581e8912827d",
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == CHUNK_RESPONSE_KEYS
    assert body["doc_id"] == document_id
    assert body["chunk_id"] == "chunk-581e8912827d"
    assert body["text"] == CHUNKS[0]["text"]
    assert body["page"] == 1
    assert body["char_start"] == 0
    assert body["char_end"] == 764
    assert body["trace_id"] == response.headers["X-Trace-Id"]


def test_chunk_endpoint_page_null_when_mismatched(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Q1：页码失配 → `null`（严禁兜底伪造 1）。"""
    document_id = _upload(client, dev_headers)
    _put_chunks(document_id)

    response = client.get(
        f"/api/v1/documents/{document_id}/chunks/chunk-9c02aa77b314",
        headers=dev_headers,
    )

    assert response.status_code == 200
    assert response.json()["page"] is None


def test_chunk_endpoint_403_cross_tenant(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
) -> None:
    """他人文档 → 403（非 404），且**先于**存储读取（PG 校验先行）。"""
    document_id = _upload(client, dev_headers)
    _put_chunks(document_id)

    response = client.get(
        f"/api/v1/documents/{document_id}/chunks/chunk-581e8912827d",
        headers=cross_tenant_headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_chunk_endpoint_404_when_document_missing(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.get(
        f"/api/v1/documents/{DOC_ID_PLACEHOLDER}/chunks/chunk-581e8912827d",
        headers=dev_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


def test_chunk_endpoint_404_when_artifact_missing(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """文档已上传但未产出 `chunks.json`（抽取未完成）→ 404，且 reason 可诊断。"""
    document_id = _upload(client, dev_headers)

    response = client.get(
        f"/api/v1/documents/{document_id}/chunks/chunk-581e8912827d",
        headers=dev_headers,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["detail"]["reason"] == "chunks_artifact_missing"


def test_chunk_endpoint_404_when_chunk_id_unknown(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """产物存在但没有这个 `chunk_id` → 404（**不**返回空串）。"""
    document_id = _upload(client, dev_headers)
    _put_chunks(document_id)

    response = client.get(
        f"/api/v1/documents/{document_id}/chunks/chunk-deadbeef0000",
        headers=dev_headers,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["detail"]["reason"] == "chunk_id_not_in_artifact"
