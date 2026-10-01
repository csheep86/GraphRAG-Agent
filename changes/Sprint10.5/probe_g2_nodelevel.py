"""G2 定音：用**纯 Cypher + 按节点 id** 复核 inconsistent 链到底存不存在。

前面 ``probe_g2_why.py`` 的邻域是按 ``canonical_name`` 匹配的，会把**同名不同 id**
的实体（例如 CSV 侧的 ``WORK_TIME_SYSTEM:综合计算工时制`` 与政策侧抽取的同名
``ent_*``）的边混在一起来看，于是"看着像有冲突链"。能否真的构成链，取决于
两条边是否挂在**同一个节点 id** 上。这里不做任何名字匹配，直接让 Cypher 判决。

只读。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KG = "attendance-demo-v1"

# 全程用 id 判定；maxFrom/minTo 纯 Cypher 算出（不依赖 Python 侧逻辑）
Q_CHAINS = """
MATCH (a:Entity {kg_version:$kg})-[r1]-(m:Entity {kg_version:$kg})-[r2]-(b:Entity {kg_version:$kg})
WHERE r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND (r1.valid_to IS NOT NULL OR r2.valid_to IS NOT NULL)
WITH a, m, b, r1, r2,
     toString(r1.valid_from) AS f1, toString(r2.valid_from) AS f2,
     [x IN [r1.valid_to, r2.valid_to] WHERE x IS NOT NULL | toString(x)] AS tos
WITH a, m, b, r1, r2, f1, f2, tos,
     (CASE WHEN f1 > f2 THEN f1 ELSE f2 END) AS maxFrom,
     reduce(mn = tos[0], t IN tos | CASE WHEN t < mn THEN t ELSE mn END) AS minTo
WHERE maxFrom > minTo
RETURN m.id AS mid, m.canonical_name AS mname,
       r1.relation_type AS r1t, f1 AS r1from, toString(r1.valid_to) AS r1to,
       r2.relation_type AS r2t, f2 AS r2from, toString(r2.valid_to) AS r2to,
       a.canonical_name AS aname, b.canonical_name AS bname
LIMIT 20
"""

Q_COUNT = """
MATCH (a:Entity {kg_version:$kg})-[r1]-(m:Entity {kg_version:$kg})-[r2]-(b:Entity {kg_version:$kg})
WHERE r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND (r1.valid_to IS NOT NULL OR r2.valid_to IS NOT NULL)
RETURN count(*) AS judgeable
"""

Q_MEETING = """
MATCH (m:Entity {kg_version:$kg})
WHERE EXISTS { MATCH (m)-[r:RELATION {kg_version:$kg}]-() WHERE r.valid_to IS NOT NULL }
  AND EXISTS { MATCH (m)-[r2:RELATION {kg_version:$kg}]-() WHERE r2.valid_from >= '2026-01-01' }
RETURN m.id AS mid, m.canonical_name AS name
LIMIT 20
"""

Q_DUPNAME = """
MATCH (e:Entity {kg_version:$kg})
WHERE e.canonical_name = '综合计算工时制'
RETURN e.id AS id, elementId(e) AS eid
LIMIT 10
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
            judgeable = int(ses.run(Q_COUNT, kg=KG).single()["judgeable"])
            print(f"可判定 2 跳链：{judgeable}")

            rows = list(ses.run(Q_CHAINS, kg=KG))
            print(f"\n=== Cypher 直接判 inconsistent 的链：{len(rows)} 条 ===")
            for i, r in enumerate(rows, 1):
                print(
                    f"  {i}. [{r['aname']}] -{r['r1t']}({r['r1from']}~{r['r1to']})- "
                    f"[{r['mname']}] -{r['r2t']}({r['r2from']}~{r['r2to']})- [{r['bname']}]"
                )

            meets = list(ses.run(Q_MEETING, kg=KG))
            print(
                "\n=== 同时挂载【已失效边】与【2026 起始边】的节点（必须同 id）："
                f"{len(meets)} 个 ==="
            )
            for r in meets:
                print(f"    {r['mid']}  {r['name']}")

            dups = list(ses.run(Q_DUPNAME, kg=KG))
            print(f"\n=== 名为『综合计算工时制』的节点数：{len(dups)} 个 ===")
            for r in dups:
                print(f"    {r['id']}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
