"""L2-③ 全生命周期 as-of：**同一句问话，两个时点，落的条款是否换了一代**。

这是 Sprint 10.5 里唯一能直接证伪 ③ 的探针，判据只有一个：

    as_of = None（当前）      ⇒ 末端应落在 **2026 版**条款（valid_from=2026-01-01）
    as_of = '2025-06-01'      ⇒ 末端应落在 **2025 版**条款（valid_to=2025-12-31）

两个时点落到**同一个条款** ⇒ ③ 没实现（过滤没生效）；
落到不同条款 ⇒ 过滤生效，且方向符合"2025 年问话只能得到当年生效的条款"。

为什么直接调 ``build_reasoning_path`` 而不是跑整个 ``POST /agent/query``：
本探针要量的是**检索层**的时态过滤是否生效，与 LLM 措辞无关；
整个问答链路每跑一次要花 token，而 LLM 侧尚未区分时点（属下一轮改造点）。
锚点走的是 production 同一条 fallback 路径，不是绕过去手挑的。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.reasoning import (  # noqa: E402
    ALL_TERMINAL_TYPES,
    HUB_EMPLOYEE_TYPE,
    PRIORITY_TERMINAL_TYPES,
    build_reasoning_path,
    resolve_anchors,
)
from app.services.reasoning import _cypher_paths, _date_text  # noqa: E402

KG = "attendance-demo-v1"

Q_ORG = """
MATCH (n:Entity {kg_version: $kg})
WHERE n.org_id IS NOT NULL
RETURN n.org_id AS org_id, count(*) AS c
ORDER BY c DESC
LIMIT 1
"""

#: 李静缺卡 —— 演示台上两代条款差异正好落在"外勤缺卡由手工补卡 → 自动补卡"
QUESTION = "李静的缺卡该怎么处理？"

#: 两个时点：2025 年中（当时只有 2025 版有效）与"当前"（2026 版已施行）
TIMEPOINTS: tuple[tuple[str, str | None], ...] = (
    ("当前（不给 as_of）", None),
    ("2025-06-01", "2025-06-01"),
    ("2026-06-01", "2026-06-01"),
)


def _hop_line(hop: Any) -> str:  # noqa: ANN401 - Neo4j 侧对象无稳定类型
    return (
        f"{hop.source.name} -[{hop.relation} "
        f"{hop.valid_from or '<none>'}~{hop.valid_to or '<none>'}]-> "
        f"{hop.target.name}"
    )


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            org_row = session.run(Q_ORG, kg=KG).single()
            if org_row is None:
                print(f"[FAIL] 版 {KG} 里没有带 org_id 的节点")
                return 1
            org_id = str(org_row["org_id"])
            results: dict[str, tuple[str, list[Any]]] = {}
            for label, as_of in TIMEPOINTS:
                hops = build_reasoning_path(
                    session=session,
                    kg_version=KG,
                    org_id=org_id,
                    question=QUESTION,
                    # 子图留空 ⇒ 走 production 的 fallback 锚点查询（同一条真实路径）
                    nodes=[],
                    as_of=as_of,
                )
                results[label] = (as_of or "null", hops)
    finally:
        driver.close()

    print(f"=== {KG} / 问句：{QUESTION} ===")
    terminals: dict[str, str | None] = {}
    for label, (as_of, hops) in results.items():
        print(f"\n--- as_of={as_of}（{label}）：{len(hops)} 跳 ---")
        for hop in hops:
            print(f"    {_hop_line(hop)}")
        terminals[label] = hops[-1].target.name if hops else None
        if hops:
            last = hops[-1]
            print(
                f"    末端窗口：valid_from={last.valid_from} valid_to={last.valid_to}"
            )

    # --------------------------------------------------------------- #
    # 候选行诊断：把"过滤没生效"与"生效了但被选链规则藏起来"分开。
    # 只看出选中的那条链无法区分二者（无日期的短链在任何时点都会赢）。
    # --------------------------------------------------------------- #
    print("\n=== 候选行：同一句 Cypher，两个时点的候选集本身变没变 ===")
    candidates: dict[str | None, list[tuple[str, str | None, str | None]]] = {}
    driver2 = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver2.session(database=settings.neo4j_database) as session:
            anchors = resolve_anchors(
                session=session, kg_version=KG, org_id=org_id, question=QUESTION,
                nodes=[],
            )
            for _label, as_of in TIMEPOINTS:
                rows = list(
                    session.run(
                        _cypher_paths(),
                        kg=KG,
                        org=org_id,
                        anchor_ids=list(anchors),
                        terminal_types=list(ALL_TERMINAL_TYPES),
                        hub=HUB_EMPLOYEE_TYPE,
                        prio_types=list(PRIORITY_TERMINAL_TYPES),
                        limit=2000,
                        as_of=as_of,
                    )
                )
                summary = []
                for row in rows:
                    tos = list(row["valid_tos"] or [])
                    froms = list(row["valid_froms"] or [])
                    summary.append(
                        (
                            str(row["names"][-1]),
                            _date_text(froms[-1] if froms else None),
                            _date_text(tos[-1] if tos else None),
                        )
                    )
                candidates[as_of] = summary
    finally:
        driver2.close()

    for as_of, summary in candidates.items():
        dated = [item for item in summary if item[1] or item[2]]
        print(f"\n--- as_of={as_of or 'null'}：候选 {len(summary)} 行，"
              f"其中末端最后一跳带日期 {len(dated)} 行 ---")
        for name, vf, vt in dated[:8]:
            print(f"    {name}  [{vf or '<none>'} ~ {vt or '<none>'}]")

    print("\n=== 判据 ===")
    current = terminals["当前（不给 as_of）"]
    past = terminals["2025-06-01"]
    print(f"  当前       → {current}")
    print(f"  2025-06-01 → {past}")
    if current is None or past is None:
        print("  ❌ 至少一个时点没路径 ⇒ 过滤把链打断了（或锚点没命中）")
        return 1
    if current == past:
        print("  ❌ 两个时点落到同一条款 ⇒ as-of 过滤未生效")
        return 1
    print("  ✅ 两个时点落到不同条款 ⇒ 全生命周期 as-of 生效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
