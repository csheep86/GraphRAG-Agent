"""图谱问答服务（Agentic-RAG）：LangChain Agent + DeepSeek + Neo4j 图谱检索。

公开面：
- :class:`AgentService`：通过 ``AgentService.instance()`` 取单例；
- :class:`AgentUnavailableError`：LLM 未配置 / LangChain 装配失败 / 图谱不可用时抛，
  路由层捕获后转 ``501 NOT_IMPLEMENTED``（阶段九骨架）；
- :func:`AgentService.query`：执行一次问答，返回契约层 :class:`AgentQueryResponse`。

设计要点：
1. **Prompt 严格经** :mod:`app.prompts.prompt_loader` **加载**——禁止硬编码
   （CODEBUDDY.md「Prompt 版本管理规范」）。
2. **LLM 失败 tenacity 重试**：阶段九骨架版采用 ``langchain_openai.ChatOpenAI``
   指向 DeepSeek（OpenAI 兼容 base_url），其内部 httpx 客户端已支持重试；
   本服务在外层再包一层 tenacity，**不**暴露给调用方。
3. **图谱检索工具**：通过 :mod:`app.services.graphs` 提供的
   :func:`fetch_active_kg_version` 与 Cypher 子图查询，把图谱数据喂给 Prompt。
4. **优雅降级**：
   - 未配置 ``LLM_API_KEY`` → :class:`AgentUnavailableError`
   - LangChain Agent 装配失败 → 同上
   - Neo4j 不可用 → 同上
   路由层捕获后统一转 ``501 NOT_IMPLEMENTED``，不污染测试用例。
5. **不持有状态**：状态以数据库 / 文件系统为准（与 ADR-0001 一致）。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, Field
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.prompts.prompt_loader import PromptRenderError, load_prompt
from app.schemas.agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    Citation,
    QueryConfidence,
    RefusalReason,
    TokenUsage,
)
from app.schemas.document import GraphEdge, GraphNode
from app.services.graphs import (
    GraphService,
    GraphUnavailableError,
)
from app.services.providers import build_chat_model

# DeepSeek 是 OpenAI 兼容 API，故使用 langchain_openai.ChatOpenAI 而非 ChatDeepSeek，
# 这样切换到其它 OpenAI 兼容厂商零代码改动。
_LLM_LANGCHAIN_IMPORT_ERROR: Exception | None = None
try:
    import langchain_openai  # noqa: F401 - 可用性探测；构造经 providers.build_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage
except Exception as exc:  # noqa: BLE001 - 兼容失败时优雅降级
    _LLM_LANGCHAIN_IMPORT_ERROR = exc
    ChatOpenAI = None  # type: ignore[assignment]
    HumanMessage = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]


#: 单次送入 Prompt 的图谱节点上限（与契约 `DocumentGraphResponse` 的 500 对齐）
_GRAPH_NODE_LIMIT = 500


@dataclass(frozen=True, slots=True)
class _SubgraphResult:
    """图谱检索结果（批次 A 第二步）。

    一次检索同时产出两份数据：
    - ``serialized``：XML-like 文本，喂给 ``kg_qa`` Prompt；
    - ``nodes`` / ``edges`` / ``truncated``：结构化图谱数据，
      直接填充契约字段 ``AgentQueryResponse.kg_nodes`` / ``kg_relations``。
    """

    serialized: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


class AgentUnavailableError(Exception):
    """Agent 装配或调用前置条件缺失（未配置 API_KEY / Neo4j 不可用等）。

    路由层捕获后转 ``501``——**不**等同 ``refused=true``：

    - ``AgentUnavailableError`` → 基础设施 / 配置故障（501）；
    - ``refused=true`` → 图谱证据不足，属**正常业务判定**（200）。
    """


class _LlmAnswerSchema(BaseModel):
    """LLM 输出 JSON 的内层 schema（Pydantic 校验 + 显式字段语义）。"""

    answer: str
    evidence: list[str] = Field(default_factory=list)
    confidence: QueryConfidence = "low"
    missing_context: list[str] = Field(default_factory=list)


class AgentService:
    """图谱问答服务（懒加载 + 单例）。"""

    _instance: AgentService | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._chat: Any = None
        self._failure_reason: str | None = None

    @classmethod
    def instance(cls) -> AgentService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅供测试）。"""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------ LLM

    def _ensure_chat(self) -> Any:
        """懒加载 ChatOpenAI；未配置 / LangChain 缺失抛 :class:`AgentUnavailableError`。"""
        if self._chat is not None:
            return self._chat

        if _LLM_LANGCHAIN_IMPORT_ERROR is not None or ChatOpenAI is None:
            self._failure_reason = (
                f"LangChain 装配失败: {_LLM_LANGCHAIN_IMPORT_ERROR!r}"
            )
            raise AgentUnavailableError(self._failure_reason)

        settings = get_settings()
        if not settings.llm_api_key:
            self._failure_reason = "LLM_API_KEY 未配置"
            raise AgentUnavailableError(self._failure_reason)

        try:
            self._chat = build_chat_model()
        except AgentUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - 装配失败包装
            self._failure_reason = f"LLM 装配失败: {exc!r}"
            raise AgentUnavailableError(self._failure_reason) from exc

        logger.bind(model=settings.llm_model).info("agent_llm_ready")
        return self._chat

    # ------------------------------------------------------------------ query

    async def query(
        self,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
    ) -> AgentQueryResponse:
        """执行一次图谱问答。

        实现策略（阶段九 9.3）：
        1. 取 ``active kg_version``（强一致过滤，ADR-0002 §3.2）；
        2. 从 Neo4j 拉取与问题相关的子图；
        3. 经 :mod:`app.prompts.prompt_loader` 加载 ``kg_qa`` Prompt；
        4. tenacity 重试调用 LLM；
        5. 解析 LLM 输出 → 映射为契约 :class:`AgentQueryResponse`。

        **故障语义边界**：Neo4j / LLM 等基础设施不可用时抛
        :class:`AgentUnavailableError`（路由层转 501）；
        只有「图谱可查但证据不足」才返回 ``refused=true``（200）。
        """
        settings = get_settings()

        # 1) active kg_version
        try:
            kg_version = GraphService.instance().fetch_active_kg_version()
        except GraphUnavailableError as exc:
            # 基础设施故障（Neo4j 不可用 / 无 active 版本）**不**等同于「检索不到证据」：
            # 后者才是 refused=true，前者必须上抛为 501，否则会把故障伪装成正常拒答。
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_graph_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 不可用: {exc}") from exc

        version = kg_version.version

        # 2) 拉取子图：一次拿到 Prompt 文本 + 结构化节点 / 关系
        #    （批次 A：nodes / edges 用于填充契约 kg_nodes / kg_relations）
        try:
            subgraph = self._fetch_subgraph_for_question(
                kg_version=version,
                doc_id=request.doc_id,
                org_id=org_id,
                scope=request.scope,
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_subgraph_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 子图查询失败: {exc}") from exc

        # 3) 加载 Prompt（任何占位符错误都立即暴露，禁止硬编码）
        template = load_prompt("kg_qa")
        try:
            system_prompt = template.render(
                graph_subgraph=subgraph.serialized,
                text_chunks="<chunks not provided in Sprint 3 phase 9 skeleton>",
                chat_history="",
                question=request.question,
            )
        except PromptRenderError as exc:
            # Prompt 渲染失败属于实现错误，不可降级为拒答
            logger.bind(trace_id=trace_id, error=str(exc)).error(
                "agent_query_prompt_render_failed"
            )
            raise AgentUnavailableError(f"Prompt 渲染失败: {exc}") from exc

        # 4) 调用 LLM（tenacity 重试），同时提取真实 token 用量
        # 仅为触发前置检查（未配置 KEY / LangChain 缺失时抛 AgentUnavailableError）
        self._ensure_chat()
        try:
            answer, token_usage = await self._invoke_chat_with_retry(
                system_prompt=system_prompt,
                question=request.question,
                trace_id=trace_id,
            )
        except AgentUnavailableError:
            # LLM 装配失败（未配置 API_KEY 等）→ 路由层转 501
            raise
        except Exception as exc:
            # 重试用尽后的兜底。**必须兜 Exception 而非 RetryError**：
            # tenacity 9.1.4（tenacity/__init__.py:403-417）在 ``reraise=True`` 时走
            # ``raise retry_exc.reraise()``，重抛的是**最后一个原始异常**，
            # ``RetryError`` 永远不会到达调用方。若只捕 ``RetryError``，
            # DeepSeek 的网络 / 鉴权 / 限流故障会穿透成 500 INTERNAL_ERROR。
            logger.bind(trace_id=trace_id, exc=str(exc)).error(
                "agent_query_llm_exhausted"
            )
            raise AgentUnavailableError(
                f"LLM 调用失败（重试 {settings.task_retry_max_attempts} 次仍失败）: {exc}"
            ) from exc

        # 5) 解析输出
        parsed = _parse_llm_answer(answer)

        # 6) 引用覆盖率为 0 → 拒答（F3：引用覆盖率 < 100% 直接 NO-GO）
        citations = [
            _to_citation(item) for item in parsed.evidence if _looks_like_citation(item)
        ]
        # 注意：`QueryRoute` / `QueryConfidence` / `RefusalReason` 是 `Literal` **类型别名**
        # 而非 Enum，**禁止**属性访问——`QueryRoute.M3_GRAPHQA` 会经
        # `typing._BaseGenericAlias.__getattr__` 转发到 `typing.Literal` 而抛
        # `AttributeError`（ruff / pytest 都测不到，只在真实调用时 500）。
        # 只能写字符串字面量，取值必须与 `contracts/openapi.yaml` 的 `enum` 一致。
        if not citations:
            # 拒答分支（批次 A 决策 + D1 缺口 6）：无支撑证据 → 统一走 `_refuse()`。
            # 原先此处 inline 构造，与 `_refuse()` 逻辑重复（DRY）；
            # Sprint 4 接入 Agent Tool 调用循环后，工具循环里的拒答可复用同一出口。
            # 语义**不变**：kg_nodes / kg_relations 为空列表，token_usage 为 None。
            return self._refuse(
                trace_id=trace_id,
                kg_version=version,
                reason="no_grounded_evidence",
                note=(
                    "图谱可查但 LLM 未给出可溯源证据"
                    "（evidence 中无 chunk-/doc- 前缀条目），按 M3 验收 3 拒答"
                ),
            )

        # 正常回答：kg_nodes / kg_relations 来自第 2 步的结构化检索结果，
        # token_usage 来自 LLM 响应的真实提取（拿不到则为 None）
        return AgentQueryResponse(
            answer=parsed.answer,
            citations=citations,
            route="m3_graphqa",
            confidence=parsed.confidence,
            refused=False,
            kg_version=version,
            trace_id=trace_id,
            kg_nodes=subgraph.nodes,
            kg_relations=subgraph.edges,
            token_usage=token_usage,
        )

    # ------------------------------------------------------------------ helpers

    async def _invoke_chat_with_retry(
        self,
        *,
        system_prompt: str,
        question: str,
        trace_id: str,
    ) -> tuple[str, TokenUsage | None]:
        """带 tenacity 重试的 ChatModel 调用。

        :returns: ``(answer_text, token_usage)``；LLM 响应中提取不到
            token 用量时 ``token_usage = None``（严禁造数据）。
        """
        if SystemMessage is None or HumanMessage is None:
            raise AgentUnavailableError("LangChain messages 不可用")

        settings = get_settings()

        def _on_retry(retry_state) -> None:  # noqa: ANN001
            logger.bind(
                trace_id=trace_id,
                attempt=retry_state.attempt_number,
                next_wait=getattr(retry_state.next_action, "sleep", None),
            ).warning("agent_llm_retry")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.task_retry_max_attempts),
            wait=_build_llm_wait_policy(),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                _on_retry(attempt.retry_state) if attempt.retry_state else None
                response = await self._chat.ainvoke(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=question),
                    ]
                )
                # 文本与 token 用量从同一个 response 中提取，避免二次调用
                return _extract_text(response), _extract_token_usage(response)

        raise AgentUnavailableError("LLM 调用未返回结果")

    def _fetch_subgraph_for_question(
        self,
        *,
        kg_version: str,
        doc_id: UUID | None,
        org_id: UUID,
        scope: str,
    ) -> _SubgraphResult:
        """拉取与问题相关的子图：Prompt 文本 + 结构化节点 / 关系。

        - ``scope = single_doc``（Pydantic 已保证 ``doc_id`` 非空）→ 文档子图；
        - ``scope = cross_doc``（``doc_id`` 为空）→ **全部**已导入实体图，
          对应 :meth:`GraphService.fetch_all_subgraph`（不依赖 PG ``document_id``）。

        图谱为空时 ``serialized`` 为 ``<graph: empty>``，让 Prompt 明确
        「无证据」而非留白，避免 LLM 用自身记忆补全。
        ``nodes`` / ``edges`` 原样透传给 ``query()`` 填充契约字段
        （批次 A：``kg_nodes`` / ``kg_relations``）。
        Sprint 4 后续替换为 LangChain Agent 的 Tool 调用循环。
        """
        graph = GraphService.instance()

        if doc_id is None:
            # 跨文档模式：全量实体图（阶段六 bridge 产物）
            nodes, edges, truncated = graph.fetch_all_subgraph(
                kg_version=kg_version,
                org_id=org_id,
                node_limit=_GRAPH_NODE_LIMIT,
            )
        else:
            nodes, edges, truncated = graph.fetch_document_subgraph(
                doc_id=doc_id,
                kg_version=kg_version,
                org_id=org_id,
                node_limit=_GRAPH_NODE_LIMIT,
            )

        if not nodes:
            serialized = f"<graph: empty scope={scope} kg_version={kg_version}>"
        else:
            serialized = _serialize_subgraph(
                nodes=nodes, edges=edges, truncated=truncated
            )
        return _SubgraphResult(
            serialized=serialized, nodes=nodes, edges=edges, truncated=truncated
        )

    def _refuse(
        self,
        *,
        trace_id: str,
        kg_version: str,
        reason: RefusalReason,
        note: str,
    ) -> AgentQueryResponse:
        """拒答的**唯一出口**（Sprint 4.10.0.D1 缺口 6：原为无调用方的死代码）。

        拒答是**正常业务判定**（HTTP ``200`` + ``refused = true``），
        **不是**基础设施故障——后者必须抛 :class:`AgentUnavailableError`（501）。

        三个图谱 / 用量字段在此**显式置空**，理由如下（严禁拼凑数据）：
        - ``kg_nodes`` / ``kg_relations``：拒答意味着**没有**任何支撑答案的证据，
          若把检索到的子图一并返回，前端会误以为答案有据可依；
        - ``token_usage``：拒答语义下不承担用量统计，即使 LLM 曾被调用过也不回填。

        :param note: 人类可读的拒答缘由，**仅**进日志便于检索（不入契约）。
        """
        logger.bind(trace_id=trace_id, reason=reason, note=note).info(
            "agent_query_refused"
        )
        return AgentQueryResponse(
            answer="无法回答",
            citations=[],
            route="m3_graphqa",
            confidence="low",
            refused=True,
            refusal_reason=reason,
            kg_version=kg_version,
            trace_id=trace_id,
            kg_nodes=[],
            kg_relations=[],
            token_usage=None,
        )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _build_llm_wait_policy() -> Any:
    """构造 LLM 重试的指数退避策略。

    **必须独立成函数以便单测覆盖**：tenacity 9.x 的 ``wait_exponential``
    **不接受** ``multiplier_getter``（9.1.4 签名只有
    ``multiplier / max / exp_base / min``）。旧写法把它内联在协程里，
    只有真正调 LLM 时才抛 ``TypeError``——测试永远碰不到。
    语义映射：``multiplier`` = 首次等待秒数，``exp_base`` = 每轮增长倍数。
    """
    settings = get_settings()
    return wait_exponential(
        multiplier=settings.task_retry_initial_seconds,
        exp_base=settings.task_retry_multiplier,
    )


def _extract_text(response: Any) -> str:
    """从 LangChain AIMessage / str / dict 中提取文本。"""
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return str(response.get("content", ""))
    return str(content)


def _is_nonneg_int(value: Any) -> bool:
    """严格判定非负 int。

    必须显式排除 ``bool``——它是 ``int`` 的子类，``True`` 会被 ``isinstance``
    误判为合法的 ``1``，导致 token 计数被悄悄污染。
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _extract_token_usage(response: Any) -> TokenUsage | None:
    """从 LangChain 响应中提取 token 用量；拿不到返回 ``None``（严禁造数据）。

    按「实测结果反哺规则」，同时探测两种结构（哪个先命中用哪个）：

    1. LangChain 标准化 ``usage_metadata``（``langchain_core`` ≥ 0.2 起
       ``AIMessage.usage_metadata`` 统一为
       ``input_tokens / output_tokens / total_tokens``）；
    2. OpenAI 兼容 ``response_metadata["token_usage"]``
       （DeepSeek 等 OpenAI 兼容厂商的原始 usage 透传，
       字段为 ``prompt_tokens / completion_tokens / total_tokens``）。

    任一字段缺失 / 非非负 int（如 ``None`` / 字符串 / 布尔）即视为
    提取失败 → 返回 ``None``，由上层以 ``token_usage = None`` 落契约。
    """
    # 路径 1：LangChain 标准化 usage_metadata
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        prompt = usage.get("input_tokens")
        completion = usage.get("output_tokens")
        total = usage.get("total_tokens")
        if all(_is_nonneg_int(v) for v in (prompt, completion, total)):
            return TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
            )

    # 路径 2：OpenAI 兼容 response_metadata["token_usage"]
    metadata = getattr(response, "response_metadata", None)
    token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if isinstance(token_usage, dict):
        prompt = token_usage.get("prompt_tokens")
        completion = token_usage.get("completion_tokens")
        total = token_usage.get("total_tokens")
        if all(_is_nonneg_int(v) for v in (prompt, completion, total)):
            return TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
            )

    return None


def _parse_llm_answer(raw: str) -> _LlmAnswerSchema:
    """解析 LLM 输出（容忍 JSON 出现在 ```json 块里）。"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # 去掉首尾 ```json ... ```
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 输出不可解析：视为拒答（F3 防御）
        return _LlmAnswerSchema(
            answer="无法回答",
            confidence="low",
            missing_context=["LLM 输出非合法 JSON"],
        )

    try:
        return _LlmAnswerSchema.model_validate(data)
    except Exception:  # noqa: BLE001 - 字段缺失时容错
        return _LlmAnswerSchema(
            answer=str(data.get("answer", "无法回答")),
            confidence="low",
        )


def _looks_like_citation(item: str) -> bool:
    """证据条目是否形似 ``chunk-<id>`` 或 ``doc-<id>``。"""
    return isinstance(item, str) and (
        item.startswith("chunk-") or item.startswith("doc-") or "chunk" in item
    )


def _to_citation(item: str) -> Citation:
    """把 LLM 证据条目映射为契约 :class:`Citation`（骨架版：缺字段填默认值）。

    Sprint 3 后段替换为 Cypher 反查以拿到真实 ``doc_id`` / ``page`` / ``snippet``。
    """
    return Citation(
        doc_id=UUID(int=0),  # 骨架版不解析真实 UUID
        page=1,
        chunk_id=item,
        char_offset=0,
        snippet="",
    )


def _serialize_subgraph(
    *,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    truncated: bool,
) -> str:
    """把子图序列化为 LLM 友好的文本。骨架版仅输出节点 label + id + 类型。"""
    lines = [f"<graph truncated={truncated}>"]
    for node in nodes:
        label = node.label
        canonical = node.canonical_name or node.id
        lines.append(f"  node {label} id={node.id} name={canonical}")
    for edge in edges:
        lines.append(f"  edge {edge.type} {edge.source} -> {edge.target}")
    lines.append("</graph>")
    return "\n".join(lines)


__all__ = [
    "AgentService",
    "AgentUnavailableError",
]
