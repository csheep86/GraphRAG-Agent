"""ORM 模型。

Sprint 1 只落 `documents`（M1 §4.1）；`kg_versions` / `qa_logs` 等表留 Sprint 3。
ADR-0003 要求在实现期给所有核心表补 `org_id`，本表已预留并建立
**以 `org_id` 打头**的复合索引（RLS 策略的性能前提）。

Sprint 5 批次 B 新增 `kg_versions` 表（ADR-0002 §3.2：状态机迁 PG），
与 `documents` 同样以 `org_id` 打头建复合索引。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
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
KG_VERSION_STATUS_VALUES = ("pending", "building", "ready", "failed")


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

    # -- 企业集成预留字段（ADR-0004 接缝 2 / plan §8.2；Sprint 5 批次 A2）--
    # 一律 nullable、只落库、**不进 contracts/openapi.yaml**（预留纪律：
    # export_openapi.py --check 无 diff）。只在对应集成真正启用时才提升到契约。
    source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # upload/api/connector
    source_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # 外部系统引用
    document_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # 业务侧主键
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 幂等去重
    source_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 外部版本
    acl_scope: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 未来 ACL 边界
    acl_owner_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # 未来属主
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 软删
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    # -- 阶段级状态（Sprint 5 批次 B：document.parse → document.extract → kg.build）--
    # 与 8 预留字段同形：nullable + 只落库 + **不进 contracts/openapi.yaml**。
    # 整体状态仍由 ``status`` 表达（``DocumentStatusResponse`` 仅暴露此字段）；
    # 阶段列仅供执行体自身重试 / 故障诊断 + 内部审计。
    extract_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extract_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kg_build_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kg_build_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    #: 本次构建产物 ``kg_versions.id``（ready 后回填；与 ``kg_versions.org_id`` 同租户）
    kg_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class KgVersion(Base):
    """`kg_versions` 表（ADR-0002 §3.2：kg_version 状态机真源）。

    Sprint 5 批次 B 落地：Neo4j 上的 ``:KgVersion`` 降级为**冗余镜像**
    （`:KgVersionMirror`），PG 为唯一真源——路由层 ``fetch_active_kg_version``
    改为先查本表，Neo4j 查询仅作兜底（批次 D 的"PG 兜底一致性"约定）。

    字段约束：
    - ``status`` 受 CheckConstraint 限制合法值；
    - ``source_doc_ids`` 存 PG ``documents.id`` 列表（JSON），供 fail-closed
      cross-check 取子图所属文档；
    - ``entity_count`` / ``relation_count`` 在 ``mark_ready`` 时回填，便于审计。
    """

    __tablename__ = "kg_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'building', 'ready', 'failed')",
            name="ck_kg_versions_status",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_kg_versions_org_id_status", "org_id", "status"),
        Index("ix_kg_versions_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 同 org 内唯一（"per_org" 策略）；Neo4j ``:KgVersionMirror.version`` 同步此值
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ``pending → building → ready`` 或 ``→ failed``（ADR-0002 §3.2）
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 此次构建涵盖的源文档 ID（JSON 数组，元素为 UUID 字符串——json.dumps 不支持
    #: UUID 原生类型；KgVersioningService 负责入库 str / 出库 UUID 的双向转换）
    source_doc_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    #: ready 时刻填写（审计用）
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
