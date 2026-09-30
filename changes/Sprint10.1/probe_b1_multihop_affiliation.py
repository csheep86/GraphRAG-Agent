"""S10 批次 B 真机验收：多跳链的**域覆盖**（只读，不依赖 PG）。

两组对照，缺一不可（避免"改了个常量就说生效"，也免得顾此失彼）：

1. **关联方域 `affiliation-demo-v1`**：旧口径（考勤白名单 + 只走 `:RELATION`）
   vs 新口径（并集白名单 + 边类型不限定）⇒ 期望 旧 0 行 / 新 ≥1 行；
2. **考勤域 `attendance-demo-v1`**：同样两口径对照 ⇒ 期望**不 regression**
   （旧有链时新也有链，且首选链一致）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402
from app.services.reasoning import (  # noqa: E402
    ALL_TERMINAL_TYPES,
    HUB_EMPLOYEE_TYPE,
    PRIORITY_TERMINAL_TYPES,
    TERMINAL_ENTITY_TYPES,
    _CYPHER_PATHS,
)

#: 旧口径 Cypher（批次 B 前的样子，逐字复刻：只走 `:RELATION`、单优先类型）
_CYPHER_OLD = """
MATCH p = (a:Entity {kg_version: $kg, org_id: $org})
          -[rels:RELATION*1..3]-
          (b:Entity {kg_version: $kg, org_id: $org})
WHERE a.id IN $anchor_ids
  AND b.entity_type IN $terminal_types
  AND ALL(r IN rels WHERE r.kg_version = $kg AND r.org_id = $org)
  AND none(n IN nodes(p)[1..-1] WHERE n.entity_type = $hub)
RETURN [n IN nodes(p) | n.id] AS ids,
       [n IN nodes(p) | n.canonical_name] AS names,
       [n IN nodes(p) | n.entity_type] AS types,
       [r IN relationships(p) | r.relation_type] AS rels
ORDER BY (CASE WHEN types[-1] = $prio_type THEN 0 ELSE 1 END),
         size(rels),
         ids[-1]
LIMIT $limit
"""

CASES = (
    ("affiliation-demo-v1", "SUBJECT"),
    ("attendance-demo-v1", "EMPLOYEE"),
)


def _first(row: dict) -> str:
    return " -> ".join(
        f"{t}:{n}" for t, n in zip(row["types"], row["names"])
    ) + f"  rels={row['rels']}"


def main() -> None:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        for version, anchor_type in CASES:
            org_row = session.run(
                "MATCH (e:Entity {kg_version: $v}) WHERE e.org_id IS NOT NULL "
                "RETURN e.org_id AS org LIMIT 1",
                v=version,
            ).single()
            anchors = [
                r["id"]
                for r in session.run(
                    "MATCH (e:Entity {kg_version: $v, entity_type: $t}) "
                    "RETURN e.id AS id LIMIT 3",
                    v=version,
                    t=anchor_type,
                )
            ]
            if org_row is None or not anchors:
                print(f"[{version}] 取不到 org_id 或 {anchor_type} 锚点，跳过")
                continue
            org = org_row["org"]

            old = list(
                session.run(
                    _CYPHER_OLD,
                    kg=version,
                    org=org,
                    anchor_ids=anchors,
                    terminal_types=list(TERMINAL_ENTITY_TYPES),
                    hub=HUB_EMPLOYEE_TYPE,
                    prio_type="POLICY_CLAUSE",
                    limit=20,
                )
            )
            new = list(
                session.run(
                    _CYPHER_PATHS,
                    kg=version,
                    org=org,
                    anchor_ids=anchors,
                    terminal_types=list(ALL_TERMINAL_TYPES),
                    hub=HUB_EMPLOYEE_TYPE,
                    prio_types=list(PRIORITY_TERMINAL_TYPES),
                    limit=20,
                )
            )
            print(f"\n[{version}] 锚点 {len(anchors)} 个（{anchor_type}）")
            print(f"  旧口径: {len(old)} 行")
            if old:
                print(f"    首选: {_first(old[0])}")
            print(f"  新口径: {len(new)} 行")
            for row in new[:3]:
                print(f"    {len(row['rels'])} 跳: {_first(row)}")


if __name__ == "__main__":
    main()
