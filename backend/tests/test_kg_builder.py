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
    # 紧随其后：索引 / 约束段（幂等）。Sprint 7.1 起含 M4 三类节点的约束，
    # 条数会随建模增长——按内容筛而不是按写死下标断言。
    index_calls = [c[0] for c in calls[1:] if c[0].startswith("CREATE ")]
    assert index_calls[0].startswith("CREATE CONSTRAINT entity_id_version")
    assert any(c.startswith("CREATE INDEX entity_org_id") for c in index_calls)
    assert any("IS UNIQUE" in c for c in index_calls)
    # 随后：实体 LOAD（UNWIND）→ 关系 LOAD（MATCH + MERGE）
    first_index = next(i for i, c in enumerate(calls) if "MERGE (n:Entity" in c[0])
    assert "UNWIND" in calls[first_index][0]
    assert "UNWIND" in calls[first_index + 1][0]
    assert "MERGE (a)-[rel:RELATION" in calls[first_index + 1][0]


def test_stage2_writes_entity_span_into_graph() -> None:
    """Sprint 10 批次 A（裁决 D-D）：抽取侧已有的 `char_start` / `char_end` **必须带进图**。

    真机事实（`changes/Sprint10/c0-recon.md` 事实 5）：`:Entity` 上**没有任何**字符区间
    属性——抽取侧 `ExtractedEntity.char_start/char_end` 一直有值，**是入图时丢的**。
    本例把"抽取有 ⇒ 入图不丢"钉在单测层，防止再丢一次（丢了引用就只能停在 chunk 级）。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)
    entity = _entity("e1")
    entity.update(char_start=120, char_end=140)

    builder.build(_request([entity], []))

    entity_calls = [c for c in calls if "MERGE (n:Entity" in c[0]]
    assert entity_calls, "stage-2 未执行"
    cypher = entity_calls[0][0]
    assert "n.char_start = e.char_start" in cypher
    assert "n.char_end = e.char_end" in cypher
    # 值随 batch 走（Cypher 侧从 map 取值，缺 key 时写 null ⇒ CSV 派生实体天然无 span）
    assert entity_calls[0][1]["batch"][0]["char_start"] == 120
    assert entity_calls[0][1]["batch"][0]["char_end"] == 140


def test_stage3_writes_temporal_fields_into_relation() -> None:
    """Sprint 10.4 批次 A：`valid_from` / `valid_to` **必须随关系进图**。

    真机事实（`changes/Sprint10.4/00-recon.md`、`probe_l2_temporal.py` 可复算）：
    抽取侧 v3 Prompt 一直产出这两个字段，**是 stage-3 的 Cypher 丢的**——它只写了
    relation_type / evidence / confidence，于是通用层 `:RELATION` 的时序覆盖恒为
    0%，上层「路径时序一致性」没有可判的日期。

    同时钉住**只写事实维**：`created_at` / `expired_at` 属摄入维，通用层端点 id 是
    `ent_<uuid>`（跨文档不可对齐）⇒ R1–R3 仲裁对它不适用，写了就是没人消费的预留字段。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)
    relation = _relation("r1", "e1", "e1")
    relation.update(valid_from="2026-01-01", valid_to=None)

    builder.build(_request([_entity("e1")], [relation]))

    rel_calls = [c for c in calls if "MERGE (a)-[rel:RELATION" in c[0]]
    assert rel_calls, "stage-3 未执行"
    cypher = rel_calls[0][0]
    assert "rel.valid_from = r.valid_from" in cypher
    assert "rel.valid_to = r.valid_to" in cypher
    assert "created_at" not in cypher
    assert "expired_at" not in cypher
    # 幂等语义：重跑不清空已有值（ON MATCH 用 coalesce 而不是覆盖）
    assert "coalesce(rel.valid_from, r.valid_from)" in cypher
    # 值随 batch 走；缺 key 的行写到图上是 null（CSV 派生关系天然无日期）
    assert rel_calls[0][1]["batch"][0]["valid_from"] == "2026-01-01"
    assert rel_calls[0][1]["batch"][0]["valid_to"] is None


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

    # 按 Cypher 内容定位实体批（stage-1b 的约束条目会随建模增长，下标不可靠）
    entity_call = next(c for c in calls if "MERGE (n:Entity" in c[0])
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
