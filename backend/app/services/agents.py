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

import hashlib
import json
import re
import threading
from collections.abc import Mapping, Sequence
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
from app.db.models import QaLog
from app.db.session import SessionLocal
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
from app.services.audit import record_audit_entry
from app.services.graphs import (
    EntitySpan,
    EvidenceChunk,
    GraphService,
    GraphUnavailableError,
)
from app.services.providers import build_chat_model

#: DeepSeek 是 OpenAI 兼容 API，故经 ``langchain_openai.ChatOpenAI`` 接入
#: （切换到其它 OpenAI 兼容厂商零代码改动）。
#:
#: **真机教训（2026-09-22 批次 B 冒烟）**：本模块**不得**直接引用 ``ChatOpenAI``
#: 这个名字——它只在下方 ``except`` 分支被赋值为 ``None``，导入**成功**时从未定义，
#: 于是 ``_ensure_chat`` 里那句 ``ChatOpenAI is None`` 会抛 ``NameError`` →
#: 全局兜底成 500（单测把 LLM 全打桩，该分支永远走不到，只能由真机暴露）。
#: 构造统一交给 :func:`app.services.providers.build_chat_model`；这里只探测
#: **可用性**（模块 + 消息类型），失败则降级为 501 而非 500。
_LLM_LANGCHAIN_IMPORT_ERROR: Exception | None = None
try:
    import langchain_openai  # noqa: F401 - 可用性探测；构造经 providers.build_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage
except Exception as exc:  # noqa: BLE001 - 兼容失败时优雅降级
    _LLM_LANGCHAIN_IMPORT_ERROR = exc
    HumanMessage = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]


#: 单次送入 Prompt 的图谱节点上限（与契约 `DocumentGraphResponse` 的 500 对齐）
_GRAPH_NODE_LIMIT = 500

#: `Citation.snippet` 上限：引用只带摘录，chunk 全文由 `GET /documents/{id}/chunks/{id}`
#: 回查（Q2 拍板——不把全文塞进 `citations`，否则响应随答案条数线性膨胀）
_SNIPPET_LIMIT = 200

#: 证据条目中的 chunk id（``chunk-<12 hex>``）。
#: 长度刻意**宽松**（1~64 位字母数字）：本处只负责从自由文本里**抠出** id，
#: 真正的闸门是后续的 ``chunk_id`` 索引回查——回查不到即丢弃（F3），
#: 因此无需在正则层面卡死位数（历史占位 / 契约示例里的短 id 也能正确解析）。
_CITATION_ID_PATTERN = re.compile(r"chunk-[0-9A-Za-z]{1,64}")

#: Sprint 10 批次 A（裁决 D-C）：证据条目里「chunk id」与「实体提及文本」的分隔符，
#: 约定形如 ``chunk-<id>#<提及>``（Prompt ``kg_qa_v4``）。
#: **模型只给文本、不给数字**——偏移由 :func:`_to_citation` 确定性换算（D-B）。
_MENTION_SEPARATOR = "#"


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


class AgentTenantLeakError(AgentUnavailableError):
    """跨租户子图泄漏检测（ADR-0003 §4，Sprint 5 批次 B fail-closed 强化）。

    路由层捕获后转 ``403`` + ``KG_TENANT_LEAK``——与 ``AgentUnavailableError``（501）
    严格区分：前者是数据质量事故（数据已写出，须禁止消费），后者是基础设施不可用。
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

        # 只判可用性探测结果：**不**再引用 ChatOpenAI 名字（真机 NameError，见上方注释）
        if _LLM_LANGCHAIN_IMPORT_ERROR is not None:
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
        db: Any = None,
    ) -> AgentQueryResponse:
        """执行一次图谱问答，**并**在产出响应后落一条 `qa_logs`（M3 §4.3 / 决策 **A4**）。

        问答此前是全函数**零 DB 写入**的唯一缺口（`specs/m3-graphqa-citation.md` §6 S6.4-3
        登记），本处即它的偿还点，因此打点放在这里而不是路由层：只有这里既握有响应体、
        又握有原始提问。

        **成功与拒答都落**（M3 §5.3：拒答事件正是发现本体缺口的输入）。
        基础设施故障（`AgentUnavailableError` → 501）**不落**本表——那次调用没有
        `AgentQueryResponse`，且同一 HTTP 请求已由审计中间件写了一条 `failure`
        （`audit_log` 覆盖失败留痕，不重复造一份残缺记录）。
        """
        response = await self._execute_query(
            request=request, org_id=org_id, trace_id=trace_id, db=db
        )
        _record_qa_log(response=response, request=request, org_id=org_id, db=db)
        return response

    async def _execute_query(
        self,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
        db: Any = None,
    ) -> AgentQueryResponse:
        """执行一次图谱问答。

        实现策略（阶段九 9.3）：
        1. 取 ``active kg_version``（强一致过滤，ADR-0002 §3.2）；
        2. 从 Neo4j 拉取与问题相关的子图；
        2.5 拉取证据片段（Sprint 6 批次 B：chunk 原文注入 ``kg_qa`` 的 ``text_chunks``，
           并建 ``chunk_id`` 索引供引用回查）；
        2.7 取多跳推理路径（Sprint 9.5 批次 D1：确定性取自图谱，与 LLM 无关）；
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
            kg_version = GraphService.instance().fetch_active_kg_version(
                org_id=org_id, db=db
            )
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
        #    Sprint 9 批次 B2：先算出「这次回答依据的是哪一天」，再把同一天传给子图
        #    ——答案模板与图视图必须**同一**个日期，否则会出现"说依据 2024 年，
        #      注入的其实是现在的数据"这种无从察觉的错位。
        as_of_date, as_of_doc_id = _resolve_context_date(
            db=db, org_id=org_id, doc_id=request.doc_id
        )
        if as_of_date is None:
            logger.bind(trace_id=trace_id, org_id=str(org_id)).info(
                "agent_query_as_of_unknown"
            )
        try:
            subgraph = self._fetch_subgraph_for_question(
                kg_version=version,
                doc_id=request.doc_id,
                org_id=org_id,
                scope=request.scope,
                as_of=as_of_date,
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_subgraph_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 子图查询失败: {exc}") from exc

        # 2.5) fail-closed 校验（ADR-0003 §4 强化，Sprint 5 批次 B）
        # 即使 Cypher 已带 ``WHERE e.org_id = $org_id`` 过滤，**仍**做一次独立的
        # 全库校验：防漏改（恶意 / 越权 build 把跨租户节点写入同一 kg_version）
        # 被 fail-open Cypher 过滤掩盖——属数据质量事故伪装为正常结论。
        try:
            tenant_clean = GraphService.instance().validate_kg_version_tenant_boundary(
                kg_version=version, current_org_id=org_id
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_tenant_boundary_check_failed"
            )
            raise AgentUnavailableError(f"fail-closed 校验失败: {exc}") from exc

        if not tenant_clean:
            if settings.agent_fail_closed:
                logger.bind(
                    trace_id=trace_id,
                    org_id=str(org_id),
                    kg_version=version,
                ).error("agent_query_tenant_leak_blocked")
                raise AgentTenantLeakError(
                    f"跨租户子图泄漏检测到（kg_version={version}，org_id={org_id}）"
                )
            logger.bind(
                trace_id=trace_id,
                org_id=str(org_id),
                kg_version=version,
            ).warning("agent_query_tenant_leak_warn_only")
            # A12（Sprint 8.1 批次 B）：逃生阀触发必须留痕——比纯日志可核，
            # 审计页能直接看到「谁在哪个版本上被放行了越权数据」。写失败只记日志。
            with SessionLocal() as session:
                record_audit_entry(
                    session,
                    org_id=org_id,
                    action="tenant_leak.warn",
                    resource=f"POST {settings.api_prefix}/agent/query",
                    status="failure",
                    trace_id=trace_id,
                    detail={
                        "kg_version": version,
                        "fail_closed": settings.agent_fail_closed,
                    },
                )
                session.commit()

        # 2.6) 证据片段（Sprint 6 批次 B）：把 chunk 原文注入 Prompt，
        #      并建立 `chunk_id -> EvidenceChunk` 索引供第 6 步回查引用。
        #      故障语义与子图查询一致：Neo4j 故障上抛 501，
        #      **不**降级为「无片段」——空片段会让 LLM 无从引用，进而伪装成正常拒答。
        entity_ids = [node.id for node in subgraph.nodes if node.label == "Entity"]
        # 2.6a) **锚点并入证据检索范围**（2026-09-28 真机事故修，见 R12 / R14）：
        #       子图是 ``node_limit`` 采样出来的，``EMPLOYEE`` 这类「数量少、粒度粗」
        #       的锚点常被事实节点挤出去 ⇒ 只按子图取证据，会注入**与当事人无关**
        #       的 chunk。实测后果：问「李静的月加班…」时注入的只有制度条款，
        #       LLM 于是答「资料中没有李静的任何信息」——**却仍带着 1 条引用**
        #       （引的是制度条款）。答案与引用不符，比拒答更危险。
        #       与 D1 推理路径**共用同一套锚点**（含子图定位不到时的直查兜底）。
        try:
            anchors = GraphService.instance().fetch_anchor_entity_ids(
                kg_version=version,
                org_id=org_id,
                question=request.question,
                nodes=subgraph.nodes,
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_anchor_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 锚点查询失败: {exc}") from exc
        if anchors:
            # 锚点排前面：证据注入的条数上限若生效，先保住当事人
            entity_ids = list(dict.fromkeys([*anchors, *entity_ids]))
        try:
            evidence_chunks = GraphService.instance().fetch_evidence_chunks(
                kg_version=version,
                org_id=org_id,
                entity_ids=entity_ids,
                doc_id=request.doc_id,
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_evidence_chunks_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 证据片段查询失败: {exc}") from exc

        chunk_index = {chunk.chunk_id: chunk for chunk in evidence_chunks}
        text_chunks = _serialize_chunks(evidence_chunks)
        logger.bind(
            trace_id=trace_id,
            entity_count=len(entity_ids),
            chunk_count=len(evidence_chunks),
        ).info("agent_query_evidence_chunks")

        # 2.7) 多跳推理路径（Sprint 9.5 批次 D1 / proposal §5.5）
        #      放在 LLM 之前：路径是**确定性**地从图上取出来的，与 LLM 输出无关
        #      ——它要能在「LLM 拒答」时依然说清楚「图上到底有没有这条链」。
        #      故障语义与证据片段一致：Neo4j 故障上抛 501，
        #      **不**降级为空路径（空 = 零命中，会把故障伪装成"图上没有链"）。
        try:
            reasoning_path = GraphService.instance().fetch_reasoning_path(
                kg_version=version,
                org_id=org_id,
                question=request.question,
                nodes=subgraph.nodes,
                edges=subgraph.edges,
                chunks=evidence_chunks,
                # 全生命周期 as-of（Sprint 10.5 / L2-③）：由请求传入，缺省 None
                # ⇒ 当前视图，与加此参数之前完全同解（缺省必须零变化）。
                as_of=request.as_of,
            )
        except GraphUnavailableError as exc:
            logger.bind(trace_id=trace_id, reason=str(exc)).error(
                "agent_query_reasoning_path_unavailable"
            )
            raise AgentUnavailableError(f"Neo4j 推理路径查询失败: {exc}") from exc
        logger.bind(trace_id=trace_id, hop_count=len(reasoning_path)).info(
            "agent_query_reasoning_path"
        )

        # 3) 加载 Prompt（任何占位符错误都立即暴露，禁止硬编码）
        template = load_prompt("kg_qa")
        try:
            # 按模板**声明**的占位符给值（与抽取侧同套路）：加 Prompt 版本不必改
            # 代码，也避免把 v2 的变量喂给 v1（loader 会报"收到未声明的变量"）。
            values: dict[str, str] = {
                "graph_subgraph": subgraph.serialized,
                "text_chunks": text_chunks,
                "chat_history": "",
                "question": request.question,
            }
            declared = set(template.placeholders)
            if "as_of_date" in declared:
                # Sprint 10.4（kg_qa_v5）：日期不可得 ⇒ **喂空串**，让模板整句不出现。
                # v4 及以前喂的是字面量 "unknown"，真机实测它会被模型照抄进答案
                # ——客户看到「依据截至 unknown 的披露文件」（17 份演示文档全无日期）。
                # 降级从"说不知道"改成"不说"，信息不少（引用仍可追溯）、错误不再。
                values["as_of_date"] = as_of_date or ""
            if "as_of_source" in declared:
                values["as_of_source"] = as_of_doc_id or _AS_OF_UNKNOWN
            system_prompt = template.render(**values)
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
        #    批次 B：`_to_citation` 回查本轮注入的证据片段，
        #    回查不到的条目（LLM 编造 / 未注入的 chunk id）直接丢弃——不得进入 citations。
        citations = _build_citations(parsed.evidence, chunk_index)
        # 6b) 归因闸门（Sprint 10 批次 E）：chunk_id 合法 ≠ 依据在这条 chunk 里。
        #     撑不住答案的引用一律丢弃；全丢 ⇒ 下面按 no_grounded_evidence 拒答。
        if settings.qa_citation_gate_enabled:
            citations = _grounded_citations(parsed.answer, citations, chunk_index)
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
            reasoning_path=reasoning_path,
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
        as_of: str | None = None,
    ) -> _SubgraphResult:
        """拉取与问题相关的子图：Prompt 文本 + 结构化节点 / 关系。

        - ``scope = single_doc``（Pydantic 已保证 ``doc_id`` 非空）→ 文档子图；
        - ``scope = cross_doc``（``doc_id`` 为空）→ **全部**已导入实体图，
          对应 :meth:`GraphService.fetch_all_subgraph`（不依赖 PG ``document_id``）。

        ``as_of``（Sprint 9 批次 B2）：把它一路传给 Cypher 的时态视图，子图因此是
        **那一天的图**而不是"当下的图"。问答再说不清依据哪天，答案就无从判断
        是不是过期的信息——这正是 ADR-0005 L0 第 3 项要的答案模板前提。

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
                as_of=as_of,
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

        三个图谱 / 用量 / 路径字段在此**显式置空**，理由如下（严禁拼凑数据）：
        - ``kg_nodes`` / ``kg_relations``：拒答意味着**没有**任何支撑答案的证据，
          若把检索到的子图一并返回，前端会误以为答案有据可依；
        - ``token_usage``：拒答语义下不承担用量统计，即使 LLM 曾被调用过也不回填；
        - ``reasoning_path``：路径是**证据链**，与上面同族——拒答时给 ``None``
          （语义「未产出」），**不**给 ``[]``（那是「检索过、零命中」，
          二者语义相反，见 ``AgentQueryResponse.reasoning_path`` 的字段说明）。

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
            reasoning_path=None,
        )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _record_qa_log(
    *,
    response: AgentQueryResponse,
    request: AgentQueryRequest,
    org_id: UUID,
    db: Any,
) -> None:
    """把一次问答写入 `qa_logs`（M3 §4.3 字段表，逐字段对应；决策 **A4**）。

    - `question_hash` / `answer_hash` **只存 SHA-256**，不存原文（M3 §5.3：提问本身
      可能就是敏感信息；这不是脱敏，是压根不保存）；
    - 其余字段**取自响应体不重算**（`citation_count` / `refused` / `refusal_reason` /
      `kg_version` / `trace_id`）——重算会在两条链路上产生分叉的口径；
    - **写失败只记日志**：打点缺陷不得把已经算好的答案变成 500（同 proposal 风险 2）；
    - 这里**显式 commit**：问答链路除本表外没有任何写库动作，没有可依附的业务事务
      （请求 session 在响应体返回后即 close，不 commit 等于静默丢弃）。
    """
    if db is None:
        logger.bind(trace_id=response.trace_id).warning("qa_log_skipped_no_session")
        return

    try:
        db.add(
            QaLog(
                org_id=org_id,
                question_hash=_sha256_text(request.question),
                answer_hash=_sha256_text(response.answer),
                citation_count=len(response.citations),
                refused=response.refused,
                refusal_reason=response.refusal_reason,
                kg_version=response.kg_version,
                trace_id=UUID(str(response.trace_id)),
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 打点失败不上抛（不影响答案本体）
        logger.bind(trace_id=response.trace_id, reason=str(exc)).warning(
            "qa_log_write_failed"
        )


def _sha256_text(value: str) -> str:
    """原文 → SHA-256 hex（`qa_logs` 的两个哈希列共用，永不以明文落库）。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _to_citation(item: str, chunks: Mapping[str, EvidenceChunk]) -> Citation | None:
    """把 LLM 证据条目映射为契约 :class:`Citation`（Sprint 6 批次 B：真实回查）。

    骨架版恒返回 ``doc_id=UUID(int=0)`` / ``page=1`` / ``snippet=""`` 的占位；
    批次 B 起改为按 ``chunk_id`` 回查**本轮注入 Prompt 的证据片段**：

    - 命中 → 填真实 ``doc_id`` / ``page``（失配为 ``None``，**不**伪造 1，Q1）/ ``snippet``；
    - 未命中（LLM 编造的 id，或该 chunk 未挂 ``:Document``）→ 返回 ``None``，
      由 :func:`_build_citations` 丢弃——F3 严禁不可溯源的引用进入响应。

    **Sprint 10 批次 A（裁决 D-A / D-B / D-C）**：``char_offset`` / ``char_end`` 是
    **片段内相对偏移**（相对 ``GET /documents/{id}/chunks/{chunk_id}`` 返回的 ``text``），
    由本函数按 ``实体 char_start − chunk char_start`` **确定性换算**——
    **偏移不由模型产出**（``langextract`` 实测模型自报偏移 14/20 不符，且违反
    「数值不出 LLM」）。引用粒度双档：

    - 主档：条目形如 ``chunk-<id>#<实体提及文本>`` ⇒ 回查到实体 span，精确到该提及；
    - 回退档：无 span 命中（只给了 chunk id / 提及对不上 / span 与片段无交集）
      ⇒ ``char_offset=0`` + ``char_end=len(text)``（整段），并留 WARNING——
      **不猜、不编**，宁可高亮整段也不给一个确定而错误的偏移。

    :param chunks: ``chunk_id -> EvidenceChunk`` 索引（本轮 :meth:`fetch_evidence_chunks` 结果）
    """
    match = _CITATION_ID_PATTERN.search(item)
    if match is None:
        return None

    chunk_id = match.group(0)
    chunk = chunks.get(chunk_id)
    if chunk is None:
        logger.bind(evidence=item, chunk_id=chunk_id).warning(
            "agent_citation_chunk_not_injected"
        )
        return None
    if chunk.doc_id is None:
        # chunk 未挂 :Document → doc_id 无从得知。丢弃而非回落 UUID(int=0) 占位。
        logger.bind(chunk_id=chunk_id).warning("agent_citation_chunk_without_document")
        return None

    span = _resolve_citation_span(chunk, item)
    if span is None:
        char_offset, char_end = 0, len(chunk.text)
        logger.bind(chunk_id=chunk_id, evidence=item).warning(
            "agent_citation_span_fallback"
        )
    else:
        char_offset = max(0, span.char_start - chunk.char_start)
        char_end = min(len(chunk.text), span.char_end - chunk.char_start)

    return Citation(
        doc_id=chunk.doc_id,
        page=chunk.page,
        chunk_id=chunk_id,
        char_offset=char_offset,
        char_end=char_end,
        snippet=_snippet(chunk.text),
    )


def _resolve_citation_span(chunk: EvidenceChunk, item: str) -> EntitySpan | None:
    """把证据条目里的「实体提及文本」回查为该片段内的实体 span（D-C 主档）。

    匹配口径**只有一条**：提及文本与 :attr:`EntitySpan.mention` **相等**
    （忽略大小写与首尾空白）。刻意**不做**包含匹配 / 模糊匹配 / 编辑距离——
    那会让"引用指到哪一句"变成随语料漂移的猜测；一旦猜错，高亮位置就是
    **确定而错误**的，比回退到整段更糟（F3 / G5 诚实性）。

    span 与片段区间**无交集**时同样视为未命中（数据异常时不能拿一个片段外的
    偏移去高亮片段内的文字）。
    """
    mention = item.partition(_MENTION_SEPARATOR)[2].strip()
    if not mention:
        return None
    lowered = mention.casefold()
    for span in chunk.entity_spans:
        if span.mention.strip().casefold() != lowered:
            continue
        if span.char_end <= chunk.char_start or span.char_start >= chunk.char_end:
            continue
        return span
    return None


def _build_citations(
    evidence: Sequence[str], chunks: Mapping[str, EvidenceChunk]
) -> list[Citation]:
    """把 LLM ``evidence`` 列表转为契约引用列表（丢弃一切不可回查的条目）。"""
    citations: list[Citation] = []
    for item in evidence:
        if not _looks_like_citation(item):
            continue
        citation = _to_citation(item, chunks)
        if citation is not None:
            citations.append(citation)
    return citations


#: 答案正文里的 ``[source: <chunk_id>]`` 标记（引用覆盖率统计依赖它，正文格式不变）
_ANSWER_SOURCE_MARK_RE = re.compile(r"\[source:[^\]]*\]")

#: 答案里**可机械比对**的凭据：单号 / 工号 / 日期 / 带量纲数字。
#: 只比对这类"硬凭据"与实体提及，**不**拿整句做包含判断——答案换个说法是正常的，
#: 那会把"措辞不同"误判成"依据不存在"（误杀比漏判更伤：会白白吃掉正确答案）。
_SUPPORT_TOKEN_RE = re.compile(
    r"[A-Za-z]{1,4}-?\d[\w./:-]*"  # SO-2026-0912 / LV0001 / E001 / 10:00
    r"|\d+(?:\.\d+)?\s*(?:小时|天|次|分钟|%)"  # 36 小时 / 3 次 / 30 分钟
)


def _answer_fragments(answer: str, chunks: Mapping[str, EvidenceChunk]) -> set[str]:
    """抽出答案里能与 chunk 原文逐字比对的凭据集合。

    两类来源：
    1. 单号 / 数字（:data:`_SUPPORT_TOKEN_RE`）——「武汉光谷希尔顿酒店」不是图上实体，
       但它旁边的 ``SO-2026-0912`` 是硬凭据；只按实体名判会漏掉这类题（实测 Q12）；
    2. 本轮注入片段里的**实体提及**（``EvidenceChunk.entity_spans``）——与
       :func:`_resolve_citation_span` 同源，不需要再查库。

    取不到任何凭据 ⇒ 返回空集，闸门**放行**（没有判据就不判，绝不猜）。
    """
    cleaned = _ANSWER_SOURCE_MARK_RE.sub("", answer or "")
    fragments = {m.group(0).strip() for m in _SUPPORT_TOKEN_RE.finditer(cleaned)}
    for chunk in chunks.values():
        for span in chunk.entity_spans:
            mention = span.mention.strip()
            if len(mention) >= 2 and mention in cleaned:
                fragments.add(mention)
    return {f for f in fragments if len(f) >= 2}


def _grounded_citations(
    answer: str,
    citations: Sequence[Citation],
    chunks: Mapping[str, EvidenceChunk],
) -> list[Citation]:
    """归因闸门：丢掉「撑不住答案」的引用（Sprint 10 批次 E，用户决策 A）。

    判据：答案里的凭据（见 :func:`_answer_fragments`）**至少有一条**逐字出现在被引
    chunk 的原文里。一条都没有 ⇒ 这条引用与答案无关，属归因错。

    为什么必须丢：模型在 ``kg_qa_v4`` 下被要求"每个事实句都要带 ``[source: ...]``"，
    而依据有时**只存在于 ``graph_subgraph``**（图实体由 CSV 抽取）不在注入片段里 ⇒
    它会挂一条**不相关但合法**的 chunk 充数。客户端点开引用看到的是另一段话，
    比拒答更伤信任。

    **全丢 ⇒ 返回空列表**，由调用方走 ``no_grounded_evidence`` 拒答（语义一致：
    没有可溯源证据）。这与 F3 同口径——宁可拒答，也不给出撑不住的引用。

    注意：凭据取不到时**原样放行**（``fragments`` 为空），不做"没凭据 = 不可信"的推定。
    """
    fragments = _answer_fragments(answer, chunks)
    if not fragments:
        return list(citations)

    kept: list[Citation] = []
    for citation in citations:
        chunk = chunks.get(citation.chunk_id)
        if chunk is None:
            continue
        if any(fragment in (chunk.text or "") for fragment in fragments):
            kept.append(citation)
    if len(kept) != len(citations):
        logger.bind(
            kept=len(kept),
            dropped=len(citations) - len(kept),
            fragments=sorted(fragments)[:5],
        ).warning("agent_citation_ungrounded_dropped")
    return kept


def _snippet(text: str) -> str:
    """引用摘录（≤ ``_SNIPPET_LIMIT`` 字）；超长截断并加省略号。

    刻意**不**回传 chunk 全文（Q2）：全文由 ``GET /documents/{id}/chunks/{chunk_id}``
    按需回查，避免 ``citations`` 随答案条数线性膨胀。
    """
    stripped = text.strip()
    if len(stripped) <= _SNIPPET_LIMIT:
        return stripped
    return f"{stripped[:_SNIPPET_LIMIT]}…"


#: Prompt 里截至日期的兜底字面量。
#:
#: **只用于 ``as_of_source``**（文档 id 那一路）——``as_of_date`` 自 Sprint 10.4
#: 起（Prompt ``kg_qa_v5``）改喂**空串**：真机实测这个字面量会被模型照抄进答案，
#: 变成「依据截至 unknown 的披露文件」。降级口径因此从"照实说不知道"
#: 改成"整句不出现"，本常量只为还没适配的旧占位符保留。
_AS_OF_UNKNOWN = "unknown"


def _resolve_context_date(
    *, db: Any, org_id: UUID, doc_id: UUID | None
) -> tuple[str | None, str | None]:
    """答案模板里「依据截至 X 日的披露文件」的那个 X —— **必须能说出出处**。

    来源优先级：本次问答限定的文档 → 该租户**最新**一份已登记日期的披露文件
    （``documents.document_date``，Sprint 9 批次 A 落的列；**这就是它的消费点**——
    没有这句回填，那列只是一份"将来会用"的预留）。

    两者都取不到 ⇒ 返回 ``None``：**代码不编日期**（与抽取侧 R4 同口径），
    由模板降级为「截至日期未知」。宁可让答案说得含糊，也不能让它说得**确定而错误**。

    **查询失败同样降级为 ``None``**：截至日期是加成信息，不能让一次 DB 抖动
    拖垮整轮问答——这与既有语义一致（连 QaLog 写失败都不该影响回答）。
    """
    if db is None:
        return None, None

    from sqlalchemy import select

    from app.db.models import Document

    stmt = select(Document.id, Document.document_date).where(
        Document.org_id == org_id, Document.document_date.is_not(None)
    )
    if doc_id is not None:
        stmt = stmt.where(Document.id == doc_id)
    else:
        stmt = stmt.order_by(Document.document_date.desc())

    try:
        row = db.execute(stmt).first()
    except Exception as exc:  # noqa: BLE001 - 加成信息不允许拖垮主流程
        logger.bind(exc_type=type(exc).__name__).warning(
            "agent_query_as_of_lookup_failed"
        )
        return None, None
    if row is None:
        return None, None
    document_date = row[1]
    return document_date.isoformat(), str(row[0])


def _serialize_chunks(chunks: Sequence[EvidenceChunk]) -> str:
    """把证据片段序列化进 ``kg_qa`` Prompt 的 ``text_chunks`` 占位符。

    空列表给 ``<chunks: empty>``（与子图的 ``<graph: empty>`` 同思路）：
    让 LLM 明确「没有原文证据」，**不**留白——留白会被当成「随便答」。
    """
    if not chunks:
        return "<chunks: empty>"

    lines = [f"<chunks count={len(chunks)}>"]
    for chunk in chunks:
        page = chunk.page if chunk.page is not None else "unknown"
        lines.append(
            f"  chunk id={chunk.chunk_id} doc={chunk.doc_id} "
            f"page={page} chars=[{chunk.char_start},{chunk.char_end})"
        )
        lines.append(f"    {chunk.text}")
    lines.append("</chunks>")
    return "\n".join(lines)


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
