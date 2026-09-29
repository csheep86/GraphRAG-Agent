import type { LucideIcon } from "lucide-react";
import { TrendingDown, TrendingUp } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDelta } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 数值语义色 —— 对齐 demo `.kpi.blue` / `.teal` / `.green` / `.amber` / `.purple` */
export type MetricAccent = "blue" | "teal" | "green" | "amber" | "purple";

const ACCENT_VALUE_CLASS: Record<MetricAccent, string> = {
  blue: "text-kpi-blue",
  teal: "text-kpi-teal",
  green: "text-kpi-green",
  amber: "text-kpi-amber",
  purple: "text-kpi-purple",
};

type MetricCardProps = {
  label: string;
  value: string;
  icon: LucideIcon;
  /** 数值语义色；不给则用默认前景色 */
  accent?: MetricAccent;
  /** 环比数值（%）；给定时展示绿色/红色趋势行 */
  delta?: number;
  /** 趋势行前缀，如「较上周」 */
  deltaLabel?: string;
  /** 无环比时展示的说明文案 */
  hint?: string;
  /** 弱化展示（对齐 p01 第 4 张卡） */
  dimmed?: boolean;
  loading?: boolean;
};

export function MetricCard({
  label,
  value,
  icon: Icon,
  accent,
  delta,
  deltaLabel = "较上周",
  hint,
  dimmed = false,
  loading = false,
}: MetricCardProps) {
  const hasDelta = typeof delta === "number";
  const positive = hasDelta && (delta as number) >= 0;

  return (
    // 对齐 demo `.kpi{padding:16px 18px}`（原 p-5 偏厚）
    <Card className={cn("gap-0 px-[18px] py-4", dimmed && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <span className="truncate text-[11.5px] text-muted-foreground">
          {label}
        </span>
        <Icon className="size-4 shrink-0 text-primary/70" />
      </div>

      {loading ? (
        <Skeleton className="mt-2 h-6 w-24" />
      ) : (
        <p
          className={cn(
            "mt-2 text-[22px] leading-none font-semibold tracking-tight tabular-nums",
            accent ? ACCENT_VALUE_CLASS[accent] : "text-foreground",
          )}
        >
          {value}
        </p>
      )}

      <div className="mt-3.5 min-h-4 text-xs">
        {loading ? (
          <Skeleton className="h-3 w-28" />
        ) : hasDelta ? (
          <span
            className={cn(
              "inline-flex items-center gap-1",
              // 原 `text-emerald-400` 是深底荧光绿，白底上约 2.1:1 不可读；
              // 改 demo `.up{color:#22a06b}`
              positive ? "text-kpi-green" : "text-destructive",
            )}
          >
            {positive ? (
              <TrendingUp className="size-3" />
            ) : (
              <TrendingDown className="size-3" />
            )}
            {`${deltaLabel} ${formatDelta(delta as number)}`}
          </span>
        ) : (
          <span className="text-muted-foreground">{hint}</span>
        )}
      </div>
    </Card>
  );
}
