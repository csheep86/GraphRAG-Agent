"""批次 E：换版出题素材——每份文档只取「够出题」的最小信息。

- 制度文档：首段前 260 字符（拿到文件名 + 文件编号 + 生效日期，供出题登记出处）
- CSV：1 条样例 chunk（拿到列名与首行，供出「查某人/某记录」的数据题）
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
            docs = session.run(
                "MATCH (d:Document {kg_version:$v}) RETURN d.id AS id, d.title AS t",
                v=VERSION,
            ).data()
            for doc in docs:
                title = doc["t"]
                rows = session.run(
                    "MATCH (d:Document {kg_version:$v})-[:HAS_CHUNK]->(c:Chunk) "
                    "WHERE d.id=$did RETURN c.text AS text ORDER BY c.char_start LIMIT 1",
                    v=VERSION,
                    did=doc["id"],
                ).data()
                if not rows:
                    continue
                text = (rows[0]["text"] or "").replace("\n", " ")
                label = title or "(制度)"
                print(f"--- {label} [{str(doc['id'])[:8]}]")
                print(f"    {text[:260]}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
