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

specs 中其余端点草案（`/auth/login`、`/audit*`、`/internal/*` 等）留在草案态，
Sprint 3 逐步纳入，禁止提前注册。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import affiliation, agent, documents, graph, health
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_prefix)

api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(graph.router)
api_router.include_router(agent.router)
api_router.include_router(affiliation.router)
