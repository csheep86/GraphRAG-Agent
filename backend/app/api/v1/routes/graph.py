"""图谱路由（`GET /graph/overview` + `GET /entities/{entity_id}`，Sprint 5 批次 C）。

公开路径：
- `GET /graph/overview` —— 全局图谱概览（节点 / 边轻量投影 + doc_count /
  entity_count / relation_count + active kg_version）；
- `GET /entities/{entity_id}` —— 单个实体的属性 + 出边邻居。

错误响应映射（与 `/documents/{id}/graph` 同族）：
- `EntityNotFoundError` → 404 `ENTITY_NOT_FOUND`；
- `NoActiveKgVersionError` → 409 `KG_VERSION_NOT_ACTIVE`；
- 其它 `GraphUnavailableError` → 501 `NOT_IMPLEMENTED`；
- 跨租户访问 → 403 `FORBIDDEN`（路由层显式判断）。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentIdentity, TraceId
from app.api.v1.responses import (
    ENTITY_NOT_FOUND,
    KG_TENANT_LEAK,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.graph import EntityDetail, GraphOverviewResponse
from app.services.graphs import (
    EntityNotFoundError,
    GraphService,
    GraphUnavailableError,
    NoActiveKgVersionError,
)

#: `graph` 标签单独建路由分组 —— 不与 `documents` 混合，便于 OpenAPI 标签筛选
router = APIRouter(tags=["graph"])


# ---------------------------------------------------------------------------
# 共享 helper（与 `routes/documents.py::_graph_not_available` 同模板，避免重复）
# ---------------------------------------------------------------------------


def _graph_not_available(*, exc: Exception, hint: str) -> AppError:
    """把 Neo4j 不可用映射为 501（基础设施故障，非数据问题）。"""
    return AppError(
        ErrorCode.NOT_IMPLEMENTED,
        "Graph store is unavailable",
        detail={
            "blocked_by": "Neo4j 不可用或 Cypher 执行失败",
            "hint": hint,
            "reason": str(exc),
        },
    )


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.get(
    "/graph/overview",
    response_model=GraphOverviewResponse,
    operation_id="getGraphOverview",
    summary="获取全局图谱概览（批次 C）",
    description=(
        "返回 active `kg_version` 的全局实体子图概览：\n"
        "- `nodes` / `edges` 轻量投影（供前端力导向图渲染）；\n"
        "- `doc_count` / `entity_count` / `relation_count` 三个统计值；\n"
        "- `truncated`：超过 500 节点上限时为 `true`，**前端必须禁用「全部展开」**；\n\n"
        "**一致性（ADR-0002 §3.2）**：只读 active 版本，不存在 active 版本时返回 "
        "**409** `KG_VERSION_NOT_ACTIVE`，**严禁静默降级**到历史版本。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **KG_TENANT_LEAK,
        **KG_VERSION_NOT_ACTIVE,
        **NOT_IMPLEMENTED,
    },
)
async def get_graph_overview(
    identity: CurrentIdentity,
    trace_id: TraceId,
) -> GraphOverviewResponse:
    graph = GraphService.instance()
    try:
        return graph.fetch_graph_overview(
            org_id=identity.org_id,
            trace_id=trace_id,
        )
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"status": "none", "hint": "无 active 版本，拒绝静默降级"},
        ) from exc
    except GraphUnavailableError as exc:
        raise _graph_not_available(exc=exc, hint="`fetch_graph_overview` 失败") from exc


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetail,
    operation_id="getEntityDetail",
    summary="获取实体详情（批次 C）",
    description=(
        "返回单个实体的属性 + 出边邻居（≤ 50 条）：\n"
        "- `attributes`：Neo4j 节点属性（系统字段 `id` / `kg_version` / `org_id` / "
        "`pii_flags` 等已过滤）；\n"
        "- `relations`：实体的 1 跳出边（含 `target_id` / `target_name` / "
        "`relation` 三元组）。\n\n"
        "**错误响应**：\n"
        "- 实体不属于当前 active `kg_version` → **404** `ENTITY_NOT_FOUND`；\n"
        "- Neo4j 不可用 / 无 active 版本 → **501** `NOT_IMPLEMENTED` 或 "
        "**409** `KG_VERSION_NOT_ACTIVE`；\n"
        "- 跨租户访问 → **403** `FORBIDDEN`（**不**走 404，避免混淆资源不存在与"
        "权限不足 —— M5 §3 验收 1）。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **KG_TENANT_LEAK,
        **KG_VERSION_NOT_ACTIVE,
        **ENTITY_NOT_FOUND,
        **NOT_IMPLEMENTED,
    },
)
async def get_entity_detail(
    entity_id: str,
    identity: CurrentIdentity,
    trace_id: TraceId,
) -> EntityDetail:
    graph = GraphService.instance()
    try:
        return graph.fetch_entity_detail(
            entity_id=entity_id,
            org_id=identity.org_id,
            trace_id=trace_id,
        )
    except EntityNotFoundError as exc:
        raise AppError(
            ErrorCode.ENTITY_NOT_FOUND,
            detail={"entity_id": entity_id, "reason": str(exc)},
        ) from exc
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"entity_id": entity_id, "status": "none"},
        ) from exc
    except GraphUnavailableError as exc:
        raise _graph_not_available(
            exc=exc, hint=f"`fetch_entity_detail` entity_id={entity_id}"
        ) from exc
