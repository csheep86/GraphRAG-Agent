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

TaskType = Literal[
    "document.parse",
    "document.extract",
    "kg.build",
    "risk.detect",
    "affiliation.detect",
]
"""当前已登记的任务类型。新增类型须同步 :mod:`app.tasks.registry`。

Sprint 5 批次 B 扩展：从单段 ``document.parse`` 扩为串行三段——
``document.parse`` → ``document.extract`` → ``kg.build``，每段独立 task_type
与独立执行体（ADR-0004 §2.1 接缝 4）。

Sprint 7.1 批次 A 增 ``risk.detect``、Sprint 7.2 批次 B 增 ``affiliation.detect``
（**本次一并补上 ``risk.detect``**：它早已登记进 ``EXECUTOR_REGISTRY``，却漏在
本 Literal 外，属既有漂移）。

两类载体，**投递时不可混用**：
- **document 类**（前四种）：一次任务绑定一份文档，``task_id == documents.id``；
- **affiliation 类**（``affiliation.detect``）：一次检测覆盖**多份**文档，
  ``task_id == affiliation_tasks.id``（批次 B 决策 **B8**）。
"""


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """提交任务的输入规格（ADR-0001 §3.1）。

    **A5（P3-A）：``org_id`` 是必填字段**——后台任务跑在请求之外（进程内
    BackgroundTasks），拿不到请求级身份；RLS 生效后，执行体若不先设 org
    就查不到自己那一行 ⇒ 合法任务会被误判成「记录不存在」（静默失败，坑 3）。

    ``org_id`` 的可信来源**只有一个**：任务**创建时**的认证态（``identity.org_id``）。
    不从 payload 取——payload 是业务数据，可被上层改写（ADR-0003 §3.3 同款纪律）。
    """

    task_type: TaskType
    payload: dict[str, Any]
    trace_id: str
    #: 任务所属租户（创建时从认证态取得；执行体据此在 Session 上设 org）
    org_id: UUID


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
    """``recover_orphan_tasks`` 的回收结果（用于启动日志与审计）。

    Sprint 7.2 批次 B 起分表计数：ADR-0001 §3.2 要求回收扫描覆盖
    ``documents`` **与** ``affiliation_tasks`` 两张表，混成一个数字会让
    「哪一类任务被回收」在启动日志里无法核对。``reclaimed`` 仍为合计（既有调用点不变）。
    """

    reclaimed: int = 0
    document_reclaimed: int = 0
    affiliation_reclaimed: int = 0


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
