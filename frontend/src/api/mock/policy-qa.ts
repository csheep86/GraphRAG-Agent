import type { components } from "@/types/api";

type AgentQueryResponse = components["schemas"]["AgentQueryResponse"];

/**
 * 政策问答 Mock（Sprint 9.5 批次 E2）。
 *
 * **这份 Mock 的真假成分必须说清楚**——它不像 `mock/compliance.ts` 那样是
 * 「整份真机返回」，因为本机 **没有配置 LLM_API_KEY**（`.env.development` 内为空），
 * `/agent/query` 走到 LLM 侧必然 501，拿不到完整真机响应。所以：
 *
 * - ✅ **`reasoning_path` 是真机实跑**：2026-09-28 对 `kg_version=attendance-demo-v1`
 *   调用 `build_reasoning_path()` 的真实返回（问句「李静的月加班超过上限了吗？」⇒
 *   EMPLOYEE:E002 → ATTENDANCE_RECORD:A00023 → SHIFT:S00023）。推理路径本来就
 *   **不出 LLM**（确定性构造），因此可以脱离 LLM 单独取真值；
 * - ⚠️ **`answer` / `confidence` / `citations` 是占位**：没有 LLM 就没有真答案。
 *   占位文案自带「非真机产出」标记，页面另有提示条，不允许被读成结论。
 */
export const MOCK_POLICY_QA: AgentQueryResponse = {
  answer:
    "【占位示例 · 非真机产出】本机未配置 LLM 凭据，Mock 模式下不会合成回答文本。" +
    "右侧推理路径与节点 id 才是本页要演示的对象：它们由图谱确定性算出，可直接回查。",
  citations: [],
  route: "m3_graphqa",
  confidence: "low",
  refused: false,
  kg_version: "attendance-demo-v1",
  trace_id: "00000000-0000-4000-8000-000000000001",
  kg_nodes: [],
  kg_relations: [],
  token_usage: null,
  reasoning_path: [
    {
      source: {
        id: "EMPLOYEE:E002",
        name: "李静",
        entity_type: "EMPLOYEE",
      },
      relation: "HAS_ATTENDANCE",
      target: {
        id: "ATTENDANCE_RECORD:A00023",
        name: "2026-10-01 normal",
        entity_type: "ATTENDANCE_RECORD",
      },
      origin: "cypher",
      evidence: null,
    },
    {
      source: {
        id: "ATTENDANCE_RECORD:A00023",
        name: "2026-10-01 normal",
        entity_type: "ATTENDANCE_RECORD",
      },
      relation: "OCCURRED_ON",
      target: {
        id: "SHIFT:S00023",
        name: "2026-10-01 正常班",
        entity_type: "SHIFT",
      },
      origin: "cypher",
      evidence: null,
    },
  ],
};
