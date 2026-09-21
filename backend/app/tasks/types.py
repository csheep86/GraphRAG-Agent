"""异步任务的数据类型（独立模块，避开 ``manager.py`` / ``registry.py`` 之间的循环导入）。

公开面：
- :class:`TaskSpec`：提交任务的输入规格；
- :class:`TaskStatus`：任务当前状态（数据库投影）；
- :class:`RecoveryReport`：回收结果；
- :class:`TaskExecutorFn`：执行体的协议签名。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from uuid import UUID

TaskType = Literal["document.parse", "document.extract", "kg.build"]
"""当前已登记的任务类型。新增类型须同步 :mod:`app.tasks.registry`。

Sprint 5 批次 B 扩展：从单段 ``document.parse`` 扩为串行三段——
``document.parse`` → ``document.extract`` → ``kg.build``，每段独立 task_type
与独立执行体（ADR-0004 §2.1 接缝 4）。
"""


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """提交任务的输入规格（ADR-0001 §3.1）。"""

    task_type: TaskType
    payload: dict[str, Any]
    trace_id: str


@dataclass(frozen=True, slots=True)
class TaskStatus:
    """任务当前状态（数据库投影）。"""

    task_id: UUID
    status: str
    retry_count: int
    error_code: str | None = None
    error_detail: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """``recover_orphan_tasks`` 的回收结果（用于启动日志与审计）。"""

    reclaimed: int = 0


class TaskExecutorFn(Protocol):
    """执行体的协议签名。

    实现方负责真正的解析逻辑（PDF / DOCX / CSV → chunk → Neo4j）；
    框架负责重试（tenacity）、并发（Semaphore）、状态推进（pending→processing→completed/failed）。
    """

    async def __call__(self, spec: TaskSpec) -> None: ...


__all__ = [
    "RecoveryReport",
    "TaskExecutorFn",
    "TaskSpec",
    "TaskStatus",
    "TaskType",
]
