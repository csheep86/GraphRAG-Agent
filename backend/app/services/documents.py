"""M1 文档上传与状态查询（Sprint 1 真实实现）。

实现边界（见 `backend/CODEBUDDY.md` §4）：
- ✅ 上传：MIME 白名单校验（415）→ 大小上限校验（413）→ 落 `documents` 记录（`pending`）；
- ✅ 状态：读 PostgreSQL / SQLite 返回，跨租户 403、不存在 404；
- ⛔ 不注册异步执行体：`TaskManager` 与启动回收留 Sprint 3（ADR-0001），
  因此本轮上传的文档 `status` 会停留在 `pending`。
- ⛔ 不写文件到存储抽象层：`storage_key` 保持 NULL（M1 §4.3 规定 `completed` 后填写）。
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.core.config import get_settings
from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode
from app.db.models import Document
from app.schemas.document import (
    DocumentError,
    DocumentStatusResponse,
    UploadResponse,
)

_UPLOAD_READ_CHUNK = 1024 * 1024

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


async def create_document_upload(
    *,
    session: Session,
    upload: UploadFile,
    identity: Identity,
    trace_id: str,
) -> UploadResponse:
    """受理上传，返回 `task_id`（= `documents.id`）。"""
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

    document = Document(
        id=uuid4(),
        filename_hash=hash_filename(upload.filename or ""),
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
