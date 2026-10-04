"""G-25 / DR-B8：**C2-a / C2-b 的 CI 门禁**（只判不退化）——护栏本体。

**为什么必须有这个文件**：``app/evaluation/gate.py`` 是纯逻辑，但**纯逻辑没人调就不算护栏**。
本文件一半用例**不需要 Neo4j**（构造 ``CriterionResult`` 直接判），把"退化 ⇒ 红"钉死；
另一半是**真图端到端**（沿用 P3-B 的口径：不可达 ⇒ **fail**，不许 skip 糊过去）。

**它不判什么**：**不判达标**（召回 ≥ 0.80 / 误报 ≤ 0.15 归 P6，且要等 A8 扩标）。
CI 只判不退化——卡绝对阈值会让召回在 0.80 附近抖动时随机红（flaky 门禁比恒绿更伤）。
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from app.evaluation.criteria import (
    CriterionResult,
    CriterionStatus,
    Provenance,
    Verdict,
)
from app.evaluation.gate import (
    DEFAULT_TOLERANCE,
    DIRECTIONS,
    build_baseline,
    direction_of,
    evaluate_gate,
    load_baseline,
)

C_RECALL = "c2_a_hidden_relation_recall"
C_FPR = "c2_b_false_positive_rate"

_GRAPH_ENV = (
    "GRAPH_REAL_NEO4J_URI",
    "GRAPH_REAL_NEO4J_USER",
    "GRAPH_REAL_NEO4J_PASSWORD",
)
_REAL_GRAPH = all(os.environ.get(name) for name in _GRAPH_ENV)
_SKIP_REASON = (
    f"需要真 Neo4j（设 {_GRAPH_ENV}）；CI 由 job env 注入。"
    "没有它就判不了「真图上的检出能力」——不许 skip 蒙混"
)


def _result(
    criterion: str,
    value: float | None,
    *,
    status: CriterionStatus = CriterionStatus.MEASURED_PROVISIONAL,
    gold_count: int = 9,
    detected_count: int | None = 9,
    threshold: float | None = None,
    verdict: Verdict | None = None,
) -> CriterionResult:
    """构造一条判据结果（**只用公开字段**，不碰 evaluator）。"""
    return CriterionResult(
        criterion=criterion,
        status=status,
        value=value,
        provenance=Provenance(
            dataset_version="gold-affiliation-v1",
            mode="live",
            git_hash="test",
            kg_version="affiliation-demo-v1",
        ),
        threshold=threshold,
        #: ``threshold_source`` 只在**有阈值**时才给（``CriterionResult`` 构造即校验）
        threshold_source="provisional" if threshold is not None else None,
        verdict=verdict,
        detail={"gold_count": gold_count, "detected_count": detected_count},
    )


def _baseline(**values: float) -> dict[str, float]:
    return dict(values)


# --------------------------------------------------------------------------- #
# 纯逻辑（**不需要 Neo4j**）
# --------------------------------------------------------------------------- #
def test_gate_passes_when_no_regression() -> None:
    """与基线一致 ⇒ 通过（且**确实做了比对**，不是空跑）。"""
    outcome = evaluate_gate(
        [_result(C_RECALL, 1.0), _result(C_FPR, 0.0)],
        baseline=_baseline(**{C_RECALL: 1.0, C_FPR: 0.0}),
    )
    assert outcome.ok
    assert len(outcome.compared) == 2, "没做比对 ⇒ 门禁是空的"


def test_gate_fails_on_recall_regression() -> None:
    """召回下降超容差 ⇒ 红。这是 G-25 的**主判据**（检出能力退化）。"""
    outcome = evaluate_gate(
        [_result(C_RECALL, 0.5)],
        baseline=_baseline(**{C_RECALL: 1.0}),
    )
    assert not outcome.ok
    assert outcome.exit_code == 1
    assert "退化" in outcome.failures[0]


def test_gate_fails_on_fpr_regression() -> None:
    """误报率**上升**也算退化（方向不同，不能照抄召回的判法）。"""
    outcome = evaluate_gate(
        [_result(C_FPR, 0.4)],
        baseline=_baseline(**{C_FPR: 0.0}),
    )
    assert not outcome.ok
    assert "退化" in outcome.failures[0]


def test_gate_tolerates_small_delta() -> None:
    """容差内的抖动 ⇒ **不红**（防 flaky：边界抖动比恒绿更伤）。"""
    outcome = evaluate_gate(
        [_result(C_RECALL, 1.0 - DEFAULT_TOLERANCE / 2)],
        baseline=_baseline(**{C_RECALL: 1.0}),
    )
    assert outcome.ok


def test_gate_fails_when_value_is_none() -> None:
    """没测出来 ⇒ **红**。「Neo4j 不可达 ⇒ 门禁恒绿」是 R-9 恒绿失效的翻版。"""
    outcome = evaluate_gate(
        [_result(C_RECALL, None, status=CriterionStatus.UNKNOWN)],
        baseline=_baseline(**{C_RECALL: 1.0}),
    )
    assert not outcome.ok
    assert "没有测量值" in outcome.failures[0]


def test_gate_fails_when_baseline_entry_missing() -> None:
    """基线缺项 ⇒ **红**：不许"基线里没有就跳过比对"（跳过 = 这条没有门禁）。"""
    outcome = evaluate_gate([_result(C_RECALL, 1.0)], baseline={})
    assert not outcome.ok
    assert "不许跳过比对" in outcome.failures[0]


def test_gate_fails_on_empty_graph() -> None:
    """**空图守卫**：gold 非空而检测产出 0 疑点 ⇒ 红，且**直说种子语料没导入**。

    空图 ⇒ 召回 0 ⇒ 会红成"退化"，但报错必须指向**真正的原因**，否则排查方向错。
    """
    outcome = evaluate_gate(
        [_result(C_RECALL, 0.0, detected_count=0)],
        baseline=_baseline(**{C_RECALL: 1.0}),
    )
    assert not outcome.ok
    assert "空图守卫" in outcome.failures[0]


def test_gate_does_not_fail_when_below_threshold() -> None:
    """**不达标 ⇒ 不红**（CI 只判不退化）：达标判定归 P6 + A8 扩标后。"""
    outcome = evaluate_gate(
        [
            _result(
                C_RECALL,
                0.5,
                threshold=0.80,
                verdict=Verdict.FAIL,
            )
        ],
        baseline=_baseline(**{C_RECALL: 0.5}),
    )
    assert outcome.ok, f"不达标不应判红：{outcome.failures}"
    assert outcome.warnings, "不达标至少要留一条 warning"


def test_direction_must_be_registered() -> None:
    """未登记方向的判据**不得**进 CI 门禁（方向不明就没法判退化）。"""
    assert C_RECALL in DIRECTIONS and C_FPR in DIRECTIONS
    assert direction_of(C_RECALL) is True
    assert direction_of(C_FPR) is False
    with pytest.raises(KeyError):
        direction_of("some_unregistered_criterion")


def test_baseline_roundtrip(tmp_path: Path) -> None:
    """基线可写可读，且**只收实测值**（None 不入基线 ⇒ 不会造出"缺项恒红"）。"""
    path = tmp_path / "baseline.json"
    payload = build_baseline(
        [_result(C_RECALL, 1.0), _result(C_FPR, None, status=CriterionStatus.UNKNOWN)],
        git_hash="abc123",
    )
    assert payload["criteria"] == {C_RECALL: 1.0}
    path.write_text(
        __import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    assert load_baseline(path) == {C_RECALL: 1.0}


# --------------------------------------------------------------------------- #
# 真图端到端（**需要真 Neo4j**；CI 由 job env 注入）
# --------------------------------------------------------------------------- #
@pytest.fixture
def real_graph(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """把 Neo4j 指向**真图库**（其余用例走"不可达"的确定性降级）。

    ⚠️ **teardown 必须再 ``reset()`` 一次**：``GraphService`` 是单例，缓存了 driver；
    只靠 monkeypatch 还原 settings **不会**让它重连。漏掉这一步 ⇒ 后续
    「Neo4j 不可达 ⇒ 501」的那几条用例会**连上真库**而失败——
    症状是"别人的用例红了"，排查方向完全错（本批实测踩到：3 条 501 用例被带红）。
    """
    from app.core.config import get_settings
    from app.services.graphs import GraphService

    settings = get_settings()
    monkeypatch.setattr(settings, "neo4j_uri", os.environ[_GRAPH_ENV[0]])
    monkeypatch.setattr(settings, "neo4j_user", os.environ[_GRAPH_ENV[1]])
    monkeypatch.setattr(settings, "neo4j_password", os.environ[_GRAPH_ENV[2]])
    GraphService.reset()
    yield
    GraphService.reset()


@pytest.mark.skipif(not _REAL_GRAPH, reason=_SKIP_REASON)
def test_g25_real_graph_detection_is_not_empty(real_graph: None) -> None:
    """真图 + **受控种子语料** ⇒ 检测必须真的产出疑点。

    为什么必须真跑：`AffiliationService().detect()` 只读 Neo4j（零 LLM / 零 HTTP），
    2.72 秒出真值 ⇒ 这是唯一能拦住「**检出能力退化**」的办法——
    用真机输出快照离线复算**拦不住**（算法坏了、喂的还是旧快照 ⇒ 算出来还是旧值）。

    ⚠️ 本条**只**断言"出真值且不少于 gold 组数"；**退化判定**（与基线比）由 CI 的
    `--gate` 步骤负责——两者分工：这里证"链路真的在测"，那里判"有没有退化"。
    """
    from app.evaluation.dataset import load_affiliation_gold, load_affiliation_meta
    from app.services.kg import AffiliationService

    #: **A8**：用 **v2 扩标语料**（200/500/100/20）——v1 只有 9 组，
    #: 即便满分其 95% 下界也只有 0.717 ⇒ **判不出**达标（UNDERPOWERED）。
    meta = load_affiliation_meta("v2")
    gold = load_affiliation_gold("v2")
    findings = AffiliationService().detect(
        kg_version=str(meta["kg_version"]),
        org_id=UUID(str(meta["org_id"])),
        limit=500,
    )
    assert len(findings) >= len(gold), (
        f"真图上只检出 {len(findings)} 组疑点，gold 有 {len(gold)} 组 ⇒ "
        "种子语料没导入、或检出能力已退化"
    )
