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
 * 工作台概览（p01）—— 契约缺失，需后端补 GET /api/v1/metrics/overview
 * ------------------------------------------------------------------------ */

export type MetricOverview = {
  /** 已处理文档数 */
  processed_documents: number;
  /** 已处理文档数环比（%），正数为上升 */
  processed_documents_delta_pct: number;
  /** KG 实体总数 */
  kg_entities: number;
  /** 已建立的实体关系总数 */
  kg_relations: number;
  /** 今日回答次数 */
  today_answers: number;
  /** 今日活跃用户数 */
  active_users: number;
  /** 回答成功率（%） */
  answer_success_rate: number;
  /** 回答成功率环比（%） */
  answer_success_rate_delta_pct: number;
};

/* --------------------------------------------------------------------------
 * 文档管理 —— 仅「重新处理」仍为 Mock 预留（后端未实装 POST /api/v1/documents/{id}/reprocess）
 * ------------------------------------------------------------------------ */

/** 「重新处理」响应；契约缺失，需后端补 POST /api/v1/documents/{id}/reprocess */
export type ReprocessResponse = {
  task_id: string;
  status: DocumentStatus;
  trace_id: string;
};

/* --------------------------------------------------------------------------
 * 问答历史（p01 最近问答历史）
 * —— 契约缺失，需后端补 GET /api/v1/qa/history
 * ------------------------------------------------------------------------ */

export type QaHistoryItem = {
  id: string;
  question: string;
  /** 展示用相对时间文案（Mock 直接返回，避免时区换算） */
  asked_at_label: string;
  citation_count: number;
};

/* --------------------------------------------------------------------------
 * 知识问答（p03）
 * —— 契约 `POST /api/v1/agent/query` 明确为「单轮、不做多轮上下文」，
 *    与设计稿的多轮会话形态冲突，故会话相关结构全部为 Mock 预留。
 * ------------------------------------------------------------------------ */

export type ChatRole = "user" | "assistant";

export type ChatSession = {
  id: string;
  title: string;
  /** 展示用相对时间文案 */
  updated_at_label: string;
  /** 检索所覆盖的文档数（p03 会话副标题「基于 N 份文档」）；契约缺失 */
  doc_count: number;
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