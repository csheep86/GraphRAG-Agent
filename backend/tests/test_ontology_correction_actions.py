"""P5-G：**M6 §3.2 三校正动作**（merge / split / rename）的行为测试（真 Neo4j + 真 PG）。

**为什么单开一个文件**：三端点的失效方向与既有的两类守卫**都不同** ——

- `test_kg_incremental_rebuild.py`（P5-F）绿只说明"增量重算只重写了受影响子图"，
  说明不了"变换语义对不对"（合并后右侧还在不在、改名后旧名去哪了）；
- `test_ontology_placeholder_endpoints.py` 绿只说明"不是占位骨架"，
  是个**反向**守卫，给不出正向行为。

五条主判据（proposal §6 判据 1 / 2 / 3 / 4 / 7 / 8 / 9）：

1. **三端点不再是 501**：各一条 200，且 `kg_version` 是**新**版本（≠ 操作前的 active）；
2. **图操作是真的**：断言对象是**图里的节点 / 属性 / 边**，不是响应体（纪律 R-9）；
3. **增量重算真被触发**：`result_kg_version` 非空（PG 读回）+ `kg_versions` 新增 `ready` 行；
4. **`entity_merge_candidates.status = applied`**（PG 读回）；
5. **跨 org → 403 且零图变更**；**失败显式失败不回落全量**；**P5F-4 显式断言**。

**本地跑法**（本机 Neo4j 常是停的）：

```powershell
docker start graphrag-neo
$env:GRAPH_REAL_NEO4J_URI="bolt://localhost:7687"
$env:GRAPH_REAL_NEO4J_USER="neo4j"
$env:GRAPH_REAL_NEO4J_PASSWORD="ci-graph-pw-2026"
uv run pytest tests/test_ontology_correction_actions.py -q
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
from app.db.models import AuditLog, EntityMergeCandidate, KgVersion, OntologyAction
from app.db.session import session_scope
from app.services.graphs import GraphService
from app.services.kg.correction import (
    OntologyCorrectionError,
    merge_entities,
    rename_entity,
    split_entity,
)
from app.services.kg.versioning import KgVersioningService

# --------------------------------------------------------------------------- #
# 真图开关（与 tests/test_kg_incremental_rebuild.py 同款：CI 上不可达 ⇒ fail，本地 ⇒ skip）
# --------------------------------------------------------------------------- #

_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"

_SETTINGS = get_settings()
_ORG_ID = _SETTINGS.default_org_id
_ACTOR_ID = _SETTINGS.default_actor_id
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


def _seed_entities(real_driver, base: str, rows: list[dict[str, Any]]) -> None:
    with real_driver.session() as session:
        session.run(
            "UNWIND $rows AS row "
            "MERGE (n:Entity {id: row.id, kg_version: row.kg_version}) "
            "SET n.org_id = row.org_id, n.entity_type = 'COMPANY', "
            "    n.canonical_name = row.name, n.confidence = row.confidence, "
            "    n.aliases = row.aliases",
            rows=rows,
        )


def _seed_relations(real_driver, base: str, rows: list[dict[str, Any]]) -> None:
    with real_driver.session() as session:
        session.run(
            "UNWIND $rows AS row "
            "MATCH (a:Entity {id: row.source, kg_version: $version}) "
            "MATCH (b:Entity {id: row.target, kg_version: $version}) "
            "MERGE (a)-[r:RELATION {id: row.rid, kg_version: $version}]->(b) "
            "SET r.relation_type = 'PARTY_TO', r.org_id = $org_id, r.evidence = 'seed'",
            rows=rows,
            version=base,
            org_id=str(_ORG_ID),
        )


def _wipe(real_driver, base: str) -> None:
    with real_driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.kg_version STARTS WITH $base DETACH DELETE n", base=base
        )
        session.run(
            "MATCH (v:KgVersionMirror) WHERE v.version STARTS WITH $base DELETE v",
            base=base,
        )


def _entity(  # noqa: PLR0913 - 种子数据的字段就是这么些，逐个传比塞 dict 可读
    base: str,
    suffix: str,
    name: str,
    *,
    org_id: uuid.UUID,
    confidence: float = 0.9,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{base}-{suffix}",
        "kg_version": base,
        "org_id": str(org_id),
        "name": name,
        "confidence": confidence,
        "aliases": aliases or [],
    }


def _node_ids(real_driver, version: str) -> set[str]:
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
            "MATCH (n:Entity {id: $id, kg_version: $version}) RETURN properties(n) AS props",
            id=node_id,
            version=version,
        ).single()
    return dict(record["props"]) if record else {}


def _relation_rows(real_driver, version: str) -> set[tuple[str, str, str]]:
    """``(source, target, rid)`` 三元组集合（**真图读回**，不是返回值）。"""
    with real_driver.session() as session:
        return {
            (str(record["s"]), str(record["t"]), str(record["rid"]))
            for record in session.run(
                "MATCH (a:Entity {kg_version: $v})-[r:RELATION {kg_version: $v}]->"
                "(b:Entity {kg_version: $v}) "
                "RETURN a.id AS s, b.id AS t, r.id AS rid",
                v=version,
            )
        }


@pytest.fixture
def pg_fixture():
    """真 PG：一条 ready 基线版本 + 一条 `human_review` 的合并候选行。

    与 `test_kg_incremental_rebuild.py::pg_fixture` 同口径（基线**必须真落库**，
    `ready_at` 必须显式给值 —— NULL 在 PG 的 DESC 下排最前，会取到别人残留的行）。
    """
    base = f"p5g-pg-{uuid.uuid4().hex[:8]}"
    trace_id = uuid.uuid4()
    candidate_id = uuid.uuid4()

    with session_scope(org_id=_ORG_ID) as session:
        session.add(
            KgVersion(
                org_id=_ORG_ID,
                version=base,
                status="ready",
                source_doc_ids=[],
                entity_count=0,
                relation_count=0,
                ready_at=datetime.now(UTC),
                trace_id=trace_id,
            )
        )
        session.commit()

    try:
        yield {
            "base_version": base,
            "trace_id": trace_id,
            "candidate_id": candidate_id,
        }
    finally:
        with session_scope(org_id=_ORG_ID) as session:
            session.execute(
                delete(KgVersion).where(
                    KgVersion.org_id == _ORG_ID,
                    KgVersion.version.like(f"{base}%"),
                )
            )
            session.execute(
                delete(OntologyAction).where(
                    OntologyAction.org_id == _ORG_ID,
                    OntologyAction.kg_version.like(f"{base}%"),
                )
            )
            session.execute(
                delete(EntityMergeCandidate).where(
                    EntityMergeCandidate.id == candidate_id,
                )
            )
            session.commit()


def _seed_candidate(
    *, base: str, left: str, right: str, candidate_id: uuid.UUID
) -> None:
    with session_scope(org_id=_ORG_ID) as session:
        session.add(
            EntityMergeCandidate(
                id=candidate_id,
                org_id=_ORG_ID,
                left_entity_id=left,
                right_entity_id=right,
                similarity=0.82,
                status="human_review",
                signals={"name_sim": 0.82, "struct_bonus": 0.0},
                trace_id=uuid.uuid4(),
            )
        )
        session.commit()


def _action_row(action_id: uuid.UUID) -> OntologyAction | None:
    with session_scope(org_id=_ORG_ID) as session:
        return session.get(OntologyAction, action_id)


def _kg_version_row(version: str) -> KgVersion | None:
    with session_scope(org_id=_ORG_ID) as session:
        return session.scalar(
            select(KgVersion).where(
                KgVersion.org_id == _ORG_ID, KgVersion.version == version
            )
        )


def _candidate_row(candidate_id: uuid.UUID) -> EntityMergeCandidate | None:
    with session_scope(org_id=_ORG_ID) as session:
        return session.get(EntityMergeCandidate, candidate_id)


# --------------------------------------------------------------------------- #
# 判据 1 / 2 / 3：merge —— 端点 200 + 图操作真 + 增量重算真被触发
# --------------------------------------------------------------------------- #


def test_merge_endpoint_returns_200_with_a_new_kg_version(
    client,
    dev_headers: dict[str, str],
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 1：`POST /ontology/merge` **不再是 501**，且 `kg_version` 是**新**版本。"""
    base = str(pg_fixture["base_version"])
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "e2", "甲公司分公司", org_id=_ORG_ID),
            _entity(base, "e3", "乙公司", org_id=_ORG_ID),
        ],
    )
    try:
        response = client.post(
            "/api/v1/ontology/merge",
            json={"left_entity_id": f"{base}-e1", "right_entity_id": f"{base}-e2"},
            headers=dev_headers,
        )
    finally:
        _wipe(real_driver, base)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["kg_version"] != base, "响应必须给**新**版本，不能回传操作的基线版本"


def test_correction_action_leaves_an_audit_row(
    client,
    dev_headers: dict[str, str],
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """D8：三端点的审计由 M5 `AuditMiddleware` **全量**覆盖 —— 实测确认**有一条**。

    为什么还要单测一次：中间件是"按路径全量写"，谁都可能以为它覆盖了而没人验过。
    这里以 `trace_id` 回查 `audit_log`，证明校正动作**真的**留了痕（不是靠读代码推断）。
    """
    base = str(pg_fixture["base_version"])
    _seed_entities(real_driver, base, [_entity(base, "e1", "甲公司", org_id=_ORG_ID)])

    try:
        response = client.post(
            "/api/v1/ontology/rename",
            json={"entity_id": f"{base}-e1", "new_canonical_name": "甲有限公司"},
            headers=dev_headers,
        )
        trace_id = uuid.UUID(response.headers["X-Trace-Id"])
        with session_scope(org_id=_ORG_ID) as session:
            rows = list(
                session.scalars(
                    select(AuditLog).where(AuditLog.trace_id == trace_id)
                ).all()
            )
            resources = [row.resource for row in rows]
            statuses = [row.status for row in rows]
            session.execute(delete(AuditLog).where(AuditLog.trace_id == trace_id))
            session.commit()
    finally:
        _wipe(real_driver, base)

    assert response.status_code == 200, response.text
    assert "POST /api/v1/ontology/rename" in resources, (
        f"校正动作没有留下审计行（实际 {resources}）"
    )
    assert "success" in statuses


def test_merge_graph_operation_is_real(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 2（merge）：右节点消失、左节点吸收其名、右侧关系按原方向挂到左侧。

    断言对象是**图里的节点 / 属性 / 边**，不是函数返回值（纪律 R-9）。
    """
    base = str(pg_fixture["base_version"])
    left, right, neighbor = f"{base}-e1", f"{base}-e2", f"{base}-e3"
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID, confidence=0.7),
            _entity(base, "e2", "甲公司分公司", org_id=_ORG_ID, confidence=0.95),
            _entity(base, "e3", "乙公司", org_id=_ORG_ID),
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {"source": left, "target": neighbor, "rid": f"{base}-r-left"},
            {"source": right, "target": neighbor, "rid": f"{base}-r-right"},
        ],
    )
    base_before = _node_ids(real_driver, base)
    relations_before = _relation_rows(real_driver, base)

    try:
        with session_scope(org_id=_ORG_ID) as session:
            result = merge_entities(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                left_entity_id=left,
                right_entity_id=right,
                graph_service=graph_service,
            )
        new_version = result.kg_version
        merged_props = _node_props(real_driver, new_version, left)
        new_nodes = _node_ids(real_driver, new_version)
        new_relations = _relation_rows(real_driver, new_version)
        # ⚠️ 后状态必须**在 try 里**取：`finally` 的 `_wipe` 会先跑，
        # 出了 try 再读图只会读到空集（把"旧版本被清空"误判成回归）
        base_after = _node_ids(real_driver, base)
        relations_after = _relation_rows(real_driver, base)
    finally:
        _wipe(real_driver, base)

    # 新版本：右侧不再独立存在
    assert right not in new_nodes, "被并入侧应当消失"
    assert left in new_nodes and neighbor in new_nodes
    # 左节点吸收右侧的规范名；confidence 取两侧较大
    assert merged_props["canonical_name"] == "甲公司"
    assert "甲公司分公司" in list(merged_props.get("aliases") or [])
    assert merged_props["confidence"] == 0.95
    # 右侧那条边按**原方向**挂到了左侧
    assert (left, neighbor, f"{base}-r-right") in new_relations
    assert (left, neighbor, f"{base}-r-left") in new_relations

    # 旧版本：一条不动（不重建全图 / 不改历史版本）
    assert base_after == base_before
    assert relations_after == relations_before


# --------------------------------------------------------------------------- #
# 判据 2：split / rename 的图操作
# --------------------------------------------------------------------------- #


def test_split_creates_new_nodes_and_retires_the_original(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 2（split）：N 个新节点 + 原节点 `status='split'` + **默认同名**迁移。"""
    base = str(pg_fixture["base_version"])
    origin, named, other = f"{base}-e1", f"{base}-n1", f"{base}-n2"
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "n1", "张伟", org_id=_ORG_ID),
            _entity(base, "n2", "李娜", org_id=_ORG_ID),
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {"source": origin, "target": named, "rid": f"{base}-r-match"},
            {"source": origin, "target": other, "rid": f"{base}-r-nomatch"},
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as session:
            result = split_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=origin,
                new_canonical_names=["张伟", "张玮"],
                graph_service=graph_service,
            )
        new_version = result.kg_version
        new_nodes = _node_ids(real_driver, new_version)
        new_relations = _relation_rows(real_driver, new_version)
        origin_props = _node_props(real_driver, new_version, origin)
        # ⚠️ 同 `test_merge_graph_operation_is_real`：后状态一律在 try 里取
        first_props = _node_props(real_driver, new_version, f"{origin}--split-1")
    finally:
        _wipe(real_driver, base)

    first, second = f"{origin}--split-1", f"{origin}--split-2"
    assert {first, second} <= new_nodes, "拆分必须真的落 N 个新节点"
    assert first_props["canonical_name"] == "张伟"
    assert origin_props.get("status") == "split", "原节点必须置 status='split'"

    # **默认同名**：对端叫"张伟"的那条边迁到了同名的新节点上，原边已删
    assert (first, named, f"{base}-r-match") in new_relations
    assert not any(
        source == origin and rid == f"{base}-r-match"
        for source, _, rid in new_relations
    ), "迁移是搬走，不是复制"
    # 匹配不上 ⇒ 留在原节点（不删、不猜）
    assert (origin, other, f"{base}-r-nomatch") in new_relations


def test_rename_changes_canonical_name_and_keeps_the_old_one_as_alias(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 2（rename）：`canonical_name` 换新 + **旧名进 `aliases`**（M2 §4.3）。"""
    base = str(pg_fixture["base_version"])
    target = f"{base}-e1"
    _seed_entities(
        real_driver,
        base,
        [_entity(base, "e1", "甲公司", org_id=_ORG_ID, aliases=["甲"])],
    )

    try:
        with session_scope(org_id=_ORG_ID) as session:
            result = rename_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=target,
                new_canonical_name="甲有限公司",
                graph_service=graph_service,
            )
        props = _node_props(real_driver, result.kg_version, target)
    finally:
        _wipe(real_driver, base)

    assert props["canonical_name"] == "甲有限公司"
    assert "甲公司" in list(props.get("aliases") or []), "旧规范名必须进 aliases"
    assert "甲" in list(props.get("aliases") or []), "既有别名不得被覆盖"


# --------------------------------------------------------------------------- #
# 判据 3 / 4：PG 真源
# --------------------------------------------------------------------------- #


def test_incremental_rebuild_really_ran(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 3：`result_kg_version` 非空（PG 读回）+ `kg_versions` 新增 `ready` 行。"""
    base = str(pg_fixture["base_version"])
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "e2", "甲公司分公司", org_id=_ORG_ID),
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as session:
            result = rename_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=f"{base}-e1",
                new_canonical_name="甲有限公司",
                graph_service=graph_service,
            )
        action = _action_row(result.action_id)
        version_row = _kg_version_row(result.kg_version)
    finally:
        _wipe(real_driver, base)

    assert action is not None
    assert action.result_kg_version == result.kg_version, "`result_kg_version` 未真回填"
    assert action.kg_version == base, "动作行记的是**操作时**的 active 版本（用于回放）"
    assert action.error_code is None
    assert version_row is not None and version_row.status == "ready"


def test_merge_marks_the_candidate_applied_in_pg(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 4：merge 后候选行 `human_review` → **`applied`**（真 PG 读回）。"""
    base = str(pg_fixture["base_version"])
    left, right = f"{base}-e1", f"{base}-e2"
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "e2", "甲公司分公司", org_id=_ORG_ID),
        ],
    )
    _seed_candidate(
        base=base, left=left, right=right, candidate_id=pg_fixture["candidate_id"]
    )
    assert _candidate_row(pg_fixture["candidate_id"]).status == "human_review"

    try:
        with session_scope(org_id=_ORG_ID) as session:
            merge_entities(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                left_entity_id=left,
                right_entity_id=right,
                graph_service=graph_service,
            )
        status = _candidate_row(pg_fixture["candidate_id"]).status
    finally:
        _wipe(real_driver, base)

    assert status == "applied"


# --------------------------------------------------------------------------- #
# 判据 7：跨 org ⇒ 403，且零图变更
# --------------------------------------------------------------------------- #


def test_cross_org_merge_is_403_and_changes_nothing(
    client,
    dev_headers: dict[str, str],
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 7：以 A org 身份动 B org 的实体 ⇒ **403 `FORBIDDEN`**，图**零变更**。

    **不**降级为「只合并同租户的那个」——那是数据污染（`ontology.py` 的
    description 已这么写）。
    """
    base = str(pg_fixture["base_version"])
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "x1", "他租户公司", org_id=_OTHER_ORG_ID),
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [{"source": f"{base}-e1", "target": f"{base}-x1", "rid": f"{base}-r-cross"}],
    )
    before = _node_ids(real_driver, base)
    relations_before = _relation_rows(real_driver, base)

    try:
        response = client.post(
            "/api/v1/ontology/merge",
            json={"left_entity_id": f"{base}-e1", "right_entity_id": f"{base}-x1"},
            headers=dev_headers,
        )
        after = _node_ids(real_driver, base)
        relations_after = _relation_rows(real_driver, base)
    finally:
        _wipe(real_driver, base)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert after == before, "跨租户被拒后不得产生任何图变更"
    assert relations_after == relations_before


# --------------------------------------------------------------------------- #
# 判据 8：失败显式失败，且不回落全量重建
# --------------------------------------------------------------------------- #


def test_incremental_failure_is_explicit_without_full_rebuild(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """判据 8：增量重算失败 ⇒ 落 `error_code`、`result_kg_version` 仍 NULL、旧版本不变。

    注入点是 P5-F 的 `_rewrite_subgraph`（**在版本行已建之后**抛 `_RebuildFailure`），
    走的是它**自己的**失败路径（`_fail`），不是假返回值——这样 `error_code` 才
    真的会落库。⚠️ **不能**注入在 `mark_building` 上：那句在 `rebuild_incrementally`
    的 `try` **之外**（`incremental.py:250`），抛出来不会被 `_fail` 兜住，
    验到的就成了"异常穿透"而不是"显式失败"。

    绝不静默回落全量重建（Non-goal 9）：真回落的话，新版本会带上全图。
    """
    base = str(pg_fixture["base_version"])
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, "e1", "甲公司", org_id=_ORG_ID),
            _entity(base, "e2", "甲公司分公司", org_id=_ORG_ID),
            _entity(base, "e3", "乙公司", org_id=_ORG_ID),
        ],
    )
    before = _node_ids(real_driver, base)

    import app.services.kg.incremental as incremental

    def _boom(**_kwargs: Any) -> None:
        raise incremental._RebuildFailure(  # noqa: SLF001 - 注入 P5-F 的真失败路径
            error_code=ErrorCode.ENTITY_NOT_FOUND, error_detail="injected failure"
        )

    monkeypatch.setattr(incremental, "_rewrite_subgraph", _boom)

    try:
        with session_scope(org_id=_ORG_ID) as session:
            with pytest.raises(OntologyCorrectionError) as excinfo:
                merge_entities(
                    db=session,
                    org_id=_ORG_ID,
                    actor_id=_ACTOR_ID,
                    trace_id=uuid.uuid4(),
                    left_entity_id=f"{base}-e1",
                    right_entity_id=f"{base}-e2",
                    graph_service=graph_service,
                )
        rows = _pending_action_rows(base)
        after = _node_ids(real_driver, base)
    finally:
        _wipe(real_driver, base)

    assert excinfo.value.error_code == ErrorCode.ENTITY_NOT_FOUND
    assert len(rows) == 1, f"失败也要留下审计行，实际 {len(rows)} 行"
    assert rows[0].error_code == "ENTITY_NOT_FOUND"
    assert rows[0].result_kg_version is None, "失败却回填了新版本 ⇒ 把事故伪装成成功"
    # 没有回落全量重建：图里没有新版本节点，旧版本一条不少
    assert after == before


def _pending_action_rows(base: str) -> list[OntologyAction]:
    with session_scope(org_id=_ORG_ID) as session:
        return list(
            session.scalars(
                select(OntologyAction).where(
                    OntologyAction.org_id == _ORG_ID,
                    OntologyAction.kg_version == base,
                )
            ).all()
        )


# --------------------------------------------------------------------------- #
# 判据 9：P5F-4 —— 新版本只承载受影响子图（**显式断言**这个已知缺口）
# --------------------------------------------------------------------------- #


def test_new_version_carries_only_the_corrected_subgraph(
    graph_service: GraphService,
    real_driver,
    pg_fixture: dict[str, Any],
    real_pg_get_active: None,
) -> None:
    """判据 9 / **P5F-4**：以新 `kg_version` 读图 ⇒ **只**看到被校正的那一小撮。

    ⚠️ 这条断言的是**已知缺口**，不是期望行为：消费侧（M3 / M4）按新版本读图
    会看不到未受影响的节点。本批**不**解决它（解决 = 把全图复制进新版本 ⇒
    直接打掉 P5F-3「增量重写节点数 = 校正节点数」的机械判据），只把它**钉成
    显式事实**，缺口登记在 `changes/P5-G/integration-log.md`，版本链读侧归后续批次。
    """
    base = str(pg_fixture["base_version"])
    _seed_entities(
        real_driver,
        base,
        [
            _entity(base, f"e{index}", f"实体{index}", org_id=_ORG_ID)
            for index in range(1, 6)
        ],
    )
    before = _node_ids(real_driver, base)
    assert len(before) == 5

    try:
        with session_scope(org_id=_ORG_ID) as session:
            result = rename_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=f"{base}-e1",
                new_canonical_name="改名后",
                graph_service=graph_service,
            )
        new_nodes = _node_ids(real_driver, result.kg_version)
        # ⚠️ 同上：后状态在 try 里取
        base_after = _node_ids(real_driver, base)
        origin_after = _node_props(real_driver, base, f"{base}-e1")
    finally:
        _wipe(real_driver, base)

    # 只承载被校正的那一个（没有 1 跳邻居可带 ⇒ 就是它自己）
    assert new_nodes == {f"{base}-e1"}
    assert len(new_nodes) != len(before), "若等于全图节点数 ⇒ 那是全量重建，不是增量"
    # 旧版本一条不动
    assert base_after == before
    assert origin_after["canonical_name"] == "实体1"


# --------------------------------------------------------------------------- #
# 前置不成立（不需要真图）
# --------------------------------------------------------------------------- #


def test_no_active_version_is_rejected(
    pg_fixture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PG 无 ready 版本 ⇒ 409 `KG_VERSION_NOT_ACTIVE`（**不**静默按别的版本改）。"""
    monkeypatch.setattr(KgVersioningService, "get_active", lambda self, *, org_id: None)
    with session_scope(org_id=_ORG_ID) as session:
        with pytest.raises(OntologyCorrectionError) as excinfo:
            rename_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id="ent-not-exist",
                new_canonical_name="新名",
            )
    assert excinfo.value.error_code == ErrorCode.KG_VERSION_NOT_ACTIVE


def test_split_with_a_single_new_entity_is_rejected(
    pg_fixture: dict[str, Any], real_pg_get_active: None
) -> None:
    """只拆 1 个等价改名 ⇒ 显式拒绝（契约的 `min_length=2` 是同一条口径）。"""
    with session_scope(org_id=_ORG_ID) as session:
        with pytest.raises(OntologyCorrectionError) as excinfo:
            split_entity(
                db=session,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id="ent-a",
                new_canonical_names=["只有一个"],
            )
    assert excinfo.value.error_code == ErrorCode.VALIDATION_ERROR
