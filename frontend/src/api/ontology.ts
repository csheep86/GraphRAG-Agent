import type { components } from "@/types/api";

import { delay, request, shouldMock } from "./client";
import { MOCK_ACTION_KG_VERSION, MOCK_MERGE_CANDIDATES } from "./mock/ontology";

export type OntologyCandidate = components["schemas"]["OntologyCandidate"];
export type OntologyCandidateListResponse =
  components["schemas"]["OntologyCandidateListResponse"];
export type OntologyActionResponse =
  components["schemas"]["OntologyActionResponse"];

/** 候选处置档位（契约 Literal 五值，不另造枚举） */
export type OntologyCandidateStatus = OntologyCandidate["status"];

export const CANDIDATE_STATUS_OPTIONS: {
  value: OntologyCandidateStatus | "all";
  label: string;
}[] = [
  { value: "all", label: "全部档位" },
  { value: "human_review", label: "待人工复核" },
  { value: "pending", label: "待处置" },
  { value: "auto_merged", label: "已自动合并" },
  { value: "applied", label: "已应用" },
  { value: "rejected", label: "已驳回" },
];

/** 每页条数：与后端默认一致（契约默认 50 / 上限 100），不做可调 UI */
export const CANDIDATE_PAGE_SIZE = 50;

const CANDIDATES_PATH = "/api/v1/ontology/candidates";
const MERGE_PATH = "/api/v1/ontology/merge";
const SPLIT_PATH = "/api/v1/ontology/split";
const RENAME_PATH = "/api/v1/ontology/rename";

export type ListCandidatesParams = {
  status?: OntologyCandidateStatus;
  page?: number;
  page_size?: number;
};

/**
 * 实体消解候选列表（`GET /api/v1/ontology/candidates`）。
 *
 * ✅ 契约已实装（P5-I）。它是**校正 GUI 的实体来源**（m6 §1.1 第 2 条要求 GUI 与
 * `entity_merge_candidates` 表绑定）⇒ 前端**不**另造实体搜索入口。
 *
 * **跨租户是空集**（不是错误）：列表类端点泄露不了单条资源的存在性，
 * UI 必须照空态渲染，不能读成"接口挂了"。
 */
export async function listMergeCandidates(
  params: ListCandidatesParams = {},
): Promise<OntologyCandidateListResponse> {
  if (shouldMock(CANDIDATES_PATH)) {
    await delay(320);
    const filtered = params.status
      ? MOCK_MERGE_CANDIDATES.filter((row) => row.status === params.status)
      : MOCK_MERGE_CANDIDATES;
    return {
      total: filtered.length,
      items: filtered,
      page: params.page ?? 1,
      page_size: params.page_size ?? CANDIDATE_PAGE_SIZE,
    };
  }

  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));

  const qs = query.toString();
  return request<OntologyCandidateListResponse>(
    `${CANDIDATES_PATH}${qs ? `?${qs}` : ""}`,
  );
}

/** 合并：`right` 并入 `left`（右侧不再独立存在） */
export async function mergeEntities(payload: {
  left_entity_id: string;
  right_entity_id: string;
}): Promise<OntologyActionResponse> {
  if (shouldMock(MERGE_PATH)) {
    await delay(320);
    return { kg_version: MOCK_ACTION_KG_VERSION, status: "applied" };
  }

  return request<OntologyActionResponse>(MERGE_PATH, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * 拆分：一个实体拆成 ≥2 个新实体。
 *
 * **只填规范名**：契约的 `OntologyNewEntity` 目前只有 `canonical_name`
 * （spec §5.5 的省略号**不自行展开**）⇒ 前端**不**假造关系信息
 * （关系迁移取后端的「默认同名」规则）。
 */
export async function splitEntity(payload: {
  entity_id: string;
  new_entities: { canonical_name: string }[];
}): Promise<OntologyActionResponse> {
  if (shouldMock(SPLIT_PATH)) {
    await delay(320);
    return { kg_version: MOCK_ACTION_KG_VERSION, status: "applied" };
  }

  return request<OntologyActionResponse>(SPLIT_PATH, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 改名：旧名进 `aliases`（后端负责），前端只提交新规范名 */
export async function renameEntity(payload: {
  entity_id: string;
  new_canonical_name: string;
}): Promise<OntologyActionResponse> {
  if (shouldMock(RENAME_PATH)) {
    await delay(320);
    return { kg_version: MOCK_ACTION_KG_VERSION, status: "applied" };
  }

  return request<OntologyActionResponse>(RENAME_PATH, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
