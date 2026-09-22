"""M1 文档接入（阶段九：上传 + 异步任务注册；Sprint 5 批次 A：真实落盘）。

实现边界：
- ✅ 上传：MIME 白名单校验（415）→ 大小上限校验（413）→ **文件写入存储抽象层**
  （Sprint 5 批次 A，`app.storage`）→ 落 `documents` 记录（`pending`）；
- ✅ 异步任务：通过 :class:`app.tasks.TaskManager` 注册 ``document.parse`` 执行体；
- ✅ 状态：读 PostgreSQL / SQLite 返回，跨租户 403、不存在 404；
- ✅ 列表（批次 C）：`GET /documents`，按 `org_id` 强制过滤，支持 `q` / `status` /
  `page` / `page_size`，返回 `DocumentListResponse`；
- ✅ `storage_key` 在解析 `completed` 时回填（M1 §4.1；executor 职责）。
  文件本体在上传时即落盘（Starlette 临时文件随请求销毁，异步任务须能从
  存储层取回原始字节）。

异步任务回收（``pending / processing → failed (TASK_INTERRUPTED)``）由
:func:`app.tasks.recover_orphan_tasks` 在 lifespan startup 触发（ADR-0001 §3.2）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import UploadFile
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.core.config import get_settings
from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode
from app.db.models import Document, KgVersion
from app.schemas.document import (
    DocumentError,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatusResponse,
    UploadResponse,
    mime_to_file_type,
)
from app.storage import build_storage_key, get_storage
from app.tasks.manager import TaskManager, TaskSpec
from app.tasks.pipeline import first_pipeline_stage

_UPLOAD_READ_CHUNK = 1024 * 1024

#: 列表接口默认 / 上限（route 层有 Query 验证；此处保留常量便于 service 单测与文档对齐）
_DEFAULT_PAGE_SIZE = 10
_MAX_PAGE_SIZE = 100

#: 进度映射：解析进度不可精确估计的场景返回 None，而不是编造数字
_PROGRESS_BY_STATUS: dict[str, float | None] = {
    "pending": 0.0,
    "processing": None,
    "completed": 1.0,
    "failed": None,
}


def hash_filename(filename: str) -> str:
    """原始文件名 SHA-256（M5 §4.5：文件名不得以原文落库 / 落日志）。"""
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DocumentListQuery:
    """`GET /documents` 查询参数集合（service 层契约，route 层负责解析/校验）。"""

    q: str | None = None
    status: str | None = None
    page: int = 1
    page_size: int = _DEFAULT_PAGE_SIZE


def list_documents(
    *,
    session: Session,
    identity: Identity,
    query: DocumentListQuery,
    trace_id: str,
) -> DocumentListResponse:
    """返回当前租户下的文档列表（`GET /documents`，Sprint 5 批次 C）。

    行为约束（CODEBUDDY.md 契约同步铁律 + ADR-0003）：
    1. ``org_id`` 强制来自认证态，**不接受** body / query 覆盖；
    2. ``q`` 匹配 ``filename_hash`` 前缀 —— SHA-256 hex 不可逆，
       演示场景量小（<10 万）可接受前缀 LIKE 性能；规模扩增需
       ADR-0004 §3 留位新增 ``filename_display`` 列；
    3. ``status`` 仅作 SQL 过滤，不做状态机迁移；
    4. 分页用纯 Python 切片（避免 SQL OFFSET 大表性能问题）；
       演示量级适用，**不**透出 Stripe-like cursor。
    """
    stmt = select(Document).where(Document.org_id == identity.org_id)

    if query.status:
        stmt = stmt.where(Document.status == query.status)

    if query.q:
        # `filename_hash` 是 hex 字符串；做大小写不敏感的前缀匹配
        q_normalized = query.q.strip().lower()
        if q_normalized:
            stmt = stmt.where(Document.filename_hash.like(f"{q_normalized}%"))

    # 取全量再做 Python 分页 —— 演示量级（< 1000）足够；超阈值再考虑 COUNT 子查询 + 关键索引
    rows = session.scalars(stmt.order_by(Document.created_at.desc())).all()
    total = len(rows)

    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    page_rows = rows[start:end]

    # 一次性查全当前租户的 (kg_version_id → entity_count) 映射，避免 N+1
    version_ids = {row.kg_version_id for row in rows if row.kg_version_id is not None}
    entity_counts_by_version: dict[UUID, int] = {}
    if version_ids:
        count_stmt = (
            select(KgVersion.id, KgVersion.entity_count)
            .where(KgVersion.id.in_(version_ids))
            .where(KgVersion.org_id == identity.org_id)
        )
        for version_id, entity_count in session.execute(count_stmt).all():
            entity_counts_by_version[version_id] = int(entity_count or 0)

    items = [_build_list_item(row, entity_counts_by_version) for row in page_rows]

    return DocumentListResponse(
        total=total,
        items=items,
        page=query.page,
        page_size=query.page_size,
        trace_id=trace_id,
    )


def _build_list_item(
    document: Document,
    entity_counts_by_version: dict[UUID, int],
) -> DocumentListItem:
    """构造单条列表结果（service 层 helper，避免 list_documents 内部循环过深）。"""
    created_at = document.created_at
    uploaded_at_str = created_at.isoformat() if created_at is not None else ""
    time_label = _format_time_label(created_at)

    entity_count: int | None = None
    if document.kg_version_id is not None:
        entity_count = entity_counts_by_version.get(document.kg_version_id)

    return DocumentListItem(
        id=document.id,
        filename=document.filename_hash,
        file_type=mime_to_file_type(document.mime_type),
        status=document.status,  # type: ignore[arg-type]
        entity_count=entity_count,
        uploaded_at=uploaded_at_str,
        time_label=time_label,
        task_id=document.id,
        trace_id=str(document.trace_id) if document.trace_id else "",
    )


def _format_time_label(created_at) -> str:
    """把 ``created_at`` 格式化为前端表格可展示的相对时间文案。

    规则（对齐前端原 mock 行为，便于前端表格组件零改动）：
    - 同一天 → ``HH:MM``
    - 昨天 → ``昨天 HH:MM``
    - 更早 → ``YYYY-MM-DD``

    当前实现仅含 ``HH:MM`` 一种格式（演示场景稳定，避免 SSR/CSR 时区差）。
    """
    if created_at is None:
        return ""
    return created_at.strftime("%H:%M")


# 重新暴露常量给 route 层 Query 校验
PAGE_SIZE_DEFAULT = _DEFAULT_PAGE_SIZE
PAGE_SIZE_MAX = _MAX_PAGE_SIZE


async def create_document_upload(
    *,
    session: Session,
    upload: UploadFile,
    identity: Identity,
    trace_id: str,
    task_manager: TaskManager | None = None,
) -> UploadResponse:
    """受理上传，返回 `task_id`（= `documents.id`）。

    当 ``task_manager`` 不为 ``None`` 时，注册 ``document.parse`` 异步执行体
    （ADR-0001 §3.1）。pytest 不传 ``task_manager``，跳过异步任务注册，
    维持 ``status = pending``，与原 Sprint 1 行为一致。
    """
    settings = get_settings()

    mime_type = (upload.content_type or "").split(";")[0].strip().lower()
    if mime_type not in settings.allowed_mime_types:
        raise AppError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            detail={
                "mime_type": mime_type or None,
                "allowed_mime_types": settings.allowed_mime_types,
            },
        )

    size_bytes = await _measure_size(upload, max_bytes=settings.max_upload_size_bytes)

    document_id = uuid4()
    filename_hash = hash_filename(upload.filename or "")
    storage_key = build_storage_key(
        org_id=identity.org_id, doc_id=document_id, filename_hash=filename_hash
    )

    # 文件落盘先于 DB 写入：put 失败 → 4xx/5xx 且无 DB 行（无幽灵记录）；
    # DB 失败 → 至多留一个孤儿文件（可被运维清理，优于「行存在但无文件」）。
    content = await upload.read()
    get_storage().put(storage_key, content)

    document = Document(
        id=document_id,
        filename_hash=filename_hash,
        mime_type=mime_type,
        size_bytes=size_bytes,
        status="pending",
        uploaded_by=identity.actor_id,
        org_id=identity.org_id,
        storage_key=None,
        retry_count=0,
        trace_id=UUID(trace_id),
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    logger.bind(
        trace_id=trace_id,
        document_id=str(document_id),
        size_bytes=size_bytes,
        mime_type=mime_type,
    ).info("document_file_stored")

    # 注册异步任务（ADR-0001 §3.1；阶段经接缝 4 pipeline_stages 解析，
    # 当前登记的执行体仅 document.parse——后续阶段登记后自动进入管线）
    if task_manager is not None:
        stage = first_pipeline_stage()
        if stage is not None:
            task_manager.submit(
                TaskSpec(
                    task_type=stage,
                    payload={"document_id": str(document.id), "mime_type": mime_type},
                    trace_id=trace_id,
                )
            )
        else:
            logger.bind(trace_id=trace_id, document_id=str(document_id)).warning(
                "document_pipeline_all_stages_disabled"
            )

    return UploadResponse(task_id=document.id, status="pending", trace_id=trace_id)


async def _measure_size(upload: UploadFile, *, max_bytes: int) -> int:
    """流式统计字节数并在超限时抛 413。

    **已知局限**：Starlette 已把 multipart 落到临时文件，本函数属于「接收后校验」，
    并非传输层限流。Sprint 3 需在反向代理 / 网关层追加同源限制。
    """
    total = 0
    while True:
        chunk = await upload.read(_UPLOAD_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                detail={
                    "max_size_bytes": max_bytes,
                    "limit_mb": max_bytes // (1024 * 1024),
                },
            )
    await upload.seek(0)
    return total


def get_document_status(
    *,
    session: Session,
    document_id: UUID,
    identity: Identity,
    trace_id: str,
) -> DocumentStatusResponse:
    """查询文档解析状态（M1 验收 5）。"""
    document = get_scoped_document(
        session=session, document_id=document_id, identity=identity
    )
    return DocumentStatusResponse(
        task_id=document.id,
        status=document.status,  # type: ignore[arg-type] - 由 CHECK 约束保证取值
        progress=_PROGRESS_BY_STATUS.get(document.status),
        error=_build_document_error(document),
        trace_id=trace_id,
    )


def get_scoped_document(
    *, session: Session, document_id: UUID, identity: Identity
) -> Document:
    """按 `org_id` 取文档；不存在 → 404，跨租户 → 403（ADR-0003 / M5 §3 验收 1）。

    实现说明：**正常路径始终带 `org_id` 过滤**（RLS 缺位期间的应用层兜底）。
    只有在主查询未命中时，才做一次仅返回「是否存在」的存在性探测，用于区分
    404 与 403 —— 这是 M5 明确要求 403 语义所带来的、已接受的信息披露面。
    """
    stmt = select(Document).where(
        Document.id == document_id, Document.org_id == identity.org_id
    )
    document = session.scalars(stmt).one_or_none()
    if document is not None:
        return document

    foreign = session.scalars(
        select(Document.org_id).where(Document.id == document_id)
    ).one_or_none()
    if foreign is None:
        raise AppError(
            ErrorCode.DOCUMENT_NOT_FOUND, detail={"document_id": str(document_id)}
        )
    raise AppError(
        ErrorCode.FORBIDDEN,
        detail={"document_id": str(document_id), "reason": "cross_tenant_access"},
    )


def _build_document_error(document: Document) -> DocumentError | None:
    if document.status != "failed":
        return None
    try:
        code = ErrorCode(document.error_code) if document.error_code else None
    except ValueError:
        code = None
    resolved = code or ErrorCode.INTERNAL_ERROR
    return DocumentError(
        code=resolved,
        message=DEFAULT_MESSAGES[resolved],
        # 刻意不回显 documents.error_detail（M1 §4.1 标注为敏感）
        detail=None,
    )
