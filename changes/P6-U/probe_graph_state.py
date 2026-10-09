"""清点 attendance-demo-v1 状态，判断两个 ingest 脚本的循环依赖怎么破。

只读，不改数据。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KG = "attendance-demo-v1"

QUERIES = [
    ("Entity 总数", "MATCH (e:Entity {kg_version: $kg}) RETURN count(e) AS c"),
    (
        "WORK_TIME_SYSTEM (政策脚本前置)",
        "MATCH (e:Entity {kg_version: $kg, entity_type: $et}) RETURN count(e) AS c",
    ),
    (
        "POLICY_CLAUSE (CSV 桥接前置)",
        "MATCH (e:Entity {kg_version: $kg, entity_type: $et}) RETURN count(e) AS c",
    ),
    (
        "RELATION",
        "MATCH ()-[r:RELATION {kg_version: $kg}]->() RETURN count(r) AS c",
    ),
    (
        "valid_to 非空",
        "MATCH ()-[r:RELATION {kg_version: $kg}]->() "
        "WHERE r.valid_to IS NOT NULL RETURN count(r) AS c",
    ),
    (
        "GOVERNED_BY",
        "MATCH ()-[r:RELATION {kg_version: $kg, relation_type: 'GOVERNED_BY'}]->() "
        "RETURN count(r) AS c",
    ),
    ("Document", "MATCH (d:Document {kg_version: $kg}) RETURN count(d) AS c"),
    ("Chunk", "MATCH (c:Chunk {kg_version: $kg}) RETURN count(c) AS c"),
]

# 前两条需要 entity_type 参数
ENTITY_TYPES = ["WORK_TIME_SYSTEM", "POLICY_CLAUSE"]


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
            print(f"=== {KG} 图状态 ===")
            et_iter = iter(ENTITY_TYPES)
            for label, q in QUERIES:
                params: dict[str, object] = {"kg": KG}
                if "$et" in q:
                    params["et"] = next(et_iter)
                row = ses.run(q, **params).single()
                print(f"  {label}: {int(row['c']) if row else 0}")
    finally:
        driver.close()

    from app.db.session import SessionLocal
    from app.db.models import Document, KgVersion

    with SessionLocal() as db:
        row = db.query(KgVersion).filter(KgVersion.version == KG).first()
        print(f"\n  PG kg_version status: {row.status if row else '<none>'}")
        docs = db.query(Document).all()
        print(f"  PG documents: {len(docs)}")
        for d in docs:
            print(
                f"    {d.id}  status={d.status} "
                f"extract={d.extract_status} kgbuild={d.kg_build_status}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
