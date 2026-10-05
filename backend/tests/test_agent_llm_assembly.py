"""**P6-G**：`AgentService` 的 LLM 装配必须**自洽**（谁用谁 ensure）。

这批修的是什么（详见 `changes/P6-G/proposal.md`）：

``_invoke_chat_with_retry`` 曾经直接用 ``self._chat``，而幂等的 ``_ensure_chat()``
全仓唯一调用点在 :meth:`AgentService.answer` 里 ⇒ **任何绕过 HTTP 路由**直接调用低层方法的
代码（P6-F 的 dense 基线侧、未来的后台任务 / worker / 批量脚本）都会遇到
``AttributeError: 'NoneType' object has no attribute 'ainvoke'`` ——
它不是 ``AgentUnavailableError`` ⇒ 路由层的 501 映射和评测的 ``blocked_by`` **都读不出真因**。

⚠️ **本文件最关键的一条是 E5：不许用预先塞好的 `_chat` 骗取绿灯**。
若测试里先写好 ``service._chat = fake`` 再调用，那么即使产品代码根本没修，测试照样是绿的
（那种测试保护的是「本坑恰恰不起作用的那部分」）。故所有用例都必须从
``AgentService.reset()`` 之后的**从未装配**状态起步。

全部用例均为纯单元测试：不连 LLM / PG / Neo4j。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.services.agents import AgentService, AgentUnavailableError


@dataclass
class _FakeResponse:
    content: str
    response_metadata: dict = field(default_factory=dict)


class _FakeChat:
    """替身 ChatModel：记录调用次数，返回一段可被解析器处理的文本。"""

    def __init__(self, text: str = "替身答案") -> None:
        self.calls = 0
        self.text = text

    async def ainvoke(self, messages: list) -> _FakeResponse:  # noqa: ANN401, ARG002
        self.calls += 1
        return _FakeResponse(content=self.text)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> AgentService:
    """返回一个**从未装配**的 AgentService（`reset()` 保证），并接上替身 ChatModel。"""
    from app.core.config import get_settings

    AgentService.reset()
    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key", raising=False)
    monkeypatch.setattr("app.services.agents.build_chat_model", lambda: _FakeChat())
    return AgentService.instance()


def _invoke(service: AgentService):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(
        service._invoke_chat_with_retry(
            system_prompt="sys", question="问一句", trace_id="t-p6g"
        )
    )


def test_invoke_without_prior_answer_path_assembles_llm(service: AgentService) -> None:
    """**E2 根因级**：不经 ``answer()``、直接从零调用也必须能工作（不炸 AttributeError）。"""
    answer, _usage = _invoke(service)
    assert answer == "替身答案"


def test_llm_misconfigured_still_raises_agent_unavailable(
    service: AgentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反方向：KEY 缺失 ⇒ 仍须抛 ``AgentUnavailableError``（**不是** AttributeError）。

    上层（路由 501 / 评测 ``blocked_by``）只认这个类型；形状变了就全读不出真因。
    """
    from app.core.config import get_settings

    AgentService.reset()
    monkeypatch.setattr(get_settings(), "llm_api_key", "", raising=False)
    fresh = AgentService.instance()

    with pytest.raises(AgentUnavailableError):
        _invoke(fresh)


def test_ensure_chat_is_idempotent(service: AgentService) -> None:
    """**零行为变化**的机读证据：重复调用不重建客户端（HTTP 路径多调一次 ⇒ 无操作）。"""
    first = service._ensure_chat()
    second = service._ensure_chat()
    assert first is second
