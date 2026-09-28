"use client";

import { useEffect } from "react";

import { RiskTable } from "@/components/compliance/risk-table";
import { RuleValuePanel } from "@/components/compliance/rule-value-panel";
import { ScanToolbar } from "@/components/compliance/scan-toolbar";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { useComplianceStore } from "@/store/use-compliance-store";

/**
 * 考勤域 · 合规预警子页（Sprint 9.5 批次 E4）。
 *
 * ✅ 契约已实装：`GET /api/v1/attendance/compliance/scan`（批次 C3）。
 * 筛选参数变化就重新扫描一次——后端是同步纯读接口，秒级返回，
 * 不需要前端缓存，也不该在前端做内存过滤（那等于把后端能力闲置）。
 *
 * **明确未做**：风险处置（确认 / 驳回 / 派单）——契约没有对应端点，
 * 本页因此**不提供**处置按钮；做了就是假交互。
 */
export default function AttendanceCompliancePage() {
  const load = useComplianceStore((state) => state.load);
  const asOf = useComplianceStore((state) => state.asOf);
  const ruleFilter = useComplianceStore((state) => state.ruleFilter);
  const levelFilter = useComplianceStore((state) => state.levelFilter);

  useEffect(() => {
    void load();
  }, [load, asOf, ruleFilter, levelFilter]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="合规预警"
          description="对全量员工跑五条确定性规则（周工时 / 月加班 / 调休 / 弹性时段 / 连续出勤）：每条风险都带计算过程与制度依据，可逐条核算。数据为演示语料（仿真）。"
        />

        <ScanToolbar />
        <RuleValuePanel />
        <RiskTable />
      </div>
    </PageShell>
  );
}
