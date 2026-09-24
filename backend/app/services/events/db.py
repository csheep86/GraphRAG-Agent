"""``db`` 实现：把事件落到 `domain_events` 表（**只落不派**）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import DomainEvent as DomainEventRow
from app.services.events.base import DomainEvent, EventSink


class DbEventSink(EventSink):
    """写 ``domain_events`` 表的 sink。

    **不**自己 commit：与业务共用同一个 session（构造时传入），由业务侧统一提交。
    这样疑点落库失败回滚时，事件也一起回滚——不会出现"疑点没了但事件还在"。

    ``dispatched_at`` **恒不写**（默认 NULL）：本阶段只落不派（plan §6.2 批次 D）。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def emit(self, event: DomainEvent) -> None:
        self._session.add(
            DomainEventRow(
                org_id=event.org_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=dict(event.payload),
                trace_id=event.trace_id,
            )
        )


__all__ = ["DbEventSink"]
