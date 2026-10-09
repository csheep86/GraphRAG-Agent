"""P6-V2 判据 2 / 3 的**取证探针**（抽完一份文档后直接读库，绕开 pytest 断言）。

为什么要单独一个探针而不是只看 pytest 输出：pytest 断言是"它自己说的"，
本脚本落到持久库里同一天**同一个 org** 的两行上，把

- 抽取行 vs 问答行是不是**两行**（X-6 的核心）
- 同一份文档跨两行是不是只被数**一次**（Y6）

直接读出来给人看。用到它还意味着本机 `graphrag_test` 得先补过 stage 列
（`uv run python ../changes/P6-V2/sync_local_test_db_stage.py`）。

跑法（backend/ 目录，双容器 Up）：

```powershell
$pw = (Select-String -Path .env -Pattern '^NEO4J_PASSWORD=(.*)$')
uv run python ../changes/P6-V2/probe_extraction_cost_rows.py
```
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import COST_STAGE_ANSWER, COST_STAGE_EXTRACTION, CostMetric, Document
from app.db.session import init_db, session_scope
from app.services.cost_metrics import build_dashboard, record_answer_usage
from app.services.extraction.langextract import ExtractionResult
from app.storage import build_parse_artifact_key, get_storage
from app.tasks.registry import document_extract_executor
from app.tasks.types import TaskSpec

_FULL_MD = (
    "# 合同正文\n\n甲方：北京青云科技有限公司。\n\n乙方：上海临港智能装备有限公司。\n\n"
)

#: 注入替身带出的用量（**非零**，否则"落点通没通"看不出来）
_STUB_USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


class _StubExtractClient:
    def __init__(self) -> None: ...

    @classmethod
    def from_settings(cls, **_kwargs: object) -> _StubExtractClient:
        return cls()

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
            llm_usage=dict(_STUB_USAGE),
        )


async def _to_thread(func, /, *args, **kwargs):  # noqa: ANN001, ANN401
    return func(*args, **kwargs)


def main() -> None:
    import asyncio as _asyncio

    import app.tasks.registry as registry

    registry.LangextractClient = _StubExtractClient  # type: ignore[misc]
    _asyncio.to_thread = _to_thread  # type: ignore[assignment]

    init_db()
    settings = get_settings()
    # ⚠️ **刻意不用默认 org**：本地 `graphrag_test` 是持久库，默认租户今天早就有
    # 上一轮跑出来的问答行（探针第一次就是这么被"污染"的：仪表盘读出来 29419）。
    # 洁净 BigDecimal ⇒ 数字必须能对上。
    org_id = uuid4()
    document_id = uuid4()

    with session_scope(org_id=org_id) as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(document_id.bytes).hexdigest(),
                mime_type="application/pdf",
                size_bytes=1024,
                status="pending",
                uploaded_by=settings.default_actor_id,
                org_id=org_id,
                trace_id=uuid4(),
            )
        )
        session.commit()
    get_storage().put(
        build_parse_artifact_key(org_id=org_id, doc_id=document_id, filename="full.md"),
        _FULL_MD.encode("utf-8"),
    )

    row_ids: list[UUID] = []
    try:
        for attempt in (1, 2):
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
            if attempt == 1:
                # 执行体对已 completed 幂等早退 ⇒ 模拟"再次提交抽取"
                with session_scope(org_id=org_id) as session:
                    doc = session.get(Document, document_id)
                    doc.extract_status = None
                    doc.extract_retry_count = 0
                    session.commit()

        today = datetime.now(UTC).date()
        with session_scope(org_id=org_id) as db:
            answer_row = record_answer_usage(
                org_id=org_id,
                token_usage=type(
                    "U",
                    (),
                    {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )(),
                doc_ids=[document_id],  # 与抽取侧**同一份**文档
                db=db,
            )
            assert answer_row is not None
            row_ids.append(answer_row.id)

            rows = sorted(
                db.scalars(
                    select(CostMetric).where(
                        CostMetric.org_id == org_id, CostMetric.metric_date == today
                    )
                ).all(),
                key=lambda row: row.stage,
            )
            row_ids.extend(row.id for row in rows if row.id not in row_ids)

            print("=== 当日 cost_metrics 实读 ===")
            for row in rows:
                print(
                    f"  stage={row.stage:<10} "
                    f"in={row.token_usage_input:<4} out={row.token_usage_output:<3} "
                    f"total={row.token_usage_total:<4} doc_count={row.doc_count} "
                    f"single_doc_cost={row.single_doc_cost:.2f} "
                    f"docs={row.counted_doc_ids}"
                )

            extraction = next(
                (r for r in rows if r.stage == COST_STAGE_EXTRACTION), None
            )
            answer = next((r for r in rows if r.stage == COST_STAGE_ANSWER), None)
            assert extraction is not None and answer is not None
            assert extraction.token_usage_total == 150 * 2, (
                f"抽取两次未累加：实读={extraction.token_usage_total}"
            )
            assert extraction.doc_count == 1, (
                f"同一文档重抽被重复计数：实读={extraction.doc_count}"
            )

            payload = build_dashboard(
                db=db,
                org_id=org_id,
                date_from=today - timedelta(days=1),
                date_to=today,
            )

        print("=== 仪表盘（同日两 stage）实读 ===")
        print(f"  token_usage_total={payload['token_usage_total']}  (期望 300+15=315)")
        print(f"  single_doc_cost  ={payload['single_doc_cost']:.2f}  (期望 315/1=315)")
        print(f"  cost_ratio       ={payload['cost_ratio']:.2f}  (无写入方 ⇒ 恒 0.0)")
        assert payload["token_usage_total"] == 315
        assert payload["single_doc_cost"] == 315.0, "跨 stage 去重失效 ⇒ 分母被翻倍"
        print("\n[OK] X-6 落地 + Y6 跨行去重，均为实读")
    finally:
        with session_scope(org_id=org_id) as session:
            if row_ids:
                session.execute(delete(CostMetric).where(CostMetric.id.in_(row_ids)))
            session.execute(delete(Document).where(Document.id == document_id))
            session.commit()


if __name__ == "__main__":
    main()
