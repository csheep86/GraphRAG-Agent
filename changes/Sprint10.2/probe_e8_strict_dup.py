"""批次 E：实体重复的**严格**判据（e7 的判据太松，不能直接拿去清数据）。

e7 按「同名 + 同类型」分组得到 2224 个"多出节点"，但**同名 ≠ 重复**：
CSV 结构化抽取里「2026-10-19 正常班」可以是 37 个员工各自的排班（不同的合法实体，
只是名字撞了；它们挂在**不同 chunk / 不同字符偏移**上）。按名字清理会**误删真数据**。

严格判据：``(canonical_name, entity_type, char_start, char_end)`` 全等才算重跑重复——
重跑 ingest 产出的实体，其名称与绝对偏移**逐字相同**；不同行/不同员工的实体偏移必然不同。

同时给出可交叉验证的第二个数：按「同一 chunk + 同一 mention」判重（MENTIONS 视角）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSIONS = ("attendance-demo-v1", "affiliation-demo-v1")


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            for version in VERSIONS:
                total = session.run(
                    "MATCH (e:Entity {kg_version:$v}) RETURN count(e) AS n", v=version
                ).single()["n"]

                strict = session.run(
                    "MATCH (e:Entity {kg_version:$v}) "
                    "WITH coalesce(e.canonical_name, e.name) AS k, e.entity_type AS t, "
                    "e.char_start AS cs, e.char_end AS ce, count(e) AS n "
                    "WHERE n > 1 AND k IS NOT NULL AND cs IS NOT NULL "
                    "RETURN sum(n - 1) AS extra, count(*) AS groups",
                    v=version,
                ).single()
                sample = session.run(
                    "MATCH (e:Entity {kg_version:$v}) "
                    "WITH coalesce(e.canonical_name, e.name) AS k, e.entity_type AS t, "
                    "e.char_start AS cs, count(e) AS n "
                    "WHERE n > 1 AND k IS NOT NULL AND cs IS NOT NULL "
                    "RETURN k, t, cs, n ORDER BY n DESC LIMIT 6",
                    v=version,
                ).data()
                via_chunk = session.run(
                    "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->"
                    "(e:Entity {kg_version:$v}) "
                    "WITH c.id AS cid, coalesce(e.canonical_name, e.name) AS k, "
                    "count(e) AS n WHERE n > 1 "
                    "RETURN sum(n - 1) AS extra, count(*) AS groups",
                    v=version,
                ).single()

                print(f"\n=== {version}  实体 {total}")
                print(
                    f"  严格判据（名+类型+起止偏移全等）: 重复组 {strict['groups']} "
                    f"多出 {strict['extra']}"
                )
                for row in sample:
                    print(
                        f"    {str(row['k'])[:22]:<24}{row['t']:<18}"
                        f"cs={row['cs']} x{row['n']}"
                    )
                print(
                    f"  交叉验证（同 chunk + 同名）: 组 {via_chunk['groups']} "
                    f"多出 {via_chunk['extra']}"
                )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
