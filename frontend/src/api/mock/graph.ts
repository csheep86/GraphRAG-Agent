import type { components } from "@/types/api";
import type {
  EntityDetail,
  GraphOverviewResponse,
} from "@/types/mock";

type DocumentGraphResponse = components["schemas"]["DocumentGraphResponse"];

/**
 * 全局知识图谱 Mock（p04）。
 * 契约缺失：现有 `GET /api/v1/documents/{id}/graph` 为文档级子图，
 * 设计稿需要全局图谱 + 实体详情，故此处为 UI 预留。
 */
export const MOCK_GRAPH_OVERVIEW: GraphOverviewResponse = {
  doc_count: 1248,
  entity_count: 86492,
  relation_count: 246810,
  nodes: [
    {
      id: "e-topic-compliance",
      name: "数据安全合规",
      type: "核心主题",
      category: "topic",
      weight: 1.65,
      seed_x: 0.14,
      seed_y: 0.38,
    },
    {
      id: "e-norm-classification",
      name: "数据分级分类",
      type: "规范",
      category: "norm",
      weight: 1,
      seed_x: 0.3,
      seed_y: 0.24,
    },
    {
      id: "e-system-policy",
      name: "合规制度",
      type: "制度",
      category: "system",
      weight: 1.1,
      seed_x: 0.63,
      seed_y: 0.24,
    },
    {
      id: "e-org-committee",
      name: "安全委员会",
      type: "组织",
      category: "org",
      weight: 1,
      seed_x: 0.45,
      seed_y: 0.33,
    },
    {
      id: "e-norm-audit-log",
      name: "审计日志",
      type: "数据",
      category: "norm",
      weight: 0.9,
      seed_x: 0.68,
      seed_y: 0.44,
    },
    {
      id: "e-topic-approval",
      name: "访问审批流程",
      type: "流程",
      category: "topic",
      weight: 1,
      seed_x: 0.33,
      seed_y: 0.55,
    },
    {
      id: "e-org-data-owner",
      name: "数据平台主管",
      type: "人员",
      category: "org",
      weight: 0.9,
      seed_x: 0.52,
      seed_y: 0.6,
    },
  ],
  edges: [
    {
      id: "r-001",
      source: "e-topic-compliance",
      target: "e-norm-classification",
      relation: "包含",
    },
    {
      id: "r-002",
      source: "e-topic-compliance",
      target: "e-topic-approval",
      relation: "关联流程",
    },
    {
      id: "r-003",
      source: "e-topic-compliance",
      target: "e-norm-audit-log",
      relation: "审计覆盖",
    },
    {
      id: "r-004",
      source: "e-topic-compliance",
      target: "e-org-committee",
      relation: "归口",
    },
    {
      id: "r-005",
      source: "e-org-committee",
      target: "e-system-policy",
      relation: "审批",
    },
    {
      id: "r-006",
      source: "e-system-policy",
      target: "e-norm-classification",
      relation: "约束",
    },
    {
      id: "r-007",
      source: "e-org-data-owner",
      target: "e-topic-approval",
      relation: "负责执行",
    },
    {
      id: "r-008",
      source: "e-norm-audit-log",
      target: "e-system-policy",
      relation: "留痕",
    },
  ],
};

const ENTITY_DETAILS: Record<string, EntityDetail> = {
  "e-topic-compliance": {
    id: "e-topic-compliance",
    name: "数据安全合规",
    tag: "核心主题",
    category: "topic",
    display_code: "ENTITY-008492",
    relation_count: 18,
    attributes: [
      { label: "首次出现", value: "企业知识库架构设计.pdf" },
      { label: "置信度", value: "0.98" },
      { label: "来源文档", value: "8 份" },
    ],
    relations: [
      {
        relation: "包含",
        target_id: "e-norm-classification",
        target_name: "数据分级分类",
      },
      {
        relation: "由…审批",
        target_id: "e-org-committee",
        target_name: "安全委员会",
      },
      {
        relation: "关联流程",
        target_id: "e-topic-approval",
        target_name: "访问审批流程",
      },
    ],
  },
  "e-norm-classification": {
    id: "e-norm-classification",
    name: "数据分级分类",
    tag: "规范",
    category: "norm",
    display_code: "ENTITY-002317",
    relation_count: 9,
    attributes: [
      { label: "首次出现", value: "安全合规手册 v2.docx" },
      { label: "置信度", value: "0.94" },
      { label: "来源文档", value: "4 份" },
    ],
    relations: [
      {
        relation: "被包含于",
        target_id: "e-topic-compliance",
        target_name: "数据安全合规",
      },
      {
        relation: "受约束于",
        target_id: "e-system-policy",
        target_name: "合规制度",
      },
    ],
  },
  "e-system-policy": {
    id: "e-system-policy",
    name: "合规制度",
    tag: "制度",
    category: "system",
    display_code: "ENTITY-001064",
    relation_count: 12,
    attributes: [
      { label: "首次出现", value: "安全合规手册 v2.docx" },
      { label: "置信度", value: "0.91" },
      { label: "来源文档", value: "6 份" },
    ],
    relations: [
      {
        relation: "由…审批",
        target_id: "e-org-committee",
        target_name: "安全委员会",
      },
      {
        relation: "约束",
        target_id: "e-norm-classification",
        target_name: "数据分级分类",
      },
    ],
  },
  "e-org-committee": {
    id: "e-org-committee",
    name: "安全委员会",
    tag: "组织",
    category: "org",
    display_code: "ENTITY-004871",
    relation_count: 14,
    attributes: [
      { label: "首次出现", value: "企业知识库架构设计.pdf" },
      { label: "置信度", value: "0.96" },
      { label: "来源文档", value: "5 份" },
    ],
    relations: [
      { relation: "审批", target_id: "e-system-policy", target_name: "合规制度" },
      {
        relation: "归口",
        target_id: "e-topic-compliance",
        target_name: "数据安全合规",
      },
    ],
  },
  "e-norm-audit-log": {
    id: "e-norm-audit-log",
    name: "审计日志",
    tag: "数据",
    category: "norm",
    display_code: "ENTITY-006105",
    relation_count: 7,
    attributes: [
      { label: "首次出现", value: "数据平台 API 规范.pdf" },
      { label: "置信度", value: "0.89" },
      { label: "来源文档", value: "3 份" },
    ],
    relations: [
      {
        relation: "留痕",
        target_id: "e-system-policy",
        target_name: "合规制度",
      },
      {
        relation: "审计覆盖",
        target_id: "e-topic-compliance",
        target_name: "数据安全合规",
      },
    ],
  },
  "e-topic-approval": {
    id: "e-topic-approval",
    name: "访问审批流程",
    tag: "流程",
    category: "topic",
    display_code: "ENTITY-005540",
    relation_count: 11,
    attributes: [
      { label: "首次出现", value: "企业知识库架构设计.pdf" },
      { label: "置信度", value: "0.93" },
      { label: "来源文档", value: "5 份" },
    ],
    relations: [
      {
        relation: "负责执行",
        target_id: "e-org-data-owner",
        target_name: "数据平台主管",
      },
      {
        relation: "关联流程",
        target_id: "e-topic-compliance",
        target_name: "数据安全合规",
      },
    ],
  },
  "e-org-data-owner": {
    id: "e-org-data-owner",
    name: "数据平台主管",
    tag: "人员",
    category: "org",
    display_code: "ENTITY-003392",
    relation_count: 6,
    attributes: [
      { label: "首次出现", value: "客户访谈纪要-华东.pdf" },
      { label: "置信度", value: "0.87" },
      { label: "来源文档", value: "2 份" },
    ],
    relations: [
      {
        relation: "负责执行",
        target_id: "e-topic-approval",
        target_name: "访问审批流程",
      },
    ],
  },
};

/** 默认选中的实体（对齐 p04 首屏「数据安全合规」） */
export const MOCK_DEFAULT_ENTITY_ID = "e-topic-compliance";

/**
 * USE_MOCK=true 时 `getDocumentGraph` 直接返回最小图谱（Sprint 4.10.1.6）：
 * 2 节点 + 1 边，让 p04 文档级力导向图可渲染。
 * 节点 / 边 / kg_version / trace_id 全部 mock；触发真实接口时由后端覆盖。
 */
export const MOCK_DOCUMENT_GRAPH: DocumentGraphResponse = {
  doc_id: "00000000-0000-4000-8000-000000000001",
  kg_version: "00000000-0000-4000-8000-0000000000aa",
  node_count: 2,
  relation_count: 1,
  truncated: false,
  version_status: "active",
  trace_id: "00000000-0000-4000-8000-0000000000bb",
  nodes: [
    {
      id: "e-mock-001",
      kg_version: "00000000-0000-4000-8000-0000000000aa",
      label: "Entity",
      canonical_name: "数据安全合规",
      entity_type: "主题",
      confidence: 0.95,
    },
    {
      id: "e-mock-002",
      kg_version: "00000000-0000-4000-8000-0000000000aa",
      label: "Entity",
      canonical_name: "数据分级分类",
      entity_type: "规范",
      confidence: 0.92,
    },
  ],
  edges: [
    {
      id: "r-mock-001",
      source: "e-mock-001",
      target: "e-mock-002",
      type: "RELATED",
    },
  ],
};

export function getMockEntityDetail(id: string): EntityDetail | null {
  return ENTITY_DETAILS[id] ?? null;
}
