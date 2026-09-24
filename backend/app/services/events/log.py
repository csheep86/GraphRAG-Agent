"""``log`` 实现：把事件打一行 JSON 日志（可观测侧，不落库）。"""

from __future__ import annotations

from loguru import logger

from app.services.events.base import DomainEvent, EventSink


class LogEventSink(EventSink):
    """打日志的 sink——让事件出口在**不派发**的前提下仍可观测。

    日志属观测侧，**不能**参与业务事务，因此它不碰 session、也不 commit。
    """

    def emit(self, event: DomainEvent) -> None:
        logger.bind(
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            org_id=str(event.org_id),
            trace_id=str(event.trace_id),
        ).info("domain_event emitted (only persisted, not dispatched)")


__all__ = ["LogEventSink"]
