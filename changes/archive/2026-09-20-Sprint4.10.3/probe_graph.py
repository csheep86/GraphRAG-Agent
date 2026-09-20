"""
Sprint 4 · 10.3 联调 probe 脚本（Python 版）

用途：联调 GET /api/v1/documents/{id}/graph（M1 接入 + Neo4j 子图查询）

运行（用户手动执行）：
  cd d:/AIProject/GraphRAG-Agent/backend
  uv run python ../changes/Sprint4.10.3/probe_graph.py 2>&1 | Tee-Object -FilePath ../changes/Sprint4.10.3/probe-output.log

前置：
  - uvicorn 跑着（监听 8000）
  - next dev 跑着（监听 3000）
  - .env.development: ALLOW_DEV_ORG_HEADER=true（X-Org-Id 兜底）
  - Neo4j 跑着（bolt://localhost:7687，user=neo4j，password=password）
  - 10.2 已跑过且 backend/dev.db 未重置 —— fae4a287-b701-4627-9020-c41a4f2ba0e0
    （10.2 场景 A 上传的 PDF 骨架文档）必须仍在 documents 表里；
    否则 P0/P1/P4 会因 PG 先于 Neo4j 判 404 而失败。脚本会在 P0 之前自动探测。
  - 依赖：requests（实测 backend/.venv 内已装，版本 2.34.2）

场景：
  P0  前置探针：用 10.2 doc_id 打 /graph，根据响应分支
  P1  200 + 空图（P0 = 200 时跑，验 Neo4j 文档子图查询契约）
  P2  409 KG_VERSION_NOT_ACTIVE（P0 = 409 时跑，验版本状态问题分支）
  P3  404 不存在（必做，随机 UUID）
  P4  403 跨租户（必做，10.2 doc_id + FOREIGN_ORG）

P1/P2 是互斥分支：P0 决定跑哪个。详见 backend/app/services/graphs.py:121-142
（Cypher 第一行 MATCH 非 OPTIONAL，无 Document 节点时返 0 行 → .single() 返 None
 → fetch_document_subgraph 返 ([], [], False) → 路由层 200 空图，不抛异常）。

不测：
  - G1 200 + 有 nodes/edges（需 cypher-shell 写 Document/Chunk/Entity fixture，
    属 v1.1.0 接入 MinerU + LangExtract 后的端到端联调范围）
  - G4 501 Neo4j 不可用（避免搞挂服务；501 语义已在阶段零 C 批次确认）

输出：本脚本不打 git、不提交；用户执行后把 PowerShell 输出贴回，由 CodeBuddy 写入 integration-log。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import requests


# --- 配置 ---
BASE_URI = "http://127.0.0.1:8000"
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"
FOREIGN_ORG_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"

# 10.2 场景 A 上传的 PDF 骨架文档的 task_id / document_id（同一 UUID）
# 要求：backend/dev.db 未重置 —— 否则 P0/P1/P4 会因 PG 404 失败。
# 该值由 10.2 probe-output.log 场景 A 的 body.task_id 提取（手抄已二次复核）。
DOC_ID_FROM_10_2 = "fae4a287-b701-4627-9020-c41a4f2ba0e0"


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
    return {
        "X-Org-Id": FOREIGN_ORG_ID,
        "X-Actor-Id": ACTOR_ID,
        "X-Trace-Id": trace_id,
    }


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
    url_graph = f"{BASE_URI}/api/v1/documents/{DOC_ID_FROM_10_2}/graph"
    url_status = f"{BASE_URI}/api/v1/documents/{DOC_ID_FROM_10_2}/status"

    # ============================================================
    # 前置校验：10.2 doc_id 是否仍在 PG 里
    # （避免 PG 已重置后 P0/P1/P4 因 404 全军覆没）
    # ============================================================
    section(f"前置校验: 10.2 doc_id {DOC_ID_FROM_10_2} 是否仍在 PG")
    try:
        trace_pre = "77777777-7777-4777-8777-777777777700"
        resp = requests.get(url_status, headers=headers_org(trace_pre), timeout=10)
        body = safe_json(resp)
        print(f"URL: {url_status}  trace={trace_pre}")
        print(f"HTTP status: {resp.status_code}")
        if resp.status_code == 200 and body and body.get("status") is not None:
            print(f"PG 文档状态: {body.get('status')}")
            print(f"PG 文档 task_id: {body.get('task_id')}")
            print("✓ 10.2 doc_id 仍存在，继续 P0")
            doc_available = True
        else:
            print("✗ 10.2 doc_id 在 PG 中不存在（dev.db 已被重置）")
            print("  → P0/P1/P4 将失败，需先重跑 10.2 上传；P3 不受影响")
            doc_available = False
    except Exception as e:
        print(f"exception: {e!r}")
        doc_available = False

    if not doc_available:
        # 不直接 sys.exit —— P3 不依赖 10.2 doc_id，仍可测
        print()
        print("⚠ 警告：10.2 doc_id 不可用，P0/P1/P2/P4 将被跳过")

    # ============================================================
    # 场景 P0：前置探针（必做，决定 P1 还是 P2 分支）
    # ============================================================
    p0_status = None
    p0_body: dict | None = None
    if doc_available:
        section(f"场景 P0: 前置探针 GET /api/v1/documents/{DOC_ID_FROM_10_2}/graph")
        try:
            traceP0 = "77777777-7777-4777-8777-777777777770"
            print(f"URL: {url_graph}  trace={traceP0}")
            resp = requests.get(url_graph, headers=headers_org(traceP0), timeout=10)
            body = safe_json(resp)
            p0_status = resp.status_code
            p0_body = body
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceP0)
            # P0 通过定义：trace_id 三方一致 + status ∈ {200, 409, 501}
            # 三者都是 Neo4j 子图查询契约分支的合法入口；其余视为异常
            valid_branch = resp.status_code in (200, 409, 501)
            passed = tmatch and valid_branch
            add_result(
                "P0_probe",
                passed,
                f"status={resp.status_code} trace_match={tmatch}",
            )
        except Exception as e:
            print(f"exception: {e!r}")
            add_result("P0_probe", False, f"exception: {e!r}")
    else:
        section("场景 P0: 前置探针（已跳过 —— 10.2 doc_id 不可用）")

    # ============================================================
    # 场景 P1：200 + 空图（P0 = 200 分支；Neo4j 可达 + 有 active 版本）
    # 期望：version_status='active' + nodes=[] + edges=[] + truncated=false
    #       + doc_id 一致 + kg_version 非空
    # ============================================================
    if doc_available and p0_status == 200:
        section(f"场景 P1: 200 + 空图 GET /api/v1/documents/{DOC_ID_FROM_10_2}/graph")
        try:
            traceP1 = "77777777-7777-4777-8777-777777777771"
            print(f"URL: {url_graph}  trace={traceP1}")
            resp = requests.get(url_graph, headers=headers_org(traceP1), timeout=10)
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceP1)
            # 契约字段对齐（DOCUMENT_GRAPH_KEYS, tests/test_graph_and_agent_routes.py:35-45）
            expected_keys = {
                "doc_id",
                "kg_version",
                "version_status",
                "nodes",
                "edges",
                "node_count",
                "relation_count",
                "truncated",
                "trace_id",
            }
            keys_match = set((body or {}).keys()) == expected_keys
            version_status_ok = (body or {}).get("version_status") == "active"
            doc_id_ok = (body or {}).get("doc_id") == DOC_ID_FROM_10_2
            kg_version_ok = bool((body or {}).get("kg_version"))
            nodes_empty = (body or {}).get("nodes") == []
            edges_empty = (body or {}).get("edges") == []
            truncated_ok = (body or {}).get("truncated") is False
            node_count_ok = (body or {}).get("node_count") == 0
            relation_count_ok = (body or {}).get("relation_count") == 0
            passed = (
                resp.status_code == 200
                and tmatch
                and keys_match
                and version_status_ok
                and doc_id_ok
                and kg_version_ok
                and nodes_empty
                and edges_empty
                and truncated_ok
                and node_count_ok
                and relation_count_ok
            )
            add_result(
                "P1_200_empty_graph",
                passed,
                f"status={resp.status_code} keys_match={keys_match} "
                f"version_status={version_status_ok} nodes_empty={nodes_empty} "
                f"edges_empty={edges_empty} truncated={truncated_ok} "
                f"trace_match={tmatch}",
            )
        except Exception as e:
            print(f"exception: {e!r}")
            add_result("P1_200_empty_graph", False, f"exception: {e!r}")
    else:
        section(
            "场景 P1: 200 + 空图（已跳过 —— P0 状态不是 200，或 10.2 doc_id 不可用）"
        )

    # ============================================================
    # 场景 P2：409 KG_VERSION_NOT_ACTIVE（P0 = 409 分支；Neo4j 可达但无 active）
    # 期望：code='KG_VERSION_NOT_ACTIVE' + detail.status='none'
    #       + detail.document_id=doc_id + detail.hint 非空
    # ============================================================
    if doc_available and p0_status == 409:
        section(f"场景 P2: 409 KG_VERSION_NOT_ACTIVE")
        try:
            traceP2 = "77777777-7777-4777-8777-777777777772"
            print(f"URL: {url_graph}  trace={traceP2}")
            resp = requests.get(url_graph, headers=headers_org(traceP2), timeout=10)
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceP2)
            detail = (body or {}).get("detail", {})
            passed = (
                resp.status_code == 409
                and (body or {}).get("code") == "KG_VERSION_NOT_ACTIVE"
                and detail.get("status") == "none"
                and detail.get("document_id") == DOC_ID_FROM_10_2
                and bool(detail.get("hint"))
                and tmatch
            )
            add_result(
                "P2_409_kg_version_not_active",
                passed,
                f"code={(body or {}).get('code')} "
                f"detail.status={detail.get('status')} "
                f"trace_match={tmatch}",
            )
        except Exception as e:
            print(f"exception: {e!r}")
            add_result("P2_409_kg_version_not_active", False, f"exception: {e!r}")
    else:
        section(
            "场景 P2: 409（已跳过 —— P0 状态不是 409，或 10.2 doc_id 不可用）"
        )

    # ============================================================
    # 场景 P3：404 不存在（必做；随机 UUID，先 PG 判）
    # ============================================================
    section("场景 P3: 404 不存在 GET /api/v1/documents/{fake-uuid}/graph")
    try:
        fake_uuid = str(uuid.uuid4())
        url_p3 = f"{BASE_URI}/api/v1/documents/{fake_uuid}/graph"
        traceP3 = "77777777-7777-4777-8777-777777777773"
        print(f"伪造 UUID       : {fake_uuid}")
        print(f"URL: {url_p3}  trace={traceP3}")
        resp = requests.get(url_p3, headers=headers_org(traceP3), timeout=10)
        body = safe_json(resp)
        print(f"HTTP status: {resp.status_code}")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, traceP3)
        detail_doc_id = (body or {}).get("detail", {}).get("document_id")
        passed = (
            resp.status_code == 404
            and (body or {}).get("code") == "DOCUMENT_NOT_FOUND"
            and detail_doc_id == fake_uuid
            and tmatch
        )
        add_result(
            "P3_404_not_found",
            passed,
            f"code={(body or {}).get('code')} trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("P3_404_not_found", False, f"exception: {e!r}")

    # ============================================================
    # 场景 P4：403 跨租户（必做；10.2 doc_id + FOREIGN_ORG_ID，先 PG 判）
    # ============================================================
    if doc_available:
        section(f"场景 P4: 跨租户 403 GET /api/v1/documents/{DOC_ID_FROM_10_2}/graph")
        try:
            traceP4 = "77777777-7777-4777-8777-777777777774"
            print(f"URL: {url_graph}  trace={traceP4}  foreign_org")
            resp = requests.get(url_graph, headers=headers_foreign(traceP4), timeout=10)
            body = safe_json(resp)
            print(f"HTTP status: {resp.status_code}")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, traceP4)
            reason = (body or {}).get("detail", {}).get("reason")
            passed = (
                resp.status_code == 403
                and (body or {}).get("code") == "FORBIDDEN"
                and reason == "cross_tenant_access"
                and tmatch
            )
            add_result(
                "P4_403_cross_tenant",
                passed,
                f"code={(body or {}).get('code')} reason={reason} trace_match={tmatch}",
            )
        except Exception as e:
            print(f"exception: {e!r}")
            add_result("P4_403_cross_tenant", False, f"exception: {e!r}")
    else:
        section("场景 P4: 403 跨租户（已跳过 —— 10.2 doc_id 不可用）")

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
    print("===== 分支决策提示 =====")
    if p0_status == 200:
        print("P0 = 200：跑了 P1（200 + 空图），未跑 P2（Neo4j 有 active 版本）")
    elif p0_status == 409:
        print("P0 = 409：跑了 P2（409 KG_VERSION_NOT_ACTIVE），未跑 P1（Neo4j 无 active 版本）")
    elif p0_status == 501:
        print("P0 = 501：Neo4j 不可达，按设计未测 501；本次 probe 仅有 P0/P3 两个有效场景")
    elif p0_status is None:
        print("P0 未跑：10.2 doc_id 不可用；本次 probe 仅有 P3 一个有效场景")
    print()
    print("===== 复制粘贴提示 =====")
    print("把上面所有输出（含 ===== 场景 X ===== 标记 + 总汇总）整段贴回给 CodeBuddy 即可。")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())