"""kg_extraction_v1 模板 + E1/E2 评测 fixture 测试（Sprint 5 批次 B）。

覆盖：
1. 模板经 :mod:`app.prompts.prompt_loader` 从文件系统加载（禁止硬编码）；
2. 占位符 ``{{text}}`` / ``{{language}}`` 声明齐全、渲染无损；
3. 评测 fixture（``eval_e1.jsonl`` / ``eval_e2.jsonl``）可解析且 ≥ 2 条；
4. E1：mockable 抽取器在 fixture 文本上命中期望实体类型；
5. E2：双 ORG 共现产生 PARTY_TO 关系（评测基线口径）。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.prompts.prompt_loader import load_prompt
from app.services.extraction.langextract import _default_extract_chunk

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> list[dict[str, object]]:
    lines = (FIXTURES_DIR / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# --------------------------------------------------------------------------- #
# 模板
# --------------------------------------------------------------------------- #


def test_template_loads_from_filesystem() -> None:
    template = load_prompt("kg_extraction", version=1)
    assert template.version == 1
    assert template.path.name == "kg_extraction_v1.md"
    assert template.raw, "模板不得为空"


def test_template_declares_text_and_language_placeholders() -> None:
    template = load_prompt("kg_extraction", version=1)
    assert set(template.placeholders) == {"text", "language"}


def test_template_render_roundtrip() -> None:
    rendered = load_prompt("kg_extraction", version=1).render(
        text="甲方：北京青云科技有限公司。",
        language="chinese",
    )
    assert "北京青云科技有限公司" in rendered
    assert "{{" not in rendered and "}}" not in rendered


# --------------------------------------------------------------------------- #
# 评测 fixture
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture_name", ["eval_e1.jsonl", "eval_e2.jsonl"])
def test_fixture_has_at_least_two_samples(fixture_name: str) -> None:
    records = _load_fixture(fixture_name)
    assert len(records) >= 2
    assert all(record.get("text") for record in records)


def test_e1_fixture_entities_hit_by_mockable_extractor() -> None:
    """E1 基线：默认抽取器在每条 fixture 上命中全部期望实体。"""
    for record in _load_fixture("eval_e1.jsonl"):
        entities, _ = _default_extract_chunk(str(record["text"]), 0)
        got = {(e.canonical_name, e.entity_type) for e in entities}
        for expected in record["expected_entities"]:  # type: ignore[index]
            name = str(expected["canonical_name"])
            entity_type = str(expected["entity_type"])
            assert (name, entity_type) in got, (
                f"fixture {record['id']}: 期望实体 {name}({entity_type}) 未命中，"
                f"实际 {sorted(got)}"
            )


def test_e2_fixture_relations_hit_by_mockable_extractor() -> None:
    """E2 基线：双 ORG 共现 → PARTY_TO，端点与期望一致。"""
    for record in _load_fixture("eval_e2.jsonl"):
        entities, relations = _default_extract_chunk(str(record["text"]), 0)
        name_by_id = {e.id: e.canonical_name for e in entities}
        got = {
            (name_by_id.get(r.source_entity_id), name_by_id.get(r.target_entity_id))
            for r in relations
        }
        for expected in record["expected_relations"]:  # type: ignore[index]
            source = str(expected["source_contains"])
            target = str(expected["target_contains"])
            assert any(s and t and source in s and target in t for s, t in got), (
                f"fixture {record['id']}: 期望关系 {source}→{target} 未命中，实际 {got}"
            )


def test_extraction_result_shape_matches_prompt_schema() -> None:
    """mockable 抽取产物结构与模板 JSON Schema 字段一一对应。"""
    from app.services.extraction import LangextractClient

    client = LangextractClient(
        provider="langextract",
        max_chars_per_chunk=4000,
        max_entities_per_doc=500,
        max_relations_per_doc=1000,
        prompt_version="kg_extraction_v1",
        # Sprint 7.0：本文件只验产物结构与模板 Schema 对齐，显式落 'mock' 档
        engine="mock",
    )
    result = client.extract_entities_relations(
        document_id=uuid4(),
        full_md_text="甲方：北京青云科技有限公司。乙方：上海临港智能装备有限公司。",
        trace_id=uuid4(),
    )
    payload = result.to_json_dict()
    entity_fields = set(payload["entities"][0])  # type: ignore[index]
    relation_fields = set(payload["relations"][0])  # type: ignore[index]
    assert entity_fields == {
        "id",
        "canonical_name",
        "entity_type",
        "mention",
        "char_start",
        "char_end",
        "confidence",
    }
    assert relation_fields == {
        "id",
        "source_entity_id",
        "target_entity_id",
        "relation_type",
        "evidence",
        "confidence",
    }
