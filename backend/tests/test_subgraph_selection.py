"""Sprint 10 批次 C：``select_subgraph_nodes``（问答子图选谁进 Prompt）。

钉死裁决 D-I 的口径：**按类型保底 + 组内度数降序 + 余量按度数补齐**。

反面教材都写在被测函数的 docstring 里（无序截断 → 锚点召回 50%；全局度数降序
→ ``LEAVE`` 掉到 0）。这些用例就是防止有人"顺手改回排序"——那样改看起来更
简单，实测却会让问句里的具体员工 / 工单从候选集里消失（R12 事故同款）。
"""

from __future__ import annotations

import random

from app.services.graphs import select_subgraph_nodes


def test_every_type_gets_a_floor_share() -> None:
    """类型数 > 名额时，每类型**至少 1 个**（小类型不被饿死）。

    floor = limit // 类型数 = 50 // 60 = 0 ⇒ 保底抬到 1 ⇒ 正好 50 个类型各 1 个。
    """
    rows = [(f"T{i}:E{j}", f"T{i}", j) for i in range(60) for j in range(3)]

    chosen = select_subgraph_nodes(rows, 50)

    assert len(chosen) == 50
    assert len({node_id.split(":")[0] for node_id in chosen}) == 50


def test_small_type_is_not_crowded_out_by_large_type() -> None:
    """大类型占绝大多数时，小类型仍按保底进候选集（不是按占比被稀释）。"""
    rows = [(f"EMPLOYEE:E{i}", "EMPLOYEE", 3) for i in range(100)]
    rows += [("LEAVE:L1", "LEAVE", 1), ("LEAVE:L2", "LEAVE", 0)]

    chosen = select_subgraph_nodes(rows, 50)

    # 2 个类型 ⇒ floor = 25 ⇒ LEAVE 全部 2 个都在（若按占比分配只剩 1 个）
    assert sorted(c for c in chosen if c.startswith("LEAVE:")) == [
        "LEAVE:L1",
        "LEAVE:L2",
    ]
    assert len(chosen) == 50


def test_within_type_ordered_by_degree_then_id() -> None:
    """组内按**度数降序**，平局按 id 升序（同输入必同解）。"""
    rows = [("A:x", "A", 1), ("A:z", "A", 5), ("A:y", "A", 5)]

    chosen = select_subgraph_nodes(rows, 2)

    assert chosen == ["A:y", "A:z"]


def test_leftover_slots_are_filled_by_degree() -> None:
    """保底取完后名额没用完 ⇒ 按全局度数补齐（不浪费 Prompt 预算）。"""
    rows = [("A:a", "A", 1), ("B:c", "B", 8), ("B:b", "B", 9)]

    chosen = select_subgraph_nodes(rows, 3)

    assert chosen == ["A:a", "B:b", "B:c"]


def test_deterministic_regardless_of_input_order() -> None:
    """结果只取决于数据，**不**取决于 Neo4j 返回顺序（否则同一问题两次答案不同）。"""
    rows = [(f"T{i % 7}:E{i}", f"T{i % 7}", i % 5) for i in range(40)]
    shuffled = list(rows)
    random.Random(20260929).shuffle(shuffled)

    assert select_subgraph_nodes(rows, 12) == select_subgraph_nodes(shuffled, 12)


def test_empty_rows_and_nonpositive_limit() -> None:
    """空输入 / 非正上限 ⇒ 空列表（不抛、不返回"随便几个"）。"""
    assert select_subgraph_nodes([], 10) == []
    assert select_subgraph_nodes([("A:a", "A", 1)], 0) == []
    assert select_subgraph_nodes([("A:a", "A", 1)], -1) == []
