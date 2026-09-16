"""Prompt 加载器测试（CODEBUDDY.md「Prompt 版本管理规范」）。"""

from __future__ import annotations

import pytest

from app.prompts.prompt_loader import (
    PromptNotFoundError,
    PromptRenderError,
    list_prompts,
    load_prompt,
    resolve_prompt,
)

KG_QA_VARS = {
    "graph_subgraph": "<graph/>",
    "text_chunks": "<chunks/>",
    "chat_history": "",
    "question": "A 公司与 B 公司是什么关系？",
}


def test_prompts_are_discovered_from_filesystem() -> None:
    names = {ref.name for ref in list_prompts()}

    assert "kg_qa" in names


def test_load_latest_version_by_default() -> None:
    template = load_prompt("kg_qa")

    assert template.version >= 1
    assert template.path.name == f"kg_qa_v{template.version}.md"


def test_resolve_explicit_version() -> None:
    assert resolve_prompt("kg_qa", 1).version == 1


def test_render_replaces_every_placeholder() -> None:
    rendered = load_prompt("kg_qa").render(**KG_QA_VARS)

    assert KG_QA_VARS["question"] in rendered
    assert "{{" not in rendered and "}}" not in rendered


def test_missing_variable_raises() -> None:
    partial = {key: value for key, value in KG_QA_VARS.items() if key != "question"}

    with pytest.raises(PromptRenderError, match="question"):
        load_prompt("kg_qa").render(**partial)


def test_unknown_variable_raises() -> None:
    with pytest.raises(PromptRenderError, match="unexpected"):
        load_prompt("kg_qa").render(**KG_QA_VARS, unexpected="x")


def test_unknown_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("no_such_prompt")


def test_unknown_version_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("kg_qa", 999)
