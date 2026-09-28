/**
 * 异常归因展示层常量（Sprint 9.5 批次 E3）。
 *
 * 这批映射**只是展示文案**：归因的权重与置信度一律来自后端
 * （确定性加权，禁止 LLM 生成），前端不参与任何计算、也不重排顺序
 * ——顺序由后端 `causes[]` 给出，前端照序渲染。
 */

/** 证据的**来源系统**：演示「跨四个系统取证」的关键一列 */
export const CAUSE_SYSTEM_META: Record<
  string,
  { label: string; system: string }
> = {
  trip_approved: { label: "出差审批", system: "HR 系统" },
  order_closed: { label: "工单闭环", system: "工单系统" },
  location_match: { label: "定位一致", system: "定位系统" },
  access_contrast: { label: "门禁对比", system: "门禁系统" },
};

/** 未登记的 code 不臆造中文名：原样显示 code，宁可露出编码也不猜 */
export function causeLabel(code: string): string {
  return CAUSE_SYSTEM_META[code]?.label ?? code;
}

export function causeSystem(code: string): string {
  return CAUSE_SYSTEM_META[code]?.system ?? "未知系统";
}

/** 异常状态文案（契约 `status` / `anomaly_type`） */
export const ANOMALY_STATUS_LABEL: Record<string, string> = {
  absent: "缺勤",
  missing_check_in: "缺卡",
};

export function anomalyStatusLabel(status: string): string {
  return ANOMALY_STATUS_LABEL[status] ?? status;
}

/**
 * 置信度分档（阈值与后端一致：≥0.80 成立 / ≥0.50 需复核 / 其余不成立）。
 *
 * **这两个数字必须与 `rules/attribution.py` 的 `CONFIDENCE_ACCEPT` /
 * `CONFIDENCE_REVIEW` 对齐**——后端没把它们放进契约（它们是阈值而非接口字段），
 * 所以这里手写一份并注明出处；改后端阈值时这里是唯一要同步的地方。
 */
export const CONFIDENCE_ACCEPT = 0.8;
export const CONFIDENCE_REVIEW = 0.5;

export type ConfidenceTone = "ok" | "warn" | "bad";

export function confidenceTone(confidence: number): ConfidenceTone {
  if (confidence >= CONFIDENCE_ACCEPT) return "ok";
  if (confidence >= CONFIDENCE_REVIEW) return "warn";
  return "bad";
}

export const CONFIDENCE_TONE_CLASS: Record<ConfidenceTone, string> = {
  ok: "bg-status-completed",
  warn: "bg-status-processing",
  bad: "bg-status-failed",
};

export const CONFIDENCE_TONE_TEXT: Record<ConfidenceTone, string> = {
  ok: "text-status-completed",
  warn: "text-status-processing",
  bad: "text-status-failed",
};

/** 归因错误码文案（与合规页同一套口径：不把失败渲染成"没问题"） */
export const ATTRIBUTION_ERROR_MESSAGE: Record<string, string> = {
  NOT_FOUND: "该员工在当前图谱版本内没有这条异常记录（不是「不成立」）。",
  KG_VERSION_NOT_ACTIVE:
    "当前没有 active 的图谱版本，无法归因。请先完成建图并激活版本。",
};
