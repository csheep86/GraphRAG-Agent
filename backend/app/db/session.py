"""数据库引擎与会话。

**Sprint 1 临时兜底**：默认 `sqlite:///./dev.db`，不支持 RLS。
Sprint 3 集成 PostgreSQL 后必须启用行级安全，并在每个事务内
`SET LOCAL app.current_org = :org_id`（ADR-0003 §3.2 / §3.6）。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith("sqlite"):
        # SQLite 在多线程 ASGI 场景下需要放开同线程检查
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个会话。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """建表。

    仅 Sprint 1 使用；Sprint 3 接入 Alembic 迁移后删除本函数调用。
    """
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)


def check_database() -> bool:
    """健康检查用：探测数据库连通性。"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - 健康检查不允许抛出
        return False
    return True


def dispose_engine() -> None:
    engine.dispose()
