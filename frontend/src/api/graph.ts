import type { components } from "@/types/api";
import type { EntityDetail, GraphOverviewResponse } from "@/types/mock";

import { delay, request, shouldMock } from "./client";
import {
  MOCK_DEFAULT_ENTITY_ID,
  MOCK_DOCUMENT_GRAPH,
  MOCK_GRAPH_OVERVIEW,
  getMockEntityDetail,
} from "./mock/graph";

/** 全局图谱概览。契约缺失：需后端补 `GET /api/v1/graph/overview` */
export async function getGraphOverview(): Promise<GraphOverviewResponse> {
  if (shouldMock("/api/v1/graph/overview")) {
    await delay(280);
    return MOCK_GRAPH_OVERVIEW;
  }

  return request<GraphOverviewResponse>("/api/v1/graph/overview");
}

/** 实体详情。契约缺失：需后端补 `GET /api/v1/entities/{id}` */
export async function getEntityDetail(
  entityId: string,
): Promise<EntityDetail | null> {
  if (shouldMock("/api/v1/entities/{id}")) {
    await delay(180);
    return getMockEntityDetail(entityId);
  }

  return request<EntityDetail>(`/api/v1/entities/${entityId}`);
}

/** 默认聚焦实体（设计稿首屏为「数据安全合规」） */
export async function getDefaultEntityId(): Promise<string | null> {
  // 契约外 + 不发请求：永远 mock，避免 p04 首屏因返回 null 而空白聚焦。
  // TODO: 契约补齐 `/api/v1/entities/default` 后改回 `if (shouldMock(...))` 三元判定。
  return MOCK_DEFAULT_ENTITY_ID;
}

/**
 * 文档级子图。
 * ✅ 契约已存在且已实装（v1.0.0）：`GET /api/v1/documents/{id}/graph`
 */
export async function getDocumentGraph(
  documentId: string,
): Promise<components["schemas"]["DocumentGraphResponse"]> {
  if (shouldMock("/api/v1/documents/{id}/graph")) {
    await delay(220);
    return MOCK_DOCUMENT_GRAPH;
  }

  return request<components["schemas"]["DocumentGraphResponse"]>(
    `/api/v1/documents/${documentId}/graph`,
  );
}
