"use client";

import { useEffect } from "react";
import { FileText, Gauge, MessageSquare, Network } from "lucide-react";

import { MetricCard } from "@/components/dashboard/metric-card";
import { RecentDocuments } from "@/components/dashboard/recent-documents";
import { RecentQaHistory } from "@/components/dashboard/recent-qa-history";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { formatNumber, formatPercent } from "@/lib/format";
import { useDashboardStore } from "@/store/use-dashboard-store";

export default function DashboardPage() {
  const metrics = useDashboardStore((state) => state.metrics);
  const loading = useDashboardStore((state) => state.loading);
  const load = useDashboardStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="知识库运行概览"
          description="追踪解析、抽取与问答质量，掌握团队知识资产的实时状态。"
        />

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="已处理文档数"
            value={metrics ? formatNumber(metrics.processed_documents) : "--"}
            icon={FileText}
            delta={metrics?.processed_documents_delta_pct}
            deltaLabel="较上周"
            loading={loading}
          />

          <MetricCard
            label="KG 实体总数"
            value={metrics ? formatNumber(metrics.kg_entities) : "--"}
            icon={Network}
            hint={
              metrics
                ? `已建立 ${formatNumber(metrics.kg_relations)} 条关系`
                : undefined
            }
            loading={loading}
          />

          <MetricCard
            label="今日回答次数"
            value={metrics ? formatNumber(metrics.today_answers) : "--"}
            icon={MessageSquare}
            hint={metrics ? `活跃用户 ${metrics.active_users} 人` : undefined}
            loading={loading}
          />

          <MetricCard
            label="回答成功率"
            value={metrics ? formatPercent(metrics.answer_success_rate) : "--"}
            icon={Gauge}
            delta={metrics?.answer_success_rate_delta_pct}
            deltaLabel="较昨日"
            dimmed
            loading={loading}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <RecentDocuments />
          <RecentQaHistory />
        </div>
      </div>
    </PageShell>
  );
}
