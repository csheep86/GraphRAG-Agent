import type { components } from "@/types/api";

/**
 * 合规预警展示层常量（Sprint 9.5 批次 E4）。
 *
 * 所有**枚举类型一律从契约生成类型取**（`components["schemas"][...]`），
 * 不手写重复定义——手写一份就会走到 L3 那条老路上（契约改了前端不报错）。
 * 契约新增规则值时，下面的 `Record` 会因缺键**编译失败**，这是故意的。
 */

type ComplianceFinding = components["schemas"]["ComplianceFinding"];
type RuleValueItem = components["schemas"]["RuleValueItem"];

export type ComplianceRule = ComplianceFinding["rule"];
export type ComplianceLevel = ComplianceFinding["level"];
export type RuleValueSource = RuleValueItem["source"];

export type ComplianceRuleFilter = ComplianceRule | "all";
export type ComplianceLevelFilter = ComplianceLevel | "all";

type LevelMeta = { label: string; variant: "failed" | "processing" };

/** 风险等级：高=红 · 中=蓝（契约只有这两档，没有 low） */
export const COMPLIANCE_LEVEL_META: Record<ComplianceLevel, LevelMeta> = {
  high: { label: "高", variant: "failed" },
  medium: { label: "中", variant: "processing" },
};

export const COMPLIANCE_LEVEL_OPTIONS: {
  value: ComplianceLevelFilter;
  label: string;
}[] = [
  { value: "all", label: "全部等级" },
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
];

/**
 * 五条规则的中文名与**建议动作**。
 *
 * ⚠️ `label` 只是筛选下拉要用的兜底文案——表格里一律优先用后端返回的
 * `rule_label`（中文名由后端给，避免两端各写一份导致对不上）。
 *
 * ⚠️ `action` 是**前端给出的处置建议，不是制度条款**：契约没有
 * `suggested_action` 字段，后端也不产出它。展示时必须让用户知道这是建议
 * 而非制度原文（UI 上有标注），否则就是在假借制度的权威。
 */
export const COMPLIANCE_RULE_META: Record<
  ComplianceRule,
  { label: string; action: string }
> = {
  weekly_hours_exceeded: {
    label: "周工时超限",
    action: "排班回溯：本周超出部分安排调休或计加班费，并检查下周排班。",
  },
  monthly_overtime_exceeded: {
    label: "月加班超限",
    action: "发薪前核对排班：超出 36h 部分依法支付加班费，次月排班压缩。",
  },
  comp_off_undigested: {
    label: "调休未消化",
    action: "排调休：本季度内安排补休，临期未休的按制度折现。",
  },
  core_window_absence: {
    label: "弹性时段越界",
    action: "与员工确认弹性时段在岗情况，必要时调整岗位工时制。",
  },
  consecutive_attendance: {
    label: "连续出勤无休",
    action: "强制安排休息，并检查该段排班是否已计入加班。",
  },
};

export const COMPLIANCE_RULE_OPTIONS: {
  value: ComplianceRuleFilter;
  label: string;
}[] = [
  { value: "all", label: "全部规则" },
  ...(
    Object.keys(COMPLIANCE_RULE_META) as ComplianceRule[]
  ).map((rule) => ({ value: rule, label: COMPLIANCE_RULE_META[rule].label })),
];

/**
 * 规则值出处（可核查性的关键）。
 *
 * `graph` = 图谱条款节点（M2 抽取），`document` = M1 产物 `full.md` 的第几行。
 * 两者都是**系统内产物**，不是代码旁的静态文件，所以能反查。
 */
export const RULE_VALUE_SOURCE_META: Record<
  RuleValueSource,
  { label: string; hint: string }
> = {
  graph: { label: "图谱条款", hint: "M2 从制度文档抽取的 POLICY_CLAUSE 节点" },
  document: { label: "文档原文", hint: "M1 解析产物 full.md 的对应行" },
};

/**
 * 后端错误码 → 本页文案。
 *
 * 这两个 409 **不是**「没有风险」，是「没法判断」——绝不能渲染成空清单，
 * 否则会被读成"全员合规"（这是合规页最危险的误读）。
 */
export const COMPLIANCE_ERROR_MESSAGE: Record<string, string> = {
  KG_VERSION_NOT_ACTIVE:
    "当前没有 active 的图谱版本，无法扫描。请先完成建图并激活版本。",
  COMPLIANCE_NO_FACTS:
    "该图谱版本内没有考勤事实（员工 / 排班 / 打卡），无法扫描——不是「没有风险」。",
};
