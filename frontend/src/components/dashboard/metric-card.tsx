import type { LucideIcon } from "lucide-react";
import { TrendingDown, TrendingUp } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDelta } from "@/lib/format";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  value: string;
  icon: LucideIcon;
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
  delta,
  deltaLabel = "较上周",
  hint,
  dimmed = false,
  loading = false,
}: MetricCardProps) {
  const hasDelta = typeof delta === "number";
  const positive = hasDelta && (delta as number) >= 0;

  return (
    <Card className={cn("gap-0 p-5", dimmed && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <span className="truncate text-xs text-muted-foreground">{label}</span>
        <Icon className="size-4 shrink-0 text-primary/70" />
      </div>

      {loading ? (
        <Skeleton className="mt-3.5 h-7 w-24" />
      ) : (
        <p className="mt-3.5 text-[28px] leading-none font-semibold tracking-tight text-foreground tabular-nums">
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
              positive ? "text-emerald-400" : "text-destructive",
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
