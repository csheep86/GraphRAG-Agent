import type { components } from "@/types/api";
import type { ChatMessage, SendQuestionPayload } from "@/types/mock";

import { delay, request, shouldMock } from "./client";
import { buildMockAnswer } from "./mock/qa";

/**
 * ⚠️ 这里**不再**提供 `listSessions` / `listMessages`（原打 `GET /api/v1/qa/sessions`，
 * 契约外 ⇒ `shouldMock()` 恒 true ⇒ 关 Mock 也静默返回 `MOCK_SESSIONS`，
 * 屏上的会话列表是编的）。
 *
 * 会话列表改由 `store/use-chat-store.ts` **本地维护**（见 R18）：列表里的每一条
 * 都是用户在本浏览器里真的问过、`POST /api/v1/agent/query` 真的答过的记录，
 * 不是服务端"历史会话"。
 *
 * **为什么不等后端补会话表**：后端 `qa_logs`（S8 已建已写）按脱敏纪律只存
 * `question_hash` / `answer_hash`，**不存原文** ⇒ 补一个 `/qa/sessions` 端点也
 * 重建不出会话内容。真要做服务端会话，需先裁决"是否明文留存问答"这一产品/合规问题。
 */

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
 * ✅ 契约已存在且已实装（v1.0.0）：`POST /api/v1/agent/query`
 * 注意：`USE_MOCK=true` 时走 Mock；置 false 后该端点走真实后端。
 */
export async function sendQuestion(
  payload: SendQuestionPayload,
): Promise<ChatMessage> {
  if (shouldMock("/api/v1/agent/query")) {
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
