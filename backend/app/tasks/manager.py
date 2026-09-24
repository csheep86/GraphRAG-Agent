"""异步任务抽象层（ADR-0001 §3）。

公开面：
- :class:`TaskManager`：业务代码**唯一**允许依赖的任务接口；每次请求一个实例，
  构造时绑定当前请求的 :class:`fastapi.BackgroundTasks`。
- :func:`recover_orphan_tasks`：FastAPI lifespan startup 调用，回收孤儿任务
  （``pending`` / ``processing`` → ``failed`` + ``error_code = TASK_INTERRUPTED``）。

实现策略（**严格**按 ADR-0001 §3）：
1. 状态真实持久化于 PostgreSQL（``documents.status``）；**严禁**保存于进程内存字典。
2. ``TaskManager.submit()`` 只做两件事：**落 `pending` → 向 BackgroundTasks 注册执行体**。
3. ``TaskManager.get_status()`` **只**读数据库，不读内存。
4. :func:`recover_orphan_tasks` 在 ``lifespan`` startup 调用，扫描并批量置 ``failed``。
5. 执行体内部 tenacity 指数退避（初始 1s、倍数 2、上限 3 次，**H8**）。
6. ``asyncio.Semaphore`` 限流，防止解析任务饿死 API 事件循环（§3.3）。

数据类型（``TaskSpec`` / ``TaskStatus`` / ``RecoveryReport`` / ``TaskExecutorFn``）位于
:mod:`app.tasks.types`，避免与 :mod:`app.tasks.registry` 形成循环导入。
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from loguru import logger
from sqlalchemy import select, update

from app.core.errors import ErrorCode
from app.db.models import AffiliationTask, Document
from app.db.session import SessionLocal
from app.tasks.registry import resolve_executor
from app.tasks.types import RecoveryReport, TaskExecutorFn, TaskSpec, TaskStatus

#: 模块级 Semaphore：解析任务并发上限（ADR-0001 §3.3）。
#: 懒加载，第一次访问时按 settings 取值。
_parse_semaphore: asyncio.Semaphore | None = None


def _get_parse_semaphore() -> asyncio.Semaphore:
    global _parse_semaphore
    if _parse_semaphore is None:
        from app.core.config import get_settings  # 避免循环导入

        _parse_semaphore = asyncio.Semaphore(get_settings().task_parse_concurrency)
    return _parse_semaphore


class TaskManager:
    """请求内可用的任务管理器。

    每个请求独立一个实例；持有当前请求的 :class:`fastapi.BackgroundTasks`，
    用于把执行体投递到 FastAPI 的进程内任务队列。
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def submit(self, spec: TaskSpec) -> str:
        """落 ``pending`` + 注册执行体，返回 task_id。

        **两类任务载体**（批次 B 决策 **B8**；新增 task_type 时必须先想清楚是哪种）：

        - **document 类**（``document.parse`` / ``document.extract`` / ``kg.build`` /
          ``risk.detect``）：一次任务绑定**一份**文档，``task_id`` 恒等于
          ``documents.id``，要求 ``payload["document_id"]``；
        - **affiliation 类**（``affiliation.detect``）：一次检测覆盖**多份**文档，
          ``task_id`` 来自 ``affiliation_tasks.id``，要求
          ``payload["affiliation_task_id"]``。

        为什么必须改在**这里**而不是让路由层直接 ``BackgroundTasks.add_task``：
        ADR-0001 要求 2 规定「业务代码只依赖 ``TaskManager`` 接口」——第二个投递入口
        等于第二个任务真值源，违背该要求。
        """
        # 用「执行体是否登记」代替硬编码白名单——新增阶段后只改 registry 即可
        try:
            resolve_executor(spec.task_type)
        except KeyError as exc:
            raise ValueError(
                f"未实现的 task_type={spec.task_type!r}；新增任务类型须先登记到 "
                f"app.tasks.registry.EXECUTOR_REGISTRY"
            ) from exc

        affiliation_id_raw = spec.payload.get("affiliation_task_id")
        if isinstance(affiliation_id_raw, str) and affiliation_id_raw:
            return self._submit_affiliation(spec, UUID(affiliation_id_raw))
        return self._submit_document(spec)

    def _submit_document(self, spec: TaskSpec) -> str:
        """document 类投递（``task_id == documents.id``）。"""
        document_id_raw = spec.payload.get("document_id")
        if not isinstance(document_id_raw, str) or not document_id_raw:
            raise ValueError("TaskSpec.payload.document_id 必填且须为字符串 UUID")
        document_id = UUID(document_id_raw)

        # 1) 状态由调用方在创建 documents 时已经落成 pending；
        #    此处只做幂等校验，避免重复 submit
        with SessionLocal() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise LookupError(f"documents 不存在: id={document_id}")
            if document.status not in {"pending", "processing"}:
                # 允许幂等：completed / failed 不再重投
                logger.bind(
                    trace_id=spec.trace_id,
                    document_id=str(document_id),
                    current_status=document.status,
                ).info("task_submit_skipped_non_pending")
                return str(document_id)

        # 2) 注册执行体（进程内队列；进程重启即丢失——这正是 recover() 兜底的原因）
        executor = resolve_executor(spec.task_type)
        self._background_tasks.add_task(_run_with_semaphore, executor, spec)

        logger.bind(
            trace_id=spec.trace_id,
            task_type=spec.task_type,
            document_id=str(document_id),
        ).info("task_submitted")
        return str(document_id)

    def _submit_affiliation(self, spec: TaskSpec, task_id: UUID) -> str:
        """affiliation 类投递（``task_id == affiliation_tasks.id``，一次任务覆盖多份文档）。"""
        with SessionLocal() as session:
            row = session.get(AffiliationTask, task_id)
            if row is None:
                raise LookupError(f"affiliation_tasks 不存在: id={task_id}")
            if row.status not in {"pending", "processing"}:
                # 与 document 类同款幂等语义：completed / failed 不再重投
                logger.bind(
                    trace_id=spec.trace_id,
                    task_id=str(task_id),
                    current_status=row.status,
                ).info("task_submit_skipped_non_pending")
                return str(task_id)

        executor = resolve_executor(spec.task_type)
        self._background_tasks.add_task(_run_with_semaphore, executor, spec)

        logger.bind(
            trace_id=spec.trace_id,
            task_type=spec.task_type,
            task_id=str(task_id),
        ).info("task_submitted")
        return str(task_id)

    def get_status(self, task_id: str | UUID) -> TaskStatus | None:
        """读 PostgreSQL；不存在返回 ``None``。**不**读内存。"""
        task_uuid = UUID(str(task_id))
        with SessionLocal() as session:
            document = session.get(Document, task_uuid)
            if document is None:
                return None
            return TaskStatus(
                task_id=document.id,
                status=document.status,
                retry_count=document.retry_count,
                error_code=document.error_code,
                error_detail=document.error_detail,
            )


async def _run_with_semaphore(executor: TaskExecutorFn, spec: TaskSpec) -> None:
    """Semaphore 限流的执行壳。"""
    semaphore = _get_parse_semaphore()
    async with semaphore:
        await executor(spec)


def recover_orphan_tasks() -> RecoveryReport:
    """扫描遗留 ``pending`` / ``processing`` 任务，批量置 ``failed (TASK_INTERRUPTED)``。

    依据：
    - ADR-0001 §3.2：进程重启回收；
    - M1 §3 验收 8：``error_code = TASK_INTERRUPTED`` + ``error_detail`` 记录「进程重启导致任务中断」；
    - **ADR-0001 第 73 行**：扫描必须覆盖 ``documents`` **与** ``affiliation_tasks``
      两张表（Sprint 7.2 批次 B 补齐后者——``affiliation_tasks`` 一落地就必须被回收，
      否则它是张「可能永远卡在 processing」的表）。

    由 FastAPI lifespan startup 调用；幂等，可重复执行。
    """
    with SessionLocal() as session:
        result = session.execute(
            update(Document)
            .where(Document.status.in_(("pending", "processing")))
            .values(
                status="failed",
                error_code=ErrorCode.TASK_INTERRUPTED.value,
                error_detail="process restarted while task was in-flight",
            )
        )
        document_reclaimed = result.rowcount or 0

        affiliation_result = session.execute(
            update(AffiliationTask)
            .where(AffiliationTask.status.in_(("pending", "processing")))
            .values(
                status="failed",
                error_code=ErrorCode.TASK_INTERRUPTED.value,
                error_detail="process restarted while task was in-flight",
            )
        )
        affiliation_reclaimed = affiliation_result.rowcount or 0
        session.commit()

    reclaimed = document_reclaimed + affiliation_reclaimed
    report = RecoveryReport(
        reclaimed=reclaimed,
        document_reclaimed=document_reclaimed,
        affiliation_reclaimed=affiliation_reclaimed,
    )
    if reclaimed:
        logger.bind(
            reclaimed=reclaimed,
            document_reclaimed=document_reclaimed,
            affiliation_reclaimed=affiliation_reclaimed,
        ).warning("task_recover_orphan_executed")
    else:
        logger.bind(reclaimed=0).info("task_recover_orphan_noop")
    return report


def list_in_flight_task_ids() -> tuple[UUID, ...]:
    """取当前所有 ``pending`` / ``processing`` 的 task_id。仅供测试与对账使用。

    **S7.2-2 偿还（Sprint 8.1 批次 B）**：扫描覆盖 ``documents`` **与**
    ``affiliation_tasks`` 两张表——与 :func:`recover_orphan_tasks` 同口径
    （ADR-0001 第 73 行）：``affiliation_tasks`` 也会卡在 ``processing``，
    对账函数看不到它就是盲区。返回顺序：documents 在前、affiliation 在后。
    """
    with SessionLocal() as session:
        document_rows = session.execute(
            select(Document.id).where(Document.status.in_(("pending", "processing")))
        ).all()
        affiliation_rows = session.execute(
            select(AffiliationTask.id).where(
                AffiliationTask.status.in_(("pending", "processing"))
            )
        ).all()
    return tuple(row[0] for row in document_rows) + tuple(
        row[0] for row in affiliation_rows
    )


def new_trace_id() -> str:
    """UUIDv4 trace_id 生成器。"""
    return str(uuid4())


__all__ = [
    "RecoveryReport",
    "TaskManager",
    "new_trace_id",
    "list_in_flight_task_ids",
    "recover_orphan_tasks",
]
