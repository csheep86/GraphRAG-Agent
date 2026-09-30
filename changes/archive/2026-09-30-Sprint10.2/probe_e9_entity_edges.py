"""批次 E：清重复实体前的**边结构勘察**——先看清怎么连，再动手删。

清理要把被删实体的边 **MERGE 到保留实体**上，前提是知道：
1. 与 ``:Entity`` 相连的**关系类型**都有哪些；
2. 各自**方向**是什么（写反了 MERGE 就是空操作 ⇒ 边随节点一起被 DETACH 删掉，
   等于静默丢证据，比不清理更糟）；
3. 这些关系带哪些**属性**（MERGE 时必须原样带上，否则会造出"半条边"）。

顺带把严格判据下的重复实体明细列出来（含 id / mention / 偏移），供清理脚本对账。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSION = "attendance-demo-v1"


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            print("=== 与 :Entity 相连的关系（类型 / 方向 / 属性 / 条数）===")
            rows = session.run(
                "MATCH (a)-[r]->(b) WHERE 'Entity' IN labels(a) OR 'Entity' IN labels(b) "
                "RETURN type(r) AS t, labels(a) AS la, labels(b) AS lb, "
                "count(r) AS n, collect(DISTINCT keys(r)) AS key_sets ORDER BY n DESC"
            ).data()
            for row in rows:
                print(
                    f"  ({'/'.join(row['la'])})-[{row['t']}]->"
                    f"({'|'.join(row['lb'])})  n={row['n']}  keys={row['key_sets']}"
                )

            print("\n=== 严格判据下的重复实体明细 ===")
            dups = session.run(
                "MATCH (e:Entity {kg_version:$v}) "
                "WITH coalesce(e.canonical_name, e.name) AS k, e.entity_type AS t, "
                "e.char_start AS cs, e.char_end AS ce, collect(e.id) AS ids "
                "WHERE size(ids) > 1 AND k IS NOT NULL AND cs IS NOT NULL "
                "RETURN k, t, cs, ce, ids ORDER BY size(ids) DESC",
                v=VERSION,
            ).data()
            for row in dups:
                print(
                    f"  {str(row['k'])[:20]:<22}{row['t']:<18}"
                    f"[{row['cs']},{row['ce']})  保留={sorted(row['ids'])[0]}  "
                    f"删={sorted(row['ids'])[1:]}"
                )

            print("\n=== 各重复实体当前挂着几条边 ===")
            for row in dups:
                for entity_id in row["ids"]:
                    n = session.run(
                        "MATCH (e:Entity {id:$id})-[r]-() RETURN count(r) AS n",
                        id=entity_id,
                    ).single()["n"]
                    print(f"    {entity_id}  边 {n}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
