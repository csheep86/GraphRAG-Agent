"""P5-H：**版本链读侧**的真图用例（真 Neo4j + 真 PG）。

判据 2 / 3 / 4 / 5（`changes/P5-H/proposal.md` §6）——
本批要修的缺陷一句话：「**一次校正之后，active `kg_version` 变成只含
受影响子图 ∪ 1 跳邻居的新版本 ⇒ 消费侧几乎读空**」。

**为什么必须走真图**：本批改的是 **Cypher 的形状**（``= $kg`` → ``IN $kgs`` +
选中表），而这恰恰是**假 session 挡不住**的那类错 —— 假会话回放的是预设行，
Cypher 写错它照样返回那几行。`test_graph_projection_semantics.py` 里躺着同族事故。
另一半（纯裁决规则）由 `test_version_read_view.py` 用假会话钉。

**版本历史不是手写的**：全部用例都用 P5-G 落地的 ``rename_entity`` / ``merge_entities``
**真的产一次校正**，再由增量重算产出新版本 —— 手写两个版本会让用例退化为
「验自己的夹具」，而不是验写侧与读侧的咬合。

**本地跑法**（本机 Neo4j 常是停的）：

```powershell
docker start graphrag-neo
$env:GRAPH_REAL_NEO4J_URI="bolt://localhost:7687"
$env:GRAPH_REAL_NEO4J_USER="neo4j"
$env:GRAPH_REAL_NEO4J_PASSWORD="ci-graph-pw-2026"
uv run pytest tests/test_version_chain_readers.py -q
```
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models import KgVersion, OntologyAction
from app.db.session import session_scope
from app.schemas.document import GraphNode
from app.services.graphs import GraphService
from app.services.kg.correction import merge_entities, rename_entity
from app.services.kg.version_view import build_read_view

# --------------------------------------------------------------------------- #
# 真图开关（与 tests/test_kg_incremental_rebuild.py 同款：CI 上不可达 ⇒ fail）
# --------------------------------------------------------------------------- #

_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"

_SETTINGS = get_settings()
_ORG_ID = _SETTINGS.default_org_id
_ACTOR_ID = _SETTINGS.default_actor_id


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
def pg_base(real_pg_get_active: None) -> Any:
    """真 PG：一条 ready 基线版本（``ready_at`` 刻意给未来值，见下）。"""
    base = f"p5h-read-{uuid.uuid4().hex[:8]}"
    with session_scope(org_id=_ORG_ID) as session:
        session.add(
            KgVersion(
                org_id=_ORG_ID,
                version=base,
                status="ready",
                source_doc_ids=[],
                entity_count=0,
                relation_count=0,
                # ``get_active`` 按 ready_at DESC 取一条 ⇒ 库里残留的行会抢走
                # active（测试踩过）；给未来值让本用例的行稳定胜出。
                ready_at=datetime.now(UTC),
                trace_id=uuid.uuid4(),
            )
        )
        session.commit()

    yield base

    with session_scope(org_id=_ORG_ID) as session:
        session.execute(
            delete(KgVersion).where(
                KgVersion.org_id == _ORG_ID, KgVersion.version.like(f"{base}%")
            )
        )
        session.execute(
            delete(OntologyAction).where(
                OntologyAction.org_id == _ORG_ID,
                OntologyAction.kg_version.like(f"{base}%"),
            )
        )
        session.commit()


# --------------------------------------------------------------------------- #
# 种子数据
# --------------------------------------------------------------------------- #


def _seed_entities(driver, version: str, rows: list[dict[str, Any]]) -> None:
    with driver.session() as session:
        session.run(
            "UNWIND $rows AS row "
            "MERGE (n:Entity {id: row.id, kg_version: row.kg_version}) "
            "SET n.org_id = row.org_id, n.entity_type = row.entity_type, "
            "    n.canonical_name = row.name, n.confidence = 0.9, "
            "    n.aliases = row.aliases, n.status = 'active', "
            "    n.work_time_system = row.wts",
            rows=rows,
        )


def _seed_relations(driver, version: str, rows: list[dict[str, str]]) -> None:
    with driver.session() as session:
        session.run(
            "UNWIND $rows AS row "
            "MATCH (a:Entity {id: row.source, kg_version: $version}) "
            "MATCH (b:Entity {id: row.target, kg_version: $version}) "
            "MERGE (a)-[r:RELATION {id: row.rid, kg_version: $version}]->(b) "
            "SET r.relation_type = row.relation_type, r.org_id = $org_id",
            rows=rows,
            version=version,
            org_id=str(_ORG_ID),
        )


def _wipe(driver, base: str) -> None:
    with driver.session() as session:
        session.run(
            "MATCH (n) WHERE n.kg_version STARTS WITH $base DETACH DELETE n", base=base
        )
        session.run(
            "MATCH (v:KgVersionMirror) WHERE v.version STARTS WITH $base DELETE v",
            base=base,
        )


def _snapshot_view(graph_service: GraphService, db: Any) -> Any:
    """把当前版本视野快照出来（判据 2/3/5 失败时的第一手诊断信息）。

    注意：它再读一次 PG + 图 ⇒ **只**用于取诊断用的 view，不参与被测路径
    （被测路径内部会各自再算一次，两者的参数结构必须一致）。
    """
    with graph_service._session() as neo:  # noqa: SLF001
        return build_read_view(db=db, session=neo, org_id=_ORG_ID)


# --------------------------------------------------------------------------- #
# 判据 2 / 3：校正之后，未受影响的节点仍读得到；被校正的读到**校正后**的值
# --------------------------------------------------------------------------- #
def test_overview_reads_the_whole_graph_after_a_rename(
    graph_service: GraphService, real_driver, pg_base: str, real_pg_get_active: None
) -> None:
    """**本批的核心判据**：5 个节点改名 1 个 ⇒ 读**仍然**拿得到全部 5 个。

    这是 P5-G 里那条例外断言（``test_new_version_carries_only_the_corrected_subgraph``）
    的**反面**：那条钉「新版本**物理上**不承载全图」，本条钉「读侧**逻辑上**能看到
    全图」。两条必须**共存** —— 删任何一条都会让这个缺陷重新变成"没人说的隐含行为"。
    """
    base = pg_base
    ids = [f"{base}-{suffix}" for suffix in ("e1", "e2", "e3", "e4", "e5")]
    _seed_entities(
        real_driver,
        base,
        [
            {
                "id": entity_id,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "COMPANY",
                "name": f"公司{suffix}",
                "aliases": [],
                "wts": None,
            }
            for entity_id, suffix in zip(
                ids, ("e1", "e2", "e3", "e4", "e5"), strict=True
            )
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": ids[0],
                "target": ids[1],
                "rid": "r12",
                "relation_type": "PARTY_TO",
            },
            {
                "source": ids[1],
                "target": ids[2],
                "rid": "r23",
                "relation_type": "PARTY_TO",
            },
            {
                "source": ids[3],
                "target": ids[4],
                "rid": "r45",
                "relation_type": "PARTY_TO",
            },
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            rename_entity(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=ids[0],
                new_canonical_name="甲公司（已更名）",
                graph_service=graph_service,
            )
            overview = graph_service.fetch_graph_overview(
                org_id=_ORG_ID, trace_id="t-p5h-1", db=db
            )

        seen = {node.id for node in overview.nodes}
        # ① 判据 2：重命名只动了 e1 及其 1 跳邻居 ⇒ 其余节点仍必须读得到
        assert seen == set(ids), (
            f"校正后读图丢失了未受影响的节点：期望 5 个，实读 {len(seen)} 个 "
            f"（缺 {sorted(set(ids) - seen)}）"
        )
        # ② 判据 3：被改名的节点读到的是**新名**，旧名退到别名里
        renamed = next(node for node in overview.nodes if node.id == ids[0])
        assert renamed.name == "甲公司（已更名）"
        with real_driver.session() as neo:
            props = neo.run(
                "MATCH (n:Entity {id: $id, kg_version: $v}) "
                "RETURN properties(n) AS props",
                id=ids[0],
                v=overview.kg_version,
            ).single()
        assert "公司e1" in list(dict(props["props"])["aliases"])
    finally:
        _wipe(real_driver, base)


def test_overview_projects_edges_that_live_in_an_older_version(
    graph_service: GraphService, real_driver, pg_base: str, real_pg_get_active: None
) -> None:
    """P5H-1 的 C 口径（**登记用**）：一端在新版本、另一端只在旧版本的边**仍出边**。

    为什么不选 D6 的另两种候选，写在 `changes/P5-H/proposal.md` §5 P5H-1：
    「两端同版本」会把这类真边判掉（图上会碎成孤岛），「较新者」同理。
    C 口径的安全侧反而更强：被 merge 删掉的节点压根不在选中表里 ⇒ 连不出去。
    """
    base = pg_base
    ids = [f"{base}-{suffix}" for suffix in ("e1", "e2", "e3")]
    _seed_entities(
        real_driver,
        base,
        [
            {
                "id": entity_id,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "COMPANY",
                "name": name,
                "aliases": [],
                "wts": None,
            }
            for entity_id, name in zip(ids, ("甲公司", "乙厂", "丙店"), strict=True)
        ],
    )
    # e1—e2—e3 一条链：校正 e1 ⇒ v1 承载 {e1, e2}（1 跳邻居），e3 只在 base
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": ids[0],
                "target": ids[1],
                "rid": "r12",
                "relation_type": "PARTY_TO",
            },
            {
                "source": ids[1],
                "target": ids[2],
                "rid": "r23",
                "relation_type": "PARTY_TO",
            },
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            rename_entity(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=ids[0],
                new_canonical_name="甲公司（已更名）",
                graph_service=graph_service,
            )
            view = _snapshot_view(graph_service, db)
            overview = graph_service.fetch_graph_overview(
                org_id=_ORG_ID, trace_id="t-p5h-2", db=db
            )

        pairs = {(edge.source, edge.target) for edge in overview.edges}
        assert {node.id for node in overview.nodes} == set(ids)
        # e2(v1) → e3(base)：跨版本边按 C 口径**出边**（登记口径的可观测证据）
        assert (ids[1], ids[2]) in pairs, (
            f"缺跨版本边 e2→e3：实读边={sorted(pairs)}；"
            f"版本链={view.versions}；选中表={dict(sorted(view.selection.items()))}"
        )
    finally:
        _wipe(real_driver, base)


# --------------------------------------------------------------------------- #
# 判据 3 / 5：被 merge 掉的节点读不到，且**不留幽灵边**
# --------------------------------------------------------------------------- #
def test_merged_away_node_and_its_edges_never_reappear(
    graph_service: GraphService, real_driver, pg_base: str, real_pg_get_active: None
) -> None:
    """merge 是 ``DETACH DELETE``（无墓碑）⇒ 删掉的节点**不得**从旧版本被继承回来。

    这条 simultaneously 是判据 5「不连出幽灵路径」的最强形式：幽灵路径的本质是
    「连到一个已经不存在的节点」，这里直接把它连的根也掐掉。
    """
    base = pg_base
    ids = [f"{base}-{suffix}" for suffix in ("e1", "e2", "e3")]
    _seed_entities(
        real_driver,
        base,
        [
            {
                "id": entity_id,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "COMPANY",
                "name": name,
                "aliases": [],
                "wts": None,
            }
            for entity_id, name in zip(
                ids, ("甲公司", "甲公司分公司", "丙店"), strict=True
            )
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": ids[0],
                "target": ids[1],
                "rid": "r12",
                "relation_type": "PARTY_TO",
            },
            {
                "source": ids[1],
                "target": ids[2],
                "rid": "r23",
                "relation_type": "PARTY_TO",
            },
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            merge_entities(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                left_entity_id=ids[0],
                right_entity_id=ids[1],
                graph_service=graph_service,
            )
            view = _snapshot_view(graph_service, db)
            overview = graph_service.fetch_graph_overview(
                org_id=_ORG_ID, trace_id="t-p5h-3", db=db
            )

        seen = {node.id for node in overview.nodes}
        assert ids[1] not in seen, (
            f"被 merge 掉的节点不得靠版本继承复活：实读={sorted(seen)}；"
            f"版本链={view.versions}；选中表={dict(sorted(view.selection.items()))}"
        )
        assert seen == {ids[0], ids[2]}
        # 幽灵边：任何一条边的两端都**不许**涉及已删除节点
        for edge in overview.edges:
            assert ids[1] not in (edge.source, edge.target), (
                f"连出了幽灵边: {edge.source} -> {edge.target}"
            )
    finally:
        _wipe(real_driver, base)


# --------------------------------------------------------------------------- #
# 判据 4：第二条读路径 —— 多跳推理路径（M3 问答链）
# --------------------------------------------------------------------------- #
def test_reasoning_path_stops_at_version_boundary_yet(
    graph_service: GraphService,
    real_driver,
    pg_base: str,
    real_pg_get_active: None,
    real_graph_read_path: None,
) -> None:
    """**已知限制（P5H-6）**：多跳路径**不**跨越版本边界 —— 本用例把这条钉成事实。

    改名 target 是 employee ⇒ 受影响集 = {employee, position}，而 ``clause``
    落在外面 ⇒ 选中表把 ``clause`` 判到**旧**版本上。而 Cypher 的变长路径走的是
    **物理边**：``position@v1`` 与 ``clause@base`` 之间**没有**物理边
    （写侧 P5F-3 刻意不迁移受影响集的边界边）⇒ 链到 position 就断了。

    为什么要把「做不到的部分」也写成用例：**没有这个用例，"推理路径已支持版本
    继承"这句话会被误解成"横跨版本的链也接通了"**。钉住 ⇒ 将来若真接通了，
    本用例会变红 ⇒ 强制回到 ADR-0008 §5 更新口径，而不是悄悄放宽。
    """
    base = pg_base
    # ``EMPLOYEE:`` / ``POSITION:`` 前缀是**确定性派生**的 id 形态，推理链的锚点
    # 过滤（``_is_deterministic_node_id``）与考勤事实查询都以它为据，不能加版本号前缀。
    employee = "EMPLOYEE:E001"
    position = "POSITION:P001"
    clause = "POLICY_CLAUSE:C01"
    _seed_entities(
        real_driver,
        base,
        [
            {
                "id": employee,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "EMPLOYEE",
                "name": "张伟",
                "aliases": [],
                "wts": "标准工时制",
            },
            {
                "id": position,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "POSITION",
                "name": "售后工程师",
                "aliases": [],
                "wts": None,
            },
            {
                "id": clause,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "POLICY_CLAUSE",
                "name": "每月加班不得超过36小时",
                "aliases": [],
                "wts": None,
            },
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": employee,
                "target": position,
                "rid": "r-e-p",
                "relation_type": "HAS_POSITION",
            },
            {
                "source": position,
                "target": clause,
                "rid": "r-p-c",
                "relation_type": "APPLIES_TO",
            },
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            result = rename_entity(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=employee,
                new_canonical_name="张伟（已更正）",
                graph_service=graph_service,
            )
            new_version = result.kg_version
            with graph_service._session() as neo:  # noqa: SLF001
                view = build_read_view(db=db, session=neo, org_id=_ORG_ID)

        nodes = [
            GraphNode(
                id=employee,
                label="Entity",
                canonical_name="张伟",
                kg_version=new_version,
            )
        ]

        assert view.inherits_history is True
        # ① 链的两段都在**同一个物理版本**里（employee 一起被带进新版本是因为它是
        #    position 的 1 跳邻居……这里反过来：改名的是 employee，受影响集 =
        #    employee ∪ {position}，而 clause 落在外面）⇒ 跨版本那段**不连**。
        #    这是本批登记的**已知限制**（P5H-6），见下方 fixture 注释与 ADR-0008 §5。
        assert view.selection[clause] == base  # clause 确实被判到旧版本上
        hops = graph_service.fetch_reasoning_path(
            kg_version=new_version,
            org_id=_ORG_ID,
            question="张伟的加班怎么算",
            nodes=nodes,
            version_view=view,
        )
        assert [hop.target.id for hop in hops] == [], (
            "多跳路径**尚未**支持跨版本续接（P5H-6 登记限制）；若本用例变红，"
            "说明这条限制已被解决 ⇒ 请同步更新 ADR-0008 §5 与 integration-log §11 指针"
        )
    finally:
        _wipe(real_driver, base)


def test_reasoning_path_recovers_after_an_unrelated_correction(
    graph_service: GraphService,
    real_driver,
    pg_base: str,
    real_pg_get_active: None,
    real_graph_read_path: None,
) -> None:
    """「几乎读空」的**真实形态**：校正落在**无关子图**上 ⇒ 推理链整条找不回来。

    构造：在另一处（两家无关公司）做一次 rename。受影响集 = 那两家公司的节点，
    与「员工 → 岗位 → 制度条款」这条推理链毫无交集 ⇒ 新版本里
    **一个相关节点都没有**。

    - 不带视野（改之前的生态）⇒ 推理链**完全空** —— 就是本批要修的缺陷；
    - 带视野 ⇒ 整条链从旧版本继承回来。

    这条比上面的社区用例更能代表生产形态：多跳路径 ⟨员工-岗位-制度条款⟩
    在同一个物理版本里是连通的，所以不需要跨越版本边界也能走完。
    """
    base = pg_base
    employee = "EMPLOYEE:E001"
    position = "POSITION:P001"
    clause = "POLICY_CLAUSE:C01"
    company_a = f"{base}-COMPANY:C901"
    company_b = f"{base}-COMPANY:C902"
    _seed_entities(
        real_driver,
        base,
        [
            {
                "id": employee,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "EMPLOYEE",
                "name": "张伟",
                "aliases": [],
                "wts": "标准工时制",
            },
            {
                "id": position,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "POSITION",
                "name": "售后工程师",
                "aliases": [],
                "wts": None,
            },
            {
                "id": clause,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "POLICY_CLAUSE",
                "name": "每月加班不得超过36小时",
                "aliases": [],
                "wts": None,
            },
            {
                "id": company_a,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "COMPANY",
                "name": "甲公司",
                "aliases": [],
                "wts": None,
            },
            {
                "id": company_b,
                "kg_version": base,
                "org_id": str(_ORG_ID),
                "entity_type": "COMPANY",
                "name": "乙公司",
                "aliases": [],
                "wts": None,
            },
        ],
    )
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": employee,
                "target": position,
                "rid": "r-e-p",
                "relation_type": "HAS_POSITION",
            },
            {
                "source": position,
                "target": clause,
                "rid": "r-p-c",
                "relation_type": "APPLIES_TO",
            },
            {
                "source": company_a,
                "target": company_b,
                "rid": "r-a-b",
                "relation_type": "PARTY_TO",
            },
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            result = rename_entity(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=company_a,
                new_canonical_name="甲公司（已更名）",
                graph_service=graph_service,
            )
            new_version = result.kg_version
            with graph_service._session() as neo:  # noqa: SLF001
                view = build_read_view(db=db, session=neo, org_id=_ORG_ID)

        nodes = [
            GraphNode(
                id=employee,
                label="Entity",
                canonical_name="张伟",
                kg_version=new_version,
            )
        ]
        with_view = graph_service.fetch_reasoning_path(
            kg_version=new_version,
            org_id=_ORG_ID,
            question="张伟的加班怎么算",
            nodes=nodes,
            version_view=view,
        )
        without_view = graph_service.fetch_reasoning_path(
            kg_version=new_version,
            org_id=_ORG_ID,
            question="张伟的加班怎么算",
            nodes=nodes,
        )

        assert view.inherits_history is True
        assert [hop.target.id for hop in with_view] == [position, clause]
        # 缺省零变化：不带视野时这条链路整体读空 —— 这就是本批要修的缺陷
        assert without_view == []
    finally:
        _wipe(real_driver, base)


# --------------------------------------------------------------------------- #
# 判据 4：第三条读路径 —— 考勤合规扫描（M3 确定性数值）
# --------------------------------------------------------------------------- #
def test_compliance_scan_still_sees_employees_outside_the_corrected_subgraph(
    graph_service: GraphService, real_driver, pg_base: str, real_pg_get_active: None
) -> None:
    """合规扫描按**继承视图**扫全公司，而不是只扫被校正的那一小撮员工。

    构造两名员工且**互不为邻居**：`E001` 被改名（连同它 1 跳的排班事实进新版本），
    `E002` 与它无连接 ⇒ 留在旧版本。单版本读 ⇒ 只扫得到 1 人；继承读 ⇒ 2 人。
    """
    base = pg_base
    # 同上：``EMPLOYEE:`` / ``SHIFT:`` 前缀是确定性派生的 id 形态。
    e1 = "EMPLOYEE:E001"
    e2 = "EMPLOYEE:E002"
    shift = "SHIFT:S001"
    employees = [
        {
            "id": e1,
            "kg_version": base,
            "org_id": str(_ORG_ID),
            "entity_type": "EMPLOYEE",
            "name": "张伟",
            "aliases": [],
            "wts": "标准工时制",
        },
        {
            "id": e2,
            "kg_version": base,
            "org_id": str(_ORG_ID),
            "entity_type": "EMPLOYEE",
            "name": "李娜",
            "aliases": [],
            "wts": "标准工时制",
        },
        {
            "id": shift,
            "kg_version": base,
            "org_id": str(_ORG_ID),
            "entity_type": "SHIFT",
            "name": "S001",
            "aliases": [],
            "wts": None,
        },
    ]
    _seed_entities(real_driver, base, employees)
    with real_driver.session() as session:
        session.run(
            "MATCH (n:Entity {id: $id, kg_version: $v}) SET n.date = '2026-10-06', "
            "n.planned_hours = 8.0, n.is_rest_day = 0",
            id=shift,
            v=base,
        )
    _seed_relations(
        real_driver,
        base,
        [
            {
                "source": e1,
                "target": shift,
                "rid": "r-e1-s",
                "relation_type": "HAS_SHIFT",
            }
        ],
    )

    try:
        with session_scope(org_id=_ORG_ID) as db:
            rename_entity(
                db=db,
                org_id=_ORG_ID,
                actor_id=_ACTOR_ID,
                trace_id=uuid.uuid4(),
                entity_id=e1,
                new_canonical_name="张伟（已更改）",
                graph_service=graph_service,
            )
            report = graph_service.scan_attendance_compliance(
                org_id=_ORG_ID, db=db, as_of=None
            )
        # 两名员工都在（E002 从未被本申请影响到 ⇒ 必须从旧版本继承进来）
        assert report.employee_count == 2, (
            f"合规扫描只读到了 {report.employee_count} 名员工（应为 2）"
        )
    finally:
        _wipe(real_driver, base)
