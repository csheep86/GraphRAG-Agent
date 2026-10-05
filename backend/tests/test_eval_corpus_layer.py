"""**P6-D · T4**：``corpus_layer`` 必须**随实测反推**，不许写死。

为什么单列一个文件：写死 ``corpus_layer`` 的后果是**假绿**——把 L1 的实测标成 L2，
报告里没有任何机器证据能证伪。所以这里钉两件事：

1. 有 M2 抽取产物 ⇒ **L2**；只有直灌数据 ⇒ **L1**；图不可用 ⇒ **None（不猜）**；
2. 一次运行碰过多个版本 ⇒ **取最高层**（不让弱样本掩盖强样本，也不让弱样本拉高）。

本文件**不连真图**（用 GraphService 的桩）⇒ CI 每次提交必过。
"""

from __future__ import annotations

import pytest

from app.evaluation import runner
from app.evaluation.corpus_layer import (
    LAYER_ALGORITHM,
    LAYER_END_TO_END,
    detect_corpus_layer,
)
from app.services.graphs import GraphService, GraphUnavailableError


class _StubGraph:
    """图谱服务桩：只回答「有多少 M2 产物 / 有多少数据」。"""

    def __init__(self, *, m2: int, pool: int, raises: bool = False) -> None:
        self._m2 = m2
        self._pool = pool
        self._raises = raises

    def count_m2_entities(
        self, *, kg_version: str, org_id: object = None, limit: int = 1
    ) -> int:
        self._check()
        return self._m2

    def fetch_chunk_pool(
        self, *, kg_version: str, org_id: object = None, limit: int = 5000
    ) -> list[object]:
        self._check()
        return [object() for _ in range(self._pool)]

    def _check(self) -> None:
        if self._raises:
            raise GraphUnavailableError("图库不可用（桩）")


def _patch(monkeypatch: pytest.MonkeyPatch, stub: _StubGraph) -> None:
    monkeypatch.setattr(GraphService, "instance", classmethod(lambda _cls: stub))


def test_m2_products_mean_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 M2 抽取产物 ⇒ **L2**（真机文档走完了解析 + 抽取）。"""
    _patch(monkeypatch, _StubGraph(m2=180, pool=194))
    assert detect_corpus_layer(kg_version="attendance-demo-v1") == LAYER_END_TO_END


def test_direct_ingest_is_algorithm_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """有数据但**无** M2 产物 ⇒ **L1**（合成 / CSV 直灌，绕过抽取）。"""
    _patch(monkeypatch, _StubGraph(m2=0, pool=988))
    assert detect_corpus_layer(kg_version="affiliation-demo-v2") == LAYER_ALGORITHM


def test_graph_unavailable_yields_none_not_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图不可用 ⇒ ``None``。**不许**兜底成 L1/L2——猜出来的层号就是假绿的入口。"""
    _patch(monkeypatch, _StubGraph(m2=0, pool=0, raises=True))
    assert detect_corpus_layer(kg_version="whatever") is None


def test_unknown_version_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """图里没有这个版本 ⇒ 什么都别写（既不是 L1 也不是 L2）。"""
    _patch(monkeypatch, _StubGraph(m2=0, pool=0))
    assert detect_corpus_layer(kg_version="no-such-version") is None


def test_empty_version_yields_none() -> None:
    assert detect_corpus_layer(kg_version="") is None


def test_runner_takes_highest_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """多版本 ⇒ **取最高层**：跑到过 L2 就不许被同批的 L1 图拉低。"""
    seen: list[str] = []

    def fake(kg_version: str, org_id: object = None) -> str:
        seen.append(kg_version)
        return LAYER_END_TO_END if kg_version == "v-l2" else LAYER_ALGORITHM

    monkeypatch.setattr(runner, "_detect_corpus_layer_impl", fake, raising=False)
    monkeypatch.setattr(
        runner,
        "detect_corpus_layer",
        fake,
        raising=False,
    )
    assert runner._detect_layer({"v-l1", "v-l2"}, "") == LAYER_END_TO_END
    assert runner._detect_layer({"v-l1"}, "") == LAYER_ALGORITHM
    assert seen  #: 真的去问了图，不是拍脑袋


def test_runner_returns_none_when_nothing_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner, "detect_corpus_layer", lambda *a, **k: None, raising=False
    )
    assert runner._detect_layer({"v-x"}, "") is None
