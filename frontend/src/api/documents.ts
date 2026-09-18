import type { components } from "@/types/api";
import type {
  DocumentListQuery,
  DocumentListResponse,
  DocumentListItem,
  ReprocessResponse,
} from "@/types/mock";

import { delay, mockId, request, shouldMock } from "./client";
import {
  MOCK_DOCUMENTS,
  MOCK_DOCUMENT_STATUS,
  MOCK_DOCUMENT_TOTAL,
  MOCK_RECENT_DOCUMENTS,
} from "./mock/documents";

/** 文档列表。契约缺失：后端需补 `GET /api/v1/documents`（q / status / page） */
export async function listDocuments(
  query: DocumentListQuery = {},
): Promise<DocumentListResponse> {
  if (shouldMock("/api/v1/documents")) {
    await delay(260);

    const keyword = query.keyword?.trim().toLowerCase() ?? "";
    const status = query.status ?? "all";

    const items = MOCK_DOCUMENTS.filter((doc) => {
      const matchStatus = status === "all" || doc.status === status;
      const matchKeyword =
        keyword.length === 0 || doc.filename.toLowerCase().includes(keyword);
      return matchStatus && matchKeyword;
    });

    const filtered = keyword.length > 0 || status !== "all";
    return {
      total: filtered ? items.length : MOCK_DOCUMENT_TOTAL,
      items,
    };
  }

  const search = new URLSearchParams();
  if (query.keyword) search.set("q", query.keyword);
  if (query.status && query.status !== "all") search.set("status", query.status);

  const qs = search.toString();
  return request<DocumentListResponse>(
    `/api/v1/documents${qs ? `?${qs}` : ""}`,
  );
}

/** 工作台「最近文档处理」。契约缺失：需后端补支持 limit 的列表端点 */
export async function listRecentDocuments(
  limit = 4,
): Promise<DocumentListItem[]> {
  if (shouldMock("/api/v1/documents")) {
    await delay(200);
    return MOCK_RECENT_DOCUMENTS.slice(0, limit);
  }

  const response = await listDocuments();
  return response.items.slice(0, limit);
}

/**
 * 上传文档。
 * ✅ 契约已存在：`POST /api/v1/documents/upload`（M1，异步受理，立即返回 task_id）。
 */
export async function uploadDocument(
  file: File,
): Promise<components["schemas"]["UploadResponse"]> {
  if (shouldMock("/api/v1/documents/upload")) {
    await delay(720);
    return {
      status: "pending",
      task_id: mockId("task"),
      trace_id: mockId("trace"),
    };
  }

  const form = new FormData();
  form.append("file", file);

  return request<components["schemas"]["UploadResponse"]>(
    "/api/v1/documents/upload",
    { method: "POST", body: form },
  );
}

/**
 * 查询解析状态。
 * ✅ 契约已存在：`GET /api/v1/documents/{id}/status`
 * 轮询建议：首次 2s，3 次后降为 10s（契约注释）。
 */
export async function getDocumentStatus(
  documentId: string,
): Promise<components["schemas"]["DocumentStatusResponse"]> {
  if (shouldMock("/api/v1/documents/{id}/status")) {
    await delay(180);
    return MOCK_DOCUMENT_STATUS;
  }

  return request<components["schemas"]["DocumentStatusResponse"]>(
    `/api/v1/documents/${documentId}/status`,
  );
}

/** 重新处理。契约缺失：需后端补 `POST /api/v1/documents/{id}/reprocess` */
export async function reprocessDocument(
  documentId: string,
): Promise<ReprocessResponse> {
  if (shouldMock("/api/v1/documents/{id}/reprocess")) {
    await delay(420);
    return {
      task_id: mockId("task"),
      status: "processing",
      trace_id: mockId("trace"),
    };
  }

  return request<ReprocessResponse>(
    `/api/v1/documents/${documentId}/reprocess`,
    { method: "POST" },
  );
}
