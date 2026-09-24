"""实体 / 关系抽取服务域（Sprint 5 批次 B：LangExtract 接入）。

与 MineruClient 同形：具体类 + ``settings.extraction_provider`` 切换键。
**不**抽 ``ExtractionProvider`` 抽象接口（与 ADR-0004 §3 第 4 条「单实现
无需登记」一致——接缝登记要求"集合 = 登记集合"，单实现不构成接缝）。

公开面：
- :class:`LangextractClient`：唯一实现（``extraction_provider`` 未知档显式报错；
  抽取引擎由 ``settings.extraction_engine`` 显式指定：``llm`` 真调 LLM /
  ``mock`` 正则占位器仅供 CI 注入，未知档同样显式报错）；
- :class:`LangextractError`：业务错误（与 :class:`MineruApiError` 对位）；
- :class:`ExtractionResult`：抽取产物（entities / relations 严格 JSON Schema，
  见 ``prompts/kg_extraction_v2.md``；``failed_chunks`` 记录被跳过的 chunk）。
"""

from app.services.extraction.langextract import (
    ExtractionResult,
    FailedChunk,
    LangextractClient,
    LangextractError,
)

__all__ = [
    "ExtractionResult",
    "FailedChunk",
    "LangextractClient",
    "LangextractError",
]
