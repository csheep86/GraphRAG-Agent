"""G-9 / DR-B11：图谱侧（Neo4j）跨 org 隔离——**真实 Neo4j** + T1 补齐（documents / qa_logs / storage_key）。

**为什么必须新增本文件**（基线 §169 / §303 的明令）：图谱侧隔离此前**只有打桩用例**
（`tests/test_agent_fail_closed.py` 用 monkeypatch 替掉整个 `GraphService`），
而 CI **没有 `neo4j` service** ⇒ 基线原话：「**在 CI 起 Neo4j 之前，该部分不得声称
"已由 CI 验证"，须独立环境留证**」。留证不能复算，故本批做两件事：

1. **CI 起真 Neo4j**（`GRAPH_REAL_NEO4J_*` 三个开关 + `neo4j` service），
   并由 :func:`test_g9_0_ci_really_has_neo4j_service` **静态盯住**——
   少了它，下面的真图用例会在 CI 上**静默 skip**，绿得毫无意义（纪律 **R-9**）；
2. **真图用例**：在真 Neo4j 的**同一个 `kg_version` 里写入两个 org 的节点**，
   验 fail-closed 校验、应用层过滤、以及问答链路的 403。

**刻意保留的诚实一条**（:func:`test_g9_5_raw_cypher_can_read_across_orgs`）：
Neo4j 社区版**没有 RLS**，裸 Cypher 直读**确实能**读到别的 org 的节点（同版本即可）。
DR-B11 的原话是「应用层过滤是**唯一**防线（不是冗余防线）」——
本文件把这件事**断言成事实**，免得日后有人把「G-9 绿」读成「图谱侧有强隔离」。

**T1 的四张对象**：`documents`（列表口径）、`qa_logs`（数据层，裸连接）、
`storage_key`（存储层跨 org key）；`audit_log` 由 P1-C 的
`tests/test_audit.py:163` 覆盖，本文件不重复。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import QaLog
from app.db.session import session_scope
from app.schemas.agent import AgentQueryRequest
from app.services.agents import AgentService, AgentTenantLeakError
from app.services.graphs import GraphService, KgVersion
from app.storage import StorageKeyError, build_storage_key, get_storage

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
CI_FILE = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"

#: 真图用例的连接开关（**刻意不用** ``NEO4J_URI``——conftest 把它指向不可达端口，
#: 让绝大多数用例确定性降级；这里必须**单独开一条**才不会波及那上千条用例）
_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"

#: A / B 两个租户（刻意**不用** conftest 的默认租户，避免与脚手架默认值重合）
ORG_A = UUID("00000000-0000-4000-8000-0000000000a1")
ORG_B = UUID("00000000-0000-4000-8000-0000000000b1")


# --------------------------------------------------------------------------- #
# 判据 0：**静态**守卫——CI 必须真有 Neo4j（否则下面的用例只是装饰）
# --------------------------------------------------------------------------- #


def test_g9_0_ci_really_has_neo4j_service() -> None:
    """CI 的 backend job **必须**起 `neo4j`，且连接开关与口令自洽。

    为什么连编排文件都要判：本文件的真图用例在**连不上 Neo4j 时会 skip**——
    本地没起图库是常态，skip 才是友好行为。于是存在一条**恒绿路径**：
    把 CI 的 `neo4j` service 删掉（或改坏口令），用例全体 skip，CI 全绿，
    而基线 §169 要的「由 CI 真验」**从头到尾没发生过**。本条就是堵它的：

    1. backend job 声明了 `neo4j` service；
    2. job env 设了 `GRAPH_REAL_NEO4J_URI`（真图用例靠它连，缺了 ⇒ skip）；
    3. `neo4j` 的 image tag == `deploy/docker-compose.yml` 的 tag
       （CI 与生产跑不同版本的图库 ⇒ 等于在另一个产品上验隔离）；
    4. service 的 `NEO4J_AUTH` 口令 == job env 的 `GRAPH_REAL_NEO4J_PASSWORD`
       （**两处各写一个值**是最容易犯的错：service 起得来、用例却永远连不上，
        表现为"图谱用例全体 skip"，与本条第 1 条被破坏的症状**一样绿**）。

    ⚠️ 本条只盯 CI 的**声明**，运行时是否真连上由 :func:`_real_graph_env` 在 CI 上
    以 `pytest.fail`（而非 skip）兜住。
    """
    workflow = yaml.safe_load(CI_FILE.read_text(encoding="utf-8")) or {}
    job = (workflow.get("jobs") or {}).get("backend")
    assert isinstance(job, dict), f"{CI_FILE.name} 无 backend job"

    services = job.get("services") or {}
    assert "neo4j" in services, (
        f"{CI_FILE.name} 的 backend job 没有 neo4j service ⇒ "
        "图谱侧用例会在 CI 上全体 skip（不是通过），基线 §169 的『由 CI 真验』从未发生"
    )

    job_env = job.get("env") or {}
    assert str(job_env.get(_REAL_URI_ENV, "")).strip(), (
        f"{CI_FILE.name} 未设 {_REAL_URI_ENV} ⇒ 真图用例连不上 ⇒ 静默 skip"
    )

    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    compose_neo4j = (compose.get("services") or {}).get("neo4j") or {}
    ci_tag = str(services["neo4j"].get("image", ""))
    deploy_tag = str(compose_neo4j.get("image", ""))
    assert ci_tag and ci_tag == deploy_tag, (
        f"CI 的 neo4j tag {ci_tag!r} 与 {COMPOSE.name} 的 {deploy_tag!r} 不一致 ⇒ "
        "两侧跑的不是同一个图库版本"
    )

    auth = str((services["neo4j"].get("env") or {}).get("NEO4J_AUTH", ""))
    assert auth.startswith("neo4j/"), (
        f"NEO4J_AUTH 格式应为 'neo4j/<password>'，实际 {auth!r}"
    )
    auth_password = auth.split("/", 1)[1]
    env_password = str(job_env.get(_REAL_PASSWORD_ENV, ""))
    assert auth_password == env_password, (
        f"service 的 NEO4J_AUTH 口令与 job env 的 {_REAL_PASSWORD_ENV} 不一致 ⇒ "
        "Neo4j 起得来但真图用例永远连不上（症状同样是全体 skip，极具迷惑性）"
    )


# --------------------------------------------------------------------------- #
# 真图夹具
# --------------------------------------------------------------------------- #


def _real_graph_env() -> tuple[str, str, str]:
    """取真 Neo4j 连接三元组；**CI 上不可达 ⇒ fail，本地未设 ⇒ skip**。

    为什么 CI 上是 fail 而不是 skip：见 :func:`test_g9_0_ci_really_has_neo4j_service`
    ——skip 会让"没在验"和"验过了"在 CI 日志里长得一模一样。
    """
    uri = os.environ.get(_REAL_URI_ENV, "").strip()
    user = os.environ.get(_REAL_USER_ENV, "").strip() or "neo4j"
    password = os.environ.get(_REAL_PASSWORD_ENV, "").strip()
    missing = "未设 GRAPH_REAL_NEO4J_URI / GRAPH_REAL_NEO4J_PASSWORD"
    if not uri or not password:
        if os.environ.get("CI"):
            pytest.fail(
                f"{missing} ⇒ CI 上真图用例连不上图库，这是**门禁失效**不是环境问题"
                "（本地无 Neo4j 时本用例会 skip）"
            )
        pytest.skip(f"{missing}（本地无 Neo4j ⇒ 真图用例跳过；CI 上为 fail）")
    return uri, user, password


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
    GraphService.reset()  # 单例里可能缓存着上一个（不可达的）driver
    try:
        yield GraphService.instance()
    finally:
        GraphService.reset()


@pytest.fixture
def two_org_kg_version(real_driver):
    """在同一个 `kg_version` 里写入 **A / B 两个 org** 的 `:Entity` 节点。

    每次用一个**唯一版本号** ⇒ 重跑 / 并发互不污染；用例结束 `DETACH DELETE` 清干净。
    """
    version = f"g9-{uuid4().hex}"
    node_a = f"{version}-a"
    node_b = f"{version}-b"

    def _seed(rows: list[dict[str, str]]) -> None:
        with real_driver.session() as session:
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n:Entity {id: row.id, kg_version: row.kg_version}) "
                "SET n.org_id = row.org_id, "
                "    n.entity_type = 'COMPANY', "
                "    n.canonical_name = row.name",
                rows=rows,
            )

    def _wipe() -> None:
        with real_driver.session() as session:
            session.run(
                "MATCH (n {kg_version: $version}) DETACH DELETE n", version=version
            )

    try:
        yield version, node_a, node_b, _seed
    finally:
        _wipe()


# --------------------------------------------------------------------------- #
# 判据 1 / 2：fail-closed 校验（真图）
# --------------------------------------------------------------------------- #


def test_g9_1_leak_detected_when_other_org_nodes_share_version(
    graph_service: GraphService, two_org_kg_version: tuple
) -> None:
    """同 `kg_version` 混入 B 的节点 ⇒ `validate_kg_version_tenant_boundary(A)` **False**。

    这是 ADR-0003 §4 的 fail-closed 校验：**Cypher 已经带 org 过滤了，仍要独立再验一次**
    ——防的是「有人把跨租户节点写进了同一版本」这种数据质量事故被过滤掩盖。
    """
    version, node_a, node_b, seed = two_org_kg_version
    seed(
        [
            {
                "id": node_a,
                "kg_version": version,
                "org_id": str(ORG_A),
                "name": "A 公司",
            },
            {
                "id": node_b,
                "kg_version": version,
                "org_id": str(ORG_B),
                "name": "B 公司",
            },
        ]
    )

    clean = graph_service.validate_kg_version_tenant_boundary(
        kg_version=version, current_org_id=ORG_A
    )
    assert clean is False, (
        f"真图里 {version} 混有 {ORG_B} 的节点，fail-closed 校验却说「干净」⇒ "
        "跨租户子图会被当成正常结论消费（数据质量事故）"
    )


def test_g9_2_clean_when_version_has_only_own_org_nodes(
    graph_service: GraphService, two_org_kg_version: tuple
) -> None:
    """同版本**只有**本 org 节点 ⇒ True（**不误报**）。

    与上一条同价：只验「检出泄漏」不验「不误报」，会诱导实现退化成
    「一律判泄漏」——那是把合法租户全部拒答，另一种事故。
    """
    version, node_a, _node_b, seed = two_org_kg_version
    seed(
        [{"id": node_a, "kg_version": version, "org_id": str(ORG_A), "name": "A 公司"}]
    )

    assert (
        graph_service.validate_kg_version_tenant_boundary(
            kg_version=version, current_org_id=ORG_A
        )
        is True
    )


# --------------------------------------------------------------------------- #
# 判据 3：应用层过滤是**唯一**防线（DR-B11）
# --------------------------------------------------------------------------- #


def test_g9_3_application_filter_excludes_other_org_nodes(
    graph_service: GraphService, two_org_kg_version: tuple
) -> None:
    """带 `org_id=A` 的图谱查询**不得**返回 B 的节点。

    DR-B11 的原话：图谱侧**没有 RLS** ⇒ 应用层过滤是**唯一**防线（不是冗余防线）。
    故这条不是"顺便验一下过滤"，而是**唯一那道防线本身**。
    """
    version, node_a, node_b, seed = two_org_kg_version
    seed(
        [
            {
                "id": node_a,
                "kg_version": version,
                "org_id": str(ORG_A),
                "name": "A 公司",
            },
            {
                "id": node_b,
                "kg_version": version,
                "org_id": str(ORG_B),
                "name": "B 公司",
            },
        ]
    )

    nodes, _edges, _truncated = graph_service.fetch_all_subgraph(
        kg_version=version, org_id=ORG_A
    )
    visible = {node.id for node in nodes}
    assert node_a in visible, f"连本 org 的节点都没查到（{visible}）⇒ 用例自身失效"
    assert node_b not in visible, (
        f"应用层过滤把 {ORG_B} 的节点带回了 A 的查询结果（{visible}）⇒ "
        "DR-B11 的唯一防线破口"
    )


# --------------------------------------------------------------------------- #
# 判据 4：问答链路 fail-closed（**真图**泄漏 ⇒ AgentTenantLeakError）
# --------------------------------------------------------------------------- #


def test_g9_4_agent_query_refuses_on_real_graph_leak(
    graph_service: GraphService,
    two_org_kg_version: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真图泄漏 ⇒ 问答**必须**抛 `AgentTenantLeakError`（路由层转 403 `KG_TENANT_LEAK`）。

    与既有 `tests/test_agent_fail_closed.py` 的分工：那边把 `GraphService` **整个打桩**，
    验的是"服务层分支与路由层映射"；这边**只桩 LLM 与 active 版本**，图谱走**真库**，
    验的是"真图真泄漏时这套链路真的会拦"。

    ⚠️ 这里的「泄漏」是**故意造出来的数据事故**（同版本写两个 org），不是产品缺陷。
    """
    version, node_a, node_b, seed = two_org_kg_version
    seed(
        [
            {
                "id": node_a,
                "kg_version": version,
                "org_id": str(ORG_A),
                "name": "A 公司",
            },
            {
                "id": node_b,
                "kg_version": version,
                "org_id": str(ORG_B),
                "name": "B 公司",
            },
        ]
    )
    # active 版本指向刚造出来的那个版本（PG 侧的 conftest 桩是 "v-test"，与真图无关）
    monkeypatch.setattr(
        GraphService,
        "fetch_active_kg_version",
        lambda _self, **_kwargs: KgVersion(version=version, scope="global"),
    )
    AgentService.reset()
    try:
        with pytest.raises(AgentTenantLeakError, match="跨租户子图泄漏"):
            asyncio.run(
                AgentService.instance().query(
                    request=AgentQueryRequest(question="A 公司与 B 公司是什么关系？"),
                    org_id=ORG_A,
                    trace_id="trace-g9-4",
                )
            )
    finally:
        AgentService.reset()


# --------------------------------------------------------------------------- #
# 判据 5：**诚实登记**——裸 Cypher 直读确实能跨租户（图谱侧无 RLS）
# --------------------------------------------------------------------------- #


def test_g9_5_raw_cypher_can_read_across_orgs(
    real_driver, two_org_kg_version: tuple
) -> None:
    """**反向事实**：不带 org 过滤的裸 Cypher **能**读到别的 org 的节点。

    这条断言的是**弱点**而不是能力：Neo4j 社区版没有 RLS，同一个 `kg_version`
    里谁的节点都能查出来。把它写成用例，是为了让「G-9 绿」**不被误读**成
    「图谱侧有强隔离」——隔离强度弱于 PG 侧（PG 有 RLS + `FORCE`），
    靠的是应用层过滤（判据 3）+ fail-closed 校验（判据 1）两道**软件**防线。

    ⚠️ 若哪天图谱侧也上了强隔离（企业版 / 分库），本条会红——那时应当**更新本条**
    并同步基线 DR-B11 行，而不是删掉它。
    """
    version, _node_a, node_b, seed = two_org_kg_version
    seed(
        [
            {
                "id": f"{version}-a",
                "kg_version": version,
                "org_id": str(ORG_A),
                "name": "A",
            },
            {"id": node_b, "kg_version": version, "org_id": str(ORG_B), "name": "B"},
        ]
    )

    with real_driver.session() as session:
        leaked = [
            row["id"]
            for row in session.run(
                "MATCH (n:Entity {kg_version: $version}) "
                "WHERE properties(n)['org_id'] <> $org "
                "RETURN n.id AS id",
                version=version,
                org=str(ORG_A),
            )
        ]

    assert node_b in leaked, (
        "裸 Cypher 读不到别的 org 的节点 ⇒ 图谱侧可能已经具备库级隔离。"
        "若属实，请更新基线 DR-B11 与本条（那是好消息，但必须落到文档里）"
    )


# --------------------------------------------------------------------------- #
# T1 补齐：`qa_logs` / `storage_key` / `documents`
# --------------------------------------------------------------------------- #


def test_g9_t1_qa_logs_other_org_rows_invisible() -> None:
    """`qa_logs`：A 的身份**看不到** B 的问答留痕（RLS + 应用层过滤）。

    **刻意用裸连接**（`set_config` + SQLAlchemy `Session`，**不**走 `session_scope`）：
    conftest 有「默认租户绑定」脚手架，走 `Session` 的断言会被它糊弄
    （与 G-26 判据 3 同款理由）。

    ⚠️ `qa_logs` **没有 API 路由**（只在服务 / 数据层存在）⇒ T1 只能在数据层验，
    这一点登记在 `changes/P3-B/proposal.md` §0，不是偷懒。
    """
    inserted: dict[str, UUID] = {}
    for org in (ORG_A, ORG_B):
        with session_scope(org_id=org) as session:
            row = QaLog(
                org_id=org,
                question_hash="a" * 64,
                answer_hash="b" * 64,
                citation_count=0,
                refused=False,
                kg_version="g9-t1",
                trace_id=uuid4(),
            )
            session.add(row)
            session.commit()
            inserted[str(org)] = row.id

    ids = list(inserted.values())
    engine = create_engine(get_settings().database_url)
    try:
        with Session(engine) as session:
            session.execute(
                text("SELECT set_config('app.current_org', :org, true)"),
                {"org": str(ORG_A)},
            )
            visible = {
                row[0]
                for row in session.execute(
                    select(QaLog.id, QaLog.org_id).where(QaLog.id.in_(ids))
                )
            }
        assert visible == {inserted[str(ORG_A)]}, (
            f"A 的身份看到了不属于自己的 qa_logs（{visible}）⇒ 跨租户越权"
        )
        # 反向对照：换成 B 的身份 ⇒ **只**见 B 的行（换租户不串号）
        with Session(engine) as session:
            session.execute(
                text("SELECT set_config('app.current_org', :org, true)"),
                {"org": str(ORG_B)},
            )
            visible_b = {
                row[0]
                for row in session.execute(
                    select(QaLog.id, QaLog.org_id).where(QaLog.id.in_(ids))
                )
            }
        assert visible_b == {inserted[str(ORG_B)]}, (
            f"换成 B 的身份后看到的是 {visible_b} ⇒ 租户串号"
        )
    finally:
        engine.dispose()
        for org in (ORG_A, ORG_B):
            with session_scope(org_id=org) as session:
                session.execute(delete(QaLog).where(QaLog.id.in_(ids)))
                session.commit()


def test_g9_t1_storage_key_cross_org_read_rejected() -> None:
    """`storage_key`：拿 **B 的**存储键以 A 的身份读 ⇒ `StorageKeyError`。

    ADR-0003 §3.5：键形如 `{org_id}/{doc_id}/{hash}`，读取时**校验前缀与 org 一致**
    （`app/storage/local_fs.py:54-58`）。`qa_logs` 与它一样**没有 API 路由** ⇒ 存储层验。
    """
    storage = get_storage()
    key_a = build_storage_key(org_id=ORG_A, doc_id=uuid4(), filename_hash="a" * 64)
    key_b = build_storage_key(org_id=ORG_B, doc_id=uuid4(), filename_hash="b" * 64)
    storage.put(key_a, b"own-org-bytes")
    storage.put(key_b, b"other-org-bytes")
    try:
        # 正向对照：自己 org 的键读得到（否则"拒绝"可能只是键根本不存在）
        assert storage.get(key_a, org_id=ORG_A) == b"own-org-bytes"
        with pytest.raises(StorageKeyError, match="越权"):
            storage.get(key_b, org_id=ORG_A)
    finally:
        storage.delete(key_a)
        storage.delete(key_b)


def test_g9_t1_documents_list_excludes_other_org(
    client, dev_headers: dict[str, str], cross_tenant_headers: dict[str, str]
) -> None:
    """`documents`：**列表**口径——B 的列表里**不含** A 的文档。

    与既有 `tests/test_documents.py:147`（**详情** 403）互补，不是重复：
    列表是**批量读**路径，漏过滤会一次性吐出全部租户；它不走详情那条 403 分支。
    """
    pdf = (
        "合同.pdf",
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n",
        "application/pdf",
    )
    uploaded = client.post(
        "/api/v1/documents/upload", files={"file": pdf}, headers=dev_headers
    )
    assert uploaded.status_code == 200, uploaded.text
    task_id = uploaded.json()["task_id"]

    own = client.get("/api/v1/documents?page=1&page_size=50", headers=dev_headers)
    assert own.status_code == 200, own.text
    own_ids = [item["id"] for item in own.json()["items"]]
    assert task_id in own_ids, "正向对照失败：连本租户的列表里都没有它 ⇒ 用例自身失效"

    other = client.get(
        "/api/v1/documents?page=1&page_size=50", headers=cross_tenant_headers
    )
    assert other.status_code == 200, other.text
    other_ids = [item["id"] for item in other.json()["items"]]
    assert task_id not in other_ids, (
        f"B 的文档列表里出现了 A 的文档 {task_id} ⇒ 列表路径未做 org 过滤"
    )
