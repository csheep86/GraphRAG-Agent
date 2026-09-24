"""Sprint 7.4 批次 D：事件出口（接缝 5）单测。

覆盖（对应 `changes/Sprint7.4/tasks.md` §4）：

1. ``risk.suspect_created`` 确实落 ``domain_events``（event_type / aggregate_type /
   payload 均可断言），``aggregate_id`` 指向**真实疑点 id**（不是空串、不是编的）；
2. ``dispatched_at`` **恒为 NULL**——只落不派（plan §6.2 批次 D）；
3. 一次 ``emit`` 同时走 **db + log 两个 sink**；
4. 业务回滚时事件**不残留**（db sink 不自己 commit，与业务同 session）；
5. ``org_id`` / ``trace_id`` 取自任务上下文，**不是**事件里新造的。

用例一律用**独立 org_id** 落库并只查自己，避免污染其他用例（测试库是共享 SQLite）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AffiliationSuspicion, AffiliationTask, DomainEvent
from app.db.session import SessionLocal, init_db
from app.services.affiliation import persist_detection_result
from app.services.events import DomainEvent as DomainEventPayload
from app.services.events import build_event_bus
from app.services.events.log import LogEventSink
from app.services.events.types import RISK_SUSPECT_CREATED


@pytest.fixture
def session() -> Iterator[Session]:
    init_db()  # 幂等：测试库是 SQLite，建表靠 create_all
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fake_suspicion(suspicion_type: str, suffix: str) -> Any:
    """duck-typed 疑点：``persist_detection_result`` 只吃 ``to_dict()``。"""

    class _Suspicion:
        def to_dict(self) -> dict[str, Any]:
            return {
                "type": suspicion_type,
                "severity": "medium",
                "entities": [f"sub-a{suffix}", f"sub-b{suffix}", f"shared-{suffix}"],
                "entity_names": [
                    f"公司A{suffix}",
                    f"公司B{suffix}",
                    f"共享节点{suffix}",
                ],
                "evidence": [
                    {"node_id": f"shared-{suffix}", "chunk_id": f"chunk-{suffix}"}
                ],
            }

    return _Suspicion()


def _new_task(session: Session, org_id: uuid.UUID) -> AffiliationTask:
    task = AffiliationTask(
        org_id=org_id,
        doc_ids=[str(uuid.uuid4())],
        status="processing",
        trace_id=uuid.uuid4(),
    )
    session.add(task)
    session.commit()
    return task


def _count_events(session: Session, org_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.org_id == org_id)
        )
        or 0
    )


def test_suspect_created_events_persisted(session: Session) -> None:
    """每条疑点一条 ``risk.suspect_created``，落库字段可逐一断言。"""
    org_id = uuid.uuid4()
    task = _new_task(session, org_id)

    count = persist_detection_result(
        session=session,
        task=task,
        suspicions=[
            _fake_suspicion("shared_legal_rep", "1"),
            _fake_suspicion("shared_address", "2"),
        ],
        kg_version="v-test",
        trace_id=task.trace_id,
    )
    assert count == 2

    rows = session.scalars(
        select(DomainEvent).where(DomainEvent.org_id == org_id)
    ).all()
    assert len(rows) == 2

    for row in rows:
        assert row.event_type == RISK_SUSPECT_CREATED
        assert row.aggregate_type == "affiliation_suspicion"
        assert row.dispatched_at is None  # 只落不派
        assert row.payload["task_id"] == str(task.id)
        assert row.payload["kg_version"] == "v-test"
        assert row.payload["evidence_count"] == 1
        # 上下文来源：不新造
        assert row.org_id == org_id
        assert row.trace_id == task.trace_id

    # aggregate_id 必须指向真实疑点（flush 后才有 id，否则这里是空串）
    suspicion_ids = {
        str(item.id)
        for item in session.scalars(
            select(AffiliationSuspicion).where(AffiliationSuspicion.org_id == org_id)
        )
    }
    assert {row.aggregate_id for row in rows} == suspicion_ids


def test_bus_fans_out_to_db_and_log(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一次 emit 同时走 db（落库）与 log（打日志）两个 sink。"""
    seen: list[DomainEventPayload] = []
    monkeypatch.setattr(LogEventSink, "emit", lambda self, event: seen.append(event))

    org_id = uuid.uuid4()
    build_event_bus(session).emit(
        DomainEventPayload(
            event_type=RISK_SUSPECT_CREATED,
            aggregate_type="affiliation_suspicion",
            aggregate_id=str(uuid.uuid4()),
            org_id=org_id,
            trace_id=uuid.uuid4(),
            payload={"probe": True},
        )
    )
    session.commit()

    assert len(seen) == 1  # log sink 收到
    assert _count_events(session, org_id) == 1  # db sink 落库


def test_event_not_persisted_when_business_rolls_back(session: Session) -> None:
    """db sink 不自己 commit：业务回滚时事件一并消失。"""
    org_id = uuid.uuid4()
    build_event_bus(session).emit(
        DomainEventPayload(
            event_type=RISK_SUSPECT_CREATED,
            aggregate_type="affiliation_suspicion",
            aggregate_id=str(uuid.uuid4()),
            org_id=org_id,
            trace_id=uuid.uuid4(),
        )
    )
    session.rollback()  # 模拟业务失败

    assert _count_events(session, org_id) == 0


def test_no_event_when_no_suspicion(session: Session) -> None:
    """没有疑点就不发事件——不发空事件凑数。"""
    org_id = uuid.uuid4()
    task = _new_task(session, org_id)

    assert (
        persist_detection_result(
            session=session,
            task=task,
            suspicions=[],
            kg_version="v-test",
            trace_id=task.trace_id,
        )
        == 0
    )
    assert _count_events(session, org_id) == 0
