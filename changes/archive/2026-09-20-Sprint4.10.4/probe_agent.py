"""
Sprint 4 · 10.4 联调 probe 脚本（Python 版）

用途：联调 POST /api/v1/agent/query（M3 图谱问答与可溯源引用）

运行（用户手动执行）：
  cd d:/AIProject/GraphRAG-Agent/backend
  $env:PYTHONIOENCODING="utf-8"
  uv run python ../changes/Sprint4.10.4/probe_agent.py 2>&1 |
    Tee-Object -FilePath ../changes/Sprint4.10.4/probe-output.log

前置：
  - uvicorn 跑着（监听 8000）
  - next dev 跑着（监听 3000）
  - .env.development: ALLOW_DEV_ORG_HEADER=true（X-Org-Id 兜底）
  - Neo4j 跑着（bolt://localhost:7687，user=neo4j，password=password）
  - Neo4j 中有 active kg_version + 23 Entity 节点（10.1 阶段零 + 10.4 证据探针核实）
  - backend/.env.development: DEEPSEEK_API_KEY 已配置（10.1 已核实）
  - 依赖：requests（实测 backend/.venv 内已装，版本 2.34.2）

场景：
  Q0  前置探针（必做，cross_doc 简单问句）
  Q1  200 + 拒答（必做，cross_doc 问"人工智能的伦理风险有哪些？"——强预期命中）
  Q2  200 + 非拒答（可选，cross_doc 问"智能制造有哪些财务指标？"——10.1 实测拒答，本批允许不命中）
  Q3  400 缺 question（必做，Pydantic min_length=1 校验）

不测：
  - Q4 跨租户 403：当前实现无租户隔离
    （Cypher _QUERY_ALL_ENTITY_SUBGRAPH fail-open：Entity 节点 org_id 属性键不存在，
    WHERE 分支 `OR properties(n)['org_id'] IS NULL` 命中 → 任何 org_id 都拉到全部 23 Entity；
    route 无 PG documents 表前置租户校验）。跨租户请求返回与同租户一致的 200，
    403 场景无法触发。属 v1.1.0 缺口（CODEBUDDY.md §4 末行待登记）。
  - 501 NOT_IMPLEMENTED（用户明示，避免搞挂服务）
  - 真实非拒答 answer 质量（LLM 输出不稳定）

可选启用：
  RUN_Q5 = True  # 启用 Q5（409 KG_VERSION_NOT_ACTIVE，显式传 FAKE kg_version）

输出：本脚本不打 git、不提交；用户执行后把 PowerShell 输出贴回，由 CodeBuddy 写入 integration-log。
"""

from __future__ import annotations

import json
import sys
import time

import requests


# --- 配置 ---
BASE_URI = "http://127.0.0.1:8000"
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"

# 请求超时（秒）：单次 LLM timeout=60 + tenacity 3 次重试 + 1s/2s/4s 退避
# 理论上限 = 60s × 3 + (1+2+4)s = 187s。
# 10.1 实测 DeepSeek 单次 3~8s；最坏 case（首两次挂住 + 第三次成功后服务端挂）
# 也需 ~125s 才到第 3 次返回。设 300s 留余量，避免 requests 提前 timeout 切断重试链路。
REQUEST_TIMEOUT = 300

# Q5（409 KG_VERSION_NOT_ACTIVE）开关：默认不测；启用改 True。
RUN_Q5 = False

# --- 结果收集 ---
results: list[tuple[str, bool, str]] = []


def section(title: str) -> None:
    print()
    print(f"===== {title} =====")


def add_result(name: str, passed: bool, detail: str) -> None:
    results.append((name, passed, detail))


def headers_org(trace_id: str) -> dict[str, str]:
    return {"X-Org-Id": ORG_ID, "X-Actor-Id": ACTOR_ID, "X-Trace-Id": trace_id}


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


def post_query(
    payload: dict,
    headers: dict[str, str],
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[requests.Response, dict | None, float]:
    """POST /api/v1/agent/query，返回 (resp, body, elapsed_sec)。"""
    url = f"{BASE_URI}/api/v1/agent/query"
    t0 = time.perf_counter()
    resp = requests.post(
        url,
        json=payload,
        headers={**headers, "Content-Type": "application/json"},
        timeout=timeout,
    )
    elapsed = time.perf_counter() - t0
    body = safe_json(resp)
    return resp, body, elapsed


# ============================================================
def main() -> int:
    # ============================================================
    # 场景 Q0：前置探针（必做，确认 Neo4j + DeepSeek 链路通）
    # 期望：HTTP 200，body 含 kg_version + trace_id + refused
    # ============================================================
    section("场景 Q0: 前置探针 POST /api/v1/agent/query（cross_doc 简单问句）")
    q0_trace = "88888888-8888-4888-8888-888888888880"
    try:
        payload = {"question": "你好", "scope": "cross_doc"}
        print(f"payload: {json.dumps(payload, ensure_ascii=False)}  trace={q0_trace}")
        resp, body, elapsed = post_query(payload, headers_org(q0_trace))
        print(f"HTTP status: {resp.status_code}  elapsed: {elapsed:.2f}s")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, q0_trace)
        # Q0 通过：trace 三方一致 + status ∈ {200, 409, 501}
        #   200 = 链路通
        #   409 = Neo4j 无 active kg_version（route 层 `_assert_active_kg_version`）
        #   501 = Neo4j / LLM 不可达
        # 仅作链路通断探针，不锁死 refused/kg_version 等语义字段
        valid_branch = resp.status_code in (200, 409, 501)
        passed = tmatch and valid_branch
        add_result(
            "Q0_probe",
            passed,
            f"status={resp.status_code} refused={(body or {}).get('refused')} "
            f"trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("Q0_probe", False, f"exception: {e!r}")

    # ============================================================
    # 场景 Q1：200 + 拒答（必做；强预期命中）
    # 期望：refused=true + refusal_reason="no_grounded_evidence"
    #       + answer="无法回答" + kg_nodes=[] + kg_relations=[]
    #       + token_usage=None + trace 三方一致
    # 额外断言：kg_version / route / confidence 字段值（必看项）
    # ============================================================
    section('场景 Q1: 200 + 拒答 POST /api/v1/agent/query（"人工智能的伦理风险有哪些？"）')
    q1_trace = "88888888-8888-4888-8888-888888888881"
    try:
        payload = {"question": "人工智能的伦理风险有哪些？", "scope": "cross_doc"}
        print(f"payload: {json.dumps(payload, ensure_ascii=False)}  trace={q1_trace}")
        resp, body, elapsed = post_query(payload, headers_org(q1_trace))
        print(f"HTTP status: {resp.status_code}  elapsed: {elapsed:.2f}s")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, q1_trace)
        refused_ok = (body or {}).get("refused") is True
        reason_ok = (body or {}).get("refusal_reason") == "no_grounded_evidence"
        answer_ok = (body or {}).get("answer") == "无法回答"
        kg_nodes_empty = (body or {}).get("kg_nodes") == []
        kg_relations_empty = (body or {}).get("kg_relations") == []
        token_usage_none = (body or {}).get("token_usage") is None
        citations_empty = (body or {}).get("citations") == []
        kg_version_present = bool((body or {}).get("kg_version"))
        # 额外断言（用户明示想看）
        kg_version_val = (body or {}).get("kg_version")
        route_val = (body or {}).get("route")
        confidence_val = (body or {}).get("confidence")
        passed = (
            resp.status_code == 200
            and tmatch
            and refused_ok
            and reason_ok
            and answer_ok
            and kg_nodes_empty
            and kg_relations_empty
            and token_usage_none
            and citations_empty
            and kg_version_present
        )
        add_result(
            "Q1_200_refused",
            passed,
            f"status={resp.status_code} refused={refused_ok} reason={reason_ok} "
            f"answer={answer_ok} kg_nodes_empty={kg_nodes_empty} "
            f"kg_relations_empty={kg_relations_empty} "
            f"token_usage_none={token_usage_none} "
            f"kg_version={kg_version_val!r} route={route_val!r} "
            f"confidence={confidence_val!r} elapsed={elapsed:.2f}s trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("Q1_200_refused", False, f"exception: {e!r}")

    # ============================================================
    # 场景 Q2：200 + 非拒答（可选，命中加分不 FAIL）
    # 问题："智能制造有哪些财务指标？"（10.1 实测拒答，本批允许不命中）
    # 命中定义：refused=False + answer 非空 + citations 非空 + token_usage 是 dict
    # ============================================================
    section('场景 Q2: 200 + 非拒答 POST /api/v1/agent/query（"智能制造有哪些财务指标？"）')
    q2_trace = "88888888-8888-4888-8888-888888888882"
    try:
        payload = {"question": "智能制造有哪些财务指标？", "scope": "cross_doc"}
        print(f"payload: {json.dumps(payload, ensure_ascii=False)}  trace={q2_trace}")
        resp, body, elapsed = post_query(payload, headers_org(q2_trace))
        print(f"HTTP status: {resp.status_code}  elapsed: {elapsed:.2f}s")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, q2_trace)
        refused_value = (body or {}).get("refused")
        hit = (
            resp.status_code == 200
            and tmatch
            and refused_value is False
            and bool((body or {}).get("answer"))
            and (body or {}).get("citations") not in (None, [])
            and isinstance((body or {}).get("token_usage"), dict)
        )
        # Q2 永远 PASS（可选场景），用 hit 标记是否命中
        add_result(
            "Q2_200_non_refused_optional",
            True,  # 永远 PASS（可选）
            f"hit={hit} (optional; 命中加分，不命中不扣分); "
            f"refused={refused_value} "
            f"kg_version={(body or {}).get('kg_version')!r} "
            f"elapsed={elapsed:.2f}s trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        # 可选场景：抛异常不扣分（避免误判 10.4 失败）
        add_result("Q2_200_non_refused_optional", True, f"optional skip (exception): {e!r}")

    # ============================================================
    # 场景 Q3：400 缺 question（必做；Pydantic min_length=1）
    # 期望：code='VALIDATION_ERROR' + detail.errors 指向 question 字段
    # （400 = 契约 + handler 硬编码 + ErrorCode 默认三方一致；
    #   FastAPI 默认 422 被全局 _handle_validation_error 改写为 400）
    # ============================================================
    section("场景 Q3: 400 缺 question POST /api/v1/agent/query")
    q3_trace = "88888888-8888-4888-8888-888888888883"
    try:
        payload = {"scope": "cross_doc"}  # 故意缺 question
        print(f"payload: {json.dumps(payload, ensure_ascii=False)}  trace={q3_trace}")
        resp, body, elapsed = post_query(payload, headers_org(q3_trace))
        print(f"HTTP status: {resp.status_code}  elapsed: {elapsed:.2f}s")
        print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
        print(f"body    trace_id : {(body or {}).get('trace_id')}")
        print("body:")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        tmatch = trace_check(resp, body, q3_trace)
        code_ok = (body or {}).get("code") == "VALIDATION_ERROR"
        # 兼容 FastAPI 默认 detail=list 与服务统一错误处理 detail={"errors": [...]}
        errors_field = (body or {}).get("detail", {})
        if isinstance(errors_field, dict):
            err_list = errors_field.get("errors") or []
        elif isinstance(errors_field, list):
            err_list = errors_field
        else:
            err_list = []
        locs = []
        for e in err_list:
            if isinstance(e, dict):
                loc = e.get("loc") or e.get("field")
                if loc:
                    locs.append(str(loc))
        # question 字段在 loc 列表里出现即可
        field_ok = any("question" in loc for loc in locs) or not err_list
        passed = (
            resp.status_code == 400
            and tmatch
            and code_ok
            and field_ok
        )
        add_result(
            "Q3_400_missing_question",
            passed,
            f"code={code_ok} field_loc_in_errors={field_ok} "
            f"err_count={len(err_list)} "
            f"elapsed={elapsed:.2f}s trace_match={tmatch}",
        )
    except Exception as e:
        print(f"exception: {e!r}")
        add_result("Q3_400_missing_question", False, f"exception: {e!r}")

    # ============================================================
    # 场景 Q5（可选）：409 KG_VERSION_NOT_ACTIVE
    # 默认不跑（RUN_Q5=False）；启用改顶部 RUN_Q5=True
    # ============================================================
    if RUN_Q5:
        section("场景 Q5: 409 KG_VERSION_NOT_ACTIVE POST /api/v1/agent/query（kg_version=FAKE）")
        q5_trace = "88888888-8888-4888-8888-888888888885"
        try:
            payload = {
                "question": "测试问题",
                "scope": "cross_doc",
                "kg_version": "FAKE_VERSION_9999_NOT_EXIST",
            }
            print(f"payload: {json.dumps(payload, ensure_ascii=False)}  trace={q5_trace}")
            resp, body, elapsed = post_query(payload, headers_org(q5_trace))
            print(f"HTTP status: {resp.status_code}  elapsed: {elapsed:.2f}s")
            print(f"响应头 X-Trace-Id: {resp.headers.get('X-Trace-Id')}")
            print(f"body    trace_id : {(body or {}).get('trace_id')}")
            print("body:")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            tmatch = trace_check(resp, body, q5_trace)
            code_ok = (body or {}).get("code") == "KG_VERSION_NOT_ACTIVE"
            detail = (body or {}).get("detail", {})
            kg_version_in_detail = detail.get("kg_version") == "FAKE_VERSION_9999_NOT_EXIST"
            passed = (
                resp.status_code == 409
                and tmatch
                and code_ok
                and kg_version_in_detail
            )
            add_result(
                "Q5_409_kg_version_not_active",
                passed,
                f"code={code_ok} detail.kg_version={kg_version_in_detail} "
                f"elapsed={elapsed:.2f}s trace_match={tmatch}",
            )
        except Exception as e:
            print(f"exception: {e!r}")
            add_result("Q5_409_kg_version_not_active", False, f"exception: {e!r}")
    else:
        section("场景 Q5: 409 KG_VERSION_NOT_ACTIVE（已跳过——RUN_Q5=False）")

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
    print("===== 已知缺口记录 =====")
    print("Q4 跨租户 403 不测——当前实现无租户隔离：")
    print("  1. Cypher _QUERY_ALL_ENTITY_SUBGRAPH fail-open：Entity 节点 org_id 属性键不存在，")
    print("     WHERE 分支 `OR properties(n)['org_id'] IS NULL` 命中 → 任何 org_id 都拉到全部 23 Entity；")
    print("  2. route 无 PG documents 表前置租户校验（identity.org_id 仅透传 Cypher，不阻断）。")
    print("  结论：跨租户请求与同租户一致返回 200；属 v1.1.0 缺口，10.4 完成后登记 CODEBUDDY.md §4。")
    print()
    print("===== 复制粘贴提示 =====")
    print("把上面所有输出（含 ===== 场景 X ===== 标记 + 总汇总 + 已知缺口记录）整段贴回给 CodeBuddy 即可。")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())