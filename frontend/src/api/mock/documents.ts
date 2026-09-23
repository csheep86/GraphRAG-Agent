import type { components } from "@/types/api";
import type { DocumentListItem } from "@/types/mock";

type DocumentStatusResponse = components["schemas"]["DocumentStatusResponse"];
type DocumentChunkResponse = components["schemas"]["DocumentChunkResponse"];

/**
 * 文档列表 Mock（p02 表格逐行还原）。
 * ✅ 契约已实装（`GET /api/v1/documents`，Sprint 5 批次 C）：字段以
 * `components["schemas"]["DocumentListItem"]` 为准，仅 USE_MOCK=true 时返回。
 *
 * 注：契约里 `filename` 字段等于 `documents.filename_hash`（SHA-256 hex），
 * 演示场景下用**伪造 hex** 替代原文「企业知识库架构设计.pdf」——既符合
 * M5 §4.5「文件名原文不得回显」约束，又能让 mock 表格与真实接口字段形态一致。
 */
export const MOCK_DOCUMENTS: DocumentListItem[] = [
  {
    id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
    filename:
      "d41d8cd98f00b204e9800998ecf8427e1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a",
    file_type: "PDF",
    status: "completed",
    entity_count: 2846,
    uploaded_at: "2026-09-17T10:42:00+00:00",
    time_label: "10:42",
    task_id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
    trace_id: "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
  },
  {
    id: "8b2d4e10-6c31-4f77-9a20-1d5e8c3b6a02",
    filename:
      "5d41402abc4b2a76b9719d911017c5922a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a",
    file_type: "DOCX",
    status: "processing",
    entity_count: null,
    uploaded_at: "2026-09-17T10:18:00+00:00",
    time_label: "10:18",
    task_id: "8b2d4e10-6c31-4f77-9a20-1d5e8c3b6a02",
    trace_id: "1a4c9e2f-3b7d-42a1-8c6e-0f5b2d9a7e34",
  },
  {
    id: "6e7c1a93-2d58-4b6f-8a15-9c3e0d7b4f28",
    filename:
      "e10adc3949ba59abbe56e057f20f883e3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a",
    file_type: "PDF",
    status: "completed",
    entity_count: 1204,
    uploaded_at: "2026-09-16T18:36:00+00:00",
    time_label: "昨天 18:36",
    task_id: "6e7c1a93-2d58-4b6f-8a15-9c3e0d7b4f28",
    trace_id: "7d2b8f41-5a9c-4e30-b7f2-3c6a1d8e5b09",
  },
  {
    id: "2f5b8d70-9a14-4c83-b6e7-5d1a0f3c8e46",
    filename:
      "c81e728d9d4c2f636f067f89cc14862c4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a",
    file_type: "DOCX",
    status: "failed",
    entity_count: null,
    uploaded_at: "2026-09-16T16:20:00+00:00",
    time_label: "昨天 16:20",
    task_id: "2f5b8d70-9a14-4c83-b6e7-5d1a0f3c8e46",
    trace_id: "9c3e6b25-4f18-4a7d-9e02-8b5c7a1d3f60",
  },
  {
    id: "4d9a3c86-1e75-4b02-a8c4-7f2e5d0b9a13",
    filename:
      "a87ff679a2f3e71d9181a67b7542122c5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b",
    file_type: "PDF",
    status: "completed",
    entity_count: 3982,
    uploaded_at: "2026-09-15T14:08:00+00:00",
    time_label: "09-15 14:08",
    task_id: "4d9a3c86-1e75-4b02-a8c4-7f2e5d0b9a13",
    trace_id: "3a7f1c58-6d92-4e14-8b30-2a5d9c6f0e71",
  },
  {
    id: "1c8e5b42-7a30-4d96-b1f8-6e3c9a2d7b05",
    filename:
      "e4da3b7fbbce2345d7772b0674a318d5c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c",
    file_type: "CSV",
    status: "completed",
    entity_count: 512,
    uploaded_at: "2026-09-15T11:02:00+00:00",
    time_label: "09-15 11:02",
    task_id: "1c8e5b42-7a30-4d96-b1f8-6e3c9a2d7b05",
    trace_id: "5b0d3a97-2c64-4f81-a7e5-9d1b4c8f3a26",
  },
  {
    id: "9a3f7d15-8b42-4c60-9e31-0d7a6f2b5c84",
    filename:
      "1679091c5a880faf6fb5dcb6a47143f37d7d7d7d7d7d7d7d7d7d7d7d7d7d7d7d",
    file_type: "CSV",
    status: "pending",
    entity_count: null,
    uploaded_at: "2026-09-14T09:47:00+00:00",
    time_label: "09-14 09:47",
    task_id: "9a3f7d15-8b42-4c60-9e31-0d7a6f2b5c84",
    trace_id: "0e6c4b83-7f25-4a19-8d63-1b9a5c7e2f40",
  },
];

/** 知识库文档总量（设计稿固定展示 1,248） */
export const MOCK_DOCUMENT_TOTAL = 1248;

/** p01「最近文档处理」只展示前 4 条 */
export const MOCK_RECENT_DOCUMENTS = MOCK_DOCUMENTS.slice(0, 4);

/**
 * USE_MOCK=true 时 `getDocumentStatus` 直接返回完成态（Sprint 4.10.1.6）：
 * 让 p02 上传后状态轮询立刻进完成态，无需真实后端。
 * progress=1 表示完成（schema 限定 0–1，不是 0–100）。
 */
export const MOCK_DOCUMENT_STATUS: DocumentStatusResponse = {
  status: "completed",
  progress: 1,
  task_id: "00000000-0000-4000-8000-000000000001",
  trace_id: "00000000-0000-4000-8000-0000000000aa",
};

/**
 * USE_MOCK=true 时 `getDocumentChunk` 的返回（Sprint 6 批次 C 引用溯源抽屉）。
 *
 * 字段以契约 `DocumentChunkResponse` 为准。**明确标注为演示文本**：真实链路
 * （`USE_MOCK=false`）走 `/api/v1/documents/{id}/chunks/{chunk_id}`，与 §5.3
 * 「关 Mock 硬门槛」一致——本常量只在开发态零依赖时生效。
 */
export const MOCK_DOCUMENT_CHUNK: DocumentChunkResponse = {
  doc_id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
  chunk_id: "chunk-mock0001",
  text: "【Mock 原文】USE_MOCK=true 时的演示文本，不代表任何真实文档内容；置 false 后由后端 chunks.json 返回真实原文片段。",
  page: 1,
  char_start: 0,
  char_end: 120,
  trace_id: "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
};
