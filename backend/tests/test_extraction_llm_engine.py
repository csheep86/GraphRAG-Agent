"""``extraction_engine='llm'`` 档单元测试（Sprint 7.0：真实抽取链路落地）。

全部用例**注入假 LLM**（``llm_invoker`` 或打桩 ``build_chat_model``），零外部依赖：

1. 合法 JSON → 解析出 :class:`ExtractedEntity` / :class:`ExtractedRelation`；
2. Prompt 经 ``prompt_loader`` 从文件系统加载并渲染（**非**硬编码）；
3. 非法 JSON / 调用失败 / 空响应 → :class:`LangextractError`（**不**静默回落 mock）；
4. 合法但为空的 JSON → 正常空结果（v1 模板第 59 行拒答兜底，不是错误）；
5. 未知 ``entity_type`` / ``relation_type`` → 降级 ``RELATED``；``confidence < 0.5`` → 丢弃；
6. ``char_start`` / ``char_end`` 原样透传并在多 chunk 下是**绝对**偏移；
7. 未知 ``extraction_engine`` 档位 → 显式报错，错误消息**含档位名**（防"静默回退"糊过去）；
8. ``mock`` 档行为与改动前完全一致（防回归）。

真实扣费的 DeepSeek 调用**不在**本文件范围（见 ``changes/Sprint7.0/integration-log.md``）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.extraction.langextract as lx
from app.core.config import get_settings
from app.services.extraction import LangextractClient, LangextractError

_TEXT = "甲方：北京青云科技有限公司。乙方：张三。"
#                        ↑3..13                ↑17..19（与下方 payload 的偏移对应）

_PAYLOAD: dict[str, object] = {
    "entities": [
        {
            "id": "ent_001",
            "canonical_name": "北京青云科技有限公司",
            "entity_type": "ORG",
            "mention": "北京青云科技有限公司",
            "char_start": 3,
            "char_end": 13,
            "confidence": 0.95,
        },
        {
            "id": "ent_002",
            "canonical_name": "张三",
            "entity_type": "PERSON",
            "mention": "张三",
            "char_start": 17,
            "char_end": 19,
            "confidence": 0.9,
        },
    ],
    "relations": [
        {
            "id": "rel_001",
            "source_entity_id": "ent_001",
            "target_entity_id": "ent_002",
            "relation_type": "PARTY_TO",
            "evidence": "甲方：北京青云科技有限公司；乙方：张三",
            "confidence": 0.9,
        }
    ],
}


def _client(**overrides: object) -> LangextractClient:
    kwargs: dict[str, object] = {
        "provider": "langextract",
        "max_chars_per_chunk": 4000,
        "max_entities_per_doc": 500,
        "max_relations_per_doc": 1000,
        "prompt_version": "kg_extraction_v1",
        "engine": "llm",
    }
    kwargs.update(overrides)
    return LangextractClient(**kwargs)  # type: ignore[arg-type]


def _invoker_returning(payload: object) -> lx.LlmInvokerFn:
    def _invoke(prompt: str) -> str:
        return json.dumps(payload, ensure_ascii=False)

    return _invoke


# --------------------------------------------------------------------------- #
# 正常解析
# --------------------------------------------------------------------------- #


def test_llm_engine_parses_schema_payload() -> None:
    client = _client(llm_invoker=_invoker_returning(_PAYLOAD))

    result = client.extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert [e.canonical_name for e in result.entities] == [
        "北京青云科技有限公司",
        "张三",
    ]
    assert [e.entity_type for e in result.entities] == ["ORG", "PERSON"]
    # char_start / char_end 原样透传（单 chunk 起点为 0）且指向原文
    assert (result.entities[0].char_start, result.entities[0].char_end) == (3, 13)
    for entity in result.entities:
        assert _TEXT[entity.char_start : entity.char_end] == entity.mention

    assert len(result.relations) == 1
    relation = result.relations[0]
    assert relation.relation_type == "PARTY_TO"
    # 端点必须指向**本次**生成的实体 id（模型给的 ent_00x 一律换新）
    entity_ids = {e.id for e in result.entities}
    assert relation.source_entity_id in entity_ids
    assert relation.target_entity_id in entity_ids
    assert entity_ids.isdisjoint({"ent_001", "ent_002"}), (
        "不得沿用模型 id（跨 chunk 会撞）"
    )


def test_llm_engine_renders_prompt_from_filesystem() -> None:
    """Prompt 必须来自 ``prompts/kg_extraction_v1.md``（禁止硬编码模板文本）。"""
    seen: list[str] = []

    def _invoke(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps(_PAYLOAD, ensure_ascii=False)

    _client(llm_invoker=_invoke).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert len(seen) == 1
    assert seen[0].startswith("# KG Extraction Prompt v1")
    assert "北京青云科技有限公司" in seen[0], "{{text}} 未渲染"
    assert "{{" not in seen[0] and "}}" not in seen[0], "占位符残留"
    assert "chinese" in seen[0], "{{language}} 未渲染"


def test_llm_engine_offsets_are_absolute_across_chunks() -> None:
    """多 chunk：块内偏移必须加回块起点（与 mock 档同一坐标系）。"""
    text = "甲方：北京青云科技有限公司。" * 30  # 每句 14 字，共 420 字
    payload = {"entities": [_PAYLOAD["entities"][0]], "relations": []}

    client = _client(max_chars_per_chunk=140, llm_invoker=_invoker_returning(payload))
    result = client.extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )

    assert len(result.chunks) == 3
    assert len(result.entities) == 3
    offsets = sorted(e.char_start for e in result.entities)
    assert offsets == [3, 143, 283], "块内偏移未加回块起点"
    for entity in result.entities:
        assert text[entity.char_start : entity.char_end] == "北京青云科技有限公司"


def test_llm_engine_resolves_missing_offsets_by_mention() -> None:
    """模型没给偏移 → 用 mention 在 chunk 内回查（原文定位，不是伪造 0）。"""
    payload = {
        "entities": [
            {
                "id": "ent_001",
                "canonical_name": "张三",
                "entity_type": "PERSON",
                "mention": "张三",
                "confidence": 0.9,
            }
        ],
        "relations": [],
    }

    result = _client(
        llm_invoker=_invoker_returning(payload)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    entity = result.entities[0]
    assert (entity.char_start, entity.char_end) == (17, 19)
    assert _TEXT[entity.char_start : entity.char_end] == "张三"


# --------------------------------------------------------------------------- #
# 失败语义（严禁静默回落 mock）
# --------------------------------------------------------------------------- #


def test_llm_engine_invalid_json_raises() -> None:
    def _invoke(prompt: str) -> str:
        return "抱歉，我无法完成该任务。"

    with pytest.raises(LangextractError, match="非法 JSON"):
        _client(llm_invoker=_invoke).extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )


def test_llm_engine_fenced_json_is_accepted() -> None:
    def _invoke(prompt: str) -> str:
        return "```json\n" + json.dumps(_PAYLOAD, ensure_ascii=False) + "\n```"

    result = _client(llm_invoker=_invoke).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert len(result.entities) == 2


def test_llm_engine_blank_response_raises() -> None:
    def _invoke(prompt: str) -> str:
        return "   \n "

    with pytest.raises(LangextractError, match="返回内容为空"):
        _client(llm_invoker=_invoke).extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )


def test_llm_engine_call_failure_raises_not_mock_fallback() -> None:
    """调用失败 → LangextractError；**绝不**回落正则抽取器伪造"抽到了"。"""

    def _invoke(prompt: str) -> str:
        raise RuntimeError("upstream 500")

    client = _client(llm_invoker=_invoke)
    with pytest.raises(LangextractError, match="LLM 调用失败"):
        client.extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )


def test_llm_engine_empty_json_is_empty_result_not_error() -> None:
    """合法但为空（v1 第 59 行拒答兜底）→ 空结果，**不是**错误。"""
    result = _client(
        llm_invoker=_invoker_returning({"entities": [], "relations": []})
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert result.entities == [] and result.relations == []
    assert result.chunks, "切块产物与抽取结果无关，仍须产出"


# --------------------------------------------------------------------------- #
# Schema 约束
# --------------------------------------------------------------------------- #


def test_unknown_types_downgrade_to_related() -> None:
    payload = {
        "entities": [
            {
                "id": "ent_001",
                "canonical_name": "北京青云科技有限公司",
                "entity_type": "LEGAL_PERSON",  # 未命中枚举（v1 第 47 行）
                "mention": "北京青云科技有限公司",
                "char_start": 3,
                "char_end": 13,
                "confidence": 0.9,
            },
            {
                "id": "ent_002",
                "canonical_name": "张三",
                "entity_type": "PERSON",
                "mention": "张三",
                "char_start": 17,
                "char_end": 19,
                "confidence": 0.9,
            },
        ],
        "relations": [
            {
                "id": "rel_001",
                "source_entity_id": "ent_001",
                "target_entity_id": "ent_002",
                "relation_type": "SHAREHOLDER_OF",  # 未命中枚举（v1 第 48 行）
                "evidence": "未知关系类型",
                "confidence": 0.8,
            }
        ],
    }

    result = _client(
        llm_invoker=_invoker_returning(payload)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert result.entities[0].entity_type == "RELATED"
    assert result.relations[0].relation_type == "RELATED"


def test_low_confidence_entities_and_relations_dropped() -> None:
    payload = {
        "entities": [
            {
                "id": "ent_001",
                "canonical_name": "北京青云科技有限公司",
                "entity_type": "ORG",
                "mention": "北京青云科技有限公司",
                "char_start": 3,
                "char_end": 13,
                "confidence": 0.49,  # < 0.5 → 丢弃（v1 第 50 行）
            },
            {
                "id": "ent_002",
                "canonical_name": "张三",
                "entity_type": "PERSON",
                "mention": "张三",
                "char_start": 17,
                "char_end": 19,
                "confidence": 0.9,
            },
        ],
        "relations": [
            {
                "id": "rel_001",
                "source_entity_id": "ent_001",
                "target_entity_id": "ent_002",
                "relation_type": "PARTY_TO",
                "evidence": "低置信关系",
                "confidence": 0.2,
            }
        ],
    }

    result = _client(
        llm_invoker=_invoker_returning(payload)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert [e.canonical_name for e in result.entities] == ["张三"]
    # 端点实体已被丢弃 → 关系一并丢弃（与 _clamp_relations 同口径）
    assert result.relations == []


# --------------------------------------------------------------------------- #
# 显式开关
# --------------------------------------------------------------------------- #


def test_unknown_engine_raises_with_engine_name_in_message() -> None:
    """错误消息必须含档位名——否则"静默回退"能糊过去。"""
    with pytest.raises(LangextractError, match="bogus_engine"):
        _client(engine="bogus_engine")


def test_from_settings_reads_extraction_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """``settings.extraction_engine`` 真的被 from_settings 消费（check_seams 判据 2）。"""
    monkeypatch.setattr(get_settings(), "extraction_engine", "bogus_engine")
    with pytest.raises(LangextractError, match="bogus_engine"):
        LangextractClient.from_settings()


def test_mock_engine_keeps_legacy_behaviour() -> None:
    """``mock`` 档 = 改动前的正则占位器（防回归）。"""
    text = (
        "甲方：北京青云科技有限公司。乙方：上海临港智能装备有限公司。"
        "2024 年营业收入为人民币 12.34 亿元。"
    )
    result = _client(engine="mock").extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )
    names = {e.canonical_name for e in result.entities}
    assert "北京青云科技有限公司" in names
    assert "上海临港智能装备有限公司" in names
    assert {e.entity_type for e in result.entities} <= {
        "ORG",
        "PERSON",
        "MONEY",
        "DATE",
    }
    assert result.relations[0].relation_type == "PARTY_TO"


def test_injected_chunk_extractor_wins_over_engine() -> None:
    """显式注入永远优先于档位（单测零外部依赖靠这条）。"""
    calls: list[int] = []

    def _extract(
        text: str, offset: int
    ) -> tuple[list[lx.ExtractedEntity], list[lx.ExtractedRelation]]:
        calls.append(offset)
        return [], []

    _client(engine="llm", chunk_extractor=_extract).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert calls == [0]


def test_llm_call_log_carries_trace_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """trace_id 必须贯穿到 LLM 调用段（CODEBUDDY.md「日志与可观测性规则」）。"""
    from loguru import logger

    class _FakeModel:
        def invoke(self, messages: list[object]) -> SimpleNamespace:
            return SimpleNamespace(
                content=json.dumps(_PAYLOAD, ensure_ascii=False),
                response_metadata={
                    "token_usage": {"prompt_tokens": 1, "completion_tokens": 2}
                },
            )

    monkeypatch.setattr(lx, "build_chat_model", lambda: _FakeModel())

    records: list[object] = []
    handler_id = logger.add(lambda m: records.append(m.record), level="INFO", format="")
    trace_id = uuid4()
    try:
        _client().extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=trace_id
        )
    finally:
        logger.remove(handler_id)

    call_records = [r for r in records if r["message"] == "langextract_llm_call"]  # type: ignore[index]
    assert len(call_records) == 1
    extra = call_records[0]["extra"]  # type: ignore[index]
    assert extra["trace_id"] == str(trace_id)
    assert extra["chunk_index"] == 0
    assert extra["prompt_tokens"] == 1 and extra["completion_tokens"] == 2


def test_token_usage_is_logged_and_never_invented() -> None:
    """取得到就记数值，取不到记 ``None``（与 agents.py「严禁造数据」同口径）。"""
    assert lx._extract_token_usage(
        SimpleNamespace(
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                }
            }
        )
    ) == {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    assert lx._extract_token_usage(SimpleNamespace()) == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_llm_engine_default_invoker_uses_build_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 invoker 必须走接缝 3 的 ``build_chat_model()``，不新建第二套客户端。"""
    captured: list[list[object]] = []

    class _FakeModel:
        def invoke(self, messages: list[object]) -> SimpleNamespace:
            captured.append(messages)
            return SimpleNamespace(content=json.dumps(_PAYLOAD, ensure_ascii=False))

    monkeypatch.setattr(lx, "build_chat_model", lambda: _FakeModel())

    result = _client().extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert len(captured) == 1, "单 chunk 只应调一次 LLM"
    assert len(result.entities) == 2
    system_prompt = captured[0][0].content  # type: ignore[attr-defined]
    assert system_prompt.startswith("# KG Extraction Prompt v1")
