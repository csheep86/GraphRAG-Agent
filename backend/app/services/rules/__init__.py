"""考勤域**确定性规则引擎**（Sprint 9.5 批次 C1）。

拆成两块，职责不同：

- :mod:`app.services.rules.policy_values` —— **规则值**从制度文本解析
  （周 40h / 月标准 174h / 加班上限 36h / 核心时段 6h / 越界 5 次 / 连续 12 天 /
  季度剩余 30 天），解析不到即 ``unresolved``，**不**用默认值静默兜底；
- :mod:`app.services.rules.engine` —— **事实**从图谱读、五条规则**确定性计算**，
  输出含计算过程与证据的 :class:`RiskFinding`。

**共同纪律**：全程无 LLM（数值不出 LLM）；结果可复现（同输入同解）。
"""

from app.services.rules.attribution import (
    ATTENDANCE_SUSPICION_TYPES,
    FINANCE_SUSPICION_TYPES,
    AttributionResult,
    Cause,
    attribute_absence,
    find_anomaly_days,
    suspicion_types_for_domain,
)
from app.services.rules.engine import (
    LEVEL_HIGH,
    LEVEL_MEDIUM,
    RULE_COMP_OFF,
    RULE_CONSECUTIVE,
    RULE_CORE_WINDOW,
    RULE_MONTHLY_OVERTIME,
    RULE_WEEKLY_HOURS,
    ComplianceReport,
    ComplianceScanError,
    EmployeeFacts,
    RiskFinding,
    load_employee_facts,
    rule_label,
    scan_compliance,
)
from app.services.rules.policy_values import (
    PolicySentence,
    RuleValue,
    RuleValueBook,
    RuleValueUnresolvedError,
    load_policy_clauses,
    load_policy_documents,
    policy_document_id,
    resolve_rule_values,
    search_policy_sentences,
)

__all__ = [
    "ATTENDANCE_SUSPICION_TYPES",
    "AttributionResult",
    "Cause",
    "FINANCE_SUSPICION_TYPES",
    "LEVEL_HIGH",
    "LEVEL_MEDIUM",
    "RULE_COMP_OFF",
    "RULE_CONSECUTIVE",
    "RULE_CORE_WINDOW",
    "RULE_MONTHLY_OVERTIME",
    "RULE_WEEKLY_HOURS",
    "ComplianceReport",
    "ComplianceScanError",
    "EmployeeFacts",
    "PolicySentence",
    "RiskFinding",
    "RuleValue",
    "RuleValueBook",
    "RuleValueUnresolvedError",
    "attribute_absence",
    "find_anomaly_days",
    "load_employee_facts",
    "load_policy_clauses",
    "load_policy_documents",
    "policy_document_id",
    "resolve_rule_values",
    "rule_label",
    "scan_compliance",
    "search_policy_sentences",
    "suspicion_types_for_domain",
]
