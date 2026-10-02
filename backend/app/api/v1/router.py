"""v1 路由聚合。

**接口范围**：严格按阶段 3.1 决策 + 各 Sprint 增补（plan §4.2）。
当前注册：
- `GET /health`
- `POST /documents/upload`、`GET /documents`、`GET /documents/{id}/status`、
  `GET /documents/{id}/graph`、`GET /documents/{id}/chunks/{chunk_id}`（M1 / Sprint 6）
- `GET /graph/overview`、`GET /entities/{id}`、`POST /graph/versions/{version}/activate`
  （Sprint 5 批次 C / Sprint 6.2）
- `POST /agent/query`（M2 / M3）
- `POST /affiliation/detect`、`GET /affiliation/tasks/{id}`、`GET /affiliation/suspicions`、
  `PATCH /affiliation/suspicions/{id}`（**Sprint 7.2 批次 B**，spec §5.5；
  路径口径以 spec 为准，plan §6.2 摘要原写 `/affiliation/suspects` 已统一为 `suspicions`）
- `GET /audit`、`GET /audit/trace/{trace_id}`（**Sprint 8.1 批次 A**，M5 §3 验收 7 / 6）
- `GET /attendance/compliance/scan`（**Sprint 9.5 批次 C3**，考勤域合规预警，确定性规则）
- **M6 契约先行批次**（`changes/P0-m6-finalization` F2，**7 个端点全部 501 占位**，
  实现归 P5-M6 / Sprint 12）：`POST /ontology/cold-start`、`POST /ontology/confirm`、
  `POST /ontology/merge`、`POST /ontology/split`、`POST /ontology/rename`、
  `GET /ontology/active`、`GET /cost/dashboard`（spec §5.5）

specs 中其余端点草案（`/auth/login`、`/internal/*` 等）留在草案态，后续 Sprint 逐步纳入。

**为什么占位端点也要注册**：契约由 `scripts/export_openapi.py` **从 app 导出**
（后端模型是唯一真源）⇒ 端点不注册就进不了 `contracts/openapi.yaml`，
前端 `gen:api` 也就拿不到类型，spec §10 ④「契约漂移核验」永远勾不上。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    affiliation,
    agent,
    audit,
    compliance,
    cost,
    documents,
    graph,
    health,
    ontology,
)
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_prefix)

api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(graph.router)
api_router.include_router(agent.router)
api_router.include_router(affiliation.router)
api_router.include_router(audit.router)
# Sprint 9.5 批次 C3：GET /attendance/compliance/scan
api_router.include_router(compliance.router)
# M6 契约先行批次（P0-m6-finalization F2）：6 个 ontology 端点 + GET /cost/dashboard，
# 全部 501 占位骨架
api_router.include_router(ontology.router)
api_router.include_router(cost.router)
