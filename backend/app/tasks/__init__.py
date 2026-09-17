"""异步任务层（ADR-0001 §3）。

公开面：
- :class:`~app.tasks.manager.TaskManager`：请求内可用的任务管理器；
- :func:`~app.tasks.manager.recover_orphan_tasks`：lifespan startup 调用，回收孤儿任务；
- :class:`~app.tasks.types.TaskSpec` / :class:`~app.tasks.types.TaskStatus`
  / :class:`~app.tasks.types.RecoveryReport`：调用方与被调用方的数据契约；
- :data:`~app.tasks.registry.EXECUTOR_REGISTRY`：任务类型 → 执行体的注册表。

执行体内部以 tenacity 指数退避重试（初始 1s、倍数 2、上限 3 次，H8）；
进程重启后由 ``recover_orphan_tasks`` 扫描 ``documents.status IN ('pending','processing')``
并批量置 ``failed`` + ``error_code = TASK_INTERRUPTED``（M1 §3 验收 8 / ADR-0001 §3.2）。
"""

from app.tasks.manager import (
    TaskManager,
    list_in_flight_task_ids,
    recover_orphan_tasks,
)
from app.tasks.registry import EXECUTOR_REGISTRY, resolve_executor
from app.tasks.types import (
    RecoveryReport,
    TaskExecutorFn,
    TaskSpec,
    TaskStatus,
    TaskType,
)

__all__ = [
    "EXECUTOR_REGISTRY",
    "RecoveryReport",
    "TaskExecutorFn",
    "TaskManager",
    "TaskSpec",
    "TaskStatus",
    "TaskType",
    "list_in_flight_task_ids",
    "recover_orphan_tasks",
    "resolve_executor",
]
