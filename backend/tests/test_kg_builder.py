"""ThreeStageKgBuilder 单元测试（ADR-0002 §3.1 三段式写入，Sprint 5 批次 B）。

Neo4j 零依赖：经 ``session_factory`` 注入桩，记录每段 Cypher 与参数：

1. stage 顺序：version mirror + 索引约束 → 实体批 → 关系批；
2. ``kg_build_batch_size`` 批切片；
3. 空 entities/relations → 直接返回零统计，不触 Neo4j；
4. 桩抛错 → 包装为 :class:`GraphUnavailableError`；
5. 未知 ``kg_version_strategy`` 显式报错。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.services.graphs import GraphUnavailableError
from app.services.kg import ThreeStageKgBuilder
from app.services.kg.builder import _CYPHER_STAGE1A_VERSION_MIRROR, KgBuildRequest


class _FakeResult:
    def data(self) -> list[dict[str, Any]]:
        return []


class _FakeSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    def run(self, cypher: str, **params: Any) -> _FakeResult:
        self._calls.append((cypher.strip(), params))
        return _FakeResult()

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeSessionFactory:
    """``session_factory()`` 返回可 with 的会话桩（与 builder._run 对齐）。"""

    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    def __call__(self) -> _FakeSession:
        return _FakeSession(self._calls)


def _make_builder(
    calls: list[tuple[str, dict[str, Any]]],
    *,
    batch_size: int = 500,
) -> ThreeStageKgBuilder:
    factory = _FakeSessionFactory(calls)
    # graph_service 传占位对象：session_factory 已注入时不会被触达
    return ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        batch_size=batch_size,
        session_factory=factory,
    )


def _entity(entity_id: str) -> dict[str, Any]:
    return {
        "id": entity_id,
        "canonical_name": f"实体{entity_id}",
        "entity_type": "ORG",
        "mention": f"实体{entity_id}",
        "confidence": 0.9,
    }


def _relation(rel_id: str, source: str, target: str) -> dict[str, Any]:
    return {
        "id": rel_id,
        "source_entity_id": source,
        "target_entity_id": target,
        "relation_type": "PARTY_TO",
        "evidence": "同句共现",
        "confidence": 0.8,
    }


def _request(
    entities: list[dict[str, Any]], relations: list[dict[str, Any]]
) -> KgBuildRequest:
    return KgBuildRequest(
        org_id=uuid4(),
        version="v-test",
        entities=entities,
        relations=relations,
        trace_id=uuid4(),
    )


# --------------------------------------------------------------------------- #
# stage 顺序
# --------------------------------------------------------------------------- #


def test_stage_order_mirror_then_entities_then_relations() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(_request([_entity("e1")], [_relation("r1", "e1", "e1")]))

    assert stats.entity_count == 1
    assert stats.relation_count == 1
    assert stats.batch_count == 2

    # 第一段必须是 KgVersionMirror MERGE（PG 真源的冗余镜像，ADR-0002 §3.2）
    assert calls[0][0] == _CYPHER_STAGE1A_VERSION_MIRROR.strip()
    assert calls[0][1]["version"] == "v-test"
    assert calls[0][1]["status"] == "building"
    # 第二、三段：索引约束（幂等）
    assert "CREATE CONSTRAINT" in calls[1][0]
    assert "CREATE INDEX" in calls[2][0]
    # 第四段起：实体 LOAD（UNWIND）→ 关系 LOAD（MATCH + MERGE）
    assert "UNWIND" in calls[3][0] and "MERGE (n:Entity" in calls[3][0]
    assert "UNWIND" in calls[4][0] and "MERGE (a)-[rel:RELATION" in calls[4][0]


def test_build_params_carry_tenant_and_version() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    org_id = uuid4()
    builder = _make_builder(calls)

    builder.build(
        KgBuildRequest(
            org_id=org_id,
            version="v-tenant",
            entities=[_entity("e1")],
            relations=[],
            trace_id=uuid4(),
        )
    )

    entity_call = calls[3]
    assert entity_call[1]["kg_version"] == "v-tenant"
    assert entity_call[1]["org_id"] == str(org_id)
    assert [e["id"] for e in entity_call[1]["batch"]] == ["e1"]


# --------------------------------------------------------------------------- #
# 批切片
# --------------------------------------------------------------------------- #


def test_entities_batched_by_batch_size() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    entities = [_entity(f"e{i}") for i in range(5)]
    builder = _make_builder(calls, batch_size=2)

    stats = builder.build(_request(entities, []))

    entity_batches = [c for c in calls if "MERGE (n:Entity" in c[0]]
    assert [len(c[1]["batch"]) for c in entity_batches] == [2, 2, 1]
    assert stats.entity_count == 5
    assert stats.batch_count == 3


def test_relations_batched_by_batch_size() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    relations = [_relation(f"r{i}", "e1", "e2") for i in range(4)]
    builder = _make_builder(calls, batch_size=3)

    stats = builder.build(_request([_entity("e1"), _entity("e2")], relations))

    relation_batches = [c for c in calls if "MERGE (a)-[rel:RELATION" in c[0]]
    assert [len(c[1]["batch"]) for c in relation_batches] == [3, 1]
    assert stats.relation_count == 4


# --------------------------------------------------------------------------- #
# 空输入 / 异常包装
# --------------------------------------------------------------------------- #


def test_empty_input_short_circuits_without_neo4j() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(_request([], []))

    assert stats.entity_count == 0
    assert stats.relation_count == 0
    assert stats.batch_count == 0
    assert calls == [], "空输入不得触碰 Neo4j"


def test_session_failure_wrapped_as_graph_unavailable() -> None:
    class _BoomSession(_FakeSession):
        def run(self, cypher: str, **params: Any) -> _FakeResult:
            raise RuntimeError("connection reset")

    class _BoomFactory:
        def __call__(self) -> _BoomSession:
            return _BoomSession([])

    builder = ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        session_factory=_BoomFactory(),
    )
    with pytest.raises(GraphUnavailableError, match="stage-1 失败"):
        builder.build(_request([_entity("e1")], []))


def test_graph_unavailable_passthrough_not_double_wrapped() -> None:
    class _UnavailableSession(_FakeSession):
        def run(self, cypher: str, **params: Any) -> _FakeResult:
            raise GraphUnavailableError("driver closed")

    class _UnavailableFactory:
        def __call__(self) -> _UnavailableSession:
            return _UnavailableSession([])

    builder = ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        session_factory=_UnavailableFactory(),
    )
    with pytest.raises(GraphUnavailableError, match="driver closed"):
        builder.build(_request([_entity("e1")], []))


def test_unknown_version_strategy_raises() -> None:
    with pytest.raises(ValueError, match="kg_version_strategy"):
        ThreeStageKgBuilder(
            graph_service=object(),  # type: ignore[arg-type]
            version_strategy="global",
        )


def test_default_batch_size_from_settings() -> None:
    from app.core.config import get_settings

    builder = ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        session_factory=_FakeSessionFactory([]),
    )
    assert builder._batch_size == get_settings().kg_build_batch_size
