import type { ChatMessage } from "@/types/mock";

/**
 * 问答 Mock 数据（仅保留 `POST /api/v1/agent/query` 的回答模拟）。
 *
 * ⚠️ **会话类 Mock（`MOCK_SESSIONS` / `MOCK_MESSAGES`）已删除（R18）**：
 * 它们服务的是 `GET /api/v1/qa/sessions`——契约外端点，`shouldMock()` 对它恒
 * 返回 true，导致 `USE_MOCK=false` 时屏幕上仍显示编造的历史会话。
 * 会话列表现已改为 `store/use-chat-store.ts` 的本地真历史，故这些编造数据随之删除，
 * 避免下一个人再拿它去"填占位"。
 */

/** `POST /api/v1/agent/query` 的 Mock 回答（模拟真实契约返回结构） */
export function buildMockAnswer(question: string): ChatMessage {
  return {
    id: `msg-${Math.random().toString(36).slice(2, 10)}`,
    role: "assistant",
    content: `已基于当前 active 图谱版本检索「${question}」。\n命中 3 个相关实体与 2 条关系路径，结论如下：\n1. 该问题可由现有图谱直接支撑，证据见下方引用来源。\n2. 引用覆盖率 100%，未做推测性补全。`,
    created_at: "2026-09-17T15:00",
    confidence: "medium",
    refused: false,
    kg_nodes: [
      {
        id: "e-11",
        label: "Entity",
        entity_type: "制度",
        canonical_name: "数据安全合规",
        confidence: 0.95,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-12",
        label: "Entity",
        entity_type: "规范",
        canonical_name: "数据分级分类",
        confidence: 0.93,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-13",
        label: "Entity",
        entity_type: "人员",
        canonical_name: "数据平台主管",
        confidence: 0.91,
        kg_version: "20260917T0000Z-MOCK",
      },
    ],
    kg_relations: [
      {
        id: "r-07",
        type: "MENTIONS",
        source: "e-11",
        target: "e-12",
        properties: { relation_name: "包含" },
      },
      {
        id: "r-08",
        type: "MENTIONS",
        source: "e-13",
        target: "e-06",
        properties: { relation_name: "负责执行" },
      },
    ],
    token_usage: {
      prompt_tokens: 1024,
      completion_tokens: 256,
      total_tokens: 1280,
    },
    citations: [
      {
        doc_id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
        page: 4,
        chunk_id: "chunk-0203",
        char_offset: 640,
        snippet: "……相关职责边界以本手册第 4 章为准……",
      },
    ],
  };
}
