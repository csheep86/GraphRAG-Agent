"""阶段九 9.3：`GET /documents/{id}/graph` 与 `POST /agent/query` 端点测试。

**全部外部依赖打桩**：`conftest.py` 已把 `NEO4J_URI` 指向不可达端口，保证
GraphService 确定性抛 :class:`GraphUnavailableError`；需要「图谱可用」的用例
一律用 ``monkeypatch`` 显式打桩，**不依赖真实 Neo4j / DeepSeek**。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent import (
    AgentQueryRequest,
    AgentQueryResponse,
    TokenUsage,
)
from app.schemas.document import DocumentGraphResponse, GraphEdge, GraphNode
from app.services.agents import AgentService, AgentUnavailableError
from app.services.graphs import (
    GraphService,
    GraphUnavailableError,
    KgVersion,
    NoActiveKgVersionError,
)

PDF = ("合同.pdf", b"%PDF-1.4", "application/pdf")

# 契约字段集（`contracts/openapi.yaml`），用于「不多不少」回归断言
DOCUMENT_GRAPH_KEYS = {
    "doc_id",
    "kg_version",
    "version_status",
    "nodes",
    "edges",
    "node_count",
    "relation_count",
    "truncated",
    "trace_id",
}
AGENT_QUERY_KEYS = {
    "answer",
    "citations",
    "route",
    "confidence",
    "refused",
    "refusal_reason",
    "kg_version",
    "trace_id",
    # Sprint 4 阶段 10.0 批次 A：契约已扩展（Sprint 3 缺口 1）
    "kg_nodes",
    "kg_relations",
    "token_usage",
}


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _upload(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/documents/upload", files={"file": PDF}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


def _graph_node(node_id: str, name: str) -> GraphNode:
    return GraphNode(
        id=node_id,
        label="Entity",
        entity_type="公司",
        canonical_name=name,
        confidence=0.9,
        kg_version="v-test",
    )


def _graph_edge(edge_id: str, source: str, target: str) -> GraphEdge:
    return GraphEdge(
        id=edge_id,
        type="AFFILIATED_WITH",
        source=source,
        target=target,
        properties={"relation_name": "持股", "share_pct": 51.0},
    )


def _patch_graph_ok(
    monkeypatch: pytest.MonkeyPatch,
    *,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    truncated: bool = False,
    version: str = "v-test",
) -> dict[str, object]:
    """打桩 GraphService：active 版本可查 + 子图返回固定夹具。

    :returns: 记录调用参数的 dict，供用例断言路由是否传对了版本 / org / 上限。
    """
    calls: dict[str, object] = {}

    def fake_active(self: GraphService, *, scope: str | None = None) -> KgVersion:
        calls["active_scope"] = scope
        return KgVersion(version=version, scope="global")

    def fake_document_subgraph(
        self: GraphService,
        *,
        doc_id: UUID,
        kg_version: str,
        org_id: UUID | None = None,
        node_limit: int = 500,
    ) -> tuple[list[GraphNode], list[GraphEdge], bool]:
        calls["doc_id"] = doc_id
        calls["kg_version"] = kg_version
        calls["org_id"] = org_id
        calls["node_limit"] = node_limit
        return nodes, edges, truncated

    monkeypatch.setattr(GraphService, "fetch_active_kg_version", fake_active)
    monkeypatch.setattr(GraphService, "fetch_document_subgraph", fake_document_subgraph)
    return calls


# =========================================================================== #
# GET /documents/{id}/graph
# =========================================================================== #


def test_graph_route_404_when_document_missing(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """文档不存在 → 404（先查 PG，**不**触碰 Neo4j）。"""
    response = client.get(f"/api/v1/documents/{uuid4()}/graph", headers=dev_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


def test_graph_route_403_cross_tenant(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
) -> None:
    """ADR-0003 / M5 §3 验收 1：他人文档 → 403（非 404），且**先于**图谱查询。"""
    document_id = _upload(client, dev_headers)

    response = client.get(
        f"/api/v1/documents/{document_id}/graph", headers=cross_tenant_headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_graph_route_501_when_neo4j_unreachable(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Neo4j 不可达（测试环境固定场景）→ 501，**不是** 200 空图，也不是 409。"""
    document_id = _upload(client, dev_headers)

    response = client.get(f"/api/v1/documents/{document_id}/graph", headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_graph_route_409_when_no_active_kg_version(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neo4j **可达**但没有 active 版本 → 409（契约明文要求）。

    必须与「Neo4j 不可达 → 501」区分：前者是版本状态问题，后者是基础设施故障。
    """

    def boom(self: GraphService, *, scope: str | None = None) -> KgVersion:
        raise NoActiveKgVersionError("Neo4j 中尚无 status='active' 的 KgVersion")

    monkeypatch.setattr(GraphService, "fetch_active_kg_version", boom)

    document_id = _upload(client, dev_headers)
    response = client.get(f"/api/v1/documents/{document_id}/graph", headers=dev_headers)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "KG_VERSION_NOT_ACTIVE"
    assert body["detail"]["status"] == "none"


def test_graph_route_success_matches_contract(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    document_id = _upload(client, dev_headers)
    calls = _patch_graph_ok(
        monkeypatch,
        nodes=[_graph_node("e1", "智能制造"), _graph_node("e7", "营业收入")],
        edges=[_graph_edge("r1", "e1", "e7")],
    )

    response = client.get(f"/api/v1/documents/{document_id}/graph", headers=dev_headers)

    assert response.status_code == 200, response.text
    body = response.json()

    # 字段「不多不少」——多出字段即契约漂移
    assert set(body) == DOCUMENT_GRAPH_KEYS
    assert body["doc_id"] == document_id
    assert body["kg_version"] == "v-test"
    assert body["version_status"] == "active"
    assert body["node_count"] == 2
    assert body["relation_count"] == 1
    assert body["truncated"] is False
    assert body["trace_id"] == response.headers["X-Trace-Id"]

    # 节点不得外泄 pii_flags（M2 §5.3）
    assert all("pii_flags" not in node for node in body["nodes"])

    # 路由必须把 active 版本、认证态 org_id、500 节点上限真切传下去
    assert calls["kg_version"] == "v-test"
    assert calls["node_limit"] == 500
    assert str(calls["org_id"]) == dev_headers["X-Org-Id"]
    assert str(calls["doc_id"]) == document_id


def test_graph_route_truncated_flag_passthrough(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M3 §3 验收 1：超过 500 节点上限时 `truncated = true` 必须透传。"""
    document_id = _upload(client, dev_headers)
    _patch_graph_ok(
        monkeypatch,
        nodes=[_graph_node("e1", "A")],
        edges=[],
        truncated=True,
    )

    response = client.get(f"/api/v1/documents/{document_id}/graph", headers=dev_headers)

    assert response.status_code == 200
    assert response.json()["truncated"] is True


def test_graph_route_501_when_neo4j_unavailable(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neo4j 在**子图查询**阶段挂掉 → 501（与「无 active 版本」同一分支）。"""
    document_id = _upload(client, dev_headers)

    def fake_active(self: GraphService, *, scope: str | None = None) -> KgVersion:
        return KgVersion(version="v-test", scope="global")

    def boom(self: GraphService, **kwargs: object) -> object:
        raise GraphUnavailableError("connection refused")

    monkeypatch.setattr(GraphService, "fetch_active_kg_version", fake_active)
    monkeypatch.setattr(GraphService, "fetch_document_subgraph", boom)

    response = client.get(f"/api/v1/documents/{document_id}/graph", headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


# =========================================================================== #
# POST /agent/query
# =========================================================================== #


def test_agent_route_success_matches_contract(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    async def fake_query(
        self: AgentService,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
    ) -> AgentQueryResponse:
        seen["question"] = request.question
        seen["org_id"] = org_id
        seen["trace_id"] = trace_id
        return AgentQueryResponse(
            answer="无法回答",
            citations=[],
            route="m3_graphqa",
            confidence="low",
            refused=True,
            refusal_reason="no_grounded_evidence",
            kg_version="v-test",
            trace_id=trace_id,
            # 批次 A 新契约字段：本用例聚焦拒答语义，显式传骨架默认值
            kg_nodes=[],
            kg_relations=[],
            token_usage=None,
        )

    monkeypatch.setattr(AgentService, "query", fake_query)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "智能制造有哪些财务指标？", "scope": "cross_doc"},
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == AGENT_QUERY_KEYS
    assert body["refused"] is True
    assert body["refusal_reason"] == "no_grounded_evidence"
    assert body["kg_version"] == "v-test"
    assert body["trace_id"] == response.headers["X-Trace-Id"]

    # org_id 只来自认证态（ADR-0003 §3.3），trace_id 透传
    assert str(seen["org_id"]) == dev_headers["X-Org-Id"]
    assert seen["trace_id"] == response.headers["X-Trace-Id"]
    assert seen["question"] == "智能制造有哪些财务指标？"


def test_agent_response_has_documented_graph_fields(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """正向守卫：Sprint 4 批次 A 契约扩展后，`kg_nodes` / `kg_relations` / `token_usage` 必须出现。

    Sprint 3 阶段九时这三字段契约未定义，旧守卫断言它们「不得出现」防静默漂移；
    Sprint 4 阶段 10.0 批次 A 已正式扩入契约（缺口 1 偿还），守卫语义随之**反转**：
    - `kg_nodes` / `kg_relations` 必须为 list（本步骨架填充空 list，AgentService
      填充逻辑在批次 A 下一步接入）；
    - `token_usage` 允许为 `null`（拒答 / 骨架链路拿不到 usage）或对象。
    """

    async def fake_query(self: AgentService, **kwargs: object) -> AgentQueryResponse:
        return AgentQueryResponse(
            answer="ok",
            citations=[],
            route="m3_graphqa",
            confidence="high",
            refused=False,
            refusal_reason=None,
            kg_version="v-test",
            trace_id="t",
            kg_nodes=[],
            kg_relations=[],
            token_usage=None,
        )

    monkeypatch.setattr(AgentService, "query", fake_query)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q"},
        headers=dev_headers,
    )

    assert response.status_code == 200
    body = response.json()

    # 三字段必须出现（缺任一即契约漂移）
    documented = {"kg_nodes", "kg_relations", "token_usage"}
    assert documented <= set(body)

    # 类型守卫：kg_nodes / kg_relations 为 list；token_usage 为 null 或对象
    assert isinstance(body["kg_nodes"], list)
    assert isinstance(body["kg_relations"], list)
    assert body["token_usage"] is None or isinstance(body["token_usage"], dict)


def test_agent_route_passes_explicit_kg_version_after_active_check(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式指定 active 版本 → 校验通过后**原样**透传给 service（不降级为最新版本）。"""
    seen: dict[str, object] = {}

    def fake_status(self: GraphService, version: str) -> str | None:
        seen["checked"] = version
        return "active"

    async def fake_query(
        self: AgentService,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
    ) -> AgentQueryResponse:
        seen["requested"] = request.kg_version
        return AgentQueryResponse(
            answer="ok",
            citations=[],
            route="m3_graphqa",
            confidence="high",
            refused=False,
            refusal_reason=None,
            kg_version=request.kg_version or "v-test",
            trace_id=trace_id,
            # 批次 A 新契约字段：显式传骨架默认值，防止未来改必填时静默失效
            kg_nodes=[],
            kg_relations=[],
            token_usage=None,
        )

    monkeypatch.setattr(GraphService, "fetch_kg_version_status", fake_status)
    monkeypatch.setattr(AgentService, "query", fake_query)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q", "kg_version": "v-active"},
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    assert seen["checked"] == "v-active"
    assert seen["requested"] == "v-active"


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("writing", "写入中"),
        ("failed", "失败"),
        ("superseded", "已被取代"),
        (None, "版本不存在"),
    ],
)
def test_agent_route_409_when_kg_version_not_active(
    client: TestClient,
    dev_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    status: str | None,
    label: str,
) -> None:
    """ADR-0002 §3.2：非 active 版本一律 409，**严禁静默降级**。"""
    called: dict[str, bool] = {"query": False}

    monkeypatch.setattr(
        GraphService, "fetch_kg_version_status", lambda self, version: status
    )

    async def fake_query(self: AgentService, **kwargs: object) -> AgentQueryResponse:
        called["query"] = True  # pragma: no cover - 不应被触达
        raise AssertionError("非 active 版本不得进入 AgentService")

    monkeypatch.setattr(AgentService, "query", fake_query)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q", "kg_version": "v-bad"},
        headers=dev_headers,
    )

    assert response.status_code == 409, label
    body = response.json()
    assert body["code"] == "KG_VERSION_NOT_ACTIVE"
    assert body["detail"]["kg_version"] == "v-bad"
    assert body["detail"]["status"] == (status or "unknown")
    assert called["query"] is False


def test_agent_route_501_when_version_check_cannot_reach_neo4j(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neo4j 不可用 **不能** 谎报为 409——基础设施故障必须是 501。"""

    def boom(self: GraphService, version: str) -> str | None:
        raise GraphUnavailableError("connection refused")

    monkeypatch.setattr(GraphService, "fetch_kg_version_status", boom)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q", "kg_version": "v-any"},
        headers=dev_headers,
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_agent_route_501_when_pipeline_unavailable(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM / 图谱未就绪 → 501（`AgentUnavailableError`），**不是** `refused=true`。"""

    async def boom(self: AgentService, **kwargs: object) -> AgentQueryResponse:
        raise AgentUnavailableError("DEEPSEEK_API_KEY 未配置")

    monkeypatch.setattr(AgentService, "query", boom)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q"},
        headers=dev_headers,
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_agent_route_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/agent/query", json={"question": "q"})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_agent_route_single_doc_without_doc_id_is_400(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`scope=single_doc` 缺 `doc_id` → 400 VALIDATION_ERROR（非 422）。"""
    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q", "scope": "single_doc"},
        headers=dev_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# =========================================================================== #
# AgentService 内部填充逻辑（批次 A 第二步：kg_nodes / kg_relations / token_usage）
# 不经路由直调 service，全链路打桩，不依赖真实 Neo4j / DeepSeek。
# =========================================================================== #


def _patch_agent_pipeline_ok(
    monkeypatch: pytest.MonkeyPatch,
    *,
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    llm_answer: str,
    llm_usage: TokenUsage | None,
) -> None:
    """打桩 AgentService 内部依赖：active 版本 + 全量实体子图 + LLM 调用。

    ``cross_doc`` 模式下 ``query()`` 走 ``fetch_all_subgraph``；
    LLM 桩直接返回 ``(文本, usage)``，绕开真实网络调用与 API Key 依赖。
    """
    monkeypatch.setattr(
        GraphService,
        "fetch_active_kg_version",
        lambda self, scope=None: KgVersion(version="v-test", scope="global"),
    )
    monkeypatch.setattr(
        GraphService,
        "fetch_all_subgraph",
        lambda self, **kwargs: (nodes, edges, False),
    )
    # 测试环境未配置 DEEPSEEK_API_KEY，前置检查必须打桩放行
    monkeypatch.setattr(AgentService, "_ensure_chat", lambda self: None)

    async def fake_invoke(
        self: AgentService, **kwargs: object
    ) -> tuple[str, TokenUsage | None]:
        return llm_answer, llm_usage

    monkeypatch.setattr(AgentService, "_invoke_chat_with_retry", fake_invoke)


def test_agent_service_fills_kg_nodes_relations_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正常问答路径：kg_nodes / kg_relations 与图谱检索结果一致，token_usage 透传。"""
    nodes = [_graph_node("e1", "智能制造"), _graph_node("e7", "营业收入")]
    edges = [_graph_edge("r1", "e1", "e7")]
    usage = TokenUsage(prompt_tokens=2048, completion_tokens=256, total_tokens=2304)
    # evidence 命中 `_looks_like_citation`（chunk- 前缀）→ 正常回答分支
    llm_answer = json.dumps(
        {
            "answer": "智能制造的财务指标包括营业收入。",
            "evidence": ["chunk-12"],
            "confidence": "high",
        },
        ensure_ascii=False,
    )
    _patch_agent_pipeline_ok(
        monkeypatch, nodes=nodes, edges=edges, llm_answer=llm_answer, llm_usage=usage
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="智能制造有哪些财务指标？"),
            org_id=uuid4(),
            trace_id="t-batch-a-ok",
        )
    )

    assert response.refused is False
    # 契约字段与检索结果**逐项**一致（非仅计数）
    assert response.kg_nodes == nodes
    assert response.kg_relations == edges
    # token_usage 透传且三字段均为非负 int
    assert response.token_usage == usage
    for value in (
        response.token_usage.prompt_tokens,
        response.token_usage.completion_tokens,
        response.token_usage.total_tokens,
    ):
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value >= 0


def test_agent_service_refusal_keeps_empty_graph_and_null_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """拒答路径：kg_nodes / kg_relations 为空列表，token_usage 为 None。"""
    # 图谱非空但 LLM 无证据 → 拒答时契约字段仍须为空（无支撑证据）
    nodes = [_graph_node("e1", "智能制造")]
    llm_answer = json.dumps(
        {"answer": "无法回答", "evidence": [], "confidence": "low"},
        ensure_ascii=False,
    )
    _patch_agent_pipeline_ok(
        monkeypatch,
        nodes=nodes,
        edges=[],
        llm_answer=llm_answer,
        llm_usage=None,
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="无证据的问题"),
            org_id=uuid4(),
            trace_id="t-batch-a-refuse",
        )
    )

    assert response.refused is True
    assert response.refusal_reason == "no_grounded_evidence"
    assert response.kg_nodes == []
    assert response.kg_relations == []
    assert response.token_usage is None


def test_extract_token_usage_from_langchain_usage_metadata() -> None:
    """路径 1：LangChain 标准化 usage_metadata → TokenUsage 三字段非负 int。"""
    from app.services.agents import _extract_token_usage

    response = SimpleNamespace(
        content="ok",
        usage_metadata={
            "input_tokens": 2048,
            "output_tokens": 256,
            "total_tokens": 2304,
        },
    )
    usage = _extract_token_usage(response)

    assert usage is not None
    assert usage.prompt_tokens == 2048
    assert usage.completion_tokens == 256
    assert usage.total_tokens == 2304


def test_extract_token_usage_from_openai_compatible_metadata() -> None:
    """路径 2：response_metadata["token_usage"]（DeepSeek / OpenAI 兼容）→ TokenUsage。"""
    from app.services.agents import _extract_token_usage

    response = SimpleNamespace(
        content="ok",
        response_metadata={
            "model_name": "deepseek-chat",
            "token_usage": {
                "prompt_tokens": 1024,
                "completion_tokens": 128,
                "total_tokens": 1152,
            },
        },
    )
    usage = _extract_token_usage(response)

    assert usage is not None
    assert usage.prompt_tokens == 1024
    assert usage.completion_tokens == 128
    assert usage.total_tokens == 1152


@pytest.mark.parametrize(
    "response",
    [
        # 两种 usage 结构都不存在
        SimpleNamespace(content="ok"),
        # usage_metadata 存在但字段缺失
        SimpleNamespace(usage_metadata={"input_tokens": 10}),
        # 字段类型非法（bool 是 int 子类，必须被拒绝；字符串数字同理）
        SimpleNamespace(
            usage_metadata={
                "input_tokens": True,
                "output_tokens": 5,
                "total_tokens": 5,
            }
        ),
        SimpleNamespace(
            response_metadata={
                "token_usage": {
                    "prompt_tokens": "1024",
                    "completion_tokens": 128,
                    "total_tokens": 1152,
                }
            }
        ),
        # 纯文本响应（无任何属性）
        "plain string",
    ],
)
def test_extract_token_usage_returns_none_when_unavailable(response: object) -> None:
    """提取失败（缺失 / 类型非法）→ None，严禁造数据。"""
    from app.services.agents import _extract_token_usage

    assert _extract_token_usage(response) is None


# --------------------------------------------------------------------------- #
# 兜底：确保打桩覆盖的是真实存在的签名（防止 service 重命名后测试静默失效）
# --------------------------------------------------------------------------- #


def test_stubbed_methods_exist_on_services() -> None:
    """打桩目标必须真实存在，防止 service 重命名后测试静默失效。"""
    for name in (
        "fetch_active_kg_version",
        "fetch_document_subgraph",
        "fetch_kg_version_status",
        "fetch_all_subgraph",
    ):
        assert callable(getattr(GraphService, name, None)), name
    assert callable(getattr(AgentService, "query", None))


def test_contract_key_sets_match_schemas() -> None:
    """本文件硬编码的字段集必须与 Pydantic 模型一致，避免「测试跟着错误一起漂移」。"""
    assert set(AgentQueryResponse.model_fields) == AGENT_QUERY_KEYS
    assert set(DocumentGraphResponse.model_fields) == DOCUMENT_GRAPH_KEYS


def test_no_active_kg_version_error_is_a_graph_unavailable_error() -> None:
    """子类关系保证既有 `except GraphUnavailableError` 不会漏网。

    `AgentService` 只按基类捕获 → 无 active 版本时同样转 `AgentUnavailableError`（501）；
    因为 `/agent/query` 的契约只对「**显式传入**非 active 版本」定义 409。
    """
    assert issubclass(NoActiveKgVersionError, GraphUnavailableError)


# --------------------------------------------------------------------------- #
# 回归：tenacity 退避策略（本地 tenacity 9.1.4 的真实签名，非官方文档）
# --------------------------------------------------------------------------- #


def test_llm_wait_policy_constructible_and_grows() -> None:
    """回归守卫：``wait_exponential`` 不接受 ``multiplier_getter``。

    旧代码传了该参数，构造即 `TypeError`；但因内联在协程里，只有真实调用
    LLM 才会暴露——测试必须直接构造策略，把它钉死。
    """
    from types import SimpleNamespace

    from app.core.config import get_settings
    from app.services.agents import _build_llm_wait_policy

    policy = _build_llm_wait_policy()  # 构造成功本身就是断言
    settings = get_settings()

    first = policy(SimpleNamespace(attempt_number=1))
    second = policy(SimpleNamespace(attempt_number=2))

    assert float(first) == pytest.approx(settings.task_retry_initial_seconds)
    assert float(second) == pytest.approx(
        settings.task_retry_initial_seconds * settings.task_retry_multiplier
    )
    assert second > first, "退避必须随重试次数增长"


# =========================================================================== #
# 批次 D1 缺口 5：Neo4j 原始数据与契约不符 → GraphUnavailableError（→ 路由 501）
# 批次 D1 缺口 6：拒答统一出口 `_refuse()`
# =========================================================================== #


class _FakeNeo4jSession:
    """Neo4j session 的最小替身：``run(...).single()`` 返回预置 payload。

    用它绕开真实 Neo4j，专门构造「查询成功、但返回数据与契约不符」的场景——
    这正是缺口 5 要覆盖的路径：D1 之前会裸抛 ``ValidationError`` 穿透成
    500 ``INTERNAL_ERROR``，而不是语义正确的 501（基础设施 / 数据契约故障）。
    """

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeNeo4jSession:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def run(self, *args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(single=lambda: self._payload)


def _patch_raw_neo4j_payload(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    """把 GraphService 的 driver 换成返回固定 payload 的替身（不连真实 Neo4j）。"""
    driver = SimpleNamespace(
        session=lambda database=None: _FakeNeo4jSession(payload),
        close=lambda: None,
    )
    monkeypatch.setattr(GraphService, "_ensure_driver", lambda self: driver)


@pytest.mark.parametrize(
    ("payload", "bad_field"),
    [
        pytest.param(
            {
                "nodes": [
                    # ``canonical_name`` 契约是 ``str | None``，这里是对象
                    {"id": "e1", "type": "公司", "canonical_name": {"zh": "智能制造"}}
                ],
                "total_nodes": 1,
                "edges": [],
            },
            "canonical_name",
            id="node-canonical_name-not-str",
        ),
        pytest.param(
            {
                # ``confidence`` 契约上界为 1.0，1.5 越界
                "nodes": [{"id": "e1", "type": "公司", "confidence": 1.5}],
                "total_nodes": 1,
                "edges": [],
            },
            "confidence",
            id="node-confidence-out-of-range",
        ),
        pytest.param(
            {
                "nodes": [],
                "total_nodes": 0,
                "edges": [
                    {
                        "id": "r1",
                        "type": "MENTIONS",
                        "source": "e1",
                        "target": "e2",
                        # ``properties`` 契约是 dict，这里是非空 list
                        "properties": ["not-a-dict"],
                    }
                ],
            },
            "properties",
            id="edge-properties-not-dict",
        ),
    ],
)
def test_fetch_all_subgraph_raises_on_contract_mismatch(
    monkeypatch: pytest.MonkeyPatch, payload: object, bad_field: str
) -> None:
    """缺口 5：投影失败 → 抛 :class:`GraphUnavailableError`，**不是**空结果。

    若此处静默返回 ``([], [], False)``，上层会把「数据坏了」当成
    「图谱里没有证据」，进而返回 ``refused = true``（200）——数据质量故障被
    伪装成正常业务结论，这正是本缺口要堵住的口子。
    """
    _patch_raw_neo4j_payload(monkeypatch, payload)

    with pytest.raises(GraphUnavailableError) as excinfo:
        GraphService.instance().fetch_all_subgraph(kg_version="v-test", node_limit=10)

    message = str(excinfo.value)
    assert bad_field in message, f"异常消息必须指名出问题的字段，实际: {message}"
    assert "fetch_all_subgraph" in message
    assert "kg_version=v-test" in message


@pytest.mark.parametrize(
    ("payload", "bad_field"),
    [
        pytest.param(
            {
                "d": {"id": "d1", "canonical_name": ["不应是数组"]},
                "chunks": [],
                "entities": [],
                "mentions": [],
            },
            "canonical_name",
            id="document-node-canonical_name-not-str",
        ),
        pytest.param(
            {
                "d": None,
                "chunks": [{"id": "c1"}],
                # entity_type 契约是 ``str | None``，这里是 int
                "entities": [{"id": "e1", "type": 123}],
                "mentions": [],
            },
            "entity_type",
            id="entity-type-not-str",
        ),
        pytest.param(
            {
                "d": None,
                "chunks": [],
                "entities": [],
                "mentions": [
                    {
                        "id": "r1",
                        "type": "MENTIONS",
                        "source": "c1",
                        "target": "e1",
                        "properties": "oops",
                    }
                ],
            },
            "properties",
            id="edge-properties-not-dict",
        ),
    ],
)
def test_fetch_document_subgraph_raises_on_contract_mismatch(
    monkeypatch: pytest.MonkeyPatch, payload: object, bad_field: str
) -> None:
    """缺口 5（第二处）：文档子图投影失败同样抛 GraphUnavailableError。"""
    _patch_raw_neo4j_payload(monkeypatch, payload)
    doc_id = uuid4()

    with pytest.raises(GraphUnavailableError) as excinfo:
        GraphService.instance().fetch_document_subgraph(
            doc_id=doc_id, kg_version="v-test", node_limit=10
        )

    message = str(excinfo.value)
    assert bad_field in message, f"异常消息必须指名出问题的字段，实际: {message}"
    assert "fetch_document_subgraph" in message
    assert str(doc_id) in message
    assert "kg_version=v-test" in message


def test_fetch_document_subgraph_ok_payload_still_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反向守卫：兜底不得误伤正常数据（合法 payload 仍正常投影）。"""
    _patch_raw_neo4j_payload(
        monkeypatch,
        {
            "d": {"id": "d1", "canonical_name": "合同.pdf"},
            "chunks": [{"id": "c1"}],
            "entities": [{"id": "e1", "type": "公司", "canonical_name": "智能制造"}],
            "mentions": [
                {
                    "id": "r1",
                    "type": "MENTIONS",
                    "source": "c1",
                    "target": "e1",
                    "properties": {"kg_version": "v-test", "weight": 0.9},
                }
            ],
        },
    )

    nodes, edges, truncated = GraphService.instance().fetch_document_subgraph(
        doc_id=uuid4(), kg_version="v-test", node_limit=10
    )

    assert [node.label for node in nodes] == ["Document", "Chunk", "Entity"]
    assert edges[0].type == "MENTIONS"
    assert truncated is False
    # `_sanitize_properties` 仍须剥离系统属性
    assert edges[0].properties == {"weight": 0.9}


def test_agent_service_refusal_goes_through_refuse_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺口 6：拒答分支必须调用 `_refuse()`（不再是 inline 构造），且传参正确。"""
    calls: list[dict[str, object]] = []
    original_refuse = AgentService._refuse

    def spy(self: AgentService, **kwargs: object) -> AgentQueryResponse:
        calls.append(dict(kwargs))
        return original_refuse(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(AgentService, "_refuse", spy)
    _patch_agent_pipeline_ok(
        monkeypatch,
        nodes=[_graph_node("e1", "智能制造")],
        edges=[],
        llm_answer=json.dumps(
            {"answer": "无法回答", "evidence": [], "confidence": "low"},
            ensure_ascii=False,
        ),
        llm_usage=None,
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="无证据的问题"),
            org_id=uuid4(),
            trace_id="t-d1-refuse-hook",
        )
    )

    assert response.refused is True
    assert len(calls) == 1, "拒答必须恰好经由 _refuse() 一次"
    assert calls[0]["trace_id"] == "t-d1-refuse-hook"
    assert calls[0]["kg_version"] == "v-test"
    assert calls[0]["reason"] == "no_grounded_evidence"
    assert calls[0]["note"], "note 必须非空，便于日志检索拒答缘由"


def test_agent_service_refusal_response_matches_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """拒答响应体必须完全符合契约：字段不多不少 + 三个扩展字段显式置空。"""
    _patch_agent_pipeline_ok(
        monkeypatch,
        nodes=[_graph_node("e1", "智能制造")],
        edges=[_graph_edge("r1", "e1", "e2")],
        llm_answer=json.dumps(
            {"answer": "无法回答", "evidence": [], "confidence": "low"},
            ensure_ascii=False,
        ),
        # 刻意给一个**非空** usage：拒答语义下仍必须落 None（不回填）
        llm_usage=TokenUsage(
            prompt_tokens=1024, completion_tokens=128, total_tokens=1152
        ),
    )

    response = asyncio.run(
        AgentService.instance().query(
            request=AgentQueryRequest(question="无证据的问题"),
            org_id=uuid4(),
            trace_id="t-d1-refuse-contract",
        )
    )
    body = json.loads(response.model_dump_json())

    # 字段「不多不少」——多出 / 缺少字段即契约漂移
    assert set(body) == AGENT_QUERY_KEYS
    assert body["refused"] is True
    assert body["refusal_reason"] == "no_grounded_evidence"
    assert body["answer"] == "无法回答"
    assert body["citations"] == []
    assert body["route"] == "m3_graphqa"
    assert body["confidence"] == "low"
    assert body["kg_version"] == "v-test"
    # 拒答不携带支撑证据，也不回填 token 用量（严禁拼凑数据）
    assert body["kg_nodes"] == []
    assert body["kg_relations"] == []
    assert body["token_usage"] is None
