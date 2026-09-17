import type { DocumentStatus } from "@/types/mock";

export type StatusBadgeVariant =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

type StatusMeta = {
  label: string;
  variant: StatusBadgeVariant;
};

/**
 * 文档状态文案与语义色。
 * 状态机取值严格对齐契约 `pending → processing → completed / failed`（M1 硬约束 H1）。
 */
export const DOCUMENT_STATUS_META: Record<DocumentStatus, StatusMeta> = {
  pending: { label: "待处理", variant: "pending" },
  processing: { label: "处理中", variant: "processing" },
  completed: { label: "已完成", variant: "completed" },
  failed: { label: "失败", variant: "failed" },
};

/** 「全部状态」筛选下拉选项 */
export const STATUS_FILTER_OPTIONS: { value: DocumentStatus | "all"; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "pending", label: "待处理" },
  { value: "processing", label: "处理中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];
