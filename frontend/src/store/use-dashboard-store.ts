import { create } from "zustand";

import { getMetricOverview, getRecentQaHistory } from "@/api/dashboard";
import {
  listRecentDocuments,
} from "@/api/documents";
import type {
  DocumentListItem,
  MetricOverview,
  QaHistoryItem,
} from "@/types/mock";

type DashboardStore = {
  metrics: MetricOverview | null;
  recentDocuments: DocumentListItem[];
  recentQaHistory: QaHistoryItem[];
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
};

/** 工作台概览（p01）数据源 */
export const useDashboardStore = create<DashboardStore>((set) => ({
  metrics: null,
  recentDocuments: [],
  recentQaHistory: [],
  loading: true,
  error: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      const [metrics, recentDocuments, recentQaHistory] = await Promise.all([
        getMetricOverview(),
        listRecentDocuments(4),
        getRecentQaHistory(3),
      ]);
      set({ metrics, recentDocuments, recentQaHistory, loading: false });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "工作台数据加载失败",
      });
    }
  },
}));
