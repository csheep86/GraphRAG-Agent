"""阶段十一 11.2：孤儿任务回收单元测试。

覆盖 :mod:`app.tasks.manager` 的两个同步函数（ADR-0001 §3.2 / M1 §3 验收 8）：

- :func:`~app.tasks.manager.recover_orphan_tasks`：进程重启时把遗留
  ``pending`` / ``processing`` 批量置 ``failed (TASK_INTERRUPTED)``，并记录中断明细；
- :func:`~app.tasks.manager.list_in_flight_task_ids`：仅返回处于
  ``pending`` / ``processing`` 的 task_id（对账 / 测试辅助）。

**隔离策略**：``documents`` 表是 session 级共享 SQLite（见 ``conftest.py``），
而 ``recover_orphan_tasks`` 是**全表扫描**，会波及同一进程内其它用例遗留的在途行。
因此本模块：

1. 通过 ``seed_document`` 夹具直接落库造数据，用例结束删除本次造的行；
2. 与「条数」相关的断言一律以调用前 ``list_in_flight_task_ids()`` 的集合大小为基准，
   绝不写死常数，避免测试结果随其它用例漂移。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import AffiliationTask, Document
from app.db.session import SessionLocal, init_db
from app.tasks.manager import list_in_flight_task_ids, recover_orphan_tasks

#: 与 ``recover_orphan_tasks`` 写入的 ``error_detail`` 保持一致
#: （M1 §3 验收 8：error_detail 记录「进程重启导致任务中断」）。
INTERRUPTED_DETAIL = "process restarted while task was in-flight"


# --------------------------------------------------------------------------- #
# 夹具与工具
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    """确保 ``documents`` 表存在（幂等）。

    本模块不请求 ``client`` 夹具（不经过 FastAPI lifespan），故显式建表；
    ``Base.metadata.create_all`` 对已存在的表是 no-op，不影响其它用例。
    """
    init_db()


def _insert_document(
    status: str,
    *,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> UUID:
    """直接落一行 ``documents``，返回主键。"""
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
                error_code=error_code,
                error_detail=error_detail,
                trace_id=uuid4(),
            )
        )
        session.commit()
    return document_id


def _snapshot(document_id: UUID) -> dict[str, Any]:
    """读回一行 ``documents`` 的状态三要素。"""
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None, f"document {document_id} 未落库"
        return {
            "status": document.status,
            "error_code": document.error_code,
            "error_detail": document.error_detail,
        }


@pytest.fixture
def seed_document() -> Iterator[Callable[..., UUID]]:
    """造 ``documents`` 行并在用例结束后清理，避免污染共享库。"""
    created: list[UUID] = []

    def _seed(status: str, **overrides: Any) -> UUID:
        document_id = _insert_document(status, **overrides)
        created.append(document_id)
        return document_id

    yield _seed

    if created:
        with SessionLocal() as session:
            session.execute(delete(Document).where(Document.id.in_(created)))
            session.commit()


# --------------------------------------------------------------------------- #
# recover_orphan_tasks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["pending", "processing"])
def test_recover_orphan_tasks_marks_in_flight_as_failed(
    seed_document: Callable[..., UUID], status: str
) -> None:
    """ADR-0001 §3.2：``pending`` / ``processing`` 一律回收为 ``failed``。"""
    document_id = seed_document(status)

    report = recover_orphan_tasks()

    assert report.reclaimed >= 1
    assert _snapshot(document_id)["status"] == "failed"


def test_recover_orphan_tasks_records_task_interrupted_error_code(
    seed_document: Callable[..., UUID],
) -> None:
    """M1 §3 验收 8：写入 ``TASK_INTERRUPTED`` + 可读的中断明细。"""
    document_id = seed_document("processing")

    recover_orphan_tasks()

    snapshot = _snapshot(document_id)
    assert snapshot["error_code"] == ErrorCode.TASK_INTERRUPTED.value
    # 明细用于区分「进程重启中断」与「解析真实失败」，必须非空且点明重启语义。
    assert snapshot["error_detail"]
    assert "restart" in snapshot["error_detail"].lower()


def test_recover_orphan_tasks_keeps_completed_as_is(
    seed_document: Callable[..., UUID],
) -> None:
    """已成功的任务绝不回退（终态不可被回收改写）。"""
    document_id = seed_document("completed")

    recover_orphan_tasks()

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["error_code"] is None
    assert snapshot["error_detail"] is None


def test_recover_orphan_tasks_keeps_failed_as_is(
    seed_document: Callable[..., UUID],
) -> None:
    """已失败任务的原始错误码 / 明细必须原样保留，不被 TASK_INTERRUPTED 覆盖。"""
    document_id = seed_document(
        "failed",
        error_code=ErrorCode.INTERNAL_ERROR.value,
        error_detail="pre-existing failure",
    )

    recover_orphan_tasks()

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"
    assert snapshot["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert snapshot["error_detail"] == "pre-existing failure"


def test_recover_orphan_tasks_reclaims_exactly_in_flight_rows(
    seed_document: Callable[..., UUID],
) -> None:
    """``reclaimed`` 精确等于调用前的在途集合大小（全表扫描语义，不多不少）。"""
    seed_document("pending")
    seed_document("processing")
    completed = seed_document("completed")
    failed = seed_document("failed", error_code=ErrorCode.INTERNAL_ERROR.value)

    before = set(list_in_flight_task_ids())
    assert len(before) >= 2
    assert completed not in before
    assert failed not in before

    report = recover_orphan_tasks()

    assert report.reclaimed == len(before)


def test_recover_orphan_tasks_is_idempotent(
    seed_document: Callable[..., UUID],
) -> None:
    """lifespan startup 可能重复触发；第二次扫描在途集合已空，回收数必为 0。"""
    seed_document("pending")

    first = recover_orphan_tasks()
    second = recover_orphan_tasks()

    assert first.reclaimed >= 1
    assert second.reclaimed == 0
    assert list_in_flight_task_ids() == ()


# --------------------------------------------------------------------------- #
# list_in_flight_task_ids
# --------------------------------------------------------------------------- #


def test_list_in_flight_task_ids_returns_only_pending_and_processing(
    seed_document: Callable[..., UUID],
) -> None:
    """只挑出 ``pending`` / ``processing``，终态（completed / failed）一律排除。"""
    pending = seed_document("pending")
    processing = seed_document("processing")
    completed = seed_document("completed")
    failed = seed_document("failed", error_code=ErrorCode.INTERNAL_ERROR.value)

    result = list_in_flight_task_ids()

    assert isinstance(result, tuple)
    assert pending in result
    assert processing in result
    assert completed not in result
    assert failed not in result


def test_list_in_flight_task_ids_is_empty_after_recover(
    seed_document: Callable[..., UUID],
) -> None:
    """回收后应无任何在途任务（与 recover 的「全清」语义互为印证）。"""
    seed_document("pending")
    seed_document("processing")
    assert list_in_flight_task_ids(), "seed 后应至少含本次造的在途行"

    recover_orphan_tasks()

    assert list_in_flight_task_ids() == ()


def test_list_in_flight_task_ids_covers_affiliation_tasks() -> None:
    """S7.2-2（Sprint 8.1 批次 B 偿还）：在途 ``affiliation_tasks`` 也在对账结果里。

    ``recover_orphan_tasks`` 早已扫两表，本函数若仍只查 ``documents``，对账
    ``affiliation_tasks`` 就是盲区（backend/CODEBUDDY.md §4 S7.2-2）。
    """
    affiliation_id = uuid4()
    with SessionLocal() as session:
        session.add(
            AffiliationTask(
                id=affiliation_id,
                org_id=get_settings().default_org_id,
                doc_ids=[str(uuid4())],
                status="processing",
                trace_id=uuid4(),
            )
        )
        session.commit()
    try:
        result = list_in_flight_task_ids()
        assert isinstance(result, tuple)
        assert affiliation_id in result
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(AffiliationTask).where(AffiliationTask.id == affiliation_id)
            )
            session.commit()
