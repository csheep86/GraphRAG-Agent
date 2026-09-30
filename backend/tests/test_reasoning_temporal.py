"""Sprint 10.4（ADR-0005 §6 L2）：**路径时序一致性**的判据。

三条必须钉死的纪律，全部来自本项目反复踩过的坑：

1. **三值语义，不许合并**：``consistent`` / ``inconsistent`` / ``unknown`` 各自独立。
   把 ``unknown`` 并进 ``consistent`` 等于默认「没写日期 = 永远有效」——那正是
   D-3（确定性仲裁）要消灭的病态：旧事实与新事实会永远同时在位，
   「当前法定代表人是谁」这类问题必然给出两个答案；
2. **纯字符串比较，不调 LLM**：``YYYY-MM-DD`` 的字典序与日期序一致，与 §5 R1–R4
   同族——能靠受控 schema 判的，不交给模型；
3. **自洽优先，但不许为了自洽选更长的链**：排序键里它排在跳数**之后**。
"""

from __future__ import annotations

from typing import Any

from app.services.reasoning import _select_shortest_path, _temporal_verdict


def _row(
    ids: list[str],
    types: list[str],
    *,
    valid_froms: list[str | None] | None = None,
    valid_tos: list[str | None] | None = None,
) -> dict[str, Any]:
    """造一条候选路径行；``*`` 结尾的行之间只有时态差异（便于比口令对比）。"""
    return {
        "ids": ids,
        "names": list(ids),
        "types": types,
        "rels": ["HOP"] * (len(ids) - 1),
        "valid_froms": valid_froms if valid_froms is not None else [],
        "valid_tos": valid_tos if valid_tos is not None else [],
    }


# --------------------------------------------------------------------------- #
# 三值语义
# --------------------------------------------------------------------------- #
def test_all_dated_and_alive_is_consistent() -> None:
    """每跳都有生效日、且都没失效 ⇒ 存在共同成立时点。"""
    verdict = _temporal_verdict(["2026-10-15", "2026-10-16"], [None, None])
    assert verdict == "consistent"


def test_overlapping_windows_are_consistent() -> None:
    """较晚开始的事实，起始日不晚于最早的失效日 ⇒ 仍能同时成立。"""
    verdict = _temporal_verdict(
        ["2026-10-01", "2026-10-16"], ["2026-10-31", "2026-12-31"]
    )
    assert verdict == "consistent"


def test_inverted_order_is_inconsistent() -> None:
    """第二跳在 2026-09-01 就失效了，第一跳却 2026-10-01 才开始 ⇒ 顺序倒置。"""
    verdict = _temporal_verdict(["2026-10-01"], ["2026-09-01"])
    assert verdict == "inconsistent"


def test_missing_date_is_unknown_not_consistent() -> None:
    """缺日期 ⇒ **不可判定**，绝不并入 consistent（R4：不为没日期的关系编一个）。"""
    assert _temporal_verdict([None, "2026-10-16"], [None, None]) == "unknown"
    assert _temporal_verdict([], []) == "unknown"


def test_single_hop_is_judged_like_any_chain() -> None:
    """单跳链同判据：已失效的一跳 ⇒ inconsistent（不是 unknown）。"""
    assert _temporal_verdict(["2026-10-01"], ["2026-09-01"]) == "inconsistent"
    assert _temporal_verdict(["2026-10-01"], [None]) == "consistent"


# --------------------------------------------------------------------------- #
# 选链：自洽优先，但不得牺牲解释力 / 跳数
# --------------------------------------------------------------------------- #
_IDS_A = ["EMPLOYEE:E001", "WORK_ORDER:A"]
_IDS_Z = ["EMPLOYEE:E001", "WORK_ORDER:Z"]
_TYPES = ["EMPLOYEE", "WORK_ORDER"]


def test_consistent_beats_unknown_at_equal_hops() -> None:
    """同样短、同样落点 ⇒ 选自洽的那条。

    自洽那条刻意排在**字典序更后**的位置（``Z`` > ``A``）：只有时序优先级真的
    生效它才会赢——否则这条用例与「按 id 字典序」的结果无法区分。
    """
    unknown = _row(_IDS_A, _TYPES, valid_froms=[None], valid_tos=[None])
    consistent = _row(_IDS_Z, _TYPES, valid_froms=["2026-10-16"], valid_tos=[None])

    selected = _select_shortest_path([unknown, consistent])
    assert selected is not None
    assert selected[0] == _IDS_Z


def test_missing_temporal_columns_is_unknown_not_error() -> None:
    """旧形状的行（没有时态列）⇒ 按 unknown 处理，**不炸、不默认自洽**。"""
    legacy = {"ids": _IDS_A, "names": _IDS_A, "types": _TYPES, "rels": ["HOP"]}
    dated = _row(_IDS_Z, _TYPES, valid_froms=["2026-10-16"], valid_tos=[None])

    selected = _select_shortest_path([legacy, dated])
    assert selected is not None
    assert selected[0] == _IDS_Z


def test_temporal_does_not_outrank_hop_count() -> None:
    """不许为了自洽挑更长的链：一跳且不自洽 > 两跳且自洽（同一终点类型）。"""
    long_consistent = _row(
        ["EMPLOYEE:E001", "POSITION:P1", "WORK_ORDER:C"],
        ["EMPLOYEE", "POSITION", "WORK_ORDER"],
        valid_froms=["2026-10-01", "2026-10-16"],
        valid_tos=[None, None],
    )
    short_inconsistent = _row(
        ["EMPLOYEE:E001", "WORK_ORDER:D"],
        _TYPES,
        valid_froms=["2026-10-01"],
        valid_tos=["2026-09-01"],
    )

    selected = _select_shortest_path([long_consistent, short_inconsistent])
    assert selected is not None
    assert selected[0] == ["EMPLOYEE:E001", "WORK_ORDER:D"]
