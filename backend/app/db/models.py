"""ORM 模型。

Sprint 1 只落 `documents`（M1 §4.1）；`kg_versions` / `qa_logs` 等表留 Sprint 3。
ADR-0003 要求在实现期给所有核心表补 `org_id`，本表已预留并建立
**以 `org_id` 打头**的复合索引（RLS 策略的性能前提）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOCUMENT_STATUS_VALUES = ("pending", "processing", "completed", "failed")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """声明式基类。"""


class Document(Base):
    """`documents` 表（M1 §4.1）。"""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_documents_status",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_documents_org_id_status", "org_id", "status"),
        Index("ix_documents_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: 原始文件名 SHA-256（日志禁止输出原文，M1 §4.1）
    filename_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 租户隔离键（ADR-0003）
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 存储键，格式 `{org_id}/{doc_id}/{filename_hash}`，解析完成后填写（M1 §4.3）
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 失败明细（敏感，日志禁输出）
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
