"""任务执行体注册表（task_type → 真正的处理函数）。

**设计动机**：TaskManager 只负责「注册 + 调度 + 回收」，**不**关心
具体业务逻辑；新增一种任务类型只需在本注册表中登记一项，TaskManager
代码无需改动。

已登记（v1.1.0 批次 A 起；批次 B 扩展）：
- ``document.parse``：PDF 经 MinerU 云解析 → 产物落存储层（M1 → M2 衔接）；
  docx / csv 的结构化解析分别由 Sprint 10 / Sprint 9 承接（plan §15.3），
  本阶段跳过解析但照常推进状态机。
- ``document.extract``（批次 B）：从 ``full.md`` 抽取实体 + 关系（LangExtract）；
  产物落存储层 ``{org_id}/{doc_id}/extract/{entities,relations}.json``。
- ``kg.build``（批次 B）：三段式写入 Neo4j（ADR-0002 §3.1），
  并把状态机迁移到 ``kg_versions`` 表（ADR-0002 §3.2 PG 真源）。
- ``risk.detect``（Sprint 7.1 批次 A）：M4 关联交易疑点检出
  （共享法人 / 共享地址两跳，作用域是 ``kg_version`` 而非单文档）。
  **注**：本仓库当前**没有**跨阶段投递——``pipeline_stages`` 只决定上传时提交
  哪一个**首个**阶段，后续阶段由脚本 / 人工按序驱动（根因：``TaskManager``
  依赖请求级 ``BackgroundTasks``，请求结束即失效，无法在阶段间续投）。
  已登记为缺口，承接 Sprint 8。
"""

from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Mapping
from dataclasses import replace
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
from app.core.errors import AppError, ErrorCode
from app.db.models import AffiliationTask, Document, KgVersion
from app.db.session import SessionLocal
from app.services.affiliation import (
    mark_task_failed,
    mark_task_processing,
    persist_detection_result,
)
from app.services.extraction import LangextractClient, LangextractError
from app.services.extraction.langextract import ExtractionResult
from app.services.graphs import GraphUnavailableError
from app.services.kg import ThreeStageKgBuilder
from app.services.kg.builder import KgDocumentRef
from app.services.kg.versioning import KgVersioningService
from app.services.parsing import MineruApiError, MineruClient
from app.services.parsing.page_index import build_page_index
from app.storage import (
    build_extract_artifact_key,
    build_kg_artifact_key,
    build_parse_artifact_key,
    build_storage_key,
    get_storage,
)
from app.tasks.types import TaskExecutorFn, TaskSpec

#: 可重试的异常类型：第三方 IO 错误（HTTP / MinerU 业务失败 / 网络与文件系统）。
#: 业务校验失败（ValueError 等）**不**重试。
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
    httpx.HTTPError,
    MineruApiError,
    LangextractError,
    GraphUnavailableError,
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

        # parser_provider（接缝 3）：当前唯一档位 mineru_cloud；
        # 未知档位显式报错，不静默回退（错误分类由 MineruApiError 承载，
        # 属可重试集合——配置错误会在重试用尽后 failed 并落 error_detail）。
        if settings.parser_provider != "mineru_cloud":
            raise MineruApiError(
                f"未知 parser_provider={settings.parser_provider!r}"
                "（当前仅支持 'mineru_cloud'）"
            )

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


# ---------------------------------------------------------------------------
# document.extract（Sprint 5 批次 B：LangExtract 抽取）
# ---------------------------------------------------------------------------


async def document_extract_executor(spec: TaskSpec) -> None:
    """``document.extract`` 执行体。

    输入：``full.md``（来自 storage ``build_parse_artifact_key(..., "full.md")``）；
    输出：``entities.json`` / ``relations.json`` 入 storage；
    状态机：``extract_status`` 字段由 ``None`` → ``processing`` → ``completed``，
    失败 → ``failed``；**整体** ``documents.status`` 不在此阶段被改写（保留为
    ``processing`` 由下一阶段 ``kg.build`` 接力）。
    """
    settings = get_settings()
    document_id = UUID(spec.payload["document_id"])

    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).error(
                "document_extract_missing_record"
            )
            return
        if document.extract_status == "completed":
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).info(
                "document_extract_skipped_already_completed"
            )
            return

        document.extract_status = "processing"
        db.commit()

        attempt_count = 0

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            document.extract_retry_count = max(attempt_count - 1, 0)
            db.commit()
            logger.bind(
                trace_id=spec.trace_id,
                document_id=str(document_id),
                attempt=attempt_count,
            ).warning("document_extract_retry")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.task_retry_max_attempts),
                wait=wait_exponential(
                    multiplier=settings.task_retry_initial_seconds,
                    exp_base=settings.task_retry_multiplier,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_extract(
                        document_id=document_id,
                        trace_id=spec.trace_id,
                        payload=spec.payload,
                    )
        except RetryError as exc:
            if (
                exc.last_attempt is not None
                and exc.last_attempt.exception() is not None
            ):
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        document = db.get(Document, document_id)
        assert document is not None
        document.extract_status = "completed"
        document.extract_retry_count = max(attempt_count - 1, 0)
        document.error_code = None
        document.error_detail = None
        db.commit()

        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            retry_count=document.extract_retry_count,
        ).info("document_extract_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        _mark_stage_failed(
            db,
            document_id,
            exc,
            spec.trace_id,
            stage="extract",
            status_field="extract_status",
            retry_field="extract_retry_count",
        )
    finally:
        db.close()


def _read_optional_parse_artifact(
    *, org_id: UUID, doc_id: UUID, filename: str
) -> bytes | None:
    """读解析产物；不存在 / 读失败 → ``None``。

    ``content_list.json`` 是**可选**输入：docx / csv 走「跳过解析」路径时本就没有它，
    缺了不应让抽取失败——只是页码判不出来（``page = None``），降级由调用方登记。
    """
    key = build_parse_artifact_key(org_id=org_id, doc_id=doc_id, filename=filename)
    try:
        return get_storage().get(key, org_id=org_id)
    except Exception as exc:  # noqa: BLE001 - 缺产物是预期内的降级分支
        logger.bind(
            document_id=str(doc_id),
            artifact=filename,
            exc_type=type(exc).__name__,
        ).warning("parse_artifact_unavailable")
        return None


def _apply_page_numbers(
    *,
    result: ExtractionResult,
    markdown: str,
    content_list_raw: bytes | None,
    document_id: UUID,
) -> ExtractionResult:
    """给抽取产物的每个 chunk 回填页码（Sprint 6 批次 A-2，best-effort）。

    ``content_list.json`` 缺失 / 非法 / 对齐 0 命中时**不**失败：chunk 的 ``page``
    保持 ``None``，由下游按「无页码」处理（**不**兜底成 1）。
    """
    if content_list_raw is None:
        logger.bind(document_id=str(document_id)).warning(
            "page_index_skipped_content_list_missing"
        )
        return result

    try:
        content_list = json.loads(content_list_raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 产物损坏是数据问题，不阻断抽取
        logger.bind(document_id=str(document_id), exc_type=type(exc).__name__).warning(
            "page_index_skipped_invalid_content_list"
        )
        return result

    if not isinstance(content_list, list):
        logger.bind(document_id=str(document_id)).warning(
            "page_index_skipped_content_list_not_list"
        )
        return result

    index = build_page_index(markdown, content_list)
    logger.bind(
        document_id=str(document_id),
        page_spans=len(index.spans),
        matched=index.matched,
        total=index.total,
        coverage=index.coverage,
    ).info("page_index_built")

    return replace(
        result,
        chunks=[
            replace(chunk, page=index.locate_range(chunk.char_start, chunk.char_end))
            for chunk in result.chunks
        ],
    )


async def _do_extract(
    *, document_id: UUID, trace_id: str, payload: Mapping[str, object]
) -> None:
    """真实抽取：读 full.md → LangExtract → 写 entities / relations / chunks JSON。"""
    storage = get_storage()
    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        full_md_key = build_parse_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="full.md"
        )
        try:
            markdown_bytes = storage.get(full_md_key, org_id=document.org_id)
        except Exception as exc:  # noqa: BLE001
            raise LangextractError(
                f"读取 full.md 失败: key={full_md_key}: {exc}"
            ) from exc
        markdown = markdown_bytes.decode("utf-8")

        client = LangextractClient.from_settings()
        # Sprint 7.0：``extraction_engine='llm'`` 时本函数是**同步阻塞**的（逐 chunk
        # 串行调 LLM，一份年报可跑数分钟）。放进工作线程，避免占住事件循环——
        # 否则一次抽取会把整个 uvicorn 的请求处理全卡住。异常语义不变。
        result = await asyncio.to_thread(
            client.extract_entities_relations,
            document_id=document_id,
            full_md_text=markdown,
            trace_id=UUID(trace_id) if isinstance(trace_id, str) else trace_id,
        )

        # Sprint 6 批次 A-2：用 content_list.json 给 chunk 判页（best-effort，失配 → None）
        result = _apply_page_numbers(
            result=result,
            markdown=markdown,
            content_list_raw=_read_optional_parse_artifact(
                org_id=document.org_id,
                doc_id=document_id,
                filename="content_list.json",
            ),
            document_id=document_id,
        )

        entities_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="entities.json"
        )
        relations_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="relations.json"
        )
        entities_payload = json.dumps(
            result.to_json_dict()["entities"], ensure_ascii=False
        ).encode("utf-8")
        relations_payload = json.dumps(
            result.to_json_dict()["relations"], ensure_ascii=False
        ).encode("utf-8")
        # Sprint 6 批次 A-1：切块产物落盘，供 kg.build 建 :Chunk 证据节点
        chunks_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="chunks.json"
        )
        chunks_payload = json.dumps(
            result.to_json_dict()["chunks"], ensure_ascii=False
        ).encode("utf-8")
        storage.put(entities_key, entities_payload)
        storage.put(relations_key, relations_payload)
        storage.put(chunks_key, chunks_payload)

        paged = sum(1 for chunk in result.chunks if chunk.page is not None)
        logger.bind(
            trace_id=trace_id,
            document_id=str(document_id),
            entity_count=len(result.entities),
            relation_count=len(result.relations),
            chunk_count=len(result.chunks),
            chunk_with_page=paged,
        ).info("document_extract_artifacts_stored")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# kg.build（Sprint 5 批次 B：ADR-0002 三段式 Neo4j 写入 + kg_versions PG 真源）
# ---------------------------------------------------------------------------


async def kg_build_executor(spec: TaskSpec) -> None:
    """``kg.build`` 执行体：读 entities / relations → 三段式 Neo4j → 回填 kg_versions。

    状态机（kg_versions PG 真源，ADR-0002 §3.2）：
    ``pending → building → ready`` / 失败 → ``failed``。
    """
    settings = get_settings()
    document_id = UUID(spec.payload["document_id"])

    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).error(
                "kg_build_missing_record"
            )
            return

        # 0. 创建 kg_version pending 行（首次执行）
        kg_version_id_str = spec.payload.get("kg_version_id")
        versioning = KgVersioningService(db)
        if kg_version_id_str:
            kg_version_id = UUID(kg_version_id_str)
        elif document.kg_version_id is not None:
            kg_version_id = document.kg_version_id
        else:
            # 全新构建：version = "v-{trace_id前8}"，per_org 策略下同 org 唯一
            new_record = versioning.create_pending(
                org_id=document.org_id,
                version=f"v-{spec.trace_id[:8]}",
                source_doc_ids=[document_id],
                trace_id=UUID(spec.trace_id)
                if isinstance(spec.trace_id, str)
                else spec.trace_id,
            )
            kg_version_id = new_record.id
            document.kg_version_id = kg_version_id
            db.commit()

        versioning.mark_building(kg_version_id)
        # 无论新建还是复用，都回填 documents.kg_version_id（阶段列，不进契约）
        document.kg_version_id = kg_version_id
        document.kg_build_status = "processing"
        db.commit()

        attempt_count = 0

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            document.kg_build_retry_count = max(attempt_count - 1, 0)
            db.commit()
            logger.bind(
                trace_id=spec.trace_id,
                document_id=str(document_id),
                attempt=attempt_count,
            ).warning("kg_build_retry")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.task_retry_max_attempts),
                wait=wait_exponential(
                    multiplier=settings.task_retry_initial_seconds,
                    exp_base=settings.task_retry_multiplier,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_kg_build(
                        document_id=document_id,
                        kg_version_id=kg_version_id,
                        payload=spec.payload,
                    )
        except RetryError as exc:
            if (
                exc.last_attempt is not None
                and exc.last_attempt.exception() is not None
            ):
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        # 成功：把整文档 status 推进 completed（pipeline 最后一段）
        document = db.get(Document, document_id)
        assert document is not None
        document.kg_build_status = "completed"
        document.kg_build_retry_count = max(attempt_count - 1, 0)
        document.status = "completed"
        document.error_code = None
        document.error_detail = None
        # storage_key 在 parse 阶段已填，这里不再写
        db.commit()

        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            kg_version_id=str(kg_version_id),
        ).info("kg_build_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        # 标记 kg_version failed + 阶段级 failed + 整体 failed
        _mark_kg_build_failed(db, document_id, exc, spec.trace_id)
    finally:
        db.close()


async def _do_kg_build(
    *,
    document_id: UUID,
    kg_version_id: UUID,
    payload: Mapping[str, object],
) -> None:
    """真实加载：从 entities / relations JSON 读 → ThreeStageKgBuilder 写入 Neo4j。"""
    storage = get_storage()
    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        kg_version = db.get(KgVersion, kg_version_id)
        if kg_version is None:
            raise GraphUnavailableError(f"kg_version 不存在: id={kg_version_id}")

        entities_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="entities.json"
        )
        relations_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="relations.json"
        )
        entities_raw = storage.get(entities_key, org_id=document.org_id)
        relations_raw = storage.get(relations_key, org_id=document.org_id)
        entities = json.loads(entities_raw.decode("utf-8"))
        relations = json.loads(relations_raw.decode("utf-8"))

        # Sprint 6 批次 A-1：chunks.json 是 Chunk 证据层的**唯一**输入。
        # 缺失即 pipeline 断裂（extract 阶段没跑或产物损坏）——**显式报错**，
        # 不静默降级为「只写实体」：那样 go/no-go 判据①会以一个看不出原因的
        # 「:Chunk 数 = 0」失败（plan §4.4：数据质量故障不得伪装成正常结论）。
        chunks_key = build_extract_artifact_key(
            org_id=document.org_id, doc_id=document_id, filename="chunks.json"
        )
        try:
            chunks_raw = storage.get(chunks_key, org_id=document.org_id)
        except Exception as exc:  # noqa: BLE001 - 统一包装为可重试业务错误
            raise LangextractError(
                f"读取 chunks.json 失败（Chunk 证据层缺失）: key={chunks_key}: {exc}"
            ) from exc
        chunks = json.loads(chunks_raw.decode("utf-8"))
        if not isinstance(chunks, list):
            raise LangextractError(
                f"chunks.json 结构非法（应为 list）: key={chunks_key}, "
                f"实际={type(chunks).__name__}"
            )

        builder = ThreeStageKgBuilder()
        from app.services.kg.builder import KgBuildRequest

        stats = builder.build(
            KgBuildRequest(
                org_id=document.org_id,
                version=kg_version.version,
                entities=entities,
                relations=relations,
                chunks=chunks,
                document=KgDocumentRef(
                    doc_id=document_id, acl_scope=document.acl_scope
                ),
                trace_id=UUID(str(payload.get("trace_id", "")))
                if payload.get("trace_id")
                else kg_version.trace_id,
            )
        )

        versioning = KgVersioningService(db)
        versioning.mark_ready(
            kg_version_id,
            entity_count=stats.entity_count,
            relation_count=stats.relation_count,
        )

        logger.bind(
            trace_id=str(payload.get("trace_id", "")),
            document_id=str(document_id),
            kg_version_id=str(kg_version_id),
            entity_count=stats.entity_count,
            relation_count=stats.relation_count,
            chunk_count=stats.chunk_count,
            evidence_edge_count=stats.evidence_edge_count,
        ).info("kg_build_artifacts_loaded")
    finally:
        db.close()


def _mark_stage_failed(
    db: Session,
    document_id: UUID,
    exc: Exception,
    trace_id: str,
    *,
    stage: str,
    status_field: str,
    retry_field: str,
) -> None:
    """阶段级失败标记：仅改阶段列，不动整体 status（由 pipeline 末段统一收口）。"""
    document = db.get(Document, document_id)
    if document is None:
        return
    setattr(document, status_field, "failed")
    document.error_code = ErrorCode.INTERNAL_ERROR.value
    document.error_detail = "".join(
        traceback.format_exception_only(type(exc), exc)
    ).strip()
    db.commit()
    logger.bind(
        trace_id=trace_id,
        document_id=str(document_id),
        stage=stage,
        error_code=document.error_code,
        exc_type=type(exc).__name__,
    ).error("pipeline_stage_failed")


def _mark_kg_build_failed(
    db: Session, document_id: UUID, exc: Exception, trace_id: str
) -> None:
    """kg.build 失败：阶段级 + 整体 status + kg_version 行同步 failed。"""
    document = db.get(Document, document_id)
    if document is None:
        return
    document.kg_build_status = "failed"
    document.status = "failed"
    document.error_code = ErrorCode.INTERNAL_ERROR.value
    error_detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    document.error_detail = error_detail
    db.commit()
    # 同步 kg_version 表
    if document.kg_version_id is not None:
        versioning = KgVersioningService(db)
        try:
            versioning.mark_failed(
                document.kg_version_id,
                error_code=document.error_code,
                error_detail=error_detail,
            )
        except LookupError:
            pass
    logger.bind(
        trace_id=trace_id,
        document_id=str(document_id),
        error_code=document.error_code,
        exc_type=type(exc).__name__,
    ).error("kg_build_failed")


# ---------------------------------------------------------------------------
# risk.detect（Sprint 7.1 批次 A：M4 关联交易疑点，接缝 4 管线第四段）
# ---------------------------------------------------------------------------


async def risk_detect_executor(spec: TaskSpec) -> None:
    """``risk.detect`` 执行体：在 **kg_version** 作用域上跑 M4 规则疑点。

    与其它三段的关键差异：

    - **作用域是 kg_version 不是单文档**：共享法人 / 共享地址只有**跨公司**才成立，
      单文档内自环已被排除（``graphs.py`` 的 ``s1.id < s2.id``）；
    - **只在 ``kg_versions.status = 'ready'`` 上跑**（ADR-0002：只有 ready 版本可被消费）；
      未建图 / 版本未 ready → **显式跳过并记账**（``risk_detect_skipped``），
      **不**当成「无嫌疑」；
    - **本批次不落 PG**：``affiliation_suspicions`` 表属 Sprint 8 批次 B，当前产物
      = 结构化日志 + ``{org_id}/{doc_id}/kg/suspicions.json``；
    - Neo4j 不可达 → :class:`GraphUnavailableError` 走 tenacity，重试用尽后
      由框架层落 failed——**绝不**降级为「没有疑点」。
    """
    settings = get_settings()
    document_id = UUID(spec.payload["document_id"])

    db: Session = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).error(
                "risk_detect_missing_record"
            )
            return

        kg_version_id = document.kg_version_id
        if kg_version_id is None:
            logger.bind(trace_id=spec.trace_id, document_id=str(document_id)).warning(
                "risk_detect_skipped_no_kg_version"
            )
            return
        kg_version = db.get(KgVersion, kg_version_id)
        if kg_version is None or kg_version.status != "ready":
            logger.bind(
                trace_id=spec.trace_id,
                document_id=str(document_id),
                kg_version_id=str(kg_version_id),
                status=kg_version.status if kg_version else None,
            ).warning("risk_detect_skipped_version_not_ready")
            return
        version = kg_version.version

        attempt_count = 0

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            logger.bind(
                trace_id=spec.trace_id,
                document_id=str(document_id),
                attempt=attempt_count,
            ).warning("risk_detect_retry")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.task_retry_max_attempts),
                wait=wait_exponential(
                    multiplier=settings.task_retry_initial_seconds,
                    exp_base=settings.task_retry_multiplier,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_risk_detect(
                        document_id=document_id,
                        org_id=document.org_id,
                        kg_version=version,
                        payload=spec.payload,
                    )
        except RetryError as exc:
            if (
                exc.last_attempt is not None
                and exc.last_attempt.exception() is not None
            ):
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            kg_version=version,
        ).info("risk_detect_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        # risk.detect 是管线末段且**没有**自己的阶段列（documents 表无 risk_detect_status）；
        # 借用 kg_build_status 会把「疑点检出失败」标成「建图失败」——**错标比不标更糟**，
        # 故直接把整体 status 推进 failed（末段语义与 kg.build 一致）。
        document = db.get(Document, document_id)
        if document is None:
            return
        document.status = "failed"
        document.error_code = ErrorCode.INTERNAL_ERROR.value
        document.error_detail = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        db.commit()
        logger.bind(
            trace_id=spec.trace_id,
            document_id=str(document_id),
            error_code=document.error_code,
            exc_type=type(exc).__name__,
        ).error("risk_detect_failed")
    finally:
        db.close()


async def _do_risk_detect(
    *,
    document_id: UUID,
    org_id: UUID,
    kg_version: str,
    payload: Mapping[str, object],
) -> None:
    """跑一次疑点检出：结果进日志 + ``kg/suspicions.json`` 产物。

    疑点**逐条**打点（``affiliation_suspicion_detected``）——汇总一条日志会让
    「到底哪几家公司、凭哪段原文被判成疑点」在真机上无法核对。
    """
    from app.services.kg import AffiliationService

    trace_id = payload.get("trace_id")
    suspicions = AffiliationService().detect(
        kg_version=kg_version,
        org_id=org_id,
        trace_id=trace_id,
    )

    for suspicion in suspicions:
        logger.bind(
            trace_id=str(trace_id) if trace_id else None,
            document_id=str(document_id),
            kg_version=kg_version,
            suspicion_type=suspicion.suspicion_type,
            severity=suspicion.severity,
            entity_names=list(suspicion.entity_names),
            evidence_chunk_ids=[item.chunk_id for item in suspicion.evidence],
        ).info("affiliation_suspicion_detected")

    artifact_key = build_kg_artifact_key(
        org_id=org_id, doc_id=document_id, filename="suspicions.json"
    )
    payload_json = json.dumps(
        {
            "kg_version": kg_version,
            "document_id": str(document_id),
            "trace_id": str(trace_id) if trace_id else None,
            "total": len(suspicions),
            "suspicions": [item.to_dict() for item in suspicions],
        },
        ensure_ascii=False,
        indent=2,
    )
    # 注意：``put(key, data)`` **不**接 ``org_id``（租户隔离靠 key 前缀，ADR-0003 §3.5）
    get_storage().put(artifact_key, payload_json.encode("utf-8"))
    logger.bind(
        trace_id=str(trace_id) if trace_id else None,
        document_id=str(document_id),
        kg_version=kg_version,
        total=len(suspicions),
        artifact_key_present=True,
    ).info("risk_detect_artifacts_written")


async def affiliation_detect_executor(spec: TaskSpec) -> None:
    """执行 ``affiliation.detect``：跑 M4 规则算法并把疑点**落库**（Sprint 7.2 批次 B）。

    与 ``risk_detect_executor`` 的差异——**两者不可合并**：

    - **任务载体**：本执行体以 ``affiliation_tasks.id`` 为主键（一次检测覆盖**多份**
      文档，批次 B 决策 **B8**）；``risk.detect`` 以 ``documents.id`` 为主键（单文档）；
    - **产物落点**：本执行体写 ``affiliation_suspicions`` 表（对外经端点可读、可复核）；
      ``risk.detect`` 仍只写日志 + ``suspicions.json``；
    - **触发方式**：本执行体由 ``POST /affiliation/detect`` 显式提交；``risk.detect``
      挂在上传管线的末段（``settings.pipeline_stages``）。

    无 active ``kg_version`` → 任务置 **failed**（``KG_VERSION_NOT_ACTIVE``）：
    「没有可读的版本」不等于「没有疑点」，按 ADR-0002 §3.2 **不**静默产出 0 条。
    """
    settings = get_settings()
    task_id = UUID(str(spec.payload.get("affiliation_task_id")))

    db: Session = SessionLocal()
    attempt_count = 0
    try:
        task = db.get(AffiliationTask, task_id)
        if task is None:
            logger.bind(trace_id=spec.trace_id, task_id=str(task_id)).error(
                "affiliation_detect_missing_record"
            )
            return

        mark_task_processing(session=db, task=task)

        def _on_retry(retry_state: Any) -> None:  # noqa: ANN401
            nonlocal attempt_count
            attempt_count = retry_state.attempt_number
            # 有列必须有消费者：retry_count 在每次重试时真实写回（H8）
            task.retry_count = max(attempt_count - 1, 0)
            db.commit()
            logger.bind(
                trace_id=spec.trace_id,
                task_id=str(task_id),
                attempt=attempt_count,
            ).warning("affiliation_detect_retry")

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.task_retry_max_attempts),
                wait=wait_exponential(
                    multiplier=settings.task_retry_initial_seconds,
                    exp_base=settings.task_retry_multiplier,
                ),
                retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
                reraise=True,
            ):
                with attempt:
                    _on_retry(attempt.retry_state)
                    await _do_affiliation_detect(
                        task=task, session=db, trace_id=spec.trace_id
                    )
        except RetryError as exc:
            if (
                exc.last_attempt is not None
                and exc.last_attempt.exception() is not None
            ):
                raise exc.last_attempt.exception() from exc  # type: ignore[misc]
            raise

        logger.bind(
            trace_id=spec.trace_id,
            task_id=str(task_id),
            total=(task.result_summary or {}).get("total"),
        ).info("affiliation_detect_completed")
    except Exception as exc:  # noqa: BLE001 - 框架层吞错并落库
        db.rollback()
        row = db.get(AffiliationTask, task_id)
        if row is None:
            return
        code = (
            exc.code.value
            if isinstance(exc, AppError)
            else ErrorCode.INTERNAL_ERROR.value
        )
        mark_task_failed(
            session=db,
            task=row,
            error_code=code,
            # error_detail 属**敏感**字段：只留异常首行，**不**含原文 / 证据内容
            error_detail="".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip(),
        )
        logger.bind(
            trace_id=spec.trace_id,
            task_id=str(task_id),
            error_code=code,
            exc_type=type(exc).__name__,
        ).error("affiliation_detect_failed")
    finally:
        db.close()


async def _do_affiliation_detect(
    *,
    task: AffiliationTask,
    session: Session,
    trace_id: str,
) -> None:
    """跑一次检测并落库（ ``_do_*`` 家族：真正干活的那一层）。"""
    from app.services.kg import AffiliationService

    # ADR-0002：只消费 ready（= active）版本；这里读 PG 真源，不用 Neo4j 镜像兜底
    record = KgVersioningService(session).get_active(org_id=task.org_id)
    if record is None:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"reason": "no_active_kg_version", "org_id": str(task.org_id)},
        )

    suspicions = AffiliationService().detect(
        kg_version=record.version,
        org_id=task.org_id,
        trace_id=trace_id,
    )

    # 疑点**逐条**打点：汇总一条日志会让「哪几家公司、凭哪段原文被判成疑点」无法核对
    for suspicion in suspicions:
        logger.bind(
            trace_id=trace_id,
            task_id=str(task.id),
            kg_version=record.version,
            suspicion_type=suspicion.suspicion_type,
            severity=suspicion.severity,
            entity_names=list(suspicion.entity_names),
            evidence_chunk_ids=[item.chunk_id for item in suspicion.evidence],
        ).info("affiliation_suspicion_detected")

    total = persist_detection_result(
        session=session,
        task=task,
        suspicions=suspicions,
        kg_version=record.version,
        trace_id=trace_id,
    )
    logger.bind(
        trace_id=trace_id,
        task_id=str(task.id),
        kg_version=record.version,
        total=total,
    ).info("affiliation_detect_persisted")


#: 任务类型 → 执行体的注册表。新增任务类型在此登记即可。
EXECUTOR_REGISTRY: dict[str, TaskExecutorFn] = {
    "document.parse": document_parse_executor,
    "document.extract": document_extract_executor,
    "kg.build": kg_build_executor,
    "risk.detect": risk_detect_executor,
    "affiliation.detect": affiliation_detect_executor,
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
