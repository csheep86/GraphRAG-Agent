"""任务执行体注册表（task_type → 真正的处理函数）。

**设计动机**：TaskManager 只负责「注册 + 调度 + 回收」，**不**关心
具体业务逻辑；新增一种任务类型只需在本注册表中登记一项，TaskManager
代码无需改动。

阶段九已登记：
- ``document.parse``：PDF / DOCX / CSV → chunks → Neo4j（M1 → M2 衔接）；
  当前为骨架版，仅完成 `pending → processing → completed` 推进 + 错误落库。
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Mapping
from uuid import UUID

from loguru import logger
from sqlalchemy.orm import Session
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import Document
from app.db.session import SessionLocal
from app.tasks.types import TaskExecutorFn, TaskSpec

#: 可重试的异常类型：第三方 IO 错误（Neo4j / HTTP / 文件解析等）。
#: 业务校验失败（ValueError 等）**不**重试。
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
)


async def document_parse_executor(spec: TaskSpec) -> None:
    """``document.parse`` 执行体骨架。

    真实 MinerU + LangExtract 链路属 Sprint 3 后段；本阶段只保证：
    1. 状态机 `pending → processing → completed` 真实推进；
    2. 第三方 IO 异常走 tenacity 重试（≤ 3 次，初始 1s、倍数 2）；
    3. 最终失败时落 `error_code` + `error_detail`，**绝不静默吞错**。
    """
    settings = get_settings()
    document_id = UUID(spec.payload["document_id"])

    db: Session = SessionLocal()
    try:
        # 1. 推进到 processing（真实写入数据库）
        document = db.get(Document, document_id)
        if document is None:
            # TaskManager.recover() 已先跑过；理论上不应再发生
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).error(
                "document_parse_missing_record"
            )
            return

        if document.status == "completed":
            logger.bind(
                trace_id=spec.trace_id, document_id=str(document_id)
            ).info("document_parse_skipped_already_completed")
            return

        document.status = "processing"
        db.commit()

        # 2. tenacity 重试（IO 异常）
        attempt_count = 0

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            next_action = getattr(retry_state, "next_action", None)
            next_sleep = getattr(next_action, "sleep", None) if next_action else None
            logger.bind(
                trace_id=spec.trace_id,
                document_id=str(document_id),
                attempt=attempt_count,
                next_wait_seconds=next_sleep,
            ).warning("document_parse_retry")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.task_retry_max_attempts),
                wait=wait_exponential(
                    multiplier=settings.task_retry_initial_seconds,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_parse(document_id=document_id, payload=spec.payload)
        except RetryError as exc:
            # 重试用尽：把最后一个底层异常抛出，由外层 except 落库
            if exc.last_attempt is not None and exc.last_attempt.exception() is not None:
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        # 3. 推进到 completed
        document = db.get(Document, document_id)
        assert document is not None  # 同 session 内不可能消失
        document.status = "completed"
        document.error_code = None
        document.error_detail = None
        db.commit()

        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            retry_count=attempt_count,
        ).info("document_parse_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        _mark_failed(db, document_id, exc, spec.trace_id)
    finally:
        db.close()


async def _do_parse(*, document_id: UUID, payload: Mapping[str, object]) -> None:
    """真正的解析逻辑（MinerU + LangExtract）。阶段九骨架：占位，让状态机推进到 completed。

    Sprint 3 后段将替换为：
    1. ``document_parse_v1`` 提示词驱动的结构化解析；
    2. ``entity_relation_extract_v1`` 提示词驱动的实体抽取；
    3. ADR-0002 三段式写入：PG `writing` → Neo4j `MERGE` → PG `active / failed`。
    """
    _ = document_id, payload
    return None


def _mark_failed(db: Session, document_id: UUID, exc: Exception, trace_id: str) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return
    document.status = "failed"
    document.error_code = ErrorCode.INTERNAL_ERROR.value
    # 错误明细**敏感**，日志禁止输出原文（CODEBUDDY.md 安全底线）
    document.error_detail = "".join(
        traceback.format_exception_only(type(exc), exc)
    ).strip()
    db.commit()
    logger.bind(
        trace_id=trace_id,
        document_id=str(document_id),
        error_code=document.error_code,
        exc_type=type(exc).__name__,
    ).error("document_parse_failed")


#: 任务类型 → 执行体的注册表。新增任务类型在此登记即可。
EXECUTOR_REGISTRY: dict[str, TaskExecutorFn] = {
    "document.parse": document_parse_executor,
}


def resolve_executor(task_type: str) -> TaskExecutorFn:
    """取 task_type 对应的执行体；未登记抛 KeyError（防止静默丢任务）。"""
    try:
        return EXECUTOR_REGISTRY[task_type]
    except KeyError as exc:
        raise KeyError(
            f"未登记的 task_type={task_type!r}；请在 app.tasks.registry.EXECUTOR_REGISTRY 登记"
        ) from exc


__all__ = ["EXECUTOR_REGISTRY", "resolve_executor"]
