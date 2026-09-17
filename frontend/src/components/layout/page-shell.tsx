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
        "min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-6 py-6",
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
    <div className={cn("flex min-h-0 flex-1 flex-col p-6", className)}>
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
      <div className="space-y-1.5">
        <h1 className="text-[22px] leading-tight font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        {description ? (
          <p className="text-[13px] text-muted-foreground">{description}</p>
        ) : null}
      </div>

      {action ? (
        <div className="flex shrink-0 items-center gap-2">{action}</div>
      ) : null}
    </div>
  );
}
