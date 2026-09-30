"""批次 E：只看 4 份**制度文档**（title 为 null 的那些）的全部 chunk 正文。

用途：换版出题时照着正文登记出处；顺带查重复 chunk（e1 里发现两条 chunk 文本完全相同）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSION = "attendance-demo-v1"
CHARS = 700


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            docs = session.run(
                "MATCH (d:Document {kg_version:$v}) WHERE d.title IS NULL "
                "RETURN d.id AS id",
                v=VERSION,
            ).data()
            print(f"制度文档（无标题）{len(docs)} 篇\n")

            all_texts: dict[str, int] = {}
            for doc in docs:
                rows = session.run(
                    "MATCH (d:Document {kg_version:$v})-[:HAS_CHUNK]->(c:Chunk) "
                    "WHERE d.id=$did RETURN c.id AS cid, c.text AS text, "
                    "c.char_start AS cs ORDER BY c.char_start",
                    v=VERSION,
                    did=doc["id"],
                ).data()
                print(f"===== doc={str(doc['id'])[:8]}  chunks={len(rows)} =====")
                for row in rows:
                    text = (row["text"] or "").replace("\n", " ")
                    all_texts[text] = all_texts.get(text, 0) + 1
                    print(f"  [{str(row['cid'])[:18]}] cs={row['cs']} {text[:CHARS]}")
                print()

            dup = {t: n for t, n in all_texts.items() if n > 1}
            print(f"重复正文的 chunk 组数: {len(dup)}")
            for text, n in list(dup.items())[:5]:
                print(f"  x{n}: {text[:80]}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
