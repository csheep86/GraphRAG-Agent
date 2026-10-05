"""**A1 / L10-A1**：RAG 基线（**dense top-k 向量检索**）+ 两侧可比性的机械断言。

为什么需要这个文件
------------------

C1「图谱增益 ≥10%」是**相对指标**：``(图谱 − 基线) / 基线``。
基线可以自选 ⇒ **选一个足够弱的基线就能刷出 >10%**——这与纪律
**R-9「恒绿失效」**同源：判据存在，但**绿不绿由选基线的人决定**。

因此 L10-A1 裁决的第一原则**不是"选哪个算法"**，而是**先把除检索方式以外的
所有变量钉死**，让增益只能归因于检索方式：

1. **共因冻结**：两侧同一 chunk 池（同一 ``kg_version`` + ``org_id``，用**池指纹**钉住）、
   同一 ``k``（且基线侧**不得更小**）、同一生成模型、同一 prompt 版本、同一判分口径；
2. **基线检索 = dense top-k**（**不以 BM25 为主**：BM25 在中文长文档上偏弱 ⇒
   基线分低 ⇒ 增益虚高）；
3. **分数 = 受控问题集上的答对率**（两侧都要**人工判分**，A3：脚本不自动判分）。

:class:`BaselineSpec` 就是这三条的**机器可读形式**——它进报告、`comparability_error`
拿它做前置断言，不符即 **不给数字**（``UNKNOWN``），而不是给一个"看起来达标"的值。

**反向守卫（反向守卫菜单）**——本模块故意让"刷绿"的每个入口都有一道**会红的断言**：

- 基线侧 ``k`` 小于图侧 ⇒ :func:`comparability_error` 判红；
- 两侧 prompt 版本或生成模型不同 ⇒ 判红；
- 两侧 chunk 池指纹不同 ⇒ 判红；
- 增益为负（基线反超）⇒ :mod:`app.evaluation.metrics` 的 ``graph_gain`` **保号**，
  测试钉死**不许**被 ``abs()`` 抹平。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from app.core.config import get_settings
from app.evaluation.metrics import AnswerRecord
from app.prompts.prompt_loader import load_prompt
from app.services.graphs import EVIDENCE_CHUNK_LIMIT, EvidenceChunk

#: 两侧检索方式的稳定标识（进报告；改名会让历史结论无法比对）
RETRIEVER_GRAPH = "graph_mentions"
RETRIEVER_BASELINE = "dense_top_k"

#: **A3**：判分口径标识（人按 MANIFEST 的 rubric 判，脚本不自动判分）
DEFAULT_JUDGED_BY = "architect"


class EmbedderUnavailable(RuntimeError):
    """embedding 不可用（未配置 / 依赖缺失）⇒ **不得**静默退化成关键词检索。

    为什么必须抛而不是降级：退化为关键词匹配就是把裁决选好的 dense top-k
    悄悄换成 BM25（后者在中文长文档上偏弱 ⇒ 增益虚高 ⇒ **刷绿**）。
    """


@dataclass(frozen=True)
class ChunkPoolRef:
    """chunk 池的**可比对身份**（不携带全文，便于进报告）。

    ``fingerprint`` 是「两侧同源」的唯一机器凭据：图谱侧沿 ``MENTIONS`` 做**有偏召回**
    （按实体反查 + 每文档保底），基线侧取整池做向量召回，两者的**候选集合天然不同**
    ⇒ 可比的是"池"（同一图、同一版本、同一租户），而不是"最终注入的那一小撮"。
    所以用**池指纹**而不是"注入片段集合"来钉同源。
    """

    kg_version: str
    org_id: str
    fingerprint: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kg_version": self.kg_version,
            "org_id": self.org_id,
            "fingerprint": self.fingerprint,
            "size": self.size,
        }


@dataclass(frozen=True)
class BaselineSpec:
    """**共因冻结清单**（L10-A1 条款 1 / 4）：报告必带，且参与可比性断言。"""

    retriever: str
    #: 基线侧的嵌入模型与维度（图侧为 ``None``）
    embedding_model: str | None
    embedding_dimension: int | None
    pool: ChunkPoolRef
    top_k: int
    generation_model: str
    #: 形如 ``kg_qa_v5``（**写死在 Motorola 报表里**，换 prompt 版本即不可比）
    prompt_id: str
    #: 是否把 ``graph_subgraph`` 喂进 prompt（图侧 True / 基线侧 False —— 这正是要测的变量）
    graph_context: bool
    judged_by: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "retriever": self.retriever,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "pool": self.pool.as_dict(),
            "top_k": self.top_k,
            "generation_model": self.generation_model,
            "prompt_id": self.prompt_id,
            "graph_context": self.graph_context,
            "judged_by": self.judged_by,
        }


def pool_fingerprint(chunk_ids: Iterable[str]) -> str:
    """池指纹（**顺序无关**）：chunk id 排序后取 SHA-256 前 16 位。

    顺序无关才有意义——同一池因 ORDER BY 不同产生的排列差异不该被读成"换池"。
    """
    joined = "\n".join(sorted(str(cid) for cid in chunk_ids))
    return sha256(joined.encode("utf-8")).hexdigest()[:16]


def comparability_error(graph: BaselineSpec, baseline: BaselineSpec) -> str | None:
    """两侧是否可比：**不符返回原因**（调用方据此降级为 ``UNKNOWN``，**不给数字**）。

    这是 L10-A1 条款 4 反向守卫的执行点。返回 ``None`` = 可比。

    为什么"不可比就不给数字"而不是给个打折的值：打了折的增益**长得跟真的一样**，
    日后没人分得清它掺了多少噪声——那正是 §5.2 防假绿要挡的东西。
    """
    if graph.pool.fingerprint != baseline.pool.fingerprint:
        return (
            "两侧 chunk 池不同（图谱侧 "
            f"{graph.pool.fingerprint} / {graph.pool.size} 条 vs 基线侧 "
            f"{baseline.pool.fingerprint} / {baseline.pool.size} 条）⇒ 增益不纯粹来自检索"
        )
    if baseline.top_k < graph.top_k:
        return (
            f"基线侧 k={baseline.top_k} 小于图侧 k={graph.top_k}"
            "（给基线喂更少的证据 ⇒ 基线分被压低 ⇒ 增益虚高）"
        )
    if baseline.prompt_id != graph.prompt_id:
        return f"两侧 prompt 版本不同（{graph.prompt_id} vs {baseline.prompt_id}）"
    if baseline.generation_model != graph.generation_model:
        return f"两侧生成模型不同（{graph.generation_model} vs {baseline.generation_model}）"
    if graph.graph_context == baseline.graph_context:
        return (
            "两侧 graph_context 一致（图谱大于制造商 Facts 应当仅在图侧注入子图）"
            "⇒ 唯一变量未隔离"
        )
    return None


class Embedder(Protocol):
    """向量化接口（评测侧自建，**不是** ADR-0004 的接缝 ⇒ 不进 `check_seams`）。"""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]: ...


class OpenAICompatibleEmbedder:
    """OpenAI 兼容的 ``/embeddings`` 客户端。

    **为什么复用现有依赖**：`langchain-openai` 已是项目依赖（`ChatOpenAI` 的提供者），
    其 ``OpenAIEmbeddings`` 支持 ``base_url`` 指向任意兼容网关 ⇒ **零新增依赖**，
    符合 A1「优先复用现有 LLM 客户端」的要求。
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._dimension: int | None = None

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimension(self) -> int | None:
        """实测维度（首次 ``embed`` 后可知；未知时为 ``None``，**不猜**）。"""
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]:
        if not self._model:
            raise EmbedderUnavailable(
                "未配置 eval_embedding_model（EVAL_EMBEDDING_MODEL）"
            )
        if not self._api_key:
            raise EmbedderUnavailable(
                "未配置 embedding 密钥（EVAL_EMBEDDING_API_KEY 或 LLM_API_KEY）"
            )
        try:
            from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415 - 延迟导入
        except Exception as exc:  # noqa: BLE001 - 依赖缺失要转成可诊断的错
            raise EmbedderUnavailable(f"langchain_openai 不可用: {exc!r}") from exc

        client = OpenAIEmbeddings(
            model=self._model,
            base_url=self._base_url or None,
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            #: **必须关掉**（P6-F 实测）：默认为 ``True`` 时 langchain 会先用 tiktoken
            #: 把文本切成一个个 token id，再把**这笔 token id 数组**当 ``input`` 发给
            #: ``/embeddings``。OpenAI 自家服务认这个格式，但**OpenAI 兼容网关普遍不认**
            #: （本批实测本地服务直接 ``422 Input should be a valid string``）。
            #:
            #: 关掉它还有一个**更安全**的副作用：原本超过上下文长度的文本会被 langchain
            #: **静默跳过** ⇒ 返回条数会少于输入条数，而 chunk_id 是按位置对齐的
            #: ⇒ 整批向量会**错位**。关掉后超长文本整段发给服务端由服务端处理，
            #: 少条数的情况会由 :func:`EmbedderUnavailable` 显式炸出来，**不会静默错位**。
            check_embedding_ctx_length=False,
        )
        vectors = client.embed_documents(list(texts))
        if vectors:
            self._dimension = len(vectors[0])
        return vectors


def build_default_embedder() -> OpenAICompatibleEmbedder:
    """按 Settings 装配默认 embedder（**不缓存**：换 env 必须立刻生效）。

    **Fail-fast（R-11）**：模型 / 密钥缺失在此即抛，不等到"已经跑了十几道题"
    才发现 ⇐ 那时的失败既贵又难归因。
    """
    settings = get_settings()
    if not settings.eval_embedding_model:
        raise EmbedderUnavailable(
            "未配置 EVAL_EMBEDDING_MODEL（嵌入模型与对话模型必然不同，无默认值可用）"
        )
    if not (settings.eval_embedding_api_key or settings.llm_api_key):
        raise EmbedderUnavailable(
            "未配置 embedding 密钥（EVAL_EMBEDDING_API_KEY 或 LLM_API_KEY）"
        )
    return OpenAICompatibleEmbedder(
        model=settings.eval_embedding_model,
        base_url=settings.eval_embedding_base_url or settings.llm_base_url,
        api_key=settings.eval_embedding_api_key or settings.llm_api_key,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """余弦相似度（**手写**：本项目无 numpy，且别为一个评测引入科学计算栈）。

    零向量 ⇒ 0.0（**不**算 NaN：NaN 会把排序打乱成不确定顺序）。
    """
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return dot / (norm_l * norm_r)


def rank_by_cosine(
    question_vector: Sequence[float],
    pool_vectors: Sequence[tuple[str, Sequence[float]]],
    top_k: int,
) -> tuple[str, ...]:
    """按余弦相似度取 top-k（**确定性**）。

    **并列怎么办**：同分时按 ``chunk_id`` **字典序升序** ——召回结果必须可复现，
    否则同一份代码两次跑出两个不同的增益，而差值其实是纯随机误差。
    """
    if top_k <= 0 or not pool_vectors:
        return ()
    scored = [
        (chunk_id, cosine_similarity(question_vector, vector))
        for chunk_id, vector in pool_vectors
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return tuple(chunk_id for chunk_id, _score in scored[:top_k])


class DenseTopKRetriever:
    """**dense top-k**：把整池向量化，对本轮提问做余弦召回。"""

    def __init__(self, embedder: Embedder, *, top_k: int) -> None:
        self._embedder = embedder
        self._top_k = top_k
        #: 池向量缓存（键 = 池指纹）：同一批问答共享一次整池嵌入，
        #: 否则每题都重嵌整池 ⇒ N×M 次调用，跑一次评测就是一笔冤枉钱。
        self._pool_cache: dict[str, list[Sequence[float]]] = {}

    @property
    def top_k(self) -> int:
        return self._top_k

    def retrieve(
        self, question: str, pool: Sequence[EvidenceChunk]
    ) -> tuple[EvidenceChunk, ...]:
        if not pool:
            return ()
        key = pool_fingerprint(chunk.chunk_id for chunk in pool)
        if key not in self._pool_cache:
            #: 整池**一次批嵌** ⇒ 同批向量必然出自同一模型版本
            vectors = self._embedder.embed([chunk.text for chunk in pool])
            if len(vectors) != len(pool):
                raise EmbedderUnavailable(
                    f"embedding 返回 {len(vectors)} 条，期望 {len(pool)} 条"
                )
            self._pool_cache[key] = list(vectors)
        pool_vectors = [
            (chunk.chunk_id, self._pool_cache[key][i]) for i, chunk in enumerate(pool)
        ]
        question_vectors = self._embedder.embed([question])
        if not question_vectors:
            raise EmbedderUnavailable("embedding 未返回提问向量")
        selected = rank_by_cosine(question_vectors[0], pool_vectors, self._top_k)
        index = {chunk.chunk_id: chunk for chunk in pool}
        #: 输出按**召回序**（相似度降序）——与 LLM「越靠前越重要」的先验一致
        return tuple(index[cid] for cid in selected if cid in index)


def build_pool_ref(
    *, kg_version: str, org_id: str, chunks: Sequence[EvidenceChunk]
) -> ChunkPoolRef:
    """构造池身份（两侧各自调用 ⇒ 指纹不同即为**换了池**）。"""
    return ChunkPoolRef(
        kg_version=kg_version,
        org_id=org_id,
        fingerprint=pool_fingerprint(chunk.chunk_id for chunk in chunks),
        size=len(chunks),
    )


async def answer_with_dense(
    *,
    question: str,
    evidence_chunks: Sequence[EvidenceChunk],
    trace_id: str = "eval-baseline",
) -> AnswerRecord:
    """用**基线检索到的证据**走一遍生成，产出与图侧同形状的 :class:`AnswerRecord`。

    **为什么不在这里新写一套生成逻辑**：两侧必须共用同一份 Prompt、同一个 ChatModel、
    同一个解析器、同一个引用回查与归因闸门，"唯一变量 = 检索方式"才有可能成立。
    自己再写一遍会多出若干无意识的差异，届时增益无从归因
    ⇒ 故此处**逐项 import 复用**产品侧的 helper（含私有件），而不是重写。

    ⚠️ **已知残留变量（如实登记，不在本批洗白）**：``as_of_date`` 走 ``db=None`` 口径
    （图侧经 HTTP 路由会带真实 DB session）。当前演示语料**全部无 ``document_date``**
    ⇒ 两侧都解析为 ``None`` ⇒ 渲染结果相同；一旦语料有日期两侧就会漂移，
    届时须把 db session 一并接进来。该差异写进 C1 报告的 ``notes``。

    :raises EmbedderUnavailable: 嵌入不可用（**不**退化为关键词检索）
    """
    from uuid import uuid4  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415
    from app.evaluation.metrics import CitationRef  # noqa: PLC0415
    from app.services.agents import (  # noqa: PLC0415
        AgentService,
        _build_citations,
        _grounded_citations,
        _parse_llm_answer,
        _serialize_chunks,
    )

    settings = get_settings()
    template = load_prompt("kg_qa")
    values: dict[str, str] = {
        #: **graph_context=False**：基线侧**不**注入子图 —— 这就是要测的那个变量
        "graph_subgraph": "",
        "text_chunks": _serialize_chunks(evidence_chunks),
        "chat_history": "",
        "question": question,
    }
    declared = set(template.placeholders)
    if "as_of_date" in declared:
        values["as_of_date"] = ""
    if "as_of_source" in declared:
        values["as_of_source"] = ""

    agent = AgentService()
    #: **P6-F（2026-10-05）**：必须先**显式装配** LLM 客户端。
    #:
    #: 产品侧 ``_invoke_chat_with_retry`` 直接用 ``self._chat``，却**从不**调用幂等的
    #: ``_ensure_chat()`` ⇒ 经 HTTP 路由时没事（路由层已 ensure 过），
    #: 但在**评测进程**里直接调用会炸 ``AttributeError: 'NoneType' object has no attribute
    #: 'ainvoke'``，且这个异常不是 ``AgentUnavailableError`` ⇒ 上层完全读不出真原因。
    #:
    #: ⚠️ **根因留在产品侧未修**（本批 Non-goals 第 6 条：不动被测链路），
    #: 已在集成日志登记为待修缺陷：**任何绕开 HTTP 路由的调用都会踩到**。
    #: 此处补装配 ⇒ 失败时抛 ``AgentUnavailableError``，能被 translated 成可读的
    #: ``blocked_by``，而不是 AttributeError。
    agent._ensure_chat()

    raw_answer, _token_usage = await agent._invoke_chat_with_retry(
        system_prompt=template.render(**values),
        question=question,
        trace_id=trace_id or uuid4().hex,
    )
    parsed = _parse_llm_answer(raw_answer)
    chunk_index = {chunk.chunk_id: chunk for chunk in evidence_chunks}
    citations = _build_citations(parsed.evidence, chunk_index)
    if settings.qa_citation_gate_enabled:
        citations = _grounded_citations(parsed.answer, citations, chunk_index)
    return AnswerRecord(
        refused=not citations,
        citations=tuple(
            CitationRef(
                chunk_id=str(item.chunk_id),
                has_span=int(item.char_end or 0) > int(item.char_offset or 0),
            )
            for item in citations
        ),
        correct=None,
        judged_by=None,
        #: **判分留证**（P6-F）：与图侧同口径，不参与任何判据计算。
        #: 注意这里是 ``parsed.answer``（清洗后的作答正文），**不是**未经解析的 raw。
        answer_text=parsed.answer,
    )


def prompt_id(name: str = "kg_qa") -> str:
    """当前生效 prompt 的稳定标识（``kg_qa_v5`` 这种形式）。"""
    template = load_prompt(name)
    return f"{template.name}_v{template.version}"


def graph_side_spec(*, pool: ChunkPoolRef, judged_by: str | None) -> BaselineSpec:
    """图侧的共因清单（基线侧必须与它可比，见 :func:`comparability_error`）。"""
    settings = get_settings()
    return BaselineSpec(
        retriever=RETRIEVER_GRAPH,
        embedding_model=None,
        embedding_dimension=None,
        pool=pool,
        top_k=EVIDENCE_CHUNK_LIMIT,
        generation_model=settings.llm_model,
        prompt_id=prompt_id(),
        graph_context=True,
        judged_by=judged_by,
    )


def baseline_side_spec(
    *,
    pool: ChunkPoolRef,
    embedder: Embedder,
    top_k: int,
    judged_by: str | None,
) -> BaselineSpec:
    """基线侧的共因清单（``retriever`` 与图侧不同 ⇒ 这就是唯一变量）。"""
    settings = get_settings()
    return BaselineSpec(
        retriever=RETRIEVER_BASELINE,
        embedding_model=embedder.model_id,
        embedding_dimension=getattr(embedder, "dimension", None),
        pool=pool,
        top_k=top_k,
        generation_model=settings.llm_model,
        prompt_id=prompt_id(),
        graph_context=False,
        judged_by=judged_by,
    )


__all__ = [
    "DEFAULT_JUDGED_BY",
    "BaselineSpec",
    "ChunkPoolRef",
    "DenseTopKRetriever",
    "Embedder",
    "EmbedderUnavailable",
    "EVIDENCE_CHUNK_LIMIT",
    "OpenAICompatibleEmbedder",
    "RETRIEVER_BASELINE",
    "RETRIEVER_GRAPH",
    "answer_with_dense",
    "baseline_side_spec",
    "build_default_embedder",
    "build_pool_ref",
    "comparability_error",
    "cosine_similarity",
    "graph_side_spec",
    "pool_fingerprint",
    "prompt_id",
    "rank_by_cosine",
]
