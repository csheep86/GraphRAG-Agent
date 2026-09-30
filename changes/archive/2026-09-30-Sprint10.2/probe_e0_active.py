"""批次 E 前置勘察：当前 active 版本是哪个域？评测集 v2（冻结在 v-s71a-fe1c4dc3）是否还适用？

背景：eval_controlled_qset.py 的 14 题冻结在**招商局系语料**上（v2-2026-09-26），
而 Sprint 10 真机一直在**考勤域**（attendance-demo-v1）上跑。若两者不同源，
直接跑评测 ⇒ 全拒答 ⇒ 会得出"召回坏了"的**假结论**（v1→v2 换版就是因为踩过这个）。

先 ¥0 勘察：列出图上所有 kg_version 的规模 + 各版本的文档清单，再决定要不要换版。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

QSET_KG_VERSION = "v-s71a-fe1c4dc3"


def main() -> None:
    settings = get_settings()
    print(f"DATABASE_URL  : {settings.database_url}")
    print(f"NEO4J_URI     : {settings.neo4j_uri}")

    # ---- 1. SQLite 侧：谁是 active（ready） ----
    db_path = settings.database_url.replace("sqlite:///", "")
    if not Path(db_path).is_absolute():
        db_path = str(BACKEND / db_path)
    print(f"\n--- SQLite ({db_path}) ---")
    try:
        conn = sqlite3.connect(db_path)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND (name LIKE '%version%' OR name LIKE '%kg%')"
            )
        ]
        print(f"相关表: {tables}")
        for table in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            print(f"  {table}: {cols}")
            rows = conn.execute(f"SELECT * FROM {table} LIMIT 10").fetchall()
            for row in rows:
                print(f"    {row}")
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] {type(exc).__name__}: {exc}")

    # ---- 2. Neo4j 侧：每个版本的规模 + 文档清单 ----
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            rows = session.run(
                "MATCH (c:Chunk) RETURN c.kg_version AS v, count(*) AS n "
                "ORDER BY n DESC"
            ).data()
            print("\n--- Neo4j：各 kg_version 的 Chunk 数 ---")
            for row in rows:
                mark = "  <== 评测集冻结版本" if row["v"] == QSET_KG_VERSION else ""
                print(f"  {row['v']}: {row['n']} chunks{mark}")

            for row in rows:
                version = row["v"]
                docs = session.run(
                    "MATCH (d:Document {kg_version:$v}) RETURN d.title AS t, d.id AS id "
                    "ORDER BY t",
                    v=version,
                ).data()
                spans = session.run(
                    "MATCH (e:Entity {kg_version:$v}) WHERE e.char_start IS NOT NULL "
                    "RETURN count(e) AS n",
                    v=version,
                ).single()["n"]
                print(
                    f"\n  [{version}] 文档 {len(docs)} / 带 span 实体 {spans}"
                )
                for doc in docs:
                    print(f"    - {doc['t']}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
