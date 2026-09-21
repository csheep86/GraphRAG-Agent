"""外部服务 Provider 抽象（接缝 3：llm / parser，Sprint 5 批次 A2）。"""

from __future__ import annotations

from app.services.providers.llm import LlmProviderError, build_chat_model

__all__ = ["LlmProviderError", "build_chat_model"]
