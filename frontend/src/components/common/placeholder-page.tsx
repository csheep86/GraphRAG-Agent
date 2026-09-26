import type { ReactNode } from "react";

import { Construction } from "lucide-react";

import { PageHeader, PageShell } from "@/components/layout/page-shell";

/**
 * 功能预留页。
 *
 * 设计稿（p01）侧栏包含「系统设置 / 权限审计」入口，但未提供页面设计，
 * 且契约中也没有对应端点。按项目规则「功能预留原则」：只预留空位，
 * 不强行同步开发，因此这里只渲染占位说明。
 *
 * `badge` / `notice` 两个插槽服务于决策 **A16（Sprint 8 批次 D）**：settings 页
 * 的处置是「加演示环境标注」而不是「隐藏路由」——隐藏会让 plan §7.2 的
 * 「零假数据」硬门槛失去可核性（分不清是没有页面还是没有数据）。
 */
export function PlaceholderPage({
  title,
  description,
  badge,
  notice,
}: {
  title: string;
  description: string;
  /** 标题右侧标签位（如「演示环境」） */
  badge?: ReactNode;
  /** 标题下方、占位卡片上方的说明卡：如实声明本页与环境口径 */
  notice?: ReactNode;
}) {
  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader title={title} description={description} action={badge} />

        {notice}

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
