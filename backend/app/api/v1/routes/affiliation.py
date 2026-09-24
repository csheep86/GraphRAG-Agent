"""M4 关联交易疑点端点（Sprint 7.2 批次 B；`specs/m4-affiliation-detection.md` §5.5）。

四个端点逐字照 spec §5.5，**路径口径以 spec 为准**（批次 B 决策 **B1**：
`plan.md:275` 原写 `/affiliation/suspects`，已统一为 `/affiliation/suspicions`）。

两个要害，改动前先读：

1. **任务状态唯一真值源 = PG `affiliation_tasks`**（ADR-0001 要求 1）。`POST detect`
   只负责落 `pending` + 经 `TaskManager` 投递执行体，**不在**这里跑算法；
2. **`reviewed_by` 取 `X-Actor-Id`**（决策 **B4**）——M5（S11）落地前这是唯一的 actor 来源，
   取它是**既有 dev 脚手架**，不新造 `AuthProvider`（ADR-0004 §2.1 登记集合不变）。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    AFFILIATION_SUSPICION_NOT_FOUND,
    AFFILIATION_TASK_NOT_FOUND,
    TENANT_ERROR_RESPONSES,
    VALIDATION_ERROR,
)
from app.schemas.affiliation import (
    AffiliationDetectRequest,
    AffiliationDetectResponse,
    AffiliationEvidenceRef,
    AffiliationSuspicionItem,
    AffiliationSuspicionListResponse,
    AffiliationSuspicionPatchRequest,
    AffiliationSuspicionPatchResponse,
    AffiliationTaskResponse,
    AffiliationTaskResultSummary,
)
from app.services.affiliation import (
    create_detection_task,
    get_task,
    list_suspicions,
    patch_suspicion_status,
)
from app.tasks.manager import TaskManager
from app.tasks.types import TaskSpec

router = APIRouter(prefix="/affiliation", tags=["affiliation"])


@router.post(
    "/detect",
    response_model=AffiliationDetectResponse,
    operation_id="detectAffiliation",
    summary="提交一次关联交易检测（异步，202）",
    description=(
        "对 `doc_ids` 覆盖的文档集合跑 M4 规则型算法（**当前只做两类**："
        "「同一法人跨公司」/「同一地址跨公司」），检出结果写 `affiliation_suspicions`。\n\n"
        "**异步语义**：请求只保证任务落库为 `pending` 并已投递，随即返回 **202** "
        "（`task_id` + `status`）；真值在 PG `affiliation_tasks` 表里，请用 "
        "`GET /affiliation/tasks/{task_id}` 轮询。\n\n"
        "**每次提交都新建一条任务**（决策 B3：幂等由任务承载，不是「复用上次的疑点」）——"
        "重复提交会得到第二批疑点，前端可用 `task_id` 区分批次。\n\n"
        "**错误分支**：`doc_ids` 为空 → 400 `VALIDATION_ERROR`；"
        "文档不存在 → 404 `DOCUMENT_NOT_FOUND`；**任一文档跨租户 → 403**（不静默剔除）。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR},
    status_code=202,
)
async def detect_affiliation(
    payload: AffiliationDetectRequest,
    background_tasks: BackgroundTasks,
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> AffiliationDetectResponse:
    task = create_detection_task(
        session=session,
        identity=identity,
        doc_ids=payload.doc_ids,
        trace_id=trace_id,
    )

    # 经 TaskManager 投递——**不**直接 add_task：ADR-0001 要求 2 规定业务代码
    # 只依赖该接口，绕过它就是第二个任务真值源（批次 B 决策 B8）
    TaskManager(background_tasks).submit(
        TaskSpec(
            task_type="affiliation.detect",
            payload={"affiliation_task_id": str(task.id)},
            trace_id=trace_id,
        )
    )

    return AffiliationDetectResponse(
        task_id=task.id, status=task.status, trace_id=trace_id
    )


@router.get(
    "/tasks/{task_id}",
    response_model=AffiliationTaskResponse,
    operation_id="getAffiliationTask",
    summary="查询检测任务状态",
    description=(
        "返回 `affiliation_tasks` 的**当前状态**（PG 唯一真值源，非进程内存）。\n\n"
        "- `pending` / `processing`：执行中，`result_summary` 为 `null`；\n"
        "- `completed`：带 `result_summary`（`{total, by_type, top_5_severity}`）；\n"
        "- `failed`：带 `error_code`（`TASK_INTERRUPTED` 表示进程重启回收，ADR-0001 §3.2）。\n\n"
        "**错误分支**：任务不存在 → 404 `NOT_FOUND`，跨租户 → **403**（非 404）。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **AFFILIATION_TASK_NOT_FOUND},
)
async def read_affiliation_task(
    task_id: UUID,
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> AffiliationTaskResponse:
    task = get_task(session=session, identity=identity, task_id=task_id)

    summary_raw = task.result_summary
    summary = (
        AffiliationTaskResultSummary.model_validate(summary_raw)
        if summary_raw
        else None
    )

    return AffiliationTaskResponse(
        task_id=task.id,
        status=task.status,  # type: ignore[arg-type]
        doc_ids=[UUID(value) for value in task.doc_ids],
        result_summary=summary,
        error_code=task.error_code,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        trace_id=trace_id,
    )


@router.get(
    "/suspicions",
    response_model=AffiliationSuspicionListResponse,
    operation_id="listAffiliationSuspicions",
    summary="列出疑点（默认最近一批）",
    description=(
        "返回当前租户的疑点列表，每条含 `entities` / `entity_names` / `evidence`"
        "（引用覆盖率 = 100%：产不出原文证据的命中在算法层就被丢弃，**不会**出现在这里）。\n\n"
        "**批次口径**（决策 B2）：不带 `task_id` 时返回**最近一条 completed 任务**"
        "产出的疑点——重复跑检测会产生多批疑点，靠 `created_at` 猜「最新」在并发 / "
        "补跑下不稳，故用 `task_id` 列精确归属。\n\n"
        "**不支持分页**（spec §5.5 未规定，不引入无消费者的 `page` / `page_size`）；"
        "租户从未跑过检测时返回**空列表** + `task_id = null`（200，非 404）。"
    ),
    responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR},
)
async def list_affiliation_suspicions(
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
    task_id: Annotated[
        UUID | None,
        Query(description="指定批次（任务 id）；缺省=最近一条 completed 任务"),
    ] = None,
    type: Annotated[  # noqa: A002 - 与 spec §5.5 的 query 名逐字一致
        str | None,
        Query(description="按疑点类型过滤：`shared_legal_rep` / `shared_address`"),
    ] = None,
    severity: Annotated[
        str | None, Query(description="按严重度过滤：`high` / `medium` / `low`")
    ] = None,
    status: Annotated[
        str | None,
        Query(description="按复核状态过滤：`open` / `confirmed` / `dismissed`"),
    ] = None,
) -> AffiliationSuspicionListResponse:
    rows, resolved_task_id = list_suspicions(
        session=session,
        identity=identity,
        task_id=task_id,
        suspicion_type=type,
        severity=severity,
        status=status,
    )

    items = [
        AffiliationSuspicionItem(
            id=row.id,
            task_id=row.task_id,
            suspicion_type=row.suspicion_type,  # type: ignore[arg-type]
            severity=row.severity,  # type: ignore[arg-type]
            entities=list(row.entities),
            entity_names=list(row.entity_names),
            evidence=[
                AffiliationEvidenceRef.model_validate(item) for item in row.evidence
            ],
            kg_version=row.kg_version,
            status=row.status,  # type: ignore[arg-type]
            reviewed_by=row.reviewed_by,
            reviewed_at=row.reviewed_at,
            created_at=row.created_at,
            trace_id=str(row.trace_id),
        )
        for row in rows
    ]

    return AffiliationSuspicionListResponse(
        items=items, total=len(items), task_id=resolved_task_id, trace_id=trace_id
    )


@router.patch(
    "/suspicions/{suspicion_id}",
    response_model=AffiliationSuspicionPatchResponse,
    operation_id="reviewAffiliationSuspicion",
    summary="复核一条疑点（确认 / 驳回）",
    description=(
        "把疑点从 `open` 流转到 `confirmed` / `dismissed`（spec §3 验收 2：状态流转落库）。\n\n"
        "**只改状态**：`entities` / `evidence` 一律不动，复核留痕不会被抹掉——"
        "已非 `open` 的疑点再次提交 → **400** `VALIDATION_ERROR`（不允许改回未复核）。\n\n"
        "`reviewed_by` 取当前请求头的 `X-Actor-Id`（决策 B4；M5 落地后改为 token 主体）。\n\n"
        "**错误分支**：疑点不存在 → 404，跨租户 → **403**（非 404）。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **AFFILIATION_SUSPICION_NOT_FOUND,
        **VALIDATION_ERROR,
    },
)
async def review_affiliation_suspicion(
    suspicion_id: UUID,
    payload: AffiliationSuspicionPatchRequest,
    identity: CurrentIdentity,
    session: DbSession,
    trace_id: TraceId,
) -> AffiliationSuspicionPatchResponse:
    row = patch_suspicion_status(
        session=session,
        identity=identity,
        suspicion_id=suspicion_id,
        status=payload.status,
        reviewed_by=identity.actor_id,
    )

    return AffiliationSuspicionPatchResponse(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        trace_id=trace_id,
    )
