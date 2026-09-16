"""M1 文档接入相关路由：上传 / 状态 / 图谱子图。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    DOCUMENT_NOT_FOUND,
    FILE_TOO_LARGE,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
    UNSUPPORTED_MEDIA_TYPE,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.document import (
    DocumentGraphResponse,
    DocumentStatusResponse,
    UploadResponse,
)
from app.services.documents import create_document_upload, get_document_status

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    operation_id="uploadDocument",
    summary="上传文档（异步受理）",
    description=(
        "**同步校验 + 立即返回**，不在请求内做任何解析：\n"
        "1. MIME 白名单校验 → 失败 415；\n"
        "2. 大小上限校验（默认 100MB）→ 失败 413；\n"
        "3. 落 `documents` 记录（`status = pending`）并返回 `task_id`。\n\n"
        "Sprint 1 边界：**不注册异步执行体**，因此 `status` 会停留在 `pending`；"
        "`TaskManager` 与启动回收在 Sprint 3 补齐（ADR-0001 §3.2）。\n\n"
        "文件名以 SHA-256 落库（`filename_hash`），日志与响应均不含原文。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **FILE_TOO_LARGE, **UNSUPPORTED_MEDIA_TYPE},
)
async def upload_document(
    file: Annotated[
        UploadFile,
        File(description="待解析文件。白名单：PDF / DOCX / CSV；单文件 ≤ 100MB"),
    ],
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> UploadResponse:
    return await create_document_upload(
        session=session, upload=file, identity=identity, trace_id=trace_id
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    operation_id="getDocumentStatus",
    summary="查询文档解析状态",
    description=(
        "状态机严格限定为 `pending → processing → completed / failed`（M1 硬约束 H1）。\n\n"
        "轮询建议：首次 2s，3 次后降为 10s。\n\n"
        "**跨租户访问返回 403**（`FORBIDDEN`），不返回 404——按 M5 §3 验收 1 的显式要求。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **DOCUMENT_NOT_FOUND},
)
async def read_document_status(
    document_id: UUID,
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> DocumentStatusResponse:
    return get_document_status(
        session=session,
        document_id=document_id,
        identity=identity,
        trace_id=trace_id,
    )


@router.get(
    "/{document_id}/graph",
    response_model=DocumentGraphResponse,
    operation_id="getDocumentGraph",
    summary="获取文档图谱子图（契约已定稿，Sprint 3 实现）",
    description=(
        "返回该文档在 Neo4j 中的子图（`nodes` + `edges`），供前端力导向图渲染。\n\n"
        "**一致性（ADR-0002 §3.2）**：只返回 `status = active` 的 `kg_version`；"
        "该文档不存在 active 版本时返回 **409** `KG_VERSION_NOT_ACTIVE`，"
        "**绝不静默降级**到其他版本；响应中的 `version_status` 恒为 `active`。\n\n"
        "规模上限对齐 M3 §3 验收 1：单次节点数 ≤ 500，超限 `truncated = true`。\n\n"
        "**当前实现状态**：返回 **501** `NOT_IMPLEMENTED`（Neo4j 查询为 Sprint 3 范围）。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **DOCUMENT_NOT_FOUND,
        **KG_VERSION_NOT_ACTIVE,
        **NOT_IMPLEMENTED,
    },
)
async def read_document_graph(
    document_id: UUID,
    identity: CurrentIdentity,
    trace_id: TraceId,
) -> DocumentGraphResponse:
    raise AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Document graph query is not implemented in Sprint 1",
        detail={
            "document_id": str(document_id),
            "planned_sprint": "3",
            "blocked_by": "Neo4j 集成与 active kg_version 一致性查询（ADR-0002）",
        },
    )
