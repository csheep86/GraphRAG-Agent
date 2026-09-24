"use client";

import {
  ChevronLeft,
  ChevronRight,
  SearchX,
  TriangleAlert,
} from "lucide-react";

import type { AuditLogItem } from "@/api/audit";
import { Badge } from "@/components/ui/badge";
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
import { formatDateTime } from "@/lib/format";
import { AUDIT_PAGE_SIZE, useAuditStore } from "@/store/use-audit-store";

const COLUMNS = ["时间", "操作", "资源", "结果", "来源 IP", "trace_id", ""];

/** 表格里截断 UUID 中段，完整值放 `title`（hover 可见） */
function shortUuid(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function StatusBadge({ status }: { status: AuditLogItem["status"] }) {
  return (
    <Badge variant={status === "success" ? "completed" : "failed"}>
      {status === "success" ? "成功" : "失败"}
    </Badge>
  );
}

export function AuditTable() {
  const items = useAuditStore((state) => state.items);
  const loading = useAuditStore((state) => state.loading);
  const initialized = useAuditStore((state) => state.initialized);
  const error = useAuditStore((state) => state.error);
  const total = useAuditStore((state) => state.total);
  const page = useAuditStore((state) => state.page);
  const setPage = useAuditStore((state) => state.setPage);
  const traceResult = useAuditStore((state) => state.traceResult);
  const searchTrace = useAuditStore((state) => state.searchTrace);

  const showSkeleton = loading || !initialized;
  const replaying = traceResult !== null;
  const rows = replaying ? traceResult.items : items;

  const pageCount = Math.max(1, Math.ceil(total / AUDIT_PAGE_SIZE));

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <div className="rounded-lg border border-[#f87171]/40 bg-[#f87171]/[0.07] p-3">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-[#f87171]">
            <TriangleAlert className="size-3.5" />
            操作未成功
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
            {error}
          </p>
        </div>
      ) : null}

      {replaying ? (
        <div className="rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2 text-[12px] text-foreground">
          正在回看 trace{" "}
          <span className="font-mono">{traceResult.trace_id}</span>：
          {traceResult.total} 条记录（<b>按时间正序</b>）。
          <span className="ml-1 text-muted-foreground">
            跨租户或查不到时这里是空集——空态不是错误。
          </span>
        </div>
      ) : null}

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
              ? Array.from({ length: 6 }).map((_, index) => (
                  <TableRow key={index} className="hover:bg-transparent">
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-64" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-12 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-24" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-16 rounded-md" />
                    </TableCell>
                  </TableRow>
                ))
              : rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="whitespace-nowrap text-[12px] text-muted-foreground">
                      {formatDateTime(row.ts)}
                    </TableCell>

                    <TableCell className="text-[13px] font-medium text-foreground">
                      {row.action}
                    </TableCell>

                    <TableCell className="max-w-[320px]">
                      <span
                        className="block truncate font-mono text-[11px] text-muted-foreground"
                        title={row.resource}
                      >
                        {row.resource}
                      </span>
                    </TableCell>

                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>

                    <TableCell className="text-[12px] text-muted-foreground">
                      {row.actor_ip ?? "--"}
                    </TableCell>

                    <TableCell
                      className="font-mono text-[11px] text-muted-foreground"
                      title={row.trace_id}
                    >
                      {shortUuid(row.trace_id)}
                    </TableCell>

                    <TableCell>
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={() => void searchTrace(row.trace_id)}
                        title="按该 trace_id 回看整条调用链"
                      >
                        回看
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>

        {!showSkeleton && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
            <SearchX className="size-6 text-muted-foreground/60" />
            <p className="text-[13px] text-foreground">
              {replaying ? "该 trace 下没有可见记录" : "还没有审计记录"}
            </p>
            <p className="text-xs text-muted-foreground">
              {replaying
                ? "trace_id 属于别的租户时也会是空集（租户隔离，ADR-0003）。"
                : "走一遍演示路径（上传 → 解析 → 建图 → 提问 → 检测 → 复核），这里就会留下每一步的痕迹。"}
            </p>
          </div>
        ) : null}
      </Card>

      {/* 分页（仅列表态；trace 回看态不支持分页——契约未定义） */}
      {!replaying && total > AUDIT_PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-2 text-[12px] text-muted-foreground">
          <Button
            variant="outline"
            size="xs"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="size-3.5" />
            上一页
          </Button>
          <span>
            第 {page} / {pageCount} 页 · 每页 {AUDIT_PAGE_SIZE} 条
          </span>
          <Button
            variant="outline"
            size="xs"
            disabled={page >= pageCount || loading}
            onClick={() => setPage(page + 1)}
          >
            下一页
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
