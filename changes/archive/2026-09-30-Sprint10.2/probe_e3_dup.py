"""批次 E 新发现：chunk 重复入库的量化。

e2 里看到制度文档 6 chunks 实为 **2 段正文各 3 份**（重复正文 11 组）。
怀疑是 ingest 脚本多次重跑、chunk id 每次新生成 ⇒ 未按 (doc, char_start) 幂等。

影响面要量化清楚再决定修不修：
- 若只有制度文档重复 ⇒ 影响"每文档保底"的名额浪费；
- 若 CSV 也重复 ⇒ 20 条注入里可能大半是同一段，召回质量被严重稀释。
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
                "MATCH (d:Document {kg_version:$v}) "
                "OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk) "
                "RETURN coalesce(d.title,'(制度)') AS title, d.id AS id, "
                "count(c) AS total, count(DISTINCT c.text) AS uniq, "
                "count(DISTINCT c.char_start) AS uniq_start "
                "ORDER BY title",
                v=VERSION,
            ).data()
            print(f"kg_version={VERSION}")
            print(f"{'文档':<28}{'chunk':>7}{'去重后':>8}{'正文重复':>10}")
            tot = uniq = 0
            for row in docs:
                dup = row["total"] - row["uniq"]
                tot += row["total"]
                uniq += row["uniq"]
                flag = "  <== 有重复" if dup else ""
                print(
                    f"  {row['title'][:26]:<28}{row['total']:>7}{row['uniq']:>8}"
                    f"{dup:>10}{flag}"
                )
            print(f"\n合计 chunk {tot} / 去重后 {uniq} / 重复 {tot - uniq}")

            # 重复是否同 char_start（=同一文档同一段被写了多次）
            rows = session.run(
                "MATCH (d:Document {kg_version:$v})-[:HAS_CHUNK]->(c:Chunk) "
                "WITH d, c.char_start AS cs, collect(c.id) AS ids, count(*) AS n "
                "WHERE n > 1 RETURN coalesce(d.title,'(制度)') AS t, cs, n, "
                "ids ORDER BY n DESC LIMIT 8",
                v=VERSION,
            ).data()
            print(f"\n同一 (doc, char_start) 下的 chunk：{len(rows)} 组（最多列 8）")
            for row in rows:
                print(
                    f"  {row['t'][:20]:<22} cs={row['cs']} x{row['n']} "
                    f"{[str(i)[:14] for i in row['ids']]}"
                )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
