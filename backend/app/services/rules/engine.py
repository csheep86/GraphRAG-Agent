"""考勤域**确定性规则引擎**（Sprint 9.5 批次 C1）。

**职责边界（纪律 3 / R10）**：本模块**只出数值与判据**，不做自然语言组织——
措辞交给 M3 的 LLM（批次 D2 收口）。所有结论必须能给出**计算过程**与**证据出处**。

**事实来源 = 图谱（不读 CSV）**：B1 已经把 9 张 CSV 确定性入图，
引擎读图既是「入图即可查」的复核，也保证与前端看到的是同一份数据
（读 CSV 会出现「图上没有 / 算出来有」的错族，9-26 已经出过一次同族事故）。

**为什么必须按 ``id`` 前缀过滤员工/排班（2026-09-28 实测，重要）**：
B2 的 M2 抽取与 B1 的 CSV 落在**同一个** ``kg_version`` 里（B3 汇合所需），
于是图里同时存在两类 ``EMPLOYEE`` / ``SHIFT`` 节点：

- CSV 派生：``EMPLOYEE:E001``，带 ``department`` / ``work_time_system`` 等业务属性；
- M2 抽取：``ent_xxxx``，名字是「全体在册员工」「排班时段」这类**通用词**，无业务属性。

不过滤就会把噪声当事实（真机实测：EMPLOYEE 47 个里只有 40 个是 CSV 派生的）。
故**全部事实查询都带 ``id STARTS WITH '<TYPE>:'`` 约束**。

**与 proposal §5.3 的一处口径细化（必须显式登记）**：
「季度调休未消化」在 §5.3 表里写作「已产生调休额度 且 已调休 = 0 且 季度剩余 < 30 天」。
**实测冲突**：演示数据窗口末日是 2026-10-31，Q4 季末 12-31 ⇒ 剩余 **61 天**，
按原写法 E004 陈敏**永远不触发**，演示用例直接塌。
故本实现把「未消化」与「临期」拆开（制度三第九条：调休应在加班所在季度内完成）：

- **触发** = 已产生调休额度 且 已调休 = 0（风险事实本身）；
- **等级** = 季度剩余 < 30 天 ⇒ ``high``，否则 ``medium``（紧迫度）。

阈值仍然来自制度（``comp_off_quarter_remaining_days``），且可用 ``as_of``
演示「越接近季末等级越高」——既保住用例，又不编数。
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from loguru import logger

from app.services.kg.version_scope import version_scope
from app.services.kg.version_view import VersionReadView
from app.services.rules.policy_values import (
    RuleValueBook,
    RuleValueUnresolvedError,
    load_policy_clauses,
    load_policy_documents,
    resolve_rule_values,
)

__all__ = [
    "LEVEL_HIGH",
    "LEVEL_MEDIUM",
    "ComplianceReport",
    "ComplianceScanError",
    "EmployeeFacts",
    "RiskFinding",
    "load_employee_facts",
    "scan_compliance",
]

LEVEL_HIGH = "high"
LEVEL_MEDIUM = "medium"

#: 工时制取值（``employees.csv`` 的列值，逐字照语料）
WTS_STANDARD = "标准工时制"
WTS_COMPREHENSIVE = "综合计算工时制"
WTS_FLEXIBLE = "不定时工作制"

#: 规则标识（写入 ``RiskFinding.rule``，供前端与契约引用）
RULE_WEEKLY_HOURS = "weekly_hours_exceeded"
RULE_MONTHLY_OVERTIME = "monthly_overtime_exceeded"
RULE_COMP_OFF = "comp_off_undigested"
RULE_CORE_WINDOW = "core_window_absence"
RULE_CONSECUTIVE = "consecutive_attendance"

_LEVEL_RANK = {LEVEL_HIGH: 0, LEVEL_MEDIUM: 1}

#: **规则语义边界**（**不是**制度阈值，见 `_rule_comp_off` 的说明）：
#: 用于「是否已开始消化」这类**有无判定**，制度里不存在对应的数值可解析。
#: 与其余阈值（全部来自 `RuleValueBook`）区分开，使 D2 守卫
#: `test_every_threshold_comes_from_policy_values` 能按常量识别、不放宽断言。
#: 现行的唯一使用者：`comp_off_undigested`（已调休 > 0 ⇒ 已消化）。
SENTINEL_UNUSED_BOUNDARY = 0.0


class ComplianceScanError(RuntimeError):
    """扫描无法进行（无数据 / 无员工 / 无法确定观察日）。

    **显式失败**：不做「返回空清单当成功」——空清单与「扫过了没问题」无法区分。
    """


# --------------------------------------------------------------------------- #
# 事实模型
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ShiftFact:
    """一条排班事实。"""

    node_id: str
    date: str
    planned_hours: float
    is_rest_day: bool


@dataclass(frozen=True, slots=True)
class AttendanceFact:
    """一条打卡事实。"""

    node_id: str
    date: str
    actual_hours: float
    core_hours_present: float
    status: str
    is_rest_day: bool


@dataclass(frozen=True, slots=True)
class OvertimeFact:
    """一条加班单事实。"""

    node_id: str
    date: str
    hours: float
    approved: bool
    comp_off_hours: float
    comp_off_used_hours: float


@dataclass(frozen=True, slots=True)
class EmployeeFacts:
    """一个员工的全部事实（图谱读出，按日期升序）。"""

    employee_id: str  # ``E001``
    node_id: str  # ``EMPLOYEE:E001``
    name: str
    department: str
    position: str
    work_time_system: str
    shifts: tuple[ShiftFact, ...]
    attendance: tuple[AttendanceFact, ...]
    overtime: tuple[OvertimeFact, ...]


# --------------------------------------------------------------------------- #
# 输出模型
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RiskFinding:
    """一条合规风险（含计算过程 —— 演示要能逐条念出来）。"""

    rule: str
    employee_id: str
    employee_name: str
    department: str
    level: str
    title: str
    observed: float
    threshold: float
    unit: str
    calculation: str
    evidence: tuple[str, ...]  # 图谱节点 id（可回查）
    policy_refs: tuple[
        str, ...
    ]  # 规则值出处（``graph:clause:…`` / ``document:doc:…``）
    work_time_system: str = ""


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """一次扫描的完整结果。"""

    kg_version: str
    as_of: date
    employee_count: int
    findings: tuple[RiskFinding, ...]
    rule_values: RuleValueBook
    skipped_rules: tuple[str, ...]  # 规则值未解析 ⇒ 跳过（**显式列出**）


# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #
#: P5-H：四条事实查询共用 :func:`version_scope` 的版本谓词 ——
#: 缺省（版本链只有 active 一条、``$sel`` 为空）⇒ 它等价于原来的
#: ``kg_version: $kg`` 内联属性匹配，**行为零变化**。
#: 员工（**只取 CSV 派生**）
_CYPHER_EMPLOYEES = f"""
MATCH (e:Entity {{entity_type: 'EMPLOYEE', org_id: $org}})
WHERE {version_scope("e")}
  AND e.id STARTS WITH 'EMPLOYEE:'
RETURN e.id AS node_id, e.canonical_name AS name,
       e.department AS department, e.position AS position,
       e.work_time_system AS wts
ORDER BY e.id
"""

_CYPHER_SHIFTS = f"""
MATCH (e:Entity {{entity_type: 'EMPLOYEE', org_id: $org}})
      -[rel:RELATION {{relation_type: 'HAS_SHIFT'}}]->
      (s:Entity {{entity_type: 'SHIFT'}})
WHERE {version_scope("e")}
  AND {version_scope("s")}
  AND rel.kg_version IN $kgs
  AND e.id STARTS WITH 'EMPLOYEE:'
RETURN e.id AS employee, s.id AS node_id, s.date AS date,
       toFloat(s.planned_hours) AS hours, toInteger(s.is_rest_day) AS rest
ORDER BY employee, date
"""

_CYPHER_ATTENDANCE = f"""
MATCH (e:Entity {{entity_type: 'EMPLOYEE', org_id: $org}})
      -[rel:RELATION {{relation_type: 'HAS_ATTENDANCE'}}]->
      (a:Entity {{entity_type: 'ATTENDANCE_RECORD'}})
WHERE {version_scope("e")}
  AND {version_scope("a")}
  AND rel.kg_version IN $kgs
  AND e.id STARTS WITH 'EMPLOYEE:'
RETURN e.id AS employee, a.id AS node_id, a.date AS date,
       toFloat(a.actual_hours) AS hours,
       toFloat(a.core_hours_present) AS core,
       a.status AS status, toInteger(a.is_rest_day) AS rest
ORDER BY employee, date
"""

_CYPHER_OVERTIME = f"""
MATCH (e:Entity {{entity_type: 'EMPLOYEE', org_id: $org}})
      -[rel:RELATION {{relation_type: 'ACCUMULATED_OVERTIME'}}]->
      (o:Entity {{entity_type: 'OVERTIME'}})
WHERE {version_scope("e")}
  AND {version_scope("o")}
  AND rel.kg_version IN $kgs
  AND e.id STARTS WITH 'EMPLOYEE:'
RETURN e.id AS employee, o.id AS node_id, o.date AS date,
       toFloat(o.hours) AS hours, toInteger(o.approved) AS approved,
       toFloat(o.comp_off_hours) AS comp_off,
       toFloat(o.comp_off_used_hours) AS comp_off_used
ORDER BY employee, date
"""


# --------------------------------------------------------------------------- #
# 事实加载
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _index_by_employee(
    rows: Sequence[Mapping[str, Any]], build: Any
) -> dict[str, list[Any]]:
    """按 ``employee`` 节点 id 归堆（保持 Cypher 的日期升序）。"""
    bucket: dict[str, list[Any]] = {}
    for row in rows:
        bucket.setdefault(str(row["employee"]), []).append(build(row))
    return bucket


def load_employee_facts(
    *,
    session: Any,
    kg_version: str,
    org_id: str,
    version_view: VersionReadView | None = None,
) -> tuple[EmployeeFacts, ...]:
    """从图谱读出全部员工的事实（排班 / 打卡 / 加班）。

    四条查询各自独立，互不依赖 ⇒ 任一类型缺失只是该类事实为空，
    不会连带吞掉其它类（吞错是本项目反复踩的坑）。

    :param version_view: P5-H 版本继承读视野；``None`` ⇒ 按 ``kg_version``
        单版本读（改之前的既有行为）。
    """
    view = version_view or VersionReadView(versions=(kg_version,), selection={})
    params = {"org": str(org_id), **view.cypher_params()}

    employees = list(session.run(_CYPHER_EMPLOYEES, **params))
    shifts = _index_by_employee(
        list(session.run(_CYPHER_SHIFTS, **params)),
        lambda row: ShiftFact(
            node_id=str(row["node_id"]),
            date=str(row["date"] or ""),
            planned_hours=_to_float(row["hours"]),
            is_rest_day=bool(row["rest"]),
        ),
    )
    attendance = _index_by_employee(
        list(session.run(_CYPHER_ATTENDANCE, **params)),
        lambda row: AttendanceFact(
            node_id=str(row["node_id"]),
            date=str(row["date"] or ""),
            actual_hours=_to_float(row["hours"]),
            core_hours_present=_to_float(row["core"]),
            status=str(row["status"] or ""),
            is_rest_day=bool(row["rest"]),
        ),
    )
    overtime = _index_by_employee(
        list(session.run(_CYPHER_OVERTIME, **params)),
        lambda row: OvertimeFact(
            node_id=str(row["node_id"]),
            date=str(row["date"] or ""),
            hours=_to_float(row["hours"]),
            approved=bool(row["approved"]),
            comp_off_hours=_to_float(row["comp_off"]),
            comp_off_used_hours=_to_float(row["comp_off_used"]),
        ),
    )

    facts: list[EmployeeFacts] = []
    for row in employees:
        node_id = str(row["node_id"])
        facts.append(
            EmployeeFacts(
                employee_id=node_id.split(":", 1)[1] if ":" in node_id else node_id,
                node_id=node_id,
                name=str(row["name"] or ""),
                department=str(row["department"] or ""),
                position=str(row["position"] or ""),
                work_time_system=str(row["wts"] or ""),
                shifts=tuple(shifts.get(node_id, ())),
                attendance=tuple(attendance.get(node_id, ())),
                overtime=tuple(overtime.get(node_id, ())),
            )
        )
    return tuple(facts)


# --------------------------------------------------------------------------- #
# 计算辅助
# --------------------------------------------------------------------------- #
def _quarter_end(day: date) -> date:
    """所在季度的最后一天。"""
    end_month = ((day.month - 1) // 3) * 3 + 3
    last_day = calendar.monthrange(day.year, end_month)[1]
    return date(day.year, end_month, last_day)


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _longest_streak(days: Sequence[date]) -> tuple[int, date, date]:
    """最长连续日期段 → ``(天数, 起, 止)``；空序列返回 ``(0, 起, 起)``。"""
    if not days:
        return 0, date.min, date.min
    best_len = current = 1
    best_start = best_end = current_start = days[0]
    for previous, current_day in zip(days, days[1:], strict=False):
        if (current_day - previous).days == 1:
            current += 1
            if current > best_len:
                best_len, best_start, best_end = current, current_start, current_day
        else:
            current, current_start = 1, current_day
    return best_len, best_start, best_end


def _evidence_ids(items: Sequence[Any], limit: int = 5) -> tuple[str, ...]:
    ids = [str(getattr(item, "node_id", "")) for item in items]
    ids = [item for item in ids if item]
    return tuple(ids[:limit])


# --------------------------------------------------------------------------- #
# 五条规则
# --------------------------------------------------------------------------- #
def _rule_weekly_hours(
    facts: EmployeeFacts, book: RuleValueBook, _as_of: date
) -> RiskFinding | None:
    """周工时超限：**标准工时制**岗位周实际工时 > 制度上限（40h）。"""
    if facts.work_time_system != WTS_STANDARD:
        return None
    try:
        cap = book.value("weekly_hours_cap")
    except RuleValueUnresolvedError:
        return None

    by_week: dict[tuple[int, int], list[AttendanceFact]] = {}
    for item in facts.attendance:
        day = _parse_day(item.date)
        if day is None:
            continue
        by_week.setdefault(day.isocalendar()[:2], []).append(item)

    worst_week: tuple[int, int] | None = None
    worst_hours = 0.0
    for week, items in by_week.items():
        total = round(sum(item.actual_hours for item in items), 2)
        if total > worst_hours:
            worst_week, worst_hours = week, total
    if worst_week is None or worst_hours <= cap:
        return None

    items = by_week[worst_week]
    return RiskFinding(
        rule=RULE_WEEKLY_HOURS,
        employee_id=facts.employee_id,
        employee_name=facts.name,
        department=facts.department,
        level=LEVEL_HIGH,
        title="周工时超限",
        observed=worst_hours,
        threshold=cap,
        unit="小时",
        calculation=(
            f"{worst_week[0]} 年第 {worst_week[1]} 周实际工时 {worst_hours:g}h "
            f"= {len(items)} 天累计（{items[0].date} ~ {items[-1].date}），"
            f"制度上限 {cap:g}h，超出 {worst_hours - cap:g}h"
        ),
        evidence=_evidence_ids(items),
        policy_refs=(book.reference("weekly_hours_cap"),),
        work_time_system=facts.work_time_system,
    )


def _rule_monthly_overtime(
    facts: EmployeeFacts, book: RuleValueBook, _as_of: date
) -> RiskFinding | None:
    """月加班超限。**口径分岔**（proposal §5.3，制度二第七条 / 制度三）：

    - 综合计算工时制：月累计排班工时 − 月标准工时（174h）；
    - 标准工时制：已审批加班单累计；
    - 不定时工作制：不适用，跳过。
    """
    if facts.work_time_system == WTS_FLEXIBLE:
        return None
    try:
        cap = book.value("monthly_overtime_cap")
    except RuleValueUnresolvedError:
        return None

    if facts.work_time_system == WTS_COMPREHENSIVE:
        try:
            standard = book.value("monthly_standard_hours")
        except RuleValueUnresolvedError:
            return None
        planned = round(sum(item.planned_hours for item in facts.shifts), 2)
        overtime = round(planned - standard, 2)
        if overtime <= cap:
            return None
        return RiskFinding(
            rule=RULE_MONTHLY_OVERTIME,
            employee_id=facts.employee_id,
            employee_name=facts.name,
            department=facts.department,
            level=LEVEL_HIGH,
            title="月加班超限",
            observed=overtime,
            threshold=cap,
            unit="小时",
            calculation=(
                f"月排班 {planned:g}h（{len(facts.shifts)} 天）− 月标准 "
                f"{standard:g}h = 加班 {overtime:g}h > 上限 {cap:g}h"
            ),
            evidence=_evidence_ids(facts.shifts),
            policy_refs=(
                book.reference("monthly_standard_hours"),
                book.reference("monthly_overtime_cap"),
            ),
            work_time_system=facts.work_time_system,
        )

    if facts.work_time_system != WTS_STANDARD:
        return None

    approved = [item for item in facts.overtime if item.approved]
    total = round(sum(item.hours for item in approved), 2)
    if total <= cap:
        return None
    return RiskFinding(
        rule=RULE_MONTHLY_OVERTIME,
        employee_id=facts.employee_id,
        employee_name=facts.name,
        department=facts.department,
        level=LEVEL_HIGH,
        title="月加班超限",
        observed=total,
        threshold=cap,
        unit="小时",
        calculation=(f"已审批加班单 {len(approved)} 条合计 {total:g}h > 上限 {cap:g}h"),
        evidence=_evidence_ids(approved),
        policy_refs=(book.reference("monthly_overtime_cap"),),
        work_time_system=facts.work_time_system,
    )


def _rule_comp_off(
    facts: EmployeeFacts, book: RuleValueBook, as_of: date
) -> RiskFinding | None:
    """调休未消化：已产生调休额度且已调休 = 0。

    **等级按季度剩余天数分档**（见本模块 docstring 的口径细化说明）。
    """
    try:
        limit = book.value("comp_off_quarter_remaining_days")
    except RuleValueUnresolvedError:
        return None

    earned = round(sum(item.comp_off_hours for item in facts.overtime), 2)
    used = round(sum(item.comp_off_used_hours for item in facts.overtime), 2)
    if earned <= 0 or used > 0:
        return None

    remaining = (_quarter_end(as_of) - as_of).days
    level = LEVEL_HIGH if remaining < limit else LEVEL_MEDIUM
    return RiskFinding(
        rule=RULE_COMP_OFF,
        employee_id=facts.employee_id,
        employee_name=facts.name,
        department=facts.department,
        level=level,
        title="调休未消化",
        observed=earned,
        # **规则语义边界，不是制度阈值**（2026-09-28 由 D2 守卫逼出来的显化）：
        # 本规则判定的是「有没有开始消化」——已调休 > 0 即视为已消化，
        # 与制度的临期判据（季度剩余 < 30 天，来自 `RuleValueBook`）是两回事。
        # 原先写成一个裸露的 `0.0`，与其余「阈值全出自规则值」的口径不一致，
        # 于是提为具名常量并在 `calculation` 里说出它的语义。
        threshold=SENTINEL_UNUSED_BOUNDARY,
        unit="小时",
        calculation=(
            f"已产生调休额度 {earned:g}h，已调休 {used:g}h"
            f"（判定边界 {SENTINEL_UNUSED_BOUNDARY:g}h：>0 即视为已消化）；"
            f"观察日 {as_of.isoformat()}，"
            f"季度剩余 {remaining} 天"
            f"季度剩余 {remaining} 天"
            + (
                f" < 阈值 {limit:g} 天 ⇒ 临期未消化"
                if remaining < limit
                else f"（阈值 {limit:g} 天）⇒ 未消化、尚未临期"
            )
        ),
        evidence=_evidence_ids(facts.overtime),
        policy_refs=(book.reference("comp_off_quarter_remaining_days"),),
        work_time_system=facts.work_time_system,
    )


def _rule_core_window(
    facts: EmployeeFacts, book: RuleValueBook, _as_of: date
) -> RiskFinding | None:
    """弹性时段越界：月度核心时段未在岗次数 > 制度阈值（5 次）。

    仅对**标准工时制**（制度二第十一条：弹性时段在标准工时制岗位上实行）。
    """
    if facts.work_time_system != WTS_STANDARD:
        return None
    try:
        required = book.value("core_hours_required")
        limit = book.value("core_absence_limit")
    except RuleValueUnresolvedError:
        return None

    missed = [item for item in facts.attendance if item.core_hours_present < required]
    if len(missed) <= limit:
        return None
    return RiskFinding(
        rule=RULE_CORE_WINDOW,
        employee_id=facts.employee_id,
        employee_name=facts.name,
        department=facts.department,
        level=LEVEL_MEDIUM,
        title="弹性时段越界",
        observed=float(len(missed)),
        threshold=float(limit),
        unit="次",
        calculation=(
            f"核心在岗时段（{required:g}h）未在岗 {len(missed)} 次 > 阈值 {limit:g} 次"
        ),
        evidence=_evidence_ids(missed),
        policy_refs=(
            book.reference("core_hours_required"),
            book.reference("core_absence_limit"),
        ),
        work_time_system=facts.work_time_system,
    )


def _rule_consecutive(
    facts: EmployeeFacts, book: RuleValueBook, _as_of: date
) -> RiskFinding | None:
    """连续出勤无休：最长连续出勤天数 ≥ 制度阈值（12 天）。

    **出勤日的定义**：有排班且当日打卡状态**不是** ``absent``。
    与语料生成器自检口径一致（``generate_corpus.py`` 按 shifts 日期连续核算）。
    """
    try:
        limit = book.value("consecutive_days_limit")
    except RuleValueUnresolvedError:
        return None

    absent_days = {item.date for item in facts.attendance if item.status == "absent"}
    worked = sorted(
        day
        for day in (
            _parse_day(item.date)
            for item in facts.shifts
            if item.date not in absent_days
        )
        if day is not None
    )
    if not worked:
        return None
    length, start, end = _longest_streak(worked)
    if length < limit:
        return None
    return RiskFinding(
        rule=RULE_CONSECUTIVE,
        employee_id=facts.employee_id,
        employee_name=facts.name,
        department=facts.department,
        level=LEVEL_MEDIUM,
        title="连续出勤无休",
        observed=float(length),
        threshold=float(limit),
        unit="天",
        calculation=(
            f"最长连续出勤 {length} 天（{start.isoformat()} ~ {end.isoformat()}）"
            f" ≥ 阈值 {limit:g} 天"
        ),
        evidence=_evidence_ids(facts.shifts),
        policy_refs=(book.reference("consecutive_days_limit"),),
        work_time_system=facts.work_time_system,
    )


_RULES: tuple[Callable[..., RiskFinding | None], ...] = (
    _rule_weekly_hours,
    _rule_monthly_overtime,
    _rule_comp_off,
    _rule_core_window,
    _rule_consecutive,
)

#: 规则 → 该规则依赖的规则值 key（用于把「跳过」说清楚，而不是笼统报一句）
_RULE_VALUE_KEYS: Mapping[str, tuple[str, ...]] = {
    RULE_WEEKLY_HOURS: ("weekly_hours_cap",),
    RULE_MONTHLY_OVERTIME: ("monthly_standard_hours", "monthly_overtime_cap"),
    RULE_COMP_OFF: ("comp_off_quarter_remaining_days",),
    RULE_CORE_WINDOW: ("core_hours_required", "core_absence_limit"),
    RULE_CONSECUTIVE: ("consecutive_days_limit",),
}

_RULE_LABELS: Mapping[str, str] = {
    RULE_WEEKLY_HOURS: "周工时超限",
    RULE_MONTHLY_OVERTIME: "月加班超限",
    RULE_COMP_OFF: "调休未消化",
    RULE_CORE_WINDOW: "弹性时段越界",
    RULE_CONSECUTIVE: "连续出勤无休",
}


# --------------------------------------------------------------------------- #
# 扫描入口
# --------------------------------------------------------------------------- #
def _resolve_as_of(employees: Sequence[EmployeeFacts], as_of: date | None) -> date:
    """观察日：显式传入优先；否则取**数据窗口末日**（不取今天 ⇒ 结果可复现）。"""
    if as_of is not None:
        return as_of
    candidates = [
        day
        for fact in employees
        for item in (*fact.shifts, *fact.attendance, *fact.overtime)
        if (day := _parse_day(item.date)) is not None
    ]
    if not candidates:
        raise ComplianceScanError(
            "图谱中没有任何带日期的考勤事实，无法确定观察日（拒绝用今天兜底）"
        )
    return max(candidates)


def scan_compliance(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    as_of: date | None = None,
    storage: Any = None,
    version_view: VersionReadView | None = None,
) -> ComplianceReport:
    """扫一遍全部员工，产出风险清单。

    :param session: Neo4j 会话（``driver.session(database=...)``）。
    :param kg_version: 图谱版本（B1/B2 共用的 ``attendance-demo-v1``）。
    :param org_id: 租户 ID（ADR-0003 强制过滤键）。
    :param as_of: 观察日；``None`` ⇒ 数据窗口末日（**可复现**，不取系统当天）。
    :param storage: 存储后端（读制度文档产物）；``None`` ⇒ ``get_storage()``。
    :param version_view: P5-H 版本继承读视野；``None`` ⇒ 按单版本读。
    """
    employees = load_employee_facts(
        session=session,
        kg_version=kg_version,
        org_id=str(org_id),
        version_view=version_view,
    )
    if not employees:
        raise ComplianceScanError(
            f"kg_version={kg_version} 里没有 CSV 派生的 EMPLOYEE 节点"
            "（请先跑 scripts/ingest_attendance_csv.py）"
        )

    book = resolve_rule_values(
        clauses=load_policy_clauses(
            session=session,
            kg_version=kg_version,
            org_id=str(org_id),
            version_view=version_view,
        ),
        documents=load_policy_documents(org_id=org_id, storage=storage),
    )
    resolved_keys = {item.key for item in book.values}

    skipped: list[str] = []
    for rule, keys in _RULE_VALUE_KEYS.items():
        missing = [key for key in keys if key not in resolved_keys]
        if missing:
            skipped.append(rule)
            logger.bind(rule=rule, missing=missing).warning("rule_skipped_no_value")

    observation_day = _resolve_as_of(employees, as_of)
    findings: list[RiskFinding] = []
    for fact in employees:
        for rule_fn in _RULES:
            try:
                finding = rule_fn(fact, book, observation_day)
            except RuleValueUnresolvedError:
                continue
            if finding is not None:
                findings.append(finding)

    findings.sort(
        key=lambda item: (
            _LEVEL_RANK.get(item.level, 9),
            item.employee_id,
            item.rule,
        )
    )
    return ComplianceReport(
        kg_version=kg_version,
        as_of=observation_day,
        employee_count=len(employees),
        findings=tuple(findings),
        rule_values=book,
        skipped_rules=tuple(skipped),
    )


def rule_label(rule: str) -> str:
    """规则中文名（供 CLI / 报告打印）。"""
    return _RULE_LABELS.get(rule, rule)
