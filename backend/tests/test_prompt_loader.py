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

#: Sprint 9 批次 B2：``kg_qa`` 升到 v2 并新增 ``as_of_date``（答案模板要说清依据
#: 截至哪天的披露文件）；变量集随最新版更新——这正是 loader「未知变量必报错」
#: 存在的意义：升级 Prompt 时**必须**在调用方留下痕迹。
KG_QA_VARS = {
    "graph_subgraph": "<graph/>",
    "text_chunks": "<chunks/>",
    "chat_history": "",
    "question": "A 公司与 B 公司是什么关系？",
    "as_of_date": "2026-09-28",
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


def test_latest_kg_qa_accepts_empty_as_of_date() -> None:
    """Sprint 10.4（``kg_qa_v5``）：日期不可得 ⇒ 调用方喂**空串**，模板负责整句不出现。

    真机来源（2026-09-30）：演示库 17 份文档 ``document_date`` 全为 NULL，而调用方
    此前喂的是字面量 ``unknown`` ⇒ 答案里出现「依据截至 **unknown** 的披露文件」。
    本例钉住"空值必须被接受"：**渲染层不许因为空值报错**，也不许把它渲染成占位符字面量。
    """
    template = load_prompt("kg_qa")
    assert "as_of_date" in template.placeholders

    rendered = template.render(**{**KG_QA_VARS, "as_of_date": ""})

    assert "{{" not in rendered and "}}" not in rendered
    # 日期那一栏必须是**空的**（后面什么都不跟），而不是被填成 "unknown"
    lines = [line for line in rendered.splitlines() if "(as-of date):" in line]
    assert len(lines) == 1
    assert lines[0].rstrip().endswith("(as-of date):")


def test_kg_qa_v4_is_left_untouched() -> None:
    """版本规范（H9）：升到 v5 时 **v4 文件一个字都不能改**。

    v4 的 as-of 降级口径（"明确说日期未知"）正是 v5 要修的那一条——若有人图省事
    原地改 v4，这条用例会红，而不是等到真机答案里再次冒出 ``unknown``。
    """
    v4 = load_prompt("kg_qa", version=4)
    assert set(v4.placeholders) == set(KG_QA_VARS)
    # v4 的原文要求模型"明确说截至日期不可用" ⇒ 该措辞必须还在 v4 里
    assert "unavailable" in v4.raw


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


def test_kg_extraction_v1_registered() -> None:
    """Sprint 5 批次 B：kg_extraction_v1（E1/E2 共用模板）必须可发现。

    Sprint 7.1 批次 A：新增 ``kg_extraction_v2`` 后，``load_prompt("kg_extraction")``
    （不指定版本）按"取最大版本"语义返回 **v2**；v1 仍必须**可发现且未被改动**
    （Prompt 版本管理规范：只增不改）。
    """
    v1 = load_prompt("kg_extraction", version=1)
    assert v1.version == 1
    assert set(v1.placeholders) == {"text", "language"}

    # Sprint 9 批次 A：又新增 ``kg_extraction_v3``。这里**不写死版本号**——
    # 断言语义是"取最大版本"，写死会让每次升版都红一次，逼人把范围判断改成数字。
    latest = load_prompt("kg_extraction")
    available = [ref.version for ref in list_prompts() if ref.name == "kg_extraction"]
    assert latest.version == max(available), "不指定版本时取最大版本"
