"""MinerU 云解析客户端（Sprint 5 批次 A：parsing 状态真实执行）。

流程复用 `mineru_mvp/run_mvp.py`（本地实测跑通，规范以实测为准——
`docs/mineru_cloud_api_spec.md` / CODEBUDDY.md「实测结果反哺规则」）：

1. POST `/api/v4/file-urls/batch`  申请 OSS 预签名上传链接（得到 batch_id）；
2. PUT 预签名链接上传文件（无须 Content-Type）；
3. GET  `/api/v4/extract-results/batch/{batch_id}` 轮询至 done / failed / 超时；
4. 下载 `full_zip_url` 并在内存中解出 `full.md` 与 `content_list*.json`。

设计边界：
- **不做**内层 tenacity 重试——外层 `document.parse` 执行体已有指数退避
  （M1 §3 验收 4），双层重试会放大等待；本类只抛可重试异常
  （:class:`MineruApiError` / httpx 错误），重试策略统一交给调用方。
- 文件名不使用原始上传名（M5 §4.5 敏感纪律）：对外仅暴露调用方给的
  ``display_name``（约定为 `{doc_id}.pdf`）。
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from dataclasses import dataclass
from io import BytesIO

import httpx
from loguru import logger


class MineruApiError(Exception):
    """MinerU 业务错误（code != 0 / 任务 failed / 轮询超时 / 结果缺产物）。"""


@dataclass(frozen=True)
class MineruParseResult:
    """解析产物（Sprint 6 批次 B 的 Chunk 证据节点以此为输入）。"""

    markdown: str
    content_list_json: str


class MineruClient:
    """MinerU 云 API 的最小异步客户端。"""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        model_version: str,
        language: str,
        request_timeout_seconds: float,
        poll_interval_seconds: float,
        poll_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._model_version = model_version
        self._language = language
        self._request_timeout_seconds = request_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_timeout_seconds = poll_timeout_seconds
        # transport 仅测试注入（httpx.MockTransport）；生产恒为 None
        self._transport = transport

    async def parse_pdf(
        self, *, content: bytes, display_name: str
    ) -> MineruParseResult:
        """上传并解析一个 PDF，返回 markdown + content_list 原文。"""
        if not self._token:
            raise MineruApiError("未配置 MINERU_TOKEN（.env），无法执行云解析")

        headers = {"Authorization": f"Bearer {self._token}"}
        client_kwargs: dict[str, object] = {
            "base_url": self._base_url,
            "headers": headers,
            "timeout": self._request_timeout_seconds,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
            batch_id, file_url = await self._request_upload_url(client, display_name)
            await self._upload_file(client, file_url, content)
            result = await self._poll_until_done(client, batch_id)
            zip_url = result.get("full_zip_url")
            if not zip_url:
                raise MineruApiError(
                    f"结果缺少 full_zip_url: state={result.get('state')}"
                )
            zip_bytes = await self._download_zip(client, zip_url)

        markdown, content_list_json = _extract_artifacts(zip_bytes)
        logger.bind(display_name=display_name, pages_hint=len(content_list_json)).info(
            "mineru_parse_done"
        )
        return MineruParseResult(markdown=markdown, content_list_json=content_list_json)

    # ------------------------------------------------------------------ #
    # 步骤实现（对齐 mineru_mvp 实测口径）
    # ------------------------------------------------------------------ #

    async def _request_upload_url(
        self, client: httpx.AsyncClient, file_name: str
    ) -> tuple[str, str]:
        resp = await client.post(
            "/api/v4/file-urls/batch",
            json={
                "files": [{"name": file_name, "is_ocr": False}],
                "model_version": self._model_version,
                "enable_formula": True,
                "enable_table": True,
                "language": self._language,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise MineruApiError(
                f"申请上传链接失败: code={data.get('code')} msg={data.get('msg')}"
            )
        return data["data"]["batch_id"], data["data"]["file_urls"][0]

    async def _upload_file(
        self, client: httpx.AsyncClient, file_url: str, content: bytes
    ) -> None:
        resp = await client.put(file_url, content=content)
        resp.raise_for_status()

    async def _poll_until_done(self, client: httpx.AsyncClient, batch_id: str) -> dict:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        while loop.time() < deadline:
            resp = await client.get(f"/api/v4/extract-results/batch/{batch_id}")
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise MineruApiError(
                    f"查询结果失败: code={data.get('code')} msg={data.get('msg')}"
                )
            result = data["data"]["extract_result"][0]
            state = result.get("state")
            if state == "done":
                return result
            if state == "failed":
                raise MineruApiError(f"解析失败: {result.get('err_msg')}")
            await asyncio.sleep(self._poll_interval_seconds)
        raise MineruApiError(
            f"轮询超时（{self._poll_timeout_seconds}s），batch_id={batch_id}"
        )

    async def _download_zip(self, client: httpx.AsyncClient, zip_url: str) -> bytes:
        resp = await client.get(zip_url)
        resp.raise_for_status()
        return resp.content


def _extract_artifacts(zip_bytes: bytes) -> tuple[str, str]:
    """从结果 zip 解出 full.md 与 content_list*.json（v1 / v2 兼容）。

    返回 (markdown, content_list_json)；任一缺失抛 :class:`MineruApiError`。
    """
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        md_candidates = [n for n in names if n.endswith(".md")]
        cl_candidates = [n for n in names if n.endswith("content_list_v2.json")] or [
            n for n in names if n.endswith("content_list.json")
        ]
        if not md_candidates or not cl_candidates:
            raise MineruApiError(
                f"结果 zip 缺产物: md={md_candidates} content_list={cl_candidates}"
            )
        markdown = zf.read(md_candidates[0]).decode("utf-8")
        raw = zf.read(cl_candidates[0]).decode("utf-8")
        # 结构合法性自检：损坏 JSON 直接抛业务错误（触发外层重试或 failed）
        json.loads(raw)
        return markdown, raw


__all__ = ["MineruApiError", "MineruClient", "MineruParseResult"]
