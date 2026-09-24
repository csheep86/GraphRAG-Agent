import type {
  AffiliationSuspicionItem,
  AffiliationTaskResponse,
} from "@/types/mock";

/**
 * 疑点 Mock 数据（Sprint 7.3 批次 C，决策 C4）。
 *
 * ⚠️ **刻意做得可识别为假**：主体名一律用「示例甲 / 示例乙 / 示例丙」这类虚构名，
 * 与真机演示数据（招商局系）**不同名**。理由：验收 §6.3「关 Mock 硬门槛」要求
 * 疑点页在 `USE_MOCK=false` 下零假数据——若 Mock 与真机长得一样，"屏幕上这几条
 * 到底是真的还是假的"就说不清了。用不同名是为了让这条**一眼可验**。
 *
 * 形状严格对齐契约 `AffiliationSuspicionItem` / `AffiliationTaskResponse`：
 * 不增删字段、不伪造契约没有的字段（`reviewed_by` 未复核时按契约给 `null`）。
 */

const MOCK_TASK_ID = "00000000-0000-4000-8000-0000000a7010";
const MOCK_TRACE_ID = "00000000-0000-4000-8000-0000000a7aa0";
const MOCK_KG_VERSION = "v-mock-00000000";
const MOCK_DOC_ID = "00000000-0000-4000-8000-00000000d001";

export const MOCK_SUSPICIONS: AffiliationSuspicionItem[] = [
  {
    id: "00000000-0000-4000-8000-0000000b1001",
    task_id: MOCK_TASK_ID,
    kg_version: MOCK_KG_VERSION,
    suspicion_type: "shared_legal_rep",
    severity: "high",
    status: "open",
    entities: ["v-mock:sub:0001", "v-mock:sub:0002", "v-mock:lp:0001"],
    entity_names: ["示例甲控股有限公司", "示例乙贸易有限公司", "示例·张三"],
    evidence: [
      {
        node_id: "v-mock:lp:0001",
        chunk_id: "chunk-mock00000001",
        doc_id: MOCK_DOC_ID,
        page: 12,
        char_start: 0,
        char_end: 48,
        text: "示例甲控股有限公司的法定代表人为张三，成立日期为 2015 年。",
      },
      {
        node_id: "v-mock:lp:0001",
        chunk_id: "chunk-mock00000002",
        doc_id: MOCK_DOC_ID,
        page: 47,
        char_start: 0,
        char_end: 46,
        text: "示例乙贸易有限公司的法定代表人为张三，注册资本 5000 万元。",
      },
    ],
    reviewed_at: null,
    reviewed_by: null,
    created_at: "2026-09-24T10:16:12Z",
    trace_id: MOCK_TRACE_ID,
  },
  {
    id: "00000000-0000-4000-8000-0000000b1002",
    task_id: MOCK_TASK_ID,
    kg_version: MOCK_KG_VERSION,
    suspicion_type: "shared_address",
    severity: "medium",
    status: "open",
    entities: ["v-mock:sub:0001", "v-mock:sub:0003", "v-mock:addr:0001"],
    entity_names: [
      "示例甲控股有限公司",
      "示例丙供应链有限公司",
      "示例市示例区示例路 1 号",
    ],
    evidence: [
      {
        node_id: "v-mock:addr:0001",
        chunk_id: "chunk-mock00000003",
        doc_id: MOCK_DOC_ID,
        page: 3,
        char_start: 0,
        char_end: 40,
        text: "示例甲控股有限公司注册地址为示例市示例区示例路 1 号。",
      },
    ],
    reviewed_at: null,
    reviewed_by: null,
    created_at: "2026-09-24T10:16:12Z",
    trace_id: MOCK_TRACE_ID,
  },
  {
    id: "00000000-0000-4000-8000-0000000b1003",
    task_id: MOCK_TASK_ID,
    kg_version: MOCK_KG_VERSION,
    suspicion_type: "shared_address",
    severity: "low",
    // 已复核样本：让复核后的样式在开发态也能看到（真机由 PATCH 落库）
    status: "confirmed",
    entities: ["v-mock:sub:0002", "v-mock:sub:0003", "v-mock:addr:0002"],
    entity_names: [
      "示例乙贸易有限公司",
      "示例丙供应链有限公司",
      "示例市示例区示例路 2 号",
    ],
    evidence: [
      {
        node_id: "v-mock:addr:0002",
        chunk_id: "chunk-mock00000004",
        doc_id: MOCK_DOC_ID,
        page: 8,
        char_start: 0,
        char_end: 38,
        text: "示例丙供应链有限公司办公地址为示例市示例区示例路 2 号。",
      },
    ],
    reviewed_at: "2026-09-24T11:02:45Z",
    reviewed_by: "00000000-0000-4000-8000-000000000001",
    created_at: "2026-09-24T10:16:12Z",
    trace_id: MOCK_TRACE_ID,
  },
];

export const MOCK_SUSPICION_LIST = {
  items: MOCK_SUSPICIONS,
  total: MOCK_SUSPICIONS.length,
  task_id: MOCK_TASK_ID,
  trace_id: MOCK_TRACE_ID,
};

export const MOCK_AFFILIATION_TASK: AffiliationTaskResponse = {
  task_id: MOCK_TASK_ID,
  status: "completed",
  doc_ids: [MOCK_DOC_ID],
  result_summary: {
    total: MOCK_SUSPICIONS.length,
    by_type: { shared_legal_rep: 1, shared_address: 2 },
    top_5_severity: ["high", "medium", "low"],
  },
  error_code: null,
  created_at: "2026-09-24T10:15:30Z",
  updated_at: "2026-09-24T10:16:12Z",
  completed_at: "2026-09-24T10:16:12Z",
  trace_id: MOCK_TRACE_ID,
};
