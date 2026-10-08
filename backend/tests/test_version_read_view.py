"""P5-H：**版本继承读**的裁决层测试（PG 真源 + 假 Neo4j 会话）。

**为什么单开一个文件**：这一层要钉的是**纯裁决规则**（版本怎么串成链、每个 id 选哪个
版本、被 merge 删掉的 id 为什么不再继承），而它们在真图用例里会被「Cypher 写对没有」
这类问题掩盖 —— 真图摔了没法一眼分清是**裁决错**还是**查询写错**。

三条在本文件钉死的性质（`:mod:`app.services.kg.version_view` 的契约）：

1. **链有序**：`resolve_read_versions()` 一定返回**新 → 旧**；
2. **链不外溢**：他 org 的动作行撞名也**不得**串进本租户的链（G-9 T1 面）；
3. **删除不再继承**：某版本对应的动作「承诺处理」了某 id 却不在该版本里 ⇒ 它被删了。

**两条本地坑（都踩过）**：

- conftest 默认把 ``KgVersioningService.get_active`` 打桩成固定版本 ⇒ 本文件的
  用例必须挂 ``real_pg_get_active`` 才能读到自己在 PG 里造的行；
- ``get_active`` 按 ``ready_at DESC`` 取一条 ⇒ 测试行的 ``ready_at`` **必须显式给**，
  否则库里残留的行会抢走 active（NULL 在 DESC 下排最前）。

**本地跑法**（本机 Neo4j 常是停的；本文件**不需要** Neo4j）：

```powershell
uv run pytest tests/test_version_read_view.py -q
```
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete

from app.db.models import KgVersion, OntologyAction
from app.db.session import session_scope
from app.services.kg.version_view import (
    DEFAULT_MAX_CHAIN_DEPTH,
    VersionReadView,
    build_read_view,
    resolve_action_scopes,
    resolve_entity_selection,
    resolve_read_versions,
    version_scope,
)

_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_OTHER_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")

_TRACE_ID = uuid.uuid4()

#: ``ready_at`` 的基准：故意用**未来**时间 —— 测试库里可能有其它 ready 行，
#: 按 ``ready_at DESC`` 取一条时会抢走 active（见模块 docstring 的两条本地坑）。
_NOW = datetime.now(UTC)


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #
class _FakeSession:
    """回放 ``(id, ver, org_id)`` 行的假 Neo4j 会话（按参数过滤，举动像真的）。"""

    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = [{"id": row[0], "ver": row[1], "org_id": row[2]} for row in rows]
        self.calls: list[dict[str, Any]] = []

    def run(self, _cypher: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(params))
        kgs = list(params.get("kgs") or ())
        org_id = params.get("org_id")
        return [
            row
            for row in self._rows
            if row["ver"] in kgs and (org_id is None or row["org_id"] == org_id)
        ]


@pytest.fixture
def pg() -> Any:
    """真 PG：一条 ready 基线版本；清理按版本号前缀（增量版本是 ``<base>-inc-*``）。"""
    base = f"p5h-view-{uuid.uuid4().hex[:8]}"
    with session_scope(org_id=_ORG_ID) as session:
        session.add(
            KgVersion(
                org_id=_ORG_ID,
                version=base,
                status="ready",
                source_doc_ids=[],
                entity_count=0,
                relation_count=0,
                ready_at=_NOW + timedelta(days=1),
                trace_id=_TRACE_ID,
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


def _ready_version(version: str, *, days: int) -> None:
    """把某个版本也置 ready（``days`` 越大 ⇒ 越可能是 active）。"""
    with session_scope(org_id=_ORG_ID) as session:
        session.add(
            KgVersion(
                org_id=_ORG_ID,
                version=version,
                status="ready",
                source_doc_ids=[],
                entity_count=0,
                relation_count=0,
                ready_at=_NOW + timedelta(days=days),
                trace_id=_TRACE_ID,
            )
        )
        session.commit()


def _action(
    *,
    base: str,
    result: str,
    entity_ids: list[str],
    new_entity_ids: list[str] | None = None,
    org_id: uuid.UUID = _ORG_ID,
    action_type: str = "rename",
) -> None:
    """造一行动作（= 一次「由 ``base`` 产出 ``result``」的校正）。

    :param entity_ids: ``target_entities.entity_ids`` —— 本次动作**承诺处理**的 id
    """
    target: dict[str, Any] = {"entity_ids": entity_ids}
    if new_entity_ids is not None:
        target["new_entity_ids"] = new_entity_ids
    with session_scope(org_id=org_id) as session:
        session.add(
            OntologyAction(
                org_id=org_id,
                action_type=action_type,
                target_entities=target,
                actor_id=_TRACE_ID,
                kg_version=base,
                result_kg_version=result,
                trace_id=_TRACE_ID,
            )
        )
        session.commit()


# --------------------------------------------------------------------------- #
# 判据 1：版本链解析（无父链 / 单跳 / 多跳）
# --------------------------------------------------------------------------- #
def test_chain_is_single_version_when_no_correction_ever(pg: str) -> None:
    """无父链：图上从没发生过校正 ⇒ 链恰好只有 active 一条（选中表为空的前提）。"""
    with session_scope(org_id=_ORG_ID) as session:
        chain = resolve_read_versions(db=session, org_id=_ORG_ID, active_version=pg)

    assert chain == (pg,), "没有任何 ontology_actions ⇒ 链不许凭空多出一截"


def test_chain_carries_parent_after_one_correction(pg: str) -> None:
    """单跳：一次校正产出 v1 ⇒ 链 = ``(v1, base)``（**新 → 旧**有序）。"""
    v1 = f"{pg}-inc-aaaaaa"
    _action(base=pg, result=v1, entity_ids=[f"{pg}-e1"])

    with session_scope(org_id=_ORG_ID) as session:
        chain = resolve_read_versions(db=session, org_id=_ORG_ID, active_version=v1)

    assert chain == (v1, pg)


def test_chain_is_ordered_after_three_consecutive_corrections(pg: str) -> None:
    """多跳：连续 3 次校正 ⇒ 链 = ``(v3, v2, v1, base)``，**顺序即继承优先级**。"""
    v1 = f"{pg}-inc-000001"
    v2 = f"{v1}-inc-000002"
    v3 = f"{v2}-inc-000003"
    _action(base=pg, result=v1, entity_ids=[f"{pg}-e1"])
    _action(base=v1, result=v2, entity_ids=[f"{pg}-e2"])
    _action(base=v2, result=v3, entity_ids=[f"{pg}-e3"])

    with session_scope(org_id=_ORG_ID) as session:
        chain = resolve_read_versions(db=session, org_id=_ORG_ID, active_version=v3)

    assert chain == (v3, v2, v1, pg)
    # 有序性的**可核查含义**：越靠前优先级越高，选中裁决逐字依赖这个次序
    assert chain[0] == v3 and chain[-1] == pg


def test_other_org_actions_never_join_my_chain(pg: str) -> None:
    """判据 11：**跨 org 的版本不混入链**（G-9 T1 越权面的第二道防线）。

    构造方式：他 org 有一行与目标版本**同名**的 ``result_kg_version``，且它的
    ``kg_version`` 指向一个本租户根本不存在的版本。若撞进来，链会凭空多出一截，
    后面的选中裁决会照着这个假祖先去继承 ⇒ 这就是跨租户数据污染的读侧形态。
    """
    v1 = f"{pg}-inc-aaaaaa"
    foreign_base = f"{pg}-FOREIGN-BASE"
    _action(base=pg, result=v1, entity_ids=[f"{pg}-e1"])
    _action(
        base=foreign_base,
        result=v1,
        entity_ids=["foreign-e1"],
        org_id=_OTHER_ORG_ID,
    )

    with session_scope(org_id=_ORG_ID) as session:
        chain = resolve_read_versions(db=session, org_id=_ORG_ID, active_version=v1)

    assert chain == (v1, pg)
    assert foreign_base not in chain


def test_chain_stops_at_depth_limit_without_error(pg: str) -> None:
    """链长超限：**截断 + 不报错**（P5H-5：限值只是防环的工程兜底）。

    故意把上限压到远小于实际链长 ⇒ 结果长度为上限，且**前缀**是对的
    （截断丢的是最老那几代，不是乱序）。
    """
    versions = [pg]
    for index in range(1, 6):
        # ⚠️ 刻意用**短**增量后缀（``-i<N>``），原因和测试数据有关、**与产品无关**：
        # 这五个数会被写进 ``ontology_actions.kg_version`` / ``result_kg_version``，
        # 两张表的这两列都是 ``String(64)``（``models.py:1069`` / ``:1071``）；
        # 若这里用产品的真实后缀 ``-inc-<6hex>``（每级 +11），head 会到 72 字符 ⇒ 撑爆。
        # 产品侧自 **P5-I0** 起版本号恒定 29 字符（不再把 base 拼进来），看门狗见
        # ``test_kg_incremental_rebuild.py::test_legacy_nested_version_would_overflow_the_column``。
        versions.append(f"{versions[-1]}-i{index}")
        _action(base=versions[-2], result=versions[-1], entity_ids=[f"{pg}-e{index}"])
    head = versions[-1]

    with session_scope(org_id=_ORG_ID) as session:
        full = resolve_read_versions(db=session, org_id=_ORG_ID, active_version=head)
        truncated = resolve_read_versions(
            db=session, org_id=_ORG_ID, active_version=head, max_depth=3
        )

    assert len(full) == 6
    assert len(full) <= DEFAULT_MAX_CHAIN_DEPTH
    assert len(truncated) == 3
    assert truncated == tuple(full[:3])


# --------------------------------------------------------------------------- #
# 选中表裁决
# --------------------------------------------------------------------------- #
def test_selection_prefers_newest_version_per_id() -> None:
    """同 id 在多版本里都有 ⇒ **链上最新者胜**（校正后的值接管旧值）。"""
    session = _FakeSession(
        [
            ("X", "v2", str(_ORG_ID)),
            ("X", "v0", str(_ORG_ID)),
            ("Y", "v0", str(_ORG_ID)),
        ]
    )
    selection = resolve_entity_selection(
        session=session, org_id=_ORG_ID, versions=("v2", "v1", "v0"), scopes={}
    )
    assert selection == {"X": "v2", "Y": "v0"}


def test_deleted_ids_are_not_inherited_back() -> None:
    """P5H-2：merge 是 ``DETACH DELETE``（无墓碑），靠**动作作用域**判删除。

    ``X`` 被 v2 那次 merge 处理过、且它不在 v2 里 ⇒ **不许**从 v0 里被继承回来；
    而从未被任何动作处理过的 ``Z`` 必须照旧从 v0 继承。
    """
    session = _FakeSession(
        [
            ("A", "v2", str(_ORG_ID)),
            ("X", "v0", str(_ORG_ID)),
            ("Z", "v0", str(_ORG_ID)),
        ]
    )
    selection = resolve_entity_selection(
        session=session,
        org_id=_ORG_ID,
        versions=("v2", "v1", "v0"),
        scopes={"v2": frozenset({"A", "X"})},
    )
    assert selection == {"A": "v2", "Z": "v0"}
    assert "X" not in selection, "被 merge 删掉的节点不得靠版本继承被复活"


def test_selection_never_crosses_org_boundary() -> None:
    """选中表严格按 org 取：他 org 的**更新版本**不得顶掉本租户的选择。

    构造 X 在他 org 里有 v2（比本租户的 v0 新）⇒ 若忘了隔离，选中裁决会把
    ``X`` 判到 v2（一个本租户版本链上的、但节点属于他 org 的版本）。
    """
    session = _FakeSession(
        [
            ("X", "v2", str(_OTHER_ORG_ID)),
            ("X", "v0", str(_ORG_ID)),
        ]
    )
    selection = resolve_entity_selection(
        session=session, org_id=_ORG_ID, versions=("v2", "v1", "v0"), scopes={}
    )
    assert selection == {"X": "v0"}
    assert session.calls[0]["org_id"] == str(_ORG_ID)


def test_scopes_read_entity_ids_and_new_entity_ids(pg: str) -> None:
    """`target_entities` 的两种键都要收：``entity_ids``（可能含被删者）与
    ``new_entity_ids``（split 产出的新节点）。"""
    v1 = f"{pg}-inc-aaaaaa"
    _action(
        base=pg,
        result=v1,
        entity_ids=[f"{pg}-e1"],
        new_entity_ids=[f"{pg}-e1--split-1"],
        action_type="split",
    )

    with session_scope(org_id=_ORG_ID) as session:
        scopes = resolve_action_scopes(db=session, org_id=_ORG_ID, versions=(v1, pg))

    assert scopes[v1] == frozenset({f"{pg}-e1", f"{pg}-e1--split-1"})


# --------------------------------------------------------------------------- #
# 组装：缺省必须零开销、零变化
# --------------------------------------------------------------------------- #
def test_build_view_does_not_touch_the_graph_without_history(
    pg: str, real_pg_get_active: None
) -> None:
    """**缺省零开销**：没有校正历史 ⇒ **不**发任何图查询（选中表为空即可）。

    这条同时是「缺省零变化」的机器证明：`$sel` 为空 map 时 Cypher 的版本谓词
    退化为 ``n.kg_version IN $kgs``（列表里只有 head），等价于原来的 ``= $kg``。
    """
    session = _FakeSession([])
    with session_scope(org_id=_ORG_ID) as db:
        view = build_read_view(db=db, session=session, org_id=_ORG_ID)

    assert view.versions == (pg,)
    assert view.selection == {}
    assert view.inherits_history is False
    assert session.calls == [], "无历史 ⇒ 不许为了视图多打一次图"


def test_build_view_resolves_inheritance_after_correction(
    pg: str, real_pg_get_active: None
) -> None:
    """带历史：链 + 选中表都被解析出来（供三条读路径直接用）。"""
    v1 = f"{pg}-inc-aaaaaa"
    _action(base=pg, result=v1, entity_ids=[f"{pg}-e1"])
    _ready_version(v1, days=3)  # 比基线的 days=1 新 ⇒ 它就是 active
    session = _FakeSession(
        [
            (f"{pg}-e1", v1, str(_ORG_ID)),
            (f"{pg}-e2", pg, str(_ORG_ID)),
        ]
    )

    with session_scope(org_id=_ORG_ID) as db:
        view = build_read_view(db=db, session=session, org_id=_ORG_ID)

    assert view.head == v1
    assert view.inherits_history is True
    assert view.selection == {f"{pg}-e1": v1, f"{pg}-e2": pg}
    assert view.cypher_params()["kgs"] == [v1, pg]


def test_version_scope_predicate_is_the_single_shared_one() -> None:
    """三条读路径**共用同一段判据**（概览 / 多跳推理 / 合规扫描），不许各写一份。

    断言的是它的**缺省形态**：``$sel`` 取不到值 ⇒ 整段等价于单版本过滤。
    """
    scope = version_scope("n")
    assert "n.kg_version IN $kgs" in scope
    # ⚠️ 必须是「选中表为空」判据，不能是「取不到值」判据 —— 后者会让
    # 「已被 merge 删掉的 id」重新读出来（本批实测踩过，2026-10-08）。
    assert "size(keys($sel)) = 0 OR $sel[n.id] = n.kg_version" in scope


def test_view_without_org_id_refuses_to_inherit(pg: str) -> None:
    """无租户上下文 ⇒ **不继承**（退回空链）——宁可少读，也不许在这条路径上
    放宽隔离键（ADR-0003：``org_id`` 是所有读路径的强制过滤键）。"""
    session = _FakeSession([])
    with session_scope(org_id=_ORG_ID) as db:
        view = build_read_view(db=db, session=session, org_id=None)

    assert view.versions == ()
    assert view.selection == {}
    assert VersionReadView(versions=(), selection={}).head == ""
