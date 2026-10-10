"""P6-V3（偏离 **X-7**）：`incremental_cost` / `full_rebuild_cost` 两侧写入方的判据。

为什么单开一个文件而不是塞进 ``test_cost_metrics.py`` / ``test_cost_metrics_extraction.py``：
那两个文件分别守着**问答侧**与**抽取侧**的 **token** 口径，本文件守的是另一个**量纲**
（图元素个数）——三条链路的同名列共用一张表的同一行，混写会让"哪一侧真的通了"读不出来。

用户 2026-10-10 裁决（spec §10.1.1 第 15 项）：两侧**同为「图元素个数」= 实体数 + 关系数**。
本文件因此有一条专门的**同量纲**用例——它是本批唯一防住"分子数节点、分母数 token"
那类把无量纲比值当成 Manhattan 证据出来的错误的判据。

**故意不依赖真 Neo4j**：增量重算支持 ``session_factory`` 注入（``_make_runner``），
判据要考的是"计数有没有落进 cost_metrics"，不是"图能不能连上"——后者由
``test_kg_incremental_rebuild.py`` 用真图守着。 ⇒ 本文件在 CI 上也能跑。

每个用例自带 org / 动作行，finally 里**按 id 精确清理**（按 org 全删会误伤其它用例的行）。
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import (
    COST_STAGE_EXTRACTION,
    CostMetric,
    Document,
    KgVersion,
    OntologyAction,
)
from app.db.session import session_scope
from app.services.cost_metrics import (
    _graph_elements,
    build_dashboard,
    record_full_rebuild_cost,
    record_incremental_rebuild_cost,
)
from app.services.kg.incremental import (
    _CYPHER_MIRROR_VERSION,
    _CYPHER_PROBE_ENTITIES,
    _CYPHER_READ_ENTITIES,
    _CYPHER_READ_RELATIONS,
    _CYPHER_WRITE_ENTITIES,
    _CYPHER_WRITE_RELATIONS,
    rebuild_incrementally,
)
from app.storage import build_extract_artifact_key, get_storage
from app.tasks.registry import kg_build_executor
from app.tasks.types import TaskSpec

_ACTOR_ID = get_settings().default_actor_id


# --------------------------------------------------------------------------- #
# 替身：**内存假图**（经 session_factory 注入）
# --------------------------------------------------------------------------- #


class _FakeSession:
    """按 Cypher **常量**分派的内存替身 —— 不是"`run` 都返回空列表"的那种糊弄替身。

    为什么要按常量而不是"含 MERGE 就算写"来判断：那样会让 `_rewrite_subgraph` 的
    计数逻辑被跳过，分子恒 0，用例反而**更容易绿**。这里让每条读定义都真返回记录，
    `entity_count` / `relation_count` 因此是真由产品代码算出来的。
    """

    def __init__(
        self,
        *,
        org_id: uuid.UUID,
        relation_count: int,
        fail_on_write: bool = False,
    ) -> None:
        self._org_id = str(org_id)
        self._relation_count = relation_count
        self._fail_on_write = fail_on_write

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    def run(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if cypher is _CYPHER_PROBE_ENTITIES:
            return [{"id": item, "org_id": self._org_id} for item in params["ids"]]
        if cypher is _CYPHER_READ_ENTITIES:
            return [
                {"id": item, "props": {"id": item, "canonical_name": f"实体{index}"}}
                for index, item in enumerate(params["ids"])
            ]
        if cypher is _CYPHER_READ_RELATIONS:
            return [
                {
                    "source_id": params["ids"][0],
                    "target_id": params["ids"][index % len(params["ids"])],
                    "props": {"id": f"rel-{index}", "relation_type": "PARTY_TO"},
                }
                for index in range(self._relation_count)
            ]
        if cypher in (_CYPHER_WRITE_ENTITIES, _CYPHER_WRITE_RELATIONS):
            if self._fail_on_write:
                raise RuntimeError("图写入失败（用例注入）")
            return []
        if cypher is _CYPHER_MIRROR_VERSION:
            return []
        raise AssertionError(f"替身没覆盖这条 Cypher: {cypher[:60]}")


def _fake_factory(
    *, org_id: uuid.UUID, relation_count: int, fail_on_write: bool = False
) -> Any:
    def _factory() -> _FakeSession:
        return _FakeSession(
            org_id=org_id, relation_count=relation_count, fail_on_write=fail_on_write
        )

    return _factory


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


def _today() -> date:
    return datetime.now(UTC).date()


def _graph_row(org_id: uuid.UUID) -> CostMetric | None:
    """**带 stage** 读当日 extraction 行——漏了谓词，本文件的断言全部失去分辨力。"""
    with session_scope(org_id=org_id) as db:
        return db.scalar(
            select(CostMetric).where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date == _today(),
                CostMetric.stage == COST_STAGE_EXTRACTION,
            )
        )


def _cleanup(
    *,
    org_id: uuid.UUID,
    action_ids: list[uuid.UUID],
    trace_ids: list[uuid.UUID],
    document_ids: list[uuid.UUID] | None = None,
) -> None:
    with session_scope(org_id=org_id) as db:
        db.execute(delete(CostMetric).where(CostMetric.org_id == org_id))
        if document_ids:
            db.execute(delete(Document).where(Document.id.in_(document_ids)))
        if action_ids:
            db.execute(delete(OntologyAction).where(OntologyAction.id.in_(action_ids)))
        if trace_ids:
            db.execute(
                delete(KgVersion).where(
                    KgVersion.org_id == org_id, KgVersion.trace_id.in_(trace_ids)
                )
            )
        db.commit()


def _seed_incremental_state(
    *, org_id: uuid.UUID, entity_count: int = 3
) -> dict[str, Any]:
    """真 PG：一条 ready 基线版本 + 一条 merge 动作行（`rebuild_incrementally` 的前置）。"""
    trace_id = uuid.uuid4()
    base = f"p6v3-{uuid.uuid4().hex[:8]}"
    action_id = uuid.uuid4()
    entity_ids = [f"{base}-e{index}" for index in range(1, entity_count + 1)]

    with session_scope(org_id=org_id) as db:
        db.add(
            KgVersion(
                org_id=org_id,
                version=base,
                status="ready",
                source_doc_ids=[str(uuid.uuid4())],
                entity_count=entity_count,
                relation_count=0,
                # get_active 按 ready_at 倒序取；NULL 在 PG 的 DESC 下排**最前**
                ready_at=datetime.now(UTC),
                trace_id=trace_id,
            )
        )
        db.add(
            OntologyAction(
                id=action_id,
                org_id=org_id,
                action_type="merge",
                target_entities=entity_ids,
                actor_id=_ACTOR_ID,
                kg_version=base,
                trace_id=trace_id,
            )
        )
        db.commit()

    return {
        "trace_id": trace_id,
        "action_id": action_id,
        "entity_ids": entity_ids,
        "base_version": base,
    }


# --------------------------------------------------------------------------- #
# 1. 分子 / 分母的两侧写入
# --------------------------------------------------------------------------- #


def test_full_rebuild_cost_records_graph_element_sum() -> None:
    """**分母**：写入值 = 实体数 + 关系数（不是 token 数、不是毫秒）。"""
    org_id = uuid.uuid4()
    try:
        with session_scope(org_id=org_id) as db:
            record_full_rebuild_cost(
                org_id=org_id, entity_count=7, relation_count=3, db=db
            )

        row = _graph_row(org_id)
        assert row is not None, "分母没有落到 cost_metrics"
        assert row.full_rebuild_cost == pytest.approx(10.0)
        assert row.incremental_cost is None, "本用例没有增量重算 ⇒ 分子必须是空的"
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])


def test_graph_costs_accumulate_and_refresh_row_ratio() -> None:
    """同一天多次重写 ⇒ 累加；行级 `cost_ratio` 跟着走（除法只做一次，且不再不为 NaN）。"""
    org_id = uuid.uuid4()
    try:
        with session_scope(org_id=org_id) as db:
            record_full_rebuild_cost(
                org_id=org_id, entity_count=10, relation_count=0, db=db
            )
            record_incremental_rebuild_cost(
                org_id=org_id, entity_count=2, relation_count=3, db=db
            )

        row = _graph_row(org_id)
        assert row is not None
        assert row.full_rebuild_cost == pytest.approx(10.0)
        assert row.incremental_cost == pytest.approx(5.0)
        assert row.cost_ratio == pytest.approx(0.5)

        with session_scope(org_id=org_id) as db:
            record_incremental_rebuild_cost(
                org_id=org_id, entity_count=1, relation_count=4, db=db
            )

        row = _graph_row(org_id)
        assert row is not None
        assert row.incremental_cost == pytest.approx(10.0)
        assert row.cost_ratio == pytest.approx(1.0)
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])


def test_both_sides_use_one_shared_unit() -> None:
    """**同量纲**（本批的核心断言）：两侧都由 `_graph_elements` 换算 ⇒ 比值是**个数比**。

    为什么这条必须存在：X-7 的分母原本打算走 token。若哪天有人把一侧改成 token /
    毫秒而另一侧仍是节点数，`cost_ratio` 会照样算出一个看似合理的浮点数——
    **没有任何异常会抛出来**。本用例和 `_graph_elements` 的单一换算口一起，
    把"单位一致"变成机器可执行的事。
    """
    org_id = uuid.uuid4()
    try:
        with session_scope(org_id=org_id) as db:
            record_full_rebuild_cost(
                org_id=org_id, entity_count=7, relation_count=3, db=db
            )
            record_incremental_rebuild_cost(
                org_id=org_id, entity_count=1, relation_count=1, db=db
            )

        row = _graph_row(org_id)
        assert row is not None
        # 两侧都能用**同一个**换算函数复述 ⇒ 单位必然同源
        assert row.full_rebuild_cost == pytest.approx(
            _graph_elements(entity_count=7, relation_count=3)
        )
        assert row.incremental_cost == pytest.approx(
            _graph_elements(entity_count=1, relation_count=1)
        )
        assert row.cost_ratio == pytest.approx(
            _graph_elements(entity_count=1, relation_count=1)
            / _graph_elements(entity_count=7, relation_count=3)
        )
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])


def test_zero_graph_elements_and_missing_session_are_skipped() -> None:
    """不写 0、不建行（`db=None` 亦然）——沿用本模块「不写 0」的既有工艺纪律。

    为什么 0 有害：`cost_ratio` 的分母一旦被写成 0.0，"没有数据"与"有数据但极小"
    在读数上无法区分，而后者会让读仪表盘的人误以为这一侧已经出数了。
    """
    org_id = uuid.uuid4()
    try:
        with session_scope(org_id=org_id) as db:
            assert (
                record_full_rebuild_cost(
                    org_id=org_id, entity_count=0, relation_count=0, db=db
                )
                is None
            )
            assert (
                record_incremental_rebuild_cost(
                    org_id=org_id, entity_count=0, relation_count=0, db=db
                )
                is None
            )
            assert (
                record_full_rebuild_cost(
                    org_id=org_id, entity_count=1, relation_count=1, db=None
                )
                is None
            )
        assert _graph_row(org_id) is None, "零图元素不该把当日行建出来"
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])


# --------------------------------------------------------------------------- #
# 2. 增量重算（分子）真的经唯一写入口落库
# --------------------------------------------------------------------------- #


def test_incremental_rebuild_writes_numerator(
    real_pg_get_active: None,
) -> None:
    """一次成功增量重算 ⇒ 分子 += 重写的图元素个数（读的是**库里的行**，不是返回值）。

    :param real_pg_get_active: 撤销 conftest 的 ``autouse`` 桩（``v-test``）。
        为什么必须：**基线版本是本 Fixture 真落库的**，若让那条桩顶替，
        取到的会是假的 ``v-test`` ⇒ 与动作行记录的基线不一致而被**拒绝重算**，
        用例会以「看起来像增量失败了」的方式红掉，很难一眼看出是夹具的问题。
    """
    org_id = uuid.uuid4()
    state = _seed_incremental_state(org_id=org_id, entity_count=3)
    try:
        with session_scope(org_id=org_id) as db:
            result = rebuild_incrementally(
                db=db,
                org_id=org_id,
                action_id=state["action_id"],
                affected_entity_ids=state["entity_ids"],
                source_doc_ids=[uuid.uuid4()],
                trace_id=state["trace_id"],
                session_factory=_fake_factory(org_id=org_id, relation_count=2),
            )

        assert result.status == "ready"
        # 3 实体 + 2 关系：这两个数是 _rewrite_subgraph 自己算的，用例只是复述
        assert (result.entity_count, result.relation_count) == (3, 2)

        row = _graph_row(org_id)
        assert row is not None, "增量重算没有落 cost_metrics"
        assert row.incremental_cost == pytest.approx(5.0)
    finally:
        _cleanup(
            org_id=org_id,
            action_ids=[state["action_id"]],
            trace_ids=[state["trace_id"]],
        )


def test_failed_incremental_rebuild_writes_nothing(
    real_pg_get_active: None,
) -> None:
    """**护栏**：重写失败 ⇒ 走 `_fail(...)`，**既不写分子、也不写分母**。

    第二条才是本批真正要拦的：为了让 C3-b「有个数」而去开一个全量重建入口、或把失败
    那次算进分母 ⇒ ``cost_ratio`` 立刻变得很好看，且**永远不会有人发现**。
    ⇒ 失败就是没数，一条都不许垫。
    """
    org_id = uuid.uuid4()
    state = _seed_incremental_state(org_id=org_id, entity_count=3)
    try:
        with session_scope(org_id=org_id) as db:
            result = rebuild_incrementally(
                db=db,
                org_id=org_id,
                action_id=state["action_id"],
                affected_entity_ids=state["entity_ids"],
                source_doc_ids=[uuid.uuid4()],
                trace_id=state["trace_id"],
                session_factory=_fake_factory(
                    org_id=org_id, relation_count=2, fail_on_write=True
                ),
            )

        assert result.status == "failed"
        assert result.error_code is not None

        row = _graph_row(org_id)
        if row is not None:
            assert row.incremental_cost is None, "失败重算不该给分子留下任何数"
            assert row.full_rebuild_cost is None, (
                "失败没有（也不许）回落全量重建 ⇒ 分母必须仍是空的"
            )
    finally:
        _cleanup(
            org_id=org_id,
            action_ids=[state["action_id"]],
            trace_ids=[state["trace_id"]],
        )


# --------------------------------------------------------------------------- #
# 3. 没有数据时怎么报：0.0，不是 NaN
# --------------------------------------------------------------------------- #


def test_cost_ratio_is_zero_not_nan_without_denominator() -> None:
    """无分母 ⇒ **0.0**（用户裁决沿用既有语义）——`NaN` 会让 JSON 序列化失败。

    同时锁住：行级与区间级**同一个口径**。
    """
    org_id = uuid.uuid4()
    today = _today()
    try:
        with session_scope(org_id=org_id) as db:
            record_incremental_rebuild_cost(
                org_id=org_id, entity_count=2, relation_count=2, db=db
            )

            row = _graph_row(org_id)
            assert row is not None
            assert row.cost_ratio == 0.0
            assert not math.isnan(row.cost_ratio)

            payload = build_dashboard(
                db=db, org_id=org_id, date_from=today, date_to=today
            )

        assert payload["cost_ratio"] == 0.0
        assert not math.isnan(payload["cost_ratio"])
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])


# --------------------------------------------------------------------------- #
# 4. 分母的「首次」语义
# --------------------------------------------------------------------------- #


class _StubKgBuilder:
    """``ThreeStageKgBuilder`` 的最小替身：只让 ``build()`` 报一组**固定**规模。

    为什么可以替：本小组考的是「重跑要不要再往分母上加一次」，不是「图能不能真的建起来」
    ——后者由 :mod:`tests.test_kg_builder` 用真 Cypher 序列守着。规模取**非对称**的
    3 / 2：写成对称的数字会让"记了一次 vs 记了两次"在倍数上看不出来。
    """

    ENTITY_COUNT = 3
    RELATION_COUNT = 2

    def __init__(self, **_kwargs: Any) -> None:
        return

    def build(self, _request: Any) -> SimpleNamespace:
        return SimpleNamespace(
            entity_count=self.ENTITY_COUNT,
            relation_count=self.RELATION_COUNT,
            chunk_count=1,
            evidence_edge_count=1,
        )


def _seed_document(org_id: uuid.UUID) -> uuid.UUID:
    """文档 + 三份抽取产物（``kg.build`` 执行体的最小前置）。"""
    document_id = uuid.uuid4()
    with session_scope(org_id=org_id) as db:
        db.add(
            Document(
                id=document_id,
                filename_hash=f"p6v3-{document_id.hex}",
                mime_type="application/pdf",
                size_bytes=1024,
                status="pending",
                uploaded_by=_ACTOR_ID,
                org_id=org_id,
                trace_id=uuid.uuid4(),
            )
        )
        db.commit()
    storage = get_storage()
    for filename in ("entities.json", "relations.json", "chunks.json"):
        storage.put(
            build_extract_artifact_key(
                org_id=org_id, doc_id=document_id, filename=filename
            ),
            b"[]",
        )
    return document_id


def _run_kg_build(document_id: uuid.UUID, org_id: uuid.UUID) -> None:
    asyncio.run(
        kg_build_executor(
            TaskSpec(
                task_type="kg.build",
                payload={"document_id": str(document_id)},
                trace_id=str(uuid.uuid4()),
                org_id=org_id,
            )
        )
    )


def test_same_corpus_rebuild_does_not_inflate_denominator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**「首次」二字的全部意义**：同一批语料重跑 `kg.build` ⇒ 分母**仍只有一份**。

    重跑在现实里很常见（失败重试 / 人工补跑）。若复用既有版本的重跑也算一次分母，
    同一批语料多构建几次，`cost_ratio` 就被人为压低几次——而且**不报任何错**。
    这正是 X-7 分母最容易变成"漂亮假账"的地方（四不像的数永远看不出来）。
    """
    monkeypatch.setattr("app.tasks.registry.ThreeStageKgBuilder", _StubKgBuilder)
    org_id = uuid.uuid4()
    document_id = _seed_document(org_id)
    try:
        _run_kg_build(document_id, org_id)
        # 第二次：``documents.kg_version_id`` 已被填上 ⇒ 走"复用"分支，不是首次构建
        _run_kg_build(document_id, org_id)

        row = _graph_row(org_id)
        assert row is not None, "首次全量构建没有落 cost_metrics"
        expected = _StubKgBuilder.ENTITY_COUNT + _StubKgBuilder.RELATION_COUNT
        assert row.full_rebuild_cost == pytest.approx(expected), (
            "分母被重跑累加了 ⇒ cost_ratio 会被人为压低（实读="
            f"{row.full_rebuild_cost}）"
        )
    finally:
        _cleanup(
            org_id=org_id,
            action_ids=[],
            trace_ids=[],
            document_ids=[document_id],
        )
        with session_scope(org_id=org_id) as db:
            db.execute(delete(KgVersion).where(KgVersion.org_id == org_id))
            db.commit()


def test_dashboard_ratio_matches_row_level() -> None:
    """区间级 = Σ分子 / Σ分母 ⇒ 单日时与行级读数一致（两种读法不许打架）。"""
    org_id = uuid.uuid4()
    today = _today()
    yesterday = today - timedelta(days=1)
    try:
        with session_scope(org_id=org_id) as db:
            record_full_rebuild_cost(
                org_id=org_id,
                entity_count=20,
                relation_count=0,
                occurred_at=datetime.combine(yesterday, datetime.min.time(), UTC),
                db=db,
            )
            record_incremental_rebuild_cost(
                org_id=org_id, entity_count=3, relation_count=1, db=db
            )

            row = _graph_row(org_id)
            assert row is not None
            payload = build_dashboard(
                db=db, org_id=org_id, date_from=yesterday, date_to=today
            )

        assert payload["cost_ratio"] == pytest.approx(4.0 / 20.0)
        assert row.cost_ratio == pytest.approx(0.0), "本日行没有分母 ⇒ 行级仍是 0.0"
    finally:
        _cleanup(org_id=org_id, action_ids=[], trace_ids=[])
