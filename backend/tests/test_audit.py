"""Sprint 8.1 批次 A：审计最小闭环（M5 §3 验收 2 / 6 / 7 + M3 §4.3 `qa_logs`）。

钉死四条纪律：

1. **审计由中间件全量写**（决策 **A1**）：每个 `/api/v1/*` 请求一条，`health` 除外；
2. **写失败不拖垮主流程**（proposal 风险 2）：审计写失败时业务响应码不变；
3. **只写结构化字段**（决策 **A5**）：`detail` 不含响应体原文；
4. **问答成功 / 拒答都落 `qa_logs`**（决策 **A4**），且 `question_hash` 不是原文。

外部依赖（Neo4j / LLM）全部打桩，与 `test_agent_citations.py` 同口径。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog, QaLog
from app.db.session import SessionLocal
from app.schemas.agent import AgentQueryRequest
from app.schemas.document import GraphNode
from app.services.agents import AgentService
from app.services.graphs import EvidenceChunk, GraphService, KgVersion

# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #


@pytest.fixture
def empty_audit_log() -> None:
    """清空 `audit_log` —— 审计是全站中间件写的，不清空就无法断言「本次请求」的条数。"""
    with SessionLocal() as session:
        session.query(AuditLog).delete()
        session.query(QaLog).delete()
        session.commit()


def _audit_rows() -> list[AuditLog]:
    with SessionLocal() as session:
        return list(session.scalars(select(AuditLog).order_by(AuditLog.ts)).all())


def _qa_rows() -> list[QaLog]:
    with SessionLocal() as session:
        return list(session.scalars(select(QaLog)).all())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


#: `qa_logs.trace_id` 是 UUID 列，故用真实 UUID 字符串（与生产链路同形）
TRACE_ANSWERED = str(uuid4())
TRACE_REFUSED = str(uuid4())
TRACE_BROKEN = str(uuid4())


# --------------------------------------------------------------------------- #
# 中间件写入（M5 §3 验收 2）
# --------------------------------------------------------------------------- #


def test_api_request_writes_exactly_one_row(
    client: TestClient, dev_headers: dict[str, str], empty_audit_log: None
) -> None:
    """每个 `/api/v1/*` 请求落一条，带 trace_id / org_id / action（决策 A1 + A2）。"""
    response = client.get("/api/v1/documents", headers=dev_headers)

    assert response.status_code == 200
    rows = _audit_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "document.list"
    assert row.status == "success"
    assert row.org_id == get_settings().default_org_id
    assert str(row.trace_id) == response.headers["X-Trace-Id"]
    # decision A5：detail 只放结构化字段，**不含**响应体（文档列表）原文
    assert row.detail is not None
    assert row.detail["status_code"] == 200
    assert "filename_hash" not in json.dumps(row.detail, ensure_ascii=False)


def test_health_is_excluded_by_allowlist(
    client: TestClient, empty_audit_log: None
) -> None:
    """allowlist 排除 `health`：探针噪声不进审计表（决策 A1），否则演示页会被撑爆。"""
    assert client.get("/api/v1/health").status_code == 200

    assert _audit_rows() == []


def test_failed_request_is_audited_as_failure(
    client: TestClient, dev_headers: dict[str, str], empty_audit_log: None
) -> None:
    """404 / 4xx 也**必须**留痕，且 `status = failure`（M5 §3 验收 2 的「成功 / 失败」两侧）。"""
    response = client.get(f"/api/v1/documents/{uuid4()}/status", headers=dev_headers)

    assert response.status_code == 404
    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0].status == "failure"
    assert rows[0].action == "document.status"
    assert rows[0].doc_id is not None


def test_audit_write_failure_does_not_break_response(
    client: TestClient,
    dev_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    empty_audit_log: None,
) -> None:
    """审计写失败 → **只记日志**，业务照常返回（proposal 风险 2：不得变成全站 500）。"""

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit table is on fire")

    monkeypatch.setattr("app.services.audit.record_audit_entry", boom)

    response = client.get("/api/v1/documents", headers=dev_headers)

    assert response.status_code == 200
    assert _audit_rows() == []


def test_unauthenticated_request_is_skipped_not_fabricated(
    client: TestClient, empty_audit_log: None
) -> None:
    """拿不到身份时不写审计：**不**拿默认 org_id 顶替（org_id 是隔离键，不能填空）。"""
    response = client.get("/api/v1/documents")

    assert response.status_code == 401
    assert _audit_rows() == []


# --------------------------------------------------------------------------- #
# 两个只读端点（M5 §3 验收 7 / 6）
# --------------------------------------------------------------------------- #


def test_list_audit_returns_own_tenant_rows_only(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
    empty_audit_log: None,
) -> None:
    """租户隔离：跨租户查询返回**空集**，不是错误也不是别人的数据（ADR-0003）。"""
    assert client.get("/api/v1/documents", headers=dev_headers).status_code == 200

    own = client.get("/api/v1/audit", headers=dev_headers)
    assert own.status_code == 200
    assert own.json()["total"] >= 1

    other = client.get("/api/v1/audit", headers=cross_tenant_headers)
    assert other.status_code == 200
    assert other.json()["items"] == []


def test_list_audit_defaults_to_ts_desc_and_page_size_50(
    client: TestClient,
    dev_headers: dict[str, str],
    empty_audit_log: None,
) -> None:
    """M5 §3 验收 7 原文口径：默认 `ts DESC`、页大小 50。

    种子行刻意打**过去**的时间戳：本请求自身的审计行（`audit.list`）的时间是「现在」，
    若把种子打到未来，DESC 的首行会是那条自举行，断言就失去意义。
    """
    base = datetime.now(UTC)
    with SessionLocal() as session:
        for offset in range(3):
            session.add(
                AuditLog(
                    org_id=get_settings().default_org_id,
                    ts=base - timedelta(minutes=3 - offset),
                    action=f"document.seed{offset}",
                    actor_id=get_settings().default_actor_id,
                    actor_ip="127.0.0.1",
                    resource="GET /api/v1/documents",
                    status="success",
                    trace_id=uuid4(),
                )
            )
        session.commit()

    # 先跑分页请求：它是本次第一批请求，响应里只有 3 条种子
    # （自己的 `audit.list` 行在本请求**之后**才写入，见契约 description 的自举说明）
    paged = client.get("/api/v1/audit?page_size=2", headers=dev_headers).json()
    assert paged["total"] == 3
    assert len(paged["items"]) == 2
    # ts 最大的是 seed2（base - 1min）—— 它排在最前，证明是 DESC 而非 ASC
    assert paged["items"][0]["action"] == "document.seed2"

    payload = client.get("/api/v1/audit", headers=dev_headers).json()
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    timestamps = [item["ts"] for item in payload["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_list_audit_rejects_invalid_status_filter(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """非法 `status` 是 400 `VALIDATION_ERROR`，**不**静默当「全不过滤」。"""
    response = client.get("/api/v1/audit?status=maybe", headers=dev_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_trace_endpoint_replays_one_request_chain(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
    empty_audit_log: None,
) -> None:
    """按 trace 回看任一步（plan §7.2 步骤 6）；跨租户为空集。**不支持分页**。"""
    response = client.get("/api/v1/documents", headers=dev_headers)
    trace_id = response.headers["X-Trace-Id"]

    replayed = client.get(f"/api/v1/audit/trace/{trace_id}", headers=dev_headers)
    assert replayed.status_code == 200
    body = replayed.json()
    assert body["trace_id"] == trace_id
    assert body["total"] == 1
    assert body["items"][0]["action"] == "document.list"
    assert "page" not in body

    cross = client.get(f"/api/v1/audit/trace/{trace_id}", headers=cross_tenant_headers)
    assert cross.status_code == 200
    assert cross.json()["items"] == []


# --------------------------------------------------------------------------- #
# qa_logs（M3 §4.3，决策 A4）
# --------------------------------------------------------------------------- #


def _patch_agent(monkeypatch: pytest.MonkeyPatch, *, llm_answer: str) -> None:
    """打桩 LLM / Neo4j，与 `test_agent_citations.py::_patch_pipeline` 同口径。"""
    nodes = [
        GraphNode(
            id="e1",
            label="Entity",
            entity_type="公司",
            canonical_name="北京青云科技有限公司",
            confidence=0.9,
            kg_version="v-test",
        )
    ]
    monkeypatch.setattr(
        GraphService,
        "fetch_active_kg_version",
        lambda self, **kwargs: KgVersion(version="v-test", scope="global"),
    )
    monkeypatch.setattr(
        GraphService, "fetch_all_subgraph", lambda self, **kwargs: (nodes, [], False)
    )
    monkeypatch.setattr(
        GraphService, "validate_kg_version_tenant_boundary", lambda self, **kwargs: True
    )
    monkeypatch.setattr(
        GraphService,
        "fetch_evidence_chunks",
        lambda self, **kwargs: [
            EvidenceChunk(
                chunk_id="chunk-581e8912827d",
                doc_id=UUID("11111111-2222-3333-4444-555555555555"),
                text="甲方：北京青云科技有限公司。",
                page=3,
                char_start=0,
                char_end=64,
            )
        ],
    )
    monkeypatch.setattr(AgentService, "_ensure_chat", lambda self: None)

    async def fake_invoke(self: AgentService, **kwargs: object) -> tuple[str, None]:
        return llm_answer, None

    monkeypatch.setattr(AgentService, "_invoke_chat_with_retry", fake_invoke)


def _answered_json(evidence: list[str]) -> str:
    return json.dumps(
        {
            "answer": "甲方是北京青云科技有限公司。",
            "evidence": evidence,
            "confidence": "high",
        },
        ensure_ascii=False,
    )


def test_qa_log_records_answered_query(
    monkeypatch: pytest.MonkeyPatch, empty_audit_log: None
) -> None:
    """成功回答落一条 `qa_logs`：字段取自响应体，**提问只留哈希**（M3 §5.3）。"""
    _patch_agent(monkeypatch, llm_answer=_answered_json(["chunk-581e8912827d"]))
    question = "甲方是谁？这家公司的合同金额是多少？"

    with SessionLocal() as session:
        response = asyncio.run(
            AgentService.instance().query(
                request=AgentQueryRequest(question=question),
                org_id=get_settings().default_org_id,
                trace_id=TRACE_ANSWERED,
                db=session,
            )
        )

    assert response.refused is False
    rows = _qa_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.question_hash == _sha256(question)
    assert question not in row.question_hash  # 不是原文（长度也不对）
    assert row.answer_hash == _sha256(response.answer)
    assert row.citation_count == 1
    assert row.refused is False
    assert row.refusal_reason is None
    assert row.kg_version == "v-test"
    assert str(row.trace_id) == TRACE_ANSWERED


def test_qa_log_records_refused_query(
    monkeypatch: pytest.MonkeyPatch, empty_audit_log: None
) -> None:
    """拒答**同样**落一条（M3 §5.3：被拒答的问题集合是本体补全的输入）。"""
    _patch_agent(monkeypatch, llm_answer=_answered_json(["chunk-unknown00000"]))

    with SessionLocal() as session:
        response = asyncio.run(
            AgentService.instance().query(
                request=AgentQueryRequest(question="经营范围有哪些？"),
                org_id=get_settings().default_org_id,
                trace_id=TRACE_REFUSED,
                db=session,
            )
        )

    assert response.refused is True
    rows = _qa_rows()
    assert len(rows) == 1
    assert rows[0].refused is True
    assert rows[0].refusal_reason == "no_grounded_evidence"
    assert rows[0].citation_count == 0


def test_qa_log_write_failure_does_not_break_answer(
    monkeypatch: pytest.MonkeyPatch, empty_audit_log: None
) -> None:
    """打点失败不得把已算好的答案变成 500（同 proposal 风险 2 的纪律）。"""
    _patch_agent(monkeypatch, llm_answer=_answered_json(["chunk-581e8912827d"]))

    class _BrokenSession:
        """任何写操作都失败的会话替身（模拟 pg 写入故障）。"""

        def add(self, *_: object) -> None:
            raise RuntimeError("qa_logs insert failed")

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="甲方是谁？"),
            org_id=get_settings().default_org_id,
            trace_id=TRACE_BROKEN,
            db=_BrokenSession(),
        )
    )

    assert response.refused is False
    assert _qa_rows() == []
