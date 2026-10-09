"""P6-V2（偏离 X-6）：M2 **抽取侧** token 落 `cost_metrics` 的判据。

为什么单独一个文件、而不是塞进 ``test_cost_metrics.py``：那边验的是「问答侧 +
仪表盘」，本模块验的是 **第二处写入方**（抽取）——两者唯一一行 vef粒度、stage、
失败语义都不一样，混写会让「哪一侧真的通了」变得不可读。

覆盖：

1. ``registry._do_extract`` 把 usage 写进抽取口径那一行（**写库仅此 1 处**的证据）；
2. 同一文档抽两次 ⇒ token 累加、**文档不重复计数**（复用 ``counted_doc_ids``）；
3. 抽取行与问答行同日**并存**、各有自己的 ``counted_doc_ids`` ⇒
   ``single_doc_cost`` 两行各自成一个口径（这就是 X-6 要防的"混入同一行"）；
4. ``mock`` 档（无真实 LLM 调用）⇒ **不写 0**、跳过（A15 反向守卫）；
5. 记帐崩了不许拖垮抽取主链路（旁路语义）。

隔离：每个用例自带 org / 文档，finally 里按 **id 精确清理**（按 org 全删会误伤
会话内其它用例的行）。
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import COST_STAGE_ANSWER, COST_STAGE_EXTRACTION, CostMetric, Document
from app.db.session import SessionLocal, init_db
from app.services.cost_metrics import build_dashboard, record_answer_usage
from app.services.extraction.langextract import ExtractionResult
from app.storage import build_parse_artifact_key, get_storage
from app.tasks.registry import document_extract_executor
from app.tasks.types import TaskSpec

_FULL_MD = "# 合同正文\n\n甲方：北京青云科技有限公司。\n\n"

#: 注入替身要带的用量（**不是 0**：0 会让"写了没有"这条断言失去分辨力）
_STUB_USAGE: dict[str, int] = {
    "prompt_tokens": 120,
    "completion_tokens": 30,
    "total_tokens": 150,
}
#: 当前用例想让替身返回什么（含"没有用量"的形态 ⇒ 测跳过）
_USAGE_BAG: dict[str, dict[str, int]] = {"value": dict(_STUB_USAGE)}


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    init_db()


class _StubExtractClient:
    """``LangextractClient`` 的最小替身：只保证 `llm_usage` 按用例要求带出。

    **为什么不 patch 真实 LangExtract**：这条链路要验的是「``_do_extract`` 有没有
    把 usage 落库」，不是「LLM 能不能抽出实体」——后者已被布尔逻辑自己的测试覆盖。
    """

    def __init__(self, usage: dict[str, int]) -> None:
        self._usage = dict(usage)

    @classmethod
    def from_settings(cls, **_kwargs: Any) -> _StubExtractClient:  # noqa: ANN401
        return cls(_USAGE_BAG["value"])

    def extract_entities_relations(
        self, *, document_id: UUID, full_md_text: str, trace_id: UUID
    ) -> ExtractionResult:
        return ExtractionResult(
            document_id=document_id,
            trace_id=trace_id,
            entities=[],
            relations=[],
            chunks=[],
            failed_chunks=[],
            llm_usage=dict(self._usage),
        )


async def _run_in_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    """同步替身：避免真开线程（替身没有 IO，开线程只会让断言更难读）。"""
    return func(*args, **kwargs)


@pytest.fixture
def fake_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, dict[str, int]]]:
    """把执行体里的抽取客户端换成替身，并交出「本次想返回什么用量」的控制权。"""
    monkeypatch.setattr("app.tasks.registry.LangextractClient", _StubExtractClient)
    monkeypatch.setattr(asyncio, "to_thread", _run_in_thread)
    _USAGE_BAG["value"] = dict(_STUB_USAGE)
    yield _USAGE_BAG
    _USAGE_BAG["value"] = dict(_STUB_USAGE)


def _seed_document(org_id: UUID) -> UUID:
    document_id = uuid4()
    with SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                mime_type="application/pdf",
                size_bytes=1024,
                status="pending",
                uploaded_by=get_settings().default_actor_id,
                org_id=org_id,
                trace_id=uuid4(),
            )
        )
        session.commit()
    get_storage().put(
        build_parse_artifact_key(org_id=org_id, doc_id=document_id, filename="full.md"),
        _FULL_MD.encode("utf-8"),
    )
    return document_id


def _reopen_extract(document_id: UUID) -> None:
    """把阶段状态拨回未完成——**已 completed 的文档会被执行体幂等早退**。

    这不是替产品遮丑：幂等是执行体的既定行为（见
    ``document_extract_skipped_already_completed``），要去重是从写库那一侧看，
    所以这里模拟的是「同一份文档被再次提交抽取」的现实路径。
    """
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.extract_status = None
        document.extract_retry_count = 0
        session.commit()


def _run_extract(document_id: UUID, org_id: UUID) -> None:
    asyncio.run(
        document_extract_executor(
            TaskSpec(
                task_type="document.extract",
                payload={"document_id": str(document_id)},
                trace_id=str(uuid4()),
                org_id=org_id,
            )
        )
    )


def _cleanup(*, org_id: UUID, document_ids: list[UUID], rows: list[Any]) -> None:
    with SessionLocal() as session:
        if rows:
            session.execute(delete(CostMetric).where(CostMetric.id.in_(rows)))
        if document_ids:
            session.execute(delete(Document).where(Document.id.in_(document_ids)))
        session.commit()


def _stage_row(db: Session, org_id: UUID, stage: str) -> CostMetric | None:
    """**带 stage** 读当日行——漏了这个谓词，本文件的断言全都失去分辨力。"""
    from datetime import UTC, datetime

    today = datetime.now(UTC).date()
    return db.scalar(
        select(CostMetric).where(
            CostMetric.org_id == org_id,
            CostMetric.metric_date == today,
            CostMetric.stage == stage,
        )
    )


# --------------------------------------------------------------------------- #
# 1. 抽取侧落点
# --------------------------------------------------------------------------- #


def test_extract_writes_usage_into_extraction_stage_row(
    fake_extraction: dict[str, dict[str, int]],
) -> None:
    """``_do_extract`` 把 usage 写进 ``stage='extraction'`` 那一行（写库仅此 1 处）。"""
    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    rows: list[Any] = []
    try:
        _run_extract(document_id, org_id)

        with SessionLocal() as db:
            row = _stage_row(db, org_id, COST_STAGE_EXTRACTION)
            assert row is not None, "抽取侧没有落任何 cost_metrics 行"
            rows.append(row.id)
            assert row.token_usage_input == _STUB_USAGE["prompt_tokens"]
            assert row.token_usage_output == _STUB_USAGE["completion_tokens"]
            assert row.token_usage_total == _STUB_USAGE["total_tokens"]
            assert row.doc_count == 1
            assert row.counted_doc_ids == [str(document_id)]
            assert row.single_doc_cost == pytest.approx(
                float(_STUB_USAGE["total_tokens"])
            )
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=rows)


def test_same_document_extracted_twice_counts_once(
    fake_extraction: dict[str, dict[str, int]],
) -> None:
    """同一份文档抽两次：token **累加**、``doc_count`` **仍是 1**（X-3 去重）。

    去重失效的后果：``single_doc_cost`` 随抽取次数单调下降 ⇒
    「多抽几次」就能把单文档成本刷低，指标当场失真。
    """
    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    _run_extract(document_id, org_id)
    _reopen_extract(document_id)
    _run_extract(document_id, org_id)

    rows: list[Any] = []
    try:
        with SessionLocal() as db:
            row = _stage_row(db, org_id, COST_STAGE_EXTRACTION)
            assert row is not None
            rows.append(row.id)
            assert row.token_usage_input == _STUB_USAGE["prompt_tokens"] * 2
            assert row.token_usage_total == _STUB_USAGE["total_tokens"] * 2
            assert row.doc_count == 1, f"去重失效：实读={row.doc_count}"
            assert row.single_doc_cost == pytest.approx(
                float(_STUB_USAGE["total_tokens"] * 2)
            )
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=rows)


# --------------------------------------------------------------------------- #
# 2. 两个口径必须落**两行**（X-6 的核心）
# --------------------------------------------------------------------------- #


def test_extraction_and_answer_rows_coexist_without_mixing(
    fake_extraction: dict[str, dict[str, int]],
) -> None:
    """同一天抽取 + 问答 ⇒ **两行并存**（``UNIQUE`` 已含 stage），各成口径。

    这条是 X-6 的正面证据：加 ``stage`` **之前**这两笔会撞唯一键、或者挤进同一行
    让 ``single_doc_cost`` 变成混合物。
    """
    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    _run_extract(document_id, org_id)

    answer_doc = uuid4()
    rows: list[Any] = []
    try:
        with SessionLocal() as db:
            answer_row = record_answer_usage(
                org_id=org_id,
                token_usage=_usage_object(10, 5, 15),
                doc_ids=[answer_doc, document_id],
                db=db,
            )
            assert answer_row is not None
            rows.append(answer_row.id)

            extraction = _stage_row(db, org_id, COST_STAGE_EXTRACTION)
            answer = _stage_row(db, org_id, COST_STAGE_ANSWER)
            assert extraction is not None and answer is not None
            rows.append(extraction.id)

            assert extraction.id != answer.id, "两侧落进了同一行 ⇒ X-6 没生效"
            assert extraction.stage == COST_STAGE_EXTRACTION
            assert answer.stage == COST_STAGE_ANSWER
            # 分母各算各的（Y4）：抽取侧只有 1 份文档，问答侧 2 份
            assert extraction.doc_count == 1
            assert answer.doc_count == 2
            assert extraction.single_doc_cost == pytest.approx(float(150))
            assert answer.single_doc_cost == pytest.approx(15 / 2)
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=rows)


def test_dashboard_does_not_double_count_a_document_seen_by_both_stages(
    fake_extraction: dict[str, dict[str, int]],
) -> None:
    """区间聚合按文档 id **跨行去重**（Y6）：同日两 TIER 都数过同一份文档 ⇒ 只算 1。"""
    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    _run_extract(document_id, org_id)

    from datetime import UTC, datetime, timedelta

    rows: list[Any] = []
    try:
        with SessionLocal() as db:
            answer_row = record_answer_usage(
                org_id=org_id,
                token_usage=_usage_object(10, 5, 15),
                doc_ids=[document_id],  # 与抽取侧**同一份**文档
                db=db,
            )
            assert answer_row is not None
            rows.append(answer_row.id)
            row = _stage_row(db, org_id, COST_STAGE_EXTRACTION)
            assert row is not None
            rows.append(row.id)

            today = datetime.now(UTC).date()
            payload = build_dashboard(
                db=db, org_id=org_id, date_from=today - timedelta(days=1), date_to=today
            )

        # 150（抽取）+ 15（问答）= 165 token；同一份文档只得 **1** 份 ⇒ 165 而不是 82.5
        assert payload["token_usage_total"] == 165
        assert payload["single_doc_cost"] == pytest.approx(165.0)
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=rows)


# --------------------------------------------------------------------------- #
# 3. 没有真实 LLM 调用 ⇒ 跳过（A15 反向守卫）
# --------------------------------------------------------------------------- #


def test_mock_like_extraction_without_usage_writes_nothing(
    fake_extraction: dict[str, dict[str, int]],
) -> None:
    """``llm_usage`` 为空（``mock`` 档 / 注入抽取器）⇒ **不写 0**、不建行。

    写 0 的害处：仪表盘会显示"有数据"，把「没记到」伪装成「成本为零」。
    """
    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    fake_extraction["value"] = {}  # 等价于 extraction_engine='mock'
    try:
        _run_extract(document_id, org_id)

        with SessionLocal() as db:
            assert _stage_row(db, org_id, COST_STAGE_EXTRACTION) is None, (
                "没有 LLM 调用却建行了 ⇒ 把『没记到』伪装成『成本为零』"
            )
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=[])


def test_extraction_survives_when_recording_fails(
    fake_extraction: dict[str, dict[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记帐是**旁路**：它炸了不许让抽取任务失败（那会让整篇文档白抽）。"""

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("cost_metrics 写挂了")

    monkeypatch.setattr("app.tasks.registry.record_extraction_usage", _boom)

    org_id = get_settings().default_org_id
    document_id = _seed_document(org_id)
    try:
        _run_extract(document_id, org_id)

        with SessionLocal() as db:
            document = db.get(Document, document_id)
            assert document is not None
            assert document.extract_status == "completed", (
                "旁路记帐失败把抽取主链路拖垮了"
            )
    finally:
        _cleanup(org_id=org_id, document_ids=[document_id], rows=[])


def _usage_object(prompt: int, completion: int, total: int) -> Any:  # noqa: ANN401
    """``TokenUsage`` 形态的最小替身（与 test_cost_metrics.py 同款）。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total
    )
