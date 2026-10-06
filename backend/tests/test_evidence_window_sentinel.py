"""P6-K：**候选窗口哨兵**单测（`_warn_if_candidate_window_narrow` + `fetch_evidence_chunks` 留痕）。

背景（裁决 D1 = O1 / D2 / D3，见 ``changes/P6-K/proposal.md`` §3）：

- **只建哨兵，不建召回** —— 本语料上「候选集是结构性窗口」实测**零损失**
  （候选 213 = 版本内 chunk 总数 213）⇒ 它是**规模风险**，不是当前缺陷；
- 判据必须是**机械量**（不依赖人工判分）⇒ 本文件的断言全是可数的布尔 / 数字，
  没有一处需要人来判断"这个答案对不对"；
- 哨兵**不改返回值、不改契约** ⇒ 有一条用例专门钉住"留痕前后返回值完全相同"。

留痕断言用的是 **loguru sink 捕获**（不是 ``caplog``）：本项目日志走 loguru
（``app/core/logging.py``），它**不**默认桥接到 stdlib logging ⇒ ``caplog``
抓不到。等价手段，不要因为换了个抓法就以为验收降了格。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from loguru import logger

from app.core.config import get_settings
from app.services import graphs
from app.services.agents import _GRAPH_NODE_LIMIT
from app.services.graphs import (
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _EVIDENCE_CHUNK_SNIPPET_CHARS,
    _EVIDENCE_WINDOW_NARROW_PREFIX,
    _EVIDENCE_WINDOW_PROBE_FAILED_PREFIX,
    _QUERY_COUNT_CHUNKS_IN_VERSION,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    _QUERY_EVIDENCE_CHUNKS_BY_IDS,
    GraphService,
    _warn_if_candidate_window_narrow,
)

#: (chunk_id, doc_id, mentions, spans, char_start) —— 与索引 Cypher 的列一致
DOC_A = "11111111-1111-1111-1111-111111111111"
KG_VERSION = "sentinel-test-v1"


def _index_rows(count: int) -> list[dict[str, Any]]:
    """合成 ``_QUERY_EVIDENCE_CHUNK_INDEX`` 的返回行（``LIMIT`` 由 :class:`_FakeSession` 复刻）。"""
    return [
        {
            "chunk_id": f"c{i}",
            "doc_id": DOC_A,
            "mentions": 1,
            "spans": 0,
            "char_start": i,
            "snippet": f"片段 {i}",
        }
        for i in range(count)
    ]


class _FakeResult:
    """只有 ``single()`` 的极简结果（``count`` 查询用）。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """复刻 ``fetch_evidence_chunks`` 的三段查询：索引 → 计数 → 取全文。

    索引段**真的按 ``index_limit`` 切片**（= 复刻 Cypher ``LIMIT``）：哨兵要测的
    正是「被截断」这件事，假会话若不截断，这条用例等于没测。
    """

    def __init__(self, index_rows: list[dict[str, Any]], total_chunks: int) -> None:
        self._index_rows = index_rows
        self._total_chunks = total_chunks
        self.count_fail = False
        #: 计数查询收到的入参（用来钉「分子分母同源」——分母必须带同一个 org 过滤）
        self.count_params: dict[str, Any] | None = None

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def run(self, query: str, **params: Any) -> Any:
        if query == _QUERY_EVIDENCE_CHUNK_INDEX:
            return self._index_rows[: params["index_limit"]]
        if query == _QUERY_COUNT_CHUNKS_IN_VERSION:
            self.count_params = params
            if self.count_fail:
                raise RuntimeError("Neo4j 抖动（合成）")
            return _FakeResult([{"n": self._total_chunks}])
        if query == _QUERY_EVIDENCE_CHUNKS_BY_IDS:
            return [
                {
                    "chunk_id": chunk_id,
                    "doc_id": DOC_A,
                    "text": f"{chunk_id} 正文",
                    "page": None,
                    "char_start": 0,
                    "char_end": 4,
                    "spans": [],
                }
                for chunk_id in params["chunk_ids"]
            ]
        raise AssertionError(f"未预期的查询: {query[:40]}")


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    """捕获 WARNING 及以上日志（loguru sink；项目日志不走 stdlib ⇒ 不用 caplog）。"""
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="WARNING",
        format="{message}",
    )
    try:
        yield captured
    finally:
        logger.remove(sink_id)


def _narrow(warnings: list[str]) -> list[str]:
    return [m for m in warnings if _EVIDENCE_WINDOW_NARROW_PREFIX in m]


# ---------------------------------------------------------------------------
# 纯函数层：两个方向 + 一条"总数未知"的边界
# ---------------------------------------------------------------------------


def test_silent_when_window_is_complete(warnings: list[str]) -> None:
    """未截断且候选 == 版本内总数 ⇒ **不打日志**（否则每轮问答都在刷屏）。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=213,
        candidate_count=213,
        index_limit=1000,
        total_chunks=213,
    )

    assert emitted is False
    assert _narrow(warnings) == []


def test_warns_when_index_is_truncated(warnings: list[str]) -> None:
    """索引行撞上 ``index_limit`` ⇒ 留痕，且把"被截断"写进原因。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=1000,
        candidate_count=1000,
        index_limit=1000,
        total_chunks=5000,
    )

    assert emitted is True
    hits = _narrow(warnings)
    assert len(hits) == 1
    assert "index_limit(1000)" in hits[0]
    assert "候选 1000 < 版本内 chunk 总数 5000" in hits[0]
    assert "20.00%" in hits[0], "窗口完整率必须是机械量（可核，不靠形容词）"


def test_warns_when_candidates_short_of_total(warnings: list[str]) -> None:
    """**没**撞上限、但候选少于总数 ⇒ 照样留痕（这才是"规模风险"的真实形态）。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=7,
        candidate_count=7,
        index_limit=1000,
        total_chunks=213,
    )

    assert emitted is True
    hits = _narrow(warnings)
    assert len(hits) == 1
    assert "候选 7 < 版本内 chunk 总数 213" in hits[0]
    assert "index_limit" not in hits[0], "没撞上限就不该谎报截断"


def test_unknown_total_does_not_fake_completeness(warnings: list[str]) -> None:
    """总数未知 ⇒ **不**报"窗口完整率 100%"，只判截断；失明由另一条告警负责。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=5,
        candidate_count=5,
        index_limit=1000,
        total_chunks=None,
    )

    assert emitted is False, "总数未知且未截断 ⇒ 不出「窗口不完整」（那是猜）"
    assert _narrow(warnings) == []


def test_unknown_total_still_warns_on_truncation(warnings: list[str]) -> None:
    """总数未知**但**确实被截断 ⇒ 仍然要叫（这条不依赖总数也能判）。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=1000,
        candidate_count=1000,
        index_limit=1000,
        total_chunks=None,
    )

    assert emitted is True
    assert "未知（哨兵未取到总数）" in _narrow(warnings)[0]


def test_zero_total_does_not_divide_by_zero(warnings: list[str]) -> None:
    """版本内 0 条 chunk（空语料）⇒ 不许 ``ZeroDivisionError`` 把读侧打挂。"""
    emitted = _warn_if_candidate_window_narrow(
        kg_version=KG_VERSION,
        row_count=0,
        candidate_count=0,
        index_limit=1000,
        total_chunks=0,
    )

    assert emitted is False


# ---------------------------------------------------------------------------
# 服务层：真调用 fetch_evidence_chunks（假会话）+ monkeypatch 配额
# ---------------------------------------------------------------------------


def _fetch(monkeypatch: pytest.MonkeyPatch, session: _FakeSession) -> list[str]:
    service = GraphService()
    monkeypatch.setattr(service, "_session", lambda: session)
    chunks = service.fetch_evidence_chunks(
        kg_version=KG_VERSION, org_id=None, entity_ids=["e1"], limit=32
    )
    return [c.chunk_id for c in chunks]


def test_sentinel_fires_when_index_limit_cut_the_candidates(
    monkeypatch: pytest.MonkeyPatch, warnings: list[str]
) -> None:
    """**人为构造的丢数据场景**：``index_limit`` 调到 2，而版本内有 5 条 chunk。

    ``index_limit`` 只在**单测内** monkeypatch —— 产品默认值
    ``_EVIDENCE_CHUNK_INDEX_LIMIT`` **一个数都不许动**（Non-goals 第 8 条）。
    """
    monkeypatch.setattr(graphs, "_EVIDENCE_CHUNK_INDEX_LIMIT", 2)

    selected = _fetch(monkeypatch, _FakeSession(_index_rows(5), total_chunks=5))

    hits = _narrow(warnings)
    assert len(hits) == 1, "候选被截断 ⇒ 哨兵必须叫"
    assert "候选 2 < 版本内 chunk 总数 5" in hits[0]
    assert "index_limit(2)" in hits[0]
    assert selected == ["c0", "c1"], "留痕**不得**改变返回值（裁决 D3）"


def test_sentinel_silent_when_window_is_complete(
    monkeypatch: pytest.MonkeyPatch, warnings: list[str]
) -> None:
    """反向：候选吃满版本内全部 chunk ⇒ **一声不响**（避免每轮问答刷屏）。"""
    selected = _fetch(monkeypatch, _FakeSession(_index_rows(5), total_chunks=5))

    assert _narrow(warnings) == []
    assert selected == ["c0", "c1", "c2", "c3", "c4"]


def test_count_failure_is_logged_but_does_not_break_the_read_path(
    monkeypatch: pytest.MonkeyPatch, warnings: list[str]
) -> None:
    """哨兵自己跑挂 ⇒ 留一条**不同前缀**的告警，问答本身照常返回（不因诊断挂掉）。"""
    session = _FakeSession(_index_rows(3), total_chunks=3)
    session.count_fail = True

    selected = _fetch(monkeypatch, session)

    failed = [m for m in warnings if _EVIDENCE_WINDOW_PROBE_FAILED_PREFIX in m]
    assert len(failed) == 1, "哨兵失明必须显式留痕（否则与『窗口确实完整』无法区分）"
    assert _narrow(warnings) == [], "取不到总数 ⇒ 不出「窗口不完整」（那是猜）"
    assert selected == ["c0", "c1", "c2"]


def test_sentinel_denominator_is_org_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """分母（版本内 chunk 总数）必须与分子**同一个 org 口径** ⇒ 完整率才可核。

    不钉这一条的话，跨租户 chunk 会被算进分母 ⇒ 单租户视角下窗口永远"不完整"，
    哨兵天天喊狼来了，最后被人当成噪音关掉。
    """
    session = _FakeSession(_index_rows(1), total_chunks=1)
    service = GraphService()
    monkeypatch.setattr(service, "_session", lambda: session)
    org = UUID("00000000-0000-4000-8000-000000000001")

    service.fetch_evidence_chunks(
        kg_version=KG_VERSION, org_id=org, entity_ids=["e1"], limit=32
    )

    assert session.count_params is not None, "哨兵应当真的去取了分母"
    assert session.count_params["org_id"] == str(org)
    assert session.count_params["kg_version"] == KG_VERSION


# ---------------------------------------------------------------------------
# P6-L：真机 —— 哨兵在**更大语料**上必须真的喊（**CI 上不 skip**）
# ---------------------------------------------------------------------------

#: 对照语料 `affiliation-demo-v2`：**988** chunk / **1268** 实体，
#: 生产 500 采样实测只覆盖 **355 / 988 = 35.93%**
#: （`uv run python scripts/probe_candidate_window.py --kg-version affiliation-demo-v2
#: --org-id 5dea8f62-…` 可 ¥0 复算）。
#:
#: 它由 **CI 的「导入受控种子语料」步骤**导入，而该步骤排在 Pytest **之前**
#: ⇒ 本组用例在 CI 上**一定跑得到**（跑不到 = 门禁前提被破坏，属 fail 不是 skip）。
_LARGE_KG_VERSION = "affiliation-demo-v2"
_LARGE_ORG = UUID("5dea8f62-0c67-579a-9509-8b4ce98eadea")

_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"


def _real_graph_env() -> tuple[str, str, str]:
    """真 Neo4j 连接三元组；**CI 上不可达 ⇒ fail，本地未设 ⇒ skip**。

    与 `tests/test_guardrails_graph.py` 同款：skip 会让「没在验」和「验过了」
    在 CI 日志里长得一模一样（纪律 **R-9「恒绿即失效」**）。
    """
    uri = os.environ.get(_REAL_URI_ENV, "").strip()
    user = os.environ.get(_REAL_USER_ENV, "").strip() or "neo4j"
    password = os.environ.get(_REAL_PASSWORD_ENV, "").strip()
    if not uri or not password:
        missing = f"未设 {_REAL_URI_ENV} / {_REAL_PASSWORD_ENV}"
        if os.environ.get("CI"):
            pytest.fail(
                f"{missing} ⇒ CI 上真图用例连不上图库，这是门禁失效不是环境问题"
            )
        pytest.skip(f"{missing}（本地无 Neo4j ⇒ 真图用例跳过；CI 上为 fail）")
    return uri, user, password


@pytest.fixture
def real_graph_service(monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphService]:
    """把 `GraphService` 指向**真** Neo4j（其余用例仍走 conftest 的不可达端口）。"""
    uri, user, password = _real_graph_env()
    settings = get_settings()
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", user)
    monkeypatch.setattr(settings, "neo4j_password", password)
    GraphService.reset()  # 单例里可能缓存着上一个（不可达的）driver
    try:
        yield GraphService.instance()
    finally:
        GraphService.reset()


def test_sentinel_fires_on_a_larger_corpus(
    real_graph_service: GraphService, warnings: list[str]
) -> None:
    """**哨兵在真实大语料上必须真的喊** —— 此前只有单测的合成场景作证（P6-K 已知限制）。

    为什么非真机不可：P6-K 的「本语料零损失」是在 **213 chunk / 每 chunk 约 13 个实体
    提及**的语料上得出的。同一个固定预算（500 采样实体 / 1000 索引行）放到
    **988 chunk / 每 chunk 约 1.28 个提及**的语料上，生产采样只覆盖 **35.93%**
    ⇒ 哨兵**必然**喊。合成场景证明不了这件事，只有真图能。
    """
    service = real_graph_service
    nodes, _edges, _truncated = service.fetch_all_subgraph(
        kg_version=_LARGE_KG_VERSION, org_id=_LARGE_ORG, node_limit=_GRAPH_NODE_LIMIT
    )
    entity_ids = [n.id for n in nodes if n.label == "Entity"]

    with service._session() as session:
        total = int(
            session.run(
                _QUERY_COUNT_CHUNKS_IN_VERSION,
                kg_version=_LARGE_KG_VERSION,
                org_id=str(_LARGE_ORG),
            ).single()["n"]
        )
        rows = list(
            session.run(
                _QUERY_EVIDENCE_CHUNK_INDEX,
                kg_version=_LARGE_KG_VERSION,
                org_id=str(_LARGE_ORG),
                entity_ids=entity_ids,
                index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
                snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
            )
        )
    candidate = len({str(r["chunk_id"]) for r in rows})

    if total == 0:
        why = f"图里没有 {_LARGE_KG_VERSION} 的 chunk ⇒ 本用例前提不成立"
        if os.environ.get("CI"):
            pytest.fail(f"{why}（CI 应先导入受控种子语料，这是门禁前提被破坏）")
        pytest.skip(f"{why}（本地可先跑 scripts/ingest_affiliation_sources.py）")

    if candidate >= total:
        pytest.skip(
            f"该语料 S 档已完整（候选 {candidate} / 总数 {total}）⇒ "
            "本用例前提（窗口窄）不再成立；若这是**召回修复**的结果，请回来更新本用例"
        )

    before = len(_narrow(warnings))
    service.fetch_evidence_chunks(
        kg_version=_LARGE_KG_VERSION,
        org_id=_LARGE_ORG,
        entity_ids=entity_ids,
        limit=32,
    )
    fired = _narrow(warnings)[before:]

    assert len(fired) == 1, (
        "哨兵必须喊：候选 "
        f"{candidate} < 版本内 chunk 总数 {total}"
        f"（窗口完整率 {candidate / total:.2%}）却没有留痕"
    )
    assert _LARGE_KG_VERSION in fired[0]
    assert f"候选 {candidate} < 版本内 chunk 总数 {total}" in fired[0]
