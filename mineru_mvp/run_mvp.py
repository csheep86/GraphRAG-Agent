# -*- coding: utf-8 -*-
"""MinerU 解析 MVP：本地 PDF -> MinerU API -> 输出 Markdown + JSON 到 output/。

用法（在 mineru_mvp/ 目录下）:
    uv run python run_mvp.py                    # 自动选取 input/ 下第一个 PDF
    uv run python run_mvp.py input/xxx.pdf     # 指定输入文件

流程（参考 MinerU 官方 API 文档 https://mineru.net/apiManage/docs）:
    1. POST /api/v4/file-urls/batch  申请 OSS 预签名上传链接，得到 batch_id
    2. PUT  上传文件到预签名链接
    3. GET  /api/v4/extract-results/batch/{batch_id} 轮询解析结果
    4. 下载 full_zip_url 并解压到 output/<文件名>/（含 full.md 与 content_list*.json）
"""

import argparse
import json
import logging
import os
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
from dotenv import load_dotenv
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mineru_mvp")

load_dotenv()

MINERU_TOKEN = os.getenv("MINERU_TOKEN", "")

BASE_URL = os.getenv("MINERU_API_BASE", "https://mineru.net").rstrip("/")
MODEL_VERSION = os.getenv("MINERU_MODEL_VERSION", "vlm")
LANGUAGE = os.getenv("MINERU_LANGUAGE", "ch")

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

# 轮询间隔与超时
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600


class MineruApiError(Exception):
    """MinerU 业务错误（code != 0）或任务失败。"""


# 重试策略：最多 3 次，指数退避（初始 1s，倍数 2）
RETRY_POLICY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, MineruApiError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


@retry(**RETRY_POLICY)
def request_upload_url(client: httpx.Client, file_name: str) -> tuple[str, str]:
    """申请上传链接，返回 (batch_id, file_url)。"""
    resp = client.post(
        f"{BASE_URL}/api/v4/file-urls/batch",
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
    batch_id = data["data"]["batch_id"]
    file_url = data["data"]["file_urls"][0]
    logger.info("已获取上传链接, batch_id=%s", batch_id)
    return batch_id, file_url


@retry(**RETRY_POLICY)
def upload_file(client: httpx.Client, file_url: str, file_path: Path) -> None:
    """PUT 上传文件到 OSS 预签名链接（无须设置 Content-Type）。"""
    with file_path.open("rb") as f:
        resp = client.put(file_url, content=f.read())
    resp.raise_for_status()
    logger.info("文件上传完成: %s", file_path.name)


@retry(**RETRY_POLICY)
def query_result(client: httpx.Client, batch_id: str) -> dict:
    """查询批量解析结果，返回首个文件的结果对象。"""
    resp = client.get(f"{BASE_URL}/api/v4/extract-results/batch/{batch_id}")
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise MineruApiError(f"查询结果失败: code={data.get('code')} msg={data.get('msg')}")
    return data["data"]["extract_result"][0]


@retry(**RETRY_POLICY)
def download_zip(client: httpx.Client, zip_url: str) -> bytes:
    """下载解析结果 zip 包。"""
    resp = client.get(zip_url)
    resp.raise_for_status()
    return resp.content


def poll_until_done(client: httpx.Client, batch_id: str) -> dict:
    """轮询直到任务 done / failed 或超时。"""
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        result = query_result(client, batch_id)
        state = result.get("state")
        progress = result.get("extract_progress") or {}
        logger.info(
            "任务状态: %s (页数 %s/%s)",
            state,
            progress.get("extracted_pages", "?"),
            progress.get("total_pages", "?"),
        )
        if state == "done":
            return result
        if state == "failed":
            raise MineruApiError(f"解析失败: {result.get('err_msg')}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise MineruApiError(f"轮询超时（{POLL_TIMEOUT_SECONDS}s），batch_id={batch_id}")


def extract_zip(zip_bytes: bytes, out_dir: Path) -> list[Path]:
    """解压结果 zip 到 out_dir，返回解压出的文件列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        zf.extractall(out_dir)
        return [out_dir / name for name in zf.namelist()]


def iter_items(content) :
    """兼容 content_list v1（条目列表）与 v2（页列表 -> 条目列表）两种结构，展平返回条目。"""
    for item in content:
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            yield from iter_items(item)


def print_tables(content_list_path: Path) -> None:
    """读取 content_list*.json，打印表格结构化结果（校验点）。"""
    content = json.loads(content_list_path.read_text(encoding="utf-8"))
    tables = [item for item in iter_items(content) if item.get("type") == "table"]
    print("\n===== 表格结构化检查（%s）=====" % content_list_path.name)
    print("表格数量: %d" % len(tables))
    for i, table in enumerate(tables, 1):
        # v1: item["body"]；v2: item["content"]["html"]
        body = (
            table.get("body")
            or (table.get("content") or {}).get("html")
            or table.get("html")
            or ""
        )
        caption = table.get("table_caption") or (table.get("content") or {}).get("table_caption") or ""
        print("\n--- 表格 %d %s---" % (i, f"({caption}) " if caption else ""))
        print(body)
    if not tables:
        print("警告：未在 content_list 中找到 type=table 的条目！")


def main() -> int:
    # Windows 控制台默认 GBK，强制 UTF-8 避免打印中文/特殊符号报错
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="MinerU 解析 MVP")
    parser.add_argument("input_file", nargs="?", default=None, help="输入 PDF 路径，默认取 input/ 下第一个 PDF")
    args = parser.parse_args()

    if not MINERU_TOKEN:
        logger.error("未配置 MINERU_TOKEN，请在 .env 中填写（参考 .env.example）")
        return 1

    if args.input_file:
        pdf_path = Path(args.input_file)
    else:
        pdfs = sorted(INPUT_DIR.glob("*.pdf"))
        if not pdfs:
            logger.error("input/ 下没有 PDF 文件")
            return 1
        pdf_path = pdfs[0]
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        logger.error("文件不存在: %s", pdf_path)
        return 1

    logger.info("输入文件: %s", pdf_path)
    logger.info("模型版本: %s, 语言: %s", MODEL_VERSION, LANGUAGE)

    with httpx.Client(
        timeout=120,
        headers={"Authorization": f"Bearer {MINERU_TOKEN}"},
    ) as client:
        # 1. 申请上传链接
        batch_id, file_url = request_upload_url(client, pdf_path.name)
        # 2. 上传文件
        upload_file(client, file_url, pdf_path)
        # 3. 轮询结果
        result = poll_until_done(client, batch_id)
        # 4. 下载并解压
        zip_url = result["full_zip_url"]
        zip_bytes = download_zip(client, zip_url)
        out_dir = OUTPUT_DIR / pdf_path.stem
        files = extract_zip(zip_bytes, out_dir)
        logger.info("结果已解压到: %s", out_dir)

        # 保存原始结果元数据
        (out_dir / "api_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n===== 解压文件清单 =====")
    for f in sorted(files):
        print(" -", f.relative_to(OUTPUT_DIR))

    # 校验表格结构化（优先 content_list_v2.json，回退 *_content_list.json）
    candidates = [
        f for f in files if f.name.endswith("content_list_v2.json")
    ] or [f for f in files if f.name.endswith("content_list.json") and "content_list_v2" not in f.name]
    if candidates:
        print_tables(candidates[0])
    else:
        print("警告：结果中未找到 content_list*.json")

    # 打印 Markdown 预览
    md_files = [f for f in files if f.name.endswith(".md")]
    if md_files:
        print("\n===== Markdown 预览（前 60 行）=====")
        for line in md_files[0].read_text(encoding="utf-8").splitlines()[:60]:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
