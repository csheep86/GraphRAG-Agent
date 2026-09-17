import type { components } from "@/types/api";
import type { EntityDetail, GraphOverviewResponse } from "@/types/mock";

import { USE_MOCK, delay, request } from "./client";
import {
  MOCK_DEFAULT_ENTITY_ID,
  MOCK_GRAPH_OVERVIEW,
  getMockEntityDetail,
} from "./mock/graph";

/** 全局图谱概览。契约缺失：需后端补 `GET /api/v1/graph/overview` */
export async function getGraphOverview(): Promise<GraphOverviewResponse> {
  if (USE_MOCK) {
    await delay(280);
    return MOCK_GRAPH_OVERVIEW;
  }

  return request<GraphOverviewResponse>("/api/v1/graph/overview");
}

/** 实体详情。契约缺失：需后端补 `GET /api/v1/entities/{id}` */
export async function getEntityDetail(
  entityId: string,
): Promise<EntityDetail | null> {
  if (USE_MOCK) {
    await delay(180);
    return getMockEntityDetail(entityId);
  }

  return request<EntityDetail>(`/api/v1/entities/${entityId}`);
}

/** 默认聚焦实体（设计稿首屏为「数据安全合规」） */
export async function getDefaultEntityId(): Promise<string | null> {
  if (USE_MOCK) return MOCK_DEFAULT_ENTITY_ID;
  return null;
}

/**
 * 文档级子图。
 * ✅ 契约已存在：`GET /api/v1/documents/{id}/graph`（当前 501 NOT_IMPLEMENTED）
 */
export async function getDocumentGraph(
  documentId: string,
): Promise<components["schemas"]["DocumentGraphResponse"]> {
  return request<components["schemas"]["DocumentGraphResponse"]>(
    `/api/v1/documents/${documentId}/graph`,
  );
}
