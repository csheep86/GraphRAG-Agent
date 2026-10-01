"""诊断：干净图上为什么 inconsistent = 0。

G2 靠 2 跳链成立——边上既要有 ``valid_from`` 又要有一跳带 ``valid_to``，
且 ``max(valid_from) > min(valid_to)``。重放后判定链从 254 降到 152、inconsistent 归零，
必须分清两种可能：

- A：Hist依赖的实体/边本就不该存在（那 2 条依赖历史累积 ⇒ 归零是正确的）；
- B：重放漏了东西（例如政策侧带 2026-01-01 的桥接边没进来 ⇒ 需要补）。

所以本探针不做判定，只把「已失效边的端点，另一端还挂着哪些 valid_from」摊开看。

只读。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KG = "attendance-demo-v1"

Q_EXPIRED = """
MATCH (a:Entity {kg_version: $kg})-[r:RELATION {kg_version: $kg}]->(b:Entity {kg_version: $kg})
WHERE r.valid_to IS NOT NULL
RETURN labels(a) AS al, a.canonical_name AS a_name, r.relation_type AS rt,
       r.valid_from AS vf, r.valid_to AS vt, b.canonical_name AS b_name
ORDER BY rt, a_name LIMIT 30
"""

Q_NEIGHBORS = """
MATCH (n:Entity {kg_version: $kg})-[r:RELATION {kg_version: $kg}]->(m:Entity {kg_version: $kg})
WHERE n.canonical_name = $name
RETURN r.relation_type AS rt, r.valid_from AS vf, r.valid_to AS vt,
       m.canonical_name AS target
ORDER BY rt LIMIT 25
"""

Q_GOVERNED_VALID = """
MATCH ()-[r:RELATION {kg_version: $kg, relation_type: 'GOVERNED_BY'}]->()
RETURN count(r) AS total,
       count(r.valid_from) AS with_valid_from,
       count(r.valid_to) AS with_valid_to
"""

Q_TWO_HOP = """
MATCH (a:Entity {kg_version: $kg})-[r1:RELATION {kg_version: $kg}]->(m:Entity {kg_version: $kg})
     -[r2:RELATION {kg_version: $kg}]->(b:Entity {kg_version: $kg})
WHERE r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND (r1.valid_to IS NOT NULL OR r2.valid_to IS NOT NULL)
RETURN count(*) AS chains
"""


def main() -> int:
    from app.core.config import get_settings
    from neo4j import GraphDatabase

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as ses:
            row = ses.run(Q_GOVERNED_VALID, kg=KG).single()
            print("=== GOVERNED_BY 边的时间字段覆盖 ===")
            print(
                f"  共 {row['total']} 条 / 有 valid_from {row['with_valid_from']} / "
                f"有 valid_to {row['with_valid_to']}"
            )

            print(f"\n=== 可判定 2 跳链总数 ===")
            print("  chains =", int(ses.run(Q_TWO_HOP, kg=KG).single()["chains"]))

            print("\n=== 已失效的边（valid_to 非空，前 30）===")
            expired_targets: list[str] = []
            for r in ses.run(Q_EXPIRED, kg=KG):
                print(
                    f"  [{r['a_name']}] -{r['rt']}-> [{r['b_name']}]  "
                    f"{r['vf']} ~ {r['vt']}"
                )
                for name in (r["a_name"], r["b_name"]):
                    if name and name not in expired_targets:
                        expired_targets.append(name)

            print("\n=== 这些端点还挂着哪些边（找有没有 2026 起始的对侧边）===")
            for name in expired_targets[:8]:
                print(f"\n  -- {name} --")
                for r in ses.run(Q_NEIGHBORS, kg=KG, name=name):
                    print(
                        f"     -{r['rt']}-> [{r['target']}]  "
                        f"{r['vf']} ~ {r['vt']}"
                    )
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
