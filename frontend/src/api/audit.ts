import type { components } from "@/types/api";

import { delay, request, shouldMock } from "./client";
import { MOCK_AUDIT_ITEMS } from "./mock/audit";

/**
 * M5 审计留痕的两个只读端点（Sprint 8.1 批次 A）。
 * ✅ 契约已实装：`GET /api/v1/audit`、`GET /api/v1/audit/trace/{trace_id}`
 *
 * 类型全部走 `components["schemas"]`——由 `npm run gen:api` 从契约生成，
 * 不在本文件另起一套标量类型（契约同步铁律）。
 */
export type AuditLogItem = components["schemas"]["AuditLogItem"];
export type AuditLogListResponse =
  components["schemas"]["AuditLogListResponse"];
export type AuditTraceResponse = components["schemas"]["AuditTraceResponse"];
export type AuditStatus = AuditLogItem["status"];

export type AuditListQuery = {
  /** 按 action 精确过滤；空 / undefined 表示不过滤 */
  action?: string;
  /** `success` / `failure`；"all" 由调用方转换为 undefined */
  status?: AuditStatus;
  /** 1-based 页码 */
  page?: number;
  /** 每页条数；后端默认 50、上限 100 */
  page_size?: number;
};

/**
 * 当前租户的审计列表（按 `ts DESC`）。
 *
 * **自举说明**：本接口自身也在 `/api/v1/*` 内，因此每次查询后端都会写一条
 * `action=audit.list` 的记录；该条**不会**出现在本次响应里（请求之后才写入），
 * 下一次刷新才会看到——这是后端行为，不是前端分页 bug。
 */
export async function listAuditLogs(
  query: AuditListQuery = {},
): Promise<AuditLogListResponse> {
  if (shouldMock("/api/v1/audit")) {
    await delay(260);

    const items = MOCK_AUDIT_ITEMS.filter(
      (item) => !query.status || item.status === query.status,
    );
    const page = query.page ?? 1;
    const pageSize = query.page_size ?? 50;
    const start = (page - 1) * pageSize;

    return {
      total: items.length,
      items: items.slice(start, start + pageSize),
      page,
      page_size: pageSize,
      trace_id: MOCK_AUDIT_ITEMS[0]?.trace_id ?? "",
    };
  }

  const search = new URLSearchParams();
  if (query.action) search.set("action", query.action);
  if (query.status) search.set("status", query.status);
  if (query.page) search.set("page", String(query.page));
  if (query.page_size) search.set("page_size", String(query.page_size));

  const qs = search.toString();
  return request<AuditLogListResponse>(`/api/v1/audit${qs ? `?${qs}` : ""}`);
}

/**
 * 按 trace_id 回看一次调用链的留痕（plan §7.2 步骤 6）。
 *
 * **不支持分页**（契约未定义 `page` / `page_size`，不引入无消费者参数）；
 * 查不到 / 跨租户均返回**空集**（不是错误）。
 */
export async function listAuditLogsByTrace(
  traceId: string,
): Promise<AuditTraceResponse> {
  if (shouldMock("/api/v1/audit/trace/{trace_id}")) {
    await delay(220);
    const items = MOCK_AUDIT_ITEMS.filter((item) => item.trace_id === traceId);
    return { trace_id: traceId, total: items.length, items };
  }

  return request<AuditTraceResponse>(
    `/api/v1/audit/trace/${encodeURIComponent(traceId)}`,
  );
}
