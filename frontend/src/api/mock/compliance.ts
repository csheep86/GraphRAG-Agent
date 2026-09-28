import type { components } from "@/types/api";

type ComplianceScanResponse = components["schemas"]["ComplianceScanResponse"];

/**
 * 合规扫描 Mock（Sprint 9.5 批次 E4）。
 *
 * ⚠️ **这不是编造的数据**：它是 2026-09-28 对真机图谱
 * `kg_version=attendance-demo-v1` 调 `GET /api/v1/attendance/compliance/scan`
 * 的**真实返回**（40 名员工 / 8 条风险 / 7 个规则值），原样照录。
 *
 * 为什么这里**不**沿用 `mock/affiliation.ts` 那套「示例甲 / 示例乙」的假名：
 * 那套做法的目的是让"屏幕上这几条是真的还是假的"一眼可验，前提是疑点页在
 * 关 Mock 后跑的是**客户的真实文档**。合规页不一样——它跑的本来就是
 * `demo/attendance/` 的**仿真语料**（已全程标注「演示语料（仿真）」），
 * 真机与 Mock 同源，不存在"伪造真实客户数据"的风险；反过来，若这里换成
 * 另一套假名字，页面上的 42h / 216h 就和规则值对不上，演示时**算不回去了**。
 *
 * 校验方式：关掉 Mock（`NEXT_PUBLIC_USE_MOCK=false`）后本页返回应与之一致
 * （`as_of` 缺省 = 数据窗口末日 2026-10-31）。
 */
export const MOCK_COMPLIANCE_SCAN: ComplianceScanResponse = {
  kg_version: "attendance-demo-v1",
  as_of: "2026-10-31",
  employee_count: 40,
  rule_values: [
    {
      key: "weekly_hours_cap",
      label: "标准工时制周工时上限",
      value: 40,
      unit: "小时",
      source: "document",
      reference: "doc:worktime-system-rules:L17",
      evidence: "标准工时制下，员工每日工作 8 小时、每周工作 40 小时。",
    },
    {
      key: "monthly_standard_hours",
      label: "月标准工时",
      value: 174,
      unit: "小时",
      source: "graph",
      reference: "clause:ent_c974307a4bd5",
      evidence: "月标准工时为 174 小时 月标准工时 174 小时",
    },
    {
      key: "monthly_overtime_cap",
      label: "月加班上限",
      value: 36,
      unit: "小时",
      source: "graph",
      reference: "clause:ent_d165867ab6e8",
      evidence: "每月加班时间不得超过 36 小时 每月加班时间不得超过 36 小时",
    },
    {
      key: "core_hours_required",
      label: "核心在岗时段时长",
      value: 6,
      unit: "小时",
      source: "document",
      reference: "doc:worktime-system-rules:L45",
      evidence: "第十二条 核心在岗时段为 10:00 至 16:00，员工须在此时段内在岗。",
    },
    {
      key: "core_absence_limit",
      label: "核心时段未在岗次数上限",
      value: 5,
      unit: "次",
      source: "document",
      reference: "doc:overtime-and-comp-off:L39",
      evidence:
        "</td><td><p>弹性时段岗位月度核心时段未在岗超过 5 次</p></td><td><p>中</p",
    },
    {
      key: "consecutive_days_limit",
      label: "连续出勤天数阈值",
      value: 12,
      unit: "天",
      source: "document",
      reference: "doc:overtime-and-comp-off:L39",
      evidence:
        "出勤无休</p></td><td><p>连续出勤达到 12 天</p></td><td><p>中</p",
    },
    {
      key: "comp_off_quarter_remaining_days",
      label: "季度剩余天数（调休临期判据）",
      value: 30,
      unit: "天",
      source: "document",
      reference: "doc:overtime-and-comp-off:L39",
      evidence:
        "累计加班已产生调休额度，已调休为 0 且季度剩余不足 30 天</p></td><td><p>高</p",
    },
  ],
  unresolved: [],
  skipped_rules: [],
  findings: [
    {
      rule: "monthly_overtime_exceeded",
      rule_label: "月加班超限",
      employee_id: "E002",
      employee_name: "李静",
      department: "生产部",
      work_time_system: "综合计算工时制",
      level: "high",
      title: "月加班超限",
      observed: 42,
      threshold: 36,
      unit: "小时",
      calculation: "月排班 216h（22 天）− 月标准 174h = 加班 42h > 上限 36h",
      policy_refs: [
        "graph:clause:ent_c974307a4bd5",
        "graph:clause:ent_d165867ab6e8",
      ],
      evidence: [
        "SHIFT:S00023",
        "SHIFT:S00024",
        "SHIFT:S00025",
        "SHIFT:S00026",
        "SHIFT:S00027",
      ],
    },
    {
      rule: "weekly_hours_exceeded",
      rule_label: "周工时超限",
      employee_id: "E005",
      employee_name: "刘洋",
      department: "研发部",
      work_time_system: "标准工时制",
      level: "high",
      title: "周工时超限",
      observed: 48,
      threshold: 40,
      unit: "小时",
      calculation:
        "2026 年第 42 周实际工时 48h = 6 天累计（2026-10-12 ~ 2026-10-17），制度上限 40h，超出 8h",
      policy_refs: ["document:doc:worktime-system-rules:L17"],
      evidence: [
        "ATTENDANCE_RECORD:A00094",
        "ATTENDANCE_RECORD:A00095",
        "ATTENDANCE_RECORD:A00096",
        "ATTENDANCE_RECORD:A00097",
        "ATTENDANCE_RECORD:A00098",
      ],
    },
    {
      rule: "consecutive_attendance",
      rule_label: "连续出勤无休",
      employee_id: "E002",
      employee_name: "李静",
      department: "生产部",
      work_time_system: "综合计算工时制",
      level: "medium",
      title: "连续出勤无休",
      observed: 22,
      threshold: 12,
      unit: "天",
      calculation: "最长连续出勤 22 天（2026-10-01 ~ 2026-10-22） ≥ 阈值 12 天",
      policy_refs: ["document:doc:overtime-and-comp-off:L39"],
      evidence: [
        "SHIFT:S00023",
        "SHIFT:S00024",
        "SHIFT:S00025",
        "SHIFT:S00026",
        "SHIFT:S00027",
      ],
    },
    {
      rule: "core_window_absence",
      rule_label: "弹性时段越界",
      employee_id: "E003",
      employee_name: "王强",
      department: "研发部",
      work_time_system: "标准工时制",
      level: "medium",
      title: "弹性时段越界",
      observed: 7,
      threshold: 5,
      unit: "次",
      calculation: "核心在岗时段（6h）未在岗 7 次 > 阈值 5 次",
      policy_refs: [
        "document:doc:worktime-system-rules:L45",
        "document:doc:overtime-and-comp-off:L39",
      ],
      evidence: [
        "ATTENDANCE_RECORD:A00046",
        "ATTENDANCE_RECORD:A00049",
        "ATTENDANCE_RECORD:A00051",
        "ATTENDANCE_RECORD:A00054",
        "ATTENDANCE_RECORD:A00056",
      ],
    },
    {
      rule: "comp_off_undigested",
      rule_label: "调休未消化",
      employee_id: "E004",
      employee_name: "陈敏",
      department: "客服部",
      work_time_system: "标准工时制",
      level: "medium",
      title: "调休未消化",
      observed: 22,
      threshold: 0,
      unit: "小时",
      calculation:
        "已产生调休额度 22h，已调休 0h；观察日 2026-10-31，季度剩余 61 天（阈值 30 天）⇒ 未消化、尚未临期",
      policy_refs: ["document:doc:overtime-and-comp-off:L39"],
      evidence: [
        "OVERTIME:OT0001",
        "OVERTIME:OT0002",
        "OVERTIME:OT0003",
        "OVERTIME:OT0004",
      ],
    },
    {
      rule: "comp_off_undigested",
      rule_label: "调休未消化",
      employee_id: "E026",
      employee_name: "韩磊",
      department: "研发部",
      work_time_system: "标准工时制",
      level: "medium",
      title: "调休未消化",
      observed: 2,
      threshold: 0,
      unit: "小时",
      calculation:
        "已产生调休额度 2h，已调休 0h；观察日 2026-10-31，季度剩余 61 天（阈值 30 天）⇒ 未消化、尚未临期",
      policy_refs: ["document:doc:overtime-and-comp-off:L39"],
      evidence: ["OVERTIME:OT0005"],
    },
    {
      rule: "comp_off_undigested",
      rule_label: "调休未消化",
      employee_id: "E035",
      employee_name: "潘婷",
      department: "客服部",
      work_time_system: "标准工时制",
      level: "medium",
      title: "调休未消化",
      observed: 4,
      threshold: 0,
      unit: "小时",
      calculation:
        "已产生调休额度 4h，已调休 0h；观察日 2026-10-31，季度剩余 61 天（阈值 30 天）⇒ 未消化、尚未临期",
      policy_refs: ["document:doc:overtime-and-comp-off:L39"],
      evidence: ["OVERTIME:OT0019"],
    },
    {
      rule: "comp_off_undigested",
      rule_label: "调休未消化",
      employee_id: "E038",
      employee_name: "余波",
      department: "行政部",
      work_time_system: "标准工时制",
      level: "medium",
      title: "调休未消化",
      observed: 3,
      threshold: 0,
      unit: "小时",
      calculation:
        "已产生调休额度 3h，已调休 0h；观察日 2026-10-31，季度剩余 61 天（阈值 30 天）⇒ 未消化、尚未临期",
      policy_refs: ["document:doc:overtime-and-comp-off:L39"],
      evidence: ["OVERTIME:OT0022"],
    },
  ],
  total: 8,
  trace_id: "3c671c5d-9c2c-4a02-aca7-92f9d5844f3a",
};
