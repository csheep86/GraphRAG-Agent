"""阶段十一 11.2 + Sprint 5 批次 A：document.parse 执行体单元测试。

覆盖 :mod:`app.tasks.registry.document_parse_executor` 的完整生命周期：

1. 状态机 ``pending → processing → completed`` 推进；
2. 已 ``completed`` 早 return 守卫（幂等性）；
3. tenacity 指数退避：第三方 IO 异常重试后成功；
4. tenacity 用尽后置 ``failed``；
5. 失败态 ``error_code / error_detail`` 落库结构化；
6. 文档记录缺失时 graceful 早 return；
7. （批次 A）completed 回填 ``storage_key``（M1 §4.1）；
8. （批次 A / B1 修复）重试计数回写 ``retry_count``；
9. （批次 A）PDF 真实路径：MinerU 客户端（mock）→ 产物落存储层；
10. （批次 A）docx 跳过结构化解析（S10 承接）。

**隔离策略**：

- 直接落库造数据（``seed_document`` 夹具，DELETE 收尾），不经过 FastAPI / BackgroundTasks；
- ``document_parse_executor`` 是 ``async``，测试通过 ``asyncio.run`` 同步直调；
- tenacity ``wait_exponential`` 等待参数在测试中临时置 0.0，
  ``monkeypatch`` 自动恢复，不污染其它用例；
- MinerU 客户端以假类整体替换（网络零依赖）。

**不与** :func:`~app.tasks.manager.recover_orphan_tasks` 混用（B3 约束）：
回收函数是全表扫描，会强制置 ``failed (TASK_INTERRUPTED)``，与 executor 测试的状态断言冲突。

**已修复（Sprint 5 批次 A）**：

- B1：``retry_count`` 现在在重试回调与 completed 分支回写 DB；
- B4：``wait_exponential`` 的 ``exp_base`` 真实读取 ``task_retry_multiplier``。
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import Document
from app.db.session import SessionLocal, init_db
from app.tasks.registry import document_parse_executor
from app.tasks.types import TaskSpec

#: 固定的 trace_id，便于日志回溯。
_TRACE_ID = "trace-test-document-parse-executor"


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
    mime_type: str = "application/pdf",
) -> UUID:
    """直接落一行 ``documents``，返回主键。"""
    settings = get_settings()
    document_id = uuid4()
    with SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(b"contract.pdf").hexdigest(),
                mime_type=mime_type,
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
    """读回一行 ``documents`` 的状态要素。"""
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None, f"document {document_id} 未落库"
        return {
            "status": document.status,
            "error_code": document.error_code,
            "error_detail": document.error_detail,
            "retry_count": document.retry_count,
            "storage_key": document.storage_key,
        }


def _make_spec(document_id: UUID) -> TaskSpec:
    """构造执行体入参。"""
    return TaskSpec(
        task_type="document.parse",
        payload={"document_id": str(document_id)},
        trace_id=_TRACE_ID,
    )


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


@pytest.fixture
def zero_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """tenacity ``wait_exponential`` 临时置 0 秒，避免真实等待 1s + 2s。

    ``monkeypatch`` 自动恢复，不污染其它用例。
    """
    monkeypatch.setattr(get_settings(), "task_retry_initial_seconds", 0.0)


# --------------------------------------------------------------------------- #
# 1. 状态机 happy path
# --------------------------------------------------------------------------- #


def test_executor_pushes_pending_to_completed(
    seed_document: Callable[..., UUID],
) -> None:
    """``pending → processing → completed`` 完整推进；无异常时 ``error_*`` 清空。

    用 docx（跳过 MinerU 的快路径）隔离状态机本身；PDF 真实路径见第 9 节。
    """
    document_id = seed_document(
        "pending",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["error_code"] is None
    assert snapshot["error_detail"] is None


# --------------------------------------------------------------------------- #
# 2. 已 completed 早 return
# --------------------------------------------------------------------------- #


def test_executor_skips_already_completed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已终态不重跑：spy 验证 ``_do_parse`` 未被调用，状态保持 ``completed``。"""
    document_id = seed_document("completed")
    calls: list[Any] = []

    async def spy(*, document_id: UUID, payload: Any) -> None:
        calls.append((document_id, payload))

    monkeypatch.setattr("app.tasks.registry._do_parse", spy)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    assert calls == [], "已 completed 的 doc 不应再调 _do_parse"
    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["error_code"] is None
    assert snapshot["error_detail"] is None


# --------------------------------------------------------------------------- #
# 3. tenacity 重试 IO 后成功
# --------------------------------------------------------------------------- #


def test_executor_retries_io_then_succeeds(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """``OSError`` 前 2 次失败、第 3 次成功 → 状态机最终落 ``completed``。"""
    document_id = seed_document("pending")
    calls: list[int] = []

    async def flaky_parse(*, document_id: UUID, payload: Any) -> None:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            raise OSError("simulated io error")
        # 第 3 次及之后：成功

    monkeypatch.setattr("app.tasks.registry._do_parse", flaky_parse)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    assert calls == [1, 2, 3], (
        f"应被调用 3 次（前 2 次失败，第 3 次成功），实际 {calls}"
    )
    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["error_code"] is None
    assert snapshot["error_detail"] is None


# --------------------------------------------------------------------------- #
# 4. tenacity 用尽后置 failed
# --------------------------------------------------------------------------- #


def test_executor_retries_exhausted_marks_failed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """``OSError`` 始终失败 → tenacity 用尽 → 状态 ``failed``，调用次数等于 ``max_attempts``。"""
    document_id = seed_document("pending")
    settings = get_settings()
    calls: list[int] = []

    async def always_fail(*, document_id: UUID, payload: Any) -> None:
        calls.append(len(calls) + 1)
        raise OSError("simulated permanent failure")

    monkeypatch.setattr("app.tasks.registry._do_parse", always_fail)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    assert calls == list(range(1, settings.task_retry_max_attempts + 1)), (
        f"调用次数应等于 max_attempts={settings.task_retry_max_attempts}，实际 {len(calls)}"
    )
    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"


# --------------------------------------------------------------------------- #
# 5. 失败态 error_code / error_detail 落库
# --------------------------------------------------------------------------- #


def test_executor_failed_state_records_error_code_and_detail(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """``ConnectionError`` → ``error_code = INTERNAL_ERROR``，``error_detail`` 含异常摘要。

    ``error_detail`` 是结构化字段，须能区分「进程重启中断」与「解析真实失败」：
    必须非空、点明异常类型与原始消息（前者日志回显原文禁止，但 ``error_detail`` 可读）。
    """
    document_id = seed_document("pending")

    async def raise_conn(*, document_id: UUID, payload: Any) -> None:
        raise ConnectionError("upstream timeout")

    monkeypatch.setattr("app.tasks.registry._do_parse", raise_conn)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"
    assert snapshot["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert snapshot["error_detail"]
    assert "ConnectionError" in snapshot["error_detail"]
    assert "upstream timeout" in snapshot["error_detail"]


# --------------------------------------------------------------------------- #
# 6. 文档记录缺失时 graceful
# --------------------------------------------------------------------------- #


def test_executor_handles_missing_document_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``documents`` 不存在：executor 早 return，无异常、无 DB 副作用。"""
    # 故意不落库
    document_id = uuid4()
    calls: list[Any] = []

    async def spy(*, document_id: UUID, payload: Any) -> None:
        calls.append((document_id, payload))

    monkeypatch.setattr("app.tasks.registry._do_parse", spy)

    # 计数基准：执行前后 ``documents`` 行数应不变
    with SessionLocal() as session:
        before = len(session.execute(select(Document.id)).all())

    asyncio.run(document_parse_executor(_make_spec(document_id)))  # 不应抛

    with SessionLocal() as session:
        after = len(session.execute(select(Document.id)).all())

    assert calls == [], "缺失 doc 不应触发 _do_parse"
    assert after == before, "缺失 doc 不应有 DB 副作用"


# --------------------------------------------------------------------------- #
# 7. （批次 A）completed 回填 storage_key（M1 §4.1）
# --------------------------------------------------------------------------- #


def test_executor_backfills_storage_key_on_completed(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """completed 后 storage_key 非 NULL 且格式 = {org}/{doc}/{hash}。"""

    async def noop(*, document_id: UUID, payload: Any) -> None:
        return None

    monkeypatch.setattr("app.tasks.registry._do_parse", noop)
    document_id = seed_document("pending")
    settings = get_settings()

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    expected_key = (
        f"{settings.default_org_id}/{document_id}/"
        + hashlib.sha256(b"contract.pdf").hexdigest()
    )
    assert snapshot["storage_key"] == expected_key


# --------------------------------------------------------------------------- #
# 8. （批次 A / B1）重试计数回写 retry_count
# --------------------------------------------------------------------------- #


def test_executor_records_retry_count(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """前 2 次失败、第 3 次成功 → retry_count = 2（重试次数，不含首次尝试）。"""
    document_id = seed_document("pending")
    calls: list[int] = []

    async def flaky(*, document_id: UUID, payload: Any) -> None:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            raise OSError("simulated io error")

    monkeypatch.setattr("app.tasks.registry._do_parse", flaky)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    assert calls == [1, 2, 3]
    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["retry_count"] == 2


def test_executor_failed_path_records_retry_count(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
    zero_retry_wait: None,
) -> None:
    """重试用尽 → failed 且 retry_count = max_attempts - 1；storage_key 保持 NULL。"""
    settings = get_settings()
    document_id = seed_document("pending")

    async def always_fail(*, document_id: UUID, payload: Any) -> None:
        raise OSError("simulated permanent failure")

    monkeypatch.setattr("app.tasks.registry._do_parse", always_fail)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "failed"
    assert snapshot["retry_count"] == settings.task_retry_max_attempts - 1
    assert snapshot["storage_key"] is None


# --------------------------------------------------------------------------- #
# 9. （批次 A）PDF 真实路径：MinerU（mock）→ 产物落存储层
# --------------------------------------------------------------------------- #


def test_do_parse_pdf_stores_artifacts(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF：源文件经存储层取出 → MinerU 解析 → md / content_list 落盘。"""
    from app.services.parsing import MineruParseResult
    from app.storage import build_parse_artifact_key, build_storage_key, get_storage
    from app.tasks.registry import _do_parse

    settings = get_settings()
    document_id = seed_document("pending")
    filename_hash = hashlib.sha256(b"contract.pdf").hexdigest()

    # 预置源文件（模拟上传链路已落盘）
    source_key = build_storage_key(
        org_id=settings.default_org_id, doc_id=document_id, filename_hash=filename_hash
    )
    get_storage().put(source_key, b"%PDF-fake-bytes")

    seen: dict[str, Any] = {}

    class _FakeMineruClient:
        def __init__(self, **kwargs: Any) -> None:
            seen["kwargs"] = kwargs

        async def parse_pdf(
            self, *, content: bytes, display_name: str
        ) -> MineruParseResult:
            seen["content"] = content
            seen["display_name"] = display_name
            return MineruParseResult(
                markdown="# 摘要", content_list_json='[{"type":"text"}]'
            )

    monkeypatch.setattr("app.tasks.registry.MineruClient", _FakeMineruClient)

    asyncio.run(
        _do_parse(document_id=document_id, payload={"document_id": str(document_id)})
    )

    # 源文件真实读取；对外文件名不含原始名（M5 §4.5）
    assert seen["content"] == b"%PDF-fake-bytes"
    assert seen["display_name"] == f"{document_id}.pdf"

    storage = get_storage()
    md_key = build_parse_artifact_key(
        org_id=settings.default_org_id, doc_id=document_id, filename="full.md"
    )
    cl_key = build_parse_artifact_key(
        org_id=settings.default_org_id, doc_id=document_id, filename="content_list.json"
    )
    assert storage.get(md_key, org_id=settings.default_org_id) == "# 摘要".encode()
    assert storage.get(cl_key, org_id=settings.default_org_id) == b'[{"type":"text"}]'


def test_executor_pdf_path_completes_with_artifacts(
    seed_document: Callable[..., UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """端到端：pending → MinerU（mock）→ completed + storage_key + 产物存在。"""
    from app.services.parsing import MineruParseResult
    from app.storage import build_parse_artifact_key, build_storage_key, get_storage

    settings = get_settings()
    document_id = seed_document("pending")
    filename_hash = hashlib.sha256(b"contract.pdf").hexdigest()

    source_key = build_storage_key(
        org_id=settings.default_org_id, doc_id=document_id, filename_hash=filename_hash
    )
    get_storage().put(source_key, b"%PDF-fake-bytes")

    class _FakeMineruClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def parse_pdf(
            self, *, content: bytes, display_name: str
        ) -> MineruParseResult:
            return MineruParseResult(markdown="md", content_list_json="[]")

    monkeypatch.setattr("app.tasks.registry.MineruClient", _FakeMineruClient)

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    assert snapshot["storage_key"] == source_key
    storage = get_storage()
    assert storage.exists(
        build_parse_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="full.md"
        )
    )


# --------------------------------------------------------------------------- #
# 10. （批次 A）docx 跳过结构化解析（S10 承接）
# --------------------------------------------------------------------------- #


def test_executor_skips_non_pdf_parse(
    seed_document: Callable[..., UUID],
) -> None:
    """docx：跳过 MinerU，照常 completed，不产生 parse/ 产物。"""
    from app.storage import build_parse_artifact_key, get_storage

    settings = get_settings()
    document_id = seed_document(
        "pending",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    asyncio.run(document_parse_executor(_make_spec(document_id)))

    snapshot = _snapshot(document_id)
    assert snapshot["status"] == "completed"
    storage = get_storage()
    assert not storage.exists(
        build_parse_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="full.md"
        )
    )
