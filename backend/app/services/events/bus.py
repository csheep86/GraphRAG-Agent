"""事件总线：把事件分发给持有的每个 sink。"""

from __future__ import annotations

from app.services.events.base import DomainEvent, EventSink


class EventBus:
    """持有若干 sink 并逐个 ``emit``。

    ⚠️ **不得继承 `EventSink`**：门禁按**基类名**统计实现类并要求恰好 2 个，
    `EventBus` 若继承会让实现数变 3 → ERROR。它**持有** sink，本身不是 sink。
    """

    def __init__(self, sinks: list[EventSink]) -> None:
        self._sinks: list[EventSink] = list(sinks)

    def emit(self, event: DomainEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


__all__ = ["EventBus"]
