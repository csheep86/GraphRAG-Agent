"""v1 路由聚合。

**接口范围**：严格按阶段 3.1 决策，只注册 5 个核心接口；
specs 中其余端点草案（`/auth/login`、`/audit*`、`/internal/*` 等）留在草案态，
Sprint 3 逐步纳入，禁止提前注册。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import agent, documents, health
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_prefix)

api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(agent.router)
