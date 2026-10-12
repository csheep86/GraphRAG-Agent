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

直接落会话级共享的 PostgreSQL 测试库（conftest 固定为 ``graphrag_test``，
不再每次换临时目录），用例自清理。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.db.models import KG_VERSION_STATUS_VALUES, KgVersion
from app.db.session import init_db, session_scope
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
        # A10：清理**逐租户**——一次会话只看见一个 org 的行
        for org_id in (ORG_A, ORG_B):
            with session_scope(org_id=org_id) as session:
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
    # A10：绑的 org 就是这行的 org（覆盖传 org_id=ORG_B 的情形）
    with session_scope(org_id=row.org_id) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# 状态机
# --------------------------------------------------------------------------- #


def test_state_machine_pending_to_ready(created_ids: list) -> None:
    with session_scope(org_id=ORG_A) as session:
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
    with session_scope(org_id=ORG_A) as session:
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
    with session_scope(org_id=ORG_A) as session:
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
    with session_scope(org_id=ORG_A) as session:
        service = KgVersioningService(session)
        with pytest.raises(LookupError, match="kg_version 不存在"):
            service.mark_building(uuid4())


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #


def test_get_active_returns_latest_ready_for_same_org(
    created_ids: list, real_pg_get_active: None
) -> None:
    """PG 真源：同 org 下取 `ready_at` 最新的 ready 版本。

    ``real_pg_get_active`` 用于撤销 conftest 的默认桩（本文件验的正是真源本身）。
    """
    # A10：ORG_B 的行必须在 ORG_B 的租户视野里创建 / 推进（跨租户写会被
    # WITH CHECK 拒掉，且本会话也看不见别的 org）
    with session_scope(org_id=ORG_B) as session:
        other = KgVersioningService(session)
        other_org = other.create_pending(
            org_id=ORG_B, version="v-other", source_doc_ids=[], trace_id=uuid4()
        )
        other.mark_ready(other_org.id, entity_count=3, relation_count=3)

    with session_scope(org_id=ORG_A) as session:
        service = KgVersioningService(session)
        older = service.create_pending(
            org_id=ORG_A, version="v-old", source_doc_ids=[], trace_id=uuid4()
        )
        newer = service.create_pending(
            org_id=ORG_A, version="v-new", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.extend([older.id, newer.id, other_org.id])

        service.mark_ready(older.id, entity_count=1, relation_count=1)
        service.mark_ready(newer.id, entity_count=2, relation_count=2)

        active = service.get_active(org_id=ORG_A)
        assert active is not None
        assert active.version == "v-new", "同 org 多个 ready 时取最新"

        assert service.get_by_version(org_id=ORG_A, version="v-old") is not None
        assert service.get_by_version(org_id=ORG_B, version="v-old") is None


def test_get_active_is_stable_when_ready_at_ties(
    created_ids: list, real_pg_get_active: None
) -> None:
    """**F-P6X-6**：``ready_at`` **并列**时也必须取到**后创建**的那个。

    真图全量实测复现过：两次 ``mark_ready`` 落在同一微秒 ⇒ ``ORDER BY ready_at DESC``
    两条并列 ⇒ 返回哪个全看运气（那条用例当时断言 ``'v-old' == 'v-new'`` 失败）。
    §6.2 的一致性判定要靠 active **唯一定位**，不能靠运气 ⇒ 排序必须有次级键。

    本条把两行的 ``ready_at`` **强行拉平**，模拟那个"同一微秒"，再断言结果稳定。
    """
    tied_at = datetime.now(UTC)
    with session_scope(org_id=ORG_A) as session:
        service = KgVersioningService(session)
        older = service.create_pending(
            org_id=ORG_A, version="v-tie-old", source_doc_ids=[], trace_id=uuid4()
        )
        newer = service.create_pending(
            org_id=ORG_A, version="v-tie-new", source_doc_ids=[], trace_id=uuid4()
        )
        created_ids.extend([older.id, newer.id])

        service.mark_ready(older.id, entity_count=1, relation_count=1)
        service.mark_ready(newer.id, entity_count=2, relation_count=2)

        # 拉平 ready_at（两条一模一样 ⇒ 只剩次级键能决定顺序）。
        # ⚠️ created_at **也必须显式拉开**：本机实测两次 create_pending 同样可能落在
        # 同一微秒（真图全量下本条就是这么红的）⇒ 不控制这个变量，本条会变成掷骰子。
        session.execute(
            update(KgVersion)
            .where(KgVersion.id == older.id)
            .values(ready_at=tied_at, created_at=tied_at - timedelta(seconds=1))
        )
        session.execute(
            update(KgVersion)
            .where(KgVersion.id == newer.id)
            .values(ready_at=tied_at, created_at=tied_at)
        )
        session.commit()

        active = service.get_active(org_id=ORG_A)

    assert active is not None
    assert active.version == "v-tie-new", (
        "ready_at 并列时必须按 created_at 取**后创建**的；"
        "若这条红了，说明次级排序键被删了（§6.2 的 active 定位会变成掷骰子）"
    )


def test_get_active_none_when_only_pending_or_failed(
    created_ids: list, real_pg_get_active: None
) -> None:
    """只有 pending / failed 时 `get_active` 返回 `None`（不静默挑一个）。"""
    with session_scope(org_id=ORG_A) as session:
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
    with session_scope(org_id=ORG_A) as session:
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
        with session_scope(org_id=ORG_A) as session:
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
