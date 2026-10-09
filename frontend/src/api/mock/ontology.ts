import type { components } from "@/types/api";

export type OntologyCandidate = components["schemas"]["OntologyCandidate"];

/**
 * 候选对的**真机快照**（`entity_merge_candidates` 的行形状，演示语料）。
 *
 * ⚠️ 只在 `shouldMock()` 为真时命中（D6）：`NEXT_PUBLIC_USE_MOCK=false` 时
 * `/api/v1/ontology/*` 已登记进 `CONTRACT_COVERED_PATTERNS` ⇒ 走真后端。
 */
export const MOCK_MERGE_CANDIDATES: OntologyCandidate[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    left_entity_id: "SUBJECT:91310000MA1FL0Q23K",
    right_entity_id: "RAW:affiliation.csv:91310000MA1FL0Q23K",
    similarity: 0.82,
    status: "human_review",
    signals: { name_sim: 0.82, struct_bonus: 0.0 },
    created_at: "2026-10-09T01:12:00Z",
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    left_entity_id: "SUBJECT:91310000MA1K35Q79X",
    right_entity_id: "RAW:affiliation.csv:91310000MA1K35Q79X",
    similarity: 0.74,
    status: "human_review",
    signals: { name_sim: 0.74, struct_bonus: 0.0, tax_conflict: false },
    created_at: "2026-10-09T01:12:00Z",
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    left_entity_id: "SUBJECT:91440300MA5EPXX12Y",
    right_entity_id: "RAW:affiliation.csv:91440300MA5EPXX12Y",
    similarity: 0.95,
    status: "auto_merged",
    signals: { name_sim: 0.95, struct_bonus: 0.1 },
    created_at: "2026-10-08T09:30:00Z",
  },
  {
    id: "44444444-4444-4444-8444-444444444444",
    left_entity_id: "SUBJECT:91110108MA01YT3X8P",
    right_entity_id: "RAW:affiliation.csv:91110108MA01YT3X8P",
    similarity: 0.91,
    status: "applied",
    signals: { name_sim: 0.91, struct_bonus: 0.05 },
    created_at: "2026-10-08T08:00:00Z",
  },
];

/**
 * Mock 模式下三动作回显的 `kg_version`。
 *
 * **刻意不伪装成真版本号**（真版本号自 P5-I0 起恒 29 字符）：Mock 下没有后端、
 * 没有真图谱，返回一个一眼能看出是 Mock 的值，免得被当成"已产出新版本"的证据。
 */
export const MOCK_ACTION_KG_VERSION = "mock-version（未接后端，图谱未变更）";
