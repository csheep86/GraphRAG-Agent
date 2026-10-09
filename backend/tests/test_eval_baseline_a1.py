"""**A1 / L10-A1** 的护栏测试：dense top-k 基线 + 双侧判分 + 反向守卫。

本文件只覆盖**可判且必须判**的那部分：

- 纯逻辑（增益保号 / 可比性 / 检索确定性 / 判分贴回）⇒ 必须钉住；
- 真链路（LLM / 向量服务）⇒ 不在这里用单测冒充实测。

本文件**刻意不含任何 LLM 调用**——它们要在 CI 每次提交**必过**
（R-8：忽快忽慢的门禁比恒绿更伤）。每条断言都可被打桩打成红（见文末反向验证段）。
"""

from __future__ import annotations

from typing import Any

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
    eval_multihop_accuracy,
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


# ---------------------------------------------------------------------------
# P6-S：双侧共因清单与可比性断言**必须早于人工判分**可见
# ---------------------------------------------------------------------------


def _live_snapshot() -> Any:
    """一次"已经有答案、还没有判分"的问答快照（无 LLM / 无网络）。"""
    from app.evaluation.runner import _QaRun

    answers = tuple(
        AnswerRecord(
            refused=False,
            citations=(CitationRef(chunk_id=f"c_{i}", has_span=True),),
            correct=None,
            judged_by=None,
        )
        for i in (1, 2)
    )
    return _QaRun(
        answers=answers,
        answered_indices=(1, 2),
        false_refusals=(),
        missed_refusals=(),
        failures=(),
        kg_versions=("attendance-demo-v1",),
        asked=2,
    )


def _patch_deps(monkeypatch: pytest.MonkeyPatch, *, comparable: bool) -> list[str]:
    """把下游依赖换成替身；返回**调用记录**（用于断言"没乱花钱"）。"""
    calls: list[str] = []
    monkeypatch.setattr("app.evaluation.runner._qa_run", lambda _ctx: _live_snapshot())
    monkeypatch.setattr(
        "app.evaluation.runner._build_embedder_or_none", lambda: object()
    )
    #: 不可比那一档：**故意**把基线侧 k 压到 8（< 图侧 32）——正是 A1 反向守卫要拦的
    base_spec = _baseline_spec() if comparable else _baseline_spec(top_k=8)
    monkeypatch.setattr(
        "app.evaluation.runner._load_pool_and_specs",
        lambda _ctx, _embedder: (_graph_spec(), base_spec, _pool(), ()),
    )

    def _fake_baseline(_ctx: object) -> tuple:  # type: ignore[type-arg]
        calls.append("baseline_side")
        raise AssertionError("不可比时不该跑到基线侧（那 40 次 LLM 是白花钱）")

    monkeypatch.setattr("app.evaluation.runner._run_baseline_side", _fake_baseline)
    return calls


def test_missing_judgement_still_reports_both_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**本批的核心**：没判分 ⇒ 不给数字，但两侧怎么比的必须**看得见**。

    为什么必须钉：原先 spec 排在判分闸门之后 ⇒ 人工判完 80 题才发现两侧不可比
    ⇒ 人工劳动全部作废，且期间报告里连"怎么比的"一个字都没有。
    """
    _patch_deps(monkeypatch, comparable=True)
    #: 缺判分这一档要走到「已跑到基线侧」：替身放回成功能的版本
    monkeypatch.setattr(
        "app.evaluation.runner._run_baseline_side",
        lambda _ctx: (None, _live_snapshot().answers, (1, 2)),
    )
    result = eval_graph_gain({"ctx": RunnerContext(mode="live", git_hash="deadbeef")})

    assert result.value is None
    assert result.blocked_by and "判分" in result.blocked_by
    detail = result.detail or {}
    assert detail["graph_spec"]["retriever"] == RETRIEVER_GRAPH
    assert detail["baseline_spec"]["retriever"] == RETRIEVER_BASELINE
    #: 同源性读点：两侧的 k / 生成模型 / prompt 版本必须逐字一致（D4）
    assert detail["graph_spec"]["top_k"] == detail["baseline_spec"]["top_k"]
    assert (
        detail["graph_spec"]["generation_model"]
        == detail["baseline_spec"]["generation_model"]
    )
    assert detail["graph_spec"]["prompt_id"] == detail["baseline_spec"]["prompt_id"]


def test_incomparable_blocks_before_running_baseline_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可比 ⇒ **先**报不可比，且。**不许**再去跑一遍注定作废的基线侧（省钱 + 早失败）。"""
    calls = _patch_deps(monkeypatch, comparable=False)
    result = eval_graph_gain({"ctx": RunnerContext(mode="live", git_hash="deadbeef")})

    assert result.value is None
    assert result.blocked_by and "L10-A1 反向守卫" in result.blocked_by
    assert result.detail and result.detail["baseline_spec"]["top_k"] == 8
    assert calls == []


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


# ---------------------------------------------------------------------------
# P6-T：出数那一趟必须留下「被判答案的原文」（D2 / 判据 4 + D3 多跳）
# ---------------------------------------------------------------------------


def _snapshot_with_text() -> Any:
    """带**答案原文**的问答快照——出数分支要留证的正是这条原文。"""
    from app.evaluation.runner import _QaRun

    answers = tuple(
        AnswerRecord(
            refused=False,
            citations=(CitationRef(chunk_id=f"c_{i}", has_span=True),),
            correct=None,
            judged_by=None,
            answer_text=f"图侧答案原文-{i}",
        )
        for i in (1, 2)
    )
    return _QaRun(
        answers=answers,
        answered_indices=(1, 2),
        false_refusals=(),
        missed_refusals=(),
        failures=(),
        kg_versions=("attendance-demo-v1",),
        asked=2,
    )


def test_c1_number_carries_answer_texts_on_both_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """出数那一趟：detail **必须**带两侧答案原文。

    为什么必须钉：判分是在 P6-S 定格的那份答卷上做的，而出数会**重新生成答案**。
    报告里没有原文 ⇒ 「人判的 80 条」是否就是「出数这趟的 80 条」**无从证明**
    ⇒ 判据 4（不许判在别人头上）会变成一句空话。
    """
    _patch_deps(monkeypatch, comparable=True)
    monkeypatch.setattr(
        "app.evaluation.runner._qa_run", lambda _ctx: _snapshot_with_text()
    )
    monkeypatch.setattr(
        "app.evaluation.runner._run_baseline_side",
        lambda _ctx: (None, _snapshot_with_text().answers, (1, 2)),
    )
    ctx = RunnerContext(
        mode="live",
        git_hash="deadbeef",
        #: 基线侧**必须 > 0**：`graph_gain` 的分母是基线分，≤ 0 ⇒ 增益无定义（A7）
        judgements={1: True, 2: True},
        baseline_judgements={1: True, 2: False},
        judged_by="architect",
    )
    result = eval_graph_gain({"ctx": ctx})

    assert result.value is not None
    detail = result.detail or {}
    graph_rows = detail["answer_texts_graph"]
    baseline_rows = detail["answer_texts_baseline"]
    assert [row["index"] for row in graph_rows] == [1, 2]
    assert [row["index"] for row in baseline_rows] == [1, 2]
    assert all(row["answer"] for row in graph_rows + baseline_rows)


def _fake_ask(_question: str, ctx: object) -> tuple[dict[str, Any], None]:  # noqa: ARG001
    """多跳的问答替身：只回一条**带原文**的答案（不碰网络 / 不碰 LLM）。"""
    return (
        {
            "answer": "多跳答案原文",
            "refused": False,
            "citations": [{"chunk_id": "c_1", "char_offset": 0, "char_end": 9}],
        },
        None,
    )


def test_multihop_without_judgement_exposes_answer_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多跳缺判分时**必须**吐答案原文（D3：人不该盲判）。

    原先 detail 只有 ``{"asked": 6, "judged": 0}`` ⇒ 人拿着它无从判分。
    """
    monkeypatch.setattr("app.evaluation.runner.ask_safe", _fake_ask)
    result = eval_multihop_accuracy(
        {"ctx": RunnerContext(mode="live", git_hash="deadbeef")}
    )

    assert result.value is None
    assert result.blocked_by and "A3" in result.blocked_by
    rows = (result.detail or {})["answer_texts"]
    assert len(rows) == 6  # gold-multihop-v1 = 6 题
    assert [row["index"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert all(row["answer"] for row in rows)


def test_multihop_number_carries_answer_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多跳出数那一趟同样要留原文（与 C1 同口径：判分与出数同源可复核）。"""
    from types import SimpleNamespace

    from app.evaluation.dataset import load_multihop_set

    judged = [
        SimpleNamespace(
            index=item.index,
            question=item.question,
            correct=True,
            judged_by="architect",
        )
        for item in load_multihop_set()
    ]
    monkeypatch.setattr("app.evaluation.runner.load_multihop_set", lambda: judged)
    monkeypatch.setattr("app.evaluation.runner.ask_safe", _fake_ask)
    result = eval_multihop_accuracy(
        {"ctx": RunnerContext(mode="live", git_hash="deadbeef")}
    )

    assert result.value == 1.0
    rows = (result.detail or {})["answer_texts"]
    assert len(rows) == 6 and all(row["answer"] for row in rows)
