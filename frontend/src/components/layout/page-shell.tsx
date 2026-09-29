import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 常规页面滚动容器（工作台 / 文档管理） */
export function PageShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        // 对齐 demo `.content{padding:22px 24px 32px}`
        "min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-6 pt-[22px] pb-8",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 满高页面容器（知识问答 / 知识图谱，内部各自滚动） */
export function FullHeightShell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col px-6 pt-[22px] pb-8",
        className,
      )}
    >
      {children}
    </div>
  );
}

type PageHeaderProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
};

/** 页面标题块：H1 + 副标题 + 右侧主操作 */
export function PageHeader({
  title,
  description,
  action,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4", className)}>
      {/* 对齐 demo `.page-head`：`h2{18px/600}` + `.sub{12px}` */}
      <div className="space-y-1">
        <h1 className="text-[18px] leading-tight font-semibold text-foreground">
          {title}
        </h1>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>

      {action ? (
        <div className="flex shrink-0 items-center gap-2">{action}</div>
      ) : null}
    </div>
  );
}

type SectionTitleProps = {
  children: ReactNode;
  /** 标题右侧的弱化说明，如 demo 的「点击进入」 */
  hint?: ReactNode;
  className?: string;
};

/**
 * 区块标题 —— 对齐 demo `.section-ttl`：标题 + 右侧延伸分隔线 + 可选弱化说明。
 *
 * demo 里它是「业务域 / 平台运行指标」这类分组的头；前端此前没有对应组件，
 * 各页用裸 `<h2>` 顶替，分组感丢失。
 */
export function SectionTitle({
  children,
  hint,
  className,
}: SectionTitleProps) {
  return (
    <div
      className={cn(
        "mt-[22px] mb-3 flex items-center gap-2 text-[13px] font-semibold text-foreground",
        className,
      )}
    >
      <span>{children}</span>
      <span className="h-px flex-1 bg-border" />
      {hint ? (
        <span className="text-[11px] font-normal text-muted-foreground">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
