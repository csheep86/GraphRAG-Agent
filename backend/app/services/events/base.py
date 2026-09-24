"""事件出口的接口与事件体（ADR-0004 §2.1 接缝 5）。

**实现类恰好两个**：:class:`DbEventSink`（落库）+ :class:`LogEventSink`（打日志）。
这不是"未来可替换的多种集成"，而是让事件出口**可观测**的最小集——门禁
``check_seams.py`` 按基类名统计实现类，要求 ``min = max = 2``，多一个即越界、
少一个即少做。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """一个领域事件（与 `domain_events` 表逐字段对应）。

    ``org_id`` / ``trace_id`` 一律由**调用方上下文**传入，**不**在 sink 里猜——
    猜出来的租户与链路 id 就是编数据。
    """

    event_type: str
    aggregate_type: str
    aggregate_id: str
    org_id: uuid.UUID
    trace_id: uuid.UUID
    payload: dict = Field(default_factory=dict)


class EventSink(ABC):
    """事件出口接口。

    实现方：
    - :class:`app.services.events.db.DbEventSink` —— 写 ``domain_events`` 表；
    - :class:`app.services.events.log.LogEventSink` —— 打一行 JSON 日志。
    """

    @abstractmethod
    def emit(self, event: DomainEvent) -> None:
        """发送一个事件。

        落库实现**不**自己 commit：与调用方共用同一 session，由业务侧统一提交，
        这样业务失败时事件一并回滚（不会出现"疑点没落库但事件留下了"）。
        """


__all__ = ["DomainEvent", "EventSink"]
