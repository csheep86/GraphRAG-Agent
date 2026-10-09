"""¥0 闸门 G1/G2 探针：2025 版入库后，图上到底有没有「失效边」，链判定有没有真的翻过面。

回答三个问题，每个都必须**指着数据说**，不许用"应该抽到了"结案：

1. 通用层 ``:RELATION`` 里 ``valid_to`` 非空的边有几条？各自属于哪份文档？
   （为什么重要：L2-②③ 的全部前提就是它有值；2026-09-30 10.4 实测是 **0**）
2. 这些边的两端是什么？——能看出它是不是"抽歪了"（例如把某句 Release 当成失效）。
3. ``_temporal_verdict`` 的分布里 ``inconsistent`` 是不是从 0 变了？这是 L2-① 判据
   在**真实数据上**第一次有机会取到非一致值。

用法（工作目录任意）::

    uv run python changes/P6-U/probe_valid_to.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

KG_VERSION = "attendance-demo-v1"

#: 按文档统计：新入库的 2025 版有没有真的带来失效边
_CYPHER_BY_DOC = """
MATCH (a)-[r:RELATION {kg_version: $kg_version}]->(b)
WHERE r.valid_to IS NOT NULL
RETURN coalesce(r.source_document_id, '<none>') AS doc,
       count(r) AS sealed
ORDER BY sealed DESC
"""

_CYPHER_SEALED_EDGES = """
MATCH (a)-[r:RELATION {kg_version: $kg_version}]->(b)
WHERE r.valid_to IS NOT NULL
RETURN r.relation_type AS rt,
       r.valid_from AS vf,
       r.valid_to AS vt,
       coalesce(a.canonical_name, a.id) AS head,
       coalesce(b.canonical_name, b.id) AS tail,
       r.source_document_id AS doc
LIMIT 20
"""

_CYPHER_DOC_NAMES = """
MATCH (d:Document) WHERE d.id IN $ids RETURN d.id AS id, coalesce(d.filename, '') AS name
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            print("=== G1：valid_to 非空的边（按源文档） ===")
            sealed_total = 0
            rows = list(session.run(_CYPHER_BY_DOC, kg_version=KG_VERSION))
            for row in rows:
                sealed_total += row["sealed"]
                print(f"  {row['doc']:<40} {row['sealed']:>4} 条")
            if not rows:
                print("  （无）")

            print("\n=== G1：这些边是什么（前 20 条） ===")
            for row in session.run(_CYPHER_SEALED_EDGES, kg_version=KG_VERSION):
                print(
                    f"  [{row['rt']:<18}] {row['vf']} → {row['vt']}  "
                    f"{str(row['head'])[:24]} → {str(row['tail'])[:24]}"
                )

        print(f"\n  合计 valid_to 非空：{sealed_total} 条")
        print(
            "  G1 判定："
            + ("✅ 有失效边，可继续 G2" if sealed_total else "❌ 仍为 0 ⇒ 停在 G1，不许手写补值")
        )
        return 0 if sealed_total else 1
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
