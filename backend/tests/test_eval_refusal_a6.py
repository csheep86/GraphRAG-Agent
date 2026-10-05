"""**A6 / L8（P6-B）**：C2-c 两档输出 + 拒答误伤独立判据的护栏。

**这两条在拦什么**：

1. **C2-c 的 1.00 不能把拒答缺陷盖住**（L8 明令"两条判据不许互相顶替"）。
   排除拒答档恒为 1.00，而含拒答档实测 **0.786** ⇒ **两档必须并列露出来**，
   只露一档 ⇒ 谁也不知道另一档长什么样；
2. **误伤方向必须分家**："不该拒却拒"（误伤，吃掉 C2-c 分子）与
   "该拒没拒"（漏拒，放行）后果不同，混在一个列表 ⇒ 0 阈值判据失去意义；
3. **误伤必须有自己的判据**：它当前 **FAIL（Q8）**，若只躺在 C2-c 的 detail 里，
   **没人被它拦**。

全部用例**不需要后端 / LLM / Neo4j**（桩掉 `ask_safe` 与题集）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.evaluation.criteria import CriterionStatus, Verdict
from app.evaluation.metrics import AnswerRecord, CitationRef
from app.evaluation.runner import ALL_CRITERIA, C_CITATION, C_REFUSAL, RunnerContext

_CITED = (CitationRef(chunk_id="chunk-1", has_span=True),)


@dataclass(frozen=True)
class _Item:
    index: int
    question: str
    should_refuse: bool


def _answer(*, refused: bool, cited: bool = True) -> AnswerRecord:
    return AnswerRecord(
        refused=refused,
        citations=_CITED if (cited and not refused) else (),
        correct=None,
        judged_by=None,
    )


def _response(*, refused: bool, cited: bool = True) -> dict[str, Any]:
    """桩响应：拒答 ⇒ 无引用（真实拒答就是这样）。"""
    return {
        "kg_version": "attendance-demo-v1",
        "refused": refused,
        "citations": (
            [{"chunk_id": "chunk-1", "char_offset": 0, "char_end": 10}]
            if (cited and not refused)
            else []
        ),
    }


@pytest.fixture
def qa_stub(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """桩掉「题集 + 问答」，让 `_qa_run` 走真实的分家逻辑但**不打网络 / LLM**。

    返回 `(题集, 响应表)` 的 setter，用例按需编排场景。
    """
    import app.evaluation.runner as runner

    runner._QA_CACHE.clear()
    items: list[_Item] = []
    responses: list[dict[str, Any]] = []

    def ask(_question: str, *, ctx: Any = None) -> tuple[dict[str, Any] | None, Any]:
        index = len(_asked)
        _asked.append(index)
        return responses[index], None

    _asked: list[int] = []
    monkeypatch.setattr(runner, "load_question_set", lambda: tuple(items))
    monkeypatch.setattr(runner, "ask_safe", ask)

    def setup(spec: list[tuple[bool, bool]]) -> None:
        """spec = [(should_refuse, 实际是否拒答), ...]

        ⚠️ **必须清 `_QA_CACHE`**：缓存键只有 `mode`，同一个用例里换场景若不清缓存，
        第二次拿到的还是**上一次**的快照 ⇒ 测试看似在验新场景，实际在验旧数据
        （本批实测踩到：两档都成 1.0、误伤数为 0）。
        """
        del items[:], responses[:], _asked[:]
        runner._QA_CACHE.clear()
        for i, (should, actual) in enumerate(spec):
            items.append(_Item(index=i + 1, question=f"Q{i + 1}", should_refuse=should))
            responses.append(_response(refused=actual))

    yield setup
    runner._QA_CACHE.clear()


def _run_citation(monkeypatch: pytest.MonkeyPatch, setup: Any):  # type: ignore[no-untyped-def]
    import app.evaluation.runner as runner

    ctx = RunnerContext(mode="live", git_hash="test")
    return runner.eval_citation_coverage({"ctx": ctx}), ctx


def _run_refusal() -> Any:
    import app.evaluation.runner as runner

    ctx = RunnerContext(mode="live", git_hash="test")
    return runner.eval_refusal_false_refusal({"ctx": ctx})


# --------------------------------------------------------------------------- #
# 一、两档必须**并列**输出（A6 配套第 1 条）
# --------------------------------------------------------------------------- #
def test_citation_outputs_both_bases(qa_stub: Any) -> None:
    """**含拒答那一档必须露出来**——此前两处都传 `include_refused=False` ⇒ 从未输出。"""
    #: 2 题正常作答 + 1 题拒答（预期拒答）
    qa_stub([(False, False), (False, False), (True, True)])
    result, _ = _run_citation(None, qa_stub)  # type: ignore[arg-type]

    detail = result.detail or {}
    assert detail.get("coverage_including_refused") is not None, "含拒答档必须输出"
    assert detail.get("coverage_require_span_including_refused") is not None
    assert detail["coverage_basis"].startswith("exclude_refused")
    #: 判据值仍是**排除拒答**档（L10-A6 裁决：不改行为）
    assert result.value == 1.0
    #: 含拒答档 = 2/3（拒答无引用）
    assert detail["coverage_including_refused"] == pytest.approx(2 / 3)
    assert result.verdict is Verdict.PASS


def test_citation_value_does_not_move_when_refusals_appear(qa_stub: Any) -> None:
    """**1.00 不能因拒答而动** ⇒ 它本来就看不见拒答 ⇒ **所以才要独立判据**。"""
    qa_stub([(False, False), (False, False)])
    clean, _ = _run_citation(None, qa_stub)  # type: ignore[arg-type]
    qa_stub([(False, False), (False, False), (True, True), (True, True)])
    with_refusals, _ = _run_citation(None, qa_stub)  # type: ignore[arg-type]

    assert clean.value == with_refusals.value == 1.0, "排除拒答档对拒答数不敏感"
    assert with_refusals.detail["coverage_including_refused"] < with_refusals.value, (
        "含拒答档必须更低 ⇒ 否则两档没区别，等于没输出"
    )


# --------------------------------------------------------------------------- #
# 二、误伤 / 漏拒**方向分家**
# --------------------------------------------------------------------------- #
def test_refusal_directions_are_split(qa_stub: Any) -> None:
    """误伤（不该拒却拒）与漏拒（该拒没拒）必须进**不同**列表。"""
    qa_stub(
        [
            (False, True),  # ① 误伤（Q8 同类）
            (True, False),  # ② 漏拒
            (False, False),  # ③ 正常
            (True, True),  # ④ 正常拒答
        ]
    )
    result = _run_refusal()
    detail = result.detail or {}

    assert len(detail["false_refusals"]) == 1, "只有①算误伤"
    assert detail["false_refusals"][0]["index"] == 1
    assert len(detail["missed_refusals"]) == 1, "只有②算漏拒"
    assert detail["missed_refusals"][0]["index"] == 2
    #: **判据值只数误伤** ⇒ 1（不因漏拒而变成 2）
    assert result.value == 1.0


def test_refusal_criterion_verdict(qa_stub: Any) -> None:
    """阈值 0（Sprint 6 §5.3「拒答 0 误伤」）：0 ⇒ PASS，≥1 ⇒ FAIL。"""
    qa_stub([(False, False), (True, True)])
    assert _run_refusal().verdict is Verdict.PASS
    assert _run_refusal().value == 0.0

    qa_stub([(False, True), (True, True)])
    failing = _run_refusal()
    assert failing.verdict is Verdict.FAIL, "1 条误伤必须判 FAIL（当前 Q8 就是这种）"
    assert failing.value == 1.0
    assert failing.threshold == 0.0
    assert failing.unit == "条（误伤数）"


def test_refusal_criterion_is_indeterminate_when_link_down(qa_stub: Any) -> None:
    """链路不可用 ⇒ **value=None**（0 会被读成"零误伤"）。"""
    import app.evaluation.runner as runner

    qa_stub([])
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner, "ask_safe", lambda _q, ctx=None: (None, "HTTP 500"))
    try:
        ctx = RunnerContext(mode="live", git_hash="test")
        result = runner.eval_refusal_false_refusal({"ctx": ctx})
    finally:
        monkeypatch.undo()

    assert result.value is None
    assert result.status is CriterionStatus.UNKNOWN
    assert result.verdict is Verdict.INDETERMINATE


# --------------------------------------------------------------------------- #
# 三、两条判据**不许互相顶替**（L8 的核心）
# --------------------------------------------------------------------------- #
def test_coverage_pass_and_refusal_fail_coexist(qa_stub: Any) -> None:
    """**同一次运行**：C2-c 可以 PASS，而拒答误伤**同时** FAIL ⇒ 缺陷没被盖住。

    这是本批的本体断言：若"误伤"只能靠 C2-c 的 detail 才看得到 ⇒ 它不算判据
    ⇒ 没人被拦。两条必须**各自独立成行、各判各的**。
    """
    qa_stub([(False, True), (False, False), (True, True)])  # ① 误伤
    citation, _ = _run_citation(None, qa_stub)  # type: ignore[arg-type]
    refusal = _run_refusal()

    assert citation.verdict is Verdict.PASS, "排除拒答档仍是 1.00"
    assert refusal.verdict is Verdict.FAIL, "但误伤必须独立判 FAIL"
    assert citation.criterion == C_CITATION
    assert refusal.criterion == C_REFUSAL


def test_two_criteria_share_one_qa_pass(qa_stub: Any) -> None:
    """同源 ⇒ **只跑一遍**问答（否则付两倍 LLM 调用，且两遍结果可能不一致）。"""
    import app.evaluation.runner as runner

    qa_stub([(False, True), (False, False), (True, True)])
    calls = {"n": 0}
    original = runner.ask_safe

    def counting(question: str, *, ctx: Any = None) -> Any:
        calls["n"] += 1
        return original(question, ctx=ctx)

    runner.ask_safe = counting  # type: ignore[assignment]
    try:
        _run_citation(None, qa_stub)  # type: ignore[arg-type]
        _run_refusal()
    finally:
        runner.ask_safe = original  # type: ignore[assignment]

    assert calls["n"] == 3, f"3 题只应问 3 次（实际 {calls['n']}）⇒ 别跑两遍"


def test_refusal_criterion_is_registered() -> None:
    """新判据必须登记（**不登记 = 脚本里跑了但没人知道**）。"""
    import app.evaluation.runner as runner

    assert C_REFUSAL in ALL_CRITERIA
    assert C_REFUSAL in runner._registered() or True  # 注册表在 run() 时装配
    runner._register_builtin_criteria()
    assert C_REFUSAL in runner._registered()
    #: 紧跟 C2-c ⇒ 报告里两行挨着，看得见"1.00 旁边挂着误伤"


# --------------------------------------------------------------------------- #
# 四、**归因必须随实测反推**（P6-D 的 corpus_layer，2026-10-05 补接 C2-c / 拒答）
# --------------------------------------------------------------------------- #
def test_both_criteria_report_corpus_layer(
    qa_stub: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """这两条判据的报告必须自带 ``corpus_layer``，且值来自**实测**而非写死。

    为什么单独钉这条：本判据要拿去说"Q8 在 **L2** 上如何如何"。若报告里的
    ``corpus_layer`` 是空的（或某个常量），那句话就**没有任何机器证据**支撑——
    改一行常量就能把 L1 的实测说成 L2。
    """
    import app.evaluation.runner as runner

    monkeypatch.setattr(runner, "_detect_layer", lambda versions, org: "L2")
    qa_stub([(False, False), (True, True)])

    citation, _ = _run_citation(None, qa_stub)  # type: ignore[arg-type]
    refusal = _run_refusal()
    assert citation.provenance.corpus_layer == "L2"
    assert refusal.provenance.corpus_layer == "L2"


def test_corpus_layer_is_none_when_layer_undetected(
    qa_stub: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """判不出层 ⇒ **空着**，不许兜底成 L1/L2（猜出来的层号就是假绿入口）。"""
    import app.evaluation.runner as runner

    monkeypatch.setattr(runner, "_detect_layer", lambda versions, org: None)
    qa_stub([(False, False), (True, True)])
    assert _run_refusal().provenance.corpus_layer is None
    assert ALL_CRITERIA.index(C_REFUSAL) == ALL_CRITERIA.index(C_CITATION) + 1
