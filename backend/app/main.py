"""FastAPI 应用装配入口。

启动：`uv run uvicorn app.main:app --reload`（工作目录为 `backend/`）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import logger, setup_logging
from app.core.middleware import TRACE_ID_HEADER, AuditMiddleware, TraceIdMiddleware
from app.core.openapi import build_openapi
from app.db.session import dispose_engine, init_db
from app.tasks import recover_orphan_tasks


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Sprint 1 直接建表；Sprint 3 接入 Alembic 迁移后移除（见 db/session.py）
        init_db()
        # ADR-0001 §3.2 / M1 §3 验收 8：进程启动回收遗留 pending / processing 任务
        recovery = recover_orphan_tasks()
        logger.bind(
            app_env=settings.app_env,
            app_version=settings.app_version,
            # 只记录驱动名，避免把数据库口令写进日志（CODEBUDDY.md 安全底线）
            db_driver=settings.database_url.split(":", 1)[0],
            dev_org_header_enabled=settings.dev_org_header_enabled,
            task_recover_reclaimed=recovery.reclaimed,
        ).info("application_startup")
        try:
            yield
        finally:
            dispose_engine()
            logger.info("application_shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="GraphRAG-Agent 后端 API（契约 v1.0）",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # 注意 add_middleware 为「后加者在外层」：TraceId 必须最外层，
    # 才能保证 CORS 预检等所有响应都带上 X-Trace-Id。
    # 审计必须挂在 TraceId **之内**（先 add）：它要靠 contextvar 拿 trace_id，
    # 挂在外层的话取到的是 None（M5 §3 验收 6）。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[TRACE_ID_HEADER],
    )
    app.add_middleware(AuditMiddleware)
    app.add_middleware(TraceIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    # 契约由 Pydantic 模型生成，后端是唯一真源（CODEBUDDY.md 契约同步铁律）
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]

    return app


app = create_app()
