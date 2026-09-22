"""kg.build 执行体单元测试（Sprint 5 批次 B：ADR-0002 §3.1/§3.2）。

覆盖 :mod:`app.tasks.registry.kg_build_executor`：

1. 全新构建：自动创建 ``kg_versions`` pending 行 → building → ready；
2. ``documents.kg_version_id`` 回填 + ``kg_build_status`` completed +
   **整体** ``status`` completed（管线末段收口）；
3. 失败：阶段级 + 整体 failed + ``kg_versions`` 行同步 failed；
4. 重试计数回写 ``kg_build_retry_count``；
5. ThreeStageKgBuilder 以假类整体替换（Neo4j 零依赖）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import Document, KgVersion
from app.db.session import SessionLocal, init_db
from app.services.graphs import GraphUnavailableError
from app.storage import build_extract_artifact_key, get_storage
from app.tasks.registry import kg_build_executor
from app.tasks.types import TaskSpec

_ENTITIES = [
    {
        "id": "ent_001",
        "canonical_name": "北京青云科技有限公司",
        "entity_type": "ORG",
        "mention": "北京青云科技有限公司",
        "char_start": 2,
        "char_end": 12,
        "confidence": 0.99,
    }
]
_RELATIONS = [
    {
        "id": "rel_001",
        "source_entity_id": "ent_001",
        "target_entity_id": "ent_001",
        "relation_type": "PARTY_TO",
        "evidence": "甲方",
        "confidence": 0.95,
    }
]


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    init_db()


@pytest.fixture
def zero_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "task_retry_initial_seconds", 0.0)


def _insert_document(status: str) -> UUID:
    settings = get_settings()
    document_id = uuid4()
    with SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(b"contract.pdf").hexdigest(),
                mime_type="application/pdf",
                size_bytes=1024,
                status=status,
                uploaded_by=settings.default_actor_id,
                org_id=settings.default_org_id,
                trace_id=uuid4(),
            )
        )
        session.commit()
    return document_id


def _place_extract_artifacts(document_id: UUID) -> None:
    settings = get_settings()
    storage = get_storage()
    storage.put(
        build_extract_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="entities.json"
        ),
        json.dumps(_ENTITIES, ensure_ascii=False).encode("utf-8"),
    )
    storage.put(
        build_extract_artifact_key(
            org_id=settings.default_org_id,
            doc_id=document_id,
            filename="relations.json",
        ),
        json.dumps(_RELATIONS, ensure_ascii=False).encode("utf-8"),
    )


def _make_spec(document_id: UUID) -> TaskSpec:
    return TaskSpec(
        task_type="kg.build",
        payload={"document_id": str(document_id)},
        trace_id=str(uuid4()),
    )


def _snapshot(document_id: UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        return {
            "status": document.status,
            "kg_build_status": document.kg_build_status,
            "kg_build_retry_count": document.kg_build_retry_count,
            "kg_version_id": document.kg_version_id,
            "error_code": document.error_code,
            "error_detail": document.error_detail,
        }


def _kg_version_snapshot(kg_version_id: UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(KgVersion, kg_version_id)
        assert row is not None
        return {
            "status": row.status,
            "entity_count": row.entity_count,
            "relation_count": row.relation_count,
            "error_code": row.error_code,
        }


@pytest.fixture
def seed_document() -> Iterator[Callable[..., UUID]]:
    doc_ids: list[UUID] = []

    def _seed(status: str) -> UUID:
        document_id = _insert_document(status)
        doc_ids.append(document_id)
        return document_id

    yield _seed

    if doc_ids:
        with SessionLocal() as session:
            # 本模块是测试库中 kg_versions 的唯一写入方（default_org_id），
            # 按 org 整体清理，避免 JSON contains 的方言差异
            session.execute(
                delete(KgVersion).where(
                    KgVersion.org_id == get_settings().default_org_id
                )
            )
            session.execute(delete(Document).where(Document.id.in_(doc_ids)))
            session.commit()


class _FakeBuilder:
    """记录 build() 入参的假 ThreeStageKgBuilder。"""

    instances: list[_FakeBuilder] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.requests: list[Any] = []
        _FakeBuilder.instances.append(self)

    def build(self, request: Any) -> Any:
        from app.services.kg.builder import BuildStats

        self.requests.append(request)
        return BuildStats(
            entity_count=len(request.entities),
            relation_count=len(request.relations),
            batch_count=1,
        )


@pytest.fixture
def fake_builder(monkeypatch: pytest.MonkeyPatch) -> type[_FakeBuilder]:
    _FakeBuilder.instances = []
    monkeypatch.setattr("app.tasks.registry.ThreeStageKgBuilder", _FakeBuilder)
    return _FakeBuilder


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_kg_build_happy_path(
    seed_document: Callable[..., UUID],
    fake_builder: type[_FakeBuilder],
) -> None:
    """全新构建：kg_versions pending → building → ready；文档三字段收口。"""
    settings = get_settings()
    document_id = seed_document("processing")
    _place_extract_artifacts(document_id)

    asyncio.run(kg_build_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["kg_build_status"] == "completed"
    assert snapshot["error_code"] is None
    assert snapshot["kg_version_id"] is not None

    kg = _kg_version_snapshot(snapshot["kg_version_id"])
    assert kg["status"] == "ready"
    assert kg["entity_count"] == len(_ENTITIES)
    assert kg["relation_count"] == len(_RELATIONS)
    assert kg["error_code"] is None

    # builder 收到正确的租户与产物
    builder = fake_builder.instances[-1]
    request = builder.requests[0]
    assert str(request.org_id) == str(settings.default_org_id)
    assert request.entities == _ENTITIES
    assert request.relations == _RELATIONS


def test_kg_build_reuses_existing_kg_version_row(
    seed_document: Callable[..., UUID],
    fake_builder: type[_FakeBuilder],
) -> None:
    """payload 指定 kg_version_id 时复用既有行（重试路径不重复建版本）。"""
    document_id = seed_document("processing")
    _place_extract_artifacts(document_id)
    trace_id = uuid4()
    with SessionLocal() as session:
        row = KgVersion(
            org_id=get_settings().default_org_id,
            version="v-retry",
            status="pending",
            source_doc_ids=[str(document_id)],
            trace_id=trace_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        existing_id = row.id

    spec = TaskSpec(
        task_type="kg.build",
        payload={"document_id": str(document_id), "kg_version_id": str(existing_id)},
        trace_id=str(trace_id),
    )
    asyncio.run(kg_build_executor(spec))

    snapshot = _snapshot(document_id)
    assert snapshot["kg_version_id"] == existing_id
    assert _kg_version_snapshot(existing_id)["status"] == "ready"
    # 只建了一个版本行（复用，不新建）
    with SessionLocal() as session:
        rows = session.execute(
            select(KgVersion.id).where(
                KgVersion.org_id == get_settings().default_org_id
            )
        ).all()
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# 失败路径
# --------------------------------------------------------------------------- #


def test_kg_build_failure_marks_document_and_version_failed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    document_id = seed_document("processing")
    _place_extract_artifacts(document_id)

    class _BoomBuilder:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def build(self, request: Any) -> Any:
            raise GraphUnavailableError("neo4j connection refused")

    monkeypatch.setattr("app.tasks.registry.ThreeStageKgBuilder", _BoomBuilder)

    asyncio.run(kg_build_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"
    assert snapshot["kg_build_status"] == "failed"
    assert snapshot["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert snapshot["error_detail"]

    assert snapshot["kg_version_id"] is not None
    kg = _kg_version_snapshot(snapshot["kg_version_id"])
    assert kg["status"] == "failed"
    assert kg["error_code"] == ErrorCode.INTERNAL_ERROR.value


def test_kg_build_records_retry_count(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    settings = get_settings()
    document_id = seed_document("processing")
    _place_extract_artifacts(document_id)
    calls: list[int] = []

    class _FlakyBuilder:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def build(self, request: Any) -> Any:
            from app.services.kg.builder import BuildStats

            calls.append(len(calls) + 1)
            if len(calls) < 3:
                raise GraphUnavailableError("transient failure")
            return BuildStats(entity_count=1, relation_count=1, batch_count=1)

    monkeypatch.setattr("app.tasks.registry.ThreeStageKgBuilder", _FlakyBuilder)

    asyncio.run(kg_build_executor(_make_spec(document_id)))

    assert calls == [1, 2, 3]
    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["kg_build_retry_count"] == 2
    assert settings.task_retry_max_attempts == 3


def test_kg_build_missing_document_graceful() -> None:
    """documents 无记录 → 早 return 不抛（TaskManager.recover 已兜底）。"""
    document_id = uuid4()
    asyncio.run(kg_build_executor(_make_spec(document_id)))
