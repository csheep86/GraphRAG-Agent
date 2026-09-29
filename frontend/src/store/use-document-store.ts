import { create } from "zustand";

import { getDocumentStatus, listDocuments, uploadDocument } from "@/api/documents";
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
  upload: (file: File, documentDate?: string) => Promise<void>;
};

function nowStamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/**
 * 上传后真实轮询 GET /api/v1/documents/{id}/status（契约内）：
 * 只写回后端返回的 `status`；取不到就停在 `pending`（M1 硬约束 H1）。
 * R19：原实现用 setTimeout 假推进并编造 entity_count（1024+random），已删除。
 */
function pollStatus(
  get: () => DocumentStore,
  set: (partial: Partial<DocumentStore> | ((state: DocumentStore) => Partial<DocumentStore>)) => void,
  documentId: string,
) {
  const patch = (status: DocumentStatus) =>
    set((state) => ({
      items: state.items.map((item) =>
        item.id === documentId ? { ...item, status } : item,
      ),
    }));

  let attempt = 0;
  const tick = async () => {
    try {
      const res = await getDocumentStatus(documentId);
      patch(res.status);
      if (res.status === "completed" || res.status === "failed") {
        // 终态后回拉列表，用后端真值回填 entity_count（不自算、不猜数）
        void get().load();
        return;
      }
    } catch {
      return; // 取不到就保留原状态，不猜
    }
    attempt += 1;
    if (attempt >= 12) return;
    setTimeout(() => void tick(), attempt < 3 ? 2000 : 10000);
  };
  setTimeout(() => void tick(), 2000);
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
      const response = await listDocuments({ q: keyword, status });
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

  upload: async (file, documentDate) => {
    set({ uploading: true, error: null });
    try {
      const response = await uploadDocument(file, documentDate);

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

      pollStatus(get, set, item.id);
    } catch (error) {
      set({
        uploading: false,
        error: error instanceof Error ? error.message : "上传失败，请重试",
      });
    }
  },
}));
