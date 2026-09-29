import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 对齐 demo `.tag.green` / `.amber` / `.gray` / `.blue` */
export type DomainTagVariant =
  | "tag-green"
  | "tag-amber"
  | "tag-gray"
  | "tag-blue";

type DomainCardProps = {
  title: string;
  /** 域内能力清单，如「政策问答 · 异常归因 · 合规预警」 */
  description: string;
  icon: LucideIcon;
  /** 图标块配色（由 `--kpi-*` / `--severity-*` 派生，不新增硬编码） */
  iconClassName: string;
  /** 状态标签文案，如「已上线」/「规划中」 */
  status: string;
  statusVariant: DomainTagVariant;
  /**
   * 域内计数。**无真实接口来源时传 `null` → 显示 `—`**。
   * demo 里的 127 / 342 / 86 等全是视觉示意值，照抄即违反红线（A16）。
   */
  count: number | null;
  /** 已上线的域才有 href；规划中的域不给，渲染为不可点卡片 */
  href?: string;
};

/**
 * 业务域卡片 —— 对齐 demo `.domain-card`。
 *
 * 不可点的域（`href` 缺省）**不给 hover 上浮**，避免暗示"可进入"；
 * 这与 `nav.ts` 里 `disabled` 的语义一致（给死链等于宣称已交付）。
 */
export function DomainCard({
  title,
  description,
  icon: Icon,
  iconClassName,
  status,
  statusVariant,
  count,
  href,
}: DomainCardProps) {
  const clickable = Boolean(href);

  return (
    <div
      className={cn(
        "relative flex flex-col overflow-hidden rounded-xl border border-border bg-card p-[18px] shadow-card transition-all duration-[180ms]",
        clickable &&
          "cursor-pointer hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-card-hover",
      )}
    >
      <div
        className={cn(
          "mb-3 flex size-[38px] shrink-0 items-center justify-center rounded-[10px]",
          iconClassName,
        )}
      >
        <Icon className="size-[18px]" />
      </div>

      <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
      <p className="mt-1.5 text-[11.5px] leading-[1.6] text-muted-foreground">
        {description}
      </p>

      <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
        <Badge
          variant={statusVariant}
          className="rounded-[10px] px-2 py-[2px] text-[10px] font-medium"
        >
          {status}
        </Badge>
        <span
          className={cn(
            "text-[16px] font-bold",
            count === null ? "text-muted-foreground/60" : "text-primary",
          )}
        >
          {count === null ? "—" : formatNumber(count)}
        </span>
      </div>

      {/* 覆盖式链接：整卡可点，但不破坏卡片自身的语义结构 */}
      {href ? (
        <Link
          href={href}
          aria-label={`进入${title}域`}
          className="absolute inset-0 rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        />
      ) : null}
    </div>
  );
}
