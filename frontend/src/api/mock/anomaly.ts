import type { components } from "@/types/api";

type AnomalyListResponse = components["schemas"]["AnomalyListResponse"];
type AnomalyExplainResponse = components["schemas"]["AnomalyExplainResponse"];

/**
 * 异常归因 Mock（Sprint 9.5 批次 E3）。
 *
 * ⚠️ **这不是编造的数据**：与 `mock/compliance.ts` 同理，它是 2026-09-28 对真机
 * `kg_version=attendance-demo-v1` 调 `GET /attendance/anomalies` 与
 * `/anomalies/explain` 的**真实返回**原样照录（E001 张伟 2026-10-16 缺卡）。
 *
 * 演示用例只有一条，因为它**本来就是语料里唯一埋设的缺卡异常**
 * （`demo/attendance/README.md` §4）——不为了"列表好看"去填更多条。
 */
export const MOCK_ANOMALY_LIST: AnomalyListResponse = {
  kg_version: "attendance-demo-v1",
  items: [
    {
      employee_id: "E001",
      employee_name: "张伟",
      date: "2026-10-16",
      status: "absent",
    },
  ],
  total: 1,
  trace_id: "6ed43964-674f-4d0f-b5a6-d3916e8b5e30",
};

export const MOCK_ANOMALY_EXPLAIN: AnomalyExplainResponse = {
  kg_version: "attendance-demo-v1",
  employee_id: "E001",
  employee_name: "张伟",
  date: "2026-10-16",
  anomaly_type: "absent",
  causes: [
    {
      code: "trip_approved",
      reason: "出差审批覆盖当日（武汉 2026-10-16~2026-10-18）",
      weight: 0.35,
      matched: true,
      evidence: ["BUSINESS_TRIP:BT-2026-0017"],
    },
    {
      code: "order_closed",
      reason: "当日工单已闭环 1 条（最早派单 2026-10-16 09:40）",
      weight: 0.3,
      matched: true,
      evidence: ["WORK_ORDER:SO-2026-0912"],
    },
    {
      code: "location_match",
      reason: "定位与出差目的地一致 2 条（武汉光谷）",
      weight: 0.22,
      matched: true,
      evidence: ["LOCATION_RECORD:L00001", "LOCATION_RECORD:L00002"],
    },
    {
      code: "access_contrast",
      reason: "当日无门禁、前一日有门禁（外勤旁证）",
      weight: 0.13,
      matched: true,
      evidence: ["ACCESS_RECORD:AC000011"],
    },
  ],
  confidence: 1,
  conclusion: "外勤出勤成立",
  action: "系统自动补卡",
  policy_refs: [
    "document:doc:attendance-policy-2026:L31",
    "document:doc:fieldwork-attendance-rules:L27",
  ],
  trace_id: "33538ebb-af69-453e-a2ee-5a1611a3f68d",
};
