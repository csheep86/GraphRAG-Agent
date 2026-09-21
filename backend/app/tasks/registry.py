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
"""

from __future__ import annotations

import asyncio
import json
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
from app.db.models import Document, KgVersion
from app.db.session import SessionLocal
from app.services.extraction import LangextractClient, LangextractError
from app.services.graphs import GraphUnavailableError
from app.services.kg import ThreeStageKgBuilder
from app.services.kg.versioning import KgVersioningService
from app.services.parsing import MineruApiError, MineruClient
from app.storage import (
    build_extract_artifact_key,
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


async def _do_extract(
    *, document_id: UUID, trace_id: str, payload: Mapping[str, object]
) -> None:
    """真实抽取：读 full.md → LangExtract → 写 entities / relations JSON。"""
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
        result = client.extract_entities_relations(
            document_id=document_id,
            full_md_text=markdown,
            trace_id=UUID(trace_id) if isinstance(trace_id, str) else trace_id,
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
        storage.put(entities_key, entities_payload)
        storage.put(relations_key, relations_payload)

        logger.bind(
            trace_id=trace_id,
            document_id=str(document_id),
            entity_count=len(result.entities),
            relation_count=len(result.relations),
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

        builder = ThreeStageKgBuilder()
        from app.services.kg.builder import KgBuildRequest

        stats = builder.build(
            KgBuildRequest(
                org_id=document.org_id,
                version=kg_version.version,
                entities=entities,
                relations=relations,
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


#: 任务类型 → 执行体的注册表。新增任务类型在此登记即可。
EXECUTOR_REGISTRY: dict[str, TaskExecutorFn] = {
    "document.parse": document_parse_executor,
    "document.extract": document_extract_executor,
    "kg.build": kg_build_executor,
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
