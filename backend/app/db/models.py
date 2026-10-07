"""ORM 模型。

Sprint 1 只落 `documents`（M1 §4.1）；`kg_versions` / `qa_logs` 等表留 Sprint 3。
ADR-0003 要求在实现期给所有核心表补 `org_id`，本表已预留并建立
**以 `org_id` 打头**的复合索引（RLS 策略的性能前提）。

Sprint 5 批次 B 新增 `kg_versions` 表（ADR-0002 §3.2：状态机迁 PG），
与 `documents` 同样以 `org_id` 打头建复合索引。

Sprint 7.2 批次 B 新增 M4 三张表（`affiliation_tasks` / `affiliation_suspicions` /
`unaligned_subjects`）：表名与字段逐字照 `specs/m4-affiliation-detection.md` §4.3–4.5，
三表**均带 `org_id` 且复合索引以 `org_id` 打头**（ADR-0003 第 54–56 行）。

Sprint 8.1 批次 A 新增审计 / 问答两张表（`audit_log` / `qa_logs`）：字段逐字照
`specs/m5-permission-audit.md` §4.4 与 `specs/m3-graphqa-citation.md` §4.3，
主键统一用 UUID（**不用** spec 写的 BIGSERIAL，差异登记 ADR-0003 §A9）。

Sprint 9.5 批次 A2 新增 `ontology_schemas` 表（M6 §4.1 的**最小子集**：
只建表 + 写考勤域种子，**不做**冷启动 GUI / 校正界面 / 增量重算，那些保持 S12）。
字段逐字照 `specs/m6-ontology-incremental.md` §4.1；
主键按 spec 取 **`(org_id, version)` 复合主键**（version 每 org 独立自增），
与其余表的 UUID 单主键不同——**以 spec 为准，不套用本文件的 UUID 惯例**。
**Alembic 基线已建立**（Sprint 9.7，``migrations/versions/00f44b912817_*``）：
生产升级按 ``docs/deployment-spec.md`` §7.2 手动 ``alembic upgrade head``；
``create_all`` 保留为 dev / 测试兜底，两者等价由
``tests/test_migrations_baseline.py`` 机械钉死（**加表 / 加列必须生成新迁移**，
否则该测试必红）。

P2 批次 A（2026-10-01）新增 `users` 表（M5 §4.1 / DR-B13）：它是 SSO（DR-D9）/
RBAC（DR-B9）/ License 席位（DR-C1）三者的**共同前置**，按 RK-1 裁决前置到 P2 第一步。
本批**只落表与迁移**：当前**没有任何代码读取它**（接线归 P2-B / P2-C）。

P2 批次 B（2026-10-03）新增 `roles` / `user_roles` 两张表（M5 §4.2 / §4.3 / DR-B9）：

- `roles` 是**全局角色字典表**，按 ADR-0003 §3.1 第 9 行**显式豁免 RLS**
  （豁免声明 / 理由 / 三条机械断言见 `specs/m5-permission-audit.md` §4.2，
  本批按 2026-10-03 裁决以「代码内显式声明 + 机械断言」履行）；
- `user_roles` 带 `org_id` 且**复合索引以 `org_id` 打头**（ADR-0003 §3.1 第 1 条），
  `doc_scope` / `scene_scope` 承载**文档级 / 场景级**两粒度；
- **本批不做 RLS 策略**（DR-B4 归 **P3**）：这里只做 `roles` 的豁免**登记**，
  策略本身一行不写。

P5-C（2026-10-07，D2 / M6 第一批）新增 `ontology_actions` 表（M6 §4.2 的审计载体）：
本表的存在理由是把「**未确认不生效**」变成可举证——确认动作落得到一行，
而不是只留在日志里。带 `org_id` ⇒ **自动**成为租户表（G-26 会盯着它的 RLS）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOCUMENT_STATUS_VALUES = ("pending", "processing", "completed", "failed")
KG_VERSION_STATUS_VALUES = ("pending", "building", "ready", "failed")
#: `users.status` 的两档（逐字取 `specs/m5-permission-audit.md` §4.1，无第三态）
USER_STATUS_VALUES = ("active", "disabled")

#: `roles.name` 的**封闭集合**（逐字取 `specs/m5-permission-audit.md` §4.2）。
#: P2-B 边界：**不得新增角色名**——要加角色须先改 spec §4.2，再改本元组与
#: `app/services/rbac/roles.py::PRESET_ROLES`，最后由 G-24 的机械断言复核。
ROLE_NAME_VALUES = ("admin", "auditor", "analyst", "viewer")

#: **RLS 豁免登记表**（ADR-0003 §3.1 第 9 行 / `specs/m5-permission-audit.md` §4.2）。
#:
#: 只有**全局字典表**（无租户维度）才配进本集合；进来了就**不参与** RLS 隔离，
#: 因此它是一个**高危集合**：偷偷往里加表 = 开一个不受租户约束的口子。
#: ⇒ 两条机械约束（由 `tests/test_guardrails_compliance.py` 的 G-24 组断言盯住）：
#:   ① 本集合必须与「模型上声明了 ``__rls_exempt__`` 的表」**逐字相等**（防偷偷加表）；
#:   ② 豁免表**不得出现租户业务列**（无 ``org_id``）——出现即说明字典表被业务污染。
#:
#: **2026-10-06 P4 追加 ``licenses``**（ADR-0006 §3.1）：它是**实例级**表——
#: 一机一 License，本就没有租户维度，与 ``roles`` 同属「无租户维度的系统表」。
#: 新增豁免表属破坏性变更，故连带同步了 ``tests/test_guardrails_rls.py`` 的
#: 豁免集合断言（该断言原本硬写 ``{"roles"}``）——**不是放宽**，是登记项更新，
#: 收紧程度不变（仍断言「库里真的没有策略」+「集合恰好相等」）。
RLS_EXEMPT_TABLES: frozenset[str] = frozenset({"roles", "licenses"})

#: `ontology_actions.action_type` 的合法值（M6 §4.2 的**三值** + 本批增补）。
#:
#: ⚠️ **偏离登记 X-2a（changes/P5-C）**：spec §4.2 明文写「``merge / split / rename``
#: **仅三值**」，那句源自 plan §12 R12 对**批次 B（校正 GUI 三动作）**的收口，
#: 并**没有**定义**批次 A（冷启动 / 确认）**的审计载体。而本批的验收判据要求
#: 「确认后状态变化必须写进 ``ontology_actions``」——写不进来，本批这张表就
#: 是 **零写入方**的表（等价于心照不宣的"建了等于没建"）。故取最小增补：
#: **只加一个 ``confirm``**，并把理由写在这里而不是藏进代码。
#: 撤回成本：一个迁移删掉 CHECK 里的第四值即可（那条判据随之作废）。
ONTOLOGY_ACTION_TYPES = ("merge", "split", "rename", "confirm")
#: 偏离登记 **X-2b**：只有 ``confirm`` 允许 ``kg_version`` 为 NULL ——
#: 确认本体时图谱尚不存在（spec §4.6 的新租户链路：先确认本体，后有图谱），
#: 该场景**没有** kg_version 可写，写假值等于 fabrication。
ONTOLOGY_ACTION_WITHOUT_KG_VERSION = "confirm"


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

    # -- 知识时效（Sprint 9 批次 A，ADR-0005 §4 / §6 L0）--
    #: 文档的**业务日期**（签署日 / 披露日 / 报表期首日），
    #: 是关系 ``valid_from`` 的**兜底源**（R4 不猜值：文本无显式日期时取它）。
    #:
    #: - 可空：不是每份文档都有可识别日期，**不代填"今天"**（假日期比没日期危险）；
    #: - **不进 contracts/openapi.yaml**：本期由集成侧写入，REST 上传接口暂不接收
    #:   （与外部系统导入同口径），待对接方确需由 API 指定时才提升到契约；
    #: - 消费者：``tasks/registry.py`` 传给 ``LangextractClient`` → 渲染进 Prompt v3。
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class RelationExpiryPolicy(Base):
    """`relation_expiry_policies` 表（ADR-0005 §6 L1；CP-T1 第 3 条的定义落地）。

    回答一个问题：**某个 ``relation_type`` 是否只能有一个"当前值"**。

    - ``single_current``：同一 ``head`` 只允许一个当前 tail（法定代表人 / 注册地址）
      ⇒ L1 仲裁会按 R1 / R2 把旧边 ``valid_to`` 封掉；
    - ``append_only``：多值并存，天然不矛盾（对外投资、供应商）
      ⇒ 仲裁**完全跳过**该类型。

    ``relation_type = '*'`` 是该租户的**兜底行**（查不到具体类型时用它的策略）；
    连兜底行都没有 ⇒ 默认 ``append_only``（保守：不封）。见
    :func:`app.services.kg.policies.load_expiry_policies`。

    **不进 contracts/openapi.yaml**：本期由运维 / 集成侧按租户初始化，
    没有 REST 写入接口（与外部系统导入同口径）。
    """

    __tablename__ = "relation_expiry_policies"
    __table_args__ = (
        CheckConstraint(
            "policy IN ('single_current', 'append_only')",
            name="ck_relation_expiry_policies_policy",
        ),
        UniqueConstraint(
            "org_id", "relation_type", name="uq_relation_expiry_policies_org_type"
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_relation_expiry_policies_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    #: 关系类型；``'*'`` = 该租户的兜底行
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 有效期策略（CheckConstraint 限两档）
    policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="append_only"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


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

SUSPICION_TYPE_VALUES = (
    "shared_legal_rep",
    "shared_address",
    "missing_check_in",
    # ---- Sprint 9.12 批次 C2：算法型三类（spec §4.7.2 判据已冻结）----
    "shared_phone",
    "cycle",
    "amount_mismatch",
)
"""能产出的疑点类型（spec §3 验收 3 的最小集 + 两批域化 / 算法化新增）。

- 前两类是 **M4 金融域**（``shared_legal_rep`` / ``shared_address``），**保留不删**；
- ``missing_check_in`` 是 **考勤域**「工作日缺卡」（``attribution.ANOMALY_MISSING_CHECK_IN``）；
- ``shared_phone`` / ``cycle`` / ``amount_mismatch`` 是 **Sprint 9.12** 补的三类算法
  与三方金额不一致（判据见 `specs/m4-affiliation-detection.md` §4.7.2）。

**为什么现在才扩**：这三类依赖 ``:Phone`` / ``:Contract`` / ``:Invoice`` / ``:Voucher``
与 ``SHARES_HOLDER`` 持股边——**数据没有就是没有**，把它们提前写进允许集合等于
向调用方承诺不存在的能力。语料与摄入器就位（S9.11 / S9.12）后才扩。

**改这里必须同步（四处 + 契约）**：
``ck_affiliation_suspicions_type`` CheckConstraint（本文件）+ 契约枚举
（``app/schemas/affiliation.py::SuspicionType``）+ Alembic 迁移
（``create_all`` **不会**改已存在的表）+ `npm run gen:api`（CI 有契约零漂移校验）。
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
            "suspicion_type IN ('shared_legal_rep', 'shared_address', "
            "'missing_check_in', 'shared_phone', 'cycle', 'amount_mismatch')",
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
    #: 归因原因链（Sprint 9.5 批次 C2 扩展）：``[{code, reason, weight, matched,
    #: evidence[]}]``。
    #:
    #: **可空且默认为空**：金融域疑点与 C2 之前的历史数据没有归因，
    #: 用 ``None`` 表示「未归因」，**不**用空列表冒充「归过因、零命中」——
    #: 二者语义相反（后者等于说证据全没对上）。
    causes: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    #: **Sprint 9.12 新增**：``amount_mismatch`` 的三方金额明细
    #: （``{trade_ref, contract_amount, invoice_amount, voucher_amount, max_diff}``，
    #: spec §3 验收 5 要求「差额 + 三方各自金额」）。其余类型一律 ``None``——
    #: **不**为了字段非空而塞空对象（``{}`` 等于宣称"有明细但内容为空"）。
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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

    **写入方（Sprint 9.11 批次 C1 已偿还 S7.2-1）**：
    `backend/scripts/ingest_affiliation_sources.py`——四源 CSV 摄入后走
    「税号 → 规范化名称 → 规范化地址」三级对齐（口径见 `specs/m4` §4.6），
    三级都未命中或命中多个 canonical 主体的行落本表，带 `reason`
    （`tax_id_missing` / `name_mismatch` / `multiple_candidates`）。

    **本表无读端点**（S9.11 裁决 **D-B**）：不进契约、前端不消费，
    缺口登记在 `specs/m4` §6 **S9.11-1**——写进去没人读，但不假装它已闭环。

    2026-09-24 建表时曾**刻意留空**（批次 B 决策 B5，避免塞假数据），
    原因是当时四源对齐还没做；写入方就位后该理由失效，故更新本注释。
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


class EntityMergeCandidate(Base):
    """`entity_merge_candidates` 表（M2 §4.5：实体消解候选，Sprint 9.13 批次 C3）。

    **判据**冻结在 `specs/m2-extract-kg.md` **§4.5.1**（先冻结、后写代码）：
    相似度 = 名称相似度 + 结构加分，三条否决（N1 税号冲突 / N2 多候选 / N3 同税号），
    三档处置（≥0.90 `auto_merged` / 0.70–0.90 `human_review` / <0.70 **不落表**）。

    两条**必须写进注释**的事实，免得后来者误判：

    1. `left_entity_id` / `right_entity_id` 是 **TEXT 而非 spec 起草时的 UUID**
       （偏离登记 **S9.13-1**，理由见 spec §4.5 表下注脚）：图谱侧实体 id 是稳定字符串
       （主体层 `SUBJECT:<税号>`、未对齐行 `RAW:<file>:<key>`），**没有 UUID 可存**；
    2. `status` 的 `applied` 是 **M6 前向预留值**（spec §4.5 注脚 + S9.11 裁决 D-C）：
       枚举里**有**、运行时**不写**、契约侧**零改动**——不为"走出 diff"而造端点。
       `pending` / `rejected` 同理：本阶段无写入方（<0.70 的候选根本不落表）。
    """

    __tablename__ = "entity_merge_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'auto_merged', 'human_review', 'rejected', "
            "'applied')",
            name="ck_entity_merge_candidates_status",
        ),
        CheckConstraint(
            "similarity >= 0.0 AND similarity <= 1.0",
            name="ck_entity_merge_candidates_similarity",
        ),
        Index("ix_entity_merge_candidates_org_id_status", "org_id", "status"),
        Index("ix_entity_merge_candidates_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 图侧实体 id（**字符串**，见 §偏离 S9.13-1）
    left_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    right_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    #: 判分依据（``{name_sim, struct_bonus, tax_conflict, multi_candidate?}``）——
    #: 审计要能回答"为什么是这一档"，只有分数不够
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)


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


AUDIT_LOG_STATUS_VALUES = ("success", "failure")
"""`audit_log.status` 合法值（`specs/m5-permission-audit.md` §4.4）。

`failure` 既覆盖 4xx 也覆盖 5xx：**审计语义是「这次调用有没有成功」**，与 HTTP
状态码族无关；真正的错误码在响应体里，不在本列。
"""


class AuditLog(Base):
    """`audit_log` 表（M5 §4.4：任一 API 调用成功 / 失败都落一条）。

    写入点**唯一** = 审计中间件（Sprint 8.1 批次 A 决策 **A1**：全量写 + allowlist），
    不是各服务显式埋点——埋点必然漏，且「漏埋」比「多写」更难被发现。

    三条硬纪律：

    1. **不复用 `domain_events`**：后者 ``payload`` 是无结构 dict（无法按
       ``action`` / ``status`` / ``actor_id`` 建索引），语义是「对外出口」而非
       「对内留痕」（决策 **A10**）；
    2. **`detail` 只写结构化字段**，**绝不写响应体原文**——本批次不引入脱敏器
       （属 H5 / S11），以「不写原文」规避新增泄露面（决策 **A5**）；
    3. **写失败只记日志、不抛异常**：审计缺陷不得变成全站 500（proposal 风险 2）。

    ``actor_id`` 可空：系统触发（如回收任务）没有操作者时不编造 UUID。
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failure')",
            name="ck_audit_log_status",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        # （`GET /audit` 的主查询路径：按 org 过滤 + ts DESC 分页）
        Index("ix_audit_log_org_id_ts", "org_id", "ts"),
        Index("ix_audit_log_org_id_action", "org_id", "action"),
        Index("ix_audit_log_org_id_status", "org_id", "status"),
        Index("ix_audit_log_org_id_trace_id", "org_id", "trace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    #: 操作类型。已登记路由取业务名（`document.upload` / `agent.query` …）；
    #: 未登记路由回落 ``http.<method>.<path>``（决策 **A2**：宁可 action 丑，不可无记录）
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    #: 资源标识（如 ``document:<uuid>``；无明确主体时取 ``<METHOD> <path>``）
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 明细（**只放结构化字段**：status_code / path / 路径参数；严禁原文）
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class QaLog(Base):
    """`qa_logs` 表（M3 §4.3：每次问答留痕，成功与拒答**都落**）。

    本表正是 S6.4 对账时登记的缺口偿还点（`specs/m3-graphqa-citation.md` §6 S6.4-3）：
    ``AgentService.query`` 此前全函数零 DB 写入。

    ``question_hash`` / ``answer_hash`` **只存 SHA-256**，不存原文（M3 §5.3 纪律：
    提问本身可能含敏感信息）。注意这是**不可逆哈希而非脱敏**——本批次不引入脱敏器，
    也不在库里保留原文（决策 **A5**）。
    """

    __tablename__ = "qa_logs"
    __table_args__ = (
        Index("ix_qa_logs_org_id_created_at", "org_id", "created_at"),
        Index("ix_qa_logs_org_id_trace_id", "org_id", "trace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 问题的 SHA-256 hex（**不记原文**，M3 §4.3）
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 答案的 SHA-256 hex（**不记原文**）
    answer_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    refusal_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kg_version: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


ONTOLOGY_SCHEMA_STATUS_VALUES = ("active", "superseded")
"""`ontology_schemas.status` 合法值（M6 §4.1）。

**仅 `active` 对外可查**；``superseded`` 是换域（重新冷启动）时旧版本的终态
（M6 §4.6：新版本落 ``version + 1``、旧版本置 ``superseded``）。
"""


class OntologySchema(Base):
    """`ontology_schemas` 表（M6 §4.1：业务域本体，**每 org 一套**）。

    Sprint 9.5 批次 A2 落地。两点纪律（M6 §3.5 验收 12 + GAP-F2）：

    1. ``status = active`` **必须经用户确认后才写入**——未确认前用内置默认 schema
       且不阻断抽取，内置默认 schema **不写入本表**；
    2. 跨 org 的 schema **互不可见**（ADR-0003 RLS），换域走 ``version + 1``，
       历史图谱**不回溯重算**。

    本批次的种子数据（考勤域）由
    ``backend/scripts/seed_attendance_ontology.py`` 写入，
    ``suggested_by_llm = false``（人工直接编辑，非 LLM 建议）。
    """

    __tablename__ = "ontology_schemas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_ontology_schemas_status",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_ontology_schemas_org_id_status", "org_id", "status"),
        Index("ix_ontology_schemas_org_id_created_at", "org_id", "created_at"),
    )

    #: 复合主键第一列 = RLS 隔离键（前缀索引天然覆盖按 org 过滤的查询）
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    #: 版本号（每 org 独立自增）
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: 实体类型集合（数组，每项 ``{name, description?}``）
    entity_types: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    #: 关系类型集合（每项 ``{name, head_types, tail_types, description?}``）
    relation_types: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    #: 业务域描述（人工输入，非 LLM 生成）
    domain_description: Mapped[str] = mapped_column(Text, nullable=False)
    #: true = LLM 建议；false = 人工直接编辑
    suggested_by_llm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    #: 确认人（M5 users.id）——**确认**是本表 status=active 的前置条件
    confirmed_by_user: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, index=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


#: `users.status` 的取值（**唯一定义处**，与下面 `ck_users_status` 的
#: CheckConstraint 同源）。P2-C 起有两个消费者：登录（`services/auth/login.py`）与
#: RBAC 判定（`services/rbac/service.py`）——两处各写一个 `"active"` 字面量，
#: 迟早一边改一边不改。
USER_STATUS_ACTIVE = "active"
USER_STATUS_DISABLED = "disabled"


class User(Base):
    """`users` 表（M5 §4.1：账号主体）—— DR-B13 / G-18。

    字段**逐字**照 `specs/m5-permission-audit.md` §4.1 的 7 列；
    类型按本仓惯例收敛（spec 的 TEXT → ``String(n)``、主键 ``Uuid``），
    与 ADR-0003 §3.1 差异表 **A9**（把 spec 的 ``BIGSERIAL`` 改 Uuid）同源：
    **先例已裁决过的收敛方式，这里沿用，不再重开讨论**。

    ⚠️ 三条纪律，别因为「终于有 users 了」就顺手破：

    1. **本批 0 消费者** —— 没有登录、没有 RBAC、没有 License 读它。
       造一个 CRUD / 端点就是「顺手预留」（CODEBUDDY「预留必须有登记」要拦的形态）；
    2. **`password_hash` 是敏感字段**（M5 §3 验收 3 / §4.5）：**不进**任何日志、
       **不进** `contracts/openapi.yaml`、不出现在任何 Schema 响应体里；
    3. **不动 `LocalAuthProvider` 语义** —— 现有 dev token / dev header 是全部测试
       的身份来源，接线归 P2-C（接缝 1 第二实现）。
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_users_status",
        ),
        # spec §4.1：`username` unique（登录名唯一）
        UniqueConstraint("username", name="uq_users_username"),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_users_org_id_status", "org_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: 登录名（spec §4.1 标 unique）
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 口令哈希（bcrypt / argon2）——**敏感**：严禁落日志 / 进契约
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 租户隔离键（ADR-0003）
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 账号状态（CheckConstraint 限两档）
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    #: **席位口径**（ADR-0006 §2.4 维度 2）—— 席位 = 「已激活且可登录」的用户。
    #: 首次**成功登录**回填（登录属 P2-C）；此刻全表为 NULL ⇒ **当前占席位 0 人**。
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: 停用时间；**可空且未停用**即计入席位（同上：席位谓词是 disabled_at IS NULL）
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: **预留**（P2-C / 子任务 ②）：外部身份源的**签发方**标识。
    #: 本批**不消费**——本地登录按 `username` 查；启用企业身份源（AD / LDAP / OIDC）
    #: 后，查找键由 `username` 改为 `(issuer, subject)`，`LocalAuthProvider` 即
    #: `issuer='local'`。登记见 `docs/adr/0004-integration-seams.md`
    #: （启用条件写在那里；**不进**任何契约，功能预留原则第 4 条）。
    issuer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: **预留**（同上）：外部身份源**内部**的主体标识（OIDC 的 `sub` / LDAP 的 DN）。
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    #: ADR-0006 §2.4：席位判定谓词，**唯一**判据（`LicensePolicy` 直接取用，避免口径漂移）
    __seat_predicate__ = "activated_at IS NOT NULL AND disabled_at IS NULL"


class License(Base):
    """``licenses`` 表（ADR-0006 §3.1）：**实例级**，RLS **显式豁免**。

    **为什么实例级**：这是一台机器一份 License（一 License 管全实例），**没有租户维度**
    ⇒ 与 ``roles`` 同属「无租户维度的系统表」（ADR-0006 §3.1 原文：显式豁免 RLS，
    与 ``roles`` 全局字典表同理）。

    **豁免的三条机械约束**（沿用 2026-10-03 用户对 ``roles`` 的裁决=「代码内显式声明 +
    机械断言 + 事后 CR 抽检」，要求未放松，只变更履行载体）：

    1. 本表**没有** ``org_id``（有即说明被租户业务污染）；
    2. 豁免集合 :data:`RLS_EXEMPT_TABLES` 与本模型的 ``__rls_exempt__`` **双向相等**；
    3. 库里不得出现 ``tenant_isolation`` 策略（由 ``tests/test_guardrails_rls.py`` 查库判）。

    **写的是谁**：每份**成功加载**的 License 落一行，用于回溯「这台机器上装过什么」
    （ADR-0006 §3.1 ``raw_payload`` 的取证目的）。消费者唯一落点：
    ``app/services/license/store.py::record_loaded_license``。
    """

    __tablename__ = "licenses"
    __rls_exempt__ = True
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'superseded')",
            name="ck_licenses_status",
        ),
        UniqueConstraint("license_id", name="uq_licenses_license_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: License 唯一标识（UUID 字符串）
    license_id: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 本机指纹（32 位 hex，ADR-0006 §2.1）
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: 过期宽限天数（ADR-0006 §2.5，默认 30）
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 维度 1：租户数上限
    max_orgs: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 维度 2：席位数上限
    max_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 维度 3：授权模块列表（``m1_ingest`` … ``connectors``，ADR-0006 §3.3）
    modules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    #: License **正文原文**（**不含签名**）——审计 / 争议取证用
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    #: Ed25519 签名（base64）
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    #: 首次生效时间
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Role(Base):
    """`roles` 表（M5 §4.2）：**全局角色字典表**，RLS **显式豁免**。

    **豁免声明（本段就是 ADR-0003 §4.1 要求的"显式声明"，不是注释习惯）**：

    - **豁免对象**：`roles`；
    - **理由**：它是**无租户维度**的**系统预置字典表**——全租户共用同一套角色定义，
      表内**仅**存放 spec §4.2 的 4 种系统预置角色（`admin / auditor / analyst / viewer`），
      **禁止**写入任何租户业务数据。`user_roles`（真正的租户授权表）**不在**豁免集合内，
      它带 `org_id` 并参与隔离；
    - **风险与约束**：豁免意味着本表**不受 RLS 约束**，因此它被三条机械断言盯住
      （见 `specs/m5-permission-audit.md` §4.2 第 2 条）：
      ① 不得出现租户业务列（本表**没有** `org_id`）；
      ② 表内仅允许 4 种预置角色（`ck_roles_name` 在 DB 层钉死）；
      ③ 豁免清单与实际模型一致（见 :data:`RLS_EXEMPT_TABLES` 的注释）。
      ⇒ **新增第 5 个角色名或给本表加 `org_id`，CI 必红。**

    ⚠️ **RLS 策略本身归 P3（DR-B4）**：本批只做豁免**登记**，不建策略。
    """

    __tablename__ = "roles"
    #: 参与 :data:`RLS_EXEMPT_TABLES` 的双向核对（G-24 断言 ③）
    __rls_exempt__ = True
    __table_args__ = (
        CheckConstraint(
            "name IN ('admin', 'auditor', 'analyst', 'viewer')",
            name="ck_roles_name",
        ),
        UniqueConstraint("name", name="uq_roles_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: 角色名（CheckConstraint 限 :data:`ROLE_NAME_VALUES` 四档；唯一）
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 角色说明（可空：预置角色的说明由 `app/services/rbac/roles.py::PRESET_ROLES` 提供）
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserRole(Base):
    """`user_roles` 表（M5 §4.3）：**租户内**的授权记录，三粒度的载体。

    三粒度 = **角色**（`role_id`）+ **文档**（`doc_scope`）+ **场景**（`scene_scope`）：

    - `doc_scope`：``{"doc_ids": [...], "tags": [...]}``（JSON，可空 = 不限）；
    - `scene_scope`：``["affiliation", "qa"]``（JSON 数组，可空 = 不限）。

    **本表带 `org_id` 且索引以 `org_id` 打头**（ADR-0003 §3.1 第 1 条），
    与 `roles` 相反——它是租户数据，**不**在 :data:`RLS_EXEMPT_TABLES` 里。

    两点类型收敛（与 ADR-0003 §3.1 差异表 **A9** 同源：先例已裁决的收敛方式沿用，
    不重开讨论，差异登记在 `changes/P2/integration-log.md`）：

    1. spec 写 **JSONB**，本仓既有 JSON 列（`kg_versions.source_doc_ids` 等）一律用
       SQLAlchemy ``JSON``（映射 PG ``json``）——保持方言中立，为 ADR-0003 §3.7 的
       **信创降级**留退路（非 PG 内核未必有 JSONB）；
    2. 主键取 ``Uuid``（全仓一致），不取 spec 未明写的整型。
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_user_roles_org_id_user_id", "org_id", "user_id"),
        Index("ix_user_roles_org_id_role_id", "org_id", "role_id"),
        # 同一租户内「同一用户 + 同一角色」只授权一次（重复授权无意义）
        UniqueConstraint(
            "org_id", "user_id", "role_id", name="uq_user_roles_org_user_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: 租户隔离键（ADR-0003）
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 被授权的主体（`users.id`；**不建外键**——与 `documents.uploaded_by` 同口径，
    #: 见 P2-A 遗留 2）
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    #: 角色（`roles.id`）
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    #: **文档级**粒度：``{"doc_ids": [...], "tags": [...]}``；``None`` = 不限
    doc_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: **场景级**粒度：``["affiliation", "qa", ...]``；``None`` = 不限
    scene_scope: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    #: 授权人（spec §4.3 标必填；系统预置时取 `DEFAULT_ACTOR_ID`）
    granted_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class OntologyAction(Base):
    """`ontology_actions` 表（M6 §4.2：本体动作的**审计**载体）。

    P5-C（M6 第一批）落地。与 `ontology_schemas` 的分工：后者存**生效中的本体**，
    本表存**谁在什么时候做了什么**——「未确认不生效」要可举证，靠的就是本表有一行。

    两处偏离登记（详见 :data:`ONTOLOGY_ACTION_TYPES` 与
    :data:`ONTOLOGY_ACTION_WITHOUT_KG_VERSION`）：

    1. **X-2a**：``action_type`` 在 spec 的三值外多一个 ``confirm``（批次 A 的确认动作）；
    2. **X-2b**：``kg_version`` 允许 NULL，但**只有** ``confirm`` 行可以为 NULL
       （其余三动作的 CHECK 要求非空，保持 spec §4.2 的语义）。

    **本批唯一的写入方是** ``confirm``（``app.services.ontology.confirm_ontology_schema``）；
    ``merge`` / ``split`` / ``rename`` 归后续批次（增量重算落地之后）。
    """

    __tablename__ = "ontology_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('merge', 'split', 'rename', 'confirm')",
            name="ck_ontology_actions_action_type",
        ),
        # X-2b：把 deviation 限制在 confirm 这一档，
        # 将来接 merge/split/rename 时漏填 kg_version 会被库当场拒绝。
        CheckConstraint(
            "action_type = 'confirm' OR kg_version IS NOT NULL",
            name="ck_ontology_actions_kg_version_required_except_confirm",
        ),
        # ADR-0003 §3.1：复合索引必须 org_id 打头
        Index("ix_ontology_actions_org_id_action_type", "org_id", "action_type"),
        Index("ix_ontology_actions_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: 租户隔离键（ADR-0003）
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 动作类型（见 :data:`ONTOLOGY_ACTION_TYPES`）
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 涉及对象：``merge`` / ``split`` / ``rename`` 是**实体 id 列表**；
    #: ``confirm`` 是**本体类型名列表** ——
    #: ``{"entity_type_names": [...], "relation_type_names": [...]}``。
    #: shape 随动作而变是 JSON 列的本分，故键名自解释，**不**对不同动作硬套同一形状。
    target_entities: Mapped[dict] = mapped_column(JSON, nullable=False)
    #: 操作人（`users.id`；**不建外键**——与 `documents.uploaded_by` 同口径）
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    #: 操作时的图谱版本（`confirm` 行恒 NULL，见
    #: :data:`ONTOLOGY_ACTION_WITHOUT_KG_VERSION`）
    kg_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 增量重算产出的新版本；NULL = 未完成或失败（spec §4.2 同口径）
    result_kg_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    #: 失败错误码（沿用 ADR-0002）
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 失败明细（**敏感**：日志禁输出原文）
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
