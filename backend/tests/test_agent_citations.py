"""Sprint 6 批次 B：引用回查链路（`_to_citation` 真实化 + 证据片段注入）。

钉死 F3（引用覆盖率 100%）的两条铁律与 Q1 / Q2 拍板口径：

1. 引用必须能回查到**本轮注入 Prompt 的证据片段**，回查不到的条目一律丢弃——
   LLM 编造的 `chunk_id` **不得**进入 `citations`；
2. 页码失配给 `None`（**严禁**兜底伪造 1）；
3. chunk 全文**不**进 `Citation`（`snippet` 只带摘录），
   全文由 `GET /documents/{id}/chunks/{chunk_id}` 按需回查。

外部依赖（Neo4j / LLM）全部打桩，与 `test_graph_and_agent_routes.py` 同口径。
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import pytest

from app.schemas.agent import AgentQueryRequest, TokenUsage
from app.schemas.document import GraphEdge, GraphNode
from app.services.agents import (
    AgentService,
    AgentUnavailableError,
    _build_citations,
    _serialize_chunks,
    _snippet,
    _to_citation,
)
from app.services.graphs import (
    EvidenceChunk,
    GraphService,
    GraphUnavailableError,
    KgVersion,
)

DOC_ID = UUID("11111111-2222-3333-4444-555555555555")
CHUNK_ID = "chunk-581e8912827d"
CHUNK_TEXT = "甲方：北京青云科技有限公司（以下简称甲方）。"


def _chunk(
    *, chunk_id: str = CHUNK_ID, page: int | None = 3, doc_id: UUID | None = DOC_ID
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=CHUNK_TEXT,
        page=page,
        char_start=0,
        char_end=764,
    )


def _index(*chunks: EvidenceChunk) -> dict[str, EvidenceChunk]:
    return {chunk.chunk_id: chunk for chunk in chunks}


# --------------------------------------------------------------------------- #
# `_to_citation` / `_build_citations` 单元
# --------------------------------------------------------------------------- #


def test_to_citation_resolves_real_fields() -> None:
    """批次 B 核心：引用回填真实 doc_id / page / chunk_id / snippet（骨架版的占位全部作废）。"""
    citation = _to_citation(CHUNK_ID, _index(_chunk()))

    assert citation is not None
    assert citation.doc_id == DOC_ID
    assert citation.page == 3
    assert citation.chunk_id == CHUNK_ID
    assert citation.char_offset == 0
    assert citation.snippet == CHUNK_TEXT


def test_to_citation_page_is_none_when_mismatched() -> None:
    """Q1：页码失配（content_list 对齐失败）→ `null`，**不**伪造 1。"""
    citation = _to_citation(
        "chunk-abc0001", _index(_chunk(chunk_id="chunk-abc0001", page=None))
    )

    assert citation is not None
    assert citation.page is None


def test_to_citation_returns_none_when_chunk_not_injected() -> None:
    """LLM 编造的 `chunk_id` → 不可溯源 → 丢弃（F3：宁可拒答也不给假引用）。"""
    assert _to_citation("chunk-deadbeef0000", _index(_chunk())) is None


def test_to_citation_returns_none_when_chunk_has_no_document() -> None:
    """chunk 未挂 `:Document` → `doc_id` 无从得知，丢弃而非回落 `UUID(int=0)` 占位。"""
    orphan = _chunk(chunk_id="chunk-orphan0001", page=None, doc_id=None)

    assert _to_citation("chunk-orphan0001", _index(orphan)) is None


def test_to_citation_returns_none_when_item_has_no_chunk_id() -> None:
    """仅含 `doc-` 的旧式证据条目：本批次不解析（批次 B 只认 `chunk-` 前缀）。"""
    assert _to_citation("doc-9/page-3/chunk-12", _index(_chunk())) is None


def test_build_citations_drops_non_chunk_items() -> None:
    citations = _build_citations(
        [CHUNK_ID, "doc-9/page-3", "chunk-deadbeef0000"], _index(_chunk())
    )

    assert len(citations) == 1
    assert citations[0].chunk_id == CHUNK_ID


# --------------------------------------------------------------------------- #
# 摘录与序列化
# --------------------------------------------------------------------------- #


def test_snippet_is_truncated_with_ellipsis() -> None:
    """Q2：snippet 只带摘录（≤ 200 字），chunk 全文不进 `citations`。"""
    snippet = _snippet("甲" * 500)

    assert len(snippet) == 201  # 200 字 + 省略号
    assert snippet.endswith("…")
    assert snippet.startswith("甲")


def test_serialize_chunks_empty_marker() -> None:
    """无证据片段时给显式空标记：让 LLM 明确「没有原文」，**不**留白。"""
    assert _serialize_chunks([]) == "<chunks: empty>"


def test_serialize_chunks_exposes_id_page_and_range() -> None:
    serialized = _serialize_chunks(
        [_chunk(), _chunk(chunk_id="chunk-abc0002", page=None)]
    )

    assert CHUNK_ID in serialized
    assert "page=3" in serialized
    assert "chars=[0,764)" in serialized
    # 页码失配显式渲染为 unknown，避免 LLM 自行脑补页码
    assert "page=unknown" in serialized


# --------------------------------------------------------------------------- #
# 端到端（服务层，LLM / Neo4j 打桩）
# --------------------------------------------------------------------------- #


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunks: list[EvidenceChunk],
    llm_answer: str,
    llm_usage: TokenUsage | None = None,
    evidence_chunks_boom: bool = False,
) -> dict[str, str]:
    """打桩 `AgentService` 内部依赖，并截获实际送出的 `system_prompt`。

    :param evidence_chunks_boom: 模拟 Neo4j 在证据片段查询阶段挂掉（应 → 501）
    """
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
    edges: list[GraphEdge] = []

    monkeypatch.setattr(
        GraphService,
        "fetch_active_kg_version",
        lambda self, scope=None, **kwargs: KgVersion(version="v-test", scope="global"),
    )
    monkeypatch.setattr(
        GraphService, "fetch_all_subgraph", lambda self, **kwargs: (nodes, edges, False)
    )
    monkeypatch.setattr(
        GraphService, "validate_kg_version_tenant_boundary", lambda self, **kwargs: True
    )
    monkeypatch.setattr(AgentService, "_ensure_chat", lambda self: None)

    if evidence_chunks_boom:

        def boom(self: GraphService, **kwargs: object) -> list[EvidenceChunk]:
            raise GraphUnavailableError("connection refused")

        monkeypatch.setattr(GraphService, "fetch_evidence_chunks", boom)
    else:
        monkeypatch.setattr(
            GraphService, "fetch_evidence_chunks", lambda self, **kwargs: list(chunks)
        )

    seen: dict[str, str] = {}

    async def fake_invoke(
        self: AgentService, **kwargs: object
    ) -> tuple[str, TokenUsage | None]:
        seen["system_prompt"] = str(kwargs.get("system_prompt", ""))
        return llm_answer, llm_usage

    monkeypatch.setattr(AgentService, "_invoke_chat_with_retry", fake_invoke)
    return seen


def _llm_answer(evidence: list[str]) -> str:
    return json.dumps(
        {
            "answer": "甲方是北京青云科技有限公司。",
            "evidence": evidence,
            "confidence": "high",
        },
        ensure_ascii=False,
    )


def test_query_injects_chunk_text_and_cites_real_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """批次 B 主线：chunk 原文进入 Prompt，引用回填真实 doc_id / page。"""
    seen = _patch_pipeline(
        monkeypatch, chunks=[_chunk()], llm_answer=_llm_answer([CHUNK_ID])
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="甲方是谁？"),
            org_id=uuid4(),
            trace_id="t-batch-b-ok",
        )
    )

    # Prompt 侧：证据片段已注入（非空占位符）
    # （不能用 `"<chunks: empty>" not in prompt` —— Prompt 正文里就有这条指令文案）
    assert "<chunks count=1>" in seen["system_prompt"]
    assert CHUNK_ID in seen["system_prompt"]
    assert CHUNK_TEXT in seen["system_prompt"]

    # 响应侧：真实引用（骨架版的 doc_id=UUID(int=0) / page=1 不再出现）
    assert response.refused is False
    assert len(response.citations) == 1
    citation = response.citations[0]
    assert citation.chunk_id == CHUNK_ID
    assert citation.doc_id == DOC_ID
    assert citation.page == 3
    assert citation.snippet == CHUNK_TEXT


def test_query_refuses_when_llm_cites_unknown_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 引用了未注入的 chunk → 引用覆盖率 0 → 拒答（F3），绝不返回假引用。"""
    _patch_pipeline(
        monkeypatch, chunks=[_chunk()], llm_answer=_llm_answer(["chunk-deadbeef0000"])
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="甲方是谁？"),
            org_id=uuid4(),
            trace_id="t-batch-b-hallucinated",
        )
    )

    assert response.refused is True
    assert response.refusal_reason == "no_grounded_evidence"
    assert response.citations == []


def test_query_501_when_evidence_chunks_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neo4j 在证据片段阶段挂掉 → AgentUnavailableError（路由 501）。

    **不**降级为「无片段」：空片段会让 LLM 无从引用，把基础设施故障伪装成正常拒答。
    """
    _patch_pipeline(
        monkeypatch,
        chunks=[_chunk()],
        llm_answer=_llm_answer([CHUNK_ID]),
        evidence_chunks_boom=True,
    )

    with pytest.raises(AgentUnavailableError):
        asyncio.run(
            AgentService.instance().query(
                request=AgentQueryRequest(question="甲方是谁？"),
                org_id=uuid4(),
                trace_id="t-batch-b-boom",
            )
        )


def test_ensure_chat_builds_model_without_undefined_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真机反哺回归：LLM 装配**不**再引用未定义的 ``ChatOpenAI`` 名字。

    2026-09-22 真机 ``POST /api/v1/agent/query`` 返回 500
    （``NameError: name 'ChatOpenAI' is not defined``）：``ChatOpenAI`` 只在
    ``except`` 分支被赋 ``None``，导入**成功**时该名字从未定义；而单测把 LLM
    全打桩、该分支永远走不到——只能由真机暴露。本例**真调** ``_ensure_chat``
    （只打桩 ``build_chat_model``），把该缺陷钉在单测层。
    """
    pytest.importorskip("langchain_openai", reason="装配链路需 langchain 可导入")

    from app.core.config import get_settings
    from app.services import agents as agents_module

    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key", raising=False)
    monkeypatch.setattr(agents_module, "build_chat_model", lambda: object())

    # 未打桩 _ensure_chat：命中即证明不再 NameError（否则会冒泡成 500）
    assert AgentService.instance()._ensure_chat() is not None
