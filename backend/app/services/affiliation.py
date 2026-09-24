"""M4 关联交易疑点的 **PG 侧**读写服务（Sprint 7.2 批次 B）。

与 :mod:`app.services.kg.affiliation` 的分工（**两处都叫 affiliation，别混淆**）：

- ``app/services/kg/affiliation.py`` = **纯算法**：输入 ``kg_version`` + ``org_id``，
  在 Neo4j 里跑两跳规则，输出 :class:`Suspicion`（**不碰 PG**）；
- 本模块 = **持久化与查询**：把算法产物落到 ``affiliation_suspicions``，
  并支撑三个读端点。**本模块不拼 Cypher**。

租户纪律（ADR-0003）：``org_id`` 一律来自调用方传入的 :class:`Identity`（请求头），
**严禁**从请求体 / query 读取；跨租户资源 → **403**，不存在 → **404**，两者不可混。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.core.errors import AppError, ErrorCode
from app.db.models import AffiliationSuspicion, AffiliationTask, Document

#: 严重度排序权重（``result_summary.top_5_severity`` 用它决定"最严重的 5 条"）
_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
#: 单个租户一次最多返回多少条疑点（演示数据集 ~10 条；给足余量但不做分页）
_MAX_LIST_ROWS: int = 200


def create_detection_task(
    *,
    session: Session,
    identity: Identity,
    doc_ids: list[uuid.UUID],
    trace_id: uuid.UUID | str,
) -> AffiliationTask:
    """建一条 ``pending`` 检测任务；文档须全部属于当前租户。

    :raises AppError: 文档不存在 → 404 ``DOCUMENT_NOT_FOUND``；跨租户 → **403**
        ``FORBIDDEN``（ADR-0003：不静默剔除，也不把它当成"没选中"）。
    """
    missing: list[str] = []
    foreign_count = 0
    for raw in doc_ids:
        document = session.get(Document, raw)
        if document is None:
            missing.append(str(raw))
            continue
        if document.org_id != identity.org_id:
            foreign_count += 1

    if missing:
        raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, detail={"document_ids": missing})
    if foreign_count:
        # 存在但不属于本租户：409/200 都是错答案，必须让调用方看见越权事实
        raise AppError(
            ErrorCode.FORBIDDEN, detail={"foreign_document_count": foreign_count}
        )

    row = AffiliationTask(
        org_id=identity.org_id,
        # JSON 列只吃 str(uuid)（json.dumps 不支持 UUID）— 沿用 KgVersion.source_doc_ids
        doc_ids=[str(item) for item in doc_ids],
        status="pending",
        trace_id=uuid.UUID(str(trace_id)),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_task(
    *, session: Session, identity: Identity, task_id: uuid.UUID
) -> AffiliationTask:
    """按 id 取任务；不存在 → 404，跨租户 → **403**。"""
    row = session.scalars(
        select(AffiliationTask).where(
            AffiliationTask.id == task_id, AffiliationTask.org_id == identity.org_id
        )
    ).one_or_none()
    if row is not None:
        return row

    foreign_org = session.scalars(
        select(AffiliationTask.org_id).where(AffiliationTask.id == task_id)
    ).one_or_none()
    if foreign_org is None:
        raise AppError(ErrorCode.NOT_FOUND, detail={"task_id": str(task_id)})
    raise AppError(ErrorCode.FORBIDDEN, detail={"task_id": str(task_id)})


def _resolve_latest_task(*, session: Session, identity: Identity) -> uuid.UUID | None:
    """取本租户**最近一条 completed** 任务的 id；从未跑过返回 ``None``。

    排序键用 ``completed_at``（完成时刻）而非 ``created_at``：补跑 / 并发下，
    「最近完成的那批」才是用户想看的结果。``completed_at`` 为空的任务（在途 /
    失败）**不参与**——它们没有产出可读的疑点。
    """
    row = session.scalars(
        select(AffiliationTask.id)
        .where(
            AffiliationTask.org_id == identity.org_id,
            AffiliationTask.status == "completed",
            AffiliationTask.completed_at.is_not(None),
        )
        .order_by(AffiliationTask.completed_at.desc())
        .limit(1)
    ).one_or_none()
    return row


def list_suspicions(
    *,
    session: Session,
    identity: Identity,
    task_id: uuid.UUID | None = None,
    suspicion_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> tuple[list[AffiliationSuspicion], uuid.UUID | None]:
    """查疑点列表，返回 ``(条目, 实际使用的 task_id)``。

    不带 ``task_id`` 时取**最近一条 completed 任务**的疑点（批次 B 决策 **B2**：
    有了 ``task_id`` 列才能这么答；没有它只能靠时间猜或返回全部历史混杂）。
    显式传 ``task_id`` 时必须属于本租户（跨租户 → 403，与 :func:`get_task` 同口径）。
    """
    if task_id is not None:
        # 复存在性 / 越权判定
        task_row = session.scalars(
            select(AffiliationTask.id).where(AffiliationTask.id == task_id)
        ).one_or_none()
        if task_row is None:
            raise AppError(ErrorCode.NOT_FOUND, detail={"task_id": str(task_id)})
        owner = session.scalars(
            select(AffiliationTask.org_id).where(AffiliationTask.id == task_id)
        ).one_or_none()
        if owner != identity.org_id:
            raise AppError(ErrorCode.FORBIDDEN, detail={"task_id": str(task_id)})
        resolved_task_id: uuid.UUID | None = task_id
    else:
        resolved_task_id = _resolve_latest_task(session=session, identity=identity)
        if resolved_task_id is None:
            return [], None

    stmt = select(AffiliationSuspicion).where(
        AffiliationSuspicion.org_id == identity.org_id,
        AffiliationSuspicion.task_id == resolved_task_id,
    )
    if suspicion_type is not None:
        stmt = stmt.where(AffiliationSuspicion.suspicion_type == suspicion_type)
    if severity is not None:
        stmt = stmt.where(AffiliationSuspicion.severity == severity)
    if status is not None:
        stmt = stmt.where(AffiliationSuspicion.status == status)

    rows = list(
        session.scalars(
            stmt.order_by(
                AffiliationSuspicion.severity, AffiliationSuspicion.created_at
            ).limit(_MAX_LIST_ROWS)
        )
    )
    return rows, resolved_task_id


def patch_suspicion_status(
    *,
    session: Session,
    identity: Identity,
    suspicion_id: uuid.UUID,
    status: str,
    reviewed_by: uuid.UUID,
) -> AffiliationSuspicion:
    """复核一条疑点（``open → confirmed / dismissed``）。

    :raises AppError: 不存在 → 404；跨租户 → **403**；非 ``open`` 状态再复核 →
        **400** ``VALIDATION_ERROR``（不允许把已复核留痕抹回去）。
    """
    row = session.scalars(
        select(AffiliationSuspicion).where(
            AffiliationSuspicion.id == suspicion_id,
            AffiliationSuspicion.org_id == identity.org_id,
        )
    ).one_or_none()
    if row is None:
        foreign = session.scalars(
            select(AffiliationSuspicion.org_id).where(
                AffiliationSuspicion.id == suspicion_id
            )
        ).one_or_none()
        if foreign is None:
            raise AppError(
                ErrorCode.NOT_FOUND, detail={"suspicion_id": str(suspicion_id)}
            )
        raise AppError(ErrorCode.FORBIDDEN, detail={"suspicion_id": str(suspicion_id)})

    if row.status != "open":
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            detail={"suspicion_id": str(suspicion_id), "current_status": row.status},
        )

    row.status = status
    row.reviewed_by = reviewed_by
    row.reviewed_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    return row


def mark_task_processing(*, session: Session, task: AffiliationTask) -> None:
    """把任务推进 ``processing``（执行体入口调用，PG 为唯一真值源）。"""
    task.status = "processing"
    session.commit()


def persist_detection_result(
    *,
    session: Session,
    task: AffiliationTask,
    suspicions: list[Any],
    kg_version: str,
    trace_id: uuid.UUID | str,
) -> int:
    """把算法产出的疑点落库，并把任务置 ``completed`` + 填 ``result_summary``。

    ``suspicions`` 是 :class:`app.services.kg.affiliation.Suspicion` 列表；这里只用
    它的 ``to_dict()`` 形状，**不** import 算法模块（保持本模块的 PG 单一职责，
    也让单元测试能用 duck-typed 假对象）。

    返回落库条数。
    """
    trace_uuid = uuid.UUID(str(trace_id))
    records: list[AffiliationSuspicion] = []
    for suspicion in suspicions:
        payload = suspicion.to_dict()
        records.append(
            AffiliationSuspicion(
                org_id=task.org_id,
                task_id=task.id,
                suspicion_type=str(payload["type"]),
                severity=str(payload["severity"]),
                entities=[str(item) for item in payload["entities"]],
                entity_names=[str(item) for item in payload["entity_names"]],
                evidence=list(payload["evidence"]),
                kg_version=kg_version,
                status="open",
                trace_id=trace_uuid,
            )
        )
    session.add_all(records)

    by_type: dict[str, int] = {}
    for record in records:
        by_type[record.suspicion_type] = by_type.get(record.suspicion_type, 0) + 1
    top_5 = sorted(records, key=lambda item: _SEVERITY_ORDER.get(item.severity, 99))[:5]

    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    task.error_code = None
    task.error_detail = None
    task.result_summary = {
        "total": len(records),
        "by_type": by_type,
        "top_5_severity": [item.severity for item in top_5],
    }
    session.commit()
    return len(records)


def mark_task_failed(
    *,
    session: Session,
    task: AffiliationTask,
    error_code: str,
    error_detail: str,
) -> None:
    """任务置 ``failed`` + 写错误码 / 明细（**明细属敏感字段，禁止进日志 / 契约**）。"""
    task.status = "failed"
    task.error_code = error_code
    task.error_detail = error_detail
    session.commit()


__all__ = [
    "create_detection_task",
    "get_task",
    "list_suspicions",
    "mark_task_failed",
    "mark_task_processing",
    "patch_suspicion_status",
    "persist_detection_result",
]
