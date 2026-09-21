"""任务执行体注册表（task_type → 真正的处理函数）。

**设计动机**：TaskManager 只负责「注册 + 调度 + 回收」，**不**关心
具体业务逻辑；新增一种任务类型只需在本注册表中登记一项，TaskManager
代码无需改动。

已登记（v1.1.0 批次 A 起）：
- ``document.parse``：PDF 经 MinerU 云解析 → 产物落存储层（M1 → M2 衔接）；
  docx / csv 的结构化解析分别由 Sprint 10 / Sprint 9 承接（plan §15.3），
  本阶段跳过解析但照常推进状态机。
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import httpx
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
from app.services.parsing import MineruApiError, MineruClient
from app.storage import build_parse_artifact_key, build_storage_key, get_storage
from app.tasks.types import TaskExecutorFn, TaskSpec

#: 可重试的异常类型：第三方 IO 错误（HTTP / MinerU 业务失败 / 网络与文件系统）。
#: 业务校验失败（ValueError 等）**不**重试。
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
    httpx.HTTPError,
    MineruApiError,
)


async def document_parse_executor(spec: TaskSpec) -> None:
    """``document.parse`` 执行体。

    1. 状态机 `pending → processing → completed` 真实推进；
    2. 第三方 IO 异常走 tenacity 重试（≤ 3 次，初始 1s、倍数读
       ``task_retry_multiplier``——B4 修复：退避参数与配置真实挂钩）；
    3. 重试计数回写 ``documents.retry_count``（B1 修复）；
    4. 成功时回填 ``storage_key``（M1 §4.1：completed 后填写）；
    5. 最终失败时落 `error_code` + `error_detail`，**绝不静默吞错**。
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
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).info(
                "document_parse_skipped_already_completed"
            )
            return

        document.status = "processing"
        db.commit()

        # 2. tenacity 重试（IO 异常）
        attempt_count = 0

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            # B1 修复：重试计数回写 DB（attempt 1 = 首次尝试，重试从 2 起）
            document.retry_count = max(attempt_count - 1, 0)
            db.commit()
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
                    # B4 修复：倍数真实读取 task_retry_multiplier（原硬编码等价于恒 2）
                    exp_base=settings.task_retry_multiplier,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_parse(document_id=document_id, payload=spec.payload)
        except RetryError as exc:
            # 重试用尽：把最后一个底层异常抛出，由外层 except 落库
            if (
                exc.last_attempt is not None
                and exc.last_attempt.exception() is not None
            ):
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        # 3. 推进到 completed + 回填 storage_key（M1 §4.1）
        document = db.get(Document, document_id)
        assert document is not None  # 同 session 内不可能消失
        document.status = "completed"
        document.error_code = None
        document.error_detail = None
        document.retry_count = max(attempt_count - 1, 0)
        document.storage_key = build_storage_key(
            org_id=document.org_id,
            doc_id=document_id,
            filename_hash=document.filename_hash,
        )
        db.commit()

        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            retry_count=document.retry_count,
            storage_key_present=True,
        ).info("document_parse_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        _mark_failed(db, document_id, exc, spec.trace_id)
    finally:
        db.close()


async def _do_parse(*, document_id: UUID, payload: Mapping[str, object]) -> None:
    """真实解析：PDF → MinerU 云 API → 产物落存储层。

    - 产物键：``{org_id}/{doc_id}/parse/{full.md, content_list.json}``
      （与原文件同前缀族，继承 ADR-0003 租户隔离；Sprint 6 批次 B 的
      Chunk 证据节点与批次 B 的 LangExtract 以此为输入）；
    - docx / csv：**跳过结构化解析**（S10 / S9 承接，plan §15.3），
      照常推进 completed——与 v1.0.0 行为一致，仅由日志显式登记。

    v1.1.0 后续批次（原「Sprint 3 后段」计划顺延）：
    1. ``entity_relation_extract_v1`` 提示词驱动的实体抽取（批次 B）；
    2. ADR-0002 三段式写入（PG ``kg_versions`` 真源 → Neo4j ``MERGE``）。
    """
    settings = get_settings()
    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        if document.mime_type != "application/pdf":
            logger.bind(
                trace_id=str(payload.get("trace_id", "")),
                document_id=str(document_id),
                mime_type=document.mime_type,
            ).info("document_parse_skipped_unsupported_parser")
            return

        storage = get_storage()
        source_key = build_storage_key(
            org_id=document.org_id,
            doc_id=document_id,
            filename_hash=document.filename_hash,
        )
        content = storage.get(source_key, org_id=document.org_id)

        # 文件名不使用原始上传名（M5 §4.5：文件名不得明文外发）
        client = MineruClient(
            base_url=settings.mineru_api_base,
            token=settings.mineru_token,
            model_version=settings.mineru_model_version,
            language=settings.mineru_language,
            request_timeout_seconds=settings.mineru_request_timeout_seconds,
            poll_interval_seconds=settings.mineru_poll_interval_seconds,
            poll_timeout_seconds=settings.mineru_poll_timeout_seconds,
        )
        result = await client.parse_pdf(
            content=content, display_name=f"{document_id}.pdf"
        )

        storage.put(
            build_parse_artifact_key(
                org_id=document.org_id, doc_id=document_id, filename="full.md"
            ),
            result.markdown.encode("utf-8"),
        )
        storage.put(
            build_parse_artifact_key(
                org_id=document.org_id, doc_id=document_id, filename="content_list.json"
            ),
            result.content_list_json.encode("utf-8"),
        )
        logger.bind(
            trace_id=str(payload.get("trace_id", "")),
            document_id=str(document_id),
            markdown_bytes=len(result.markdown.encode("utf-8")),
        ).info("document_parse_artifacts_stored")
    finally:
        db.close()


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
