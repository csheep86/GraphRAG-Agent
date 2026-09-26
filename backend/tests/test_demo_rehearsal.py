"""`scripts/demo_rehearsal.py` 与 `scripts/slice_demo_corpus.py` 的回归守卫。

为什么必须有这两个脚本的测试：**彩排脚本是「演示零假数据」的唯一机械证据**——
它自己若失灵（比如把恒 0 的统计值判成 PASS），这条证据就是假的。故用
``httpx.MockTransport`` 对每步断言打桩，重点守两处**真机才暴露过**的回归：

- 统计值恒 0（`_fetch_graph_overview_stats` 曾硬编码返回 0，见 notes §7.5）；
- 实体 `entity_type` 恒空（写 `entity_type` / 读 `type` 的属性名错配，见 notes §7.5.1）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> Any:
    """按文件路径加载 `scripts/` 下的脚本（该目录不是包，不能 import）。

    .. note::
       必须先登记进 ``sys.modules`` 再 ``exec_module``——否则模块级 ``@dataclass``
       解析类型注解时会因 ``sys.modules[cls.__module__]`` 为 ``None`` 而炸
       （``dataclasses._is_type`` 依赖该查找）。
    """
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REHEARSAL = _load("demo_rehearsal")
SLICE = _load("slice_demo_corpus")


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(
        base_url="http://rehearsal.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )


def _overview(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nodes": [{"id": "ent_1"}],
        "edges": [{"id": "rel_1"}],
        "doc_count": 6,
        "entity_count": 2000,
        "relation_count": 819,
        "kg_version": "v-test",
        "truncated": False,
        "trace_id": "t",
    }
    base.update(over)
    return base


def test_step2_rejects_zero_stats() -> None:
    """统计值有 0 ⇒ FAIL（硬编码 0 的静默假数据不得被判 PASS）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_overview(entity_count=0))

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_2_graph(client, report)

    assert report.failed == 1
    assert "统计值" in report.checks[0].detail


def test_step2_rejects_empty_entity_type() -> None:
    """`entity_type` 恒空 ⇒ FAIL（属性名错配回归）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/graph/overview"):
            return httpx.Response(200, json=_overview())
        return httpx.Response(200, json={"id": "ent_1", "entity_type": None})

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_2_graph(client, report)

    assert report.failed == 1
    assert "entity_type" in report.checks[0].detail


def test_step3_skips_llm_by_default() -> None:
    """默认 ¥0：不调 `/agent/query`（真实 LLM 烧 token）。"""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url.path))
        return httpx.Response(200, json={"answer": "x"})

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_3_ask(client, report, with_llm=False, question="q")

    assert called == []
    assert report.checks[0].status == "SKIP"


def test_step4_picks_first_document_with_subgraph() -> None:
    """候选里混着未建图文档（本机 9 篇中 3 篇子图为空）⇒ 逐篇试探取有子图的。"""
    probed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        probed.append(path)
        if path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        # 前两篇无子图，第三篇有
        return httpx.Response(
            200, json={"node_count": 0 if "doc-3" not in path else 500}
        )

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_4_trace_back(client, report, ["doc-1", "doc-2", "doc-3"])

    assert report.failed == 0
    assert "doc-3" in report.checks[0].detail


def test_step4_fails_when_no_document_has_subgraph() -> None:
    """全部无子图 ⇒ FAIL（不得因"有 completed 文档"就放行）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(200, json={"node_count": 0})

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_4_trace_back(client, report, ["doc-1", "doc-2"])

    assert report.failed == 1


def test_step6_requires_every_step_action() -> None:
    """缺任一 action ⇒ FAIL（否则"审计回放"证据不完整却被判 PASS）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        # 少一条 affiliation.list
        actions = [
            "document.list",
            "graph.overview",
            "graph.entity",
            "document.status",
            "document.graph",
        ]
        return httpx.Response(200, json={"items": [{"action": a} for a in actions]})

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_6_audit(
            client, report, "00000000-0000-4000-8000-000000000001", min_rows=5
        )

    assert report.failed == 1
    assert "affiliation.list" in report.checks[0].detail


def test_step6_passes_when_actions_complete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        items = [{"action": a} for a in REHEARSAL.REQUIRED_ACTIONS]
        return httpx.Response(200, json={"items": items})

    report = REHEARSAL.Rehearsal()
    with _client(handler) as client:
        REHEARSAL.step_6_audit(
            client, report, "00000000-0000-4000-8000-000000000001", min_rows=5
        )

    assert report.failed == 0


@pytest.mark.parametrize("name", sorted(SLICE.RECORDED_NAME_HASHES))
def test_slice_filename_hashes_match_live_db(name: str) -> None:
    """切片文件名 → `filename_hash` 必须与现库一致（改名就与 `documents` 对不上）。"""
    prefix, suffix = SLICE.RECORDED_NAME_HASHES[name]
    digest = SLICE._name_hash(name)
    assert digest.startswith(prefix), f"{name} 前缀不符：{digest[:8]}"
    assert digest.endswith(suffix), f"{name} 后缀不符：{digest[-5:]}"


def test_slice_rules_cover_all_seed_sources() -> None:
    """切分规则必须为每份原件产出**已登记在库**的两个切片名（页范围不能错位）。"""
    for source in SLICE.SOURCES:
        total = int(source["pages"])
        for start, end in ((1, SLICE.SPLIT_AT), (SLICE.SPLIT_AT + 1, total)):
            name = f"{source['prefix']}_p{start}-{end}.pdf"
            assert name in SLICE.RECORDED_NAME_HASHES, f"未登记的切片名：{name}"
