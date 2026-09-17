import type { ChatMessage, ChatSession } from "@/types/mock";

/**
 * 问答会话 Mock（p03）。
 *
 * ⚠️ 契约冲突提示：`POST /api/v1/agent/query` 在 openapi.yaml 中明确
 * 「单轮，不做多轮上下文」，而设计稿为多轮会话形态。此处为 UI 预留，
 * 待后端补齐会话接口后替换（见「接口对齐清单」）。
 */
export const MOCK_SESSIONS: ChatSession[] = [
  {
    id: "session-1",
    title: "数据安全合规梳理",
    updated_at_label: "刚刚",
    doc_count: 24,
  },
  {
    id: "session-2",
    title: "Q3 路线图关键节点",
    updated_at_label: "12 分钟前",
    doc_count: 9,
  },
  {
    id: "session-3",
    title: "华东客户访谈总结",
    updated_at_label: "昨天",
    doc_count: 6,
  },
  {
    id: "session-4",
    title: "知识图谱覆盖率",
    updated_at_label: "9月15日",
    doc_count: 31,
  },
  {
    id: "session-5",
    title: "API 规范变更影响",
    updated_at_label: "9月14日",
    doc_count: 12,
  },
];

const SESSION_1_MESSAGES: ChatMessage[] = [
  {
    id: "msg-1-1",
    role: "user",
    content: "哪些文档涉及数据安全合规？请按制度、流程和责任人分类。",
    created_at: "2026-09-17T14:52",
  },
  {
    id: "msg-1-2",
    role: "assistant",
    content:
      "知识库中共有 8 份文档直接涉及数据安全合规，主要集中在三类：\n1. 制度：安全合规手册、数据分级分类规范。\n2. 流程：数据访问审批、脱敏处理与审计流程。\n3. 责任人：安全委员会负责制度审批，数据平台主管负责执行。",
    created_at: "2026-09-17T14:52",
    confidence: "high",
    refused: false,
    // 批次 A 契约扩展：图谱证据用 kg_nodes / kg_relations 表达
    //（type 用受控投影枚举值 MENTIONS，真实关系名放 properties.relation_name）
    kg_nodes: [
      {
        id: "e-01",
        label: "Entity",
        entity_type: "制度",
        canonical_name: "数据安全合规",
        confidence: 0.95,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-02",
        label: "Entity",
        entity_type: "规范",
        canonical_name: "数据分级分类",
        confidence: 0.93,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-03",
        label: "Entity",
        entity_type: "组织",
        canonical_name: "安全委员会",
        confidence: 0.9,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-04",
        label: "Entity",
        entity_type: "制度",
        canonical_name: "合规制度",
        confidence: 0.88,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-05",
        label: "Entity",
        entity_type: "人员",
        canonical_name: "数据平台主管",
        confidence: 0.91,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-06",
        label: "Entity",
        entity_type: "流程",
        canonical_name: "访问审批流程",
        confidence: 0.92,
        kg_version: "20260917T0000Z-MOCK",
      },
    ],
    kg_relations: [
      {
        id: "r-01",
        type: "MENTIONS",
        source: "e-01",
        target: "e-02",
        properties: { relation_name: "包含" },
      },
      {
        id: "r-02",
        type: "MENTIONS",
        source: "e-03",
        target: "e-04",
        properties: { relation_name: "审批" },
      },
      {
        id: "r-03",
        type: "MENTIONS",
        source: "e-05",
        target: "e-06",
        properties: { relation_name: "负责执行" },
      },
    ],
    token_usage: {
      prompt_tokens: 2048,
      completion_tokens: 312,
      total_tokens: 2360,
    },
    citations: [
      {
        doc_id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
        page: 3,
        chunk_id: "chunk-0142",
        char_offset: 480,
        snippet: "……数据分级分类规范由安全委员会审定，覆盖公开、内部、机密三级……",
      },
      {
        doc_id: "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
        page: 7,
        chunk_id: "chunk-0311",
        char_offset: 1024,
        snippet: "……数据访问审批流程由数据平台主管负责执行，审计日志留存不少于 180 天……",
      },
      {
        doc_id: "2f5b8d70-9a14-4c83-b6e7-5d1a0f3c8e46",
        page: 2,
        chunk_id: "chunk-0058",
        char_offset: 216,
        snippet: "……脱敏处理与审计流程须纳入安全合规手册统一管理……",
      },
    ],
  },
];

const SESSION_2_MESSAGES: ChatMessage[] = [
  {
    id: "msg-2-1",
    role: "user",
    content: "Q3 产品路线图有哪些关键节点？",
    created_at: "2026-09-17T14:40",
  },
  {
    id: "msg-2-2",
    role: "assistant",
    content:
      "Q3 路线图包含 3 个关键节点：\n1. 7 月：GraphRAG 检索链路灰度，覆盖 3 个试点部门。\n2. 8 月：实体消解与人审工作台上线。\n3. 9 月：多模态解析（PDF / DOCX / CSV）全量放开。",
    created_at: "2026-09-17T14:40",
    confidence: "high",
    refused: false,
    kg_nodes: [
      {
        id: "e-07",
        label: "Entity",
        entity_type: "规划",
        canonical_name: "Q3 路线图",
        confidence: 0.94,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-08",
        label: "Entity",
        entity_type: "里程碑",
        canonical_name: "检索链路灰度",
        confidence: 0.9,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-09",
        label: "Entity",
        entity_type: "里程碑",
        canonical_name: "实体消解工作台",
        confidence: 0.89,
        kg_version: "20260917T0000Z-MOCK",
      },
      {
        id: "e-10",
        label: "Entity",
        entity_type: "里程碑",
        canonical_name: "多模态解析",
        confidence: 0.87,
        kg_version: "20260917T0000Z-MOCK",
      },
    ],
    kg_relations: [
      {
        id: "r-04",
        type: "MENTIONS",
        source: "e-07",
        target: "e-08",
        properties: { relation_name: "包含" },
      },
      {
        id: "r-05",
        type: "MENTIONS",
        source: "e-07",
        target: "e-09",
        properties: { relation_name: "包含" },
      },
      {
        id: "r-06",
        type: "MENTIONS",
        source: "e-07",
        target: "e-10",
        properties: { relation_name: "包含" },
      },
    ],
    token_usage: {
      prompt_tokens: 1536,
      completion_tokens: 208,
      total_tokens: 1744,
    },
    citations: [
      {
        doc_id: "8b2d4e10-6c31-4f77-9a20-1d5e8c3b6a02",
        page: 1,
        chunk_id: "chunk-0007",
        char_offset: 96,
        snippet: "……7 月完成检索链路灰度，试点范围限定在 3 个部门……",
      },
    ],
  },
];

const FALLBACK_MESSAGES: ChatMessage[] = [
  {
    id: "msg-f-1",
    role: "user",
    content: "这份材料里有哪些需要人工复核的结论？",
    created_at: "2026-09-17T11:20",
  },
  {
    id: "msg-f-2",
    role: "assistant",
    content:
      "当前图谱中该问题的可追溯证据不足，为避免编造引用，本次不给出结论。\n建议先补齐来源文档，或在「文档管理」中确认解析状态为「已完成」后重试。",
    created_at: "2026-09-17T11:20",
    refused: true,
    confidence: "low",
    // 拒答契约语义：无支撑证据 → 空列表；未调用 LLM → token_usage 为 null
    kg_nodes: [],
    kg_relations: [],
    token_usage: null,
    citations: [],
  },
];

export const MOCK_MESSAGES: Record<string, ChatMessage[]> = {
  "session-1": SESSION_1_MESSAGES,
  "session-2": SESSION_2_MESSAGES,
  "session-3": FALLBACK_MESSAGES,
  "session-4": FALLBACK_MESSAGES,
  "session-5": FALLBACK_MESSAGES,
};

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
