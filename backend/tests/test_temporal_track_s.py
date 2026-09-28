"""Sprint 9 批次 B2：**PoC Track S 判分脚本迁入正式测试集**（`sprint-calendar` §4 CP-T2 强制项）。

原脚本 ``temporal_poc/run_track_s.py`` 在此前是一次性脚本：它靠 LLM **现场抽取**，
结果随模型漂移，也无法进 CI——那样的 3/3 只是一次运气。迁入后做了三处改动：
1. **不调 LLM**：relations 的 ``valid_from`` 直接写死。要验的**不是**抽取（另有
   ``test_extraction_temporal.py``），而是「写入 → 仲裁 → 读侧判分」这条链。
2. **默认零外部依赖**：``conftest`` 刻意把 Neo4j 指向不可达端口以保证 CI 确定性，
   于是这里的判分跑在一层轻薄的**图态记账**上（把仲裁结论应用到内存边列表）。
   想连真机重跑**同一组断言**：设 ``TEMPORAL_TRACK_REAL_URI``（用法见文件末尾）。
3. 判分口径照抄 PoC §2：当前值正确 / as-of 2024-06-01 回溯 / 历史保留 / 自动判失效，
   并像 PoC 一样**重复 3 轮**——单次成功只证明"能跑"。

关于 as-of 的那一项：桩模式下它是 Python 侧重算的，**与 Cypher 不是同一份实现**，
存在"两边语义各走各的"风险 ⇒ 因此必须由真机用例用**真实 Cypher**
（与 :func:`graphs._temporal_view` 逐字符共用同一片段）覆核一遍。
"""

from __future__ import annotations

import os

import pytest

from app.services.kg.temporal import (
    ExpiryPlan,
    TemporalRelation,
    plan_expiries,
)

_COMPANY = "招银金融租赁有限公司"
_LEGAL_REP = "LEGAL_REP"
#: 与 PoC §2 一致：回溯到这个时点应仍能查到旧事实
_AS_OF = "2024-06-01"

#: PoC §2「重复 3 轮」的落点：同一场景跑三轮，区别只有版本号
_ROUNDS = ("v-track-s-1", "v-track-s-2", "v-track-s-3")


def _build_edges(
    version_suffix: str,
) -> tuple[list[TemporalRelation], list[TemporalRelation]]:
    """构造 PoC 语料里的两期事实（**不调 LLM**），返回 ``(第一期, 第二期)``。

    第二期是**变更公告**（"由张三变更为李四"），两句同一天 ⇒ R1 管不到，
    这正是 R2 存在的理由（PoC §4 坑 5：首版只靠 R1，当前值全线阵亡）。
    """
    head = f"sub-{_COMPANY}-{version_suffix}"
    first = TemporalRelation(
        head_id=head,
        tail_id=f"lpr-张三-{version_suffix}",
        relation_type=_LEGAL_REP,
        valid_from="2023-12-31",
        source_document_id="doc-annual-2023",
    )
    # 变更句在原文里的两个 tail：张三在前、李四在后 ⇒ R2 保留后者
    second = [
        TemporalRelation(
            head_id=head,
            tail_id=f"lpr-张三-{version_suffix}",
            relation_type=_LEGAL_REP,
            valid_from="2025-05-01",
            source_document_id="doc-change-2025",
            tail_position=10,
        ),
        TemporalRelation(
            head_id=head,
            tail_id=f"lpr-李四-{version_suffix}",
            relation_type=_LEGAL_REP,
            valid_from="2025-05-01",
            source_document_id="doc-change-2025",
            tail_position=52,
        ),
    ]
    return [first], second


def _apply(
    edges: list[TemporalRelation], plans: list[ExpiryPlan]
) -> list[TemporalRelation]:
    """把封边指令应用到图态上——**写的是 valid_to，不是删除**（历史必须还在）。"""
    closed = {
        (plan.relation.head_id, plan.relation.tail_id, plan.relation.valid_from): plan
        for plan in plans
    }
    applied: list[TemporalRelation] = []
    for edge in edges:
        plan = closed.get((edge.head_id, edge.tail_id, edge.valid_from))
        if plan is None:
            applied.append(edge)
            continue
        applied.append(
            TemporalRelation(
                head_id=edge.head_id,
                tail_id=edge.tail_id,
                relation_type=edge.relation_type,
                valid_from=edge.valid_from,
                valid_to=plan.valid_to,
                source_document_id=edge.source_document_id,
                tail_position=edge.tail_position,
            )
        )
    return applied


def _current(edges: list[TemporalRelation]) -> list[TemporalRelation]:
    return [edge for edge in edges if edge.valid_to is None]


def _as_of(edges: list[TemporalRelation], day: str) -> list[TemporalRelation]:
    """重现 :func:`graphs._temporal_view` 的语义（桩模式专用；真机另有覆核）。"""
    return [
        edge
        for edge in edges
        if edge.valid_from is not None
        and edge.valid_from <= day
        and (edge.valid_to is None or edge.valid_to > day)
    ]


def _single_current(relation_type: str) -> bool:  # noqa: ARG001
    return True


@pytest.mark.parametrize("version", _ROUNDS)
def test_track_s_scorecard_is_three_of_three(version: str) -> None:
    """PoC 判分项在迁入后被机械复算：**当前值 / 历史保留 / 自动失效**各 1/1。"""
    existing, incoming = _build_edges(version)

    # 第一期写入：没有可比旧事实 ⇒ 什么都不该封
    assert (
        plan_expiries(existing=[], incoming=existing, is_single_current=_single_current)
        == []
    )

    # 第二期写入：既要封掉 2023 年的张三（R1），也要在变更句里留下李四（R2）
    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )
    graph_state = _apply(existing + incoming, plans)

    # ① 当前值唯一且正确：李四（张三的两条——2023 年的和变更句里的——都被封口）
    alive = _current(graph_state)
    assert alive == [
        edge for edge in graph_state if edge.tail_id == f"lpr-李四-{version}"
    ]
    assert len(alive) == 1, f"当前法定代表人应只有一个：{[e.tail_id for e in alive]}"

    # ③ 历史保留：2023 年那条没被删，只是被封到 2025-05-01
    first_edge = next(edge for edge in graph_state if edge.valid_from == "2023-12-31")
    assert first_edge.valid_to == "2025-05-01"
    assert len(graph_state) == 3 > len(alive)

    # ④ 自动判失效：**两条规则都被触发过**，且都没有依赖 LLM
    assert {plan.reason for plan in plans} == {"R1", "R2"}


@pytest.mark.parametrize("version", _ROUNDS)
def test_as_of_query_returns_the_old_fact(version: str) -> None:
    """PoC 判分项②：as-of 2024-06-01 应回溯到张三。

    这条同时也是对「旧事实**不许物理删除**」的直接断言。
    """
    existing, incoming = _build_edges(version)
    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )
    graph_state = _apply(existing + incoming, plans)

    back_then = _as_of(graph_state, _AS_OF)
    assert [edge.tail_id for edge in back_then] == [f"lpr-张三-{version}"]


# --------------------------------------------------------------------------- #
# 真机覆核（默认跳过）：用**真实 Cypher** 验证上面 Python 侧重算的 as-of 语义，
# 顺带拦我自己拼出来的 Cypher 语法错误——那正是桩模式盖不住的风险。
# --------------------------------------------------------------------------- #

_REAL_URI_ENV = "TEMPORAL_TRACK_REAL_URI"
#: 凭据也要单独给：``conftest`` 为中和外部依赖把 ``NEO4J_PASSWORD`` 置空了，
#: 真机连接只能靠显式注入（与 conftest「要真连就用 monkeypatch 显式开启」同口径）
_REAL_PASSWORD_ENV = "TEMPORAL_TRACK_REAL_PASSWORD"


def _real_uri() -> str:
    return os.getenv(_REAL_URI_ENV, "").strip()


def _real_driver():  # noqa: ANN202 - 第三方类型
    """显式开了环境变量才连真机。

    连接过程中的异常**原样抛出**：开关一旦打开，意图就是"这次要真的连真机"，
    此时"连不上还装作没开"会把 CI 的绿变成**假绿**——那正是 PoC §2
    「用数据而不是感觉决定路线」要防的东西。
    """
    uri = _real_uri()
    if not uri:
        return None
    from neo4j import GraphDatabase

    from app.core.config import get_settings

    settings = get_settings()
    driver = GraphDatabase.driver(
        uri,
        auth=(
            settings.neo4j_user,
            os.getenv(_REAL_PASSWORD_ENV) or settings.neo4j_password or "",
        ),
    )
    driver.verify_connectivity()
    return driver


# local_only：需 `TEMPORAL_TRACK_REAL_URI` + 真机口令，CI 上无凭据 ⇒ 必然 skip。
# 标记后 CI 用单独一步跑它并打印 skip 原因，避免「谁都说跑过、其实无人能复算」。
@pytest.mark.local_only
@pytest.mark.skipif(not _real_uri(), reason=f"设 {_REAL_URI_ENV} 后才会连接真机 Neo4j")
@pytest.mark.parametrize("round_index", _ROUNDS)
def test_as_of_query_against_real_neo4j(round_index: str) -> None:
    """同一份语料、同一套判据，跑在真 Neo4j 上——**自己写数据，再自我判分**。

    这里的 Cypher **逐字符复用** :func:`graphs._temporal_view`，所以它同时是：
    ① as-of 语义的覆核（桩模式那版 Python 重算不被当成最终证据）；
    ② 那段拼接出来的 Cypher 的**语法 / 参数 / 参数个数**校验——这是桩模式盖不住的风险。
    """
    from uuid import uuid4

    from app.core.config import get_settings
    from app.services.graphs import GraphService, _temporal_view
    from app.services.kg import ThreeStageKgBuilder
    from app.services.kg.builder import KgBuildRequest, KgDocumentRef

    driver = _real_driver()
    assert driver is not None, f"{_REAL_URI_ENV} 已设置但连不上"

    settings = get_settings()
    org_id = settings.default_org_id
    # PoC §2「重复 3 轮」：每轮独占一套节点（版本号隔离），互不串味
    version = f"{round_index}-real-{uuid4().hex[:8]}"
    graph = GraphService.instance()
    original = graph._driver
    graph._driver = driver

    def _entities(person: str) -> list[dict]:
        return [
            {
                "id": "ent_org",
                "canonical_name": _COMPANY,
                "entity_type": "ORG",
                "confidence": 0.9,
            },
            {
                "id": f"ent_{person}",
                "canonical_name": person,
                "entity_type": "LEGAL_PERSON",
                "char_start": 40,
                "confidence": 0.9,
            },
        ]

    def _relations(person: str, valid_from: str) -> list[dict]:
        return [
            {
                "id": "rel_rep",
                "source_entity_id": "ent_org",
                "target_entity_id": f"ent_{person}",
                "relation_type": _LEGAL_REP,
                "evidence": f"法定代表人为{person}",
                "confidence": 0.9,
                "valid_from": valid_from,
                "valid_to": None,
            }
        ]

    builder = ThreeStageKgBuilder(policy_lookup=lambda _rt: True)
    cypher = (
        """
MATCH (:Subject)-[r:LEGAL_REP]->(p:LegalPerson)
WHERE r.org_id = $org_id AND r.kg_version = $version"""
        + _temporal_view("r")
        + """
RETURN p.name AS name, r.valid_from AS valid_from, r.valid_to AS valid_to
ORDER BY r.valid_from
"""
    )
    try:
        for person, valid_from in (("张三", "2023-12-31"), ("李四", "2025-05-01")):
            builder.build(
                KgBuildRequest(
                    org_id=org_id,
                    version=version,
                    entities=_entities(person),
                    relations=_relations(person, valid_from),
                    trace_id=uuid4(),
                    document=KgDocumentRef(doc_id=uuid4()),
                )
            )

        with driver.session(database=settings.neo4j_database) as session:
            now_names = [
                row["name"]
                for row in session.run(
                    cypher, org_id=str(org_id), version=version, as_of=None
                )
            ]
            back_names = [
                row["name"]
                for row in session.run(
                    cypher, org_id=str(org_id), version=version, as_of=_AS_OF
                )
            ]
    finally:
        with driver.session(database=settings.neo4j_database) as session:
            session.run(
                "MATCH (n {kg_version: $version}) DETACH DELETE n", version=version
            )
        graph._driver = original
        driver.close()

    assert now_names == ["李四"], f"当前法定代表人应只剩李四，实际 {now_names}"
    assert back_names == ["张三"], f"as-of {_AS_OF} 应回溯到张三，实际 {back_names}"
