/**
 * 推理路径展示常量（Sprint 9.5 批次 E2 / 后端批次 D1）。
 *
 * 全部只是**展示文案**：路径的每一跳都由后端从图上取出来，前端不重排、不补跳、
 * 不做任何语义推断。未登记的 `entity_type` / `relation` 一律**原样显示**，
 * 不猜中文名——宁可露出编码也不替它解释。
 */

type EntityTypeMeta = { label: string; system: string };

/** 终点/途经实体的类型 → 中文名 + 所属系统（演示「跨四个系统取证」用） */
export const ENTITY_TYPE_META: Record<string, EntityTypeMeta> = {
  EMPLOYEE: { label: "员工", system: "HR 系统" },
  POSITION: { label: "岗位", system: "HR 系统" },
  DEPARTMENT: { label: "部门", system: "HR 系统" },
  POLICY_CLAUSE: { label: "制度条款", system: "制度库" },
  ATTENDANCE_RECORD: { label: "考勤记录", system: "考勤系统" },
  SHIFT: { label: "排班", system: "考勤系统" },
  LEAVE: { label: "请假", system: "HR 系统" },
  OVERTIME: { label: "加班", system: "考勤系统" },
  BUSINESS_TRIP: { label: "出差单", system: "HR 系统" },
  WORK_ORDER: { label: "工单", system: "工单系统" },
  LOCATION_RECORD: { label: "定位记录", system: "定位系统" },
  ACCESS_RECORD: { label: "门禁记录", system: "门禁系统" },
};

/** 契约 `Optional` 字段在生成类型里可能是 `T | null | undefined`，统一放宽 */
type Maybe = string | null | undefined;

export function entityTypeLabel(entityType: Maybe): string {
  if (!entityType) return "未标类型";
  return ENTITY_TYPE_META[entityType]?.label ?? entityType;
}

export function entitySystem(entityType: Maybe): string {
  if (!entityType) return "未知系统";
  return ENTITY_TYPE_META[entityType]?.system ?? "未知系统";
}

/** 关系名映射（**只登记考勤本体里的关系**，其余原样显示） */
export const RELATION_LABEL: Record<string, string> = {
  HAS_POSITION: "任职岗位",
  BELONGS_TO: "所属部门",
  HAS_ATTENDANCE: "有考勤记录",
  OCCURRED_ON: "对应排班",
  ACCUMULATED_OVERTIME: "累计加班",
  ON_BUSINESS_TRIP: "当日出差",
  HANDLED_ORDER: "当日处理工单",
  LOCATED_AT: "定位地点",
  SWIPED_AT: "门禁刷卡",
  GOVERNED_BY: "制度依据",
};

export function relationLabel(relation: string): string {
  return RELATION_LABEL[relation] ?? relation;
}

/** 该跳的来源（`cypher` / `graph` / `document`，三者互斥，已在后端取最高者） */
export const ORIGIN_META: Record<
  string,
  { label: string; hint: string }
> = {
  document: {
    label: "原文命中",
    hint: "终点名字出现在注入 Prompt 的制度原文片段里（最强：可回看原句）",
  },
  graph: {
    label: "本轮子图",
    hint: "这条边就在本轮已检索的子图里（强：答案用到了它）",
  },
  cypher: {
    label: "多跳遍历",
    hint: "由多跳 Cypher 在图上进行确定性遍历得出",
  },
};

export function originMeta(origin: string) {
  return ORIGIN_META[origin] ?? { label: origin, hint: "未知来源" };
}

/** 置信度档位文案（契约 `QueryConfidence` 枚举） */
export const CONFIDENCE_META: Record<string, string> = {
  high: "高置信",
  medium: "中置信",
  low: "低置信",
};

export function confidenceLabel(confidence: Maybe): string {
  if (!confidence) return "—";
  return CONFIDENCE_META[confidence] ?? confidence;
}

/** 拒答原因文案（契约 `RefusalReason` 枚举） */
export const REFUSAL_REASON_META: Record<string, string> = {
  no_grounded_evidence: "无引用支撑的证据（守 F3：宁可拒答，不给凑合答案）",
  out_of_scope: "超出知识库范围",
};

export function refusalReasonLabel(reason: Maybe): string {
  if (!reason) return "—";
  return REFUSAL_REASON_META[reason] ?? reason;
}
