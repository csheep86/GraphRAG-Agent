"""数据库引擎与会话。

**DR-B1**：开发 / 测试 / 生产一律 PostgreSQL 16.x。SQLite 既非替身也非兜底，
方言特判不允许保留（ADR-0003 §3.6.2 已将 SQLite 列为待偿债务，现已清偿）。

租户隔离依赖 RLS：每个事务内须 `SET LOCAL app.current_org = :org_id`
（ADR-0003 §3.2 / §3.6）。**RLS 策略本身归 P3（DR-B4），本阶段不落地。**
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _build_engine() -> Engine:
    """建引擎（PostgreSQL）。

    原先多线程 ASGI 场景下那条 SQLite 方言 ``connect_args`` 特判已于 **DR-B3** 删除：
    PostgreSQL 无此项，保留它等于给「SQLite 上明明跑得好好的」留一条回头路。

    ⚠️ 不要在此文件（含注释）重新写出那个被删开关的**名字**：G-21 是按**字样**扫描
    本文件的，连「已删除」的说明也会让它判定为命中（本批次实踩两次）。
    """
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


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
    """建表（``create_all``）。

    **dev / 测试兜底**（启动行为不变，Sprint 9.7 起）：生产升级走
    ``alembic upgrade head``（基线见 ``migrations/versions/``，部署流程见
    ``docs/deployment-spec.md`` §7.2）。两者等价由
    ``tests/test_migrations_baseline.py`` 钉死——**加表 / 加列必须生成新迁移**。
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
