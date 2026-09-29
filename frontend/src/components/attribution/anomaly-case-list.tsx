"use client";

import { SearchX, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { anomalyStatusLabel } from "@/lib/attribution";
import { useAttributionStore } from "@/store/use-attribution-store";

/** 异常用例列表：先说清楚「要给谁归因」 */
export function AnomalyCaseList() {
  const cases = useAttributionStore((state) => state.cases);
  const loading = useAttributionStore((state) => state.loading);
  const initialized = useAttributionStore((state) => state.initialized);
  const error = useAttributionStore((state) => state.error);
  const selected = useAttributionStore((state) => state.selected);
  const select = useAttributionStore((state) => state.select);

  const showSkeleton = loading || !initialized;

  return (
    <Card className="w-[260px] shrink-0 self-start">
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-medium text-foreground">待归因异常</span>
        <span className="text-[11px] text-muted-foreground">
          {showSkeleton ? "…" : `${cases.length} 条`}
        </span>
      </div>

      {error ? (
        <div className="mx-4 mb-4 rounded-lg border border-severity-high/40 bg-severity-high/[0.07] p-2.5">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-severity-high">
            <TriangleAlert className="size-3.5" />
            加载失败
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-foreground/85">
            {error}
          </p>
        </div>
      ) : null}

      <div className="flex flex-col gap-1 px-2 pb-3">
        {showSkeleton
          ? Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="px-2 py-2">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="mt-1.5 h-3 w-16" />
              </div>
            ))
          : cases.map((item) => {
              const active =
                selected?.employee_id === item.employee_id &&
                selected?.date === item.date;

              return (
                <button
                  key={`${item.employee_id}-${item.date}`}
                  type="button"
                  onClick={() => void select(item)}
                  className={`flex flex-col items-start gap-1 rounded-lg px-2 py-2 text-left transition-colors ${
                    active ? "bg-accent" : "hover:bg-foreground/[0.04]"
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="text-[13px] text-foreground">
                      {item.employee_name}
                    </span>
                    <Badge variant="outline">
                      {anomalyStatusLabel(item.status)}
                    </Badge>
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {item.employee_id} · {item.date}
                  </span>
                </button>
              );
            })}

        {!showSkeleton && !error && cases.length === 0 ? (
          <div className="flex flex-col items-center gap-1.5 px-3 py-8 text-center">
            <SearchX className="size-5 text-muted-foreground/60" />
            <p className="text-[12px] text-foreground">没有待归因的异常</p>
            <p className="text-[11px] text-muted-foreground">
              当前图谱里没有缺卡 / 缺勤记录。
            </p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
