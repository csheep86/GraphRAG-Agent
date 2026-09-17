import { Construction } from "lucide-react";

import { PageHeader, PageShell } from "@/components/layout/page-shell";

/**
 * 功能预留页。
 *
 * 设计稿（p01）侧栏包含「系统设置 / 权限审计」入口，但未提供页面设计，
 * 且契约中也没有对应端点。按项目规则「功能预留原则」：只预留空位，
 * 不强行同步开发，因此这里只渲染占位说明。
 */
export function PlaceholderPage({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader title={title} description={description} />

        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-6 py-24 text-center">
          <Construction className="size-6 text-muted-foreground/60" />
          <p className="text-[13px] text-foreground">功能预留</p>
          <p className="max-w-md text-xs leading-relaxed text-muted-foreground">
            该页面尚未进入设计稿与接口范围，前端仅保留导航入口，不做实现。
          </p>
        </div>
      </div>
    </PageShell>
  );
}
