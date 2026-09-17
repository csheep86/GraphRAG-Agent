import { create } from "zustand";

import {
  listDocuments,
  reprocessDocument,
  uploadDocument,
} from "@/api/documents";
import { inferFileType } from "@/lib/file";
import type { DocumentListItem, DocumentStatus } from "@/types/mock";

export type StatusFilter = DocumentStatus | "all";

type DocumentStore = {
  items: DocumentListItem[];
  total: number;
  keyword: string;
  status: StatusFilter;
  loading: boolean;
  initialized: boolean;
  uploading: boolean;
  uploadOpen: boolean;
  error: string | null;

  load: () => Promise<void>;
  setKeyword: (keyword: string) => void;
  setStatus: (status: StatusFilter) => void;
  setUploadOpen: (open: boolean) => void;
  upload: (file: File) => Promise<void>;
  reprocess: (documentId: string) => Promise<void>;
};

function nowStamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/**
 * Mock 模式下模拟异步链路状态流转：
 * `pending → processing → completed`（M1 硬约束 H1）。
 * 真实后端接入后应改为轮询 `GET /documents/{id}/status`。
 */
function scheduleProgress(
  get: () => DocumentStore,
  set: (partial: Partial<DocumentStore> | ((state: DocumentStore) => Partial<DocumentStore>)) => void,
  documentId: string,
) {
  const patch = (status: DocumentStatus, entityCount: number | null) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.id === documentId
          ? { ...item, status, entity_count: entityCount }
          : item,
      ),
    }));

  setTimeout(() => patch("processing", null), 1200);
  setTimeout(() => patch("completed", 1024 + Math.round(Math.random() * 900)), 3000);
  void get;
}

/** 文档管理（p02）数据源 */
export const useDocumentStore = create<DocumentStore>((set, get) => ({
  items: [],
  total: 0,
  keyword: "",
  status: "all",
  loading: true,
  initialized: false,
  uploading: false,
  uploadOpen: false,
  error: null,

  load: async () => {
    set({ loading: true, error: null });
    try {
      const { keyword, status } = get();
      const response = await listDocuments({ keyword, status });
      set({
        items: response.items,
        total: response.total,
        loading: false,
        initialized: true,
      });
    } catch (error) {
      set({
        loading: false,
        initialized: true,
        error: error instanceof Error ? error.message : "文档列表加载失败",
      });
    }
  },

  setKeyword: (keyword) => {
    set({ keyword });
    void get().load();
  },

  setStatus: (status) => {
    set({ status });
    void get().load();
  },

  setUploadOpen: (uploadOpen) => set({ uploadOpen }),

  upload: async (file) => {
    set({ uploading: true, error: null });
    try {
      const response = await uploadDocument(file);

      const item: DocumentListItem = {
        id: response.task_id,
        filename: file.name,
        file_type: inferFileType(file.name),
        status: "pending",
        entity_count: null,
        uploaded_at: nowStamp(),
        time_label: "刚刚",
        task_id: response.task_id,
        trace_id: response.trace_id,
      };

      set((state) => ({
        items: [item, ...state.items],
        total: state.total + 1,
        uploading: false,
        uploadOpen: false,
      }));

      scheduleProgress(get, set, item.id);
    } catch (error) {
      set({
        uploading: false,
        error: error instanceof Error ? error.message : "上传失败，请重试",
      });
    }
  },

  reprocess: async (documentId) => {
    set((state) => ({
      items: state.items.map((item) =>
        item.id === documentId
          ? { ...item, status: "processing", entity_count: null }
          : item,
      ),
    }));

    try {
      await reprocessDocument(documentId);
      scheduleProgress(get, set, documentId);
    } catch (error) {
      set((state) => ({
        error: error instanceof Error ? error.message : "重新处理失败",
        items: state.items.map((item) =>
          item.id === documentId ? { ...item, status: "failed" } : item,
        ),
      }));
    }
  },
}));
