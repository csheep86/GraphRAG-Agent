"""文档日期的**写入路径**（Sprint 9 批次 C，ADR-0005 §4）。

``documents.document_date`` 此前**只有读、没有写**——实测 13 份文档无一有日期，
抽取侧因此恒渲染 ``unknown``、问答的「依据截至哪天」恒答不上来。本模块钉住
现在的两条写入路径：

1. **人工指定**：上传接口的可选表单字段 ``document_date`` 直接落库；
2. **正文解析**：上传时没给 ⇒ 抽取执行体从 ``full.md`` 认；**认不出就留 None**。

第 2 条的「认不出」与「认出」同样重要：认错了等于给关系编一个生效日，
比留空危险得多（R4 纪律）。
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal, init_db
from app.storage import build_parse_artifact_key, get_storage
from app.tasks.registry import document_extract_executor
from app.tasks.types import TaskSpec

#: 上传样例（docx 与 test_documents.py 同款：后缀决定解析器）
DOCX = (
    "合同.docx",
    b"PK\x03\x04 docx bytes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

#: 正文**带出处**的日期 ⇒ 应被认出
FULL_MD_WITH_DATE = "# 年报\n\n报告期：2025年6月30日\n\n营业收入 12.34 亿元。"
#: 正文有日期但**没有出处**（成立日期不是文档日期）⇒ 必须留 None
FULL_MD_WITHOUT_SOURCE = "# 年报\n\n本公司成立于 2018 年 3 月。\n"


@pytest.fixture(scope="module", autouse=True)
def _ensure_schema() -> None:
    init_db()


def _insert_document(*, document_date: date | None = None) -> UUID:
    settings = get_settings()
    document_id = uuid4()
    with SessionLocal() as session:
        session.add(
            Document(
                id=document_id,
                filename_hash=hashlib.sha256(b"report.pdf").hexdigest(),
                mime_type="application/pdf",
                size_bytes=1024,
                status="pending",
                uploaded_by=settings.default_actor_id,
                org_id=settings.default_org_id,
                trace_id=uuid4(),
                document_date=document_date,
            )
        )
        session.commit()
    return document_id


def _place_full_md(document_id: UUID, text: str) -> None:
    settings = get_settings()
    get_storage().put(
        build_parse_artifact_key(
            org_id=settings.default_org_id, doc_id=document_id, filename="full.md"
        ),
        text.encode("utf-8"),
    )


def _read_document_date(document_id: UUID) -> date | None:
    with SessionLocal() as session:
        document = session.get(Document, document_id)
        assert document is not None
        return document.document_date


@pytest.fixture
def cleanup_documents() -> Iterator[Callable[[UUID], None]]:
    created: list[UUID] = []

    def _track(document_id: UUID) -> None:
        created.append(document_id)

    yield _track

    if created:
        with SessionLocal() as session:
            session.execute(delete(Document).where(Document.id.in_(created)))
            session.commit()


# --------------------------------------------------------------------------- #
# 路径一：上传时人工指定（人说的算）
# --------------------------------------------------------------------------- #


def test_upload_persists_explicit_document_date(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": DOCX},
        data={"document_date": "2025-06-30"},
        headers=dev_headers,
    )
    assert response.status_code == 200, response.text
    document_id = UUID(response.json()["task_id"])
    assert _read_document_date(document_id) == date(2025, 6, 30)


def test_upload_without_date_leaves_null(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """不填 ⇒ null，**不代填今天**。"""
    response = client.post(
        "/api/v1/documents/upload", files={"file": DOCX}, headers=dev_headers
    )
    assert response.status_code == 200, response.text
    assert _read_document_date(UUID(response.json()["task_id"])) is None


def test_upload_rejects_malformed_date(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """格式非法 ⇒ 4xx，**不是静默忽略成 null**。

    状态码取 400 而非 FastAPI 默认的 422：本项目由全局异常处理器统一转
    ``400 VALIDATION_ERROR``（错误响应规范），断言跟着项目走。
    """
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": DOCX},
        data={"document_date": "2025/06/30"},
        headers=dev_headers,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# 路径二：抽取执行体从正文认（认不出就 None）
# --------------------------------------------------------------------------- #


def test_extract_fills_document_date_from_text(
    cleanup_documents: Callable[[UUID], None],
) -> None:
    document_id = _insert_document()
    cleanup_documents(document_id)
    _place_full_md(document_id, FULL_MD_WITH_DATE)

    asyncio.run(
        document_extract_executor(
            TaskSpec(
                task_type="document.extract",
                payload={"document_id": str(document_id)},
                trace_id=str(uuid4()),
                # A5：org 必填（后台任务没有请求身份，只能由 TaskSpec 携带）
                org_id=get_settings().default_org_id,
            )
        )
    )

    assert _read_document_date(document_id) == date(2025, 6, 30)


def test_extract_leaves_none_when_date_has_no_source(
    cleanup_documents: Callable[[UUID], None],
) -> None:
    """正文有日期但**无出处** ⇒ None：宁可说不清，不可说错。"""
    document_id = _insert_document()
    cleanup_documents(document_id)
    _place_full_md(document_id, FULL_MD_WITHOUT_SOURCE)

    asyncio.run(
        document_extract_executor(
            TaskSpec(
                task_type="document.extract",
                payload={"document_id": str(document_id)},
                trace_id=str(uuid4()),
                # A5：org 必填（后台任务没有请求身份，只能由 TaskSpec 携带）
                org_id=get_settings().default_org_id,
            )
        )
    )

    assert _read_document_date(document_id) is None


def test_extract_does_not_overwrite_explicit_date(
    cleanup_documents: Callable[[UUID], None],
) -> None:
    """人工指定的优先：正文再像也不覆盖人给的值。"""
    document_id = _insert_document(document_date=date(2024, 1, 1))
    cleanup_documents(document_id)
    _place_full_md(document_id, FULL_MD_WITH_DATE)

    asyncio.run(
        document_extract_executor(
            TaskSpec(
                task_type="document.extract",
                payload={"document_id": str(document_id)},
                trace_id=str(uuid4()),
                # A5：org 必填（后台任务没有请求身份，只能由 TaskSpec 携带）
                org_id=get_settings().default_org_id,
            )
        )
    )

    assert _read_document_date(document_id) == date(2024, 1, 1)
