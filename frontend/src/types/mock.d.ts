/**
 * 设计稿所需的、当前契约（`contracts/openapi.yaml`）**尚未覆盖**的数据结构。
 *
 * ⚠️ 约束（项目规则 §功能预留原则）：
 * - 本文件只在 `frontend/` 内扩展，**不修改 `contracts/` 与 `backend/`**；
 * - `src/types/api.d.ts` 是 `npm run gen:api` 的生成物，**禁止手工修改**；
 * - 一旦后端补齐对应端点与 Pydantic 模型，应删除此处同名字段并改回
 *   `components["schemas"][...]`，同时在前端输出「接口对齐清单」。
 *
 * Sprint 5 批次 C 收口（`/documents` 列表、`/graph/overview`、`/entities/{id}` 三端点
 * 契约补齐）：原 mock 复刻的同名字段已迁移至 `api.d.ts::components["schemas"]`，
 * 此处仅保留**仍未实装**的预留类型。
 *
 * 字段命名对齐后端既有风格：snake_case。
 */

import type { components } from "@/types/api";

/** 契约既有类型别名（复用，避免重名手写） */
export type Citation = components["schemas"]["Citation"];
export type DocumentStatus = components["schemas"]["DocumentStatusResponse"]["status"];
export type ConfidenceLevel = components["schemas"]["AgentQueryResponse"]["confidence"];
export type GraphNode = components["schemas"]["GraphNode"];
export type GraphEdge = components["schemas"]["GraphEdge"];
export type TokenUsage = components["schemas"]["TokenUsage"];

/* ---- Sprint 7.2 批次 B 已进契约的 M4 疑点类型（Sprint 7.3 批次 C 前端消费） ---- */
export type AffiliationDetectResponse =
  components["schemas"]["AffiliationDetectResponse"];
export type AffiliationTaskResponse =
  components["schemas"]["AffiliationTaskResponse"];
export type AffiliationSuspicionItem =
  components["schemas"]["AffiliationSuspicionItem"];
export type AffiliationSuspicionListResponse =
  components["schemas"]["AffiliationSuspicionListResponse"];
export type AffiliationSuspicionPatchResponse =
  components["schemas"]["AffiliationSuspicionPatchResponse"];
export type AffiliationEvidenceRef =
  components["schemas"]["AffiliationEvidenceRef"];
/** 复核状态：`open` 为初始态（不可作为 PATCH 入参，契约已限定） */
export type AffiliationSuspicionStatus =
  AffiliationSuspicionItem["status"];
export type AffiliationSuspicionType =
  AffiliationSuspicionItem["suspicion_type"];
export type AffiliationSeverity = AffiliationSuspicionItem["severity"];

/* --------------------------------------------------------------------------
 * Sprint 5 批次 C 收口：以下类型已迁入契约 `components["schemas"]`，直接复用
 * ------------------------------------------------------------------------ */

export type DocumentFileType = components["schemas"]["DocumentFileType"];
export type DocumentListItem = components["schemas"]["DocumentListItem"];
export type DocumentListQuery = {
  /** `q` 关键字（前后端命名差异：后端沿用 q，前端 mock 用了 keyword；Sprint 5 批次 C 收口保留后端语义） */
  q?: string;
  /** `all` 表示不筛选 */
  status?: DocumentStatus | "all";
  page?: number;
  page_size?: number;
};
export type DocumentListResponse = components["schemas"]["DocumentListResponse"];
export type GraphCategory = components["schemas"]["GraphCategory"];
export type GraphOverviewNode = components["schemas"]["GraphOverviewNode"];
export type GraphOverviewEdge = components["schemas"]["GraphOverviewEdge"];
export type GraphOverviewResponse = components["schemas"]["GraphOverviewResponse"];
export type EntityAttribute = components["schemas"]["EntityAttribute"];
export type EntityRelation = components["schemas"]["EntityRelation"];
export type EntityDetail = components["schemas"]["EntityDetail"];

/* --------------------------------------------------------------------------
 * 知识问答（p03）
 * —— 契约 `POST /api/v1/agent/query` 为「单轮、不做多轮上下文」，而 UI 是多轮
 *    会话形态 ⇒ **会话只存在于本地**（`store/use-chat-store.ts`）。后端无会话端点，
 *    且 `qa_logs` 按脱敏纪律只存哈希、不存问答原文 ⇒ 服务端不存在"历史会话"的
 *    真相源（详见 R18）。**禁止**再用 Mock 会话充当历史。
 *
 *    ⚠️ 已随 R18 删除 `MetricOverview`（`/metrics/overview`）、`QaHistoryItem`
 *    （`/qa/history`）、`ReprocessResponse`（`POST /documents/{id}/reprocess`）
 *    三个契约外类型——留着只会诱导下一个人拿它们往屏幕上填数字。
 * ------------------------------------------------------------------------ */

export type ChatRole = "user" | "assistant";

export type ChatSession = {
  id: string;
  title: string;
  /** 展示用相对时间文案 */
  updated_at_label: string;

};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  created_at: string;
  /* ---- 以下仅 assistant 消息可能存在 ---- */
  citations?: Citation[];
  /**
   * 支撑本次回答的图谱节点（契约 `AgentQueryResponse.kg_nodes`）。
   * Sprint 4 批次 A 契约扩展后由 `mapAgentQueryResponse` 直接透传，
   * 取代原先的 `node_count` / `graph_paths` 降级占位。
   */
  kg_nodes?: GraphNode[];
  /**
   * 支撑本次回答的图谱关系（契约 `AgentQueryResponse.kg_relations`）；
   * 真实关系名见 `properties.relation_name`（后端受控投影约定）。
   */
  kg_relations?: GraphEdge[];
  /** LLM token 用量；拒答 / LLM 未返回 usage 时为 null（契约语义，非缺数） */
  token_usage?: TokenUsage | null;
  confidence?: ConfidenceLevel;
  refused?: boolean;
  /** 流式/加载占位 */
  pending?: boolean;
};

export type SendQuestionPayload = {
  session_id: string;
  question: string;
};
