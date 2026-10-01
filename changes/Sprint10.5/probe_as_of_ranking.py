"""¥0 诊断：as-of 视图里，候选路径**按现行 sort key 是怎么排的**。

要解决的问题
------------
给了 ``as_of='2025-06-01'``，主链却落在「加班与调休管理办法」（一份 2026 版
文档、无日期）。可能的原因只有两个，修法完全不同，**必须先分清**：

1. **候选里根本没有**当日成立的带日期链 ⇒ 是召回问题（Cypher 过滤太狠）；
2. 候选里有，但输在了 sort key 的**某一维** ⇒ 是排序问题（该提哪一档）。

本探针把每个候选行的**每一维**都打出来，一眼看出属于哪种。

为什么用 monkey-patch 而不是重跑一遍 Cypher 自己算
--------------------------------------------------
``_select_shortest_path`` 收到的是 Cypher 返回的**原始行**；包一层就能拿到它们，
而排序仍然由生产函数自己出结果。自己复算一遍排序等于**复制一份口径**——正是不久前
在 ``probe_current_view_composition.py`` 第一版犯过的错（漏了 ``_temporal_view``
谓词，把"全图存在"当成"视图可达"，错报 37 条失效末端）。这里只做打印，不做判断。

用法::

    uv run python changes/Sprint10.5/probe_as_of_ranking.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
import app.services.reasoning as reasoning  # noqa: E402
from app.services.reasoning import (  # noqa: E402
    ALL_TERMINAL_TYPES,
    HUB_EMPLOYEE_TYPE,
    PRIORITY_TERMINAL_TYPES,
    TERMINAL_PRIORITY_TYPE,
    _TERMINAL_RANK,
    _row_temporal_verdict,
    _select_shortest_path,
    resolve_anchors,
)

KG = "attendance-demo-v1"
QUESTION = "李静的缺卡该怎么处理？"
AS_OF = "2025-06-01"

Q_ORG = """
MATCH (n:Entity {kg_version: $kg})
WHERE n.org_id IS NOT NULL
RETURN n.org_id AS org_id, count(*) AS c
ORDER BY c DESC
LIMIT 1
"""


def _dims(row: object) -> tuple[object, ...]:
    """按生产口径算出该行的排序维度（**只用于打印**，不参与选择）。"""
    types = list(row["types"] or [])  # type: ignore[index]
    terminal = str(types[-1]) if types else ""
    rels = list(row["rels"] or [])  # type: ignore[index]
    return (
        0 if terminal == TERMINAL_PRIORITY_TYPE else 1,
        _TERMINAL_RANK.get(terminal, len(_TERMINAL_RANK)),
        len(rels),
        _row_temporal_verdict(row),
        str(types[-1]) if types else "",
        str(list(row["names"] or [])[-1]) if list(row["names"] or []) else "",  # type: ignore[index]
    )


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    captured: list[list[object]] = []

    def spy(rows: list[object], as_of: str | None = None) -> object:
        captured.append(list(rows))
        return _select_shortest_path(rows, as_of=as_of)

    reasoning._select_shortest_path = spy  # type: ignore[assignment]
    try:
        with driver.session(database=settings.neo4j_database) as session:
            org_id = str(session.run(Q_ORG, kg=KG).single()["org_id"])
            anchors = resolve_anchors(
                session=session,
                kg_version=KG,
                org_id=org_id,
                question=QUESTION,
                nodes=[],
            )
            hops = reasoning.build_reasoning_path(
                session=session,
                kg_version=KG,
                org_id=org_id,
                question=QUESTION,
                nodes=[],
                as_of=AS_OF,
            )
    finally:
        driver.close()
        reasoning._select_shortest_path = _select_shortest_path  # type: ignore[assignment]

    rows = captured[0] if captured else []
    print(f"=== {KG} / {QUESTION} / as_of={AS_OF} ===")
    print(f"锚点 {list(anchors)}｜候选 {len(rows)} 行")

    picked_names = [hop.target.name for hop in hops]
    print(f"生产选中的链：{' → '.join(picked_names) if picked_names else '(空)'}")

    scored = sorted(  # 与生产 sort key 同序，用于**展示位次**
        enumerate(rows),
        key=lambda pair: _dims(pair[1])[:4],
    )
    print("\n=== 候选按现行口径排序（前 12）===")
    print("  #   prio rank hops verdict        终点类型                终点名")
    for position, (index, row) in enumerate(scored[:12], start=1):
        prio, rank, hops_count, verdict, terminal, tail = _dims(row)
        mark = "★" if tail == (picked_names[-1] if picked_names else None) else " "
        print(
            f"  {mark}{position:<3} {prio}    {rank:<3}  {hops_count}    {verdict:<12}"
            f"  {terminal:<22} {tail}"
        )

    dated = [
        (index, row)
        for index, row in enumerate(rows)
        if (list(row["valid_froms"] or []) or [None])[-1]  # type: ignore[index]
        or (list(row["valid_tos"] or []) or [None])[-1]  # type: ignore[index]
    ]
    print(f"\n=== 末端最后一跳**带日期**的候选：{len(dated)} 行 ===")
    print("  #   prio rank hops verdict        终点类型                终点名")
    for index, row in dated[:12]:
        prio, rank, hops_count, verdict, terminal, tail = _dims(row)
        best = next(
            (pos for pos, (idx, _r) in enumerate(scored, start=1) if idx == index),
            None,
        )
        print(
            f"  {best:<4} {prio}    {rank:<3}  {hops_count}    {verdict:<12}"
            f"  {terminal:<22} {tail}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
