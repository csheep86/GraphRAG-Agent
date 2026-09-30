"""批次 E：重复实体清理**之后**的验收——光看总数对账还不够。

``fix_dup_entities.py`` 的对账只比了总数（实体 2795→2792、MENTIONS 364→361、
RELATION 3667→3667）。RELATION **一条没变**这件事必须解释清楚：
它既可能是"边的端点迁走了、旧边删了，净 0"，也可能是"边根本没迁走、直接被 DETACH 删了"
（后者就是**静默丢证据**，比不清理更糟）。

这里逐项验：
1. 保留实体现在挂几条边、都是什么类型（清理前每个是 2 条）；
2. 被删的 3 个 id 是否真的不存在了；
3. 有没有造出**并行边**（同端点对 + 同类型 + 同 kg_version 却有多条）——
   迁边时最容易犯的错；
4. 有没有**孤儿边**（指向已删实体）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSION = "attendance-demo-v1"
KEPT = ("ent_88239c648e6b", "ent_41081deb3c41")
DELETED = ("ent_d756786ccc36", "ent_e53743dd4dd7", "ent_f77611c55c5f")


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            print("=== 1. 保留实体的边 ===")
            for entity_id in KEPT:
                edges = session.run(
                    "MATCH (e:Entity {id:$id})-[r]-(o) "
                    "RETURN type(r) AS t, "
                    "CASE startNode(r).id WHEN $id THEN 'out' ELSE 'in' END AS dir, "
                    "labels(o) AS lo, o.id AS oid",
                    id=entity_id,
                ).data()
                print(f"  {entity_id}: {len(edges)} 条")
                for edge in edges:
                    print(
                        f"      -[{edge['t']} {edge['dir']}]- "
                        f"{'/'.join(edge['lo'])}:{str(edge['oid'])[:20]}"
                    )

            print("\n=== 2. 被删 id 是否还在 ===")
            for entity_id in DELETED:
                n = session.run(
                    "MATCH (e:Entity {id:$id}) RETURN count(e) AS n", id=entity_id
                ).single()["n"]
                print(f"  {entity_id}: {'仍在（未删掉！）' if n else '已删除 ✔'}")

            print("\n=== 3. 并行边（同端点对 + 同类型，条数 > 1）===")
            parallel = session.run(
                "MATCH (a:Entity {kg_version:$v})-[r]->(b:Entity {kg_version:$v}) "
                "WITH a.id AS s, type(r) AS t, b.id AS d, count(r) AS n "
                "WHERE n > 1 RETURN s, t, d, n ORDER BY n DESC LIMIT 10",
                v=VERSION,
            ).data()
            total_parallel = sum(row["n"] - 1 for row in parallel)
            print(f"  并行边组 {len(parallel)}，多出 {total_parallel} 条")
            for row in parallel:
                print(f"    {row['s'][:14]} -[{row['t']}]-> {row['d'][:14]} x{row['n']}")

            print("\n=== 4. 孤儿：指向已删实体的边 ===")
            orphan = session.run(
                "MATCH ()-[r]->(e:Entity) WHERE e.kg_version IS NULL "
                "RETURN count(r) AS n"
            ).single()["n"]
            print(f"  悬空（目标无 kg_version）边: {orphan}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
