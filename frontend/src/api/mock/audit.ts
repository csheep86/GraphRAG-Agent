import type { AuditLogItem } from "@/api/audit";

/**
 * 审计 Mock 数据（Sprint 8.1 批次 A）。
 *
 * ⚠️ **刻意做得可识别为假**：actor / doc / trace 一律用 `00000000-…-9XXX` 段，
 * IP 用 `203.0.113.*`（RFC 5737 文档保留网段），资源路径带 `?mock=1`。
 * 理由与 `mock/affiliation.ts` §头部注释一致：**关 Mock 硬门槛**要求
 * `USE_MOCK=false` 下零假数据，Mock 若与真机长得一样就无法一眼验出来源。
 *
 * 形状严格对齐契约 `AuditLogItem`：不增删字段；`detail` 只放
 * `status_code` / `method` / `path` 三个结构化键（与后端中间件口径一致）。
 */

const ACTOR_ID = "00000000-0000-4000-8000-000000009001";
const DOC_ID = "00000000-0000-4000-8000-000000009002";

function detail(statusCode: number, method: string, path: string) {
  return { status_code: statusCode, method, path };
}

export const MOCK_AUDIT_ITEMS: AuditLogItem[] = [
  {
    id: "00000000-0000-4000-8000-00000000a001",
    ts: "2026-09-24T09:00:06Z",
    action: "document.upload",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "POST /api/v1/documents/upload?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa01",
    detail: detail(200, "POST", "/api/v1/documents/upload"),
  },
  {
    id: "00000000-0000-4000-8000-00000000a002",
    ts: "2026-09-24T09:00:41Z",
    action: "document.status",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: DOC_ID,
    resource: "GET /api/v1/documents/00000000-...-9002/status?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa02",
    detail: detail(200, "GET", "/api/v1/documents/" + DOC_ID + "/status"),
  },
  {
    id: "00000000-0000-4000-8000-00000000a003",
    ts: "2026-09-24T09:02:12Z",
    action: "graph.activate",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "POST /api/v1/graph/versions/v-mock/activate?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa03",
    detail: detail(200, "POST", "/api/v1/graph/versions/v-mock/activate"),
  },
  {
    id: "00000000-0000-4000-8000-00000000a004",
    ts: "2026-09-24T09:03:55Z",
    action: "agent.query",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "POST /api/v1/agent/query?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa04",
    detail: detail(200, "POST", "/api/v1/agent/query"),
  },
  {
    id: "00000000-0000-4000-8000-00000000a005",
    ts: "2026-09-24T09:05:20Z",
    action: "affiliation.detect",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "POST /api/v1/affiliation/detect?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa05",
    detail: detail(202, "POST", "/api/v1/affiliation/detect"),
  },
  {
    id: "00000000-0000-4000-8000-00000000a006",
    ts: "2026-09-24T09:06:03Z",
    action: "affiliation.review",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "PATCH /api/v1/affiliation/suspicions/00000000-...-b1001?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa06",
    detail: detail(
      200,
      "PATCH",
      "/api/v1/affiliation/suspicions/00000000-0000-4000-8000-0000000b1001",
    ),
  },
  {
    // 失败样例：`detail` 仍只有结构化字段，**不**塞响应体原文（决策 A5）
    id: "00000000-0000-4000-8000-00000000a007",
    ts: "2026-09-24T09:07:44Z",
    action: "document.status",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: "00000000-0000-4000-8000-000000009999",
    resource: "GET /api/v1/documents/00000000-...-9999/status?mock=1",
    status: "failure",
    trace_id: "00000000-0000-4000-8000-00000000aa07",
    detail: detail(
      404,
      "GET",
      "/api/v1/documents/00000000-0000-4000-8000-000000009999/status",
    ),
  },
  {
    id: "00000000-0000-4000-8000-00000000a008",
    ts: "2026-09-24T09:08:12Z",
    action: "http.get./api/v1/audit",
    actor_id: ACTOR_ID,
    actor_ip: "203.0.113.10",
    doc_id: null,
    resource: "GET /api/v1/audit?mock=1",
    status: "success",
    trace_id: "00000000-0000-4000-8000-00000000aa08",
    detail: detail(200, "GET", "/api/v1/audit"),
  },
];
