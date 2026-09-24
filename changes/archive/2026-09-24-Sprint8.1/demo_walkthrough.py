"""Sprint 8.1 批次 A：演示路径真机走查（在线服务 + 真实 Neo4j / LLM）。

用法（工作目录 = backend/；**先**确保服务已起）：

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8123
    uv run python ../changes/Sprint8.1/demo_walkthrough.py

纪律：
- **复用现有图谱，不重建**（决策 A13）：不触发 extract / kg.build，因此除「提问」外
  本脚本**不调 LLM**；检测是规则型算法，也不花钱；
- 上传用仓库内既有 4KB 样例 PDF（`mineru_mvp/input/complex_table.pdf`），
  走真实 MinerU 解析（该步有第三方额度消耗，单次、低价）；
- **计数走 `dev.db` 直读**（`sqlite3`），不通过 `GET /audit` 统计——后者自身会写
  一条自举行，会把演示路径的条数混进来（见 proposal 风险 3 / 7）。
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# 脚本位于 changes/ 下，需显式把 backend/（cwd）加进模块搜索路径，
# 才能 `import app.core.config` 复用在线服务的同一份配置（不在脚本里硬编码 org_id）。
sys.path.insert(0, str(Path.cwd()))

BASE_URL = "http://127.0.0.1:8123"
DB_PATH = Path("dev.db")
SAMPLE_PDF = Path("../mineru_mvp/input/complex_table.pdf")

QUESTION = "招商局集团有限公司与招商局轮船有限公司之间存在哪些关联？"


def _headers() -> dict[str, str]:
    """从**在线服务的同一份配置**取 dev 头：不许在脚本里硬编码 org_id。"""
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "X-Org-Id": str(settings.default_org_id),
        "X-Actor-Id": str(settings.default_actor_id),
    }


def audit_facts() -> dict[str, Any]:
    """直读 `dev.db` 统计审计表（**不**经 `/audit` 端点，避免自举行污染计数）。"""
    with sqlite3.connect(DB_PATH) as connection:
        tables = {row[0] for row in connection.execute(
            "select name from sqlite_master where type='table'"
        )}
        if "audit_log" not in tables:
            return {"audit_total": 0, "by_action": [], "distinct_trace": 0, "qa_rows": 0}

        facts: dict[str, Any] = {}
        facts["audit_total"] = list(
            connection.execute("select count(*) from audit_log")
        )[0][0]
        facts["distinct_trace"] = list(
            connection.execute("select count(distinct trace_id) from audit_log")
        )[0][0]
        facts["by_action"] = [
            (row[0], row[1], row[2])
            for row in connection.execute(
                "select action, status, count(*) from audit_log "
                "group by action, status order by min(ts)"
            )
        ]
        facts["qa_rows"] = (
            list(connection.execute("select count(*) from qa_logs"))[0][0]
            if "qa_logs" in tables
            else 0
        )
        facts["qa_detail"] = [
            tuple(row)
            for row in connection.execute(
                "select refused, citation_count, kg_version, trace_id from qa_logs"
            )
        ] if "qa_logs" in tables else []
        return facts


def _step(label: str) -> None:
    print(f"\n--- {label} ---")


def main(*, reuse_existing: bool = False, skip_qa: bool = False) -> None:
    """跑演示路径。

    :param reuse_existing: 复用本轮已完成的「上传 / 解析」步骤（不再消耗 MinerU 额度）
    :param skip_qa: 跳过「提问」——**唯一花钱的一步**，同一会话里已跑过一次就跳过
    """
    headers = _headers()
    client = httpx.Client(base_url=BASE_URL, headers=headers, timeout=120.0)

    before = audit_facts()
    print(f"[T0] 起步前 audit_log={before['audit_total']} 条（allowlist：health 不应写）")

    # 1) 上传（真实 MinerU 解析，异步）
    _step("1 上传")
    if reuse_existing:
        # 复用本轮已走通的「上传 → 解析」：这两步不再重跑，避免重复消耗第三方额度
        with sqlite3.connect(DB_PATH) as connection:
            latest = list(connection.execute(
                "select id from documents order by created_at desc limit 1"
            ))[0][0]
        doc_id = str(uuid.UUID(latest))
        print(f"    复用本轮已上传文档 doc_id={doc_id}（跳过上传 / 解析）")
    else:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), "application/pdf")},
        )
        response.raise_for_status()
        upload = response.json()
        doc_id = upload["task_id"]
        print(f"    200 task_id={doc_id} trace={upload['trace_id']}")

        # 2) 解析状态（轮询 3 次，间隔 5s）
        _step("2 解析状态轮询")
        for attempt in range(3):
            status_body = client.get(f"/api/v1/documents/{doc_id}/status").json()
            print(f"    #{attempt} status={status_body['status']}")
            if status_body["status"] in {"completed", "failed"}:
                break
            time.sleep(5)

    # 3) 文档列表
    _step("3 文档列表")
    listing = client.get("/api/v1/documents?page_size=5").json()
    print(f"    total={listing['total']} 首页 {len(listing['items'])} 条")

    # 4) 图谱总览 + 文档子图（复用现有图谱，**不**重建）
    _step("4 看图")
    overview = client.get("/api/v1/graph/overview").json()
    print(f"    entity_count={overview.get('entity_count')} doc_count={overview.get('doc_count')} "
          f"nodes={len(overview.get('nodes') or [])} edges={len(overview.get('edges') or [])} "
          f"kg_version={overview.get('kg_version')} truncated={overview.get('truncated')}")
    # 取**新上传之前**就存在的文档：刚解析的文档还没建图，子图为空属预期
    with sqlite3.connect(DB_PATH) as connection:
        preexisting = list(connection.execute(
            "select id from documents where id != ? order by created_at desc limit 1",
            (doc_id.replace('-', ''),),
        ))
    subgraph = client.get(f"/api/v1/documents/{preexisting[0][0]}/graph").json()
    print(f"    子图 nodes={len(subgraph.get('nodes') or [])} truncated={subgraph.get('truncated')}")

    # 5) 提问（**唯一花钱的一步**：真实 LLM）
    _step("5 提问")
    if skip_qa:
        print("    本次跳过（本轮已跑过一次，避免重复消耗 LLM 额度）")
    else:
        query = client.post("/api/v1/agent/query", json={"question": QUESTION}).json()
        print(f"    refused={query['refused']} citations={len(query['citations'])} "
              f"kg_version={query['kg_version']}")
        print(f"    trace_id={query['trace_id']}")
        print(f"    token_usage={query.get('token_usage')}")
        if query["citations"]:
            first = query["citations"][0]
            docId = first["doc_id"]
            chunk = client.get(
                f"/api/v1/documents/{docId}/chunks/{first['chunk_id']}"
            ).json()
            print(f"    溯源命中 chunk={chunk['chunk_id']} 文本长度={len(chunk['text'])}")

    # 6) 疑点检测（规则型，不花钱）
    _step("6 疑点检测")
    with sqlite3.connect(DB_PATH) as connection:
        completed_ids = [
            row[0]
            for row in connection.execute(
                "select id from documents where status='completed' and id != ? "
                "order by created_at desc limit 5",
                (doc_id.replace('-', ''),),
            )
        ]
    print(f"    检测输入 {len(completed_ids)} 份已完成文档（含本批新解析的一份已剔除：它尚未建图）")
    detect_response = client.post(
        "/api/v1/affiliation/detect", json={"doc_ids": completed_ids}
    )
    print(f"    HTTP {detect_response.status_code}")
    detect = detect_response.json()
    if "task_id" not in detect:
        print(f"    !! 未受理：{detect}")
        raise SystemExit(1)
    print(f"    task_id={detect['task_id']} trace={detect['trace_id']}")

    _step("6b 检测任务轮询")
    task_status = "pending"
    for attempt in range(10):
        task = client.get(f"/api/v1/affiliation/tasks/{detect['task_id']}").json()
        task_status = task["status"]
        print(f"    #{attempt} status={task_status}")
        if task_status in {"completed", "failed"}:
            if task_status == "completed":
                print(f"    summary={task.get('result_summary')}")
            break
        time.sleep(3)

    suspicions = client.get(
        f"/api/v1/affiliation/suspicions?task_id={detect['task_id']}"
    ).json()
    print(f"    疑点 {suspicions['total']} 条")
    reviewed_trace = None
    open_items = [item for item in suspicions["items"] if item["status"] == "open"]
    if open_items:
        target = open_items[0]
        patch = client.patch(
            f"/api/v1/affiliation/suspicions/{target['id']}",
            json={"status": "confirmed"},
        ).json()
        reviewed_trace = patch["trace_id"]
        print(f"    复核 {target['id']} -> {patch['status']} trace={reviewed_trace}")
    else:
        print("    （本批无 open 疑点，跳过复核）")

    # ---- 计数（直读库，不经 /audit 端点） ----
    after = audit_facts()
    print("\n================ 演示路径审计计数（直读 dev.db） ================")
    print(f"audit_log 总条数 = {after['audit_total']}  (distinct trace = {after['distinct_trace']})")
    print(f"qa_logs 条数     = {after['qa_rows']}")
    for action, status, count in after["by_action"]:
        print(f"    {action:<28} {status:<8} {count}")
    for row in after["qa_detail"]:
        print(f"    qa_logs: refused={row[0]} citations={row[1]} version={row[2]} trace={row[3]}")

    # ---- 端点自举行为：连调两次列表，验证自举行不会污染本次响应 ----
    _step("端点自举验证")
    first_call = client.get("/api/v1/audit?page_size=50").json()
    time.sleep(0.2)
    second_call = client.get("/api/v1/audit?page_size=50").json()
    print(f"    第一次 total={first_call['total']} items={len(first_call['items'])}")
    print(f"    第二次 total={second_call['total']} items={len(second_call['items'])} "
          f"（多出来的即是前一次查询自身写的 audit.list）")
    print(f"    默认 page={first_call['page']} page_size={first_call['page_size']}")

    if reviewed_trace:
        trace_view = client.get(f"/api/v1/audit/trace/{reviewed_trace}").json()
        print(f"    复核 trace 回看：total={trace_view['total']} "
              f"action={[i['action'] for i in trace_view['items']]}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="演示路径真机走查")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="复用本轮已完成的上传 / 解析步骤（不重复消耗 MinerU 额度）",
    )
    parser.add_argument(
        "--skip-qa",
        action="store_true",
        help="跳过提问（唯一花钱的一步）",
    )
    args = parser.parse_args()
    main(reuse_existing=args.reuse, skip_qa=args.skip_qa)
