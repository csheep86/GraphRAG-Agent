import { create } from "zustand";

import { ApiError } from "@/api/client";
import { explainAnomaly, listAnomalies } from "@/api/anomaly";
import { ATTRIBUTION_ERROR_MESSAGE } from "@/lib/attribution";
import type { components } from "@/types/api";

type AnomalyCaseItem = components["schemas"]["AnomalyCaseItem"];
type AnomalyExplainResponse = components["schemas"]["AnomalyExplainResponse"];

type AttributionStore = {
  cases: AnomalyCaseItem[];
  kgVersion: string | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;

  /** 当前选中的异常用例 */
  selected: AnomalyCaseItem | null;
  explain: AnomalyExplainResponse | null;
  explainLoading: boolean;
  explainError: string | null;

  load: () => Promise<void>;
  select: (item: AnomalyCaseItem) => Promise<void>;
};

/**
 * 异常归因子页数据源（Sprint 9.5 批次 E3）。
 *
 * 两步：先拉异常清单（谁 / 哪天），选中一条再拉归因结论。
 * **归因不批量跑**：每条归因都要跨四系统取证，全量跑一遍既慢又没人看，
 * 让演示观众挑一条点开，正好还原 HR「一次处理一条」的真实节奏。
 */
export const useAttributionStore = create<AttributionStore>((set, get) => ({
  cases: [],
  kgVersion: null,
  loading: true,
  initialized: false,
  error: null,

  selected: null,
  explain: null,
  explainLoading: false,
  explainError: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      const data = await listAnomalies();
      set({
        cases: data.items,
        kgVersion: data.kg_version,
        loading: false,
        initialized: true,
      });
      // 首屏自动选中第一条：演示时打开就能看到结论，不用先点一下
      const first = data.items[0];
      if (first) await get().select(first);
    } catch (error) {
      set({
        loading: false,
        initialized: true,
        error:
          error instanceof ApiError
            ? (ATTRIBUTION_ERROR_MESSAGE[error.code] ?? error.message)
            : error instanceof Error
              ? error.message
              : "异常清单加载失败",
      });
    }
  },

  select: async (item) => {
    set({
      selected: item,
      explainLoading: true,
      explainError: null,
      explain: null,
    });
    try {
      const data = await explainAnomaly({
        employee_id: item.employee_id,
        date: item.date,
      });
      set({ explain: data, explainLoading: false });
    } catch (error) {
      set({
        explainLoading: false,
        explainError:
          error instanceof ApiError
            ? (ATTRIBUTION_ERROR_MESSAGE[error.code] ?? error.message)
            : error instanceof Error
              ? error.message
              : "归因失败",
      });
    }
  },
}));
