"""批次 E 遗留面：**实体 / 关系 id 同样是随机 uuid**（chunk 已修，这两个没修）。

``langextract.py`` 里实体 id = ``ent_{uuid4().hex[:12]}``、关系 id = ``rel_{uuid4().hex[:12]}``，
与已修的 chunk id 是**同一族问题**：重跑 ingest ⇒ 写侧 ``MERGE`` 按 id 去重失效 ⇒
图上实体 / 关系节点随重跑次数**线性膨胀**（chunk 那次实测：230 → 去重后 205）。

本探针只量化，不改：
1. 每个 kg_version 里「同名同类型」的实体有多少组重复、多出多少节点；
2. 关系是否也重复（按 端点 + 类型）；
3. 顺带看 affiliation-demo-v1 有没有同样的病（它是否也被重跑过）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            versions = [
                row["v"]
                for row in session.run(
                    "MATCH (n:Entity) RETURN DISTINCT n.kg_version AS v"
                ).data()
            ]
            for version in versions:
                total = session.run(
                    "MATCH (e:Entity {kg_version:$v}) RETURN count(e) AS n", v=version
                ).single()["n"]
                # 实体名键：canonical_name 优先，其次 name
                rows = session.run(
                    "MATCH (e:Entity {kg_version:$v}) "
                    "WITH coalesce(e.canonical_name, e.name) AS k, e.entity_type AS t, "
                    "count(e) AS n WHERE n > 1 AND k IS NOT NULL "
                    "RETURN k, t, n ORDER BY n DESC LIMIT 8",
                    v=version,
                ).data()
                extra = session.run(
                    "MATCH (e:Entity {kg_version:$v}) "
                    "WITH coalesce(e.canonical_name, e.name) AS k, "
                    "e.entity_type AS t, count(e) AS n WHERE n > 1 AND k IS NOT NULL "
                    "RETURN sum(n - 1) AS extra, count(*) AS groups",
                    v=version,
                ).single()
                print(f"\n=== {version}  实体 {total}")
                print(
                    f"  同名同类型重复组 {extra['groups']}  "
                    f"多出节点 {extra['extra']}"
                    + ("" if extra["extra"] else "  （干净）")
                )
                for row in rows:
                    print(f"    {str(row['k'])[:24]:<26} {row['t']:<18} x{row['n']}")

                rel = session.run(
                    "MATCH (a:Entity {kg_version:$v})-[r:RELATION]->"
                    "(b:Entity {kg_version:$v}) "
                    "WITH a.id AS s, b.id AS t, r.relation_type AS rt, count(r) AS n "
                    "WHERE n > 1 RETURN sum(n - 1) AS extra, count(*) AS groups",
                    v=version,
                ).single()
                print(
                    f"  关系重复（同端点同类型）: 组 {rel['groups']} 多出 {rel['extra']}"
                )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
