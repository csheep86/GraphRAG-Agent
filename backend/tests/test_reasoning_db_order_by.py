"""P6-V1：候选路径**两侧排序口径**的对齐（`_cypher_paths()` ↔ `_select_shortest_path`）。

来源：`changes/P6-U/13-as-of-evidence-rank.md` §遗留 —— Cypher 侧
``ORDER BY (prio, size(rels), ids[-1]) LIMIT 400`` 与 Python 侧 7 维精排键
**并不一致**；真机候选最多 165 行、够不着 400 ⇒ 一直没触发。

为什么这组用例**必须**存在（三条钉死，否则下一次又漂回去）：

1. **Cypher 侧是截断，不是排序**：``LIMIT`` 一截断，Python 侧精排的对象就只剩
   「幸存者」。故 DB 侧 ``ORDER BY`` 必须是 Python 键的**连续前缀**——
   跳维（做 1,2,3,5 而漏 4）比不做更糟：它会把真胜者排到 400 之外；
2. **不许"改一边就完了"**：两侧口径必须落在**同一份常量**上并被机械断言，
   不能靠模块注释互相保证（注释正是上一轮写错的那处）；
3. **判据要能复跑**：>400 的对照用例跑的是**生产 Cypher 本身**，只换 ``ORDER BY``
   子句（旧键表达式以常量形式登记在 :data:`_DB_TERMINAL_TIER_LEGACY_EXPR`）。
   自己另写一段 Cypher 去"模拟"DB 侧，等价于重犯 P6-U 探针的老错。
"""

from __future__ import annotations

import os
import re
from typing import Any
from uuid import uuid4

import pytest

from app.schemas.document import GraphNode
from app.services.kg.version_view import VersionReadView
from app.services.reasoning import (
    _DB_TERMINAL_TIER_EXPR,
    _DB_TERMINAL_TIER_LEGACY_EXPR,
    _PATH_CANDIDATE_LIMIT,
    _TERMINAL_RANK,
    ALL_TERMINAL_TYPES,
    DB_ORDER_BY_DIMENSIONS,
    HUB_EMPLOYEE_TYPE,
    PATH_SORT_DIMENSIONS,
    PRIORITY_TERMINAL_TYPES,
    TERMINAL_PRIORITY_TYPE,
    _cypher_paths,
    _select_shortest_path,
    build_reasoning_path,
)

# --------------------------------------------------------------------------- #
# 真图夹具
#
# 与 `tests/test_guardrails_graph.py` 的 `_real_graph_env` / `real_driver` 同源。
# 本处**刻意没有**去动那份共享夹具：本批是小修，为它改 conftest 会波及上千条
# 用例；等真图用例出现**第三处**再一并抽到 `conftest.py`（登记，不蔓延）。
# --------------------------------------------------------------------------- #
_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"


def _real_graph_env() -> tuple[str, str, str]:
    """真 Neo4j 连接三元组；**CI 上不可达 ⇒ fail（不是 skip）**。

    为什么 CI 上必须是 fail：skip 会让「没在验」和「验过了」在 CI 日志里长得
    一模一样——那正是恒绿失效。
    """
    uri = os.environ.get(_REAL_URI_ENV, "").strip()
    user = os.environ.get(_REAL_USER_ENV, "").strip() or "neo4j"
    password = os.environ.get(_REAL_PASSWORD_ENV, "").strip()
    if not uri or not password:
        if os.environ.get("CI"):
            pytest.fail(
                f"未设 {_REAL_URI_ENV} / {_REAL_PASSWORD_ENV} ⇒ CI 上真图用例连不上"
                "图库，这是**门禁失效**不是环境问题"
            )
        pytest.skip(f"未设 {_REAL_URI_ENV} / {_REAL_PASSWORD_ENV}（本地无 Neo4j）")
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


# --------------------------------------------------------------------------- #
# 判据 1：两侧排序键的**逐维登记**与前缀性质
# --------------------------------------------------------------------------- #
def test_db_dimensions_are_a_continuous_prefix_of_python_dims() -> None:
    """DB 侧参与的维必须是 Python 键的**连续前缀**——**跳维比不做更糟**。

    Cypher 侧 ``LIMIT`` 是截断：只要 DB 键是前缀，被截掉的候选就一定排在保留者
    之后（排序的加粗），真胜者不会被截；一旦跳维，第 k+1 维的次序与 Python 侧
    不同 ⇒ 真胜者可能被排到 400 之外，而这在候选 < 400 时**完全看不出来**。
    """
    assert DB_ORDER_BY_DIMENSIONS, "DB 侧一个维都不排 ⇒ 截断等于随机抽样"
    assert (
        DB_ORDER_BY_DIMENSIONS == PATH_SORT_DIMENSIONS[: len(DB_ORDER_BY_DIMENSIONS)]
    ), (
        f"DB 侧排序维 {DB_ORDER_BY_DIMENSIONS} 不是 Python 键 "
        f"{PATH_SORT_DIMENSIONS} 的连续前缀 ⇒ 截断会丢真胜者"
    )
    # 不许全量照搬：那意味着 Cypher 里又写了一份 _temporal_verdict（同一判断散写
    # 成两份，正是 _cypher_paths() docstring 记着的事故源）。
    assert len(DB_ORDER_BY_DIMENSIONS) < len(PATH_SORT_DIMENSIONS), (
        "DB 侧把 7 维全搬进 Cypher ⇒ 时序三值语义在 Cypher 里有了第二份实现"
    )


def test_cypher_renders_the_registered_order_by_expression() -> None:
    """Cypher 里**真的**用了登记的那个档位表达式（防止只改常量、不改查询）。"""
    query = _cypher_paths()
    assert _DB_TERMINAL_TIER_EXPR in query, (
        "Cypher 的 ORDER BY 用的是别的表达式 ⇒ 登记与实现已经漂移"
    )
    assert _DB_TERMINAL_TIER_LEGACY_EXPR not in query, (
        "Cypher 仍在用修复前的旧档位表达式（旧键把 LEGAL_PERSON 也算优先终点）"
    )


def test_cypher_order_by_references_only_supplied_params() -> None:
    """``ORDER BY`` 里引用的每个 ``$参数`` 都必须被生产代码真的下发。

    这条是「两侧同一份常量」的机械版：档位表达式引用 ``$prio_type`` /
    ``$terminal_rank``，而它们的值由 :func:`build_reasoning_path` 从
    ``TERMINAL_PRIORITY_TYPE`` / ``_TERMINAL_RANK`` 取——不是 Cypher 里硬写类型名。
    """
    query = _cypher_paths()
    sent = _capture_path_params()
    referenced = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", query))
    missing = referenced - set(sent)
    assert not missing, f"Cypher 引用了没有下发的参数：{sorted(missing)}"


def test_db_sort_params_come_from_the_same_constants_as_python() -> None:
    """DB 侧档位的**实参**与 Python 侧精排读的是同一份常量。

    这是本批真正的修法：不是"把 Python 的口径抄进 Cypher"，而是让 Cypher 去读
    Python 的常量。抄一份类型表，抄的当天一致，第二天就漂。
    """
    sent = _capture_path_params()
    assert sent["prio_type"] == TERMINAL_PRIORITY_TYPE
    assert sent["terminal_rank"] == dict(_TERMINAL_RANK)
    assert sent["terminal_rank_default"] == len(_TERMINAL_RANK)
    # 旧参数**不再**下发（它带着"LEGAL_PERSON 也算优先"的过期口径）
    assert "prio_types" not in sent


def test_python_side_gives_no_priority_to_affiliation_terminal() -> None:
    """事实登记：Python 侧第 1 维**只**认 ``POLICY_CLAUSE``。

    ``LEGAL_PERSON`` 并不在 :data:`_TERMINAL_RANK` 里 ⇒ 它从未拿到过排序优先权，
    而旧 Cypher 键把 :data:`PRIORITY_TERMINAL_TYPES`（含它）当优先终点。
    P6-V1 的对齐方向是 **Cypher 向 Python 对齐**——不是反过来给 Python 加优先权，
    那会动 P6-V 刚接线的关联方域既有排序。本条把方向钉死。
    """
    assert "LEGAL_PERSON" in PRIORITY_TERMINAL_TYPES  # 前提：旧键确实把它算优先
    assert "LEGAL_PERSON" not in _TERMINAL_RANK  # 前提：Python 侧没给它档位

    affiliation = _row(
        ["EMPLOYEE:E001", "POSITION:P1", "LEGAL_PERSON:A"],
        ["EMPLOYEE", "POSITION", "LEGAL_PERSON"],
    )
    evidence = _row(
        ["EMPLOYEE:E001", "POSITION:P1", "BUSINESS_TRIP:Z"],
        ["EMPLOYEE", "POSITION", "BUSINESS_TRIP"],
    )
    # 字典序刻意让 LEGAL_PERSON 更靠前：它要是赢了，说明优先权真的生效了
    selected = _select_shortest_path([affiliation, evidence])
    assert selected is not None
    assert selected[0][-1] == "BUSINESS_TRIP:Z"


# --------------------------------------------------------------------------- #
# 判据 2：候选 > 400 时，真胜者**不被** DB 侧截断
# --------------------------------------------------------------------------- #
#: 干扰候选条数：**刻意 > `_PATH_CANDIDATE_LIMIT`**，逼出截断。
_NOISE_COUNT = 400


def test_db_truncation_drops_true_winner_only_under_legacy_key(real_driver) -> None:  # noqa: ANN001
    """同一批真图数据、同一条生产查询，只换 ``ORDER BY`` ⇒ 旧键丢、新键不丢。

    构造：锚点（EMPLOYEE）一跳连到 401 个终点——400 个 ``ACCESS_RECORD``
    （``_TERMINAL_RANK`` 里排 **7**，最末）加 1 个 ``BUSINESS_TRIP``（排 **0**，
    最前）。真胜者的 id 字典序**最大**：

    - 旧键 ``(prio, hops, ids[-1])``：两边 prio 都是 1、hops 都是 1 ⇒ 全靠
      ``ids[-1]`` ⇒ 真胜者排第 **401** ⇒ 被 ``LIMIT 400`` 截掉；
    - 新键 ``(终点档位, hops, ids[-1])``：``BUSINESS_TRIP`` = 1+0 = **1**，
      ``ACCESS_RECORD`` = 1+7 = **8** ⇒ 真胜者排第 **1** ⇒ 保住。

    两条断言缺一不可：只测"新键选中真胜者"考不出截断（候选 < 400 时旧键也能过），
    只测"旧键丢了"考不出修好了没。
    """
    version = f"p6v1-{uuid4().hex[:12]}"
    org = "org-p6v1"
    anchor_id = f"{version}-EMPLOYEE:ANCHOR"
    winner_id = f"{version}-BUSINESS_TRIP:ZZZ"

    rows = [
        {
            "id": f"{version}-ACCESS_RECORD:{index:04d}",
            "anchor": anchor_id,
            "kg_version": version,
            "org_id": org,
            "type": "ACCESS_RECORD",
            "name": f"门禁记录-{index:04d}",
        }
        for index in range(_NOISE_COUNT)
    ]
    rows.append(
        {
            "id": winner_id,
            "anchor": anchor_id,
            "kg_version": version,
            "org_id": org,
            "type": "BUSINESS_TRIP",
            "name": "出差单-真胜者",
        }
    )
    assert len(rows) > _PATH_CANDIDATE_LIMIT, "构不构不出截断 ⇒ 用例自身失效"

    _seed(real_driver, version=version, org=org, anchor_id=anchor_id, rows=rows)
    try:
        params = _path_query_params(version=version, org=org, anchor_id=anchor_id)
        legacy_query = _cypher_paths().replace(
            _DB_TERMINAL_TIER_EXPR, _DB_TERMINAL_TIER_LEGACY_EXPR
        )
        legacy_rows = _run(real_driver, legacy_query, params)
        current_rows = _run(real_driver, _cypher_paths(), params)

        # ① 截断**真的发生了**（否则下面两条都是空转）
        assert len(legacy_rows) == _PATH_CANDIDATE_LIMIT, (
            f"旧键返回 {len(legacy_rows)} 行，未触发截断 ⇒ 用例自身失效"
        )

        legacy_terminals = [str(row["ids"][-1]) for row in legacy_rows]
        current_terminals = [str(row["ids"][-1]) for row in current_rows]

        # ② 旧键：真胜者在 DB 侧就被截掉 ⇒ Python 侧精排根本看不到它
        assert winner_id not in legacy_terminals, (
            "旧键下真胜者仍在 400 行内 ⇒ 这条用例构不出「会丢」的事实，"
            "也就证明不了本次修法的必要性"
        )
        legacy_pick = _select_shortest_path(legacy_rows)
        assert legacy_pick is not None
        assert legacy_pick[0][-1] != winner_id, "旧键竟选中了真胜者 ⇒ 对照失效"

        # ③ 新键：真胜者被保住，且 Python 侧精排确实选它
        assert winner_id in current_terminals, (
            "新键下真胜者仍被截断 ⇒ 排序口径没对齐（这是本批的核心判据）"
        )
        current_pick = _select_shortest_path(current_rows)
        assert current_pick is not None
        assert current_pick[0][-1] == winner_id
    finally:
        _wipe(real_driver, version=version)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _row(ids: list[str], types: list[str]) -> dict[str, Any]:
    return {
        "ids": ids,
        "names": list(ids),
        "types": types,
        "rels": ["HOP"] * (len(ids) - 1),
        "valid_froms": [],
        "valid_tos": [],
    }


class _RecordingSession:
    """记录查询与参数的假会话（只验接线，不连真机）。"""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.queries: list[str] = []
        self.params: list[dict] = []

    def run(self, cypher: str, **params: object) -> list[dict]:
        self.queries.append(cypher)
        self.params.append(dict(params))
        return list(self._rows)


_PATH_ROW = {
    "ids": ["EMPLOYEE:E001", "POSITION:P001", "WORK_ORDER:SO-1"],
    "names": ["张伟", "售后工程师", "SO-1"],
    "types": ["EMPLOYEE", "POSITION", "WORK_ORDER"],
    "rels": ["HAS_POSITION", "HANDLED_ORDER"],
}


def _capture_path_params() -> dict[str, Any]:
    """跑一次 :func:`build_reasoning_path`，抓它下发给路径查询的参数。"""
    session = _RecordingSession([_PATH_ROW])
    build_reasoning_path(
        session=session,  # type: ignore[arg-type]
        kg_version="v-test",
        org_id="org-1",
        question="张伟的缺卡该怎么处理？",
        nodes=[
            GraphNode(
                id="EMPLOYEE:E001",
                label="Entity",
                entity_type="EMPLOYEE",
                canonical_name="张伟",
                confidence=0.9,
                kg_version="v-test",
            )
        ],
    )
    assert session.params, "没发出路径查询 ⇒ 用例自身失效"
    return dict(session.params[-1])


def _path_query_params(*, version: str, org: str, anchor_id: str) -> dict[str, Any]:
    """真图用例下发的参数：**与生产同参**（含旧键要用的 `prio_types`）。

    两次调用（新键 / 旧键）用**同一份**参数，只有 query 字符串不同 ⇒ 对照严格。
    """
    return {
        "org": org,
        "anchor_ids": [anchor_id],
        "terminal_types": list(ALL_TERMINAL_TYPES),
        "hub": HUB_EMPLOYEE_TYPE,
        "prio_type": TERMINAL_PRIORITY_TYPE,
        "terminal_rank": dict(_TERMINAL_RANK),
        "terminal_rank_default": len(_TERMINAL_RANK),
        # 旧键表达式需要它；新键不用（Neo4j 忽略未引用参数）
        "prio_types": list(PRIORITY_TERMINAL_TYPES),
        "limit": _PATH_CANDIDATE_LIMIT,
        "as_of": None,
        **VersionReadView(versions=(version,), selection={}).cypher_params(),
    }


def _seed(driver, *, version: str, org: str, anchor_id: str, rows: list[dict]) -> None:
    with driver.session() as session:
        session.run(
            "MERGE (a:Entity {id: $anchor, kg_version: $version}) "
            "SET a.org_id = $org, a.entity_type = 'EMPLOYEE', "
            "    a.canonical_name = '张伟'",
            anchor=anchor_id,
            version=version,
            org=org,
        )
        session.run(
            "UNWIND $rows AS row "
            "MERGE (b:Entity {id: row.id, kg_version: row.kg_version}) "
            "SET b.org_id = row.org_id, b.entity_type = row.type, "
            "    b.canonical_name = row.name",
            rows=rows,
        )
        session.run(
            "UNWIND $rows AS row "
            "MATCH (a:Entity {id: row.anchor, kg_version: row.kg_version}), "
            "      (b:Entity {id: row.id, kg_version: row.kg_version}) "
            "CREATE (a)-[r:RELATION]->(b) "
            "SET r.kg_version = row.kg_version, r.org_id = row.org_id, "
            "    r.relation_type = 'HOP'",
            rows=rows,
        )


def _run(driver, query: str, params: dict[str, Any]) -> list[Any]:
    with driver.session() as session:
        return list(session.run(query, **params))


def _wipe(driver, *, version: str) -> None:
    with driver.session() as session:
        session.run("MATCH (n {kg_version: $version}) DETACH DELETE n", version=version)
