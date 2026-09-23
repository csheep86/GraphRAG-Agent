"""Sprint 6.3：在线激活端点 `POST /graph/versions/{version}/activate`。

真机发现：**后端没有激活端点**——建图只把 PG 置 ``ready``，没人同步 Neo4j 镜像，
读侧于是长期命中旧导入版本（无 ``:Chunk``）。本文件把该端点的**错误语义**钉死：

- 200：真源 ``ready`` + 镜像 ``active``，返回被置 ``superseded`` 的历史版本；
- 404：PG 查不到（``kg_version_not_found``）/ 图里没有（``kg_version_absent_in_graph``）；
- 409：``pending`` / ``building`` / ``failed`` → ``KG_VERSION_NOT_ACTIVE``；
- 501：Neo4j 不可用 → ``NOT_IMPLEMENTED``（**不**伪装成 404 / 409）。

PG 与 Neo4j 全部打桩，不依赖外部服务。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.graphs import GraphService, GraphUnavailableError
from app.services.kg.versioning import (
    KgVersioningService,
    KgVersionNotActivatableError,
    KgVersionNotFoundError,
    KgVersionRecord,
)

VERSION = "v-3e381d36"
OLD_VERSION = "20260917T090000Z-phase09"


def _record(*, version: str = VERSION, status: str = "ready") -> KgVersionRecord:
    return KgVersionRecord(
        id=uuid4(),
        org_id=uuid4(),
        version=version,
        status=status,
        source_doc_ids=[],
        entity_count=18,
        relation_count=15,
        error_code=None,
        error_detail=None,
        ready_at=None,
        trace_id=uuid4(),
    )


def _patch_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """PG 真源允许激活 + 图侧存在该版本 + 镜像写入成功。"""
    monkeypatch.setattr(
        KgVersioningService,
        "activate_by_version",
        lambda self, *, org_id, version: _record(version=version),
    )
    monkeypatch.setattr(
        GraphService,
        "fetch_kg_version_status",
        lambda self, version: "superseded",
    )
    monkeypatch.setattr(
        GraphService,
        "activate_kg_version",
        lambda self, *, version, org_id, trace_id: [OLD_VERSION],
    )


def test_activate_returns_200_and_reports_both_statuses(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """真源 ``ready`` 与镜像 ``active`` 是**同一语义的两套词汇**，都必须返回。"""
    _patch_ok(monkeypatch)

    response = client.post(
        f"/api/v1/graph/versions/{VERSION}/activate", headers=dev_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == VERSION
    assert body["source_status"] == "ready"
    assert body["graph_mirror_status"] == "active"
    assert body["superseded_versions"] == [OLD_VERSION]
    assert body["trace_id"]


def test_activate_404_when_version_missing_in_source(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PG 真源查不到 → 404（复用 ``NOT_FOUND``，不新增错误码）。"""

    def _boom(self: KgVersioningService, *, org_id: Any, version: str) -> Any:
        raise KgVersionNotFoundError(f"kg_version 不存在: version={version}")

    monkeypatch.setattr(KgVersioningService, "activate_by_version", _boom)

    response = client.post(
        f"/api/v1/graph/versions/{VERSION}/activate", headers=dev_headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["detail"]["reason"] == "kg_version_not_found"


def test_activate_409_when_version_not_activatable(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``failed`` 版本不得被激活（图数据已被三段式补偿清理）。"""

    def _boom(self: KgVersioningService, *, org_id: Any, version: str) -> Any:
        raise KgVersionNotActivatableError(version=version, status="failed")

    monkeypatch.setattr(KgVersioningService, "activate_by_version", _boom)

    response = client.post(
        f"/api/v1/graph/versions/{VERSION}/activate", headers=dev_headers
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "KG_VERSION_NOT_ACTIVE"
    assert body["detail"]["status"] == "failed"


def test_activate_404_when_absent_in_graph(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PG 有而图里没有 → 激活后仍查不到数据，属「假成功」，必须 404。"""
    monkeypatch.setattr(
        KgVersioningService,
        "activate_by_version",
        lambda self, *, org_id, version: _record(version=version),
    )
    monkeypatch.setattr(
        GraphService, "fetch_kg_version_status", lambda self, version: None
    )

    response = client.post(
        f"/api/v1/graph/versions/{VERSION}/activate", headers=dev_headers
    )

    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "kg_version_absent_in_graph"


def test_activate_501_when_neo4j_down(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neo4j 不可用 → 501（基础设施故障，**不**伪装成 404 / 409）。"""
    monkeypatch.setattr(
        KgVersioningService,
        "activate_by_version",
        lambda self, *, org_id, version: _record(version=version),
    )
    monkeypatch.setattr(
        GraphService, "fetch_kg_version_status", lambda self, version: "ready"
    )

    def _boom(
        self: GraphService, *, version: str, org_id: Any, trace_id: str
    ) -> list[str]:
        raise GraphUnavailableError("connection refused")

    monkeypatch.setattr(GraphService, "activate_kg_version", _boom)

    response = client.post(
        f"/api/v1/graph/versions/{VERSION}/activate", headers=dev_headers
    )

    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"
