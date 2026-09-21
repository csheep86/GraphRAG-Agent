"""LangextractClient 单元测试（Sprint 5 批次 B：document.extract 输入源）。

覆盖 :mod:`app.services.extraction.langextract`：

1. mockable 默认路径（正则占位抽取器，零外部依赖）；
2. ``extraction_max_*`` 上限裁剪（confidence 降序）；
3. 关系端点漂移丢弃（与 Neo4j stage-3 MATCH 语义一致）；
4. chunk 切分与 char_offset 反推；
5. 未知 provider / 非法上限 / 空输入 → :class:`LangextractError`；
6. trace_id / document_id 透传。

真实 LLM 调用留位（``extraction_provider`` 别档显式报错），不在本模块范围。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.extraction import (
    ExtractionResult,
    LangextractClient,
    LangextractError,
)
from app.services.extraction.langextract import (
    ExtractedEntity,
    ExtractedRelation,
    _default_extract_chunk,
    _split_into_chunks,
)

_TEXT = (
    "甲方：北京青云科技有限公司。乙方：上海临港智能装备有限公司。"
    "2024 年营业收入为人民币 12.34 亿元。"
)


def _client(**overrides: object) -> LangextractClient:
    kwargs: dict[str, object] = {
        "provider": "langextract",
        "max_chars_per_chunk": 4000,
        "max_entities_per_doc": 500,
        "max_relations_per_doc": 1000,
        "prompt_version": "kg_extraction_v1",
    }
    kwargs.update(overrides)
    return LangextractClient(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 构造校验
# --------------------------------------------------------------------------- #


def test_unknown_provider_raises() -> None:
    with pytest.raises(LangextractError, match="extraction_provider"):
        _client(provider="openai_github_copilot")


def test_invalid_chunk_size_raises() -> None:
    with pytest.raises(LangextractError, match="max_chars_per_chunk"):
        _client(max_chars_per_chunk=0)


def test_invalid_clamp_limits_raise() -> None:
    with pytest.raises(LangextractError, match="max_entities_per_doc"):
        _client(max_entities_per_doc=-1)


def test_empty_input_raises() -> None:
    client = _client()
    with pytest.raises(LangextractError, match="full.md 为空"):
        client.extract_entities_relations(
            document_id=uuid4(), full_md_text="   \n  ", trace_id=uuid4()
        )


# --------------------------------------------------------------------------- #
# mockable 默认路径
# --------------------------------------------------------------------------- #


def test_default_extractor_finds_org_entities() -> None:
    """默认正则抽取器：中文机构名 → ORG；两个 ORG → PARTY_TO 关系。"""
    entities, relations = _default_extract_chunk(_TEXT, 0)

    orgs = [e for e in entities if e.entity_type == "ORG"]
    names = {e.canonical_name for e in orgs}
    assert "北京青云科技有限公司" in names
    assert "上海临港智能装备有限公司" in names
    assert len(relations) == 1
    assert relations[0].relation_type == "PARTY_TO"


def test_extract_entities_relations_roundtrip() -> None:
    client = _client()
    document_id, trace_id = uuid4(), uuid4()

    result = client.extract_entities_relations(
        document_id=document_id, full_md_text=_TEXT, trace_id=trace_id
    )

    assert isinstance(result, ExtractionResult)
    assert result.document_id == document_id
    assert result.trace_id == trace_id
    assert result.entities, "至少应抽到 ORG 实体"
    assert all(e.char_start < e.char_end for e in result.entities)
    # char_start/end 指向原文
    for entity in result.entities:
        assert _TEXT[entity.char_start : entity.char_end] == entity.mention


# --------------------------------------------------------------------------- #
# 上限裁剪
# --------------------------------------------------------------------------- #


def test_entity_clamp_keeps_highest_confidence() -> None:
    client = _client(max_entities_per_doc=1)
    result = client.extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert len(result.entities) == 1
    # ORG 置信度 0.85 高于 DATE 0.7
    assert result.entities[0].entity_type == "ORG"


def test_relation_clamp_drops_dangling_endpoints() -> None:
    """关系端点不在实体集合内 → 丢弃（stage-3 MATCH 语义前置）。"""
    bogus = ExtractedRelation(
        id="rel_bogus",
        source_entity_id="ent_missing",
        target_entity_id="ent_also_missing",
        relation_type="RELATED",
        evidence="dangling",
        confidence=0.99,
    )

    def extractor(
        text: str, offset: int
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        entities, relations = _default_extract_chunk(text, offset)
        return entities, relations + [bogus]

    client = _client(chunk_extractor=extractor)
    result = client.extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert "rel_bogus" not in {r.id for r in result.relations}


# --------------------------------------------------------------------------- #
# chunk 切分
# --------------------------------------------------------------------------- #


def test_short_text_single_chunk() -> None:
    assert _split_into_chunks("短文本", 4000) == [(0, "短文本")]


def test_long_text_offsets_cover_whole_document() -> None:
    text = "句子。".join(["这是一段用于测试切分逻辑的文本"] * 40)
    chunks = _split_into_chunks(text, 100)

    assert len(chunks) > 1
    # 重建全文：offset + 片段拼接无损
    rebuilt = "".join(text[offset : offset + len(chunk)] for offset, chunk in chunks)
    assert rebuilt == text
    assert sum(len(chunk) for _, chunk in chunks) == len(text)


def test_extractor_receives_chunk_offsets() -> None:
    """注入的抽取器收到正确的 char_offset（供 char_start 反推全局位置）。"""
    text = "北京青云科技有限公司。" * 50  # 远超 100 字符
    seen_offsets: list[int] = []

    def recorder(
        chunk: str, offset: int
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        seen_offsets.append(offset)
        assert text[offset : offset + len(chunk)] == chunk
        return [], []

    client = _client(
        max_chars_per_chunk=100,
        chunk_extractor=recorder,
    )
    client.extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )
    assert seen_offsets[0] == 0
    assert len(seen_offsets) > 1
