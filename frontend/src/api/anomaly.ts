import { delay, request, shouldMock } from "./client";
import {
  MOCK_ANOMALY_EXPLAIN,
  MOCK_ANOMALY_LIST,
} from "./mock/anomaly";
import type { components } from "@/types/api";

type AnomalyListResponse = components["schemas"]["AnomalyListResponse"];
type AnomalyExplainResponse = components["schemas"]["AnomalyExplainResponse"];

const LIST_PATH = "/api/v1/attendance/anomalies";
const EXPLAIN_PATH = "/api/v1/attendance/anomalies/explain";

/**
 * 待归因的考勤异常清单（Sprint 9.5 批次 C4 → E3）。
 *
 * ✅ 契约已实装：`GET /api/v1/attendance/anomalies`
 *
 * **空列表是正常结果**（这份图里没人缺卡），不是失败——与合规扫描不同，
 * 那边「扫不到事实」是 409，这边「没有异常」正是想听到的答案。
 */
export async function listAnomalies(
  employeeId?: string,
): Promise<AnomalyListResponse> {
  if (shouldMock(LIST_PATH)) {
    await delay(260);
    if (!employeeId) return MOCK_ANOMALY_LIST;
    const items = MOCK_ANOMALY_LIST.items.filter(
      (item) => item.employee_id === employeeId,
    );
    return { ...MOCK_ANOMALY_LIST, items, total: items.length };
  }

  const qs = employeeId
    ? `?employee_id=${encodeURIComponent(employeeId)}`
    : "";
  return request<AnomalyListResponse>(`${LIST_PATH}${qs}`);
}

/**
 * 一条异常的归因结论。
 *
 * ✅ 契约已实装：`GET /api/v1/attendance/anomalies/explain`
 *
 * `date` 缺省时后端取该员工的**第一个**异常日；员工不在图上 / 该日无异常
 * ⇒ **404**（不是零证据的 200——零证据会被读成"系统判断他不成立"）。
 */
export async function explainAnomaly(params: {
  employee_id: string;
  date?: string;
}): Promise<AnomalyExplainResponse> {
  if (shouldMock(EXPLAIN_PATH)) {
    await delay(320);
    return {
      ...MOCK_ANOMALY_EXPLAIN,
      employee_id: params.employee_id,
      date: params.date ?? MOCK_ANOMALY_EXPLAIN.date,
    };
  }

  const query = new URLSearchParams({ employee_id: params.employee_id });
  if (params.date) query.set("date", params.date);
  return request<AnomalyExplainResponse>(`${EXPLAIN_PATH}?${query.toString()}`);
}
