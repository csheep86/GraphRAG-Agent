"""Sprint 9 批次 B：仲裁规则 R1–R4 的**纯函数**验收（ADR-0005 §5 / D-3）。

全部零外部依赖：不连 Neo4j、不查 PG、不调 LLM——规则引擎就该这样测，
否则维护成本会从"规则"转移到"Mock"，而后者对正确性毫无帮助。

每条用例名都用它在防的真实事故命名，方便日后回看「为什么要有这条」。
"""

from __future__ import annotations

from app.services.kg.temporal import (
    ExpiryPlan,
    TemporalRelation,
    always_append_only,
    plan_expiries,
)

#: 只关心裁判结果的类型
DocID = str | None


def _single_current(relation_type: str) -> bool:  # noqa: ARG001
    """被测的策略：一律「唯一当前」——把策略维度排除掉，专测规则。"""
    return True


def _edge(
    head: str,
    tail: str,
    valid_from: str | None,
    *,
    relation_type: str = "LEGAL_REP",
    valid_to: str | None = None,
    doc: DocID = "doc-A",
    position: int | None = None,
) -> TemporalRelation:
    return TemporalRelation(
        head_id=head,
        tail_id=tail,
        relation_type=relation_type,
        valid_from=valid_from,
        valid_to=valid_to,
        source_document_id=doc,
        tail_position=position,
    )


def _target(plan: ExpiryPlan) -> tuple[str, str, str]:
    """``(tail_id, valid_to, reason)``——断言只关心这三项。"""
    return (plan.relation.tail_id, plan.valid_to, plan.reason)


# --------------------------------------------------------------------------- #
# R1 跨文档
# --------------------------------------------------------------------------- #


def test_r1_newer_fact_closes_the_old_one() -> None:
    """2025 年的李四 ⇒ 2023 年的张三失效到 2025-05-01。"""
    existing = [_edge("sub-1", "lpr-张三", "2023-04-01", doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B")]

    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )

    assert [_target(p) for p in plans] == [("lpr-张三", "2025-05-01", "R1")]


def test_r1_requires_strictly_later_not_equal() -> None:
    """**严格**晚于：同日的两条不算取代（这是坑 5 的根因）。

    若这里退化成 ``<=``，同一变更句的旧值会把新值封掉，当前值全线阵亡。
    """
    existing = [_edge("sub-1", "lpr-张三", "2025-05-01", doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B")]

    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )

    assert plans == [], "生效日相同 ⇒ 不是取代关系，R2 才是它的对口规则"


def test_r1_leaves_older_facts_alone() -> None:
    """后写入的旧事实不封已在图里的新事实——仲裁只认「更新 ⇒ 取代」这个方向。"""
    existing = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B")]
    incoming = [_edge("sub-1", "lpr-张三", "2023-04-01", doc="doc-A")]

    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )

    assert plans == []


def test_r1_same_tail_is_a_restatement_not_a_replacement() -> None:
    """同一目标值在另一份文档里被重申 ⇒ 那条边还在有效期内，不是被取代。"""
    existing = [_edge("sub-1", "lpr-张三", "2023-04-01", doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-张三", "2025-05-01", doc="doc-B")]

    assert (
        plan_expiries(
            existing=existing, incoming=incoming, is_single_current=_single_current
        )
        == []
    )


# --------------------------------------------------------------------------- #
# R2 同文档变更句
# --------------------------------------------------------------------------- #


def test_r2_change_sentence_keeps_the_last_tail() -> None:
    """「由张三变更为李四」：两句同一天 ⇒ 保留原文里**最后出现**的李四。"""
    incoming = [
        _edge("sub-1", "lpr-张三", "2025-05-01", doc="doc-A", position=31),
        _edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-A", position=52),
    ]

    plans = plan_expiries(
        existing=[], incoming=incoming, is_single_current=_single_current
    )

    assert [_target(p) for p in plans] == [("lpr-张三", "2025-05-01", "R2")]


def test_r2_without_position_refuses_to_judge() -> None:
    """定位不到 tail 位置 ⇒ **整组不判**（R4：拿不准就不封）。

    保留两条 alive 边是可诊断的现状；猜一个封掉会在答案里留下一处无人知晓的错。
    """
    incoming = [
        _edge("sub-1", "lpr-张三", "2025-05-01", doc="doc-A", position=None),
        _edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-A", position=52),
    ]

    assert (
        plan_expiries(existing=[], incoming=incoming, is_single_current=_single_current)
        == []
    )


def test_r2_duplicate_same_tail_is_not_a_change() -> None:
    """同一目标值的两条 evidence（同一事实被强调两次）不算变更。"""
    incoming = [
        _edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-A", position=10),
        _edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-A", position=90),
    ]

    assert (
        plan_expiries(existing=[], incoming=incoming, is_single_current=_single_current)
        == []
    )


# --------------------------------------------------------------------------- #
# R3 禁同批次互封 / R4 不猜值 / 策略与去重
# --------------------------------------------------------------------------- #


def test_r3_same_document_never_invalidates_itself() -> None:
    """同一份文档内的边互不封（PoC 坑 5：李四先写后被张三反封，当前值阵亡）。"""
    existing = [_edge("sub-1", "lpr-张三", "2023-04-01", doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-A")]

    assert (
        plan_expiries(
            existing=existing, incoming=incoming, is_single_current=_single_current
        )
        == []
    )


def test_r4_edge_without_valid_from_is_never_compared() -> None:
    """缺日期 ⇒ 不参与时效比较（不替它编一个日期，也不因"没日期"就封别人）。"""
    existing = [_edge("sub-1", "lpr-张三", None, doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B")]

    assert (
        plan_expiries(
            existing=existing, incoming=incoming, is_single_current=_single_current
        )
        == []
    )


def test_append_only_policy_never_closes_anything() -> None:
    """多值并存类型（对外投资 / 供应商）：哪怕遇到更晚的新事实也不封。"""
    existing = [_edge("sub-1", "org-子公司A", "2023-04-01", doc="doc-A")]
    incoming = [_edge("sub-1", "org-子公司B", "2025-05-01", doc="doc-B")]

    plans = plan_expiries(
        existing=existing,
        incoming=incoming,
        is_single_current=lambda _rt: False,
    )

    assert plans == []


def test_default_policy_is_consistently_conservative() -> None:
    """策略未加载 ⇒ 默认「并存」。保守是有意的：未配置就封 = 历史边静默消失。"""
    existing = [_edge("sub-1", "lpr-张三", "2023-04-01", doc="doc-A")]
    incoming = [_edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B")]

    assert plan_expiries(existing=existing, incoming=incoming) == []
    assert always_append_only("LEGAL_REP") is False


def test_multiple_new_facts_close_the_old_one_at_the_earliest_date() -> None:
    """同一旧边被多条新事实命中 ⇒ 取**最早**的失效日。

    取最晚会让旧事实在中间那段时间里"已失效却还活着"，被 as-of 查询当成真相。
    """
    existing = [_edge("sub-1", "lpr-张三", "2020-01-01", doc="doc-A")]
    incoming = [
        _edge("sub-1", "lpr-李四", "2025-05-01", doc="doc-B"),
        _edge("sub-1", "lpr-王五", "2023-04-01", doc="doc-C"),
    ]

    plans = plan_expiries(
        existing=existing, incoming=incoming, is_single_current=_single_current
    )

    assert [_target(p) for p in plans] == [("lpr-张三", "2023-04-01", "R1")]
