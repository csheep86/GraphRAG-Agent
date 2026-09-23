"""图谱关系投影语义（Sprint 6.3：真机发现 D4）。

真机实测：抽取产物把**真实语义**写在 ``properties.relation_type``
（``PARTY_TO``），而 Neo4j 的 ``type(r)`` 是通用 token ``RELATION``。
旧实现只看 ``type(r)`` → 未命中契约枚举 → 兜底成 ``MENTIONS``，
于是图谱页与 Prompt 里的所有关系都显示成 ``MENTIONS``（真机污染）。

本文件把「**语义优先、类型兜底、未知才 MENTIONS**」这条顺序钉死。
"""

from __future__ import annotations

from app.services.graphs import _edge_from_record, _relation_type


def test_semantic_relation_type_wins_over_generic_type_token() -> None:
    """``type(r)=RELATION`` + ``relation_type=PARTY_TO`` → 契约上报 ``PARTY_TO``。"""
    assert _relation_type("RELATION", semantic="PARTY_TO") == "PARTY_TO"


def test_type_token_is_used_when_no_semantic_value() -> None:
    """无语义字段（或语义未命中）时沿用 ``type(r)``。"""
    assert _relation_type("HAS_FINANCIAL_INDICATOR") == "HAS_FINANCIAL_INDICATOR"
    assert _relation_type("HAS_CHUNK", semantic=None) == "HAS_CHUNK"
    # 语义值本身不在契约枚举里 → 不生效，回落到 type(r)
    assert _relation_type("SUPPLIES_TO", semantic="某内部代号") == "SUPPLIES_TO"


def test_unknown_falls_back_to_mentions() -> None:
    """两者都未命中 → 兜底 ``MENTIONS``（真实关系名由 properties 承载）。"""
    assert _relation_type("RELATION") == "MENTIONS"
    assert _relation_type("RELATION", semantic="未知语义") == "MENTIONS"


def test_edge_projection_reads_semantic_relation_type() -> None:
    """端到端：一条真机形状的记录（通用 RELATION）必须投影出 ``PARTY_TO``。"""
    edge = _edge_from_record(
        {
            "id": "rel_ef354a4d33d4",
            "type": "RELATION",
            "source": "ent_75dfb6f513eb",
            "target": "ent_e239933fc63c",
            "properties": {"relation_type": "PARTY_TO", "confidence": 0.65},
        }
    )

    assert edge.type == "PARTY_TO"
    assert edge.properties["relation_type"] == "PARTY_TO"
