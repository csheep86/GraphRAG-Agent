"""Sprint 4.10.4 证据探针：只读 Neo4j，查 Entity.org_id 分布 + 节点总览。"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
with driver.session(database="neo4j") as s:
    print("=== [证据 3] Entity.org_id 分布 ===")
    r = s.run(
        "MATCH (e:Entity) "
        "RETURN coalesce(toString(e.org_id), '<<NULL>>') AS org_id_value, "
        "       count(*) AS cnt "
        "ORDER BY cnt DESC"
    )
    for row in r:
        print(f"  org_id={row['org_id_value']!r}: cnt={row['cnt']}")
    print()

    print("=== 辅助：KgVersion 状态 ===")
    r = s.run(
        "MATCH (k:KgVersion) "
        "RETURN coalesce(k.status, '<<NULL>>') AS status, count(*) AS cnt "
        "ORDER BY cnt DESC"
    )
    for row in r:
        print(f"  status={row['status']!r}: cnt={row['cnt']}")
    print()

    print("=== 辅助：Document / Chunk / Evidence / HAS_CHUNK 关系总数 ===")
    for lbl in ["Document", "Chunk", "Evidence"]:
        cnt = s.run(f"MATCH (n:{lbl}) RETURN count(n) AS n").single()["n"]
        print(f"  {lbl}: {cnt}")
    rel_cnt = s.run(
        "MATCH ()-[r:HAS_CHUNK]->() RETURN count(r) AS n"
    ).single()["n"]
    print(f"  HAS_CHUNK: {rel_cnt}")
    rel_cnt2 = s.run(
        "MATCH ()-[r:MENTIONS]->() RETURN count(r) AS n"
    ).single()["n"]
    print(f"  MENTIONS: {rel_cnt2}")

driver.close()