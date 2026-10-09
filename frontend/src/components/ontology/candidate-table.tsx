"use client";

import { ChevronLeft, ChevronRight, SearchX, TriangleAlert } from "lucide-react";

import type { OntologyCandidate } from "@/api/ontology";
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
import { CANDIDATE_PAGE_SIZE } from "@/api/ontology";
import { useOntologyStore } from "@/store/use-ontology-store";

const COLUMNS = [
  "保留侧实体",
  "被并入侧实体",
  "相似度",
  "档位",
  "判分依据",
  "落库时间",
  "",
];

const STATUS_TEXT: Record<OntologyCandidate["status"], string> = {
  pending: "待处置",
  auto_merged: "已自动合并",
  human_review: "待人工复核",
  rejected: "已驳回",
  applied: "已应用",
};

function StatusBadge({ status }: { status: OntologyCandidate["status"] }) {
  const variant =
    status === "applied"
      ? "completed"
      : status === "human_review"
        ? "pending"
        : status === "rejected"
          ? "failed"
          : "muted";
  return <Badge variant={variant}>{STATUS_TEXT[status]}</Badge>;
}

/** 实体 id 很长，表格里截断、完整值放 `title`（hover 可见） */
function EntityId({ value }: { value: string }) {
  return (
    <span
      className="block max-w-[220px] truncate font-mono text-[11px] text-foreground"
      title={value}
    >
      {value}
    </span>
  );
}

export function CandidateTable() {
  const items = useOntologyStore((state) => state.items);
  const loading = useOntologyStore((state) => state.loading);
  const initialized = useOntologyStore((state) => state.initialized);
  const error = useOntologyStore((state) => state.error);
  const total = useOntologyStore((state) => state.total);
  const page = useOntologyStore((state) => state.page);
  const setPage = useOntologyStore((state) => state.setPage);
  const openDialog = useOntologyStore((state) => state.openDialog);

  const showSkeleton = loading || !initialized;
  const pageCount = Math.max(1, Math.ceil(total / CANDIDATE_PAGE_SIZE));

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <div className="rounded-lg border border-severity-high/40 bg-severity-high/[0.07] p-3">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-severity-high">
            <TriangleAlert className="size-3.5" />
            候选列表加载失败
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
              ? Array.from({ length: 4 }).map((_, index) => (
                  <TableRow key={index} className="hover:bg-transparent">
                    <TableCell>
                      <Skeleton className="h-4 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-12" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-20 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-4 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-28 rounded-md" />
                    </TableCell>
                  </TableRow>
                ))
              : items.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <EntityId value={row.left_entity_id} />
                    </TableCell>

                    <TableCell>
                      <EntityId value={row.right_entity_id} />
                    </TableCell>

                    <TableCell className="text-[13px] font-medium text-foreground">
                      {row.similarity.toFixed(2)}
                    </TableCell>

                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>

                    <TableCell
                      className="max-w-[180px] truncate text-[11px] text-muted-foreground"
                      title={row.signals ? JSON.stringify(row.signals) : "无"}
                    >
                      {row.signals ? JSON.stringify(row.signals) : "--"}
                    </TableCell>

                    <TableCell className="whitespace-nowrap text-[12px] text-muted-foreground">
                      {formatDateTime(row.created_at)}
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => openDialog("merge", row)}
                          disabled={row.status === "applied"}
                          title="把被并入侧的实体并入保留侧"
                        >
                          合并
                        </Button>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => openDialog("rename", row)}
                          title="改实体的规范名（旧名进 aliases）"
                        >
                          改名
                        </Button>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => openDialog("split", row)}
                          title="把一个实体拆成多个新实体（≥2）"
                        >
                          拆分
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
            <p className="text-[13px] text-foreground">该档位下没有候选</p>
            <p className="text-xs text-muted-foreground">
              候选由实体消解环节写入 `entity_merge_candidates`；别的租户的候选
              <b>不会</b>出现在这里（租户隔离，ADR-0003）。
            </p>
          </div>
        ) : null}
      </Card>

      {!showSkeleton && total > CANDIDATE_PAGE_SIZE ? (
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
            第 {page} / {pageCount} 页 · 每页 {CANDIDATE_PAGE_SIZE} 条
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
