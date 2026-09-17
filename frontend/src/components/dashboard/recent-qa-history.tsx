"use client";

import Link from "next/link";
import { MoreHorizontal, Download, Trash2 } from "lucide-react";

import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardStore } from "@/store/use-dashboard-store";

export function RecentQaHistory() {
  const history = useDashboardStore((state) => state.recentQaHistory);
  const loading = useDashboardStore((state) => state.loading);

  return (
    <Card className="gap-0">
      <CardHeader className="px-5 pt-4 pb-3">
        <CardTitle>最近问答历史</CardTitle>
        <CardAction>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="更多操作"
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
              >
                <MoreHorizontal className="size-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem>
                <Download />
                导出记录
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Trash2 />
                清空历史
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>

      <div className="flex flex-col">
        {loading
          ? Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="space-y-1.5 border-t border-border px-5 py-3.5 first:border-t-0"
              >
                <Skeleton className="h-3.5 w-full" />
                <Skeleton className="h-3 w-20" />
              </div>
            ))
          : history.map((item) => (
              <Link
                key={item.id}
                href="/qa"
                className="block border-t border-border px-5 py-3.5 transition-colors first:border-t-0 hover:bg-white/[0.025]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] text-foreground">
                      {item.question}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {item.asked_at_label}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {item.citation_count} 个引用
                  </span>
                </div>
              </Link>
            ))}
      </div>
    </Card>
  );
}
