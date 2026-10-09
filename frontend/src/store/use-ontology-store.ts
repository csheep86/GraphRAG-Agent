"use client";

import { create } from "zustand";

import {
  CANDIDATE_PAGE_SIZE,
  listMergeCandidates,
  mergeEntities,
  renameEntity,
  splitEntity,
  type OntologyCandidate,
  type OntologyCandidateStatus,
} from "@/api/ontology";
import { ApiError } from "@/api/client";
import { useGraphStore } from "@/store/use-graph-store";

export type CorrectionAction = "merge" | "split" | "rename";

export type CandidateStatusFilter = OntologyCandidateStatus | "all";

type CorrectionDialog = {
  action: CorrectionAction;
  candidate: OntologyCandidate;
} | null;

type OntologyStore = {
  items: OntologyCandidate[];
  total: number;
  page: number;
  statusFilter: CandidateStatusFilter;
  loading: boolean;
  initialized: boolean;
  error: string | null;

  /** 动作提交中（三动作是**同步**端点：返回即已 applied，不轮询） */
  submitting: boolean;
  /** 动作失败的可辨识反馈；成功即清空 */
  actionError: string | null;
  /** 最近一次动作产出的**新** kg_version（D5 = A：UI 必须能看到它） */
  lastKgVersion: string | null;
  /** 图谱视图是否已随新版本刷新过（`GET /graph/overview`，该路径已切版本继承读） */
  graphRefreshedAt: string | null;

  dialog: CorrectionDialog;

  load: () => Promise<void>;
  setStatusFilter: (value: CandidateStatusFilter) => void;
  setPage: (page: number) => void;
  openDialog: (action: CorrectionAction, candidate: OntologyCandidate) => void;
  closeDialog: () => void;
  submitMerge: (candidate: OntologyCandidate) => Promise<boolean>;
  submitRename: (entityId: string, newName: string) => Promise<boolean>;
  submitSplit: (entityId: string, names: string[]) => Promise<boolean>;
};

/**
 * 把后端错误翻成**可辨识**的中文反馈（判据 7：不吞错、不假造成功）。
 *
 * 三条必须分得开：
 * - **403**：跨租户 / 无权限（**不是** 404 —— ADR-0003 要求两者严格区分）；
 * - **404**：实体不存在（`ENTITY_NOT_FOUND`）；
 * - **409**：无 active `kg_version`（`KG_VERSION_NOT_ACTIVE`）。
 */
function describeActionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return `被拒绝（403 ${error.code}）：该实体不属于当前租户，或当前角色没有本体写权限。`;
    }
    if (error.status === 404) {
      return `实体不存在（404 ${error.code}）：它已不在 active 图谱版本内，请刷新候选列表后重试。`;
    }
    if (error.status === 409) {
      return `当前没有 active 图谱版本（409 ${error.code}）：校正必须先有一个 active 版本，未降级到旧版本。`;
    }
    if (error.status === 400) {
      return `入参被拒（400 ${error.code}）：${error.message}`;
    }
    return `动作未成功（${error.status} ${error.code}）：${error.message}`;
  }
  return error instanceof Error ? error.message : "动作未成功，原因未知";
}

export const useOntologyStore = create<OntologyStore>((set, get) => ({
  items: [],
  total: 0,
  page: 1,
  statusFilter: "human_review",
  loading: true,
  initialized: false,
  error: null,

  submitting: false,
  actionError: null,
  lastKgVersion: null,
  graphRefreshedAt: null,

  dialog: null,

  load: async () => {
    const { page, statusFilter } = get();
    set({ loading: true, error: null });
    try {
      const response = await listMergeCandidates({
        page,
        page_size: CANDIDATE_PAGE_SIZE,
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
        error: error instanceof Error ? error.message : "候选列表加载失败",
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

  openDialog: (action, candidate) => {
    set({ dialog: { action, candidate }, actionError: null });
  },

  closeDialog: () => set({ dialog: null, actionError: null }),

  submitMerge: async (candidate) => {
    set({ submitting: true, actionError: null });
    try {
      const response = await mergeEntities({
        left_entity_id: candidate.left_entity_id,
        right_entity_id: candidate.right_entity_id,
      });
      await applySuccess(set, get, response.kg_version);
      return true;
    } catch (error) {
      set({ submitting: false, actionError: describeActionError(error) });
      return false;
    }
  },

  submitRename: async (entityId, newName) => {
    set({ submitting: true, actionError: null });
    try {
      const response = await renameEntity({
        entity_id: entityId,
        new_canonical_name: newName,
      });
      await applySuccess(set, get, response.kg_version);
      return true;
    } catch (error) {
      set({ submitting: false, actionError: describeActionError(error) });
      return false;
    }
  },

  submitSplit: async (entityId, names) => {
    set({ submitting: true, actionError: null });
    try {
      const response = await splitEntity({
        entity_id: entityId,
        new_entities: names.map((canonical_name) => ({ canonical_name })),
      });
      await applySuccess(set, get, response.kg_version);
      return true;
    } catch (error) {
      set({ submitting: false, actionError: describeActionError(error) });
      return false;
    }
  },
}));

/**
 * 动作成功后的**同一套**收尾（三个动作共用，避免各写一遍而漏掉刷新）：
 *
 * 1. 记下响应回来的新 `kg_version`（D5）；
 * 2. **真的**刷新图谱视图 —— 走 `GET /graph/overview`，该路径自 P5-H 起按
 *    **版本继承读**（active ∪ 祖先）读图 ⇒ 刷新后看到的是完整图谱，
 *    而不是只有受影响子图；
 * 3. 重载候选列表（合并后对应行 `human_review` → `applied` ⇒ 它会从当前筛选里消失）。
 */
async function applySuccess(
  set: (partial: Partial<OntologyStore>) => void,
  get: () => OntologyStore,
  kgVersion: string,
): Promise<void> {
  set({
    submitting: false,
    actionError: null,
    dialog: null,
    lastKgVersion: kgVersion,
  });

  await useGraphStore.getState().load();
  set({ graphRefreshedAt: kgVersion });

  await get().load();
}
