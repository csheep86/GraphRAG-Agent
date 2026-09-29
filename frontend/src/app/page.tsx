"use client";

import { useEffect } from "react";
import { CircleCheck, FileText, Network, Share2 } from "lucide-react";

import { DomainCard } from "@/components/dashboard/domain-card";
import { MetricCard } from "@/components/dashboard/metric-card";
import { RecentDocuments } from "@/components/dashboard/recent-documents";
import { RecentQaHistory } from "@/components/dashboard/recent-qa-history";
import {
  PageHeader,
  PageShell,
  SectionTitle,
} from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";
import { domainNav } from "@/lib/nav";
import { useDashboardStore } from "@/store/use-dashboard-store";

/**
 * 业务域卡片的**展示文案**。key 与 `nav.ts::domainNav` 的 `href` 对齐。
 *
 * ⚠️ 这里只放描述文案与图标配色；**交付状态一律取自 `domainNav`**
 * （`disabled` / `badge` 是唯一真源）——在此另写一套状态会与侧栏打架。
 */
const DOMAIN_META: Record<
  string,
  { description: string; iconClassName: string }
> = {
  "/attendance": {
    description: "政策问答 · 异常归因 · 合规预警",
    iconClassName: "bg-kpi-blue/10 text-kpi-blue",
  },
  "/service": {
    description: "故障诊断 · 工单归因 · 配件关联",
    iconClassName: "bg-kpi-teal/10 text-kpi-teal",
  },
  "/rd": {
    description: "专利关联 · BOM 图谱 · 设计复用",
    iconClassName: "bg-kpi-purple/10 text-kpi-purple",
  },
  "/supply": {
    description: "物料关联 · 供应商 · 替代方案",
    iconClassName: "bg-kpi-amber/10 text-kpi-amber",
  },
  "/hr": {
    description: "技能图谱 · 人岗匹配 · 知识传承",
    iconClassName: "bg-kpi-green/10 text-kpi-green",
  },
  "/quality": {
    description: "缺陷归因 · 测试案例 · 改进追踪",
    iconClassName: "bg-severity-high/10 text-severity-high",
  },
  "/patent": {
    description: "专利-产品关联 · 发明人 · 引证",
    iconClassName: "bg-kpi-blue/10 text-kpi-blue",
  },
};

/** 图谱概览取不到时的说明文案：按失败原因区分，不笼统写"未激活" */
function graphUnavailableHint(code: string | null): string {
  if (code === "NOT_IMPLEMENTED") return "图谱存储未就绪（Neo4j 不可用）";
  if (code === "KG_VERSION_NOT_ACTIVE") return "暂无 active 图谱版本";
  return code ? `图谱暂不可用（${code}）` : "—";
}

export default function DashboardPage() {
  const graphOverview = useDashboardStore((state) => state.graphOverview);
  const documentTotal = useDashboardStore((state) => state.documentTotal);
  const graphErrorCode = useDashboardStore((state) => state.graphErrorCode);
  const loading = useDashboardStore((state) => state.loading);
  const error = useDashboardStore((state) => state.error);
  const load = useDashboardStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  const active = graphOverview !== null;

  return (
    <PageShell>
      <PageHeader
        title="企业知识图谱总览"
        description="多业务域知识融合 · 统一本体 · 本地部署"
      />

      {error ? (
        <Card className="mt-4 gap-0 px-[18px] py-3 text-[13px] text-destructive">
          工作台数据加载失败：{error}
        </Card>
      ) : null}

      {/* KPI 行 —— 全部来自契约内 `GET /api/v1/graph/overview`，
          取不到（无 active 版本 → 409）一律显示 `—`，不填示意值。 */}
      <div className="mt-[18px] grid gap-[14px] sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="图谱实体总量"
          value={
            graphOverview ? formatNumber(graphOverview.entity_count) : "—"
          }
          icon={Network}
          accent="blue"
          hint={
            active
              ? "当前 active 版本内的实体总数"
              : graphUnavailableHint(graphErrorCode)
          }
          loading={loading}
        />
        <MetricCard
          label="关系边"
          value={
            graphOverview ? formatNumber(graphOverview.relation_count) : "—"
          }
          icon={Share2}
          accent="teal"
          hint={
            active
              ? "当前 active 版本内的关系总数"
              : graphUnavailableHint(graphErrorCode)
          }
          loading={loading}
        />
        <MetricCard
          label="文档总数"
          value={documentTotal === null ? "—" : formatNumber(documentTotal)}
          icon={FileText}
          accent="green"
          hint="当前租户下的文档总数"
          loading={loading}
        />
        <MetricCard
          label="图谱状态"
          value={loading ? "—" : active ? "已激活" : "不可用"}
          icon={CircleCheck}
          accent={active ? "purple" : undefined}
          // 如实说明是哪一种不可用：NOT_IMPLEMENTED = Neo4j 未就绪，
          // KG_VERSION_NOT_ACTIVE = 无 active 版本。不笼统写"未激活"。
          hint={
            graphOverview
              ? graphOverview.kg_version
              : graphUnavailableHint(graphErrorCode)
          }
          loading={loading}
        />
      </div>

      <SectionTitle hint="点击进入">业务域</SectionTitle>
      <div className="grid gap-[14px] sm:grid-cols-2 xl:grid-cols-4">
        {domainNav.map((item) => {
          const meta = DOMAIN_META[item.href];

          return (
            <DomainCard
              key={item.href}
              title={item.label}
              description={meta?.description ?? "能力规划中"}
              icon={item.icon}
              iconClassName={
                meta?.iconClassName ?? "bg-foreground/[0.06] text-muted-foreground"
              }
              // 状态取自 nav.ts 的 `disabled`，不在此另立一套
              status={item.disabled ? "规划中" : "已上线"}
              statusVariant={item.disabled ? "tag-gray" : "tag-green"}
              // ⚠️ 域内计数一律 `null`：契约无任何域级计数端点，
              // demo 的 127 / 342 / 86 是视觉示意值，照抄即造假。
              count={null}
              href={item.disabled ? undefined : item.href}
            />
          );
        })}

        <DomainCard
          title="图谱总览"
          description="全局实体网络 · 跨域关联"
          icon={Network}
          iconClassName="bg-foreground/[0.06] text-muted-foreground"
          status="管理视图"
          statusVariant="tag-gray"
          count={null}
          href="/graph"
        />
      </div>

      <SectionTitle>运行近况</SectionTitle>
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <RecentDocuments />
        <RecentQaHistory />
      </div>
    </PageShell>
  );
}
