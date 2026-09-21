"""Agent fail-closed 跨租户校验测试（ADR-0003 §4，Sprint 5 批次 B）。

覆盖 ``/agent/query`` 链路上的三段防线：

1. 服务层：``validate_kg_version_tenant_boundary`` 返回 False +
   ``agent_fail_closed=True``（默认）→ :class:`AgentTenantLeakError`；
2. 服务层：``agent_fail_closed=False`` → 仅告警放行（LLM 未配置时以
   ``AgentUnavailableError`` 收尾，但**不是** AgentTenantLeakError）；
3. 服务层：校验查询本身抛 :class:`GraphUnavailableError` → 501 语义；
4. 路由层：``AgentTenantLeakError`` → **403 KG_TENANT_LEAK**（必须先于
   父类 ``AgentUnavailableError``（501）分支捕获——子类陷阱守卫）。

隔离：GraphService / 子图检索全部打桩，LLM 不装配（测试环境无 API_KEY）。
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.schemas.agent import AgentQueryRequest, AgentQueryResponse
from app.services.agents import (
    AgentService,
    AgentTenantLeakError,
    AgentUnavailableError,
)
from app.services.graphs import GraphService, GraphUnavailableError, KgVersion


def _patch_graph(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tenant_clean: bool = True,
    boundary_raises: Exception | None = None,
) -> dict[str, object]:
    """打桩 GraphService：active 版本 + 子图 + 租户边界校验。"""
    calls: dict[str, object] = {}

    def fake_active(self: GraphService, *, scope: str | None = None) -> KgVersion:
        return KgVersion(version="v-test", scope="global")

    def fake_subgraph(
        self: AgentService,
        *,
        kg_version: str,
        doc_id: UUID | None,
        org_id: UUID,
        scope: str,
    ) -> object:
        calls["subgraph_org_id"] = org_id
        return _StubSubgraph()

    def fake_validate(
        self: GraphService, *, kg_version: str, current_org_id: UUID
    ) -> bool:
        calls["validate_org_id"] = current_org_id
        if boundary_raises is not None:
            raise boundary_raises
        return tenant_clean

    monkeypatch.setattr(GraphService, "fetch_active_kg_version", fake_active)
    monkeypatch.setattr(AgentService, "_fetch_subgraph_for_question", fake_subgraph)
    monkeypatch.setattr(
        GraphService, "validate_kg_version_tenant_boundary", fake_validate
    )

    # 确定性收尾：无论本地 .env 是否配置 LLM_API_KEY，都止步于装配检查
    def fail_chat(self: AgentService) -> object:
        raise AgentUnavailableError("LLM 未配置（测试打桩）")

    monkeypatch.setattr(AgentService, "_ensure_chat", fail_chat)
    return calls


class _StubSubgraph:
    serialized = "<graph: stub/>"


def _query() -> object:
    return AgentService.instance().query(
        request=AgentQueryRequest(question="A 公司与 B 公司是什么关系？"),
        org_id=get_settings().default_org_id,
        trace_id="trace-fail-closed",
    )


@pytest.fixture(autouse=True)
def _fresh_agent_service() -> None:
    AgentService.reset()
    yield
    AgentService.reset()


# --------------------------------------------------------------------------- #
# 服务层：fail-closed 默认开
# --------------------------------------------------------------------------- #


def test_tenant_leak_raises_when_fail_closed_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """泄漏 + agent_fail_closed=True → AgentTenantLeakError（LLM 不得被触达）。"""
    _patch_graph(monkeypatch, tenant_clean=False)

    with pytest.raises(AgentTenantLeakError, match="跨租户子图泄漏"):
        asyncio.run(_query())


def test_tenant_leak_warn_only_when_fail_closed_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """泄漏 + agent_fail_closed=False → 放行；后续因 LLM 未配置抛普通 501 异常。"""
    monkeypatch.setattr(get_settings(), "agent_fail_closed", False)
    _patch_graph(monkeypatch, tenant_clean=False)

    with pytest.raises(AgentUnavailableError) as exc_info:
        asyncio.run(_query())

    # 子类陷阱守卫：放行路径的失败必须是普通 501，不得误伤为 KG_TENANT_LEAK
    assert not isinstance(exc_info.value, AgentTenantLeakError)


def test_tenant_clean_proceeds_past_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无泄漏 → 校验通过（后续因 LLM 未配置抛 AgentUnavailableError，属正常）。"""
    calls = _patch_graph(monkeypatch, tenant_clean=True)

    with pytest.raises(AgentUnavailableError) as exc_info:
        asyncio.run(_query())

    assert not isinstance(exc_info.value, AgentTenantLeakError)
    # 校验用的 org_id 来自认证态（identity.org_id），非请求体
    assert calls["validate_org_id"] == get_settings().default_org_id


def test_boundary_check_infra_failure_is_501_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验查询本身挂掉 → AgentUnavailableError（基础设施故障 ≠ 数据事故）。"""
    _patch_graph(monkeypatch, boundary_raises=GraphUnavailableError("neo4j down"))

    with pytest.raises(AgentUnavailableError, match="fail-closed 校验失败"):
        asyncio.run(_query())


# --------------------------------------------------------------------------- #
# 路由层：403 转换
# --------------------------------------------------------------------------- #


def test_route_returns_403_on_tenant_leak(
    client: TestClient,
    dev_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentTenantLeakError → 403 + code=KG_TENANT_LEAK（不落入 501 分支）。"""

    async def leak(
        self: AgentService,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
    ) -> AgentQueryResponse:
        raise AgentTenantLeakError("跨租户子图泄漏检测到（kg_version=v-test）")

    monkeypatch.setattr(AgentService, "query", leak)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q"},
        headers=dev_headers,
    )

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "KG_TENANT_LEAK"
    assert "fail-closed" in body["detail"]["blocked_by"]
    assert body["trace_id"] == response.headers["X-Trace-Id"]


def test_route_returns_501_on_plain_unavailable(
    client: TestClient,
    dev_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通 AgentUnavailableError 仍是 501（子类陷阱的反向守卫）。"""

    async def unavailable(
        self: AgentService,
        *,
        request: AgentQueryRequest,
        org_id: UUID,
        trace_id: str,
    ) -> AgentQueryResponse:
        raise AgentUnavailableError("LLM_API_KEY 未配置")

    monkeypatch.setattr(AgentService, "query", unavailable)

    response = client.post(
        "/api/v1/agent/query",
        json={"question": "q"},
        headers=dev_headers,
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"
