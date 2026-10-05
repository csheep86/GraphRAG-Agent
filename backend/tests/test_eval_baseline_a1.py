"""**A1 / L10-A1** 的护栏测试：dense top-k 基线 + 双侧判分 + 反向守卫。

本文件只覆盖**可判且必须判**的那部分：

- 纯逻辑（增益保号 / 可比性 / 检索确定性 / 判分贴回）⇒ 必须钉住；
- 真链路（LLM / 向量服务）⇒ 不在这里用单测冒充实测。

本文件**刻意不含任何 LLM 调用**——它们要在 CI 每次提交**必过**
（R-8：忽快忽慢的门禁比恒绿更伤）。每条断言都可被打桩打成红（见文末反向验证段）。
"""

from __future__ import annotations

import pytest

from app.evaluation.baseline import (
    DEFAULT_JUDGED_BY,
    RETRIEVER_BASELINE,
    RETRIEVER_GRAPH,
    BaselineSpec,
    ChunkPoolRef,
    DenseTopKRetriever,
    EmbedderUnavailable,
    OpenAICompatibleEmbedder,
    build_default_embedder,
    comparability_error,
    cosine_similarity,
    pool_fingerprint,
    rank_by_cosine,
)
from app.evaluation.metrics import AnswerRecord, CitationRef, graph_gain
from app.evaluation.runner import (
    C1_GAIN_THRESHOLD,
    RunnerContext,
    _judged_answers,
    _run_baseline_side,
    eval_graph_gain,
)


def _pool(size: int = 2, *, fingerprint: str = "fp-demo") -> ChunkPoolRef:
    return ChunkPoolRef(
        kg_version="v-demo", org_id="org-demo", fingerprint=fingerprint, size=size
    )


def _graph_spec() -> BaselineSpec:
    return BaselineSpec(
        retriever=RETRIEVER_GRAPH,
        embedding_model=None,
        embedding_dimension=None,
        pool=_pool(),
        top_k=32,
        generation_model="deepseek-chat",
        prompt_id="kg_qa_v5",
        graph_context=True,
        judged_by=DEFAULT_JUDGED_BY,
    )


def _baseline_spec(**over: object) -> BaselineSpec:
    base: dict[str, object] = {
        "retriever": RETRIEVER_BASELINE,
        "embedding_model": "text-embedding-3-large",
        "embedding_dimension": 3072,
        "pool": _pool(),
        "top_k": 32,
        "generation_model": "deepseek-chat",
        "prompt_id": "kg_qa_v5",
        "graph_context": False,
        "judged_by": DEFAULT_JUDGED_BY,
    }
    base.update(over)
    return BaselineSpec(**base)  # type: ignore[arg-type]


class _FakeEmbedder:
    """确定性 embedder：**不联网、不依赖真服务**—— pure logic 测试的可复现基石。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls = 0

    @property
    def model_id(self) -> str:
        return "fake-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vectors.get(text, [0.0, 0.0]) for text in texts]


# ---------------------------------------------------------------------------
# 反向守卫 ①：增益**保号**（基线反超不得被 abs() 抹平）
# ---------------------------------------------------------------------------


def test_graph_gain_preserves_negative_sign() -> None:
    """基线反超 ⇒ 增益必须为**负**，且在报告里看得出来（L10-A1 条款 4 反向守卫）。

    **为什么这条存在**：``(图谱 − 基线) / 基线`` 一旦有人"顺手加个 abs()"，
    基线反超就会被读成"图谱增益 12.5%"——这正是 §5.2 要挡的假绿，
    所以把符号用测试钉死，而不是靠人记得。
    """
    metric = graph_gain(0.70, 0.80)
    assert metric.value is not None
    assert metric.value < 0
    #: 保号之外还要**量级正确**：(-0.10)/0.80 = -0.125
    assert metric.value == pytest.approx(-0.125)


def test_graph_gain_positive_case_is_unaffected() -> None:
    """正常方向不受影响（防"为了保号把正增益也弄坏"）。"""
    metric = graph_gain(0.88, 0.80)
    assert metric.value == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 反向守卫 ②③④：共因冻结（k / 模型 / prompt / 池）
# ---------------------------------------------------------------------------


def test_comparable_specs_pass() -> None:
    assert comparability_error(_graph_spec(), _baseline_spec()) is None


def test_smaller_baseline_top_k_is_rejected() -> None:
    """基线 k < 图侧 ⇒ 判红（喂更少证据 ⇒ 基线分被压低 ⇒ 增益虚高）。"""
    reason = comparability_error(_graph_spec(), _baseline_spec(top_k=8))
    assert reason is not None and "k=8" in reason and "虚高" in reason


def test_different_pool_is_rejected() -> None:
    """两侧不是同一份池 ⇒ 判红（"换池"是最隐蔽的刷绿手法）。"""
    other = ChunkPoolRef(
        kg_version="v-other", org_id="org-demo", fingerprint="fp-other", size=2
    )
    reason = comparability_error(_graph_spec(), _baseline_spec(pool=other))
    assert reason is not None and "chunk 池不同" in reason


def test_different_prompt_or_model_is_rejected() -> None:
    assert (
        comparability_error(_graph_spec(), _baseline_spec(prompt_id="kg_qa_v6"))
        is not None
    )
    assert (
        comparability_error(_graph_spec(), _baseline_spec(generation_model="qwen-plus"))
        is not None
    )


def test_graph_context_must_differ() -> None:
    """唯一变量必须是"是否注入子图" ⇒ 两侧 graph_context **相同**才是异常。"""
    same_true = _baseline_spec(graph_context=True)
    assert comparability_error(_graph_spec(), same_true) is not None


# ---------------------------------------------------------------------------
# 池指纹
# ---------------------------------------------------------------------------


def test_pool_fingerprint_is_order_insensitive() -> None:
    """排列不同不该被读成"换了池"（否则 ORDER BY 一变就误判）。"""
    assert pool_fingerprint(["c2", "c1", "c3"]) == pool_fingerprint(["c1", "c2", "c3"])


def test_pool_fingerprint_detects_content_change() -> None:
    assert pool_fingerprint(["c1", "c2"]) != pool_fingerprint(["c1", "c3"])


# ---------------------------------------------------------------------------
# dense top-k 检索：确定性 / 零向量 / 缓存
# ---------------------------------------------------------------------------


def test_rank_by_cosine_is_deterministic_on_ties() -> None:
    ties: list[tuple[str, list[float]]] = [
        ("c_b", [1.0, 0.0]),
        ("c_a", [1.0, 0.0]),
    ]
    #: 同分 ⇒ 按 chunk_id 字典序升序（可复现优先，不然两次跑出两个增益）
    assert rank_by_cosine([1.0, 0.0], ties, top_k=2) == ("c_a", "c_b")


def test_cosine_of_zero_vector_is_zero_not_nan() -> None:
    """零向量 ⇒ 0.0（NaN 会污染排序，并且会产出不可复现的增益）。"""
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_retriever_is_deterministic_and_respects_top_k() -> None:
    embedder = _FakeEmbedder(
        {
            "甲 Doc問": [1.0, 0.0],
            "乙 unrelated 无关文本": [0.0, 1.0],
            "问这个吗": [1.0, 0.0],
        }
    )
    retriever = DenseTopKRetriever(embedder, top_k=1)
    pool = [
        _chunk("c_1", "甲 Doc問"),
        _chunk("c_2", "乙 unrelated 无关文本"),
    ]
    selected = retriever.retrieve("问这个吗", pool)
    assert [c.chunk_id for c in selected] == ["c_1"]
    #: 第二次同提问 ⇒ 走池缓存，不再重嵌整池（避免 N×M 次调用）
    calls_before = embedder.calls
    retriever.retrieve("问这个吗", pool)
    assert embedder.calls == calls_before + 1  # 只多嵌 1 条提问


def test_retriever_rejects_short_embedding_response() -> None:
    embedder = _FakeEmbedder({})
    retriever = DenseTopKRetriever(embedder, top_k=1)
    embedder.embed = lambda texts: [[0.0, 0.0]]  # type: ignore[method-assign]
    with pytest.raises(EmbedderUnavailable):
        retriever.retrieve("问", [_chunk("c_1", "甲"), _chunk("c_2", "乙")])


def _chunk(chunk_id: str, text: str):  # noqa: ANN202
    from uuid import uuid4

    from app.services.graphs import EvidenceChunk

    return EvidenceChunk(
        chunk_id=chunk_id,
        doc_id=str(uuid4()),
        text=text,
        page=None,
        char_start=0,
        char_end=len(text),
        entity_spans=(),
    )


# ---------------------------------------------------------------------------
# A3：人工判分（缺侧 ⇒ 不成数）
# ---------------------------------------------------------------------------


def test_judged_answers_leaves_unjudged_as_none() -> None:
    from typing import Any

    answers: tuple[Any, ...] = (
        AnswerRecord(refused=False, citations=(), correct=None, judged_by=None),
        AnswerRecord(refused=True, citations=(), correct=None, judged_by=None),
    )
    judged = _judged_answers(answers, (1, 2), {1: True}, "architect")
    assert judged[0].correct is True
    #: 未判分的题：**不入分母**（评分体系下的 None，不是 False）
    assert judged[1].correct is None
    assert judged[1].judged_by is None


def test_judged_answers_uses_item_index_not_position() -> None:
    """``answered_indices`` 就是为"跳过的失败题"准备的（错位 ⇒ 判分别人头上）。"""
    records = (
        AnswerRecord(refused=False, citations=(), correct=None, judged_by=None),
        AnswerRecord(refused=False, citations=(), correct=None, judged_by=None),
    )
    #: 实际答题是 #7 与 #9（中间 #8 挂了）
    judged = _judged_answers(records, (7, 9), {9: False}, "architect")
    assert judged[0].correct is None
    assert judged[1].correct is False


# ---------------------------------------------------------------------------
# C1 evaluator：缺依赖 ⇒ UNKNOWN，且**不给数字**
# ---------------------------------------------------------------------------


def test_offline_mode_gives_no_number() -> None:
    ctx = RunnerContext(mode="offline", git_hash="deadbeef")
    result = eval_graph_gain({"ctx": ctx})
    assert result.value is None
    assert result.blocked_by and "live" in result.blocked_by
    assert result.threshold == C1_GAIN_THRESHOLD
    assert result.threshold_source == "provisional"


def test_missing_embedding_blocks_c1_without_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配 embedding ⇒ ``_run_baseline_side`` 必须**报原因**，而不是退化成关键词检索。"""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "eval_embedding_model", "")
    monkeypatch.setattr(get_settings(), "eval_embedding_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_api_key", "dummy-key")
    ctx = RunnerContext(mode="live", git_hash="deadbeef")
    error, answers, indices = _run_baseline_side(ctx)
    assert error and "EVAL_EMBEDDING_MODEL" in error
    assert answers == () and indices == ()


def test_build_default_embedder_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置缺失必须**当场抛**（R-11），且**点名缺失的那一项**。

    ⚠️ 为什么先坐实密钥、再断言：不这样做时，"模型名缺了"会被相邻的密钥分支接住，
    判红权落到别人头上 ⇒ 把模型名校验删掉，测试**照样绿**（变异 4 实测的结论）。
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "eval_embedding_model", "")
    monkeypatch.setattr(settings, "eval_embedding_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "dummy-key")
    with pytest.raises(EmbedderUnavailable) as exc:
        build_default_embedder()
    assert "EVAL_EMBEDDING_MODEL" in str(exc.value)


def test_embedder_reports_missing_config() -> None:
    embedder = OpenAICompatibleEmbedder(model="", base_url="", api_key="k")
    with pytest.raises(EmbedderUnavailable) as exc:
        embedder.embed(["问"])
    assert "EVAL_EMBEDDING_MODEL" in str(exc.value)


def test_citation_has_span_flag_shape() -> None:
    """``CitationRef.has_span`` 的形状校验——它是 C2-a / C2-b 的共同判据输入。"""
    ref = CitationRef(chunk_id="c_1", has_span=True)
    assert ref.chunk_id == "c_1" and ref.has_span is True
