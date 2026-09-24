import type {
  AffiliationSeverity,
  AffiliationSuspicionStatus,
  AffiliationSuspicionType,
  DocumentStatus,
} from "@/types/mock";

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

/* --------------------------------------------------------------------------
 * Sprint 7.3 批次 C：M4 疑点的类型 / 严重度 / 复核状态
 * 取值严格对齐契约 `AffiliationSuspicionItem` 的三个枚举（不新增档位）
 * ------------------------------------------------------------------------ */

export type SuspicionBadgeVariant =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "muted"
  | "outline";

type SuspicionMeta = { label: string; variant: SuspicionBadgeVariant };

/** 疑点类型（契约 `suspicion_type`） */
export const SUSPICION_TYPE_META: Record<
  AffiliationSuspicionType,
  SuspicionMeta
> = {
  shared_legal_rep: { label: "共享法定代表人", variant: "outline" },
  shared_address: { label: "共享注册地址", variant: "outline" },
};

/** 严重度：高=红 · 中=蓝 · 低=灰 */
export const SUSPICION_SEVERITY_META: Record<
  AffiliationSeverity,
  SuspicionMeta
> = {
  high: { label: "高", variant: "failed" },
  medium: { label: "中", variant: "processing" },
  low: { label: "低", variant: "muted" },
};

/** 复核状态（契约 `status`；`open` 为初始态） */
export const SUSPICION_STATUS_META: Record<
  AffiliationSuspicionStatus,
  SuspicionMeta
> = {
  open: { label: "待复核", variant: "pending" },
  confirmed: { label: "已确认", variant: "completed" },
  dismissed: { label: "已驳回", variant: "muted" },
};

export const SUSPICION_TYPE_OPTIONS: {
  value: AffiliationSuspicionType | "all";
  label: string;
}[] = [
  { value: "all", label: "全部类型" },
  { value: "shared_legal_rep", label: "共享法定代表人" },
  { value: "shared_address", label: "共享注册地址" },
];

export const SUSPICION_STATUS_OPTIONS: {
  value: AffiliationSuspicionStatus | "all";
  label: string;
}[] = [
  { value: "all", label: "全部状态" },
  { value: "open", label: "待复核" },
  { value: "confirmed", label: "已确认" },
  { value: "dismissed", label: "已驳回" },
];
