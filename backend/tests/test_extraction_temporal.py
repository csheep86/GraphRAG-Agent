"""Sprint 9 批次 A：抽取侧**知识时效**（ADR-0005 §4 / §6 L0，零外部依赖，注入假 LLM）。

覆盖三件事：

1. **Prompt v3** 声明 ``{{document_date}}``，且渲染时拿到**真实文档日期**；
   日期未知 ⇒ 渲染为 ``"unknown"``（不代填今天——R4 不猜值）；
2. **关系时态字段** ``valid_from`` / ``valid_to`` 被解析、进产物 JSON；
   **格式非法只丢时态字段、不丢关系**（召回率比日期格式重要）；
3. **v2 文件未被修改**（只增不改，CODEBUDDY.md「Prompt 版本管理规范」）。

真机抽取值不在这里验（见 ``changes/Sprint9/integration-log.md``）。
"""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import app.services.extraction.langextract as lx
from app.prompts.prompt_loader import load_prompt
from app.services.extraction import LangextractClient

_TEXT = "发行人：北京青云科技有限公司，法定代表人：张三。"

_PAYLOAD: dict[str, object] = {
    "entities": [
        {
            "id": "ent_001",
            "canonical_name": "北京青云科技有限公司",
            "entity_type": "ORG",
            "mention": "北京青云科技有限公司",
            "confidence": 0.95,
        },
        {
            "id": "ent_002",
            "canonical_name": "张三",
            "entity_type": "LEGAL_PERSON",
            "mention": "张三",
            "confidence": 0.93,
        },
    ],
    "relations": [
        {
            "id": "rel_001",
            "source_entity_id": "ent_001",
            "target_entity_id": "ent_002",
            "relation_type": "LEGAL_REP",
            "evidence": "法定代表人：张三",
            "confidence": 0.92,
            "valid_from": "2025-05-01",
            "valid_to": None,
        },
    ],
}


def _client(**overrides: object) -> LangextractClient:
    kwargs: dict[str, object] = {
        "provider": "langextract",
        "max_chars_per_chunk": 4000,
        "max_entities_per_doc": 500,
        "max_relations_per_doc": 1000,
        "prompt_version": "kg_extraction_v3",
        "engine": "llm",
    }
    kwargs.update(overrides)
    return LangextractClient(**kwargs)  # type: ignore[arg-type]


def _invoker_capturing(payload: object, seen: list[str]) -> lx.LlmInvokerFn:
    def _invoke(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps(payload, ensure_ascii=False)

    return _invoke


# --------------------------------------------------------------------------- #
# 1. Prompt v3：document_date 注入 / unknown 兜底
# --------------------------------------------------------------------------- #


def test_v3_declares_document_date_placeholder() -> None:
    template = load_prompt("kg_extraction", version=3)
    assert template.path.name == "kg_extraction_v3.md"
    assert "document_date" in template.placeholders


def test_v2_is_untouched() -> None:
    """v3 是**新增**版本，v2 一个字都不许动（Prompt 版本管理规范）。"""
    template = load_prompt("kg_extraction", version=2)
    assert "document_date" not in template.placeholders


def test_document_date_rendered_into_prompt() -> None:
    seen: list[str] = []
    _client(
        llm_invoker=_invoker_capturing(_PAYLOAD, seen),
        document_date=date(2025, 6, 30),
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert len(seen) == 1
    assert "2025-06-30" in seen[0]


def test_unknown_document_date_is_not_backfilled() -> None:
    """日期未知 ⇒ 渲染 ``"unknown"``，**不**用今天填（假日期比没日期危险）。"""
    seen: list[str] = []
    _client(llm_invoker=_invoker_capturing(_PAYLOAD, seen)).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert "unknown" in seen[0]


# --------------------------------------------------------------------------- #
# 2. 关系时态字段
# --------------------------------------------------------------------------- #


def test_temporal_fields_parsed_and_exported() -> None:
    result = _client(
        llm_invoker=_invoker_capturing(_PAYLOAD, [])
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    relation = result.relations[0]
    assert (relation.valid_from, relation.valid_to) == ("2025-05-01", None)

    exported = result.to_json_dict()["relations"][0]  # type: ignore[index]
    assert exported["valid_from"] == "2025-05-01"
    assert exported["valid_to"] is None


def test_invalid_date_drops_field_but_keeps_relation() -> None:
    """中文 / 残缺日期 ⇒ 只丢时态字段，**关系本体必须留下**。"""
    payload = json.loads(json.dumps(_PAYLOAD, ensure_ascii=False))
    payload["relations"][0]["valid_from"] = "2025年5月"

    result = _client(
        llm_invoker=_invoker_capturing(payload, [])
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert len(result.relations) == 1
    assert result.relations[0].valid_from is None


def test_missing_dates_default_to_none() -> None:
    """模型没给时态字段 ⇒ None（**不得**解读为"今天生效"）。"""
    payload = json.loads(json.dumps(_PAYLOAD, ensure_ascii=False))
    del payload["relations"][0]["valid_from"]
    del payload["relations"][0]["valid_to"]

    result = _client(
        llm_invoker=_invoker_capturing(payload, [])
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    relation = result.relations[0]
    assert (relation.valid_from, relation.valid_to) == (None, None)


def test_mock_engine_relations_have_no_temporal_fields() -> None:
    """mock 引擎（CI 占位器）不生产时态字段——它不代表真实抽取质量。

    用**两个 ORG** 的文本：占位器只在 ≥2 个 ORG 时才产出 ``PARTY_TO`` 关系。
    """
    result = _client(engine="mock").extract_entities_relations(
        document_id=uuid4(),
        full_md_text="甲方：北京青云科技有限公司。乙方：上海浦江科技有限公司。",
        trace_id=uuid4(),
    )
    assert result.relations, "两个 ORG 的文本应有一条 mock 关系"
    assert all(r.valid_from is None for r in result.relations)
