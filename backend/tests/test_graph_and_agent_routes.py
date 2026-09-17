"""阶段九 9.3：`GET /documents/{id}/graph` 与 `POST /agent/query` 端点测试。

**全部外部依赖打桩**：`conftest.py` 已把 `NEO4J_URI` 指向不可达端口，保证
GraphService 确定性抛 :class:`GraphUnavailableError`；需要「图谱可用」的用例
一律用 ``monkeypatch`` 显式打桩，**不依赖真实 Neo4j / DeepSeek**。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent import AgentQueryRequest, AgentQueryResponse
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


def test_agent_response_has_no_undocumented_fields(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归守卫：契约未定义的 `kg_nodes` / `kg_relations` / `token_usage` 不得出现。

    这三项是阶段九需求口头提到、但 `contracts/openapi.yaml` **未定义**的字段。
    按 CODEBUDDY.md「功能预留原则」，本轮**不**扩契约、**不**擅自补充；
    等 Sprint 4 统一刷新契约后再落。本用例防止有人手滑加上去造成静默漂移。
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
        )

    monkeypatch.setattr(AgentService, "query", fake_query)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q"},
        headers=dev_headers,
    )

    assert response.status_code == 200
    undocumented = {"kg_nodes", "kg_relations", "token_usage"}
    assert not (undocumented & set(response.json()))


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
