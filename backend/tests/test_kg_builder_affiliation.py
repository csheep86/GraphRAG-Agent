"""Sprint 7.1 批次 A §2.2：M4 主体层写入（`:Subject` / `:Address` / `:LegalPerson` + 两条边）。

Neo4j 零依赖：`session_factory` 注入桩记录每段 Cypher 与参数。覆盖点对应
``changes/Sprint7.1/tasks.md`` §2.2 的验收清单：

1. 三类节点都按 M4 §4.1 属性写入，且带 ``kg_version``（ADR-0002：与 M2 同版本不分裂）；
   ``tax_id`` / ``region_code`` / ``id_hash`` **缺失即 null，不兜底生成**；
2. ``LEGAL_REP`` / ``REGISTERED_AT`` 两条边的端点必须是对应的三类节点；
3. **不与 ``:Entity`` 桥接**（M4 段不写 Entity、不打补丁）；
4. 同名跨文档**合成同一节点**（这是共享法人两跳算法能成立的前提）；
5. 无 affiliation 数据时**一段都不跑**（保持既有调用方行为）；
6. 失败包装为 :class:`GraphUnavailableError`。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.services.graphs import GraphUnavailableError
from app.services.kg import ThreeStageKgBuilder
from app.services.kg.builder import (
    _CYPHER_STAGE2C_LOAD_SUBJECTS,
    _CYPHER_STAGE2D_LOAD_ADDRESSES,
    _CYPHER_STAGE2E_LOAD_LEGAL_PERSONS,
    _CYPHER_STAGE3B_LEGAL_REP,
    _CYPHER_STAGE3C_REGISTERED_AT,
    KgBuildRequest,
    KgDocumentRef,
    build_affiliation_rows,
)

_ORG = {
    "id": "ent_001",
    "canonical_name": "招商局集团有限公司",
    "entity_type": "ORG",
    "mention": "招商局集团有限公司",
    "confidence": 0.95,
}
_PERSON = {
    "id": "ent_002",
    "canonical_name": "缪建民",
    "entity_type": "LEGAL_PERSON",
    "mention": "缪建民",
    "confidence": 0.93,
}
_ADDRESS = {
    "id": "ent_003",
    "canonical_name": "北京市朝阳区建国路 118 号",
    "entity_type": "ADDRESS",
    "mention": "北京市朝阳区建国路 118 号",
    "confidence": 0.9,
}
_LEGAL_REP = {
    "id": "rel_001",
    "source_entity_id": "ent_001",
    "target_entity_id": "ent_002",
    "relation_type": "LEGAL_REP",
    "evidence": "法定代表人：缪建民",
    "confidence": 0.92,
}
_REGISTERED_AT = {
    "id": "rel_002",
    "source_entity_id": "ent_001",
    "target_entity_id": "ent_003",
    "relation_type": "REGISTERED_AT",
    "evidence": "住所：北京市朝阳区建国路 118 号",
    "confidence": 0.9,
}


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


def _request(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    acl_scope: str | None = None,
) -> KgBuildRequest:
    return KgBuildRequest(
        org_id=uuid4(),
        version="v-m4",
        entities=entities,
        relations=relations,
        trace_id=uuid4(),
        document=KgDocumentRef(doc_id=uuid4(), acl_scope=acl_scope),
    )


# --------------------------------------------------------------------------- #
# build_affiliation_rows（纯函数）
# --------------------------------------------------------------------------- #


def test_rows_from_legal_rep_and_registered_at() -> None:
    rows = build_affiliation_rows(
        [_ORG, _PERSON, _ADDRESS], [_LEGAL_REP, _REGISTERED_AT], version="v-m4"
    )

    assert len(rows.subjects) == 1
    assert len(rows.legal_persons) == 1
    assert len(rows.addresses) == 1
    assert len(rows.legal_rep_edges) == 1
    assert len(rows.registered_at_edges) == 1

    subject = rows.subjects[0]
    assert subject["name"] == "招商局集团有限公司"
    assert subject["type"] == "ORG"
    assert subject["tax_id"] is None, "没有统一社会信用代码就 null，不许拿名字凑"
    address = rows.addresses[0]
    assert address["full_address"] == "北京市朝阳区建国路 118 号"
    assert address["region_code"] is None, "不猜行政区划"
    person = rows.legal_persons[0]
    assert person["name"] == "缪建民"
    assert person["id_hash"] is None, "严禁兜底生成哈希"


def test_same_fact_across_documents_collapses_into_one_edge() -> None:
    """共享法人是**两跳**查询：不同文档里同名的法人必须合成同一个节点；
    而同一条**事实**（同一对 主体→法人）在 N 份文档里出现，必须是 **1 条边**。

    抽取侧的实体 id 是 ``ent_<uuid>``（每次抽取都不同，跨文档必然连不上），
    所以行构造必须按**名称**算稳定 id。

    边也按**端点**算 id（``_relatioin_id`` 来自抽取侧，用它会导致同一事实
    MERGE 出 N 条并行边 → M4 两跳按**路径**匹配，同一疑点被报 N 遍；真机踩到过）。
    多份文档的重复命中不丢信息：证据汇聚在节点的 ``source_entity_ids`` 里
    （见 :func:`test_repeated_facts_accumulate_source_entity_ids`）。
    """
    org_a = {**_ORG, "id": "ent_100", "canonical_name": "北京青云科技有限公司"}
    org_b = {**_ORG, "id": "ent_200", "canonical_name": "北京青云科技有限公司"}
    person_a = {**_PERSON, "id": "ent_101"}
    person_b = {**_PERSON, "id": "ent_201"}
    rel_a = {
        **_LEGAL_REP,
        "id": "rel_100",
        "source_entity_id": "ent_100",
        "target_entity_id": "ent_101",
    }
    rel_b = {
        **_LEGAL_REP,
        "id": "rel_200",
        "source_entity_id": "ent_200",
        "target_entity_id": "ent_201",
    }

    rows = build_affiliation_rows(
        [org_a, org_b, person_a, person_b], [rel_a, rel_b], version="v-m4"
    )

    assert len(rows.subjects) == 1, "同名同公司应合并为一个 :Subject"
    assert len(rows.legal_persons) == 1, "同名法人必须合并成一个 :LegalPerson"
    assert len(rows.legal_rep_edges) == 1, "同一事实在不同文档里必须合成一条边"
    assert rows.legal_rep_edges[0]["source_id"] == rows.subjects[0]["id"]
    assert rows.legal_rep_edges[0]["target_id"] == rows.legal_persons[0]["id"]
    # 两份文档的溯源都不丢（"少了一条边"≠"少了一份证据"）
    assert rows.legal_persons[0]["source_entity_ids"] == ["ent_101", "ent_201"]
    assert rows.subjects[0]["source_entity_ids"] == ["ent_100", "ent_200"]


def test_registered_at_same_fact_across_documents_collapses_into_one_edge() -> None:
    """同上，地址侧：同一 (公司, 地址) 事实跨文档合并为一条 ``REGISTERED_AT``。"""
    org_a = {**_ORG, "id": "ent_300"}
    org_b = {**_ORG, "id": "ent_400"}
    address_a = {**_ADDRESS, "id": "ent_301"}
    address_b = {**_ADDRESS, "id": "ent_401"}
    rel_a = {
        **_REGISTERED_AT,
        "id": "rel_300",
        "source_entity_id": "ent_300",
        "target_entity_id": "ent_301",
    }
    rel_b = {
        **_REGISTERED_AT,
        "id": "rel_400",
        "source_entity_id": "ent_400",
        "target_entity_id": "ent_401",
    }

    rows = build_affiliation_rows(
        [org_a, org_b, address_a, address_b], [rel_a, rel_b], version="v-m4"
    )

    assert len(rows.subjects) == 1
    assert len(rows.addresses) == 1
    assert len(rows.registered_at_edges) == 1
    assert rows.addresses[0]["source_entity_ids"] == ["ent_301", "ent_401"]


def test_type_mismatch_or_dangling_endpoints_are_dropped() -> None:
    """类型对不上 / 悬空端点 → 丢弃。**不**退化为「拿实体硬凑一条边」。"""
    wrong_source = {
        "id": "ent_009",
        "canonical_name": "张三",
        "entity_type": "PERSON",
        "mention": "张三",
    }
    rows = build_affiliation_rows(
        [_ORG, _PERSON, wrong_source],
        [
            # source 是 PERSON（不是 ORG）→ 不能当 :Subject
            {
                "id": "rel_901",
                "source_entity_id": "ent_009",
                "target_entity_id": "ent_002",
                "relation_type": "LEGAL_REP",
            },
            # target 类型不符（ORG 不是 LegalPerson）
            {
                "id": "rel_902",
                "source_entity_id": "ent_001",
                "target_entity_id": "ent_001",
                "relation_type": "LEGAL_REP",
            },
            # 悬空端点
            {
                "id": "rel_903",
                "source_entity_id": "ent_404",
                "target_entity_id": "ent_002",
                "relation_type": "LEGAL_REP",
            },
        ],
        version="v-m4",
    )
    assert rows.is_empty


def test_unrelated_relations_produce_no_rows() -> None:
    """M2 的其它关系（PARTY_TO 等）不产出任何 M4 行（避免主体层被污染）。"""
    rows = build_affiliation_rows(
        [_ORG, _PERSON],
        [
            {
                "id": "rel_801",
                "source_entity_id": "ent_001",
                "target_entity_id": "ent_002",
                "relation_type": "PARTY_TO",
            }
        ],
        version="v-m4",
    )
    assert rows.is_empty


# --------------------------------------------------------------------------- #
# 写入段落
# --------------------------------------------------------------------------- #


def test_stage_order_subjects_then_addresses_then_persons_then_edges() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(
        _request([_ORG, _PERSON, _ADDRESS], [_LEGAL_REP, _REGISTERED_AT])
    )

    assert stats.subject_count == 1
    assert stats.address_count == 1
    assert stats.legal_person_count == 1
    assert stats.affiliation_edge_count == 2

    order = [cypher for cypher, _ in calls][-5:]
    assert order == [
        _CYPHER_STAGE2C_LOAD_SUBJECTS.strip(),
        _CYPHER_STAGE2D_LOAD_ADDRESSES.strip(),
        _CYPHER_STAGE2E_LOAD_LEGAL_PERSONS.strip(),
        _CYPHER_STAGE3B_LEGAL_REP.strip(),
        _CYPHER_STAGE3C_REGISTERED_AT.strip(),
    ]


def test_rows_carry_kg_version_and_acl_scope() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(
        _request([_ORG, _PERSON], [_LEGAL_REP], acl_scope="restricted:contract")
    )

    by_cypher = {cypher.strip(): params for cypher, params in calls}
    params = by_cypher[_CYPHER_STAGE2C_LOAD_SUBJECTS.strip()]
    assert params["kg_version"] == "v-m4", "ADR-0002：与 M2 共享同一版本，不分裂"
    assert params["acl_scope"] == "restricted:contract", ":Subject 继承文档 acl_scope"
    assert by_cypher[_CYPHER_STAGE2E_LOAD_LEGAL_PERSONS.strip()]["acl_scope"] == (
        "restricted:contract"
    ), ":LegalPerson / :Address 继承 acl_scope（S11 RLS 穿透要用）"


def test_no_affiliation_data_runs_no_m4_stage() -> None:
    """抽取产物里没有法人 / 地址时，**一段都不跑**（保持既有调用方看到的行为）。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    stats = builder.build(
        _request(
            [{"id": "e1", "canonical_name": "某公司", "entity_type": "ORG"}],
            [
                {
                    "id": "r1",
                    "source_entity_id": "e1",
                    "target_entity_id": "e1",
                    "relation_type": "PARTY_TO",
                }
            ],
        )
    )

    assert (stats.subject_count, stats.legal_person_count, stats.address_count) == (
        0,
        0,
        0,
    )
    assert stats.affiliation_edge_count == 0
    m4_cyphers = {
        _CYPHER_STAGE2C_LOAD_SUBJECTS.strip(),
        _CYPHER_STAGE2D_LOAD_ADDRESSES.strip(),
        _CYPHER_STAGE2E_LOAD_LEGAL_PERSONS.strip(),
        _CYPHER_STAGE3B_LEGAL_REP.strip(),
        _CYPHER_STAGE3C_REGISTERED_AT.strip(),
    }
    assert not (m4_cyphers & {cypher for cypher, _ in calls})


def test_m4_stages_do_not_touch_entity_layer() -> None:
    """**不与 :Entity 桥接**：M4 段不得出现 Entity / MENTIONS / 任何 Entity 属性补丁。"""
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls)

    builder.build(_request([_ORG, _PERSON, _ADDRESS], [_LEGAL_REP, _REGISTERED_AT]))

    m4_calls = [
        params
        for cypher, params in calls
        if cypher.strip().startswith(("UNWIND $batch",))
        and "mention" not in str(params)
        and cypher.strip()
        in {
            _CYPHER_STAGE2C_LOAD_SUBJECTS.strip(),
            _CYPHER_STAGE2D_LOAD_ADDRESSES.strip(),
            _CYPHER_STAGE2E_LOAD_LEGAL_PERSONS.strip(),
            _CYPHER_STAGE3B_LEGAL_REP.strip(),
            _CYPHER_STAGE3C_REGISTERED_AT.strip(),
        }
    ]
    assert m4_calls, "本例应有 M4 写入"
    blob = "\n".join(str(params) for params in m4_calls)
    assert ":Entity" not in blob and "MENTIONS" not in blob


def test_batch_size_is_respected() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    builder = _make_builder(calls, batch_size=1)

    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for index in range(3):
        entities.extend(
            [
                {**_ORG, "id": f"org_{index}", "canonical_name": f"公司{index}"},
                {**_PERSON, "id": f"p_{index}", "canonical_name": f"法人{index}"},
            ]
        )
        relations.append(
            {
                **_LEGAL_REP,
                "id": f"rel_{index}",
                "source_entity_id": f"org_{index}",
                "target_entity_id": f"p_{index}",
            }
        )

    stats = builder.build(_request(entities, relations))

    assert stats.subject_count == 3 and stats.legal_person_count == 3
    subject_calls = [
        params
        for cypher, params in calls
        if cypher.strip() == _CYPHER_STAGE2C_LOAD_SUBJECTS.strip()
    ]
    assert len(subject_calls) == 3, "batch_size=1 ⇒ 三个 :Subject 分三批写"


def test_driver_failure_is_wrapped_as_graph_unavailable() -> None:
    class _BoomSession(_FakeSession):
        def run(self, cypher: str, **params: Any) -> _FakeResult:
            if cypher.strip() == _CYPHER_STAGE2C_LOAD_SUBJECTS.strip():
                raise RuntimeError("Neo4j 连接中断")
            return _FakeResult()

    class _Factory:
        def __call__(self) -> _BoomSession:
            calls: list[tuple[str, dict[str, Any]]] = []
            return _BoomSession(calls)

    builder = ThreeStageKgBuilder(
        graph_service=object(),  # type: ignore[arg-type]
        batch_size=500,
        session_factory=_Factory(),
    )

    with pytest.raises(GraphUnavailableError, match="stage-2.6/3.2 失败"):
        builder.build(_request([_ORG, _PERSON], [_LEGAL_REP]))
