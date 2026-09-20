"""
Sprint 4 · 10.2 联调 probe 脚本（Python 版）

用途：联调 /documents/upload + /documents/{id}/status（不验证 /graph）

运行（用户手动执行）：
  cd d:/AIProject/GraphRAG-Agent/backend
  uv run python ../changes/Sprint4.10.2/probe.py 2>&1 | Tee-Object -FilePath ../changes/Sprint4.10.2/probe-output.log

前置：
  - uvicorn 跑着（监听 8000）
  - next dev 跑着（监听 3000）
  - .env.development: ALLOW_DEV_ORG_HEADER=true（X-Org-Id 兜底）
  - 依赖：requests（实测 backend/.venv 内已装，版本 2.34.2；未装则 uv add requests）
  - 后端 MIME 提取：FastAPI UploadFile.content_type 读 multipart part 的 Content-Type header
    （不是从文件名推断）。所以 multipart 必须显式指定 content_type，否则会被 PS 7 默认
    设为 application/octet-stream → 415。（这是 probe.ps1 在场景 A 失败的根因。）

输出：本脚本不打 git、不提交；用户执行后把 PowerShell 输出贴回，由 CodeBuddy 写入 integration-log。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

import requests


# --- 配置 ---
BASE_URI = "http://127.0.0.1:8000"
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"
FOREIGN_ORG_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
PDF_PATH = Path("d:/AIProject/GraphRAG-Agent/mineru_mvp/input/complex_table.pdf")
MAX_POLL = 5
POLL_SLEEP_SEC = 2

ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
}


# --- 结果收集 ---
results: list[tuple[str, bool, str]] = []


def section(title: str) -> None:
    print()
    print(f"===== {title} =====")


def add_result(name: str, passed: bool, detail: str) -> None:
    results.append((name, passed, detail))


def headers_org(trace_id: str) -> dict[str, str]:
    return {"X-Org-Id": ORG_ID, "X-Actor-Id": ACTOR_ID, "X-Trace-Id": trace_id}


def headers_foreign(trace_id: str) -> dict[str, str]:
    return {"X-Org-Id": FOREIGN_ORG_ID, "X-Actor-Id": ACTOR_ID, "X-Trace-Id": trace_id}


def safe_json(resp: requests.Response) -> dict | None:
    try:
        return resp.json()
    except Exception:
        return None


def trace_check(resp: requests.Response, body: dict | None, expected: str) -> bool:
    """响应头 X-Trace-Id 与 body.trace_id 是否都与 expected 一致。"""
    header_trace = resp.headers.get("X-Trace-Id", "")
    body_trace = (body or {}).get("trace_id", "")
    return header_trace == expected and body_trace == expected


# ============================================================
def main() -> int:
    task_id: str | None = None

    # ========== 场景 0：健康探活 ==========
    section("场景 0: 健康探活 GET /api/v1/health")
    try:
        url = f"{BASE_URI}/api/v1/health"
        trace0 = "00000000-0000-4000-8000-000000000000"
        print(f"URL: {url}  trace={trace0}")
        resp = requests.get(url, headers={"X-Trace-Id": trace0}, timeout=5)
        body = safe_json(resp)
        print(f"HTTP status: {resp.status_code}")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, trace0)
        db = (body or {}).get("checks", {}).get("database")
        passed = (
            resp.status_code == 200
            and (body or {}).get("status") == "ok"
            and db == "up"
            and tmatch
        )
        add_result(
            "0_health",
            passed,
            f"status={(body or {}).get('status')} db={db} trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("0_health", False, f"exception: {e!r}")


    # ========== 场景 A：upload 成功（PDF） ==========
    section("场景 A: upload 成功路径 POST /api/v1/documents/upload (PDF)")
    try:
        url = f"{BASE_URI}/api/v1/documents/upload"
        traceA = "11111111-1111-4111-8111-111111111111"
        print(f"URL: {url}  trace={traceA}  file={PDF_PATH}")
        with PDF_PATH.open("rb") as f:
            files = {"file": (PDF_PATH.name, f, "application/pdf")}
            resp = requests.post(url, files=files, headers=headers_org(traceA), timeout=30)
        body = safe_json(resp)
        print(f"HTTP status: {resp.status_code}")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if body:
            task_id = body.get("task_id")
            print(f"保存 task_id = {task_id}")
        tmatch = trace_check(resp, body, traceA)
        passed = (
            resp.status_code == 200
            and (body or {}).get("status") == "pending"
            and tmatch
        )
        add_result(
            "A_upload_200",
            passed,
            f"task_id={task_id} trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("A_upload_200", False, f"exception: {e!r}")


    # ========== 场景 B：status 轮询 ==========
    section(
        f"场景 B: status 轮询 GET /api/v1/documents/{task_id}/status "
        f"(最多 {MAX_POLL} 次, {POLL_SLEEP_SEC}s 间隔)"
    )
    try:
        if not task_id:
            raise RuntimeError("task_id 为空，跳过场景 B")
        url = f"{BASE_URI}/api/v1/documents/{task_id}/status"
        final_status = ""
        final_progress = None
        hit_terminal = False
        all_trace_match = True
        for i in range(1, MAX_POLL + 1):
            traceB = f"22222222-2222-4222-8222-2222222222{i:02d}"
            stamp = time.strftime("%H:%M:%S")
            print(f"URL: {url}  poll={i}  trace={traceB}  at={stamp}")
            resp = requests.get(url, headers=headers_org(traceB), timeout=10)
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print(
                f"status: {(body or {}).get('status')}  "
                f"progress: {(body or {}).get('progress')}"
            )
            tmatch = trace_check(resp, body, traceB)
            if not tmatch:
                all_trace_match = False
            final_status = (body or {}).get("status", "")
            final_progress = (body or {}).get("progress")
            if final_status in ("completed", "failed"):
                hit_terminal = True
                break
            time.sleep(POLL_SLEEP_SEC)
        passed = hit_terminal and (final_status == "completed") and all_trace_match
        add_result(
            "B_status_poll",
            passed,
            f"final={final_status} progress={final_progress} trace_all_match={all_trace_match}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("B_status_poll", False, f"exception: {e!r}")


    # ========== 场景 E：跨租户 403 ==========
    section(
        f"场景 E: 跨租户 403 GET /api/v1/documents/{task_id}/status (换 X-Org-Id)"
    )
    try:
        if not task_id:
            raise RuntimeError("task_id 为空，跳过场景 E")
        url = f"{BASE_URI}/api/v1/documents/{task_id}/status"
        traceE = "55555555-5555-4555-8555-555555555555"
        print(f"URL: {url}  trace={traceE}  foreign_org")
        resp = requests.get(url, headers=headers_foreign(traceE), timeout=10)
        body = safe_json(resp)
        print(f"HTTP status: {resp.status_code}")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, traceE)
        reason = (body or {}).get("detail", {}).get("reason")
        passed = (
            resp.status_code == 403
            and (body or {}).get("code") == "FORBIDDEN"
            and reason == "cross_tenant_access"
            and tmatch
        )
        add_result(
            "E_403_cross_tenant",
            passed,
            f"code={(body or {}).get('code')} reason={reason} trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("E_403_cross_tenant", False, f"exception: {e!r}")


    # ========== 场景 C：415 MIME 不对（.exe） ==========
    section("场景 C: 415 MIME 错误 POST /api/v1/documents/upload (.exe)")
    try:
        url = f"{BASE_URI}/api/v1/documents/upload"
        traceC = "33333333-3333-4333-8333-333333333333"
        with tempfile.TemporaryDirectory() as tmpdir:
            exe_path = Path(tmpdir) / "test_415.exe"
            exe_path.write_text("fake exe content for 415 test")
            print(f"URL: {url}  trace={traceC}  file={exe_path}")
            with exe_path.open("rb") as f:
                files = {"file": (exe_path.name, f, "application/x-msdownload")}
                resp = requests.post(
                    url, files=files, headers=headers_org(traceC), timeout=10
                )
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceC)
            detail = (body or {}).get("detail", {})
            mime = detail.get("mime_type")
            allowed = detail.get("allowed_mime_types", [])
            mime_not_allowed = mime not in ALLOWED_MIMES
            passed = (
                resp.status_code == 415
                and (body or {}).get("code") == "UNSUPPORTED_MEDIA_TYPE"
                and mime_not_allowed
                and len(allowed) == 3
                and tmatch
            )
            add_result(
                "C_415_mime",
                passed,
                f"code={(body or {}).get('code')} mime={mime} "
                f"allowed_count={len(allowed)} trace_match={tmatch}",
            )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("C_415_mime", False, f"exception: {e!r}")


    # ========== 场景 D：413 文件过大（100MB+1B） ==========
    section("场景 D: 413 文件过大 POST /api/v1/documents/upload (100MB+1B)")
    try:
        url = f"{BASE_URI}/api/v1/documents/upload"
        traceD = "44444444-4444-4444-8444-444444444444"
        with tempfile.TemporaryDirectory() as tmpdir:
            big_path = Path(tmpdir) / "test_413.pdf"
            # 用 sparse file：seek 到 100MB，写 1 字节，让 stat 报 100MB+1B。
            # NTFS / ReFS / ext4 / APFS 都支持；物理占用接近 0。
            with big_path.open("wb") as f:
                f.seek(100 * 1024 * 1024)
                f.write(b"\x01")
            actual = big_path.stat().st_size
            print(f"生成大文件: {big_path} ({actual} bytes, sparse)")
            print(f"URL: {url}  trace={traceD}")
            with big_path.open("rb") as f:
                files = {"file": (big_path.name, f, "application/pdf")}
                resp = requests.post(
                    url, files=files, headers=headers_org(traceD), timeout=30
                )
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceD)
            detail = (body or {}).get("detail", {})
            passed = (
                resp.status_code == 413
                and (body or {}).get("code") == "FILE_TOO_LARGE"
                and detail.get("max_size_bytes") == 104857600
                and detail.get("limit_mb") == 100
                and tmatch
            )
            add_result(
                "D_413_too_large",
                passed,
                f"code={(body or {}).get('code')} limit_mb={detail.get('limit_mb')} "
                f"trace_match={tmatch}",
            )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("D_413_too_large", False, f"exception: {e!r}")


    # ========== 场景 F：404 不存在 ==========
    section("场景 F: 404 不存在 GET /api/v1/documents/{fake-uuid}/status")
    try:
        fake_uuid = str(uuid.uuid4())
        url = f"{BASE_URI}/api/v1/documents/{fake_uuid}/status"
        traceF = "66666666-6666-4666-8666-666666666666"
        print(f"伪造 UUID       : {fake_uuid}")
        print(f"URL: {url}  trace={traceF}")
        resp = requests.get(url, headers=headers_org(traceF), timeout=10)
        body = safe_json(resp)
        print(f"HTTP status: {resp.status_code}")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, traceF)
        detail_doc_id = (body or {}).get("detail", {}).get("document_id")
        passed = (
            resp.status_code == 404
            and (body or {}).get("code") == "DOCUMENT_NOT_FOUND"
            and detail_doc_id == fake_uuid
            and tmatch
        )
        add_result(
            "F_404_not_found",
            passed,
            f"code={(body or {}).get('code')} trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("F_404_not_found", False, f"exception: {e!r}")


    # ============================================================
    # 总汇总
    # ============================================================
    print()
    print("===== 总汇总 =====")
    name_w = max((len(r[0]) for r in results), default=10)
    for name, passed, detail in results:
        mark = "PASS" if passed else "FAIL"
        print(f"{name.ljust(name_w)}  {mark}  {detail}")
    total = len(results)
    pass_count = sum(1 for r in results if r[1])
    fail_count = total - pass_count
    print(f"PASS: {pass_count} / FAIL: {fail_count} / Total: {total}")
    print()
    print("===== 复制粘贴提示 =====")
    print("把上面所有输出（含 ===== 场景 X ===== 标记 + 总汇总）整段贴回给 CodeBuddy 即可。")
    print(f"任务 ID（供后续批次的 status 引用）：{task_id}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())