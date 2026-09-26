"""`GET /graph/overview` + `GET /entities/{id}` 路由测试（Sprint 5 批次 C）。

外部依赖打桩约定：
- `NEO4J_URI` 已指向不可达端口（`conftest.py`），GraphService 确定性抛
  :class:`GraphUnavailableError`；
- 需要「图谱可用」的用例一律 monkeypatch 显式打桩。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.schemas.graph import (
    EntityAttribute,
    EntityDetail,
    EntityRelation,
    GraphOverviewEdge,
    GraphOverviewNode,
    GraphOverviewResponse,
)
from app.services.graphs import (
    EntityNotFoundError,
    GraphService,
    KgVersion,
    NoActiveKgVersionError,
)

#: `contracts/openapi.yaml::GraphOverviewResponse` 字段集
GRAPH_OVERVIEW_KEYS = {
    "doc_count",
    "entity_count",
    "relation_count",
    "kg_version",
    "nodes",
    "edges",
    "truncated",
    "trace_id",
}
#: `contracts/openapi.yaml::EntityDetail` 字段集
ENTITY_DETAIL_KEYS = {
    "id",
    "canonical_name",
    "entity_type",
    "category",
    "confidence",
    "kg_version",
    "relation_count",
    "attributes",
    "relations",
    "trace_id",
}


def _patch_active_version(
    monkeypatch: pytest.MonkeyPatch, *, version: str = "v-test"
) -> None:
    """把 ``fetch_active_kg_version`` 打桩成「返回一个现成版本」。"""
    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_active_kg_version",
        lambda **kwargs: KgVersion(version=version, status="active"),
    )


def _patch_overview_ok(
    monkeypatch: pytest.MonkeyPatch,
    *,
    nodes: list[GraphOverviewNode] | None = None,
    edges: list[GraphOverviewEdge] | None = None,
    truncated: bool = False,
    doc_count: int = 3,
    entity_count: int = 12,
    relation_count: int = 18,
    kg_version: str = "v-test",
) -> None:
    """把 ``fetch_graph_overview`` 打桩成「直接返回指定响应」。"""
    if nodes is None:
        nodes = [
            GraphOverviewNode(
                id="e1",
                name="实体1",
                type="公司",
                category="org",
                weight=0.9,
                seed_x=0.3,
                seed_y=0.4,
            )
        ]
    if edges is None:
        edges = []

    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_graph_overview",
        lambda **_kwargs: GraphOverviewResponse(
            doc_count=doc_count,
            entity_count=entity_count,
            relation_count=relation_count,
            kg_version=kg_version,
            nodes=nodes,
            edges=edges,
            truncated=truncated,
            trace_id="t-fixed",
        ),
    )


def _patch_entity_ok(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entity_id: str = "entity-x",
    relations: list[EntityRelation] | None = None,
    attributes: list[EntityAttribute] | None = None,
    relation_count: int = 0,
) -> None:
    """把 ``fetch_entity_detail`` 打桩成「直接返回指定响应」。"""
    if relations is None:
        relations = [
            EntityRelation(
                relation="AFFILIATED_WITH", target_id="e2", target_name="实体2"
            )
        ]
        relation_count = 1
    if attributes is None:
        attributes = [
            EntityAttribute(label="alias", value="别称A"),
            EntityAttribute(label="source_url", value="https://example.com/x"),
        ]

    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_entity_detail",
        lambda **_kwargs: EntityDetail(
            id=entity_id,
            canonical_name="示例实体",
            entity_type="公司",
            category="org",
            confidence=0.95,
            kg_version="v-test",
            relation_count=relation_count,
            attributes=attributes,
            relations=relations,
            trace_id="t-fixed",
        ),
    )


# --------------------------------------------------------------------------- #
# `GET /graph/overview`
# --------------------------------------------------------------------------- #


def test_overview_returns_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Neo4j 不可达 → 501 `NOT_IMPLEMENTED`（**不**走 200 + 空图谱，参考 4.10.0.D1）。"""
    response = client.get("/api/v1/graph/overview", headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_overview_returns_409_when_no_active_version(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neo4j 可达但无 active → 409 `KG_VERSION_NOT_ACTIVE`。"""
    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_active_kg_version",
        lambda **kwargs: (_ for _ in ()).throw(
            NoActiveKgVersionError("no active version")
        ),
    )

    response = client.get("/api/v1/graph/overview", headers=dev_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "KG_VERSION_NOT_ACTIVE"


def test_overview_200_when_service_ok(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常路径：返回契约字段集 + 节点 + 边 + kg_version。"""
    _patch_overview_ok(monkeypatch)

    response = client.get("/api/v1/graph/overview", headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == GRAPH_OVERVIEW_KEYS
    assert body["kg_version"] == "v-test"
    assert body["entity_count"] == 12
    assert body["relation_count"] == 18
    assert body["doc_count"] == 3
    assert body["truncated"] is False
    assert body["trace_id"] == "t-fixed"
    assert isinstance(body["nodes"], list)
    assert isinstance(body["edges"], list)


def test_overview_requires_auth(client: TestClient) -> None:
    """未认证 → 401 `UNAUTHORIZED`。"""
    response = client.get("/api/v1/graph/overview")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_overview_tenant_protection_declares_403(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """契约响应集合必须声明 403 跨租户（ADR-0003）。"""
    # 重新生成 schema 以验证 responses 字段
    from app.main import app

    schema = app.openapi()
    responses = schema["paths"]["/api/v1/graph/overview"]["get"]["responses"]
    assert "403" in responses
    assert "401" in responses


# --------------------------------------------------------------------------- #
# 统计值真源（2026-09-26 修复：此前 `_fetch_graph_overview_stats` 硬编码返回 0）
#
# 为什么必须在这里补：原有用例把整个 `fetch_graph_overview` 打桩了，
# 硬编码 0 因此**测不出来**（392 passed 也照样红不了）——真机才暴露。
# --------------------------------------------------------------------------- #


@pytest.fixture
def _stats_fixture() -> object:
    """造一个 ready 版本 + 3 篇文档（2 篇属该版本 / 1 篇属历史版本）。"""
    from sqlalchemy import delete

    from app.db.models import Document, KgVersion
    from app.db.session import SessionLocal, init_db

    init_db()

    org_id = uuid4()
    version = f"v-stats-{uuid4().hex[:8]}"
    old_version_id = uuid4()

    with SessionLocal() as session:
        row = KgVersion(
            org_id=org_id,
            version=version,
            status="ready",
            source_doc_ids=[str(uuid4())],
            entity_count=42,
            relation_count=7,
            trace_id=uuid4(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        def _doc(kg_version_id: object) -> Document:
            return Document(
                filename_hash=f"h-{uuid4().hex[:16]}",
                mime_type="application/pdf",
                size_bytes=1024,
                status="completed",
                uploaded_by=uuid4(),
                org_id=org_id,
                trace_id=uuid4(),
                kg_version_id=kg_version_id,  # type: ignore[arg-type]
            )

        session.add_all([_doc(row.id), _doc(row.id), _doc(old_version_id), _doc(None)])
        session.commit()
        version_id = row.id

    yield org_id, version, version_id

    with SessionLocal() as session:
        session.execute(delete(Document).where(Document.org_id == org_id))
        session.execute(delete(KgVersion).where(KgVersion.id == version_id))
        session.commit()


def test_overview_stats_read_from_pg_source(
    _stats_fixture: object, real_pg_get_active: None
) -> None:
    """统计值来自 PG 真源：entity/relation 取 `kg_versions`，doc 只数 active 版本。"""
    org_id, version, _version_id = _stats_fixture  # type: ignore[misc]

    stats = GraphService.instance()._fetch_graph_overview_stats(
        version=version,
        org_id=org_id,
        db=SessionLocal(),
    )

    assert stats == {
        "doc_count": 2,  # 3 篇中有 1 篇属历史版本、1 篇未建图 ⇒ 不计入 active 视图
        "entity_count": 42,
        "relation_count": 7,
    }


def test_overview_stats_rejects_missing_db(_stats_fixture: object) -> None:
    """`db` 缺失 → 显式报错，**不**返回 0 冒充统计值（原硬编码 0 正是静默假数据）。"""
    org_id, version, _version_id = _stats_fixture  # type: ignore[misc]

    with pytest.raises(ValueError, match="禁止返回 0 冒充"):
        GraphService.instance()._fetch_graph_overview_stats(
            version=version, org_id=org_id
        )


def test_overview_stats_rejects_unknown_version(
    _stats_fixture: object, real_pg_get_active: None
) -> None:
    """PG 中无该版本 → `NoActiveKgVersionError`（路由层转 409），不静默 0。"""
    org_id, _version, _version_id = _stats_fixture  # type: ignore[misc]

    with pytest.raises(NoActiveKgVersionError):
        GraphService.instance()._fetch_graph_overview_stats(
            version="v-not-exist", org_id=org_id, db=SessionLocal()
        )


# --------------------------------------------------------------------------- #
# `GET /entities/{entity_id}`
# --------------------------------------------------------------------------- #


def test_entity_detail_404_when_not_found(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """实体不存在 → 404 `ENTITY_NOT_FOUND`（与跨租户 403 语义分离）。"""
    _patch_active_version(monkeypatch)
    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_entity_detail",
        lambda **_kwargs: (_ for _ in ()).throw(
            EntityNotFoundError("entity not found")
        ),
    )

    response = client.get("/api/v1/entities/missing", headers=dev_headers)

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "ENTITY_NOT_FOUND"
    assert body["detail"]["entity_id"] == "missing"


def test_entity_detail_200_when_found(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """正常路径：返回契约字段集 + attributes + relations + relation_count。"""
    _patch_entity_ok(monkeypatch)

    response = client.get("/api/v1/entities/entity-x", headers=dev_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ENTITY_DETAIL_KEYS
    assert body["id"] == "entity-x"
    assert body["canonical_name"] == "示例实体"
    assert body["category"] == "org"
    assert body["confidence"] == 0.95
    assert body["relation_count"] == 1
    assert isinstance(body["attributes"], list)
    assert any(item["label"] == "alias" for item in body["attributes"])
    assert body["relations"][0]["target_name"] == "实体2"


def test_entity_detail_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """Neo4j 不可达 → 501 `NOT_IMPLEMENTED`。"""
    response = client.get("/api/v1/entities/entity-x", headers=dev_headers)

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"


def test_entity_detail_409_when_no_active_version(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 active 版本 → 409。"""
    monkeypatch.setattr(
        GraphService.instance(),
        "fetch_active_kg_version",
        lambda **kwargs: (_ for _ in ()).throw(
            NoActiveKgVersionError("no active version")
        ),
    )

    response = client.get("/api/v1/entities/entity-x", headers=dev_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "KG_VERSION_NOT_ACTIVE"


def test_entity_detail_requires_auth(client: TestClient) -> None:
    """未认证 → 401。"""
    response = client.get("/api/v1/entities/entity-x")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
