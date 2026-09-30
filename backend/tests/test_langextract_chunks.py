"""抽取切块产物单元测试（Sprint 6 批次 A-1：``chunks.json`` 的写侧输入）。

覆盖 :class:`app.services.extraction.langextract.ExtractedChunk`：

1. 单个 chunk 时区间覆盖全文；
2. ``chunk_id`` 前缀为 ``chunk-``（与 ``agents.py`` 的引用前缀校验对齐）且互不重复；
3. ``to_json_dict()["chunks"]`` 字段齐全，``page`` 默认 ``None``（页码由 A-2 回填）；
4. 多 chunk 时 ``char_start`` / ``char_end`` 是**绝对**偏移且首尾衔接
   （与 :class:`ExtractedEntity` 同坐标系——这是 stage-4 归属的唯一依据）。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.services.extraction.langextract import LangextractClient


def _client(max_chars: int = 4000) -> LangextractClient:
    return LangextractClient(
        provider="langextract",
        max_chars_per_chunk=max_chars,
        max_entities_per_doc=50,
        max_relations_per_doc=50,
        prompt_version="v1",
        # Sprint 7.0：本文件只验切块，显式落 'mock' 档（默认 'llm' 会真调 LLM）
        engine="mock",
    )


def test_single_chunk_covers_whole_text() -> None:
    """短文本 → 单 chunk，区间为 ``[0, len(text))``。"""
    text = "甲方：北京青云科技有限公司（以下简称甲方）。"

    result = _client().extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.char_start == 0
    assert chunk.char_end == len(text)
    assert chunk.text == text


def test_chunk_ids_use_contract_prefix_and_are_unique() -> None:
    """``chunk_id`` 必须带 ``chunk-`` 前缀（``doc-`` 为文档级降级档）且不重复。"""
    text = "第一句内容。" * 200

    result = _client(max_chars=100).extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )

    assert len(result.chunks) > 1
    for chunk in result.chunks:
        assert chunk.id.startswith("chunk-")
    assert len({chunk.id for chunk in result.chunks}) == len(result.chunks)


def test_chunk_id_is_deterministic_so_reingest_is_idempotent() -> None:
    """同一文档同一段**重跑必须得到同一 chunk_id**（Sprint 10 批次 E）。

    真机教训：id 曾由 ``uuid4()`` 随机生成 ⇒ 同一份制度文档每 ingest 一次就多一套
    ``:Chunk``（写侧 ``MERGE`` 按 id，去重失效）。实测 230 chunks → 去重后 205，
    同一段最多写了 4 次，白白吃掉证据注入名额（``probe_e3_dup.py`` / ``probe_e5_q11.py``）。
    这里把「重跑幂等」钉死：同 (document_id, char_start, text) ⇒ 同 id；
    换文档 ⇒ 换 id（避免把不同文档的同文段落并成一个节点）。
    """
    document_id = uuid4()
    text = "同一段制度正文。" * 30

    first = _client(max_chars=100).extract_entities_relations(
        document_id=document_id, full_md_text=text, trace_id=uuid4()
    )
    second = _client(max_chars=100).extract_entities_relations(
        document_id=document_id, full_md_text=text, trace_id=uuid4()
    )
    other = _client(max_chars=100).extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )

    assert [c.id for c in first.chunks] == [c.id for c in second.chunks], (
        "同文档重跑 chunk_id 变了 ⇒ 重跑 ingest 会再生成一套重复 :Chunk"
    )
    assert [c.id for c in first.chunks] != [c.id for c in other.chunks]


def test_entity_and_relation_ids_are_deterministic() -> None:
    """实体 / 关系 id 也必须**重跑不变**（与 chunk id 同族，Sprint 10 批次 E）。

    id 若仍随机，写侧 ``MERGE`` 按 id 去重就失效 ⇒ 每重跑一次 ingest，图上实体
    多一套。注意判据用**严格口径**（名 + 类型 + 起止偏移），不能按名字判重——
    CSV 里「2026-10-19 正常班」可以是 37 个员工各自的排班，同名不等于重复。
    """
    document_id = uuid4()
    text = "甲方：北京青云科技有限公司。乙方：上海远洋物流有限公司。"

    def run(doc: UUID) -> list[tuple[str, str, str]]:
        result = _client().extract_entities_relations(
            document_id=doc, full_md_text=text, trace_id=uuid4()
        )
        return [
            (e.id, r.id, f"{r.source_entity_id}->{r.target_entity_id}")
            for e in result.entities
            for r in result.relations
        ]

    first = run(document_id)
    second = run(document_id)
    other = run(uuid4())

    assert first == second, "同文档重跑实体/关系 id 变了 ⇒ 重跑 ingest 会重复入库"
    assert first != other, "换文档后 id 未变 ⇒ 会把不同文档的实体并成一个"


def test_chunks_serialized_with_full_field_set() -> None:
    """``chunks.json`` 字段齐全；``page`` 由 A-2 回填前为 ``None``（不伪造 1）。"""
    text = "甲方：北京青云科技有限公司。"

    payload = (
        _client()
        .extract_entities_relations(
            document_id=uuid4(), full_md_text=text, trace_id=uuid4()
        )
        .to_json_dict()
    )

    assert "chunks" in payload
    assert payload["chunks"] == [
        {
            "id": payload["chunks"][0]["id"],
            "char_start": 0,
            "char_end": len(text),
            "text": text,
            "page": None,
        }
    ]


def test_multi_chunk_offsets_are_absolute_and_contiguous() -> None:
    """多 chunk 偏移是**绝对**值（不是块内偏移）且首尾衔接。

    与实体区间同坐标系 → stage-4 可直接用 ``char_start`` 判定归属。
    """
    text = "第一句内容。" * 200  # 1200 字符，max_chars=100 → 多块

    result = _client(max_chars=100).extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )

    assert result.chunks[0].char_start == 0
    for previous, current in zip(result.chunks, result.chunks[1:], strict=False):
        assert current.char_start == previous.char_end, (
            "块内偏移未加回块起点 → 与实体区间不同坐标系，stage-4 会全部误归属"
        )
        assert current.char_start > previous.char_start
    # 每块的 text 必须与所声明区间一致（否则前端高亮会错位）
    for chunk in result.chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text
