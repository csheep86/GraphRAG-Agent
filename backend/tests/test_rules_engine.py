"""考勤域规则引擎单测（Sprint 9.5 批次 C1）。

**为什么单测（而不是只跑脚本）**：引擎的输出是**会被写进交付口径的数值**
（36h / 42h / 22 天…）。这类数值一旦因重构错位（例如把「综合制」的口径误用到
「标准制」上），脚本只会打印一个看起来合理的数 —— 必须有断言把它钉死。

**不连真机 Neo4j**：事实加载用假 session（只校验查询接线，不校验数据），
规则计算用手工构造的 :class:`EmployeeFacts` —— 两者职责分开，跑得快且可控。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.rules import (
    LEVEL_HIGH,
    LEVEL_MEDIUM,
    ComplianceScanError,
    RuleValueUnresolvedError,
    scan_compliance,
)
from app.services.rules.engine import (
    AttendanceFact,
    EmployeeFacts,
    OvertimeFact,
    ShiftFact,
    _longest_streak,
    _quarter_end,
    _rule_comp_off,
    _rule_consecutive,
    _rule_core_window,
    _rule_monthly_overtime,
    _rule_weekly_hours,
    load_employee_facts,
)
from app.services.rules.policy_values import (
    RuleValueBook,
    load_policy_clauses,
    resolve_rule_values,
)


# --------------------------------------------------------------------------- #
# 规则值
# --------------------------------------------------------------------------- #
def _book(**values: float) -> RuleValueBook:
    """用 ``key=value`` 快速造一本规则值（出处统一标注为 test）。"""
    from app.services.rules.policy_values import RuleValue

    return RuleValueBook(
        values=tuple(
            RuleValue(
                key=key,
                label=key,
                value=value,
                unit="",
                source="test",
                reference="test",
                evidence="test",
            )
            for key, value in values.items()
        )
    )


def test_resolve_prefers_graph_clause_over_document() -> None:
    """图谱条款优先于文档产物（同源数值以图谱为准，出处可核查）。"""
    from app.services.rules.policy_values import _TextSegment

    book = resolve_rule_values(
        clauses=(
            _TextSegment(
                text="每月加班时间不得超过36小时",
                source="graph",
                reference="clause:ent_1",
                order=("ent_1", 0),
            ),
        ),
        documents=(
            _TextSegment(
                text="第四条 每月加班时间不得超过 99 小时。",
                source="document",
                reference="doc:x:L1",
                order=("x", 1),
            ),
        ),
    )
    assert book.value("monthly_overtime_cap") == 36.0
    assert book.by_key["monthly_overtime_cap"].source == "graph"


def test_resolve_core_hours_from_window_text() -> None:
    """核心在岗时长由「10:00 至 16:00」算出 6h（不是硬编码）。"""
    from app.services.rules.policy_values import _TextSegment

    book = resolve_rule_values(
        documents=(
            _TextSegment(
                text="第十二条 核心在岗时段为 10:00 至 16:00，员工须在此时段内在岗。",
                source="document",
                reference="doc:x:L45",
                order=("x", 45),
            ),
        )
    )
    assert book.value("core_hours_required") == 6.0


def test_unresolved_value_raises_and_is_listed() -> None:
    """解析不到即 unresolved：**取数抛错**（不静默给默认值）。"""
    book = resolve_rule_values()
    assert set(book.unresolved) >= {"weekly_hours_cap", "monthly_standard_hours"}
    with pytest.raises(RuleValueUnresolvedError):
        book.value("weekly_hours_cap")


def test_missing_rule_value_disables_rule_not_crash() -> None:
    """规则值缺失 ⇒ 该规则**跳过**（返回 None），不影响其它规则。"""
    facts = _employee("E002", "综合计算工时制")
    assert _rule_monthly_overtime(facts, _book(), date(2026, 10, 31)) is None


# --------------------------------------------------------------------------- #
# 事实构造
# --------------------------------------------------------------------------- #
def _employee(
    employee_id: str,
    work_time_system: str,
    *,
    shifts: tuple[ShiftFact, ...] = (),
    attendance: tuple[AttendanceFact, ...] = (),
    overtime: tuple[OvertimeFact, ...] = (),
) -> EmployeeFacts:
    return EmployeeFacts(
        employee_id=employee_id,
        node_id=f"EMPLOYEE:{employee_id}",
        name="测试员工",
        department="测试部",
        position="测试岗",
        work_time_system=work_time_system,
        shifts=shifts,
        attendance=attendance,
        overtime=overtime,
    )


def _attendance(
    days: int, hours: float = 8.0, core: float = 6.0, status: str = "normal"
) -> tuple[AttendanceFact, ...]:
    return tuple(
        AttendanceFact(
            node_id=f"ATTENDANCE_RECORD:A{i:05d}",
            date=date(2026, 10, 5 + i).isoformat(),
            actual_hours=hours,
            core_hours_present=core,
            status=status,
            is_rest_day=False,
        )
        for i in range(days)
    )


# --------------------------------------------------------------------------- #
# 计算辅助
# --------------------------------------------------------------------------- #
def test_longest_streak_and_quarter_end() -> None:
    days = [date(2026, 10, d) for d in (1, 2, 3, 5, 6)]
    assert _longest_streak(days)[0] == 3
    assert _quarter_end(date(2026, 10, 31)) == date(2026, 12, 31)
    assert _quarter_end(date(2026, 2, 3)) == date(2026, 3, 31)


# --------------------------------------------------------------------------- #
# 五条规则
# --------------------------------------------------------------------------- #
def test_monthly_overtime_comprehensive_uses_standard_hours() -> None:
    """综合计算工时制：加班 = 月排班 − 月标准 174h（**不是**加班单累计）。"""
    book = _book(monthly_standard_hours=174.0, monthly_overtime_cap=36.0)
    facts = _employee(
        "E002",
        "综合计算工时制",
        shifts=tuple(
            ShiftFact(
                node_id=f"SHIFT:S{i:05d}",
                date=date(2026, 10, 1 + i).isoformat(),
                planned_hours=12.0 if i < 10 else 8.0,
                is_rest_day=False,
            )
            for i in range(22)
        ),
        # 故意给加班单：综合制**不得**使用它（口径分岔的反向验证）
        overtime=(OvertimeFact("OVERTIME:OT1", "2026-10-11", 6.0, True, 6.0, 0.0),),
    )
    finding = _rule_monthly_overtime(facts, book, date(2026, 10, 31))
    assert finding is not None
    assert finding.observed == 42.0  # 216 − 174
    assert finding.level == LEVEL_HIGH
    assert "216" in finding.calculation and "174" in finding.calculation


def test_monthly_overtime_standard_uses_approved_overtime() -> None:
    """标准工时制：加班 = 已审批加班单累计（不减月标准）。"""
    book = _book(monthly_standard_hours=174.0, monthly_overtime_cap=36.0)
    facts = _employee(
        "E004",
        "标准工时制",
        overtime=tuple(
            OvertimeFact(f"OVERTIME:OT{i}", f"2026-10-{10 + i}", 12.0, True, 12.0, 0.0)
            for i in range(4)
        ),
    )
    finding = _rule_monthly_overtime(facts, book, date(2026, 10, 31))
    assert finding is not None
    assert finding.observed == 48.0
    # 未审批的单据不得计入
    unapproved = _employee(
        "E004",
        "标准工时制",
        overtime=(OvertimeFact("OVERTIME:OT9", "2026-10-20", 48.0, False, 0.0, 0.0),),
    )
    assert _rule_monthly_overtime(unapproved, book, date(2026, 10, 31)) is None


def test_monthly_overtime_skips_flexible_system() -> None:
    """不定时工作制不适用月加班规则。"""
    book = _book(monthly_standard_hours=174.0, monthly_overtime_cap=36.0)
    facts = _employee(
        "E099",
        "不定时工作制",
        shifts=tuple(
            ShiftFact(f"SHIFT:S{i}", f"2026-10-{i + 1:02d}", 12.0, False)
            for i in range(28)
        ),
    )
    assert _rule_monthly_overtime(facts, book, date(2026, 10, 31)) is None


def test_weekly_hours_only_for_standard_system() -> None:
    """周工时规则只看标准工时制，且**严格大于**上限才触发。"""
    book = _book(weekly_hours_cap=40.0)
    standard = _employee("E003", "标准工时制", attendance=_attendance(6, hours=8.0))
    assert _rule_weekly_hours(standard, book, date(2026, 10, 31)) is not None

    exactly_40 = _employee("E003", "标准工时制", attendance=_attendance(5, hours=8.0))
    assert _rule_weekly_hours(exactly_40, book, date(2026, 10, 31)) is None

    comprehensive = _employee("E002", "综合计算工时制", attendance=_attendance(7))
    assert _rule_weekly_hours(comprehensive, book, date(2026, 10, 31)) is None


def test_core_window_absence_counts_below_required_hours() -> None:
    """弹性越界：核心时段在岗不足 6h 记一次，超过 5 次才触发。"""
    book = _book(core_hours_required=6.0, core_absence_limit=5.0)
    missed = _attendance(7, core=0.0)
    ok_days = _attendance(5, core=6.0)
    facts = _employee("E003", "标准工时制", attendance=missed + ok_days)
    finding = _rule_core_window(facts, book, date(2026, 10, 31))
    assert finding is not None
    assert finding.observed == 7.0 and finding.level == LEVEL_MEDIUM

    few = _employee("E003", "标准工时制", attendance=_attendance(5, core=0.0))
    assert _rule_core_window(few, book, date(2026, 10, 31)) is None


def test_comp_off_level_depends_on_quarter_remaining_days() -> None:
    """调休未消化：触发看「已产生额度且已调休 0」，**等级**看季度剩余天数。"""
    book = _book(comp_off_quarter_remaining_days=30.0)
    facts = _employee(
        "E004",
        "标准工时制",
        overtime=(OvertimeFact("OVERTIME:OT1", "2026-10-11", 22.0, True, 22.0, 0.0),),
    )
    far = _rule_comp_off(facts, book, date(2026, 10, 31))  # 季末剩 61 天
    near = _rule_comp_off(facts, book, date(2026, 12, 15))  # 季末剩 16 天
    assert far is not None and far.level == LEVEL_MEDIUM
    assert near is not None and near.level == LEVEL_HIGH

    used = _employee(
        "E004",
        "标准工时制",
        overtime=(OvertimeFact("OVERTIME:OT1", "2026-10-11", 22.0, True, 22.0, 22.0),),
    )
    assert _rule_comp_off(used, book, date(2026, 12, 15)) is None


def test_consecutive_attendance_excludes_absent_days() -> None:
    """连续出勤：连续排班日中剔除 ``absent`` 日后再算最长段。"""
    book = _book(consecutive_days_limit=12.0)
    days = [date(2026, 10, day) for day in range(1, 23)]
    shifts = tuple(
        ShiftFact(f"SHIFT:S{i:05d}", day.isoformat(), 8.0, False)
        for i, day in enumerate(days)
    )
    attendance = tuple(
        AttendanceFact(
            f"ATTENDANCE_RECORD:A{i:05d}",
            day.isoformat(),
            8.0,
            6.0,
            "absent" if day == date(2026, 10, 8) else "normal",
            False,
        )
        for i, day in enumerate(days)
    )
    facts = _employee("E002", "综合计算工时制", shifts=shifts, attendance=attendance)
    finding = _rule_consecutive(facts, book, date(2026, 10, 31))
    assert finding is not None
    # 10-08 absent ⇒ 断成 7 天 + 14 天两段，最长 14
    assert finding.observed == 14.0


# --------------------------------------------------------------------------- #
# 查询接线（假 session，只验接线不验数据）
# --------------------------------------------------------------------------- #
class _FakeSession:
    """按 Cypher 关键字返回预设行的假会话。"""

    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self._rows = rows
        self.queries: list[str] = []

    def run(self, cypher: str, **params: object) -> list[dict]:
        self.queries.append(cypher)
        for key, rows in self._rows.items():
            if key in cypher:
                return list(rows)
        return []


def test_load_employee_facts_filters_csv_derived_nodes() -> None:
    """员工事实只取 CSV 派生节点（``EMPLOYEE:`` 前缀）——M2 噪声节点不得混入。"""
    session = _FakeSession(
        {
            "e.id AS node_id": [
                {
                    "node_id": "EMPLOYEE:E001",
                    "name": "张伟",
                    "department": "售后部",
                    "position": "售后工程师",
                    "wts": "综合计算工时制",
                }
            ],
            "HAS_SHIFT": [
                {
                    "employee": "EMPLOYEE:E001",
                    "node_id": "SHIFT:S00001",
                    "date": "2026-10-01",
                    "hours": 8.0,
                    "rest": 0,
                }
            ],
            "HAS_ATTENDANCE": [
                {
                    "employee": "EMPLOYEE:E001",
                    "node_id": "ATTENDANCE_RECORD:A00001",
                    "date": "2026-10-01",
                    "hours": 8.0,
                    "core": 6.0,
                    "status": "normal",
                    "rest": 0,
                }
            ],
            "ACCUMULATED_OVERTIME": [
                {
                    "employee": "EMPLOYEE:E001",
                    "node_id": "OVERTIME:OT0001",
                    "date": "2026-10-11",
                    "hours": 6.0,
                    "approved": 1,
                    "comp_off": 6.0,
                    "comp_off_used": 0.0,
                }
            ],
        }
    )
    facts = load_employee_facts(session=session, kg_version="v", org_id="org")
    assert len(facts) == 1
    assert facts[0].employee_id == "E001"
    assert facts[0].shifts[0].planned_hours == 8.0
    assert facts[0].overtime[0].comp_off_hours == 6.0
    # 四条事实查询都带 CSV 前缀约束（防 M2 噪声混入）
    assert len(session.queries) == 4
    assert all("STARTS WITH 'EMPLOYEE:'" in query for query in session.queries)


def test_scan_compliance_requires_employees() -> None:
    """没有 CSV 派生员工 ⇒ **显式报错**（不返回空清单冒充成功）。"""
    session = _FakeSession({})
    with pytest.raises(ComplianceScanError):
        scan_compliance(session=session, kg_version="v", org_id="org")


def test_load_policy_clauses_query_shape() -> None:
    """条款读取：库内按 id 升序（多次解析同解），文本 = mention + canonical_name。"""
    session = _FakeSession(
        {
            "POLICY_CLAUSE": [
                {"id": "ent_b", "name": "第十一条", "mention": "第十一条"},
                {"id": "ent_a", "name": "每月加班时间不得超过36小时", "mention": ""},
            ]
        }
    )
    clauses = load_policy_clauses(session=session, kg_version="v", org_id="org")
    assert "ORDER BY n.id" in session.queries[0]
    assert len(clauses) == 2
    assert clauses[1].text == "每月加班时间不得超过36小时"

    # 解析阶段按 order 排序（同解保证）
    book = resolve_rule_values(clauses=clauses)
    assert book.value("monthly_overtime_cap") == 36.0
