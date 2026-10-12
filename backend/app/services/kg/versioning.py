"""`kg_versions` 表的 CRUD 与真源状态机（ADR-0002 §3.2，Sprint 5 批次 B）。

公开面：
- :class:`KgVersioningService`：封装表的状态机迁移（pending → building → ready /
  → failed），调用方只需走流程，无需关心实现细节；
- :meth:`KgVersioningService.get_active`：取同 org **最新** ready 版本（fail-closed 兜底）。
  （P6-X2 更正：是「最新」不是「唯一」——同 org 允许多个 ready 共存，见该方法
  docstring 与 **F-P6X-6**。）

**真源约定**：本表是 ``kg_version`` 状态机的**唯一**真源；Neo4j
``:KgVersionMirror`` 仅为冗余镜像（stage-1 写入），路由层 ``fetch_active_kg_version``
后续批次会先查本表、Neo4j 查询降级为兜底（ADR-0002 §3.2）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KgVersion


@dataclass(frozen=True, slots=True)
class KgVersionRecord:
    """KgVersion 的对外投影（隔离 SQLAlchemy 会话生命周期）。"""

    id: uuid.UUID
    org_id: uuid.UUID
    version: str
    status: str
    source_doc_ids: list[uuid.UUID]
    entity_count: int
    relation_count: int
    error_code: str | None
    error_detail: str | None
    ready_at: datetime | None
    trace_id: uuid.UUID


class KgVersionNotFoundError(Exception):
    """``kg_versions`` 中不存在该 (org_id, version)（路由层 → 404）。"""


class KgVersionNotActivatableError(Exception):
    """该版本不可被激活（当前为 ``failed`` / ``pending``；路由层 → 409）。

    **严禁静默降级**：failed 版本的图数据不完整（ADR-0002 §3.2 三段式已补偿清理），
    把它置为可消费等于把事故伪装成正常结论（plan §4.4 纪律）。
    """

    def __init__(self, *, version: str, status: str) -> None:
        super().__init__(f"kg_version={version} 当前 status={status}，不可激活")
        self.version = version
        self.status = status


def _to_record(row: KgVersion) -> KgVersionRecord:
    return KgVersionRecord(
        id=row.id,
        org_id=row.org_id,
        version=row.version,
        status=row.status,
        source_doc_ids=[
            uuid.UUID(value) if isinstance(value, str) else value
            for value in (row.source_doc_ids or [])
        ],
        entity_count=row.entity_count,
        relation_count=row.relation_count,
        error_code=row.error_code,
        error_detail=row.error_detail,
        ready_at=row.ready_at,
        trace_id=row.trace_id,
    )


class KgVersioningService:
    """``kg_versions`` 表的状态机迁移服务（PG 真源）。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    # -------------------------------------------------------------- 创建

    def create_pending(
        self,
        *,
        org_id: uuid.UUID,
        version: str,
        source_doc_ids: list[uuid.UUID],
        trace_id: uuid.UUID,
    ) -> KgVersionRecord:
        """以 ``pending`` 状态写入新版本行。"""
        row = KgVersion(
            org_id=org_id,
            version=version,
            status="pending",
            # JSON 列不能直接存 UUID（json.dumps 不支持）——统一转字符串
            source_doc_ids=[str(doc_id) for doc_id in source_doc_ids],
            entity_count=0,
            relation_count=0,
            trace_id=trace_id,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        logger.bind(
            trace_id=str(trace_id),
            org_id=str(org_id),
            version=version,
            kg_version_id=str(row.id),
        ).info("kg_version_pending")
        return _to_record(row)

    # -------------------------------------------------------------- 状态迁移

    def mark_building(self, version_id: uuid.UUID) -> KgVersionRecord:
        row = self._require(version_id)
        row.status = "building"
        self._db.commit()
        self._db.refresh(row)
        logger.bind(kg_version_id=str(version_id), version=row.version).info(
            "kg_version_building"
        )
        return _to_record(row)

    def mark_ready(
        self,
        version_id: uuid.UUID,
        *,
        entity_count: int,
        relation_count: int,
    ) -> KgVersionRecord:
        row = self._require(version_id)
        row.status = "ready"
        row.entity_count = entity_count
        row.relation_count = relation_count
        row.ready_at = datetime.now(UTC)
        row.error_code = None
        row.error_detail = None
        self._db.commit()
        self._db.refresh(row)
        logger.bind(
            kg_version_id=str(version_id),
            version=row.version,
            entity_count=entity_count,
            relation_count=relation_count,
        ).info("kg_version_ready")
        return _to_record(row)

    def mark_failed(
        self,
        version_id: uuid.UUID,
        *,
        error_code: str,
        error_detail: str,
    ) -> KgVersionRecord:
        row = self._require(version_id)
        row.status = "failed"
        row.error_code = error_code
        row.error_detail = error_detail
        self._db.commit()
        self._db.refresh(row)
        logger.bind(
            kg_version_id=str(version_id),
            version=row.version,
            error_code=error_code,
        ).warning("kg_version_failed")
        return _to_record(row)

    # -------------------------------------------------------------- 激活

    def activate_by_version(
        self, *, org_id: uuid.UUID, version: str
    ) -> KgVersionRecord:
        """把指定版本置为**可消费**——PG 真源的 active 语义在本表中写作 ``ready``。

        幂等：已是 ``ready`` 时只回读不写。``pending`` / ``building`` / ``failed``
        一律拒绝（:class:`KgVersionNotActivatableError`）：前两者图尚未写完，
        后者已被三段式补偿清理——把它们置为可消费等于把事故伪装成正常结论
        （plan §4.4 纪律）。不存在 → :class:`KgVersionNotFoundError`。
        """
        stmt = select(KgVersion).where(
            KgVersion.org_id == org_id, KgVersion.version == version
        )
        row = self._db.execute(stmt).scalar_one_or_none()
        if row is None:
            raise KgVersionNotFoundError(
                f"kg_version 不存在: org_id={org_id} version={version}"
            )
        if row.status != "ready":
            raise KgVersionNotActivatableError(version=version, status=row.status)

        logger.bind(
            version=version, org_id=str(org_id), kg_version_id=str(row.id)
        ).info("kg_version_activated")
        return _to_record(row)

    # -------------------------------------------------------------- 查询

    def get_active(self, *, org_id: uuid.UUID) -> KgVersionRecord | None:
        """取同 org **最新** ready 版本（PG 真源，ADR-0002 §3.2）。

        **P6-X2（F-P6X-6）**：排序键是 ``ready_at DESC, created_at DESC, id DESC``
        ——``ready_at`` 单独用**不够**：两次 ``mark_ready`` 落在**同一微秒**时它会并列，
        「active 是哪个版本」就成了掷骰子（真图口径全量实测复现：
        ``test_get_active_returns_latest_ready_for_same_org`` 断言 ``'v-old' == 'v-new'``）。
        §6.2 的一致性判定要靠 active 唯一定位，不能靠运气 ⇒ 补次级键。

        - ``created_at``：行创建（``pending`` 落库）时刻，晚建的版本更新；
          且 ``ix_kg_versions_org_id_created_at`` 已存在 ⇒ **不新增索引**；
        - ``id``：最后是确定性兜底（并列时结果至少**稳定**，不会每次跑不一样）。

        ⚠️ 语义是「**最新** ready」，**不是**「唯一 ready」—— 同 org 允许多个 ready
        共存（本机实测 5 行全 ready）。旧 docstring 写「唯一」会被读成"唯一性约束"，
        从而把现状误判成异常。
        """
        stmt = (
            select(KgVersion)
            .where(KgVersion.org_id == org_id, KgVersion.status == "ready")
            .order_by(
                KgVersion.ready_at.desc(),
                KgVersion.created_at.desc(),
                KgVersion.id.desc(),
            )
            .limit(1)
        )
        row = self._db.execute(stmt).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    def get_by_version(
        self, *, org_id: uuid.UUID, version: str
    ) -> KgVersionRecord | None:
        """按 (org_id, version) 唯一定位（stage-1 幂等键）。"""
        stmt = select(KgVersion).where(
            KgVersion.org_id == org_id, KgVersion.version == version
        )
        row = self._db.execute(stmt).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    # -------------------------------------------------------------- 内部

    def _require(self, version_id: uuid.UUID) -> KgVersion:
        row = self._db.get(KgVersion, version_id)
        if row is None:
            raise LookupError(f"kg_version 不存在: id={version_id}")
        return row


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "KgVersionNotActivatableError",
    "KgVersionNotFoundError",
    "KgVersionRecord",
    "KgVersioningService",
]
