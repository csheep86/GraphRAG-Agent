"""M1 文档接入相关路由：上传 / 状态 / 图谱子图。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile

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
from app.services.documents import (
    create_document_upload,
    get_document_status,
    get_scoped_document,
)
from app.services.graphs import (
    GraphService,
    GraphUnavailableError,
    NoActiveKgVersionError,
)
from app.tasks.manager import TaskManager

router = APIRouter(prefix="/documents", tags=["documents"])

#: 单次返回节点上限（契约 `DocumentGraphResponse`：≤ 500，超限 `truncated = true`）
_GRAPH_NODE_LIMIT = 500


@router.post(
    "/upload",
    response_model=UploadResponse,
    operation_id="uploadDocument",
    summary="上传文档（异步受理）",
    description=(
        "**同步校验 + 立即返回**，不在请求内做任何解析：\n"
        "1. MIME 白名单校验 → 失败 415；\n"
        "2. 大小上限校验（默认 100MB）→ 失败 413；\n"
        "3. 落 `documents` 记录（`status = pending`），注册 `document.parse` 异步执行体，"
        "并返回 `task_id`。\n\n"
        "**解析链路**：执行体真实推进 `pending → processing → completed / failed`"
        "（M1 硬约束 H1），第三方 IO 异常按 H8 指数退避重试（≤ 3 次）；"
        "进程重启时由启动回收把在途任务置 `failed` + `error_code = TASK_INTERRUPTED`"
        "（ADR-0001 §3.2）。\n\n"
        "上传响应的 `status` 恒为 `pending`，后续进度请轮询 "
        "`GET /documents/{id}/status`。\n\n"
        "**当前局限**：状态机与错误落库为真实链路；MinerU 结构化解析与 LangExtract "
        "实体关系抽取尚未接入，执行体当前返回空结果（后续版本补齐，见 v1.1.0 待办）。\n\n"
        "文件名以 SHA-256 落库（`filename_hash`），日志与响应均不含原文。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **FILE_TOO_LARGE, **UNSUPPORTED_MEDIA_TYPE},
)
async def upload_document(
    file: Annotated[
        UploadFile,
        File(description="待解析文件。白名单：PDF / DOCX / CSV；单文件 ≤ 100MB"),
    ],
    background_tasks: BackgroundTasks,
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> UploadResponse:
    return await create_document_upload(
        session=session,
        upload=file,
        identity=identity,
        trace_id=trace_id,
        task_manager=TaskManager(background_tasks),
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
    summary="获取文档图谱子图",
    description=(
        "返回该文档在 Neo4j 中的子图（`nodes` + `edges`），供前端力导向图渲染。\n\n"
        "**一致性（ADR-0002 §3.2）**：只返回 `status = active` 的 `kg_version`；"
        "该文档不存在 active 版本时返回 **409** `KG_VERSION_NOT_ACTIVE`，"
        "**绝不静默降级**到其他版本；响应中的 `version_status` 恒为 `active`。\n\n"
        "规模上限对齐 M3 §3 验收 1：单次节点数 ≤ 500，超限 `truncated = true`。\n\n"
        "**实现状态**：已实装——由 `GraphService.fetch_document_subgraph`"
        "（`app/services/graphs.py`）按 `kg_version` 查询 Neo4j 子图，"
        "并映射为 `DocumentGraphResponse`（`nodes` / `edges` / `truncated` / `version_status`）。\n\n"
        "**501 `NOT_IMPLEMENTED` 的真实语义**：Neo4j 不可用（连接失败 / 查询超时 / 凭据错误）"
        "属**基础设施故障**，此时返回 501——**不**表示「接口未实现」。"
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
    session: DbSession,
    trace_id: TraceId,
) -> DocumentGraphResponse:
    # 1) 文档可见性（纯 PG，先于任何外部依赖）：不存在 → 404，跨租户 → 403
    get_scoped_document(session=session, document_id=document_id, identity=identity)

    graph = GraphService.instance()

    # 2) active kg_version（ADR-0002 §3.2：只消费 active）
    #    注意区分两种故障——「无 active 版本」是版本状态问题（409），
    #    「连不上 Neo4j」是基础设施故障（501）。契约 §/documents/{id}/graph 明文要求 409。
    try:
        kg_version = graph.fetch_active_kg_version()
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={
                "document_id": str(document_id),
                "status": "none",
                "hint": "该文档不存在 active 版本，拒绝静默降级",
            },
        ) from exc
    except GraphUnavailableError as exc:
        raise _graph_not_available(document_id=document_id, exc=exc) from exc

    # 3) 拉取该文档在 active 版本下的子图
    try:
        nodes, edges, truncated = graph.fetch_document_subgraph(
            doc_id=document_id,
            kg_version=kg_version.version,
            org_id=identity.org_id,
            node_limit=_GRAPH_NODE_LIMIT,
        )
    except GraphUnavailableError as exc:
        raise _graph_not_available(document_id=document_id, exc=exc) from exc

    return DocumentGraphResponse(
        doc_id=document_id,
        kg_version=kg_version.version,
        version_status="active",
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        relation_count=len(edges),
        truncated=truncated,
        trace_id=trace_id,
    )


def _graph_not_available(*, document_id: UUID, exc: Exception) -> AppError:
    """把 Neo4j 不可用映射为 501（契约已声明该分支；基础设施故障非数据问题）。"""
    return AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Graph store is unavailable",
        detail={
            "document_id": str(document_id),
            "blocked_by": "Neo4j 不可用或尚无 active kg_version（ADR-0002 §3.2）",
            "reason": str(exc),
        },
    )
