"""P5-F：**M6 §3.3 增量重算**的行为测试（真 Neo4j + 真 PG）。

**为什么单开一个文件**：增量重算是「校正动作 → 新版本」的落点，它的失效方向
与既有的 `test_kg_versioning.py`（版本状态机 CRUD）**相反**——后者绿只说明
"版本行能建能改"，说明不了"重算时只动了受影响的子图"。混在一起会互相掩护。

五条主判据（proposal §6）：

1. **不重建全图**：真图前后**计数**做差 = 受影响节点数，**不是**全图节点数；
   未受影响节点 `id` / 属性**逐条不变**；
2. **新版本落库且文档级**：`kg_versions` 新增一行走完状态机，`source_doc_ids`
   **只含受影响文档**（≠ 全量文档）；
3. **`result_kg_version` 真被回填**（PG 读回，不是函数返回值）；
4. **失败显式失败**：落 `error_code` / `error_detail`，`result_kg_version` 仍 NULL，
   **且没有回落全量重建**（旧版本节点数不变）；
5. **配置有真实消费者**：改 `increment_rebuild_batch_size` 会真的改变批数
   （断言**读到并生效**，不只断言"设了"）。

**本地跑法**（本机 Neo4j 常是停的）：

```powershell
docker start graphrag-neo
$env:GRAPH_REAL_NEO4J_URI="bolt://localhost:7687"
$env:GRAPH_REAL_NEO4J_USER="neo4j"
$env:GRAPH_REAL_NEO4J_PASSWORD="ci-graph-pw-2026"
uv run pytest tests/test_kg_incremental_rebuild.py -q
```
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import Document, KgVersion, OntologyAction
from app.db.session import session_scope
from app.services.graphs import GraphService
from app.services.kg.incremental import (
    IncrementalRebuildError,
    rebuild_incrementally,
)
from app.services.kg.versioning import KgVersioningService

# --------------------------------------------------------------------------- #
# 真图开关（与 tests/test_guardrails_graph.py 同款：CI 上不可达 ⇒ fail，本地 ⇒ skip）
# --------------------------------------------------------------------------- #

_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"

_SETTINGS = get_settings()
_ORG_ID = _SETTINGS.default_org_id
_ACTOR_ID = _SETTINGS.default_actor_id
#: 第二个租户（跨租户判据用；与 conftest.OTHER_ORG_ID 同值）
_OTHER_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _real_graph_env() -> tuple[str, str, str]:
    uri = os.environ.get(_REAL_URI_ENV, "").strip()
    user = os.environ.get(_REAL_USER_ENV, "").strip() or "neo4j"
    password = os.environ.get(_REAL_PASSWORD_ENV, "").strip()
    if not uri or not password:
        if os.environ.get("CI"):
            pytest.fail(
                f"未设 {_REAL_URI_ENV} / {_REAL_PASSWORD_ENV} ⇒ CI 上真图用例连不上图库，"
                "这是**门禁失效**不是环境问题"
            )
        pytest.skip(
            f"未设 {_REAL_URI_ENV} / {_REAL_PASSWORD_ENV}（本地无 Neo4j ⇒ 真图用例跳过）"
        )
    return uri, user, password


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def real_driver():
    """真 Neo4j driver（模块级：建一次连接，用例共享）。"""
    uri, user, password = _real_graph_env()
    from neo4j import GraphDatabase  # 局部导入：与产品代码同款（避免导入期连接）

    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=10.0)
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


@pytest.fixture
def graph_service(monkeypatch: pytest.MonkeyPatch) -> GraphService:
    """把 `GraphService` 指向**真** Neo4j（其余用例仍走不可达端口）。"""
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


@pytest.fixture
def seeded_graph(real_driver, pg_fixture: dict[str, Any]):
    """真图：同一 `kg_version` 下 **5 个**本 org 节点 + 1 个**他 org** 节点。

    ⚠️ 图上用的版本号**就是 PG 基线版本的那个值**：增量重算的 `base_version`
    取自 PG 真源，图与库的版本号必须同一个，否则判据会退化成"两个世界各说各话"。

    - `e1 -[:RELATION]-> e2`（**两端都受影响** ⇒ 应被迁移）
    - `e1 -[:RELATION]-> e3`（一端不受影响 ⇒ **不**迁移）
    - `x1`（他 org 节点，供跨租户判据用）

    版本号唯一 ⇒ 重跑 / 并发互不污染；用例结束按**前缀**清干净
    （增量版本是 `<base>-inc-<suffix>`，一并清掉）。
    """
    base = str(pg_fixture["base_version"])
    rows = [
        {
            "id": f"{base}-e{i}",
            "kg_version": base,
            "org_id": str(_ORG_ID),
            "name": f"实体{i}",
            "entity_type": "COMPANY",
            "confidence": 0.9,
        }
        for i in range(1, 6)
    ]
    rows.append(
        {
            "id": f"{base}-x1",
            "kg_version": base,
            "org_id": str(_OTHER_ORG_ID),
            "name": "他租户实体",
            "entity_type": "COMPANY",
            "confidence": 0.9,
        }
    )

    def _seed_entities() -> None:
        with real_driver.session() as session:
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n:Entity {id: row.id, kg_version: row.kg_version}) "
                "SET n.org_id = row.org_id, n.entity_type = row.entity_type, "
                "    n.canonical_name = row.name, n.confidence = row.confidence",
                rows=rows,
            )

    def _seed_relations() -> None:
        with real_driver.session() as session:
            session.run(
                "UNWIND $rows AS row "
                "MATCH (a:Entity {id: row.source, kg_version: $version}) "
                "MATCH (b:Entity {id: row.target, kg_version: $version}) "
                "MERGE (a)-[r:RELATION {id: row.rid, kg_version: $version}]->(b) "
                "SET r.relation_type = 'PARTY_TO', r.org_id = $org_id, "
                "    r.evidence = 'seed'",
                rows=[
                    {
                        "source": f"{base}-e1",
                        "target": f"{base}-e2",
                        "rid": f"{base}-r-inside",
                    },
                    {
                        "source": f"{base}-e1",
                        "target": f"{base}-e3",
                        "rid": f"{base}-r-outside",
                    },
                ],
                version=base,
                org_id=str(_ORG_ID),
            )

    def _wipe() -> None:
        with real_driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.kg_version STARTS WITH $base DETACH DELETE n",
                base=base,
            )
            session.run(
                "MATCH (v:KgVersionMirror) WHERE v.version STARTS WITH $base DELETE v",
                base=base,
            )

    _seed_entities()
    _seed_relations()
    try:
        yield base
    finally:
        _wipe()


def _node_ids(real_driver, version: str) -> set[str]:
    """该 `kg_version` 下的 `:Entity` 节点 id 集合（**真图计数**，不是返回值）。"""
    with real_driver.session() as session:
        return {
            str(record["id"])
            for record in session.run(
                "MATCH (n:Entity {kg_version: $version}) RETURN n.id AS id",
                version=version,
            )
        }


def _node_props(real_driver, version: str, node_id: str) -> dict[str, Any]:
    with real_driver.session() as session:
        record = session.run(
            "MATCH (n:Entity {id: $id, kg_version: $version}) "
            "RETURN properties(n) AS props",
            id=node_id,
            version=version,
        ).single()
    return dict(record["props"]) if record else {}


def _relation_ids(real_driver, version: str) -> set[str]:
    with real_driver.session() as session:
        return {
            str(record["rid"])
            for record in session.run(
                "MATCH ()-[r:RELATION {kg_version: $version}]->() RETURN r.id AS rid",
                version=version,
            )
        }


@pytest.fixture
def pg_fixture():
    """真 PG：3 份文档（1 份受影响）+ 一条 ready 基线版本 + 一条 `ontology_actions`。

    基线版本**必须真落库**：增量重算的 `base_version` 取自 PG 真源的 active
    （= `ready`）版本，桩掉它就等于把判据换成"函数自说自话"。
    用例结束按 id / 前缀精确清理，不污染其它用例。
    """
    doc_ids = [uuid.uuid4() for _ in range(3)]
    base = f"p5f-pg-{uuid.uuid4().hex[:8]}"
    action_id = uuid.uuid4()
    trace_id = uuid.uuid4()

    with session_scope(org_id=_ORG_ID) as session:
        for doc_id in doc_ids:
            session.add(
                Document(
                    id=doc_id,
                    filename_hash=f"p5f-{doc_id.hex}",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    status="completed",
                    uploaded_by=_ACTOR_ID,
                    org_id=_ORG_ID,
                    trace_id=trace_id,
                )
            )
        session.add(
            KgVersion(
                org_id=_ORG_ID,
                version=base,
                status="ready",
                source_doc_ids=[str(doc_id) for doc_id in doc_ids],
                entity_count=5,
                relation_count=2,
                # get_active 按 ready_at 倒序取；NULL 在 PG 的 DESC 下排**最前**
                # ⇒ 必须显式给值，否则取到的可能是别人残留的行。
                ready_at=datetime.now(UTC),
                trace_id=trace_id,
            )
        )
        session.add(
            OntologyAction(
                id=action_id,
                org_id=_ORG_ID,
                action_type="merge",
                target_entities=[f"{base}-e1", f"{base}-e2"],
                actor_id=_ACTOR_ID,
                kg_version=base,
                trace_id=trace_id,
            )
        )
        session.commit()

    try:
        yield {
            "doc_ids": doc_ids,
            "affected_doc_id": doc_ids[0],
            "base_version": base,
            "action_id": action_id,
            "trace_id": trace_id,
        }
    finally:
        with session_scope(org_id=_ORG_ID) as session:
            session.execute(delete(Document).where(Document.id.in_(doc_ids)))
            session.execute(
                delete(KgVersion).where(
                    KgVersion.org_id == _ORG_ID,
                    KgVersion.version.like(f"{base}%"),
                )
            )
            session.execute(
                delete(OntologyAction).where(OntologyAction.id == action_id)
            )
            session.commit()


def _kg_version_row(version: str) -> KgVersion | None:
    with session_scope(org_id=_ORG_ID) as session:
        return session.scalar(
            select(KgVersion).where(
                KgVersion.org_id == _ORG_ID, KgVersion.version == version
            )
        )


def _action_row(action_id: uuid.UUID) -> OntologyAction | None:
    with session_scope(org_id=_ORG_ID) as session:
        return session.get(OntologyAction, action_id)


# --------------------------------------------------------------------------- #
# 判据 1 / 2：不重建全图 + 新版本文档级（真图 + 真 PG）
# --------------------------------------------------------------------------- #


def test_incremental_rebuild_rewrites_only_affected_subgraph(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
    real_driver,
) -> None:
    """受影响 2 个节点 ⇒ 新版本**只有**这 2 个；旧版本 5 个一条不动。

    这是「不重建全图」唯一的机械形态：全量重建会写出 5 个（且要重跑抽取），
    增量只写 2 个。断言对象是**图里的实际计数**，不是函数返回值（纪律 R-9）。
    """
    base = seeded_graph
    affected = [f"{base}-e1", f"{base}-e2"]
    before_base = _node_ids(real_driver, base)
    before_props = {nid: _node_props(real_driver, base, nid) for nid in before_base}

    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=affected,
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    assert result.status == "ready", result.error_detail
    assert result.entity_count == 2
    assert result.relation_count == 1, "两端都受影响的边才迁移（另有一条跨边界的不动）"

    # 新版本：**只有**受影响的 2 个
    assert _node_ids(real_driver, result.new_version) == set(affected)
    # 不等于全图节点数（5 个本 org + 1 个他 org）
    assert len(_node_ids(real_driver, result.new_version)) != len(before_base)

    # 旧版本：一条不动，属性逐条不变
    assert _node_ids(real_driver, base) == before_base
    for nid, props in before_props.items():
        assert _node_props(real_driver, base, nid) == props, (
            f"未受影响节点 {nid} 的属性被改动 ⇒ 动的不是「受影响子图」"
        )

    # 关系：只迁移受影响子图内部的那一端都在集合内的边
    assert _relation_ids(real_driver, result.new_version) == {f"{base}-r-inside"}
    assert _relation_ids(real_driver, base) == {
        f"{base}-r-inside",
        f"{base}-r-outside",
    }


def test_new_kg_version_row_is_ready_and_document_scoped(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """新版本行走完状态机，且 `source_doc_ids` **只含受影响文档**（P5F-2）。"""
    base = seeded_graph
    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=[f"{base}-e1", f"{base}-e2"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    row = _kg_version_row(result.new_version)
    assert row is not None, "kg_versions 未新增行"
    assert row.status == "ready", f"状态机未走完: status={row.status}"
    assert row.version != base

    assert row.source_doc_ids == [str(pg_fixture["affected_doc_id"])]
    all_docs = {str(doc_id) for doc_id in pg_fixture["doc_ids"]}
    assert set(row.source_doc_ids) != all_docs, (
        "新版本挂上了全量文档 ⇒ 这不是「文档级」增量"
    )


# --------------------------------------------------------------------------- #
# 判据 3：result_kg_version 真被回填（PG 读回）
# --------------------------------------------------------------------------- #


def test_result_kg_version_is_backfilled_in_pg(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """`ontology_actions.result_kg_version` 由 NULL → 新版本号（**真读回**）。"""
    base = seeded_graph
    action_id = pg_fixture["action_id"]
    assert _action_row(action_id).result_kg_version is None

    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=action_id,
            affected_entity_ids=[f"{base}-e1", f"{base}-e2"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    row = _action_row(action_id)
    assert row.result_kg_version == result.new_version
    assert row.error_code is None
    assert row.error_detail is None


# --------------------------------------------------------------------------- #
# 判据 4：失败显式失败，且不回落全量重建
# --------------------------------------------------------------------------- #


def test_failure_lands_error_code_without_full_rebuild(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
    real_driver,
) -> None:
    """受影响集里有一个**不存在**的实体 ⇒ 显式失败，**不**静默回落全量重建。

    「不回落全量」的机械判据：失败后**图里没有任何新版本节点**，且旧版本
    节点数一条不少（真回落全量的话，新版本会带上全图 5 个节点）。
    """
    base = seeded_graph
    before_base = _node_ids(real_driver, base)

    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=[f"{base}-e1", f"{base}-does-not-exist"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    assert result.status == "failed"
    assert result.error_code == str(ErrorCode.ENTITY_NOT_FOUND)
    assert result.error_detail

    row = _action_row(pg_fixture["action_id"])
    assert row.error_code == str(ErrorCode.ENTITY_NOT_FOUND)
    assert row.error_detail
    assert row.result_kg_version is None, "失败却回填了新版本 ⇒ 把事故伪装成成功"

    failed = _kg_version_row(result.new_version)
    assert failed is not None and failed.status == "failed"
    assert failed.error_code == str(ErrorCode.ENTITY_NOT_FOUND)

    # 没有全量重建：新版本一个节点都没有，旧版本一条不少
    assert _node_ids(real_driver, result.new_version) == set()
    assert _node_ids(real_driver, base) == before_base


def test_cross_org_entity_is_rejected_not_skipped(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """受影响实体属于**他 org** ⇒ `KG_TENANT_LEAK`，**不**静默跳过继续算。

    静默跳过会让「他租户的节点被写进本租户的新版本」这种数据污染在日志里
    表现为"少算了一个"，而不是"拒绝了一次"。
    """
    base = seeded_graph
    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=[f"{base}-e1", f"{base}-x1"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    assert result.status == "failed"
    assert result.error_code == str(ErrorCode.KG_TENANT_LEAK)
    assert _action_row(pg_fixture["action_id"]).error_code == str(
        ErrorCode.KG_TENANT_LEAK
    )


# --------------------------------------------------------------------------- #
# 判据 5：配置有真实消费者（改了会真的改变批数）
# --------------------------------------------------------------------------- #


def test_batch_size_from_settings_really_changes_batches(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`increment_rebuild_batch_size=1` ⇒ 批数变多（证明**读到了**并在用）。

    断言**读到的值**而不只是"设了"（`Settings.model_config` 是 `extra="ignore"`，
    环境变量名拼错会被静默忽略——P5-D 已踩过一次）。
    """
    base = seeded_graph
    settings = get_settings()
    monkeypatch.setattr(settings, "increment_rebuild_batch_size", 1)
    assert settings.increment_rebuild_batch_size == 1

    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=[f"{base}-e1", f"{base}-e2"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    # 2 个节点（2 批）+ 1 条关系（1 批）
    assert result.batch_count == 3


def test_batch_size_default_comes_from_settings(
    graph_service: GraphService,
    seeded_graph: str,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """不显式传 `batch_size` ⇒ 取 `settings.increment_rebuild_batch_size`（默认 100）。"""
    base = seeded_graph
    with session_scope(org_id=_ORG_ID) as session:
        result = rebuild_incrementally(
            db=session,
            org_id=_ORG_ID,
            action_id=pg_fixture["action_id"],
            affected_entity_ids=[f"{base}-e1", f"{base}-e2"],
            source_doc_ids=[pg_fixture["affected_doc_id"]],
            graph_service=graph_service,
        )

    # 100 > 受影响规模 ⇒ 节点 1 批 + 关系 1 批
    assert result.batch_count == 2


# --------------------------------------------------------------------------- #
# 前置不成立（不需要真图）
# --------------------------------------------------------------------------- #


def test_no_active_version_raises_and_writes_nothing(
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PG 无 ready 版本 ⇒ `KG_VERSION_NOT_ACTIVE`，且**一行 `kg_versions` 都不落**。"""
    monkeypatch.setattr(KgVersioningService, "get_active", lambda self, *, org_id: None)
    with session_scope(org_id=_ORG_ID) as session:
        with pytest.raises(IncrementalRebuildError) as excinfo:
            rebuild_incrementally(
                db=session,
                org_id=_ORG_ID,
                action_id=pg_fixture["action_id"],
                affected_entity_ids=["e1"],
            )

    assert excinfo.value.error_code == ErrorCode.KG_VERSION_NOT_ACTIVE
    with session_scope(org_id=_ORG_ID) as session:
        rows = session.scalars(
            select(KgVersion).where(
                KgVersion.org_id == _ORG_ID,
                KgVersion.version.like(f"{pg_fixture['base_version']}-inc-%"),
            )
        ).all()
    assert rows == []


def test_empty_affected_set_rejected(
    pg_fixture: dict[str, Any], real_pg_get_active: None
) -> None:
    """受影响集为空 ⇒ 显式失败（空集重算 = 什么都没做却被记为成功）。"""
    with session_scope(org_id=_ORG_ID) as session:
        with pytest.raises(IncrementalRebuildError) as excinfo:
            rebuild_incrementally(
                db=session,
                org_id=_ORG_ID,
                action_id=pg_fixture["action_id"],
                affected_entity_ids=[],
            )
    assert excinfo.value.error_code == ErrorCode.VALIDATION_ERROR
