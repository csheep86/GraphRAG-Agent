"""ORM 模型。

Sprint 1 只落 `documents`（M1 §4.1）；`kg_versions` / `qa_logs` 等表留 Sprint 3。
ADR-0003 要求在实现期给所有核心表补 `org_id`，本表已预留并建立
**以 `org_id` 打头**的复合索引（RLS 策略的性能前提）。

Sprint 5 批次 B 新增 `kg_versions` 表（ADR-0002 §3.2：状态机迁 PG），
与 `documents` 同样以 `org_id` 打头建复合索引。

Sprint 7.2 批次 B 新增 M4 三张表（`affiliation_tasks` / `affiliation_suspicions` /
`unaligned_subjects`）：表名与字段逐字照 `specs/m4-affiliation-detection.md` §4.3–4.5，
三表**均带 `org_id` 且复合索引以 `org_id` 打头**（ADR-0003 第 54–56 行）。
**无 Alembic**：建表靠启动时的 ``create_all``（见 :mod:`app.db.session`）。
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


AFFILIATION_TASK_STATUS_VALUES = ("pending", "processing", "completed", "failed")
"""`affiliation_tasks.status` 合法值（ADR-0001：PG 为唯一真值源）。"""

SUSPICION_STATUS_VALUES = ("open", "dismissed", "confirmed")
"""`affiliation_suspicions.status` 合法值（spec §4.3）。"""

SUSPICION_TYPE_VALUES = ("shared_legal_rep", "shared_address")
"""本批次能产出的疑点类型（spec §3 验收 3 的最小集）。

spec 全集还含 ``shared_phone`` / ``cycle`` / ``amount_mismatch``，但它们依赖
``:Phone`` / ``:Invoice`` / ``:Voucher`` / ``:Contract`` 节点（**Sprint 9 批次 B**）。
**不提前把产不出的数据写进允许集合**——那等于向调用方承诺不存在的能力；
S9 落地时同步扩本常量 + CheckConstraint + 契约枚举。
"""

SUSPICION_SEVERITY_VALUES = ("high", "medium", "low")
UNALIGNED_SUBJECT_STATUS_VALUES = ("pending", "aligned", "ignored")
#: ADR-0004 §4：`external_refs.object_type` 取值（外来 ID ↔ 图谱 ID 的映射对象类型）
EXTERNAL_OBJECT_TYPES = ("entity", "document", "org")


class AffiliationTask(Base):
    """`affiliation_tasks` 表（M4 §4.4：一次关联交易检测 = 一条任务）。

    状态机**逐字**照 ADR-0001 §3：``pending → processing → completed / failed``，
    **唯一真值源 = PostgreSQL**（严禁进程内存），且必须被
    :func:`app.tasks.manager.recover_orphan_tasks` 扫到（同 ADR 第 73 行要求扫
    ``documents`` + ``affiliation_tasks`` 两张表）。

    与其它任务表的差异：一次检测覆盖**多份**文档（``doc_ids``），所以
    ``task_id`` 是本表主键，**不是** ``documents.id``——这正是批次 B 决策 **B8**
    要扩展 ``TaskManager.submit()`` 的原因。
    """

    __tablename__ = "affiliation_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_affiliation_tasks_status",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_affiliation_tasks_org_id_status", "org_id", "status"),
        Index("ix_affiliation_tasks_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 本次检测覆盖的文档 id（JSON 数组，元素为 UUID 字符串——沿用
    #: ``KgVersion.source_doc_ids`` 的写法：``json.dumps`` 不支持 UUID 原生类型）
    doc_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 已重试次数（H8；每次重试写回——有列必须有消费者，同 B1 纪律）
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 失败明细（**敏感**，日志禁输出）
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: 完成后填入 ``{total, by_type, top_5_severity}``
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)


class AffiliationSuspicion(Base):
    """`affiliation_suspicions` 表（M4 §4.3：疑点 + 状态 + 证据引用）。

    两条硬约束：

    1. **引用覆盖率 = 100%**：证据取不到的命中在算法层就被丢弃
       （``affiliation_suspicion_dropped_no_evidence``），故 ``evidence`` **非空**；
    2. ``task_id``（批次 B 决策 **B2** 新增）回答「这条疑点属于哪一批检测」——
       没有它，``GET /affiliation/suspicions`` 只能靠 ``created_at`` 猜最新批次
       （并发 / 补跑下不稳）或返回全部历史疑点（新旧混杂）。
    """

    __tablename__ = "affiliation_suspicions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'dismissed', 'confirmed')",
            name="ck_affiliation_suspicions_status",
        ),
        CheckConstraint(
            "suspicion_type IN ('shared_legal_rep', 'shared_address')",
            name="ck_affiliation_suspicions_type",
        ),
        CheckConstraint(
            "severity IN ('high', 'medium', 'low')",
            name="ck_affiliation_suspicions_severity",
        ),
        Index("ix_affiliation_suspicions_org_id_status", "org_id", "status"),
        # 「返回哪一批疑点」的主查询路径（B2）
        Index("ix_affiliation_suspicions_org_id_task_id", "org_id", "task_id"),
        Index("ix_affiliation_suspicions_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 产出该疑点的 ``affiliation_tasks.id``（B2 新增，必有写入方）
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    suspicion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    #: 涉及节点 id 列表（[主体A, 主体B, 共享节点]）
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    #: 与 entities 对应的名称（仅展示用；判重以 id 为准）
    entity_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    #: 原文证据引用列表（**非空**：无证据的疑点不落库）
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    kg_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    #: 复核人（`X-Actor-Id`；M5 落地后改为 token 主体）
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)


class UnalignedSubject(Base):
    """`unaligned_subjects` 表（M4 §4.5：未对齐主体）。

    **本批次只建表不写**（批次 B 决策 **B5**）：四源主体对齐属 **Sprint 9 批次 D**，
    spec §3 验收 1 的「对齐成功率 ≥ 0.95」同样在那里才可能判定。现在写只能靠凑——
    与其塞假数据，不如诚实留空，并把「空表」登记到
    `backend/CODEBUDDY.md` §4（避免变成无人知晓的死表）。
    """

    __tablename__ = "unaligned_subjects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'aligned', 'ignored')",
            name="ck_unaligned_subjects_status",
        ),
        Index("ix_unaligned_subjects_org_id_status", "org_id", "status"),
        Index("ix_unaligned_subjects_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_doc_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    candidates: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ExternalRef(Base):
    """`external_refs` 表（ADR-0004 §4 接缝 7：外来 ID ↔ 本系统 ID 的唯一映射）。

    **本批次只建表 + 写入点**（plan §6.2 批次 B）：写入点是
    `python -m app.services.external_data.cli`（外部数据导入 CLI，接缝 8）。
    **不对接任何真实外部系统**——按 ADR-0004 §5 难题 2：接 1 个系统时映射很简单，
    难的是接 8 个系统后「同一个供应商在 ERP / OA / CLM / MDM 里是 4 个 ID」；
    本阶段**不预判**那个解法，只把映射面本身准备好。

    字段与类型控制在受socket范围内下降维：``local_id`` / ``external_id`` 用字符串
    （外部 ID 不一定是 UUID，造 UUID 就是编数据），``object_type`` / ``external_system``
    按 ADR-0004 §4 取值。
    """

    __tablename__ = "external_refs"
    __table_args__ = (
        CheckConstraint(
            "object_type IN ('entity', 'document', 'org')",
            name="ck_external_refs_object_type",
        ),
        Index("ix_external_refs_org_id_object_type", "org_id", "object_type"),
        # 唯一性：同一外部系统里一个外来 ID 只能映射到本系统的一个对象
        Index(
            "ux_external_refs_org_sys_ext",
            "org_id",
            "external_system",
            "external_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 本系统 ID（图谱实体 ID / 文档 ID）——**字符串**，因为外部系统侧的 ID 未必是 UUID
    local_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_system: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # mdm / erp / gsxt / hr …
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class DomainEvent(Base):
    """`domain_events` 表（ADR-0004 §2.1 接缝 5 事件出口；Sprint 7.4 批次 D）。

    **只落库不派发**（plan §6.2 批次 D 口径）：``dispatched_at`` **恒为 NULL**——
    本阶段无订阅方、无重试、无 webhook；未来接 OA / BPM / ITSM 时由新增的 sink
    消费本表并回写该字段（ADR-0004 §4）。

    **预留表不进契约**（CODEBUDDY §功能预留原则第 4 条）：本表**不**出现在
    `contracts/openapi.yaml`，前端也不消费它。

    事件类型按 ADR-0004 登记四个；本批次**只有** ``risk.suspect_created`` 有真实
    事件源（疑点落库处），其余三个仅定义取值、**不发送**——没有真实触发点却发，
    就是假事件。
    """

    __tablename__ = "domain_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('document.parsed', 'kg.updated', "
            "'risk.suspect_created', 'qa.answered')",
            name="ck_domain_events_event_type",
        ),
        Index("ix_domain_events_org_id_event_type", "org_id", "event_type"),
        Index("ix_domain_events_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 聚合根类型 / id（疑点事件为 ``affiliation_suspicion`` / ``<suspicion_id>``）
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 事件体（JSON；各事件类型自定字段）
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    #: 派发时间；**本阶段恒为 NULL**（只落不派），未来由新增 sink 回写
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
