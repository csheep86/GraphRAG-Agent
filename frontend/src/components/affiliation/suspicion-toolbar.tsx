"use client";

import { Loader2, Radar } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { SUSPICION_STATUS_OPTIONS, SUSPICION_TYPE_OPTIONS } from "@/lib/status";
import {
  useAffiliationStore,
  type SuspicionStatusFilter,
  type SuspicionTypeFilter,
} from "@/store/use-affiliation-store";

/** 任务状态文案（契约 `AffiliationTaskResponse.status` 四档） */
const TASK_STATUS_LABEL: Record<string, string> = {
  pending: "已受理，排队中",
  processing: "正在检测",
  completed: "检测完成",
  failed: "检测失败",
};

export function SuspicionToolbar() {
  const total = useAffiliationStore((state) => state.total);
  const running = useAffiliationStore((state) => state.running);
  const taskStatus = useAffiliationStore((state) => state.taskStatus);
  const typeFilter = useAffiliationStore((state) => state.typeFilter);
  const statusFilter = useAffiliationStore((state) => state.statusFilter);
  const setTypeFilter = useAffiliationStore((state) => state.setTypeFilter);
  const setStatusFilter = useAffiliationStore((state) => state.setStatusFilter);
  const detect = useAffiliationStore((state) => state.detect);

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* 决策 C1：一键对当前租户全部已完成文档跑一次检测 */}
      <Button onClick={() => void detect()} disabled={running}>
        {running ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Radar className="size-4" />
        )}
        {running ? "检测中…" : "跑一次检测"}
      </Button>

      <Select
        value={typeFilter}
        onValueChange={(value) => setTypeFilter(value as SuspicionTypeFilter)}
      >
        <SelectTrigger className="w-[152px]" aria-label="按类型筛选">
          {/* 直接渲染文案而非 SelectValue：保证 SSR 首屏有字，避免水合闪烁 */}
          <span>
            {SUSPICION_TYPE_OPTIONS.find((o) => o.value === typeFilter)?.label}
          </span>
        </SelectTrigger>
        <SelectContent>
          {SUSPICION_TYPE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={statusFilter}
        onValueChange={(value) =>
          setStatusFilter(value as SuspicionStatusFilter)
        }
      >
        <SelectTrigger className="w-[124px]" aria-label="按状态筛选">
          <span>
            {
              SUSPICION_STATUS_OPTIONS.find((o) => o.value === statusFilter)
                ?.label
            }
          </span>
        </SelectTrigger>
        <SelectContent>
          {SUSPICION_STATUS_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <span className="text-[13px] text-muted-foreground">
        共 {total} 条疑点
      </span>

      {running && taskStatus ? (
        <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          {TASK_STATUS_LABEL[taskStatus] ?? taskStatus}
        </span>
      ) : null}
    </div>
  );
}
