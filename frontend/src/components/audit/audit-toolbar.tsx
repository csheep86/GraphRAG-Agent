"use client";

import { Loader2, RefreshCw, ScrollText, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { useAuditStore, type AuditStatusFilter } from "@/store/use-audit-store";

const STATUS_OPTIONS: { value: AuditStatusFilter; label: string }[] = [
  { value: "all", label: "全部结果" },
  { value: "success", label: "仅成功" },
  { value: "failure", label: "仅失败" },
];

export function AuditToolbar() {
  const total = useAuditStore((state) => state.total);
  const loading = useAuditStore((state) => state.loading);
  const statusFilter = useAuditStore((state) => state.statusFilter);
  const setStatusFilter = useAuditStore((state) => state.setStatusFilter);
  const load = useAuditStore((state) => state.load);

  const traceInput = useAuditStore((state) => state.traceInput);
  const setTraceInput = useAuditStore((state) => state.setTraceInput);
  const searchTrace = useAuditStore((state) => state.searchTrace);
  const clearTrace = useAuditStore((state) => state.clearTrace);
  const traceLoading = useAuditStore((state) => state.traceLoading);
  const traceResult = useAuditStore((state) => state.traceResult);

  const hasTraceQuery = traceResult !== null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          {loading ? "加载中…" : "刷新"}
        </Button>

        <Select
          value={statusFilter}
          onValueChange={(value) => setStatusFilter(value as AuditStatusFilter)}
        >
          <SelectTrigger className="w-[124px]" aria-label="按结果筛选">
            {/* 直接渲染文案而非 SelectValue：保证 SSR 首屏有字，避免水合闪烁 */}
            <span>
              {STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label}
            </span>
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span className="text-[13px] text-muted-foreground">
          共 {total} 条记录
        </span>
      </div>

      {/* 按 trace 回看（plan §7.2 步骤 6：审计页要能按 trace_id 过滤回看任一步） */}
      <div className="flex flex-wrap items-center gap-2">
        <ScrollText className="size-4 shrink-0 text-muted-foreground" />
        <Input
          value={traceInput}
          onChange={(event) => setTraceInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void searchTrace();
          }}
          placeholder="输入 trace_id 回看该次调用链"
          aria-label="trace_id"
          className="max-w-[320px] font-mono text-[12px]"
        />
        <Button
          variant="outline"
          onClick={() => void searchTrace()}
          disabled={traceLoading || traceInput.trim().length === 0}
        >
          {traceLoading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Search className="size-4" />
          )}
          回看
        </Button>
        {hasTraceQuery ? (
          <Button variant="ghost" onClick={clearTrace}>
            <X className="size-4" />
            清除回看
          </Button>
        ) : null}
      </div>
    </div>
  );
}
