import type { components } from "@/types/api";
import type {
  ChatMessage,
  ChatSession,
  SendQuestionPayload,
} from "@/types/mock";

import { USE_MOCK, delay, request } from "./client";
import { MOCK_MESSAGES, MOCK_SESSIONS, buildMockAnswer } from "./mock/qa";

/** 会话列表。契约缺失：需后端补 `GET /api/v1/qa/sessions` */
export async function listSessions(): Promise<ChatSession[]> {
  if (USE_MOCK) {
    await delay(200);
    return MOCK_SESSIONS;
  }

  return request<ChatSession[]>("/api/v1/qa/sessions");
}

/** 会话消息。契约缺失：需后端补 `GET /api/v1/qa/sessions/{id}` */
export async function listMessages(
  sessionId: string,
): Promise<ChatMessage[]> {
  if (USE_MOCK) {
    await delay(260);
    return MOCK_MESSAGES[sessionId] ?? [];
  }

  return request<ChatMessage[]>(`/api/v1/qa/sessions/${sessionId}`);
}

/**
 * 契约响应 → 前端会话消息的适配器。
 *
 * Sprint 4 批次 A 契约扩展（Sprint 3 缺口 1 偿还）：
 * `AgentQueryResponse` 已含 `kg_nodes` / `kg_relations` / `token_usage`，
 * 原先对 `node_count` / `relation_count` / `graph_paths` 的降级处理已移除，
 * 三字段直接透传给 p03「引用证据」面板。
 */
export function mapAgentQueryResponse(
  response: components["schemas"]["AgentQueryResponse"],
): ChatMessage {
  return {
    id: `msg-${response.trace_id}`,
    role: "assistant",
    content: response.answer,
    created_at: new Date().toISOString().slice(0, 16),
    citations: response.citations,
    confidence: response.confidence,
    refused: response.refused,
    kg_nodes: response.kg_nodes ?? [],
    kg_relations: response.kg_relations ?? [],
    token_usage: response.token_usage ?? null,
  };
}

/**
 * 图谱问答。
 * ✅ 契约已存在：`POST /api/v1/agent/query`
 * 注意：当前后端实现状态为 501 NOT_IMPLEMENTED（Sprint 3 范围），
 * 因此默认走 Mock。
 */
export async function sendQuestion(
  payload: SendQuestionPayload,
): Promise<ChatMessage> {
  if (USE_MOCK) {
    await delay(900);
    return buildMockAnswer(payload.question);
  }

  const response = await request<
    components["schemas"]["AgentQueryResponse"]
  >("/api/v1/agent/query", {
    method: "POST",
    body: JSON.stringify({
      question: payload.question,
      scope: "cross_doc",
    }),
  });

  return mapAgentQueryResponse(response);
}
