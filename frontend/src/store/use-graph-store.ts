import { create } from "zustand";

import { ApiError } from "@/api/client";
import { getDefaultEntityId, getEntityDetail, getGraphOverview } from "@/api/graph";
import type { EntityDetail, GraphOverviewResponse } from "@/types/mock";

export const ZOOM_MIN = 0.7;
export const ZOOM_MAX = 2.2;
const ZOOM_STEP = 0.25;

type GraphStore = {
  overview: GraphOverviewResponse | null;
  loading: boolean;
  error: string | null;

  selectedId: string | null;
  detail: EntityDetail | null;
  detailLoading: boolean;
  /** 实体详情加载失败原因（如 ENTITY_NOT_FOUND / FORBIDDEN / NOT_IMPLEMENTED） */
  detailError: string | null;

  zoom: number;

  load: () => Promise<void>;
  select: (entityId: string) => void;
  closeDetail: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
};

/** 知识图谱（p04）数据源 */
export const useGraphStore = create<GraphStore>((set, get) => ({
  overview: null,
  loading: true,
  error: null,

  selectedId: null,
  detail: null,
  detailLoading: false,
  detailError: null,

  zoom: 1,

  load: async () => {
    set({ loading: true, error: null });
    try {
      const overview = await getGraphOverview();
      set({ overview, loading: false });

      const defaultId = await getDefaultEntityId();
      if (defaultId && overview.nodes.some((node) => node.id === defaultId)) {
        get().select(defaultId);
      }
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "图谱数据加载失败",
      });
    }
  },

  select: (entityId) => {
    set({ selectedId: entityId, detailLoading: true, detailError: null });
    void getEntityDetail(entityId).then(
      (detail) => {
        // 防止竞态：仅当仍是当前选中实体时才写入
        if (get().selectedId !== entityId) return;
        set({ detail, detailLoading: false });
      },
      (error: unknown) => {
        if (get().selectedId !== entityId) return;
        // 契约错误：ENTITY_NOT_FOUND / FORBIDDEN / NOT_IMPLEMENTED 等
        const code = error instanceof ApiError ? error.code : "INTERNAL_ERROR";
        set({ detail: null, detailLoading: false, detailError: code });
      },
    );
  },

  closeDetail: () =>
    set({ selectedId: null, detail: null, detailError: null }),

  zoomIn: () =>
    set((state) => ({ zoom: Math.min(ZOOM_MAX, state.zoom + ZOOM_STEP) })),

  zoomOut: () =>
    set((state) => ({ zoom: Math.max(ZOOM_MIN, state.zoom - ZOOM_STEP) })),

  resetZoom: () => set({ zoom: 1 }),
}));
