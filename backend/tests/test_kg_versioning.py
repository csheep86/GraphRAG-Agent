"""KgVersioningService + kg_versions ORM 约束测试（ADR-0002 §3.2，批次 B）。

覆盖：
1. 状态机 ``pending → building → ready`` / ``→ failed`` 全迁移；
2. ``mark_ready`` 回填 entity/relation_count + ready_at + 清空 error_*；
3. ``get_active`` 只取同 org 的 ready 版本（最新优先）；
4. ``get_by_version`` 按 (org_id, version) 定位；
5. 不存在的 version_id → ``LookupError``；
6. ORM：CheckConstraint 拦截非法 status；source_doc_ids JSON 落库为字符串数组、
   出库回转 UUID（json.dumps 不支持 UUID 原生类型）；
7. ``KG_VERSION_STATUS_VALUES`` 常量与模型注释一致。

直接落 sqlite 共享测试库（conftest 已隔离到临时目录），用例自清理。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models import KG_VERSION_STATUS_VALUES, KgVersion
from app.db.session import SessionLocal, init_db
from app.services.kg import KgVersioningService

ORG_A = uuid4()
ORG_B = uuid4()


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    init_db()


@pytest.fixture
def created_ids() -> list:
    ids: list = []
    yield ids
    if ids:
        with SessionLocal() as session:
            session.execute(delete(KgVersion).where(KgVersion.id.in_(ids)))
            session.commit()


def _seed_row(**overrides: object) -> KgVersion:
    kwargs: dict[str, object] = {
        "org_id": ORG_A,
        "version": f"v-{uuid4().hex[:8]}",
        "status": "pending",
        "source_doc_ids": [str(uuid4())],
        "trace_id": uuid4(),
    }
    kwargs.update(overrides)
    row = KgVersion(**kwargs)  # type: ignore[arg-type]
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# 状态机
# --------------------------------------------------------------------------- #


def test_state_machine_pending_to_ready(created_ids: list) -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        record = service.create_pending(
            org_id=ORG_A, version="v-ready", source_doc_ids=[uuid4()], trace_id=uuid4()
        )
        created_ids.append(record.id)

        assert record.status == "pending"
        assert record.entity_count == 0
        assert record.relation_count == 0
        assert record.ready_at is None

        building = service.mark_building(record.id)
        assert building.status == "building"

        ready = service.mark_ready(record.id, entity_count=42, relation_count=7)
        assert ready.status == "ready"
        assert ready.entity_count == 42
        assert ready.relation_count == 7
        assert ready.ready_at is not None


def test_state_machine_mark_failed(created_ids: list) -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        record = service.create_pending(
            org_id=ORG_A, version="v-failed", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.append(record.id)
        service.mark_building(record.id)

        failed = service.mark_failed(
            record.id, error_code="INTERNAL_ERROR", error_detail="boom"
        )
        assert failed.status == "failed"
        assert failed.error_code == "INTERNAL_ERROR"
        assert failed.error_detail == "boom"


def test_mark_ready_clears_stale_errors(created_ids: list) -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        record = service.create_pending(
            org_id=ORG_A, version="v-recover", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.append(record.id)
        service.mark_failed(record.id, error_code="X", error_detail="y")

        recovered = service.mark_ready(record.id, entity_count=1, relation_count=1)
        assert recovered.status == "ready"
        assert recovered.error_code is None
        assert recovered.error_detail is None


def test_missing_version_raises_lookup_error() -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        with pytest.raises(LookupError, match="kg_version 不存在"):
            service.mark_building(uuid4())


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #


def test_get_active_returns_latest_ready_for_same_org(created_ids: list) -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        older = service.create_pending(
            org_id=ORG_A, version="v-old", source_doc_ids=[], trace_id=uuid4()
        )
        newer = service.create_pending(
            org_id=ORG_A, version="v-new", source_doc_ids=[], trace_id=uuid4()
        )
        other_org = service.create_pending(
            org_id=ORG_B, version="v-other", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.extend([older.id, newer.id, other_org.id])

        service.mark_ready(older.id, entity_count=1, relation_count=1)
        service.mark_ready(newer.id, entity_count=2, relation_count=2)
        service.mark_ready(other_org.id, entity_count=3, relation_count=3)

        active = service.get_active(org_id=ORG_A)
        assert active is not None
        assert active.version == "v-new", "同 org 多个 ready 时取最新"

        assert service.get_by_version(org_id=ORG_A, version="v-old") is not None
        assert service.get_by_version(org_id=ORG_B, version="v-old") is None


def test_get_active_none_when_only_pending_or_failed(created_ids: list) -> None:
    with SessionLocal() as session:
        service = KgVersioningService(session)
        pending = service.create_pending(
            org_id=ORG_A, version="v-pending", source_doc_ids=[], trace_id=uuid4()
        )
        failed = service.create_pending(
            org_id=ORG_A, version="v-failed-2", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.extend([pending.id, failed.id])
        service.mark_failed(failed.id, error_code="X", error_detail="y")

        assert service.get_active(org_id=ORG_A) is None


# --------------------------------------------------------------------------- #
# ORM 约束 / JSON 序列化
# --------------------------------------------------------------------------- #


def test_source_doc_ids_roundtrip_str_to_uuid(created_ids: list) -> None:
    doc_ids = [uuid4(), uuid4()]
    with SessionLocal() as session:
        service = KgVersioningService(session)
        record = service.create_pending(
            org_id=ORG_A,
            version="v-json",
            source_doc_ids=doc_ids,
            trace_id=uuid4(),
        )
        created_ids.append(record.id)

        assert record.source_doc_ids == doc_ids, "出库必须回转为 UUID"

        raw = session.get(KgVersion, record.id)
        assert raw is not None
        assert all(isinstance(value, str) for value in raw.source_doc_ids)


def test_check_constraint_rejects_invalid_status() -> None:
    with pytest.raises(IntegrityError):
        with SessionLocal() as session:
            session.add(
                KgVersion(
                    org_id=ORG_A,
                    version="v-bogus",
                    status="writing",  # 未登记状态（ADR-0002 §3.2 合法值外）
                    source_doc_ids=[],
                    trace_id=uuid4(),
                )
            )
            session.commit()


def test_status_values_constant_matches_adr() -> None:
    assert KG_VERSION_STATUS_VALUES == ("pending", "building", "ready", "failed")
