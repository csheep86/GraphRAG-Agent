"""审计留痕：写入与查询（M5 §3 验收 2 / 6 / 7，Sprint 8.1 批次 A）。

三条硬纪律（proposal「硬约束」+「风险」）：

1. **写入点唯一 = 审计中间件**（决策 **A1**）：不是各服务显式埋点——埋点必然漏，
   而「漏埋」比「多写」更难被发现。本模块只提供 :func:`record_audit_entry`
   这一个写入原语，谁都能调，但**只有中间件在调**。
2. **`detail` 只写结构化字段**：**绝不写响应体原文**（决策 **A5**）。本批次不引入
   脱敏器（属 H5 / S11），所以宁可不写，也不先把原文写进库再想办法脱敏。
3. **写失败只记日志、不抛异常**（proposal 风险 2）：审计缺陷不得变成全站 500。
   本模块的所有异常都在 :func:`record_audit_entry` 内部吞掉并打日志。

**同 session 范式**（决策 **A10**）：业务内的写入（当前只有间接场景）与业务共用 session、
不自行 commit；**中间件**没有业务 session 可用，故由 :meth:`AuditMiddleware` 自己
持有一个短会话并显式提交——这是「唯一没有业务事务可依附」的写入点，已在
`app/core/middleware.py` 就地注释说明。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.core.errors import AppError, ErrorCode
from app.db.models import AuditLog
from app.schemas.audit import (
    AuditLogItem,
    AuditLogListResponse,
    AuditTraceResponse,
)

#: `GET /audit` 分页口径（M5 §3 验收 7 原文：默认 `ts DESC`、页大小 50）
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100

#: `status` 合法过滤值
AUDIT_STATUS_VALUES = ("success", "failure")

#: 路由端点函数名 → 业务 action（决策 **A2**）。
#: 键是 Starlette 匹配后写入 ``scope["endpoint"]`` 的**函数对象名**（不是 URL），
#: 因此路由改路径**不会**导致 action 漂移——只有改函数名才需要同步这里。
ACTION_BY_ROUTE_NAME: dict[str, str] = {
    # M1 文档
    "list_documents_endpoint": "document.list",
    "upload_document": "document.upload",
    "read_document_status": "document.status",
    "read_document_graph": "document.graph",
    "read_document_chunk": "document.chunk",
    # M2 / M5 图谱与版本
    "get_graph_overview": "graph.overview",
    "get_entity_detail": "graph.entity",
    "activate_kg_version": "graph.activate",
    # M3 问答
    "query_agent": "agent.query",
    # M4 关联交易
    "detect_affiliation": "affiliation.detect",
    "read_affiliation_task": "affiliation.task",
    "list_affiliation_suspicions": "affiliation.list",
    "review_affiliation_suspicion": "affiliation.review",
    # M5 审计自身（自举记录：查审计也是一次 API 调用）
    "list_audit_logs_endpoint": "audit.list",
    "list_audit_logs_by_trace_endpoint": "audit.trace",
}

#: 列宽上限（``audit_log.action`` / ``resource`` 均为 ``String(255)``）。
#: 未登记路由会把**原始路径**写进 action / resource，超长时截断而非让整条审计写失败
#: ——截掉的是攻击者可控的超长 URL 尾部，保留前 255 字符足以定位入口。
_MAX_TEXT_LEN = 255


def resolve_action(*, endpoint: Any, method: str, path: str) -> str:
    """把一次请求解析为 action：命中路由元数据用业务名，否则回落到 HTTP 三元组。

    回落时打 **WARNING**：回落意味着新增了未登记的路由（每个 Sprint 都可能加），
    静默回落 = 永远没人知道该补映射了（决策 **A2** 明确要求留痕）。
    """
    name = getattr(endpoint, "__name__", None)
    if isinstance(name, str) and name in ACTION_BY_ROUTE_NAME:
        return ACTION_BY_ROUTE_NAME[name]

    action = f"http.{method.lower()}.{path}"
    logger.bind(method=method, path=path, route=name).warning(
        "audit_action_route_not_registered"
    )
    return action[:_MAX_TEXT_LEN]


def truncate_resource(value: str) -> str:
    """把资源标识压进 ``String(255)`` 列宽（同 :func:`resolve_action` 的截断口径）。"""
    return value[:_MAX_TEXT_LEN]


def record_audit_entry(
    session: Session,
    *,
    org_id: UUID,
    action: str,
    resource: str,
    status: str,
    trace_id: UUID | str,
    actor_id: UUID | None = None,
    actor_ip: str | None = None,
    doc_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> bool:
    """向当前 session 追加一条 `audit_log`（**不自行 commit**，照 `events/db.py:14-17`）。

    :returns: 是否成功入 session。失败（如字段超长 / 约束冲突）**只记日志**，
        由调用方决定是否继续——审计不得拖垮主流程（proposal 风险 2）。
    """
    try:
        session.add(
            AuditLog(
                org_id=org_id,
                action=truncate_resource(action),
                actor_id=actor_id,
                actor_ip=actor_ip,
                doc_id=doc_id,
                resource=truncate_resource(resource),
                status=status,
                trace_id=UUID(str(trace_id)),
                detail=detail,
            )
        )
    except Exception as exc:  # noqa: BLE001 - 审计写失败绝不上抛
        logger.bind(action=action, resource=resource, reason=str(exc)).warning(
            "audit_log_write_failed"
        )
        return False
    return True


def list_audit_logs(
    *,
    session: Session,
    identity: Identity,
    action: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
    trace_id: str = "",
) -> AuditLogListResponse:
    """`GET /api/v1/audit`：当前租户的审计列表（`ts DESC` + Python 切片分页）。

    口径照 `documents.list_documents`（全量取 → Python 切片）：演示量级足够，
    且避免深 OFFSET。``org_id`` 强制来自认证态（ADR-0003 §3.3）。
    """
    stmt = select(AuditLog).where(AuditLog.org_id == identity.org_id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if status:
        _assert_valid_status(status)
        stmt = stmt.where(AuditLog.status == status)

    rows = session.scalars(stmt.order_by(AuditLog.ts.desc())).all()
    total = len(rows)

    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]

    return AuditLogListResponse(
        total=total,
        items=[_to_item(row) for row in page_rows],
        page=page,
        page_size=page_size,
        trace_id=trace_id,
    )


def list_audit_logs_by_trace(
    *,
    session: Session,
    identity: Identity,
    trace_id: str,
) -> AuditTraceResponse:
    """`GET /api/v1/audit/trace/{trace_id}`：按 trace 回看全程（同一租户内）。

    跨租户 -> **空集**（不是错误）：trace_id 是 UUIDv4，本就不可猜；
    返回空即达成"不泄露资源存在性"（ADR-0003）。
    """
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.org_id == identity.org_id)
        .where(AuditLog.trace_id == UUID(trace_id))
        .order_by(AuditLog.ts.asc())
    ).all()

    return AuditTraceResponse(
        trace_id=trace_id,
        total=len(rows),
        items=[_to_item(row) for row in rows],
    )


def _assert_valid_status(status: str) -> None:
    """`status` 过滤值合法性（非法值 400，不静默当"全不过滤"处理）。"""
    if status not in AUDIT_STATUS_VALUES:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            detail={
                "field": "status",
                "value": status,
                "allowed": list(AUDIT_STATUS_VALUES),
            },
        )


def _to_item(row: AuditLog) -> AuditLogItem:
    """ORM 行 → 契约模型。``trace_id`` 取本行的值（不一定等于本次请求）。"""
    return AuditLogItem(
        id=row.id,
        ts=row.ts,
        action=row.action,
        actor_id=row.actor_id,
        actor_ip=row.actor_ip,
        doc_id=row.doc_id,
        resource=row.resource,
        status=row.status,  # type: ignore[arg-type] - 写入侧受 CheckConstraint 约束
        trace_id=str(row.trace_id),
        detail=row.detail,
    )


__all__ = [
    "ACTION_BY_ROUTE_NAME",
    "AUDIT_STATUS_VALUES",
    "PAGE_SIZE_DEFAULT",
    "PAGE_SIZE_MAX",
    "list_audit_logs",
    "list_audit_logs_by_trace",
    "record_audit_entry",
    "resolve_action",
    "truncate_resource",
]
