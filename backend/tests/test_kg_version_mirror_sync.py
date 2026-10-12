"""P6-X2：图库 ``:KgVersion`` 镜像同步的护栏（**F-P6X-1** / **F-P6X-5**）。

覆盖四件事：

1. ``sync_kg_version_mirror`` 真的去调镜像激活，且带上了 ``org_id``；
2. 它是**旁路**：图库挂了**不抛**、返回 ``False``（不让已写完图的构建判 failed，
   该报的错由 §6.2 的 ``ghost_version`` 照出来）；
3. **F-P6X-5**：``superseded`` 只在**同 org** 内生效 —— 真图上激活 A 租户的版本，
   B 租户的节点**不得**被取代（这是本批最贵、也最该钉的一条）；
4. ``org_id`` 为 ``NULL`` 的历史节点**不得被污染**（既不 supersede、也不写 org）。

**为什么第 1 / 2 条用打桩、第 3 / 4 条打真图**：前两条是编排语义（谁调谁、失败怎么处置），
打桩即可钉死；后两条是**跨租户副作用**，只有真图能证 —— 静态断言 Cypher 文本只能拦
"有人把过滤条件删了"，证不出"过滤真的生效"。真图用例在默认口径下 skip。

**两条静态护栏**：断言 Cypher 文本里带 org 过滤。它们是**回归护栏**（防止有人改回
不分租户的 supersede / 不按 org 的兜底），不是"实现细节测试"。
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

from app.services.graphs import (
    _CYPHER_SUPERSEDE_OTHER_VERSIONS,
    _QUERY_ACTIVE_KG_VERSION,
    GraphService,
    GraphUnavailableError,
)
from app.services.kg.mirror import sync_kg_version_mirror

_ORG_A = uuid4()
_ORG_B = uuid4()


def _real_graph_env() -> tuple[str, str, str]:
    """真图口径的三件套（缺一个就 skip —— 默认口径下这些用例不跑）。"""
    uri = os.environ.get("GRAPH_REAL_NEO4J_URI")
    user = os.environ.get("GRAPH_REAL_NEO4J_USER")
    password = os.environ.get("GRAPH_REAL_NEO4J_PASSWORD")
    if not (uri and user and password):
        pytest.skip("未设 GRAPH_REAL_NEO4J_*（真图口径才跑）")
    return uri, user, password


@pytest.fixture
def graph_service(monkeypatch: pytest.MonkeyPatch) -> GraphService:
    """把 ``GraphService`` 指向**真** Neo4j（其余用例仍走不可达端口）。"""
    from app.core.config import get_settings

    uri, user, password = _real_graph_env()
    settings = get_settings()
    monkeypatch.setattr(settings, "neo4j_uri", uri)
    monkeypatch.setattr(settings, "neo4j_user", user)
    monkeypatch.setattr(settings, "neo4j_password", password)
    GraphService.reset()
    try:
        yield GraphService.instance()
    finally:
        GraphService.reset()


# --------------------------------------------------------------------------- #
# 1 / 2：编排语义（打桩）
# --------------------------------------------------------------------------- #


def test_sync_calls_activate_with_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """镜像同步**真的**调激活，且 org_id / trace_id 都传下去（F-P6X-1）。"""
    calls: list[dict[str, object]] = []

    def _fake(
        self: GraphService, *, version: str, org_id: UUID, trace_id: str
    ) -> list[str]:
        calls.append({"version": version, "org_id": org_id, "trace_id": trace_id})
        return []

    monkeypatch.setattr(GraphService, "activate_kg_version", _fake)

    ok = sync_kg_version_mirror(version="v-1", org_id=_ORG_A, trace_id="t-1")

    assert ok is True
    assert calls == [{"version": "v-1", "org_id": _ORG_A, "trace_id": "t-1"}]


def test_sync_is_bypass_when_graph_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图库不可用 ⇒ **不抛**、返回 ``False``（图已写完，判 failed 是造假）。

    可观测性由 §6.2 的一致性判据兜底：它会把「PG 有、图库没有」判 ``ghost_version`` FAIL。
    """

    def _boom(
        self: GraphService, *, version: str, org_id: UUID, trace_id: str
    ) -> list[str]:
        raise GraphUnavailableError("connection refused")

    monkeypatch.setattr(GraphService, "activate_kg_version", _boom)

    ok = sync_kg_version_mirror(version="v-1", org_id=_ORG_A, trace_id="t-1")

    assert ok is False  # 不抛，只是没同步成


# --------------------------------------------------------------------------- #
# 静态护栏（防改回不分租户）
# --------------------------------------------------------------------------- #


def test_supersede_cypher_is_scoped_to_org() -> None:
    """``superseded`` 的 Cypher **必须**带 org 过滤（F-P6X-5 的回归护栏）。"""
    assert "v.org_id = $org_id" in _CYPHER_SUPERSEDE_OTHER_VERSIONS
    # 旧实现是 ``WHERE v.version <> $version`` 后直接 SET ⇒ 一旦只剩这一句就是越权
    assert "v.version <> $version" in _CYPHER_SUPERSEDE_OTHER_VERSIONS


def test_active_fallback_requires_org() -> None:
    """兜底查询**必须**按 org 取（否则会命中别租户 / 字典序最大的历史版本）。"""
    assert "v.org_id = $org_id" in _QUERY_ACTIVE_KG_VERSION


# --------------------------------------------------------------------------- #
# 3 / 4：真图跨租户（默认口径 skip）
# --------------------------------------------------------------------------- #


def _seed(real_driver, rows: list[dict[str, object]]) -> None:  # noqa: ANN001
    with real_driver.session() as session:
        for row in rows:
            session.run(
                "CREATE (v:KgVersion {version: $version}) "
                "SET v.status = 'active', v.scope = 'global', v.org_id = $org_id",
                version=row["version"],
                org_id=row["org_id"],
            )


def _wipe(real_driver, versions: list[str]) -> None:  # noqa: ANN001
    with real_driver.session() as session:
        session.run(
            "MATCH (v:KgVersion) WHERE v.version IN $versions DETACH DELETE v",
            versions=versions,
        )


def _org_of(real_driver, version: str) -> object:  # noqa: ANN001
    with real_driver.session() as session:
        record = session.run(
            "MATCH (v:KgVersion {version: $version}) RETURN v.org_id AS org_id",
            version=version,
        ).single()
    return None if record is None else record["org_id"]


@pytest.fixture
def real_driver():  # noqa: ANN201
    """真 Neo4j driver（与 ``test_kg_incremental_rebuild.py`` 同款）。"""
    from neo4j import GraphDatabase

    uri, user, password = _real_graph_env()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 - 连通性即判据
        driver.close()
        if os.environ.get("CI"):
            pytest.fail(f"CI 上连不上 Neo4j（{uri}）：{exc}")
        pytest.skip(f"连不上 Neo4j（{uri}）：{exc}")
    try:
        yield driver
    finally:
        driver.close()


def test_activating_org_a_does_not_supersede_org_b(
    graph_service: GraphService, real_driver
) -> None:
    """**本批最该钉的一条**：激活 A 的版本 ⇒ B 的节点**保持 active**（F-P6X-5）。"""
    ver_a_new = f"p6x2-a-new-{uuid4().hex[:8]}"
    ver_a_old = f"p6x2-a-old-{uuid4().hex[:8]}"
    ver_b = f"p6x2-b-{uuid4().hex[:8]}"
    versions = [ver_a_new, ver_a_old, ver_b]
    _seed(
        real_driver,
        [
            {"version": ver_a_new, "org_id": str(_ORG_A)},
            {"version": ver_a_old, "org_id": str(_ORG_A)},
            {"version": ver_b, "org_id": str(_ORG_B)},
        ],
    )
    try:
        graph_service.activate_kg_version(
            version=ver_a_new, org_id=_ORG_A, trace_id="t-p6x2"
        )
        assert graph_service.fetch_kg_version_status(ver_a_new) == "active"
        # 同 org 的旧版本被取代
        assert graph_service.fetch_kg_version_status(ver_a_old) == "superseded"
        # **别租户的一条都不许动**
        assert graph_service.fetch_kg_version_status(ver_b) == "active"
    finally:
        _wipe(real_driver, versions)


def test_null_org_node_is_never_claimed(
    graph_service: GraphService, real_driver
) -> None:
    """``org_id`` 为 NULL 的历史节点：既不 supersede，也**不许**被写成当前 org。"""
    ver_new = f"p6x2-new-{uuid4().hex[:8]}"
    ver_legacy = f"p6x2-legacy-{uuid4().hex[:8]}"
    versions = [ver_new, ver_legacy]
    _seed(
        real_driver,
        [
            {"version": ver_new, "org_id": str(_ORG_A)},
            {"version": ver_legacy, "org_id": None},
        ],
    )
    try:
        graph_service.activate_kg_version(
            version=ver_new, org_id=_ORG_A, trace_id="t-p6x2"
        )
        assert graph_service.fetch_kg_version_status(ver_legacy) == "active"
        # 关键：没有被"顺手"认领成本 org
        assert _org_of(real_driver, ver_legacy) is None
    finally:
        _wipe(real_driver, versions)
