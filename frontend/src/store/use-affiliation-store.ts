import { create } from "zustand";

import {
  detectAffiliation,
  getAffiliationTask,
  listAffiliationSuspicions,
  reviewAffiliationSuspicion,
} from "@/api/affiliation";
import { getDocumentChunk, listDocuments } from "@/api/documents";
import type { components } from "@/types/api";
import type {
  AffiliationSuspicionItem,
  AffiliationSuspicionStatus,
  AffiliationSuspicionType,
} from "@/types/mock";

export type SuspicionTypeFilter = AffiliationSuspicionType | "all";
export type SuspicionStatusFilter = AffiliationSuspicionStatus | "all";
/** 任务状态：与契约 `AffiliationTaskResponse.status` 同枚举 */
export type AffiliationTaskStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

type DocumentChunk = components["schemas"]["DocumentChunkResponse"];

/** key = 证据在 `detail.evidence` 数组中的下标 */
type ChunkMap = Record<number, DocumentChunk>;

type AffiliationStore = {
  items: AffiliationSuspicionItem[];
  total: number;
  /** 最近一次检测任务；从没跑过时为 `null`（契约语义，非错误） */
  taskId: string | null;
  taskStatus: AffiliationTaskStatus | null;
  typeFilter: SuspicionTypeFilter;
  statusFilter: SuspicionStatusFilter;
  loading: boolean;
  initialized: boolean;
  /** 检测任务在飞（控制"跑检测"按钮与轮询指示） */
  running: boolean;
  error: string | null;

  /** 详情抽屉：当前疑点 + 它每条证据的原文回查结果 */
  detail: AffiliationSuspicionItem | null;
  detailLoading: boolean;
  detailChunks: ChunkMap;
  detailErrors: Record<number, string>;

  load: (taskId?: string) => Promise<void>;
  detect: () => Promise<void>;
  review: (
    suspicionId: string,
    status: Exclude<AffiliationSuspicionStatus, "open">,
  ) => Promise<void>;
  setTypeFilter: (value: SuspicionTypeFilter) => void;
  setStatusFilter: (value: SuspicionStatusFilter) => void;
  openDetail: (item: AffiliationSuspicionItem) => Promise<void>;
  closeDetail: () => void;

  /** 轮询内部：调度一次 / 执行一次（暴露仅为 store 内互调） */
  schedulePoll: (attempt: number) => void;
  runPoll: (attempt: number) => Promise<void>;
};

/**
 * 轮询定时器句柄（模块级）。
 *
 * 全仓首个真轮询实现——documents 页那套是 `setTimeout` 假推进
 * （`use-document-store.ts` 的 `scheduleProgress`），真实链路不得沿用。
 * 句柄放模块级是为了 `detect()` 重入时先掐掉上一轮，避免两个轮询叠加。
 */
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

/** 疑点清单（p05）数据源 */
export const useAffiliationStore = create<AffiliationStore>((set, get) => ({
  items: [],
  total: 0,
  taskId: null,
  taskStatus: null,
  typeFilter: "all",
  statusFilter: "all",
  loading: true,
  initialized: false,
  running: false,
  error: null,

  detail: null,
  detailLoading: false,
  detailChunks: {},
  detailErrors: {},

  load: async (taskId) => {
    set({ loading: true, error: null });
    try {
      const response = await listAffiliationSuspicions(taskId);
      set({
        items: response.items,
        total: response.total,
        taskId: response.task_id ?? null,
        loading: false,
        initialized: true,
      });
    } catch (error) {
      set({
        loading: false,
        initialized: true,
        error: error instanceof Error ? error.message : "疑点清单加载失败",
      });
    }
  },

  /**
   * 发起检测（决策 C1）：对当前租户**全部 completed 文档**跑一次。
   * 不做跨页多选，也不让后端新增"全租户"语义——演示集规模下这是最顺的口径。
   */
  detect: async () => {
    stopPolling();
    set({ running: true, error: null });
    try {
      const documents = await listDocuments({
        status: "completed",
        page_size: 100,
      });
      const docIds = documents.items.map((item) => item.id);

      if (docIds.length === 0) {
        set({
          running: false,
          error: "当前没有解析完成的文档，无法发起检测",
        });
        return;
      }

      const response = await detectAffiliation(docIds);
      set({ taskId: response.task_id, taskStatus: "pending" });
      get().schedulePoll(0);
    } catch (error) {
      set({
        running: false,
        error: error instanceof Error ? error.message : "检测任务发起失败",
      });
    }
  },

  /** 决策 C3：首次 2s，3 次后降为 10s（契约注释 + `02-product-outline.md:196`） */
  schedulePoll: (attempt) => {
    stopPolling();
    const waitMs = attempt < 3 ? 2000 : 10000;
    pollTimer = setTimeout(() => {
      void get().runPoll(attempt);
    }, waitMs);
  },

  runPoll: async (attempt) => {
    const { taskId } = get();
    if (!taskId) return;

    try {
      const task = await getAffiliationTask(taskId);
      set({ taskStatus: task.status });

      if (task.status === "completed") {
        stopPolling();
        set({ running: false });
        await get().load(taskId);
        return;
      }

      if (task.status === "failed") {
        stopPolling();
        set({
          running: false,
          // failed 是真失败，不当空列表处理；错误码来自后端 error_code
          error: `检测任务失败${task.error_code ? `（${task.error_code}）` : ""}`,
        });
        return;
      }

      get().schedulePoll(attempt + 1);
    } catch (error) {
      stopPolling();
      set({
        running: false,
        error: error instanceof Error ? error.message : "检测任务状态查询失败",
      });
    }
  },

  /**
   * 复核一条疑点。契约只允许 `confirmed` / `dismissed`，已复核的**改不回**
   * `open`（后端返 400），故本页不提供"撤销"——做了就是假交互（决策 C5）。
   */
  review: async (suspicionId, status) => {
    try {
      const response = await reviewAffiliationSuspicion(suspicionId, status);
      const patch = {
        status: response.status,
        reviewed_at: response.reviewed_at ?? null,
        reviewed_by: response.reviewed_by ?? null,
      };
      set((state) => ({
        items: state.items.map((item) =>
          item.id === response.id ? { ...item, ...patch } : item,
        ),
        detail:
          state.detail && state.detail.id === response.id
            ? { ...state.detail, ...patch }
            : state.detail,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "复核失败，请重试",
      });
    }
  },

  setTypeFilter: (typeFilter) => set({ typeFilter }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),

  /**
   * 打开一条疑点 → 并发回查它**每条证据**的 chunk 原文（复用 Sprint 6 溯源端点）。
   *
   * `doc_id` 为 `null` 表示该 chunk 未挂 `:Document`（契约语义）——**不伪造
   * id 去撞接口**，直接在该条证据下说明无法回查。单条失败不影响其余证据。
   */
  openDetail: async (item) => {
    set({
      detail: item,
      detailLoading: true,
      detailChunks: {},
      detailErrors: {},
    });

    const results = await Promise.all(
      item.evidence.map(async (evidence) => {
        if (!evidence.doc_id) {
          return { error: "该证据未挂载到具体文档，无法回查原文" };
        }
        try {
          const chunk = await getDocumentChunk(
            evidence.doc_id,
            evidence.chunk_id,
          );
          return { chunk };
        } catch (error) {
          return {
            error: error instanceof Error ? error.message : "原文回查失败",
          };
        }
      }),
    );

    const chunks: ChunkMap = {};
    const errors: Record<number, string> = {};
    results.forEach((result, index) => {
      if (result.chunk) chunks[index] = result.chunk;
      if (result.error) errors[index] = result.error;
    });

    set({ detailLoading: false, detailChunks: chunks, detailErrors: errors });
  },

  closeDetail: () =>
    set({ detail: null, detailChunks: {}, detailErrors: {} }),
}));
