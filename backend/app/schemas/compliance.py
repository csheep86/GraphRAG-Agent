"""考勤域**合规预警**契约（Sprint 9.5 批次 C3 / D3）。

字段来源：
- ``changes/Sprint9.5/proposal.md`` §5.3（五条规则 + 规则值来自制度文本）；
- ``backend/app/services/rules/engine.py`` 的 :class:`ComplianceReport` /
  :class:`RiskFinding`（本文件是它们的**契约投影**，不是另起一套语义）。

**三条纪律在契约里的体现**（不是文档修辞，而是字段设计）：

1. **数值不硬编码** ⇒ ``rule_values[]`` 每个值都带 ``source`` / ``reference`` /
   ``evidence``，前端必须能把「40 小时」点开看到制度原句；
2. **无溯源即拒答**（F3）⇒ ``unresolved[]`` / ``skipped_rules[]`` 显式暴露：
   规则值解析不到时对应规则**跳过**，**不**用默认值算出一个"看起来合理"的结论；
3. **可复算** ⇒ 每条 finding 带 ``calculation``（计算过程）与 ``observed`` /
   ``threshold`` / ``unit``，演示时能逐条念出并手工核算。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ComplianceRule = Literal[
    "weekly_hours_exceeded",
    "monthly_overtime_exceeded",
    "comp_off_undigested",
    "core_window_absence",
    "consecutive_attendance",
]
"""五条确定性规则的标识（与 ``engine.RULE_*`` 常量逐字一致）。

**为什么用 Literal 而不是 str**：前端据此生成联合类型，写错规则名在编译期就报错；
新规则必须先在此登记（契约即承诺，不提供未实现的枚举值）。
"""

ComplianceLevel = Literal["high", "medium"]
"""风险等级。当前规则集**只产出 high / medium**（无 low）——不把产不出的等级写进枚举。"""

RuleValueSource = Literal["graph", "document"]
"""规则值出处：``graph`` = 图谱 ``POLICY_CLAUSE``（span 级）；``document`` = M1 产物 ``full.md``。"""


class RuleValueItem(BaseModel):
    """一个**解析自制度文本**的规则值（含出处，可逐条核查）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "key": "monthly_overtime_cap",
                "label": "月加班上限",
                "value": 36.0,
                "unit": "小时",
                "source": "graph",
                "reference": "clause:ent_d165867ab6e8",
                "evidence": "每月加班时间不得超过 36 小时",
            }
        }
    )

    key: str = Field(description="规则值标识（如 `monthly_overtime_cap`）")
    label: str = Field(description="中文名（如「月加班上限」）")
    value: float = Field(description="解析出的数值（**制度文本里认出来的**，非硬编码）")
    unit: str = Field(description="单位：小时 / 次 / 天")
    source: RuleValueSource = Field(description="出处类型")
    reference: str = Field(
        description="出处定位：`clause:<节点 id>` 或 `doc:<文档 stem>:L<行号>`"
    )
    evidence: str = Field(description="命中的制度原文片段（供前端直接回显）")


class ComplianceFinding(BaseModel):
    """一条合规风险（含计算过程与证据 —— 演示要能逐条念出来）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rule": "monthly_overtime_exceeded",
                "rule_label": "月加班超限",
                "employee_id": "E002",
                "employee_name": "李静",
                "department": "生产部",
                "work_time_system": "综合计算工时制",
                "level": "high",
                "title": "月加班超限",
                "observed": 42.0,
                "threshold": 36.0,
                "unit": "小时",
                "calculation": "月排班 216h（22 天）− 月标准 174h = 加班 42h > 上限 36h",
                "policy_refs": ["graph:clause:ent_c974307a4bd5"],
                "evidence": ["SHIFT:S00023", "SHIFT:S00024"],
            }
        }
    )

    rule: ComplianceRule = Field(description="命中的规则")
    rule_label: str = Field(description="规则中文名")
    employee_id: str = Field(description="员工工号（如 `E002`）")
    employee_name: str = Field(description="员工姓名")
    department: str = Field(description="所属部门")
    work_time_system: str = Field(
        description="工时制（综合计算 / 标准 / 不定时工作制）"
    )
    level: ComplianceLevel = Field(description="风险等级")
    title: str = Field(description="风险标题")
    observed: float = Field(description="实测值")
    threshold: float = Field(description="制度阈值（来自 `rule_values[]`）")
    unit: str = Field(description="单位")
    calculation: str = Field(description="计算过程（可直接展示 / 朗读）")
    policy_refs: list[str] = Field(
        description="制度依据引用（`graph:clause:…` / `document:doc:…`）"
    )
    evidence: list[str] = Field(
        description="证据节点 id 列表（`GET /entities/{id}` 可回查详情）"
    )


class ComplianceScanResponse(BaseModel):
    """`GET /attendance/compliance/scan` 响应：一次全量合规扫描。

    **同步返回**（非异步任务）：扫描是**纯读**（不落库、不调 LLM），
    40 名员工实测秒级完成 —— 引入 `task_id` 轮询只会多一轮往返且无状态可存。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "kg_version": "attendance-demo-v1",
                "as_of": "2026-10-31",
                "employee_count": 40,
                "rule_values": [],
                "unresolved": [],
                "skipped_rules": [],
                "findings": [],
                "total": 8,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    kg_version: str = Field(description="扫描所基于的图谱版本（只读 active 版本）")
    as_of: date = Field(
        description="观察日；缺省取数据窗口末日（**不取系统当天**，保证可复现）"
    )
    employee_count: int = Field(ge=0, description="参与扫描的员工数")
    rule_values: list[RuleValueItem] = Field(
        description="已解析出的规则值（每个都带制度出处）"
    )
    unresolved: list[str] = Field(
        description="**未**解析出的规则值 key；对应规则已跳过，**未用默认值兜底**"
    )
    skipped_rules: list[str] = Field(
        description="因缺规则值而跳过的规则（不是「没风险」，是「没判据」）"
    )
    findings: list[ComplianceFinding] = Field(
        description="风险清单（按等级 / 工号排序）"
    )
    total: int = Field(ge=0, description="风险条数（与 `len(findings)` 一致）")
    trace_id: str = Field(description="本次请求的 trace_id")
