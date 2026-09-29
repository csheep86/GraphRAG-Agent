import type {
  AffiliationSeverity,
  AffiliationSuspicionStatus,
  AffiliationSuspicionType,
  DocumentStatus,
} from "@/types/mock";

export type StatusBadgeVariant =
  "pending" | "processing" | "completed" | "failed";

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
export const STATUS_FILTER_OPTIONS: {
  value: DocumentStatus | "all";
  label: string;
}[] = [
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
  "pending" | "processing" | "completed" | "failed" | "muted" | "outline";

type SuspicionMeta = { label: string; variant: SuspicionBadgeVariant };

/**
 * 疑点类型（契约 `suspicion_type`）
 *
 * `missing_check_in` 为 **Sprint 9.5 批次 C2 域化新增**（考勤域「工作日缺卡」）；
 * `shared_phone` / `cycle` / `amount_mismatch` 为 **Sprint 9.12 批次 C2 新增**
 * （三类图算法 + 三方金额不一致，判据冻结在 `specs/m4` §4.7.2）。
 * 金融域各类保留不动 —— 契约是「只加不改」，前端按域各显示各的，不做跨域混用。
 */
export const SUSPICION_TYPE_META: Record<
  AffiliationSuspicionType,
  SuspicionMeta
> = {
  shared_legal_rep: { label: "共享法定代表人", variant: "outline" },
  shared_address: { label: "共享注册地址", variant: "outline" },
  missing_check_in: { label: "工作日缺卡", variant: "outline" },
  shared_phone: { label: "共享联系电话", variant: "outline" },
  cycle: { label: "循环持股", variant: "outline" },
  amount_mismatch: { label: "三方金额不一致", variant: "outline" },
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

/**
 * 类型筛选下拉（**金融域视图**）：只列金融域类型，`missing_check_in` 属考勤域，
 * 按「不做跨域混用」不进本列表（它仍可经 `SUSPICION_TYPE_META` 正确渲染）。
 */
export const SUSPICION_TYPE_OPTIONS: {
  value: AffiliationSuspicionType | "all";
  label: string;
}[] = [
  { value: "all", label: "全部类型" },
  { value: "shared_legal_rep", label: "共享法定代表人" },
  { value: "shared_address", label: "共享注册地址" },
  { value: "shared_phone", label: "共享联系电话" },
  { value: "cycle", label: "循环持股" },
  { value: "amount_mismatch", label: "三方金额不一致" },
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
