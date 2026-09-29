import { create } from "zustand";

import { ApiError } from "@/api/client";
import { listDocuments } from "@/api/documents";
import { getGraphOverview } from "@/api/graph";
import type { DocumentListItem, GraphOverviewResponse } from "@/types/mock";

type DashboardStore = {
  /**
   * 首页 KPI 数据源。
   *
   * ⚠️ **刻意不用 `getMetricOverview()`**：它打的是 `/api/v1/metrics/overview`，
   * 该端点**不在契约内**，因此 `shouldMock()` 对它恒返回 true
   * （`api/client.ts:68-71`）——即使 `USE_MOCK=false` 也仍然是 Mock 常量。
   * 首页拿它出数字等于展示假数据，与 A16「诚实可核」冲突。
   *
   * 改用契约内已实装的 `GET /api/v1/graph/overview`（`entity_count` /
   * `relation_count` / `doc_count` / `kg_version`），关 Mock 即为真值。
   *
   * 同理不消费 `getRecentQaHistory()`（`/api/v1/qa/history` 也是契约外）。
   */
  graphOverview: GraphOverviewResponse | null;
  recentDocuments: DocumentListItem[];
  /**
   * 文档总数（`GET /api/v1/documents` 的 `total`）。
   * 与 `graphOverview.doc_count` 不同源：后者只统计**已建图**的文档，
   * 且依赖 Neo4j（不可用时整个 overview 拿不到）。
   */
  documentTotal: number | null;
  /** 图谱概览取不到时的失败原因（错误码）；拿得到时为 null */
  graphErrorCode: string | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
};

/** 工作台概览（p01）数据源 */
export const useDashboardStore = create<DashboardStore>((set) => ({
  graphOverview: null,
  recentDocuments: [],
  documentTotal: null,
  graphErrorCode: null,
  loading: true,
  error: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      let failedCode: string | null = null;

      const [documents, overview] = await Promise.all([
        // 一次拿 `total` + 前 4 条：比 `listRecentDocuments` 多带一个真实总数，
        // 且不额外打一次接口。
        listDocuments({ page: 1, page_size: 4 }),
        // 已知的两种"取不到"都兜底为 null（KPI 显示 `—`），不牵连文档列表：
        //  - 无 active kg_version → 409 `KG_VERSION_NOT_ACTIVE`（契约严禁静默降级）
        //  - Neo4j 不可用 → `NOT_IMPLEMENTED`（图谱存储未就绪）
        // 但**失败原因要留下来**：UI 得如实说明是哪种不可用，
        // 而不是笼统写"未激活"。
        getGraphOverview().catch((error: unknown) => {
          failedCode =
            error instanceof ApiError
              ? error.code
              : error instanceof Error
                ? error.message
                : "UNKNOWN";
          return null;
        }),
      ]);
      set({
        recentDocuments: documents.items,
        documentTotal: documents.total,
        graphOverview: overview,
        graphErrorCode: failedCode,
        loading: false,
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "工作台数据加载失败",
      });
    }
  },
}));
