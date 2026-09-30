"""批次 E：为评测集换版（v3，attendance 域）勘察语料。

v2 题集冻结在 v-s71a-fe1c4dc3，但该版本在 Neo4j 上已无 chunk ⇒ 题集失效。
换版前必须**照着 chunk 正文出题**（v2 的纪律：每题登记出处 + 期望答案要点，
且出处经 chunk 正文命中核对），否则又是"凭印象出题 ⇒ 拒答口径失真"。

输出：每篇文档的前若干 chunk 正文，供人工出题时核对出处。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSION = "attendance-demo-v1"
PER_DOC = 3
CHARS = 320


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            docs = session.run(
                "MATCH (d:Document {kg_version:$v}) "
                "OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk) "
                "RETURN d.id AS id, d.title AS title, d.doc_type AS dtype, "
                "d.source_type AS stype, count(c) AS chunks "
                "ORDER BY coalesce(d.title, '~')",
                v=VERSION,
            ).data()
            print(f"kg_version={VERSION}  文档 {len(docs)} 篇")
            for doc in docs:
                print(
                    f"\n=== {doc['title'] or '(无标题)'} | id={str(doc['id'])[:8]} "
                    f"type={doc['dtype']} src={doc['stype']} chunks={doc['chunks']}"
                )
                rows = session.run(
                    "MATCH (d:Document {kg_version:$v})-[r:HAS_CHUNK]->(c:Chunk) "
                    "WHERE d.id=$did RETURN c.id AS cid, c.text AS text, "
                    "c.char_start AS cs, c.char_end AS ce ORDER BY r.index LIMIT $n",
                    v=VERSION,
                    did=doc["id"],
                    n=PER_DOC,
                ).data()
                for row in rows:
                    text = (row["text"] or "").replace("\n", " ")[:CHARS]
                    print(f"  [{str(row['cid'])[:20]}] ({row['cs']},{row['ce']}) {text}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
