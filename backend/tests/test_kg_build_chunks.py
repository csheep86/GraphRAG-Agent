"""Chunk 证据层构建单元测试（Sprint 6 批次 A-3：stage-1.5 / 2.5 / 4）。

Neo4j 零依赖：经 ``session_factory`` 注入桩记录每段 Cypher 与参数，覆盖：

1. 五段式顺序：mirror → 索引 → ``:Document`` → ``:Entity`` → ``:Chunk``
   → ``RELATION`` → ``HAS_CHUNK`` → ``MENTIONS``；
2. ``acl_scope`` 从 ``documents.acl_scope`` 继承到 ``:Document`` / ``:Chunk``；
3. ``page = None``（页码失配）允许写入，不报错、不补 1；
4. 实体按**字符区间**归属 chunk（``_assign_entities_to_chunks``）；
5. 无 ``document`` 引用 → 跳过证据段（保持 v1.1.0 三段式行为）；
6. 空 entities / relations / chunks → 零调用短路。

读侧对齐：``graphs.py::_QUERY_DOCUMENT_SUBGRAPH`` 查的正是
``(:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity)``。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.services.kg import ThreeStageKgBuilder
from app.services.kg.builder import (
    KgBuildRequest,
    KgDocumentRef,
    _assign_entities_to_chunks,
)


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
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    def __call__(self) -> _FakeSession:
        return _FakeSession(self._calls)


def _make_builder(
    calls: list[tuple[str, dict[str, Any]]], *, batch_size: int = 500
) -> ThreeStageKgBuilder:
    return ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        batch_size=batch_size,
        session_factory=_FakeSessionFactory(calls),
    )


def _entity(entity_id: str, char_start: int = 0) -> dict[str, Any]:
    return {
        "id": entity_id,
        "canonical_name": f"实体{entity_id}",
        "entity_type": "ORG",
        "mention": f"实体{entity_id}",
        "confidence": 0.9,
        "char_start": char_start,
        "char_end": char_start + 4,
    }


def _chunk(chunk_id: str, start: int, end: int, page: int | None = 1) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "char_start": start,
        "char_end": end,
        "text": "正文",
        "page": page,
    }


def _request(
    *,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    document: KgDocumentRef | None = None,
) -> KgBuildRequest:
    return KgBuildRequest(
        org_id=uuid4(),
        version="v-chunk",
        entities=entities,
        relations=relations or [],
        chunks=chunks or [],
        document=document,
        trace_id=uuid4(),
    )


def _find(calls: list[tuple[str, dict[str, Any]]], needle: str) -> dict[str, Any]:
    """取第一条包含 ``needle`` 的 Cypher 的参数（顺序断言用）。"""
    for cypher, params in calls:
        if needle in cypher:
            return params
    raise AssertionError(f"未找到包含 {needle!r} 的 Cypher 段")


def test_five_stage_order_with_evidence_layers() -> None:
    """写侧顺序必须能让读侧 ``_QUERY_DOCUMENT_SUBGRAPH`` 查到：Document→Chunk→Entity。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(
        _request(
            entities=[_entity("e1", char_start=2)],
            chunks=[_chunk("chunk-1", 0, 50)],
            document=KgDocumentRef(doc_id=uuid4(), acl_scope=None),
        )
    )

    cyphers = [cypher for cypher, _ in calls]
    order = [
        "KgVersionMirror",  # stage-1a
        "CREATE CONSTRAINT",  # stage-1b
        "MERGE (d:Document",  # stage-1.5
        "MERGE (n:Entity",  # stage-2
        "MERGE (n:Chunk",  # stage-2.5
        "HAS_CHUNK",  # stage-4a
        "MENTIONS",  # stage-4b
    ]
    positions = [
        next(i for i, c in enumerate(cyphers) if marker in c) for marker in order
    ]
    assert positions == sorted(positions), (
        f"段顺序错乱：{list(zip(order, positions, strict=True))}"
    )

    assert stats.chunk_count == 1
    # 1 条 HAS_CHUNK + 1 条 MENTIONS
    assert stats.evidence_edge_count == 2


def test_acl_scope_inherited_from_document_to_chunks() -> None:
    """``acl_scope``（预留字段，不进契约）从 documents 表继承到 :Document / :Chunk。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(
        _request(
            entities=[_entity("e1")],
            chunks=[_chunk("chunk-1", 0, 50)],
            document=KgDocumentRef(doc_id=uuid4(), acl_scope="org:finance"),
        )
    )

    assert _find(calls, "MERGE (d:Document")["acl_scope"] == "org:finance"
    assert _find(calls, "MERGE (n:Chunk")["acl_scope"] == "org:finance"


def test_chunk_page_none_is_written_as_is() -> None:
    """页码失配（``PageIndex`` 返回 None）→ 原样写 null，**不**补成 1。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(
        _request(
            entities=[],
            chunks=[_chunk("chunk-1", 0, 50, page=None)],
            document=KgDocumentRef(doc_id=uuid4()),
        )
    )

    batch = _find(calls, "MERGE (n:Chunk")["batch"]
    assert batch[0]["page"] is None


def test_mentions_assigns_entity_by_char_range() -> None:
    """实体按 ``char_start`` 落在哪个 chunk 区间归属；区间外的实体不挂靠。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(
        _request(
            entities=[_entity("e_in", char_start=10), _entity("e_out", char_start=999)],
            chunks=[_chunk("chunk-1", 0, 50), _chunk("chunk-2", 50, 100)],
            document=KgDocumentRef(doc_id=uuid4()),
        )
    )

    batch = _find(calls, "MENTIONS")["batch"]
    assert batch == [{"id": "chunk-1", "entity_ids": ["e_in"]}]


def test_assign_entities_to_chunks_edge_cases() -> None:
    """归属函数的边界：半开区间、无 chunk、实体无 id。"""
    chunks = [_chunk("chunk-1", 0, 10), _chunk("chunk-2", 10, 20)]

    # char_start = 10 归属后一个 chunk（半开区间）
    assert _assign_entities_to_chunks(chunks, [{"id": "e1", "char_start": 10}]) == [
        {"id": "chunk-2", "entity_ids": ["e1"]}
    ]
    # 落在所有区间之外 → 不归属（不猜最近邻）
    assert _assign_entities_to_chunks(chunks, [{"id": "e1", "char_start": 99}]) == []
    # 无 chunk → 无归属
    assert _assign_entities_to_chunks([], [{"id": "e1", "char_start": 0}]) == []
    # 实体缺 id → 跳过
    assert _assign_entities_to_chunks(chunks, [{"char_start": 5}]) == []


def test_no_document_skips_evidence_links() -> None:
    """无 ``document`` 引用 → 跳过 stage-1.5 / stage-4（保持 v1.1.0 三段式兼容）。

    chunk 节点**仍会**写入：写节点不依赖文档引用，缺的只是「文档→证据」的挂接。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(
        _request(entities=[_entity("e1")], chunks=[_chunk("chunk-1", 0, 50)])
    )

    cyphers = " ".join(cypher for cypher, _ in calls)
    assert "MERGE (d:Document" not in cyphers
    assert "HAS_CHUNK" not in cyphers
    assert "MENTIONS" not in cyphers
    assert "MERGE (n:Chunk" in cyphers
    assert stats.chunk_count == 1
    assert stats.evidence_edge_count == 0


def test_empty_request_short_circuits_without_neo4j() -> None:
    """entities / relations / chunks 全空 → 零 Neo4j 调用、零统计。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(_request(entities=[]))

    assert calls == []
    assert stats.chunk_count == 0
    assert stats.evidence_edge_count == 0


def test_chunk_batches_are_sliced_by_batch_size() -> None:
    """``kg_build_batch_size`` 对 chunk 同样生效（与实体 / 关系同一批切片器）。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls, batch_size=2)
    doc_id: UUID = uuid4()

    stats = builder.build(
        _request(
            entities=[],
            chunks=[
                _chunk("chunk-1", 0, 10),
                _chunk("chunk-2", 10, 20),
                _chunk("chunk-3", 20, 30),
            ],
            document=KgDocumentRef(doc_id=doc_id),
        )
    )

    chunk_loads = [params for cypher, params in calls if "MERGE (n:Chunk" in cypher]
    assert [len(batch["batch"]) for batch in chunk_loads] == [2, 1]
    # HAS_CHUNK 也按同一批大小切片
    links = [params for cypher, params in calls if "HAS_CHUNK" in cypher]
    assert [len(batch["batch"]) for batch in links] == [2, 1]
    assert _find(calls, "HAS_CHUNK")["doc_id"] == str(doc_id)
    assert stats.chunk_count == 3
    # 3 条 HAS_CHUNK（无实体 → 0 条 MENTIONS）
    assert stats.evidence_edge_count == 3


def test_chunk_position_fields_are_written_as_integers() -> None:
    """位置字段必须**整型**落库（真机教训：曾存成 `'1'` / `'0'` / `'764'`）。

    读侧虽已 ``int()`` 归一，但 Neo4j 里类型是 string 时区间筛选与排序语义都会变；
    写侧一次性 cast 才是根治。``page`` 缺失仍写 ``null``（不伪造页码）。
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(
        _request(
            entities=[_entity("e1", char_start=2)],
            chunks=[
                # 模拟上游给出字符串（真机原样）
                {
                    "id": "chunk-str",
                    "char_start": "0",
                    "char_end": "764",
                    "text": "正文",
                    "page": "3",
                },
                # page 缺失 → null
                {
                    "id": "chunk-nopage",
                    "char_start": 0,
                    "char_end": 10,
                    "text": "正文",
                    "page": None,
                },
            ],
            document=KgDocumentRef(doc_id=uuid4(), acl_scope=None),
        )
    )

    batch = _find(calls, "MERGE (n:Chunk")["batch"]
    by_id = {row["id"]: row for row in batch}

    assert by_id["chunk-str"]["char_start"] == 0
    assert by_id["chunk-str"]["char_end"] == 764
    assert by_id["chunk-str"]["page"] == 3
    assert isinstance(by_id["chunk-str"]["char_start"], int)
    assert isinstance(by_id["chunk-str"]["page"], int)

    assert by_id["chunk-nopage"]["page"] is None
    assert by_id["chunk-nopage"]["char_start"] == 0
