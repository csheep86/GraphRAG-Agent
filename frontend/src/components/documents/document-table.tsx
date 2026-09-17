"use client";

import Link from "next/link";
import { FileText, Network, RefreshCw, SearchX } from "lucide-react";

import { DocumentStatusBadge } from "@/components/common/document-status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useDocumentStore } from "@/store/use-document-store";

const COLUMNS = ["文件名", "类型", "状态", "实体数", "上传时间", "操作"];

export function DocumentTable() {
  const items = useDocumentStore((state) => state.items);
  const loading = useDocumentStore((state) => state.loading);
  const initialized = useDocumentStore((state) => state.initialized);
  const reprocess = useDocumentStore((state) => state.reprocess);

  const showSkeleton = loading || !initialized;

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {COLUMNS.map((column) => (
              <TableHead key={column}>{column}</TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <TableBody>
          {showSkeleton
            ? Array.from({ length: 5 }).map((_, index) => (
                <TableRow key={index} className="hover:bg-transparent">
                  <TableCell>
                    <Skeleton className="h-3.5 w-44" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-3.5 w-10" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-12 rounded-md" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-3.5 w-12" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-3.5 w-28" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-7 w-40 rounded-md" />
                  </TableCell>
                </TableRow>
              ))
            : items.map((document) => (
                <TableRow key={document.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <FileText className="size-4 shrink-0 text-muted-foreground" />
                      <span className="text-[13px] text-foreground">
                        {document.filename}
                      </span>
                    </div>
                  </TableCell>

                  <TableCell className="text-[13px] text-muted-foreground">
                    {document.file_type}
                  </TableCell>

                  <TableCell>
                    <DocumentStatusBadge status={document.status} />
                  </TableCell>

                  <TableCell className="text-[13px] text-foreground tabular-nums">
                    {document.entity_count === null ? (
                      <span className="text-muted-foreground">--</span>
                    ) : (
                      formatNumber(document.entity_count)
                    )}
                  </TableCell>

                  <TableCell className="text-[13px] text-muted-foreground tabular-nums">
                    {formatDateTime(document.uploaded_at)}
                  </TableCell>

                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="xs" asChild>
                        <Link href={`/graph?doc=${document.id}`}>
                          <Network className="size-3.5" />
                          查看图谱
                        </Link>
                      </Button>

                      <Button
                        variant="outline"
                        size="xs"
                        onClick={() => void reprocess(document.id)}
                      >
                        <RefreshCw className="size-3.5" />
                        重新处理
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
        </TableBody>
      </Table>

      {!showSkeleton && items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
          <SearchX className="size-6 text-muted-foreground/60" />
          <p className="text-[13px] text-foreground">没有匹配的文档</p>
          <p className="text-xs text-muted-foreground">
            试试调整关键词，或把状态筛选切回「全部状态」。
          </p>
        </div>
      ) : null}
    </Card>
  );
}
