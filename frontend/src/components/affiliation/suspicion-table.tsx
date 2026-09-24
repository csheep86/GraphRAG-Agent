"use client";

import { Check, SearchX, TriangleAlert, X } from "lucide-react";

import { SuspicionDetailSheet } from "@/components/affiliation/suspicion-detail-sheet";
import {
  SuspicionSeverityBadge,
  SuspicionStatusBadge,
  SuspicionTypeBadge,
} from "@/components/common/suspicion-badges";
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
import { useAffiliationStore } from "@/store/use-affiliation-store";

const COLUMNS = ["类型", "严重度", "涉及主体", "证据", "状态", "操作"];

export function SuspicionTable() {
  const items = useAffiliationStore((state) => state.items);
  const loading = useAffiliationStore((state) => state.loading);
  const initialized = useAffiliationStore((state) => state.initialized);
  const error = useAffiliationStore((state) => state.error);
  const taskId = useAffiliationStore((state) => state.taskId);
  const typeFilter = useAffiliationStore((state) => state.typeFilter);
  const statusFilter = useAffiliationStore((state) => state.statusFilter);
  const openDetail = useAffiliationStore((state) => state.openDetail);
  const review = useAffiliationStore((state) => state.review);

  const showSkeleton = loading || !initialized;

  // 类型 / 状态筛选在前端内存过滤：契约的 GET /affiliation/suspicions
  // 只支持 task_id 一个查询参数，不引入后端没有的参数。
  const visible = items.filter((item) => {
    const matchType =
      typeFilter === "all" || item.suspicion_type === typeFilter;
    const matchStatus = statusFilter === "all" || item.status === statusFilter;
    return matchType && matchStatus;
  });

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
                      <Skeleton className="h-5 w-24 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-10 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-3.5 w-56" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-24 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-14 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-32 rounded-md" />
                    </TableCell>
                  </TableRow>
                ))
              : visible.map((item) => {
                  const reviewed = item.status !== "open";

                  return (
                    <TableRow key={item.id}>
                      <TableCell>
                        <SuspicionTypeBadge type={item.suspicion_type} />
                      </TableCell>

                      <TableCell>
                        <SuspicionSeverityBadge severity={item.severity} />
                      </TableCell>

                      <TableCell className="max-w-[280px]">
                        <span
                          className="block truncate text-[13px] text-foreground"
                          title={item.entity_names.join(" · ")}
                        >
                          {item.entity_names.join(" · ")}
                        </span>
                      </TableCell>

                      <TableCell className="text-[13px] text-muted-foreground">
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => void openDetail(item)}
                        >
                          {item.evidence.length} 条证据
                        </Button>
                      </TableCell>

                      <TableCell>
                        <SuspicionStatusBadge status={item.status} />
                      </TableCell>

                      <TableCell>
                        <div className="flex items-center gap-2">
                          {/* 决策 C5：已复核不可改回 open（后端 400），不做"撤销" */}
                          <Button
                            variant="outline"
                            size="xs"
                            disabled={reviewed}
                            title={
                              reviewed
                                ? "已复核的疑点不可改回待复核（契约限定）"
                                : undefined
                            }
                            onClick={() => void review(item.id, "confirmed")}
                          >
                            <Check className="size-3.5" />
                            确认
                          </Button>
                          <Button
                            variant="outline"
                            size="xs"
                            disabled={reviewed}
                            title={
                              reviewed
                                ? "已复核的疑点不可改回待复核（契约限定）"
                                : undefined
                            }
                            onClick={() => void review(item.id, "dismissed")}
                          >
                            <X className="size-3.5" />
                            驳回
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
          </TableBody>
        </Table>

        {!showSkeleton && visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
            <SearchX className="size-6 text-muted-foreground/60" />
            <p className="text-[13px] text-foreground">
              {taskId === null && items.length === 0
                ? "还没有检测记录"
                : "没有匹配的疑点"}
            </p>
            <p className="text-xs text-muted-foreground">
              {taskId === null && items.length === 0
                ? "点上方「跑一次检测」，系统会基于已完成解析的文档识别关联关系疑点。"
                : "试试把类型或状态筛选切回「全部」。"}
            </p>
          </div>
        ) : null}
      </Card>

      <SuspicionDetailSheet />
    </div>
  );
}
