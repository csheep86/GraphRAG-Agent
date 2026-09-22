"""document.extract 执行体单元测试（Sprint 5 批次 B）。

覆盖 :mod:`app.tasks.registry.document_extract_executor`：

1. 状态机：``extract_status`` ``None → processing → completed``；
2. **整体** ``documents.status`` 不在本阶段被改写（保留给 kg.build 收口）；
3. 已 completed 早 return（幂等）；
4. tenacity 指数退避后成功 → ``extract_retry_count`` 回写；
5. 重试用尽 → 阶段级 ``failed`` + ``error_code / error_detail``；
6. 真实路径：storage ``full.md`` → LangExtract（mockable 默认抽取器）→
   ``entities.json`` / ``relations.json`` 落 storage；
7. 文档记录缺失时 graceful。

隔离策略与 :mod:`test_document_parse_executor` 一致：直接落库造数据、
``asyncio.run`` 同步直调、retry 等待置 0。
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
from app.db.models import Document
from app.db.session import SessionLocal, init_db
from app.services.extraction import LangextractError
from app.storage import (
    build_extract_artifact_key,
    build_parse_artifact_key,
    get_storage,
)
from app.tasks.registry import document_extract_executor
from app.tasks.types import TaskSpec

_FULL_MD = (
    "# 合同正文\n\n"
    "甲方：北京青云科技有限公司。\n\n"
    "乙方：上海临港智能装备有限公司。\n\n"
    "2024 年营业收入为人民币 12.34 亿元。"
)


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


def _snapshot(document_id: UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        return {
            "status": document.status,
            "extract_status": document.extract_status,
            "extract_retry_count": document.extract_retry_count,
            "error_code": document.error_code,
            "error_detail": document.error_detail,
        }


def _make_spec(document_id: UUID) -> TaskSpec:
    # trace_id 必须是可解析的 UUID（_do_extract 内部转 UUID 供日志绑定）
    return TaskSpec(
        task_type="document.extract",
        payload={"document_id": str(document_id)},
        trace_id=str(uuid4()),
    )


@pytest.fixture
def seed_document() -> Iterator[Callable[..., UUID]]:
    created: list[UUID] = []

    def _seed(status: str) -> UUID:
        document_id = _insert_document(status)
        created.append(document_id)
        return document_id

    yield _seed

    if created:
        with SessionLocal() as session:
            session.execute(delete(Document).where(Document.id.in_(created)))
            session.commit()


def _place_full_md(document_id: UUID) -> None:
    settings = get_settings()
    get_storage().put(
        build_parse_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="full.md"
        ),
        _FULL_MD.encode("utf-8"),
    )


# --------------------------------------------------------------------------- #
# 状态机
# --------------------------------------------------------------------------- #


def test_extract_happy_path_completes_stage_status(
    seed_document: Callable[..., UUID],
) -> None:
    """真实路径：full.md → 默认 mockable 抽取器 → 产物落 storage。"""
    settings = get_settings()
    document_id = seed_document("pending")
    _place_full_md(document_id)

    asyncio.run(document_extract_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["extract_status"] == "completed"
    assert snapshot["error_code"] is None
    # 阶段纪律：整体 status 不在本段被改写（由 kg.build 收口）
    assert snapshot["status"] == "pending"

    storage = get_storage()
    entities_raw = storage.get(
        build_extract_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="entities.json"
        ),
        org_id=settings.default_org_id,
    )
    relations_raw = storage.get(
        build_extract_artifact_key(
            org_id=settings.default_org_id,
            doc_id=document_id,
            filename="relations.json",
        ),
        org_id=settings.default_org_id,
    )
    entities = json.loads(entities_raw.decode("utf-8"))
    relations = json.loads(relations_raw.decode("utf-8"))
    assert entities, "两个中文机构名必须被 mockable 抽取器命中"
    assert {e["entity_type"] for e in entities} & {"ORG", "DATE"}
    assert relations, "两个 ORG 共现应产生 PARTY_TO 关系"


def test_extract_skips_already_completed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = seed_document("pending")
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.extract_status = "completed"
        session.commit()

    calls: list[Any] = []

    async def spy(*args: object, **kwargs: object) -> None:
        calls.append(args)

    monkeypatch.setattr("app.tasks.registry._do_extract", spy)
    asyncio.run(document_extract_executor(_make_spec(document_id)))

    assert calls == []
    assert _snapshot(document_id)["extract_status"] == "completed"


# --------------------------------------------------------------------------- #
# 重试
# --------------------------------------------------------------------------- #


def test_extract_retries_io_then_succeeds(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    document_id = seed_document("pending")
    calls: list[int] = []

    async def flaky(*, document_id: UUID, trace_id: str, payload: Any) -> None:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            raise OSError("simulated io error")

    monkeypatch.setattr("app.tasks.registry._do_extract", flaky)

    asyncio.run(document_extract_executor(_make_spec(document_id)))

    assert calls == [1, 2, 3]
    snapshot = _snapshot(document_id)
    assert snapshot["extract_status"] == "completed"
    assert snapshot["extract_retry_count"] == 2


def test_extract_retries_exhausted_marks_stage_failed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    settings = get_settings()
    document_id = seed_document("pending")

    async def always_fail(*, document_id: UUID, trace_id: str, payload: Any) -> None:
        # LangextractError 属可重试集合（与 MineruApiError 对位）
        raise LangextractError("permanent upstream failure")

    monkeypatch.setattr("app.tasks.registry._do_extract", always_fail)

    asyncio.run(document_extract_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["extract_status"] == "failed"
    assert snapshot["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert snapshot["error_detail"]
    assert snapshot["extract_retry_count"] == settings.task_retry_max_attempts - 1


def test_extract_failed_state_keeps_overall_status_pending(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """阶段级失败：只标 extract_status，整体 status 仍留给管线诊断。"""
    document_id = seed_document("pending")

    async def always_fail(*, document_id: UUID, trace_id: str, payload: Any) -> None:
        raise OSError("boom")

    monkeypatch.setattr("app.tasks.registry._do_extract", always_fail)

    asyncio.run(document_extract_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["extract_status"] == "failed"
    assert snapshot["status"] == "pending"


# --------------------------------------------------------------------------- #
# 缺失记录 graceful
# --------------------------------------------------------------------------- #


def test_extract_handles_missing_document_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    calls: list[Any] = []

    async def spy(*args: object, **kwargs: object) -> None:
        calls.append(args)

    monkeypatch.setattr("app.tasks.registry._do_extract", spy)

    with SessionLocal() as session:
        before = len(session.execute(select(Document.id)).all())

    asyncio.run(document_extract_executor(_make_spec(document_id)))  # 不应抛

    with SessionLocal() as session:
        after = len(session.execute(select(Document.id)).all())

    assert calls == []
    assert after == before
