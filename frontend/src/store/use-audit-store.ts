import { create } from "zustand";

import {
  listAuditLogs,
  listAuditLogsByTrace,
  type AuditLogItem,
  type AuditStatus,
  type AuditTraceResponse,
} from "@/api/audit";

/** 页大小固定 50 = M5 §3 验收 7 的默认值（不引入可调 UI：契约上限 100） */
export const AUDIT_PAGE_SIZE = 50;

export type AuditStatusFilter = AuditStatus | "all";

type AuditStore = {
  items: AuditLogItem[];
  total: number;
  page: number;
  statusFilter: AuditStatusFilter;
  loading: boolean;
  initialized: boolean;
  error: string | null;

  /** 「按 trace 回看」的结果；未查询过为 `null`（查到空集则为 `{ total: 0 }`） */
  traceResult: AuditTraceResponse | null;
  traceLoading: boolean;

  /** trace 输入框的值（不直接触发查询，避免每敲一个字符打一次后端） */
  traceInput: string;

  load: () => Promise<void>;
  setStatusFilter: (value: AuditStatusFilter) => void;
  setPage: (page: number) => void;
  setTraceInput: (value: string) => void;
  searchTrace: (traceId?: string) => Promise<void>;
  clearTrace: () => void;
};

/**
 * 审计页数据源（Sprint 8.1 批次 A，决策 **A8**：不引轮询）。
 *
 * 审计是**事后账本**，不是异步任务——页面上的记录只会随时间增加，没有
 * 「处理中 → 完成」的状态迁移，因此轮询只会平白给 `audit_log` 灌自举行。
 * 需要刷新就点「刷新」。
 */
export const useAuditStore = create<AuditStore>((set, get) => ({
  items: [],
  total: 0,
  page: 1,
  statusFilter: "all",
  loading: true,
  initialized: false,
  error: null,

  traceResult: null,
  traceLoading: false,
  traceInput: "",

  load: async () => {
    const { page, statusFilter } = get();
    set({ loading: true, error: null });
    try {
      const response = await listAuditLogs({
        page,
        page_size: AUDIT_PAGE_SIZE,
        ...(statusFilter === "all" ? {} : { status: statusFilter }),
      });
      set({
        items: response.items,
        total: response.total,
        page: response.page,
        loading: false,
        initialized: true,
      });
    } catch (error) {
      set({
        loading: false,
        initialized: true,
        error: error instanceof Error ? error.message : "审计记录加载失败",
      });
    }
  },

  setStatusFilter: (statusFilter) => {
    set({ statusFilter, page: 1 });
    void get().load();
  },

  setPage: (page) => {
    set({ page });
    void get().load();
  },

  setTraceInput: (traceInput) => set({ traceInput }),

  /**
   * 按 trace 回看。**跨租户 / 查不到都是空集**（不是错误），UI 必须照空态渲染，
   * 不让用户以为接口挂了。
   */
  searchTrace: async (traceId) => {
    const target = (traceId ?? get().traceInput).trim();
    if (!target) return;

    set({ traceLoading: true, error: null, traceInput: target });
    try {
      const response = await listAuditLogsByTrace(target);
      set({ traceResult: response, traceLoading: false });
    } catch (error) {
      set({
        traceResult: null,
        traceLoading: false,
        error: error instanceof Error ? error.message : "trace 回看失败",
      });
    }
  },

  clearTrace: () => set({ traceInput: "", traceResult: null }),
}));
