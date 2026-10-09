"""Sprint 9.5 批次 D1：M3 响应新增 ``reasoning_path``（多跳推理路径）。

钉死四条纪律（对应 ``app/services/reasoning.py`` 的模块 docstring）：

1. **零假数据**：每一跳都能回溯到**真实查询**（锚点来自本轮子图、跳转来自 Cypher
   返回行）；定位不到 / 走不到终点 ⇒ 空列表，**不**填示例路径；
2. **数值不出 LLM**：``ReasoningPathHop`` 没有任何数值字段（该断言在
   ``test_boundary_numeric_provenance.py``，与 D2 守卫同族）；
3. **可核查**：每跳带起点 / 终点实体（id + 名称 + 类型）+ 关系类型 + 该跳来源；
4. **可空语义**：``None`` = 未产出（拒答）；``[]`` = 检索了零命中。二者不许混用。

外部依赖（Neo4j / LLM）全部打桩，与 ``test_agent_citations.py`` 同口径。
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import pytest

from app.schemas.agent import AgentQueryRequest
from app.schemas.document import GraphEdge, GraphNode
from app.services.agents import AgentService, AgentUnavailableError
from app.services.graphs import (
    EvidenceChunk,
    GraphService,
    GraphUnavailableError,
    KgVersion,
)
from app.services.reasoning import (
    _TERMINAL_RANK,
    ALL_TERMINAL_TYPES,
    HUB_EMPLOYEE_TYPE,
    TERMINAL_ENTITY_TYPES,
    TERMINAL_PRIORITY_TYPE,
    anchor_ids_for_question,
    build_reasoning_path,
)

DOC_ID = UUID("11111111-2222-3333-4444-555555555555")
QUESTION = "张伟（售后工程师）上周六在武汉出差处理工单，这算加班吗？"

#: 一条真机形状的路径：EMPLOYEE → POSITION → WORK_ORDER
PATH_ROW = {
    "ids": ["EMPLOYEE:E001", "POSITION:P001", "WORK_ORDER:SO-2026-0912"],
    "names": ["张伟", "售后工程师", "SO-2026-0912"],
    "types": ["EMPLOYEE", "POSITION", "WORK_ORDER"],
    "rels": ["HAS_POSITION", "HANDLED_ORDER"],
}


def _node(node_id: str, name: str, entity_type: str = "EMPLOYEE") -> GraphNode:
    return GraphNode(
        id=node_id,
        label="Entity",
        entity_type=entity_type,
        canonical_name=name,
        confidence=0.9,
        kg_version="v-test",
    )


def _edge(source: str, target: str) -> GraphEdge:
    return GraphEdge(
        id=f"r-{source}-{target}",
        type="MENTIONS",
        source=source,
        target=target,
        properties={},
    )


def _chunk(chunk_id: str, text: str) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        doc_id=DOC_ID,
        text=text,
        page=3,
        char_start=0,
        char_end=len(text),
    )


class _FakeSession:
    """记录查询、回放预设行的假 Neo4j 会话（只验接线，不连真机）。"""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.queries: list[str] = []
        self.params: list[dict] = []

    def run(self, cypher: str, **params: object) -> list[dict]:
        self.queries.append(cypher)
        self.params.append(dict(params))
        return list(self._rows)


# --------------------------------------------------------------------------- #
# 第一步：问句 → 定位实体
# --------------------------------------------------------------------------- #
def test_anchor_prefers_longest_name() -> None:
    """「武汉光谷」压过「武汉」——长名优先，避免被子串吃掉定位精度。"""
    nodes = [
        _node("LOCATION:L1", "武汉", "LOCATION_RECORD"),
        _node("LOCATION:L2", "武汉光谷", "LOCATION_RECORD"),
        _node("EMPLOYEE:E001", "张伟"),
    ]
    assert anchor_ids_for_question(question="在武汉光谷出差", nodes=nodes) == (
        "LOCATION:L2",
    )


def test_anchor_ignores_non_entity_and_short_names() -> None:
    """Document / Chunk 不是推理起点；单字名（噪声）不参与定位。"""
    nodes = [
        GraphNode(id="d1", label="Document", kg_version="v-test"),
        _node("X:1", "的"),
        _node("EMPLOYEE:E001", "张伟"),
    ]
    assert anchor_ids_for_question(question="张伟的缺卡", nodes=nodes) == (
        "EMPLOYEE:E001",
    )


# --------------------------------------------------------------------------- #
# 第二 / 三步：沿关系跳转 → 命中条款 / 事实 → 逐跳标注来源
# --------------------------------------------------------------------------- #
def test_path_hops_carry_verifiable_endpoints() -> None:
    """每跳都带起点 / 终点（id + 名称 + 类型）+ 关系类型，且首尾相接。"""
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[
            _node("EMPLOYEE:E001", "张伟"),
            _node("POSITION:P001", "售后工程师", "POSITION"),
        ],
    )

    assert len(hops) == 2
    assert [hop.relation for hop in hops] == ["HAS_POSITION", "HANDLED_ORDER"]
    # 首尾相接：上一跳终点 = 下一跳起点（否则前端画不出链）
    assert hops[0].target.id == hops[1].source.id
    assert hops[0].source.name == "张伟"
    assert hops[0].target.name == "售后工程师"
    assert hops[0].target.entity_type == "POSITION"
    assert hops[-1].target.id == "WORK_ORDER:SO-2026-0912"


def test_every_hop_traces_back_to_the_query_result() -> None:
    """**核心守卫**：每一跳的 (起点, 关系, 终点) 必须逐条出现在 Cypher 返回行里。"""
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )

    ids = PATH_ROW["ids"]
    rels = PATH_ROW["rels"]
    triples = {(ids[i], rels[i], ids[i + 1]) for i in range(len(rels))}
    for hop in hops:
        assert (hop.source.id, hop.relation, hop.target.id) in triples
    # 跳数 = 节点数 - 1：**不**多编一跳
    assert len(hops) == len(PATH_ROW["ids"]) - 1


def test_query_is_parameterized_by_kg_version_and_org() -> None:
    """Cypher 必带 kg_version / org_id / 终点类型过滤（ADR-0002 §3.2 / ADR-0003）。"""
    session = _FakeSession([PATH_ROW])
    build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org-1",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )

    params = session.params[0]
    # P5-H（2026-10-08）：版本过滤由「单值 ``$kg``」换成「版本列表 ``$kgs`` +
    # 选中表 ``$sel``」。**不带视野**的默认形态必须恰好等价于原来的 ``= $kg``：
    # 列表里只有 active 一条、选中表为空 ⇒ 每个节点的版本判定退化为单版本。
    # 这条断言是对既有守卫「Cypher 必带版本过滤」的**同义收紧**，不是放宽。
    assert params["kgs"] == ["v-test"]
    assert params["sel"] == {}
    assert params["org"] == "org-1"
    # Sprint 10 批次 B：终点类型由「考勤一套」扩为「已登记域的并集」
    assert set(params["terminal_types"]) == set(ALL_TERMINAL_TYPES)
    assert set(params["terminal_types"]) >= set(TERMINAL_ENTITY_TYPES)
    assert "EMPLOYEE:E001" in params["anchor_ids"]
    # 关系也要逐个约束租户 / 版本（只过滤端点会放进跨租户边）
    assert "ALL(r IN rels" in session.queries[0]


def test_no_anchor_returns_empty_without_fabricating_hops() -> None:
    """问句没定位到任何实体 ⇒ 空列表（不凭空编跳）。

    **允许发一次查询**：子图被 `node_limit` 截断时锚点会整个消失（真机实测：
    `EMPLOYEE:E001` 常被 SHIFT / ATTENDANCE_RECORD 挤出子图），故允许一次
    「按名字直查确定性派生实体」的兜底；**兜底仍无果 ⇒ []**，不补一跳让链好看。
    """
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question="完全无关的一句话",
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )
    assert hops == []
    assert len(session.queries) == 1  # 只发了锚点兜底查询，没去鲁棒凑路径


def test_no_path_returns_empty_list() -> None:
    """锚点走不到任何条款 / 事实 ⇒ 零命中 = `[]`（**不是** None）。"""
    session = _FakeSession([])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )
    assert hops == []


def test_malformed_rows_are_dropped_not_patched() -> None:
    """脏行（节点数 ≠ 关系数 + 1）整行丢弃，**不**截断补全。"""
    broken = {**PATH_ROW, "rels": ["HAS_POSITION"]}
    session = _FakeSession([broken, PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )
    assert len(hops) == 2

    only_broken = _FakeSession([broken])
    assert (
        build_reasoning_path(
            session=only_broken,
            kg_version="v-test",
            org_id="org",
            question=QUESTION,
            nodes=[_node("EMPLOYEE:E001", "张伟")],
        )
        == []
    )


def test_shortest_path_wins_deterministically() -> None:
    """多条候选 ⇒ 跳数最少者胜（同解保证，可复现）。"""
    long_row = {
        "ids": ["EMPLOYEE:E001", "POSITION:P001", "X:1", "WORK_ORDER:SO-1"],
        "names": ["张伟", "售后工程师", "中间", "SO-2026-0912"],
        "types": ["EMPLOYEE", "POSITION", "X", "WORK_ORDER"],
        "rels": ["HAS_POSITION", "X_TO_Y", "HANDLED_ORDER"],
    }
    session = _FakeSession([long_row, PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )
    assert len(hops) == 2
    assert hops[0].target.id == "POSITION:P001"


# --------------------------------------------------------------------------- #
# 该跳的来源（cypher / graph / document）
# --------------------------------------------------------------------------- #
def test_origin_document_when_terminal_appears_in_chunk_text() -> None:
    """终点能在注入的原文片段里找到 ⇒ `document` + 出处 `chunk:<id>`。"""
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
        chunks=[_chunk("chunk-abc0001", "工单 SO-2026-0912 于 10:22 闭环。")],
    )
    assert hops[-1].origin == "document"
    assert hops[-1].evidence == "chunk:chunk-abc0001"
    # 没有原文支撑的跳仍老实标 cypher
    assert hops[0].origin == "cypher"
    assert hops[0].evidence is None


def test_origin_graph_when_edge_already_in_subgraph() -> None:
    """该跳的两端点已在本轮检索到的子图边集里 ⇒ `graph`。"""
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
        edges=[_edge("EMPLOYEE:E001", "POSITION:P001")],
    )
    assert hops[0].origin == "graph"
    assert hops[1].origin == "cypher"


def test_origin_prefers_document_over_graph() -> None:
    """证据强度取最高：`document` > `graph` > `cypher`（不许把弱来源标成强来源）。"""
    session = _FakeSession([PATH_ROW])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
        edges=[_edge("POSITION:P001", "WORK_ORDER:SO-2026-0912")],
        chunks=[_chunk("chunk-abc0001", "... SO-2026-0912 ...")],
    )
    assert hops[-1].origin == "document"


def test_missing_name_falls_back_to_id_without_inventing() -> None:
    """节点缺 `canonical_name` ⇒ 名称回落 id（**不**编一个名字）。"""
    row = {
        **PATH_ROW,
        "names": [None, None, None],
        "types": ["EMPLOYEE", None, "WORK_ORDER"],
    }
    session = _FakeSession([row])
    hops = build_reasoning_path(
        session=session,
        kg_version="v-test",
        org_id="org",
        question=QUESTION,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
    )
    assert hops[0].source.name == "EMPLOYEE:E001"
    # entity_type 缺失 ⇒ null（不猜类型）
    assert hops[0].target.entity_type is None


# --------------------------------------------------------------------------- #
# 端到端（服务层，LLM / Neo4j 打桩）
# --------------------------------------------------------------------------- #
def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    chunks: list[EvidenceChunk],
    path_rows: list[dict],
    llm_answer: str,
    reasoning_boom: bool = False,
) -> None:
    monkeypatch.setattr(
        GraphService,
        "fetch_active_kg_version",
        lambda self, scope=None, **kwargs: KgVersion(version="v-test", scope="global"),
    )
    monkeypatch.setattr(
        GraphService, "fetch_all_subgraph", lambda self, **kwargs: (nodes, edges, False)
    )
    monkeypatch.setattr(
        GraphService, "validate_kg_version_tenant_boundary", lambda self, **kwargs: True
    )
    monkeypatch.setattr(
        GraphService, "fetch_evidence_chunks", lambda self, **kwargs: list(chunks)
    )
    monkeypatch.setattr(AgentService, "_ensure_chat", lambda self: None)

    def fake_path(self: GraphService, **kwargs: object) -> list[object]:
        if reasoning_boom:
            raise GraphUnavailableError("connection refused")
        return build_reasoning_path(
            session=_FakeSession(path_rows),
            kg_version=str(kwargs["kg_version"]),
            org_id=kwargs["org_id"],
            question=str(kwargs["question"]),
            nodes=kwargs["nodes"],  # type: ignore[arg-type]
            edges=kwargs["edges"],  # type: ignore[arg-type]
            chunks=kwargs["chunks"],  # type: ignore[arg-type]
        )

    monkeypatch.setattr(GraphService, "fetch_reasoning_path", fake_path)

    async def fake_invoke(self: AgentService, **kwargs: object) -> tuple[str, None]:
        return llm_answer, None

    monkeypatch.setattr(AgentService, "_invoke_chat_with_retry", fake_invoke)


def _llm_answer(evidence: list[str]) -> str:
    return json.dumps(
        {"answer": "是的。", "evidence": evidence, "confidence": "high"},
        ensure_ascii=False,
    )


def test_query_response_carries_reasoning_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """主线：正常回答带逐跳链（不是 null、也不是空列表）。"""
    _patch_pipeline(
        monkeypatch,
        nodes=[
            _node("EMPLOYEE:E001", "张伟"),
            _node("POSITION:P001", "售后工程师", "POSITION"),
        ],
        edges=[],
        chunks=[_chunk("chunk-abc0001", "甲方：北京青云科技有限公司。")],
        path_rows=[PATH_ROW],
        llm_answer=_llm_answer(["chunk-abc0001"]),
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question=QUESTION),
            org_id=uuid4(),
            trace_id="t-d1-ok",
        )
    )

    assert response.refused is False
    assert response.reasoning_path is not None
    assert len(response.reasoning_path) == 2
    assert response.reasoning_path[0].source.id == "EMPLOYEE:E001"


def test_refused_response_has_null_path_not_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**可空语义**：拒答 = `None`（未产出），**不**用 `[]` 冒充「检索过、零命中」。"""
    _patch_pipeline(
        monkeypatch,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
        edges=[],
        chunks=[_chunk("chunk-abc0001", "甲方：北京青云科技有限公司。")],
        path_rows=[PATH_ROW],
        llm_answer=_llm_answer(["chunk-deadbeef0000"]),  # LLM 编造 ⇒ 引用覆盖率 0
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question=QUESTION),
            org_id=uuid4(),
            trace_id="t-d1-refused",
        )
    )

    assert response.refused is True
    assert response.reasoning_path is None


def test_reasoning_path_failure_is_501_not_silent_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neo4j 在路径阶段挂掉 → `AgentUnavailableError`（501）。

    **不**降级为 `[]`：空路径 = 零命中，会把基础设施故障伪装成「图上没有链」。
    """
    _patch_pipeline(
        monkeypatch,
        nodes=[_node("EMPLOYEE:E001", "张伟")],
        edges=[],
        chunks=[_chunk("chunk-abc0001", "甲方：北京青云科技有限公司。")],
        path_rows=[PATH_ROW],
        llm_answer=_llm_answer(["chunk-abc0001"]),
        reasoning_boom=True,
    )

    with pytest.raises(AgentUnavailableError):
        asyncio.run(
            AgentService.instance().query(
                request=AgentQueryRequest(question=QUESTION),
                org_id=uuid4(),
                trace_id="t-d1-boom",
            )
        )


# --------------------------------------------------------------------------- #
# Sprint 10 批次 B（裁决 D-F）：终点类型按**域**登记，不再写死考勤本体
# --------------------------------------------------------------------------- #


def test_terminal_types_cover_both_registered_domains() -> None:
    """两个已登记域的落点都在白名单里。

    真机缺口（`changes/Sprint10.1/proposal.md` §1）：改之前 `affiliation-demo-v1`
    的 176 个实体**一个都不在**考勤白名单里 ⇒ 该域的多跳链恒为空。
    """
    assert "POLICY_CLAUSE" in ALL_TERMINAL_TYPES  # 考勤
    assert "SUBJECT" in ALL_TERMINAL_TYPES  # 关联方
    assert "LEGAL_PERSON" in ALL_TERMINAL_TYPES


def test_terminal_types_exclude_unregistered_types() -> None:
    """未登记的类型**不是**合法落点。

    这条是纪律 1「零假数据」的守卫：新业务域没登记时，链自然取不到（空列表），
    而不是"放宽成任意类型、随便走两跳"——那叫编链。
    """
    for unregistered in ("POSITION", "DEPARTMENT", "RELATED", "PHONE"):
        assert unregistered not in ALL_TERMINAL_TYPES


def test_build_path_queries_with_union_terminal_types() -> None:
    """取链时下发的是**并集**白名单 + 两域各自的最优落点（不再写死考勤一套）。

    刻意用"关联方子图"当输入：改之前这套输入会命中不了任何考勤终点。
    """
    session = _FakeSession(rows=[PATH_ROW])

    build_reasoning_path(
        session=session,  # type: ignore[arg-type]
        kg_version="v-test",
        org_id="org-1",
        question="甲公司与乙公司是否由同一人代表？",
        nodes=[
            _node("SUBJECT:S1", "甲公司", "SUBJECT"),
            _node("EMPLOYEE:E001", "张伟", "EMPLOYEE"),
        ],
    )

    assert session.queries, "未发起路径查询"
    sent = session.params[-1]
    assert "SUBJECT" in sent["terminal_types"]
    assert "POLICY_CLAUSE" in sent["terminal_types"]
    # P6-V1（2026-10-09）：排序口径不再下发 ``prio_types``（它把 LEGAL_PERSON 也算
    # 优先终点，与 Python 侧第 1 维只认 POLICY_CLAUSE **不等价**）。改为下发
    # ``prio_type`` / ``terminal_rank``，值取自 Python 侧精排同一份常量。
    assert sent["prio_type"] == TERMINAL_PRIORITY_TYPE
    assert sent["terminal_rank"] == dict(_TERMINAL_RANK)
    assert sent["terminal_rank_default"] == len(_TERMINAL_RANK)
    # hub 约束保留：中途禁止穿员工（考勤域实测：不禁会每条都出"员工→员工"废链）
    assert sent["hub"] == HUB_EMPLOYEE_TYPE
