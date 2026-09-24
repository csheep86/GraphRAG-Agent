"""Sprint 7.1 批次 A：抽取侧三件事（**全部零外部依赖，注入假 LLM**）。

1. **Prompt v2**：`prompts/kg_extraction_v2.md` 类型枚举参数化 + 法人 / 地址两类可用；
   **v1 模板文件未被修改**（只增不改，CODEBUDDY.md「Prompt 版本管理规范」）；
2. **单 chunk 容错**：一个 chunk 失败 → 就地重试 1 次 → 仍失败则**跳过并记账**
   （`FailedChunk`），整份文档不再被外层 tenacity 全量重跑；
   **全部** chunk 失败仍然抛 `LangextractError`（基础设施故障不许伪装成"没抽到"）；
3. **`char_offset` 口径**：模型自报偏移与 `mention` 不符 → **以 `mention` 回查为准**。

真机扣费的抽取不在本文件范围（见 `changes/Sprint7.1/integration-log.md`）。
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

import app.services.extraction.langextract as lx
from app.prompts.prompt_loader import load_prompt
from app.services.extraction import LangextractClient, LangextractError

_TEXT = "甲方：北京青云科技有限公司。乙方：张三。"
#: 含法人 / 住所的完整一句（``mention`` 能在原文里回查到，否则实体会被判 malformed 丢弃）
_V2_TEXT = "发行人：北京青云科技有限公司，法定代表人：张三，住所：北京市海淀区中关村大街 1 号。"

_V2_PAYLOAD: dict[str, object] = {
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
            "entity_type": "LEGAL_PERSON",  # v2 新增
            "mention": "张三",
            "confidence": 0.93,
        },
        {
            "id": "ent_003",
            "canonical_name": "北京市海淀区中关村大街 1 号",
            "entity_type": "ADDRESS",  # v2 新增
            "mention": "北京市海淀区中关村大街 1 号",
            "confidence": 0.9,
        },
    ],
    "relations": [
        {
            "id": "rel_001",
            "source_entity_id": "ent_001",
            "target_entity_id": "ent_002",
            "relation_type": "LEGAL_REP",  # v2 新增
            "evidence": "法定代表人：张三",
            "confidence": 0.92,
        },
        {
            "id": "rel_002",
            "source_entity_id": "ent_001",
            "target_entity_id": "ent_003",
            "relation_type": "REGISTERED_AT",  # v2 新增
            "evidence": "住所：北京市海淀区中关村大街 1 号",
            "confidence": 0.9,
        },
    ],
}


def _client(**overrides: object) -> LangextractClient:
    kwargs: dict[str, object] = {
        "provider": "langextract",
        "max_chars_per_chunk": 4000,
        "max_entities_per_doc": 500,
        "max_relations_per_doc": 1000,
        "prompt_version": "kg_extraction_v2",
        "engine": "llm",
    }
    kwargs.update(overrides)
    return LangextractClient(**kwargs)  # type: ignore[arg-type]


def _invoker_returning(payload: object) -> lx.LlmInvokerFn:
    def _invoke(prompt: str) -> str:
        return json.dumps(payload, ensure_ascii=False)

    return _invoke


# --------------------------------------------------------------------------- #
# 1. Prompt v2 / v1 未被改动
# --------------------------------------------------------------------------- #


def test_v2_template_declares_parameterised_placeholders() -> None:
    template = load_prompt("kg_extraction", version=2)
    assert template.path.name == "kg_extraction_v2.md"
    assert set(template.placeholders) == {
        "text",
        "language",
        "entity_types",
        "relation_types",
    }


def test_v2_renders_new_types_and_leaves_no_placeholder() -> None:
    seen: list[str] = []

    def _invoke(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps(_V2_PAYLOAD, ensure_ascii=False)

    _client(llm_invoker=_invoke).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert len(seen) == 1
    assert seen[0].startswith("# KG Extraction Prompt v2")
    for token in ("LEGAL_PERSON", "ADDRESS", "LEGAL_REP", "REGISTERED_AT"):
        assert token in seen[0], f"v2 渲染后应注入 {token}"
    assert "{{" not in seen[0] and "}}" not in seen[0], "占位符残留"


def test_v1_template_is_untouched() -> None:
    """v1 **只增不改**：仍只有 text / language 两个占位符，且不含 v2 的新类型。"""
    template = load_prompt("kg_extraction", version=1)
    assert set(template.placeholders) == {"text", "language"}
    assert "LEGAL_PERSON" not in template.raw
    assert template.raw.startswith("# KG Extraction Prompt v1")


def test_v1_still_renders_without_new_variables() -> None:
    """v1 渲染时**不会**收到 v2 的变量（否则 prompt_loader 会报未声明变量）。"""
    seen: list[str] = []

    def _invoke(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"entities": [], "relations": []}, ensure_ascii=False)

    LangextractClient(
        provider="langextract",
        max_chars_per_chunk=4000,
        max_entities_per_doc=500,
        max_relations_per_doc=1000,
        prompt_version="kg_extraction_v1",
        engine="llm",
        llm_invoker=_invoke,
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )

    assert seen and seen[0].startswith("# KG Extraction Prompt v1")
    assert "LEGAL_PERSON" not in seen[0]


def test_v2_new_types_survive_instead_of_downgrading() -> None:
    """v2 的 LEGAL_PERSON / ADDRESS / LEGAL_REP / REGISTERED_AT 不得被降级成 RELATED。"""
    result = _client(
        llm_invoker=_invoker_returning(_V2_PAYLOAD)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_V2_TEXT, trace_id=uuid4()
    )

    assert [e.entity_type for e in result.entities] == [
        "ORG",
        "LEGAL_PERSON",
        "ADDRESS",
    ]
    # 偏移必须指向各自的 mention（新版口径：mention 回查）
    for entity in result.entities:
        assert _V2_TEXT[entity.char_start : entity.char_end] == entity.mention
    assert {r.relation_type for r in result.relations} == {
        "LEGAL_REP",
        "REGISTERED_AT",
    }


def test_v2_legacy_types_do_not_regress() -> None:
    """原 v1 类型（PERSON / ORG / PARTY_TO 等）在 v2 下行为不变。"""
    payload = {
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
                "entity_type": "PERSON",
                "mention": "张三",
                "confidence": 0.9,
            },
        ],
        "relations": [
            {
                "id": "rel_001",
                "source_entity_id": "ent_001",
                "target_entity_id": "ent_002",
                "relation_type": "PARTY_TO",
                "evidence": "甲方 / 乙方",
                "confidence": 0.9,
            }
        ],
    }
    result = _client(
        llm_invoker=_invoker_returning(payload)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert [e.entity_type for e in result.entities] == ["ORG", "PERSON"]
    assert result.relations[0].relation_type == "PARTY_TO"
    # 未知类型仍降级 RELATED（v1 第 47–48 行约束不得丢）
    assert "UNKNOWN_KIND" not in lx.ENTITY_TYPES
    assert "UNKNOWN_KIND" not in lx.RELATION_TYPES


# --------------------------------------------------------------------------- #
# 2. 单 chunk 容错
# --------------------------------------------------------------------------- #


def _capture_logs(level: str = "WARNING") -> tuple[list[object], object]:
    from loguru import logger

    records: list[object] = []
    handler_id = logger.add(lambda m: records.append(m.record), level=level, format="")
    return records, handler_id


def test_failed_chunk_is_retried_once_then_skipped_and_accounted() -> None:
    """坏 chunk：调用 2 次（首次 + 重试 1 次）后跳过，其余 chunk 正常出结果。"""
    text = "北京青云科技有限公司。" * 3 + "上海临港智能装备有限公司。" * 3
    bad_calls: list[int] = []

    def _invoke(prompt: str) -> str:
        if "临港" in prompt:
            bad_calls.append(1)
            return "抱歉，我无法完成该任务。"  # 非法 JSON
        return json.dumps(
            {
                "entities": [
                    {
                        "id": "ent_001",
                        "canonical_name": "北京青云科技有限公司",
                        "entity_type": "ORG",
                        "mention": "北京青云科技有限公司",
                        "confidence": 0.9,
                    }
                ],
                "relations": [],
            },
            ensure_ascii=False,
        )

    records, handler_id = _capture_logs()
    from loguru import logger

    try:
        result = _client(
            max_chars_per_chunk=20, llm_invoker=_invoke
        ).extract_entities_relations(
            document_id=uuid4(), full_md_text=text, trace_id=uuid4()
        )
    finally:
        logger.remove(handler_id)

    # 每个坏 chunk 都应是「首次 + 就地重试 1 次」= 2 次调用（不写死坏 chunk 个数，
    # 切分边界随 max_chars_per_chunk 变化，写死会让用例脆断）
    assert len(bad_calls) == 2 * len(result.failed_chunks)
    assert result.failed_chunks, "跳过的 chunk 必须记账，不许静默"
    assert len(result.failed_chunks) < len(result.chunks), "不应把所有 chunk 都判失败"
    assert result.entities, "好 chunk 的产物必须保留"
    # 记账内容可回溯到原文位置
    for failed in result.failed_chunks:
        assert 0 <= failed.char_offset < len(text)
        assert "非法 JSON" in failed.reason
    messages = {r["message"] for r in records}  # type: ignore[index]
    assert "langextract_chunk_retry" in messages
    assert "langextract_chunk_failed" in messages


def test_all_chunks_failed_raises_instead_of_empty_result() -> None:
    """全败 = 基础设施故障：抛错交外层 tenacity，**不许**当成"这份文档没有实体"。"""
    calls: list[int] = []

    def _invoke(prompt: str) -> str:
        calls.append(1)
        return "抱歉，我无法完成该任务。"

    with pytest.raises(LangextractError, match="非法 JSON"):
        _client(llm_invoker=_invoke).extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )

    assert len(calls) == 2, "单 chunk 文档：首次 + 重试 1 次后仍失败 → 抛错"


def test_injected_extractor_bug_is_not_swallowed() -> None:
    """容错只兜 LangextractError；注入抽取器抛别的异常 = bug，必须冒泡。"""

    def _extract(text: str, offset: int):  # type: ignore[no-untyped-def]
        raise ValueError("注入抽取器的 bug")

    with pytest.raises(ValueError, match="注入抽取器的 bug"):
        _client(chunk_extractor=_extract).extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )


# --------------------------------------------------------------------------- #
# 3. char_offset 口径：偏移与 mention 不符 → 以 mention 为准
# --------------------------------------------------------------------------- #


def test_model_offset_is_ignored_when_it_disagrees_with_mention() -> None:
    """模型给的偏移不指向自己的 mention（7.0 真机 14/20 如此）→ 用 mention 回查。"""

    payload = {
        "entities": [
            {
                "id": "ent_001",
                "canonical_name": "张三",
                "entity_type": "PERSON",
                "mention": "张三",
                "char_start": 3,  # 指向"北京青云…"，与 mention 不符
                "char_end": 13,
                "confidence": 0.9,
            }
        ],
        "relations": [],
    }

    records, handler_id = _capture_logs()
    from loguru import logger

    try:
        result = _client(
            llm_invoker=_invoker_returning(payload)
        ).extract_entities_relations(
            document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
        )
    finally:
        logger.remove(handler_id)

    entity = result.entities[0]
    assert _TEXT[entity.char_start : entity.char_end] == "张三"
    assert (entity.char_start, entity.char_end) == (17, 19)
    assert "langextract_char_span_mismatch" in {
        r["message"]
        for r in records  # type: ignore[index]
    }


def test_model_offset_is_kept_when_it_matches_mention() -> None:
    """偏移与 mention 一致 → 原样采用（不无谓改写已正确的真值）。"""
    payload = {
        "entities": [
            {
                "id": "ent_001",
                "canonical_name": "北京青云科技有限公司",
                "entity_type": "ORG",
                "mention": "北京青云科技有限公司",
                "char_start": 3,
                "char_end": 13,
                "confidence": 0.95,
            }
        ],
        "relations": [],
    }
    result = _client(
        llm_invoker=_invoker_returning(payload)
    ).extract_entities_relations(
        document_id=uuid4(), full_md_text=_TEXT, trace_id=uuid4()
    )
    assert (result.entities[0].char_start, result.entities[0].char_end) == (3, 13)
