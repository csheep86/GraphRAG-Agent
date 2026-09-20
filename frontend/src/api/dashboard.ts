import type { MetricOverview, QaHistoryItem } from "@/types/mock";

import { delay, request, shouldMock } from "./client";
import {
  MOCK_METRIC_OVERVIEW,
  MOCK_RECENT_QA_HISTORY,
} from "./mock/dashboard";

/** 工作台指标卡。契约缺失：需后端补 `GET /api/v1/metrics/overview` */
export async function getMetricOverview(): Promise<MetricOverview> {
  if (shouldMock("/api/v1/metrics/overview")) {
    await delay(240);
    return MOCK_METRIC_OVERVIEW;
  }

  return request<MetricOverview>("/api/v1/metrics/overview");
}

/** 工作台「最近问答历史」。契约缺失：需后端补 `GET /api/v1/qa/history` */
export async function getRecentQaHistory(
  limit = 3,
): Promise<QaHistoryItem[]> {
  if (shouldMock("/api/v1/qa/history")) {
    await delay(200);
    return MOCK_RECENT_QA_HISTORY.slice(0, limit);
  }

  return request<QaHistoryItem[]>(`/api/v1/qa/history?limit=${limit}`);
}
