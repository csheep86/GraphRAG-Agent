"""Sprint 7.1 批次 A §2.3：M4 规则算法（共享法人 / 共享地址）单测。

Neo4j 零依赖：``AffiliationService`` 注入 ``GraphService`` 桩。覆盖：

1. 两类疑点都产出，``type ∈ {shared_legal_rep, shared_address}``，结构对齐 M4 §3 验收 3；
2. **无证据不产疑点**（引用覆盖率 100% 的硬要求），且丢弃**必须留痕**不算静默；
3. 证据带 ``node_id`` 归属 + ``chunk_id`` 原文定位（可点击）；
4. ``doc_id`` 非法 / 缺失 → ``None``，**不**伪造 UUID；
5. Neo4j 不可用 → 抛 :class:`GraphUnavailableError`，**不**降级为「没有疑点」；
6. 严重度固定 ``medium``（本批次**无**可调阈值）。

另含 ``build_affiliation_rows`` 的溯源字段用例（``source_entity_ids`` 是证据链的地基）。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.services.graphs import GraphUnavailableError
from app.services.kg import AffiliationService
from app.services.kg.builder import build_affiliation_rows

_KG = "v-m4"
_ORG_ID = uuid4()


def _hit(suspicion_type: str, suffix: str = "1") -> dict[str, Any]:
    return {
        "suspicion_type": suspicion_type,
        "subject_a_id": f"sub-a{suffix}",
        "subject_a_name": f"公司A{suffix}",
        "subject_b_id": f"sub-b{suffix}",
        "subject_b_name": f"公司B{suffix}",
        "shared_id": f"shared-{suffix}",
        "shared_name": f"共享节点{suffix}",
    }


def _evidence(node_id: str, chunk_id: str) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "chunk_id": chunk_id,
        "doc_id": str(uuid4()),
        "text": f"{node_id} 的原文片段",
        "page": 12,
        "char_start": 100,
        "char_end": 160,
    }


class _GraphStub:
    """``GraphService`` 替身：按参数回数据；``raise_error`` 时模拟 Neo4j 不可达。"""

    def __init__(
        self,
        hits: list[dict[str, Any]] | None = None,
        evidence: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._hits = hits or []
        self._evidence = evidence or {}
        self.evidence_calls: list[list[str]] = []

    def fetch_shared_affiliations(
        self, *, kg_version: str, org_id: Any = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        assert kg_version == _KG
        return self._hits

    def fetch_affiliation_evidence(
        self,
        *,
        kg_version: str,
        node_ids: list[str],
        org_id: Any = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.evidence_calls.append(list(node_ids))
        rows: list[dict[str, Any]] = []
        for node_id in node_ids:
            rows.extend(self._evidence.get(node_id, []))
        return rows


class _BrokenGraph(_GraphStub):
    def fetch_shared_affiliations(
        self, *, kg_version: str, org_id: Any = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        raise GraphUnavailableError("neo4j connection refused")


def _service(graph: _GraphStub) -> AffiliationService:
    return AffiliationService(graph_service=graph)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #


def test_two_rule_types_produce_suspicions() -> None:
    graph = _GraphStub(
        hits=[_hit("shared_legal_rep", "1"), _hit("shared_address", "2")],
        evidence={
            "sub-a1": [_evidence("sub-a1", "chunk-1")],
            "shared-2": [_evidence("shared-2", "chunk-2")],
        },
    )

    suspicions = _service(graph).detect(kg_version=_KG, org_id=_ORG_ID)

    assert [s.suspicion_type for s in suspicions] == [
        "shared_legal_rep",
        "shared_address",
    ]
    for suspicion in suspicions:
        assert suspicion.severity == "medium", "本批次严重度固定，无阈值可调"
        assert len(suspicion.entities) == 3, "entities = [主体A, 主体B, 共享节点]"
        assert suspicion.evidence, "引用覆盖率 100%：每条疑点必须有证据"


def test_no_evidence_means_no_suspicion() -> None:
    """取不到 :Chunk 证据的命中**丢弃**——不留「启发式但无原文」的疑点。"""
    graph = _GraphStub(hits=[_hit("shared_legal_rep")], evidence={})

    assert _service(graph).detect(kg_version=_KG, org_id=_ORG_ID) == []
    # 丢弃不是静默：仍然发起过证据查询（日志 side 另有 WARNING 记账）
    assert graph.evidence_calls == [["sub-a1", "sub-b1", "shared-1"]]


def test_evidence_carries_node_and_chunk_identity() -> None:
    graph = _GraphStub(
        hits=[_hit("shared_legal_rep")],
        evidence={
            "sub-a1": [_evidence("sub-a1", "chunk-a")],
            "shared-1": [_evidence("shared-1", "chunk-shared")],
        },
    )

    suspicion = _service(graph).detect(kg_version=_KG, org_id=_ORG_ID)[0]

    assert {item.node_id for item in suspicion.evidence} == {"sub-a1", "shared-1"}
    first = suspicion.evidence[0]
    assert first.chunk_id.startswith("chunk-")
    assert first.page == 12 and (first.char_end - first.char_start) == 60
    assert first.doc_id is not None


def test_invalid_doc_id_becomes_none_not_fabricated() -> None:
    bad = {**_evidence("sub-a1", "chunk-1"), "doc_id": "not-a-uuid"}
    graph = _GraphStub(hits=[_hit("shared_legal_rep")], evidence={"sub-a1": [bad]})

    suspicion = _service(graph).detect(kg_version=_KG, org_id=_ORG_ID)[0]

    assert suspicion.evidence[0].doc_id is None, "非法 doc_id 归 None，严禁造占位 UUID"


def test_evidence_capped_per_suspicion() -> None:
    many = [_evidence("sub-a1", f"chunk-{i}") for i in range(20)]
    graph = _GraphStub(hits=[_hit("shared_legal_rep")], evidence={"sub-a1": many})

    suspicion = AffiliationService(
        graph_service=graph,
        max_evidence=3,  # type: ignore[arg-type]
    ).detect(kg_version=_KG, org_id=_ORG_ID)[0]

    assert len(suspicion.evidence) == 3


def test_graph_unavailable_is_not_silently_empty() -> None:
    """Neo4j 挂了必须抛：**不能**让「没跑成」与「没有疑点」长得一样。"""
    with pytest.raises(GraphUnavailableError):
        _service(_BrokenGraph()).detect(kg_version=_KG, org_id=_ORG_ID)


def test_to_dict_shape_matches_spec_acceptance() -> None:
    graph = _GraphStub(
        hits=[_hit("shared_address")],
        evidence={"sub-a1": [_evidence("sub-a1", "chunk-1")]},
    )

    payload = _service(graph).detect(kg_version=_KG, org_id=_ORG_ID)[0].to_dict()

    assert set(payload) == {"type", "severity", "entities", "entity_names", "evidence"}
    assert payload["type"] == "shared_address"
    assert payload["evidence"][0]["chunk_id"] == "chunk-1"


# --------------------------------------------------------------------------- #
# §2.3 的地基：主体层节点的 source_entity_ids 溯源
# --------------------------------------------------------------------------- #


def test_affiliation_rows_carry_source_entity_ids() -> None:
    """``source_entity_ids`` 是「疑点能回原文」的唯一通路（:Chunk 只 MENTIONS :Entity）。"""
    rows = build_affiliation_rows(
        [
            {
                "id": "ent_org",
                "canonical_name": "招商局集团有限公司",
                "entity_type": "ORG",
            },
            {
                "id": "ent_person",
                "canonical_name": "缪建民",
                "entity_type": "LEGAL_PERSON",
            },
            {
                "id": "ent_addr",
                "canonical_name": "北京市朝阳区建国路 118 号",
                "entity_type": "ADDRESS",
            },
        ],
        [
            {
                "id": "rel_1",
                "source_entity_id": "ent_org",
                "target_entity_id": "ent_person",
                "relation_type": "LEGAL_REP",
            },
            {
                "id": "rel_2",
                "source_entity_id": "ent_org",
                "target_entity_id": "ent_addr",
                "relation_type": "REGISTERED_AT",
            },
        ],
        version=_KG,
    )

    assert rows.subjects[0]["source_entity_ids"] == ["ent_org"]
    assert rows.legal_persons[0]["source_entity_ids"] == ["ent_person"]
    assert rows.addresses[0]["source_entity_ids"] == ["ent_addr"]


def test_same_node_from_two_documents_accumulates_sources() -> None:
    """同一法人被两份文档抽到 → 溯源**累加**（不是覆盖），否则会丢一半证据。"""
    rows = build_affiliation_rows(
        [
            {"id": "org_1", "canonical_name": "甲公司", "entity_type": "ORG"},
            {"id": "p_1", "canonical_name": "缪建民", "entity_type": "LEGAL_PERSON"},
            {"id": "org_2", "canonical_name": "乙公司", "entity_type": "ORG"},
            {"id": "p_2", "canonical_name": "缪建民", "entity_type": "LEGAL_PERSON"},
        ],
        [
            {
                "id": "rel_1",
                "source_entity_id": "org_1",
                "target_entity_id": "p_1",
                "relation_type": "LEGAL_REP",
            },
            {
                "id": "rel_2",
                "source_entity_id": "org_2",
                "target_entity_id": "p_2",
                "relation_type": "LEGAL_REP",
            },
        ],
        version=_KG,
    )

    assert len(rows.legal_persons) == 1
    assert rows.legal_persons[0]["source_entity_ids"] == ["p_1", "p_2"]
    assert len(rows.subjects) == 2
