"""LLM Provider 工厂（接缝 3，Sprint 5 批次 A2）。

依据 plan §4.2 批次 A2 与 ADR-0004 §2.1 第 3 行：
- ``settings.llm_provider`` 是唯一切换开关；
- 当前唯一档位 ``openai_compatible``（DeepSeek 及任何 OpenAI 兼容端点）；
- 内网双轨（本地 vLLM / Ollama，plan §18.4）落地时切换 base_url 即可，
  **不新增档位不写 stub**（ADR-0004 §3 第 2 条）。

抽象原则（批次 A2 CP 闸门）：「只多一层」——工厂仅做构造参数收敛，
不引入额外消息转换 / 会话管理。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:  # 避免在未装 langchain 的环境下导入失败
    from langchain_openai import ChatOpenAI


class LlmProviderError(Exception):
    """未知 provider 档位（显式报错，不静默回退默认档）。"""


def build_chat_model() -> ChatOpenAI:
    """按 ``settings.llm_provider`` 构造 LLM 客户端。

    ``llm_provider`` 的**唯一消费点**（check_seams 判据 2）。
    """
    settings = get_settings()
    provider = settings.llm_provider

    if provider != "openai_compatible":
        # 未知档位显式报错：静默回退会掩盖配置错误（plan §4.4 纪律）
        raise LlmProviderError(
            f"未知 llm_provider={provider!r}（当前仅支持 'openai_compatible'；"
            "内网本地端点同样走 openai_compatible，仅切 base_url）"
        )

    from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_request_timeout_seconds,
        max_retries=0,  # 重试由调用方（AgentService / 执行体）tenacity 统一管控
    )


__all__ = ["LlmProviderError", "build_chat_model"]
