"""LLM Provider 工厂（接缝 3，Sprint 5 批次 A2）。

依据 plan §4.2 批次 A2 与 ADR-0004 §2.1 第 3 行：
- ``settings.llm_provider`` 是唯一切换开关；
- 当前唯一档位 ``openai_compatible``（DeepSeek 及任何 OpenAI 兼容端点）；
- 内网双轨（本地 vLLM / Ollama，plan §18.4）落地时切换 base_url 即可，
  **不新增档位不写 stub**（ADR-0004 §3 第 2 条）。

出向管控（M5 §3 验收 4）：本函数是 LLM 出向的**唯一构造点**，私域守卫挂在这里即
覆盖全部 LLM 路径（``AgentService`` / 本体建议 / 抽取的 ``llm`` 档都经此构造）。
内网 base_url **天然放行**——否则"只改 base_url 就切内网"这句话会被自己的守卫否掉。

抽象原则（批次 A2 CP 闸门）：「只多一层」——工厂仅做构造参数收敛，
不引入额外消息转换 / 会话管理。

采样确定性（**P6-R 裁决 O1**，2026-10-09）：``temperature`` **钉 0，且不留配置开关**。

- **为什么钉**：默认采样下产物**不可复现**——① 问答侧：同一份代码 / 同一份数据连跑，
  拒答误伤读数 **1 / 0 / 0** 抖动（P6-Q 实测，翻转题 Q28）；
  ② **抽取侧**：同一份固定文本连跑两次，实体 **14 vs 19** 条、关系 **7 vs 8** 条
  （P6-R 实测，探针 ``scripts/probe_p6r_extraction_drift.py``）
  ⇒ 出问题的不只是某一条判据的读数，而是**入图产物本身**。
- **为什么不留开关**：做成配置项会让不同部署取到不同值 ⇒ 历史数字不可比；
  且「无消费者的配置不得提交」。钉成常量**不新增配置字段**。
- **它不是放宽判定**：``no_grounded_evidence`` 判定一行未改，``missed_refusals`` 恒空
  （该拒答的库外题仍拒答）——这条是 A6 第 2 条的反向护栏。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.egress import guard_egress

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

    # 私域出向管控（M5 §3 验收 4）：**构造期**判定，目标是 settings.llm_base_url。
    # 违规 ⇒ 抛 503 PRIVATE_DEPLOY_BLOCKED，**一个字节都没发出去**。
    # 这也是内网双轨（本地 vLLM / Ollama 只改 base_url）的使用前提——
    # 内网地址天然放行，不需要进白名单（D9）。
    guard_egress(settings.llm_base_url, target="llm.base_url")

    from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_request_timeout_seconds,
        max_retries=0,  # 重试由调用方（AgentService / 执行体）tenacity 统一管控
        # P6-R 裁决 O1：钉 0 ⇒ 采样确定化（问答 / 抽取 / 本体建议三条路径一并生效）。
        # 理由见模块 docstring「采样确定性」；**不留配置开关**是裁决的一部分。
        temperature=0,
    )


__all__ = ["LlmProviderError", "build_chat_model"]
