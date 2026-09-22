"""MinerU 客户端单元测试（Sprint 5 批次 A；httpx.MockTransport，零真实网络）。

流程口径对齐 `mineru_mvp/run_mvp.py` 本地实测（CODEBUDDY.md「实测结果反哺规则」）：
申请链接 → PUT 上传 → 轮询 → 下载 zip → 解出 md + content_list。
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

import httpx
import pytest

from app.services.parsing import MineruApiError, MineruClient

_MARKDOWN = "# 标题\n\n正文段落。"
_CONTENT_LIST = [
    {"type": "text", "page_idx": 0, "text": "标题"},
    {"type": "table", "page_idx": 1, "html": "<table></table>"},
]


def _result_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("abc123/full.md", _MARKDOWN)
        zf.writestr("abc123/content_list.json", json.dumps(_CONTENT_LIST))
    return buf.getvalue()


def _make_client(transport: httpx.MockTransport) -> MineruClient:
    return MineruClient(
        base_url="https://mineru.test",
        token="t0k3n",
        model_version="vlm",
        language="ch",
        request_timeout_seconds=5,
        poll_interval_seconds=0,
        poll_timeout_seconds=1,
        transport=transport,
    )


def test_parse_pdf_happy_path() -> None:
    """四步全流程：md 与 content_list 原文返回，请求头带 Bearer。"""
    seen: list[tuple[str, str | None]] = []
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("Authorization")))
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-1",
                        "file_urls": ["https://oss.test/pre-signed"],
                    },
                },
            )
        if request.method == "PUT":
            return httpx.Response(200)
        if request.method == "GET" and "extract-results" in str(request.url):
            polls["n"] += 1
            if polls["n"] < 2:
                return httpx.Response(
                    200,
                    json={
                        "code": 0,
                        "data": {"extract_result": [{"state": "running"}]},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://oss.test/result.zip",
                            }
                        ]
                    },
                },
            )
        return httpx.Response(200, content=_result_zip())

    result = asyncio.run(
        _make_client(httpx.MockTransport(handler)).parse_pdf(
            content=b"%PDF-1.4", display_name="doc.pdf"
        )
    )

    assert result.markdown == _MARKDOWN
    assert json.loads(result.content_list_json) == _CONTENT_LIST
    # 全流程携带鉴权头
    assert all(auth == "Bearer t0k3n" for _, auth in seen)
    assert polls["n"] == 2, "应轮询到 done 为止"


def test_empty_token_raises_immediately() -> None:
    client = MineruClient(
        base_url="https://mineru.test",
        token="",
        model_version="vlm",
        language="ch",
        request_timeout_seconds=5,
        poll_interval_seconds=0,
        poll_timeout_seconds=1,
    )
    with pytest.raises(MineruApiError, match="MINERU_TOKEN"):
        asyncio.run(client.parse_pdf(content=b"x", display_name="d.pdf"))


def test_api_code_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "msg": "bad token"})

    with pytest.raises(MineruApiError, match="401"):
        asyncio.run(
            _make_client(httpx.MockTransport(handler)).parse_pdf(
                content=b"x", display_name="d.pdf"
            )
        )


def test_state_failed_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"batch_id": "b", "file_urls": ["https://oss.test/u"]},
                },
            )
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "extract_result": [{"state": "failed", "err_msg": "page limit"}]
                },
            },
        )

    with pytest.raises(MineruApiError, match="page limit"):
        asyncio.run(
            _make_client(httpx.MockTransport(handler)).parse_pdf(
                content=b"x", display_name="d.pdf"
            )
        )


def test_poll_timeout_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"batch_id": "b", "file_urls": ["https://oss.test/u"]},
                },
            )
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"extract_result": [{"state": "running"}]},
            },
        )

    with pytest.raises(MineruApiError, match="轮询超时"):
        asyncio.run(
            _make_client(httpx.MockTransport(handler)).parse_pdf(
                content=b"x", display_name="d.pdf"
            )
        )


def test_zip_missing_artifacts_raises() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("only.md", _MARKDOWN)  # 缺 content_list

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"batch_id": "b", "file_urls": ["https://oss.test/u"]},
                },
            )
        if request.method == "PUT":
            return httpx.Response(200)
        if "extract-results" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://oss.test/z.zip",
                            }
                        ]
                    },
                },
            )
        return httpx.Response(200, content=buf.getvalue())

    with pytest.raises(MineruApiError, match="缺产物"):
        asyncio.run(
            _make_client(httpx.MockTransport(handler)).parse_pdf(
                content=b"x", display_name="d.pdf"
            )
        )
