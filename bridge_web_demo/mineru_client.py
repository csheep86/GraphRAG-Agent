# -*- coding: utf-8 -*-
"""MinerU 云解析客户端（Bridge Web Demo 用）。

严格遵循 docs/mineru_cloud_api_spec.md 的 4 步流程：
    1. POST /api/v4/file-urls/batch              申请 OSS 预签名上传链接
    2. PUT  <file_url>                           上传 PDF（不设置 Content-Type）
    3. GET  /api/v4/extract-results/batch/{id}   轮询任务状态
    4. GET  <full_zip_url>                       下载并解压到 mineru_mvp/output/<stem>/

复用实测结论：输出必须落在 output/<任务子目录>/（见规范 §3 实测差异 1）。
本文件为独立 MVP，不修改 mineru_mvp/ 与 backend/。
"""

from __future__ import annotations

import json
import logging
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("mineru_client")

TOKEN = os.getenv("MINERU_TOKEN", "").strip()
API_BASE = os.getenv("MINERU_API_BASE", "https://mineru.net").rstrip("/")
MODEL_VERSION = os.getenv("MINERU_MODEL_VERSION", "vlm")
LANGUAGE = os.getenv("MINERU_LANGUAGE", "ch")

# 默认与 mineru_mvp 共用输出根目录（规范 §3），可用环境变量覆盖
_default_output = BASE_DIR.parent / "mineru_mvp" / "output"
_env_output = os.getenv("MINERU_OUTPUT_DIR", "").strip()
MINERU_OUTPUT_DIR = Path(_env_output) if _env_output else _default_output
if not MINERU_OUTPUT_DIR.is_absolute():
    MINERU_OUTPUT_DIR = (BASE_DIR / MINERU_OUTPUT_DIR).resolve()

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600

class MineruApiError(Exception):
    """MinerU 业务错误（code != 0）或任务失败。"""


# 重试策略：最多 3 次，指数退避（初始 1s、倍数 2），对齐 specs/m2-extract-kg.md 验收 5
_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, MineruApiError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

ProgressCallback = Callable[[str], None]


def _notify(on_progress: ProgressCallback | None, message: str) -> None:
    logger.info(message)
    if on_progress:
        on_progress(message)


@retry(**_RETRY)
def _request_upload_url(client: httpx.Client, file_name: str) -> tuple[str, str]:
    resp = client.post(
        f"{API_BASE}/api/v4/file-urls/batch",
        json={
            "files": [{"name": file_name, "is_ocr": False}],
            "model_version": MODEL_VERSION,
            "enable_formula": True,
            "enable_table": True,
            "language": LANGUAGE,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise MineruApiError(f"申请上传链接失败: code={data.get('code')} msg={data.get('msg')}")
    return data["data"]["batch_id"], data["data"]["file_urls"][0]


@retry(**_RETRY)
def _upload_file(client: httpx.Client, file_url: str, file_path: Path) -> None:
    # 注意：不要设置 Content-Type，否则预签名校验会失败（规范 §5 实测差异 4）
    with file_path.open("rb") as f:
        resp = client.put(file_url, content=f.read())
    resp.raise_for_status()


@retry(**_RETRY)
def _query_result(client: httpx.Client, batch_id: str) -> dict[str, Any]:
    resp = client.get(f"{API_BASE}/api/v4/extract-results/batch/{batch_id}")
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise MineruApiError(f"查询结果失败: code={data.get('code')} msg={data.get('msg')}")
    return data["data"]["extract_result"][0]


@retry(**_RETRY)
def _download_zip(client: httpx.Client, zip_url: str) -> bytes:
    resp = client.get(zip_url)
    resp.raise_for_status()
    return resp.content


def parse_pdf(
    pdf_path: Path,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """上传 PDF -> 轮询 -> 解压，返回任务子目录路径。"""
    if not TOKEN or TOKEN.startswith("sk-your"):
        raise MineruApiError("未配置真实 MINERU_TOKEN，请编辑 bridge_web_demo/.env")
    if not pdf_path.exists():
        raise MineruApiError(f"PDF 不存在: {pdf_path}")

    with httpx.Client(
        timeout=120,
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as client:
        _notify(on_progress, f"申请 MinerU 上传链接（{pdf_path.name}）...")
        batch_id, file_url = _request_upload_url(client, pdf_path.name)

        _notify(on_progress, f"上传文件到 OSS（batch_id={batch_id}）...")
        _upload_file(client, file_url, pdf_path)

        _notify(on_progress, "等待 MinerU 解析...")
        deadline = time.time() + POLL_TIMEOUT_SECONDS
        result: dict[str, Any] | None = None
        while time.time() < deadline:
            current = _query_result(client, batch_id)
            state = current.get("state")
            progress = current.get("extract_progress") or {}
            _notify(
                on_progress,
                f"解析状态 {state} ({progress.get('extracted_pages', '?')}/"
                f"{progress.get('total_pages', '?')} 页)",
            )
            if state == "done":
                result = current
                break
            if state == "failed":
                raise MineruApiError(f"MinerU 解析失败: {current.get('err_msg')}")
            time.sleep(POLL_INTERVAL_SECONDS)
        if result is None:
            raise MineruApiError(f"MinerU 轮询超时（{POLL_TIMEOUT_SECONDS}s）")

        _notify(on_progress, "下载并解压解析结果...")
        zip_bytes = _download_zip(client, result["full_zip_url"])

    out_dir = MINERU_OUTPUT_DIR / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        zf.extractall(out_dir)
    (out_dir / "api_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _notify(on_progress, f"解析结果已解压到: {out_dir}")
    return out_dir
