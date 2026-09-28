"use client";

import { useEffect } from "react";

import { AnomalyCaseList } from "@/components/attribution/anomaly-case-list";
import { AttributionPanel } from "@/components/attribution/attribution-panel";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { useAttributionStore } from "@/store/use-attribution-store";

/**
 * 考勤域 · 异常归因子页（Sprint 9.5 批次 E3 / 后端批次 C4）。
 *
 * ✅ 契约已实装：`GET /api/v1/attendance/anomalies` + `/anomalies/explain`。
 *
 * 演示的是「HR 原来跨 5 个系统查 18 分钟」这件事：左列表选一条缺卡，
 * 右侧一次给出跨 **HR / 门禁 / 工单 / 定位** 四个系统的取证结果与置信度。
 *
 * **明确未做**：归因复核（确认 / 驳回）——契约没有对应端点，不做假交互。
 */
export default function AttendanceAttributionPage() {
  const load = useAttributionStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="异常归因"
          description="一条缺卡异常，系统跨 HR / 门禁 / 工单 / 定位四个系统取证：每条原因带权重与证据节点，置信度由确定性加权算出（不出 LLM）。数据为演示语料（仿真）。"
        />

        <div className="flex flex-col gap-4 lg:flex-row">
          <AnomalyCaseList />
          <AttributionPanel />
        </div>
      </div>
    </PageShell>
  );
}
