import type { MetricOverview, QaHistoryItem } from "@/types/mock";

/** p01 KPI 指标卡（契约缺失：需后端补 GET /api/v1/metrics/overview） */
export const MOCK_METRIC_OVERVIEW: MetricOverview = {
  processed_documents: 1248,
  processed_documents_delta_pct: 12.6,
  kg_entities: 86492,
  kg_relations: 24608,
  today_answers: 326,
  active_users: 48,
  answer_success_rate: 97.8,
  answer_success_rate_delta_pct: 1.4,
};

/** p01「最近问答历史」（契约缺失：需后端补 GET /api/v1/qa/history） */
export const MOCK_RECENT_QA_HISTORY: QaHistoryItem[] = [
  {
    id: "qa-71c4f0a2",
    question: "哪些文档涉及数据安全合规？",
    asked_at_label: "刚刚",
    citation_count: 3,
  },
  {
    id: "qa-3b8d5e17",
    question: "总结 Q3 产品路线图的关键节点",
    asked_at_label: "12 分钟前",
    citation_count: 5,
  },
  {
    id: "qa-9e2a6c40",
    question: "华东客户最关心的功能是什么？",
    asked_at_label: "昨天 18:02",
    citation_count: 2,
  },
];
