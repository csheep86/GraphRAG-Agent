"""Sprint 9 批次 B：写侧接线（M4 边的四字段 + stage-3.3 仲裁调用）。

Neo4j 零依赖：``session_factory`` 注入桩，按需返回「现存的活边」，
据此断言 builder **会不会**去封、封到哪天、以及**顺序**（先写后封）。

这里不重复验仲裁规则本身——那是 ``test_temporal_arbitration.py`` 的职责；
本文件只验「规则有没有被正确地接进构建链路」。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.services.graphs import GraphUnavailableError
from app.services.kg import ThreeStageKgBuilder
from app.services.kg.builder import (
    _CYPHER_EXPIRE_LEGAL_REP,
    _CYPHER_QUERY_ALIVE_LEGAL_REP,
    _CYPHER_STAGE3B_LEGAL_REP,
    KgBuildRequest,
    build_affiliation_rows,
)

_ORG = {
    "id": "ent_001",
    "canonical_name": "招商局集团有限公司",
    "entity_type": "ORG",
    "confidence": 0.95,
}
_PERSON = {
    "id": "ent_002",
    "canonical_name": "缪建民",
    "entity_type": "LEGAL_PERSON",
    "char_start": 40,
    "confidence": 0.93,
}
_PERSON_LATER = {
    "id": "ent_004",
    "canonical_name": "李四",
    "entity_type": "LEGAL_PERSON",
    "char_start": 88,
    "confidence": 0.93,
}


def _relation(target_id: str, *, valid_from: str | None) -> dict[str, Any]:
    return {
        "id": "rel_001",
        "source_entity_id": "ent_001",
        "target_entity_id": target_id,
        "relation_type": "LEGAL_REP",
        "evidence": "法定代表人",
        "confidence": 0.92,
        "valid_from": valid_from,
        "valid_to": None,
    }


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeSession:
    """按 Cypher 分支返回：查询活边时给 ``alive_rows``，其余返回空。"""

    def __init__(
        self, calls: list[tuple[str, dict[str, Any]]], alive_rows: list[dict[str, Any]]
    ) -> None:
        self._calls = calls
        self._alive_rows = alive_rows

    def run(self, cypher: str, **params: Any) -> _FakeResult:
        self._calls.append((cypher.strip(), params))
        if cypher.strip().startswith("UNWIND $heads"):
            return _FakeResult(self._alive_rows)
        return _FakeResult([])

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeSessionFactory:
    def __init__(
        self, calls: list[tuple[str, dict[str, Any]]], alive_rows: list[dict[str, Any]]
    ) -> None:
        self._calls = calls
        self._alive_rows = alive_rows

    def __call__(self) -> _FakeSession:
        return _FakeSession(self._calls, self._alive_rows)


def _builder(
    calls: list[tuple[str, dict[str, Any]]],
    alive_rows: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> ThreeStageKgBuilder:
    return ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        batch_size=500,
        session_factory=_FakeSessionFactory(calls, alive_rows or []),
        **kwargs,
    )


def _request() -> KgBuildRequest:
    return KgBuildRequest(
        org_id=uuid4(),
        version="v-temporal",
        entities=[_ORG, _PERSON],
        relations=[_relation("ent_002", valid_from="2025-05-01")],
        trace_id=uuid4(),
    )


# --------------------------------------------------------------------------- #
# build_affiliation_rows：时态字段与血缘
# --------------------------------------------------------------------------- #


def test_edge_rows_carry_temporal_fields_and_lineage() -> None:
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [_relation("ent_002", valid_from="2025-05-01")],
        version="v1",
        source_document_id="doc-42",
    )

    edge = rows.legal_rep_edges[0]
    assert edge["valid_from"] == "2025-05-01"
    assert edge["valid_to"] is None
    assert edge["source_document_id"] == "doc-42"
    assert edge["tail_position"] == 40  # target 实体的字符偏移，R2 的判据


def test_missing_valid_from_stays_none_instead_of_being_invented() -> None:
    """抽取没给日期 ⇒ ``None`` 原样透传（R4：不猜值，也不塞今天）。"""
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [_relation("ent_002", valid_from=None)],
        version="v1",
        source_document_id="doc-42",
    )

    assert rows.legal_rep_edges[0]["valid_from"] is None


def test_repeated_fact_keeps_the_earliest_valid_from() -> None:
    """同一事实在两份文档里被抽到 ⇒ 合并成一条，``valid_from`` 取**最早**证据。

    "后来者赢"会把 2023 年披露的事实改成 2025 年的生效日——等于悄悄改写历史。
    """
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [
            _relation("ent_002", valid_from="2025-05-01"),
            _relation("ent_002", valid_from="2023-04-01"),
        ],
        version="v1",
        source_document_id="doc-42",
    )

    assert len(rows.legal_rep_edges) == 1
    assert rows.legal_rep_edges[0]["valid_from"] == "2023-04-01"


# --------------------------------------------------------------------------- #
# stage-3.3：builder 是否真的按策略跑仲裁
# --------------------------------------------------------------------------- #


def test_policy_not_configured_means_no_arbitration_at_all() -> None:
    """没注入策略 ⇒ 一次查询都不发（保守默认：并存），行为与接入前一致。"""
    calls: list[tuple[str, dict[str, Any]]] = []

    stats = _builder(calls).build(_request())

    assert stats.expired_edge_count == 0
    assert all(cypher != _CYPHER_QUERY_ALIVE_LEGAL_REP.strip() for cypher, _ in calls)


def test_single_current_policy_writes_then_closes() -> None:
    """配置了「唯一当前」⇒ 写入之后执行封边，且顺序是**先写后封**。

    顺序不是实现细节：R2 封的就是本次刚写入的那批边，反过来做一封一个空。
    所以这里必须给出一条可被取代的旧边，让封边**真的发生**。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [_relation("ent_002", valid_from="2025-05-01")],
        version="v-temporal",
        source_document_id="doc-B",
    )
    builder = _builder(
        calls,
        alive_rows=[
            {
                "head_id": rows.legal_rep_edges[0]["source_id"],
                "tail_id": "lpr-old",
                "valid_from": "2023-04-01",
                "source_document_id": "doc-A",
            }
        ],
        policy_lookup=lambda _rt: True,
    )

    builder.build(_request())

    written_at = next(
        i
        for i, (cypher, _) in enumerate(calls)
        if cypher == _CYPHER_STAGE3B_LEGAL_REP.strip()
    )
    expired_at = next(
        (
            i
            for i, (cypher, _) in enumerate(calls)
            if cypher == _CYPHER_EXPIRE_LEGAL_REP.strip()
        ),
        None,
    )
    assert expired_at is not None, "有活边被取代时应发出封边 Cypher"
    assert written_at < expired_at, "R2 封的是本次刚写入的边 ⇒ 必须先写"


def test_cross_document_fact_closes_alive_old_edge() -> None:
    """图里已有 2023 年的张三（另一份文档）⇒ 本次的李四把它封到 2025-05-01。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [_relation("ent_002", valid_from="2025-05-01")],
        version="v-temporal",
        source_document_id="doc-B",
    )
    builder = _builder(
        calls,
        alive_rows=[
            {
                "head_id": rows.legal_rep_edges[0]["source_id"],
                "tail_id": "lpr-other",
                "valid_from": "2023-04-01",
                "source_document_id": "doc-A",
            }
        ],
        policy_lookup=lambda _rt: True,
    )

    stats = builder.build(_request())

    assert stats.expired_edge_count == 1
    payloads = [
        params["batch"]
        for cypher, params in calls
        if cypher == _CYPHER_EXPIRE_LEGAL_REP.strip()
    ]
    assert payloads[0][0]["valid_to"] == "2025-05-01"
    assert payloads[0][0]["reason"] == "R1"


def test_arbitration_failure_is_not_swallowed() -> None:
    """仲裁炸了必须往外抛——静默跳过的后果是"两个法定代表人同时在位"。"""

    class _BoomSession(_FakeSession):
        def run(self, cypher: str, **params: Any) -> _FakeResult:
            if cypher.strip().startswith("UNWIND $heads"):
                raise RuntimeError("Neo4j 连接断了")
            return super().run(cypher, **params)

    class _Factory:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        def __call__(self) -> _BoomSession:
            return _BoomSession(self.calls, [])

    builder = ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        batch_size=500,
        session_factory=_Factory(),
        policy_lookup=lambda _rt: True,
    )

    with pytest.raises(GraphUnavailableError, match="stage-2.6/3.2/3.3 失败"):
        builder.build(_request())
