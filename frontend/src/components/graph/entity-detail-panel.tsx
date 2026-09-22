"use client";

import { ArrowUpRight, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useGraphStore } from "@/store/use-graph-store";

import { CATEGORY_COLOR_VAR } from "./graph-legend";

export function EntityDetailPanel() {
  const detail = useGraphStore((state) => state.detail);
  const detailLoading = useGraphStore((state) => state.detailLoading);
  const detailError = useGraphStore((state) => state.detailError);
  const closeDetail = useGraphStore((state) => state.closeDetail);
  const select = useGraphStore((state) => state.select);

  return (
    <Card className="flex h-full min-h-0 flex-col gap-0 overflow-hidden">
      <CardHeader className="px-4 pt-4 pb-3">
        <CardTitle>实体详情</CardTitle>
        <CardAction>
          <button
            type="button"
            onClick={closeDetail}
            aria-label="关闭详情"
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </CardAction>
      </CardHeader>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-4 pb-4">
        {detailLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        ) : detailError ? (
          <div className="rounded-lg border border-border bg-white/[0.02] p-4 text-xs text-muted-foreground">
            {detailError === "ENTITY_NOT_FOUND"
              ? "该实体不存在或不属于当前 active 版本。"
              : detailError === "FORBIDDEN"
                ? "跨租户访问被拒（403）。"
                : detailError === "NOT_IMPLEMENTED"
                  ? "图谱存储暂不可用（501）。"
                  : "实体详情加载失败。"}
          </div>
        ) : !detail ? null : (
          <>
            <div className="rounded-xl border border-primary/30 bg-primary/[0.10] p-3.5">
              <div className="flex items-start gap-3">
                <span
                  className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: CATEGORY_COLOR_VAR[detail.category] }}
                >
                  <span className="size-3 rounded-full bg-white/85" />
                </span>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-base leading-snug font-semibold text-foreground">
                    {detail.canonical_name}
                  </p>

                  <Badge className="mt-2 bg-primary text-primary-foreground">
                    {detail.entity_type}
                  </Badge>

                  <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                    {detail.id} · 关联 {detail.relation_count} 个节点
                  </p>
                </div>
              </div>
            </div>

            <p className="mt-4 text-[11px] text-muted-foreground">属性</p>
            <div className="mt-2.5 space-y-2.5">
              {detail.attributes.map((attribute) => (
                <div
                  key={attribute.label}
                  className="flex items-center justify-between gap-3 text-xs"
                >
                  <span className="shrink-0 text-muted-foreground">
                    {attribute.label}
                  </span>
                  <span className="truncate text-foreground">
                    {attribute.value}
                  </span>
                </div>
              ))}
            </div>

            <Separator className="my-4" />

            <p className="text-[11px] text-muted-foreground">
              关联关系 · {detail.relation_count}
            </p>
            <div className="mt-2.5 space-y-2">
              {detail.relations.map((relation) => (
                <button
                  key={`${relation.relation}-${relation.target_id}`}
                  type="button"
                  onClick={() => select(relation.target_id)}
                  className="flex w-full items-center gap-2 rounded-lg border border-border bg-white/[0.02] px-3 py-2.5 text-left transition-colors hover:bg-white/[0.05]"
                >
                  <span className="shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {relation.relation}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                    {relation.target_name}
                  </span>
                  <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
