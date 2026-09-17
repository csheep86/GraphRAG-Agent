# -*- coding: utf-8 -*-
"""Bridge Web Demo —— 极简 FastAPI 后端。

职责（规范 docs/bridge-pipeline-specification-v1.0.md §6/§7）：
    - 接收 PDF 上传（限 100MB、MIME 白名单）
    - 后台线程执行 Bridge Pipeline（先 MinerU 解析，再 LangExtract 抽取）
    - 通过 GET /api/jobs/{job_id} 暴露步骤级实时状态（前端 1s 轮询）
    - 提供结果 JSON 与单页 HTML

启动（在 bridge_web_demo/ 目录下）：
    uv run uvicorn server:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from bridge_pipeline import (
    MINERU_OUTPUT_DIR,
    OUTPUT_JSON,
    STEP_LABELS,
    run_pipeline,
)
from mineru_client import MineruApiError, parse_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bridge_server")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100MB（CODEBUDDY.md「存储规范」）
ALLOWED_SUFFIX = {".pdf"}

app = FastAPI(title="Bridge Pipeline Demo", version="1.0.0")

# 单 worker：LangExtract 与 MinerU 均为重 IO，串行可避免并发抢占 API 配额
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# 错误响应（对齐 CODEBUDDY.md「错误响应规范」）
# --------------------------------------------------------------------------- #
def error_response(status_code: int, code: str, message: str, detail: str, trace_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": detail, "trace_id": trace_id},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
    return error_response(
        exc.status_code,
        f"HTTP_{exc.status_code}",
        str(exc.detail) if isinstance(exc.detail, str) else "请求错误",
        detail,
        request.headers.get("x-trace-id", "") or str(uuid.uuid4()),
    )


# --------------------------------------------------------------------------- #
# 任务状态管理
# --------------------------------------------------------------------------- #
def _init_job(job_id: str, trace_id: str, step_names: list[str]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "trace_id": trace_id,
        "status": "pending",
        "current_step": None,
        "steps": [
            {
                "name": name,
                "label": STEP_LABELS.get(name, name),
                "status": "pending",
                "detail": None,
                "duration_ms": None,
            }
            for name in step_names
        ],
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result_ready": False,
    }


def _update_step(job: dict[str, Any], name: str, status: str, detail: str | None, duration_ms: int | None) -> None:
    with _lock:
        for step in job["steps"]:
            if step["name"] == name:
                step["status"] = status
                if detail is not None:
                    step["detail"] = detail
                if duration_ms is not None:
                    step["duration_ms"] = duration_ms
                break
        if status == "processing":
            job["current_step"] = name
            job["status"] = "processing"
        elif status == "failed":
            job["current_step"] = name
            job["status"] = "failed"


def _save_upload(upload: UploadFile, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError("文件超过 100MB 限制")
            out.write(chunk)
    return total


# --------------------------------------------------------------------------- #
# Pipeline 后台任务
# --------------------------------------------------------------------------- #
def _run_job(job: dict[str, Any], pdf_path: Path | None) -> None:
    job_id = job["job_id"]
    try:
        # step0 接收 PDF
        if any(s["name"] == "receive_pdf" for s in job["steps"]):
            _update_step(
                job,
                "receive_pdf",
                "completed",
                f"已保存 {pdf_path.name}" if pdf_path else "未上传文件",
                None,
            )

        # step1 MinerU 解析（可选）
        if any(s["name"] == "mineru_parse" for s in job["steps"]):
            if pdf_path is None:
                _update_step(job, "mineru_parse", "completed", "已跳过（使用已有输出）", None)
            else:
                _update_step(job, "mineru_parse", "processing", None, None)
                try:
                    out_dir = parse_pdf(
                        pdf_path,
                        on_progress=lambda msg: _update_step(job, "mineru_parse", "processing", msg, None),
                    )
                except (MineruApiError, Exception) as exc:  # noqa: BLE001
                    _update_step(job, "mineru_parse", "failed", str(exc), None)
                    raise
                _update_step(job, "mineru_parse", "completed", f"结果目录: {out_dir}", None)

        # step2~5 Bridge Pipeline（回调内部已含 processing/completed/failed）
        result = run_pipeline(
            mineru_output_dir=MINERU_OUTPUT_DIR,
            output_path=OUTPUT_JSON,
            on_progress=lambda ev: _update_step(
                job, ev["name"], ev["status"], ev.get("detail"), ev.get("duration_ms")
            ),
            trace_id=job["trace_id"],
        )

        with _lock:
            job["status"] = "completed"
            job["current_step"] = None
            job["result_ready"] = True
            job["result"] = {
                "source_path": result["source"]["source_path"],
                "input_mode": result["source"]["input_mode"],
                "stats": result["stats"],
            }
        logger.info("[%s] 任务完成: %s", job_id, OUTPUT_JSON)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 任务失败", job_id)
        with _lock:
            job["status"] = "failed"
            job["error"] = {"code": "PIPELINE_FAILED", "message": str(exc)}
            for step in job["steps"]:
                if step["status"] == "processing":
                    step["status"] = "failed"
                    step["detail"] = step["detail"] or str(exc)


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html", media_type="text/html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    from bridge_pipeline import _API_KEY  # 局部导入，避免暴露到模块导出

    return {
        "status": "ok",
        "mineru_output_dir": str(MINERU_OUTPUT_DIR),
        "output_json": str(OUTPUT_JSON),
        "has_api_key": bool(_API_KEY and not _API_KEY.startswith("sk-your")),
    }


@app.post("/api/jobs", status_code=202)
async def create_job(
    file: UploadFile | None = File(None),
    skip_mineru: bool = Form(False),
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())

    pdf_path: Path | None = None
    step_names: list[str] = []
    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIX:
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = UPLOAD_DIR / f"{job_id}{suffix}"
        try:
            size = _save_upload(file, pdf_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info("[%s] 已接收上传: %s (%d bytes)", job_id, file.filename, size)
        step_names.append("receive_pdf")
        if not skip_mineru:
            step_names.append("mineru_parse")
    step_names += ["locate_source", "clean_text", "langextract_extract", "build_graph"]

    job = _init_job(job_id, trace_id, step_names)
    with _lock:
        _jobs[job_id] = job

    _executor.submit(_run_job, job, pdf_path)
    return {"job_id": job_id, "trace_id": trace_id, "status": job["status"]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    with _lock:
        return json.loads(json.dumps(job, ensure_ascii=False, default=str))


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str) -> JSONResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    if not job.get("result_ready"):
        raise HTTPException(status_code=409, detail="NOT_READY: 任务尚未完成")
    if not OUTPUT_JSON.exists():
        raise HTTPException(status_code=404, detail="output.json 不存在")
    return JSONResponse(json.loads(OUTPUT_JSON.read_text(encoding="utf-8")))


@app.get("/api/result/latest")
async def get_latest_result() -> JSONResponse:
    if not OUTPUT_JSON.exists():
        raise HTTPException(status_code=404, detail="尚无 output.json，请先运行 Pipeline")
    return JSONResponse(json.loads(OUTPUT_JSON.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
