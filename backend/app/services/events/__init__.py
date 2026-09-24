"""事件出口（ADR-0004 §2.1 接缝 5；Sprint 7.4 批次 D）。

用法（落库由**业务侧**统一 commit，sink 自己不提交）：

    bus = build_event_bus(session)
    bus.emit(DomainEvent(...))

本阶段**只落库不派发**：``domain_events.dispatched_at`` 恒为 NULL。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.events.base import DomainEvent, EventSink
from app.services.events.bus import EventBus
from app.services.events.db import DbEventSink
from app.services.events.log import LogEventSink


def build_event_bus(session: Session) -> EventBus:
    """构造事件总线（db + log 两个本地实现）。

    **每次现场构造，不做模块级单例**：``DbEventSink`` 绑定的是请求级 session，
    做成单例会一直持有过期 session。
    """
    return EventBus([DbEventSink(session), LogEventSink()])


__all__ = [
    "DomainEvent",
    "EventBus",
    "EventSink",
    "build_event_bus",
]
