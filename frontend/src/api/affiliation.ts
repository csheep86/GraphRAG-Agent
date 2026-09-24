import type {
  AffiliationDetectResponse,
  AffiliationSuspicionListResponse,
  AffiliationSuspicionPatchResponse,
  AffiliationSuspicionStatus,
  AffiliationTaskResponse,
} from "@/types/mock";

import { delay, mockId, request, shouldMock } from "./client";
import { MOCK_AFFILIATION_TASK, MOCK_SUSPICION_LIST } from "./mock/affiliation";

/**
 * 发起一次关联关系检测。
 * ✅ 契约已实装（Sprint 7.2 批次 B）：`POST /api/v1/affiliation/detect`
 *
 * 202 受理、检测异步执行；状态唯一真值源是 PG `affiliation_tasks` 表，
 * 前端拿 `task_id` 轮询 `getAffiliationTask`，**不**依赖进程内状态。
 */
export async function detectAffiliation(
  docIds: string[],
): Promise<AffiliationDetectResponse> {
  if (shouldMock("/api/v1/affiliation/detect")) {
    await delay(420);
    return {
      status: "pending",
      task_id: mockId("task"),
      trace_id: mockId("trace"),
    };
  }

  return request<AffiliationDetectResponse>("/api/v1/affiliation/detect", {
    method: "POST",
    body: JSON.stringify({ doc_ids: docIds }),
  });
}

/**
 * 查询检测任务状态。
 * ✅ 契约已实装：`GET /api/v1/affiliation/tasks/{id}`
 *
 * 轮询口径（决策 C3）：**首次 2s，3 次后降为 10s**——与契约注释及
 * `docs/02-product-outline.md:196` 一致；终止条件 `completed` / `failed`。
 * `failed` 时读 `error_code`（如 `KG_VERSION_NOT_ACTIVE`）而非当空列表处理。
 */
export async function getAffiliationTask(
  taskId: string,
): Promise<AffiliationTaskResponse> {
  if (shouldMock("/api/v1/affiliation/tasks/{id}")) {
    await delay(200);
    return { ...MOCK_AFFILIATION_TASK, task_id: taskId };
  }

  return request<AffiliationTaskResponse>(
    `/api/v1/affiliation/tasks/${encodeURIComponent(taskId)}`,
  );
}

/**
 * 疑点清单。
 * ✅ 契约已实装：`GET /api/v1/affiliation/suspicions`
 *
 * **不支持分页**（契约未定义 `page` / `page_size`，不引入无消费者参数）。
 * 不传 `task_id` 时后端返回最近一条 completed 任务的疑点；当前租户从未跑过
 * 检测时 `task_id` 为 `null`、`items` 为空——这是**空态**，不是错误。
 */
export async function listAffiliationSuspicions(
  taskId?: string,
): Promise<AffiliationSuspicionListResponse> {
  if (shouldMock("/api/v1/affiliation/suspicions")) {
    await delay(260);
    return MOCK_SUSPICION_LIST;
  }

  const qs = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
  return request<AffiliationSuspicionListResponse>(
    `/api/v1/affiliation/suspicions${qs}`,
  );
}

/**
 * 复核一条疑点（确认 / 驳回）。
 * ✅ 契约已实装：`PATCH /api/v1/affiliation/suspicions/{id}`
 *
 * 契约只允许 `dismissed` / `confirmed`——已复核的疑点**不可改回** `open`
 * （后端返 400），所以本页不提供"撤销"：做了就是假交互（决策 C5）。
 */
export async function reviewAffiliationSuspicion(
  suspicionId: string,
  status: Exclude<AffiliationSuspicionStatus, "open">,
): Promise<AffiliationSuspicionPatchResponse> {
  if (shouldMock("/api/v1/affiliation/suspicions/{id}")) {
    await delay(220);
    return {
      id: suspicionId,
      status,
      reviewed_at: new Date().toISOString(),
      reviewed_by: "00000000-0000-4000-8000-000000000001",
      trace_id: mockId("trace"),
    };
  }

  return request<AffiliationSuspicionPatchResponse>(
    `/api/v1/affiliation/suspicions/${encodeURIComponent(suspicionId)}`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );
}
