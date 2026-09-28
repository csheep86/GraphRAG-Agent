"""Sprint 9.6 G1：GOVERNED_BY 汇合（R10 事实↔条款连通）的单测。

这些用例钉死的是 ``changes/Sprint9.6/proposal.md`` §1 的**真机纪律**，
不是实现细节：

- M2 span 的 ``WORK_TIME_SYSTEM`` 噪声节点（「系统」「核心在岗时段」…）
  绝不允许出现在边的端点；
- 匹配文本源是条款的 MENTIONS chunk 文本（条款名多为碎片，属性匹配必失败）；
- 未命中必须**可见**（misses），不得静默；
- 同输入同输出（确定性纪律，与 ``policy_values.load_policy_clauses`` 同款）。
"""

from __future__ import annotations

from typing import Any

from scripts.ingest_attendance_csv import (
    build_governed_by_relations,
    fetch_policy_context,
)

_WTS = [
    {"id": "WORK_TIME_SYSTEM:综合计算工时制", "canonical_name": "综合计算工时制"},
    {"id": "WORK_TIME_SYSTEM:标准工时制", "canonical_name": "标准工时制"},
]

_CLAUSES = [
    {
        "id": "ent_a",
        "name": "第十一条",
        "text": "第十一条 实行综合计算工时制的，月加班不得超过 36 小时。",
    },
    {
        "id": "ent_b",
        "name": "2026 年 1 月 1 日",  # 碎片名：属性匹配必失败，文本匹配命中
        "text": "自 2026 年 1 月 1 日起，标准工时制员工每日工作 8 小时。",
    },
    {
        "id": "ent_c",
        "name": "第七条",
        "text": "第七条 考勤记录以门禁与定位为准。",  # 不含任何工时制名
    },
]


# --------------------------------------------------------------------------- #
# build_governed_by_relations
# --------------------------------------------------------------------------- #
def test_hit_edges_with_deterministic_ids() -> None:
    rows, misses = build_governed_by_relations(_WTS, _CLAUSES)

    ids = [r["id"] for r in rows]
    # 边 id 确定性（重跑 MERGE 幂等的根基）；顺序 = wts 按 id 升序
    # （「标」U+6807 < 「综」U+7EFC ⇒ 标准工时制在前）
    assert ids == [
        "GOVERNED_BY:WORK_TIME_SYSTEM:标准工时制->ent_b",
        "GOVERNED_BY:WORK_TIME_SYSTEM:综合计算工时制->ent_a",
    ]
    # 行顺序稳定（wts 与条款都按 id 升序）
    assert [r["head"] for r in rows] == sorted(r["head"] for r in rows)
    assert misses == []


def test_span_noise_never_participates() -> None:
    """真机纪律 1：span 噪声（ent_*）绝不进边端点——防御断言生效。"""
    span_rows = [
        {"id": "ent_deadbeef", "canonical_name": "系统"},
        {"id": "ent_c0ffee", "canonical_name": "核心在岗时段"},
        *_WTS,
    ]
    rows, misses = build_governed_by_relations(span_rows, _CLAUSES)

    assert all(r["head"].startswith("WORK_TIME_SYSTEM:") for r in rows)
    assert len(rows) == 2  # 只有两个 CSV 派生节点建了边
    assert any("skipped-non-csv" in m for m in misses)


def test_fragment_names_matched_via_chunk_text() -> None:
    """真机纪律 2：条款名是碎片（「2026 年 1 月 1 日」），靠 chunk 文本命中。"""
    rows, _ = build_governed_by_relations(_WTS[:1], _CLAUSES)

    assert rows[0]["tail"] == "ent_a"  # 名字是「第十一条」，文本命中靠正文


def test_unmatched_visible_in_misses() -> None:
    """未命中必须可见，不得静默（连通失败要能被发现）。"""
    lonely = [{"id": "WORK_TIME_SYSTEM:不存在的制度", "canonical_name": "不存在的制度"}]
    rows, misses = build_governed_by_relations(lonely, _CLAUSES)

    assert rows == []
    assert misses == ["不存在的制度"]


def test_empty_name_skipped() -> None:
    rows, misses = build_governed_by_relations(
        [{"id": "WORK_TIME_SYSTEM:", "canonical_name": ""}], _CLAUSES
    )

    assert rows == []
    assert misses == ["[skipped-empty-name] WORK_TIME_SYSTEM:"]


def test_duplicate_context_rows_deduped() -> None:
    duplicated = _CLAUSES + [_CLAUSES[0]]
    rows, _ = build_governed_by_relations(_WTS[:1], duplicated)

    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# fetch_policy_context：查询形状（文本源 = MENTIONS → POLICY_CLAUSE 的 chunk）
# --------------------------------------------------------------------------- #
class _FakeSession:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        self.queries: list[str] = []

    def run(self, query: str, **_: Any) -> Any:
        self.queries.append(query)
        return iter(self._data)


def test_fetch_policy_context_query_shape() -> None:
    """文本源必须是「chunk -MENTIONS-> POLICY_CLAUSE」——
    这一条把 CSV 证据 chunk（只 MENTIONS 到 EMPLOYEE）天然排除在外。"""
    session = _FakeSession(
        [{"id": "ent_a", "name": "第十一条", "text": "…综合计算工时制…"}]
    )

    context = fetch_policy_context(session, kg_version="v")

    query = session.queries[0]
    assert "MENTIONS" in query
    assert "POLICY_CLAUSE" in query
    assert "ORDER BY p.id" in query  # 确定性：按 id 升序
    assert context == [{"id": "ent_a", "name": "第十一条", "text": "…综合计算工时制…"}]


def test_fetch_policy_context_null_tolerant() -> None:
    """无 chunk / 无名字的条款：None → 空串，不抛错不伪造。"""
    session = _FakeSession([{"id": "ent_x", "name": None, "text": None}])

    context = fetch_policy_context(session, kg_version="v")

    assert context == [{"id": "ent_x", "name": "", "text": ""}]
