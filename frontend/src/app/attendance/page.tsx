"use client";

import Link from "next/link";
import { ArrowRight, CalendarClock, MessageSquare, ShieldAlert } from "lucide-react";

import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";

/**
 * 考勤域首页（Sprint 9.5 批次 E1）。
 *
 * 三个子页**全部**已接后端端点（批次 C3 / C4 / D1），无占位空位：
 *
 * - 合规预警：`GET /attendance/compliance/scan`（批次 C3）；
 * - 异常归因：`GET /attendance/anomalies` + `/anomalies/explain`（批次 C4）；
 * - 政策问答：`POST /agent/query`，响应带 `reasoning_path`（批次 D1）。
 */
const SUB_PAGES: {
  title: string;
  description: string;
  href: string | null;
  icon: typeof CalendarClock;
  badge?: string;
}[] = [
  {
    title: "合规预警",
    description:
      "全量扫描工时 / 加班 / 调休风险，每条带计算过程与制度依据，发薪前可核查。",
    href: "/attendance/compliance",
    icon: CalendarClock,
  },
  {
    title: "异常归因",
    description:
      "缺卡异常跨 HR / 门禁 / 工单 / 定位四系统取证并给出置信度，含原因排序。",
    href: "/attendance/attribution",
    icon: ShieldAlert,
  },
  {
    title: "政策问答",
    description:
      "答案来自图谱检索 + 制度原文：可视化多跳推理路径，每跳带实体 / 关系 / 来源。",
    href: "/attendance/qa",
    icon: MessageSquare,
  },
];

export default function AttendanceDomainPage() {
  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="考勤域"
          description="跨 HR / 门禁 / 工单 / 定位四个系统取证的知识图谱应用。当前数据为演示语料（仿真），非真实客户数据。"
        />

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SUB_PAGES.map((page) => {
            const Icon = page.icon;

            const body = (
              <>
                <div className="flex items-center gap-2">
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="text-[13px] font-medium text-foreground">
                    {page.title}
                  </span>
                  {page.badge ? (
                    <span className="ml-auto rounded border border-border px-1.5 py-px text-[10px] text-muted-foreground/70">
                      {page.badge}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
                  {page.description}
                </p>
              </>
            );

            return page.href ? (
              <Link key={page.title} href={page.href}>
                <Card className="h-full px-4 py-4 transition-colors hover:border-primary/40">
                  {body}
                  <p className="mt-3 flex items-center gap-1 text-[11px] text-primary">
                    进入
                    <ArrowRight className="size-3" />
                  </p>
                </Card>
              </Link>
            ) : (
              <Card
                key={page.title}
                className="h-full px-4 py-4 opacity-70"
                title="该子页依赖的后端端点尚未进契约，本 Sprint 未接"
              >
                {body}
                <p className="mt-3 text-[11px] text-muted-foreground/70">
                  未接后端，不提供入口
                </p>
              </Card>
            );
          })}
        </div>
      </div>
    </PageShell>
  );
}
