import type {
  ComplianceLevel,
  ComplianceRule,
} from "@/lib/compliance";
import type { components } from "@/types/api";

import { delay, request, shouldMock } from "./client";
import { MOCK_COMPLIANCE_SCAN } from "./mock/compliance";

type ComplianceScanResponse = components["schemas"]["ComplianceScanResponse"];

/**
 * 合规扫描查询参数。**只传后端契约有的 4 个**，不引入前端自造的过滤维度。
 *
 * - `as_of` 观察日：影响「调休未消化」的临期判据（季度剩余 < 30 天判 high）；
 *   缺省取数据窗口末日（**不取系统当天**，保证可复现）。
 * - `rule` / `level` / `employee_id`：只影响 `findings`，`rule_values[]` 始终全量
 *   （判据不因过滤而消失）。
 */
export type ComplianceScanParams = {
  as_of?: string;
  rule?: ComplianceRule;
  level?: ComplianceLevel;
  employee_id?: string;
};

const SCAN_PATH = "/api/v1/attendance/compliance/scan";

/**
 * 考勤域合规扫描（Sprint 9.5 批次 C3 → E4）。
 *
 * ✅ 契约已实装：`GET /api/v1/attendance/compliance/scan`
 *
 * **同步返回**（契约注释写明）：扫描是纯读、不落库、不调 LLM，40 员工秒级完成，
 * 所以这里**没有** `task_id` 轮询——引入轮询只会多一轮往返且无状态可存。
 *
 * Mock 分支返回的是**真机快照**（见 `mock/compliance.ts`），并按后端同样的
 * 语义做过滤：只过滤 `findings`、保留全量 `rule_values`。
 */
export async function scanCompliance(
  params: ComplianceScanParams = {},
): Promise<ComplianceScanResponse> {
  if (shouldMock(SCAN_PATH)) {
    await delay(320);
    const findings = MOCK_COMPLIANCE_SCAN.findings.filter((finding) => {
      if (params.rule && finding.rule !== params.rule) return false;
      if (params.level && finding.level !== params.level) return false;
      if (params.employee_id && finding.employee_id !== params.employee_id) {
        return false;
      }
      return true;
    });
    return {
      ...MOCK_COMPLIANCE_SCAN,
      // 观察日在 Mock 侧只回显：快照本身是 2026-10-31 那一次扫描的结果
      as_of: params.as_of || MOCK_COMPLIANCE_SCAN.as_of,
      findings,
      total: findings.length,
    };
  }

  const query = new URLSearchParams();
  if (params.as_of) query.set("as_of", params.as_of);
  if (params.rule) query.set("rule", params.rule);
  if (params.level) query.set("level", params.level);
  if (params.employee_id) query.set("employee_id", params.employee_id);

  const qs = query.toString();
  return request<ComplianceScanResponse>(`${SCAN_PATH}${qs ? `?${qs}` : ""}`);
}
