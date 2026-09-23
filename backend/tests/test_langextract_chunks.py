"""抽取切块产物单元测试（Sprint 6 批次 A-1：``chunks.json`` 的写侧输入）。

覆盖 :class:`app.services.extraction.langextract.ExtractedChunk`：

1. 单个 chunk 时区间覆盖全文；
2. ``chunk_id`` 前缀为 ``chunk-``（与 ``agents.py`` 的引用前缀校验对齐）且互不重复；
3. ``to_json_dict()["chunks"]`` 字段齐全，``page`` 默认 ``None``（页码由 A-2 回填）；
4. 多 chunk 时 ``char_start`` / ``char_end`` 是**绝对**偏移且首尾衔接
   （与 :class:`ExtractedEntity` 同坐标系——这是 stage-4 归属的唯一依据）。
"""

from __future__ import annotations

from uuid import uuid4

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
