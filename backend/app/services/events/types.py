"""事件类型取值（ADR-0004 §2.1 接缝 5 登记）。

四个类型**全部定义**，但本批次**只有** :data:`RISK_SUSPECT_CREATED` 有真实事件源
（疑点落库处）；其余三个没有真实触发点，**不发送**——没有触发点却发事件，就是假事件。

与 `app/db/models.py` 的 ``ck_domain_events_event_type`` 约束保持一致：改这里要同步改那里。
"""

from __future__ import annotations

DOCUMENT_PARSED = "document.parsed"
KG_UPDATED = "kg.updated"
RISK_SUSPECT_CREATED = "risk.suspect_created"
QA_ANSWERED = "qa.answered"

EVENT_TYPE_VALUES: tuple[str, ...] = (
    DOCUMENT_PARSED,
    KG_UPDATED,
    RISK_SUSPECT_CREATED,
    QA_ANSWERED,
)

__all__ = [
    "DOCUMENT_PARSED",
    "EVENT_TYPE_VALUES",
    "KG_UPDATED",
    "QA_ANSWERED",
    "RISK_SUSPECT_CREATED",
]
