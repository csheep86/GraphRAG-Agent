"use client";

import Link from "next/link";
import { FileText } from "lucide-react";

import { DocumentStatusBadge } from "@/components/common/document-status-badge";
import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardStore } from "@/store/use-dashboard-store";

export function RecentDocuments() {
  const documents = useDashboardStore((state) => state.recentDocuments);
  const loading = useDashboardStore((state) => state.loading);

  return (
    <Card className="gap-0">
      <CardHeader className="px-5 pt-4 pb-3">
        <CardTitle>最近文档处理</CardTitle>
        <CardAction>
          <Link
            href="/documents"
            className="rounded text-xs text-primary transition-opacity hover:opacity-80"
          >
            查看全部 →
          </Link>
        </CardAction>
      </CardHeader>

      <div className="flex flex-col">
        {loading
          ? Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="flex items-center gap-3 border-t border-border px-5 py-3.5 first:border-t-0"
              >
                <Skeleton className="size-4 rounded" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-40" />
                  <Skeleton className="h-3 w-16" />
                </div>
                <Skeleton className="h-5 w-12 rounded-md" />
              </div>
            ))
          : documents.map((document) => (
              <div
                key={document.id}
                className="flex items-center gap-3 border-t border-border px-5 py-3.5 first:border-t-0"
              >
                <FileText className="size-4 shrink-0 text-muted-foreground" />

                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-foreground">
                    {document.filename}
                  </p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {document.time_label}
                  </p>
                </div>

                <DocumentStatusBadge status={document.status} />
              </div>
            ))}
      </div>
    </Card>
  );
}
