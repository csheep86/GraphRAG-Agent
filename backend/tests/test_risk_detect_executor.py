"""Sprint 7.1 批次 A §2.4：``risk.detect`` 执行体（M4 疑点检出挂管线）。

覆盖 tasks §2.4 的四条纪律：

1. **作用域是 ``kg_version``**（跨文档）——无 ``kg_version_id`` / 版本非 ``ready``
   → **显式跳过并记账**，不许当成「无嫌疑」；
2. 成功 → 逐条打点 + 写 ``kg/suspicions.json`` 产物；
3. Neo4j 不可用 → **整体 failed**（末段语义），**不**降级为「没有疑点」；
4. 登记进 ``EXECUTOR_REGISTRY`` 后 ``resolve_pipeline_stages()`` 即包含本阶段
   （「删掉即停用」的接缝 4 语义）。

Neo4j 零依赖：``AffiliationService`` 以假类整体替换。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import Document, KgVersion
from app.db.session import SessionLocal, init_db
from app.services.graphs import GraphUnavailableError
from app.services.kg import Suspicion, SuspicionEvidence
from app.storage import build_kg_artifact_key, get_storage
from app.tasks.pipeline import resolve_pipeline_stages
from app.tasks.registry import risk_detect_executor
from app.tasks.types import TaskSpec

_SUSPICION = Suspicion(
    suspicion_type="shared_legal_rep",
    severity="medium",
    entities=("sub-a", "sub-b", "lpr-c"),
    entity_names=("甲公司", "乙公司", "缪建民"),
    evidence=(
        SuspicionEvidence(
            node_id="lpr-c",
            chunk_id="chunk-0001",
            doc_id=None,
            text="法定代表人：缪建民",
            page=45,
            char_start=120,
            char_end=132,
        ),
    ),
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    init_db()


@pytest.fixture
def zero_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "task_retry_initial_seconds", 0.0)


@pytest.fixture
def cleanup_rows() -> Any:  # noqa: ANN401 - 生成器夹具返回 list
    """真机 DB 收尾：本用例造的 Document / KgVersion 行一律删除（**不**污染演示库）。"""
    created: dict[str, list[UUID]] = {"documents": [], "kg_versions": []}
    yield created
    with SessionLocal() as session:
        if created["kg_versions"]:
            session.execute(
                delete(KgVersion).where(KgVersion.id.in_(created["kg_versions"]))
            )
        if created["documents"]:
            session.execute(
                delete(Document).where(Document.id.in_(created["documents"]))
            )
        session.commit()


def _insert_document(created: dict[str, list[UUID]]) -> UUID:
    settings = get_settings()
    document_id = uuid4()
    with SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(b"risk.pdf").hexdigest(),
                mime_type="application/pdf",
                size_bytes=2048,
                status="processing",
                uploaded_by=settings.default_actor_id,
                org_id=settings.default_org_id,
                trace_id=uuid4(),
            )
        )
        session.commit()
    created["documents"].append(document_id)
    return document_id


def _insert_kg_version(
    created: dict[str, list[UUID]], document_id: UUID, *, status: str = "ready"
) -> UUID:
    settings = get_settings()
    row_id = uuid4()
    with SessionLocal() as session:
        session.add(
            KgVersion(
                id=row_id,
                org_id=settings.default_org_id,
                version=f"v-risk-{row_id.hex[:8]}",
                status=status,
                source_doc_ids=[str(document_id)],
                trace_id=uuid4(),
            )
        )
        session.commit()
    created["kg_versions"].append(row_id)
    return row_id


def _seed(
    created: dict[str, list[UUID]], *, version_status: str | None = "ready"
) -> UUID:
    """造一份「已建图」的文档；``version_status=None`` 表示尚未建图。"""
    document_id = _insert_document(created)
    if version_status is not None:
        version_id = _insert_kg_version(created, document_id, status=version_status)
        _link_kg_version(document_id, version_id)
    return document_id


def _link_kg_version(document_id: UUID, kg_version_id: UUID) -> None:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.kg_version_id = kg_version_id
        session.commit()


def _snapshot(document_id: UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        return {
            "status": document.status,
            "error_code": document.error_code,
            "error_detail": document.error_detail,
            "kg_version_id": document.kg_version_id,
        }


def _make_spec(document_id: UUID) -> TaskSpec:
    trace_id = str(uuid4())
    return TaskSpec(
        task_type="risk.detect",
        payload={"document_id": str(document_id), "trace_id": trace_id},
        trace_id=trace_id,
    )


class _FakeAffiliationService:
    """``AffiliationService`` 替身（**传类不传实例**：执行体会 ``AffiliationService()``）。"""

    calls: list[dict[str, Any]] = []
    raises: BaseException | None = None

    def __init__(self, *, graph_service: Any = None, max_evidence: int = 6) -> None:
        self.graph_service = graph_service

    def detect(self, **kwargs: Any) -> list[Suspicion]:
        _FakeAffiliationService.calls.append(kwargs)
        if _FakeAffiliationService.raises is not None:
            raise _FakeAffiliationService.raises
        return [_SUSPICION]


def _patch_service(
    monkeypatch: pytest.MonkeyPatch, *, raises: BaseException | None = None
) -> None:
    # ``_do_risk_detect`` 在函数体内 ``from app.services.kg import AffiliationService``，
    # 故打桩**模块属性**即可（无需打 registry 的名字）
    import app.services.kg as kg_pkg

    _FakeAffiliationService.calls = []
    _FakeAffiliationService.raises = raises
    monkeypatch.setattr(kg_pkg, "AffiliationService", _FakeAffiliationService)


def test_skip_when_no_kg_version(
    zero_retry_wait: None, cleanup_rows: dict[str, list[UUID]]
) -> None:
    """没建图就没有可查的版本 → 跳过（**不**产疑点、**不**报错、**不**改 status）。"""
    document_id = _seed(cleanup_rows, version_status=None)

    asyncio.run(risk_detect_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "processing"
    assert snapshot["error_code"] is None


def test_skip_when_version_not_ready(
    zero_retry_wait: None,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_rows: dict[str, list[UUID]],
) -> None:
    """ADR-0002：只有 ``ready`` 版本可被消费；``building`` / ``failed`` 一律跳过。"""
    document_id = _seed(cleanup_rows, version_status="building")
    _patch_service(monkeypatch)

    asyncio.run(risk_detect_executor(_make_spec(document_id)))

    assert _FakeAffiliationService.calls == [], "非 ready 版本不得执行检出"
    assert _snapshot(document_id)["status"] == "processing"


def test_detect_writes_artifact_and_keeps_status(
    zero_retry_wait: None,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_rows: dict[str, list[UUID]],
) -> None:
    """成功路径：检出 → 写 ``kg/suspicions.json``；``documents.status`` 由末段收口。"""
    document_id = _seed(cleanup_rows)
    _patch_service(monkeypatch)

    asyncio.run(risk_detect_executor(_make_spec(document_id)))

    assert len(_FakeAffiliationService.calls) == 1
    call = _FakeAffiliationService.calls[0]
    assert call["org_id"] == get_settings().default_org_id
    assert set(call) >= {"kg_version", "org_id", "trace_id"}

    settings = get_settings()
    raw = get_storage().get(
        build_kg_artifact_key(
            org_id=settings.default_org_id,
            doc_id=document_id,
            filename="suspicions.json",
        ),
        org_id=settings.default_org_id,
    )
    payload = json.loads(raw.decode("utf-8"))
    assert payload["total"] == 1
    assert payload["suspicions"][0]["type"] == "shared_legal_rep"
    assert payload["suspicions"][0]["evidence"][0]["chunk_id"] == "chunk-0001"


def test_graph_unavailable_marks_document_failed(
    zero_retry_wait: None,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_rows: dict[str, list[UUID]],
) -> None:
    """Neo4j 挂了 = 任务失败（末段收口），**绝不**降级成「没有疑点」。"""
    document_id = _seed(cleanup_rows)
    _patch_service(monkeypatch, raises=GraphUnavailableError("connection refused"))

    asyncio.run(risk_detect_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"
    assert snapshot["error_code"] == ErrorCode.INTERNAL_ERROR.value


def test_registered_stage_is_resolvable() -> None:
    """登记后管线即包含 ``risk.detect``（接缝 4：删掉配置即停用的前提）。"""
    assert "risk.detect" in resolve_pipeline_stages()


def test_disabled_stage_drops_out_of_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tasks §2.4：``settings.pipeline_stages`` 删掉它 → 阶段不再被解析出来（可启停）。"""
    monkeypatch.setattr(
        get_settings(),
        "pipeline_stages",
        ["document.parse", "document.extract", "kg.build"],
    )

    assert resolve_pipeline_stages() == [
        "document.parse",
        "document.extract",
        "kg.build",
    ]
