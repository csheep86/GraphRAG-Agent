"""S10 批次 A 前置探针：证据层（`:Chunk`）与 `confidence` 的真机现状。

只读，不改任何数据。回答四个问题（决定批次 A 到底要做什么，避免重复劳动）：

1. `:Chunk` 落了几条？`char_start` / `char_end` / `page` **是否有值**、落库**类型**是 int 还是 string（builder 注释记过一次 string 事故）
2. `:Chunk` 的 id 形态是否符合 R16 的 `chunk-<hex>`（不合规则引用抠不出来）
3. `:Entity.confidence` 到底有没有值（plan §17 批次 C 说"读出来是 None"，要确认是**没写**还是**写了但抽取没产出**）
4. 证据边（`HAS_CHUNK` / `MENTIONS`）现状，以及 `:Entity` 上有没有字符区间属性（决定 span 要不要新增）
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    drv = GraphDatabase.driver(
        s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
    )
    with drv.session(database=s.neo4j_database) as sess:
        print("== 1. :Chunk 概况 ==")
        row = sess.run(
            "MATCH (c:Chunk) "
            "RETURN count(c) AS n, "
            "count(c.char_start) AS cs, count(c.char_end) AS ce, "
            "count(c.page) AS page, count(c.text) AS text"
        ).single()
        print(f"Chunk 总数={row['n']} char_start 非空={row['cs']} "
              f"char_end 非空={row['ce']} page 非空={row['page']} text 非空={row['text']}")

        print("\n== 2. :Chunk 位置字段类型 + id 形态（抽样 5 条）==")
        for r in sess.run(
            "MATCH (c:Chunk) RETURN c.id AS id, c.char_start AS cs, c.char_end AS ce, "
            "c.page AS page, valueType(c.char_start) AS cs_type LIMIT 5"
        ):
            print(f"  id={r['id']!r} char_start={r['cs']!r}({r['cs_type']}) "
                  f"char_end={r['ce']!r} page={r['page']!r}")

        print("\n== 3. :Entity confidence 现状 ==")
        row = sess.run(
            "MATCH (e:Entity) RETURN count(e) AS n, count(e.confidence) AS has_conf"
        ).single()
        print(f"Entity 总数={row['n']} confidence 非空={row['has_conf']}")
        for r in sess.run(
            "MATCH (e:Entity) WHERE e.confidence IS NOT NULL "
            "RETURN e.id AS id, e.confidence AS conf, valueType(e.confidence) AS t LIMIT 5"
        ):
            print(f"  有值样例: {r['id']!r} confidence={r['conf']!r} ({r['t']})")
        for r in sess.run(
            "MATCH (e:Entity) WHERE e.confidence IS NULL "
            "RETURN e.id AS id, e.canonical_name AS name LIMIT 3"
        ):
            print(f"  NULL 样例: {r['id']!r} name={r['name']!r}")

        print("\n== 4. :Entity 是否已有字符区间属性 ==")
        row = sess.run(
            "MATCH (e:Entity) RETURN count(e.char_start) AS cs, count(e.char_end) AS ce, "
            "count(e.evidence_span) AS es LIMIT 1"
        ).single()
        print(f"char_start 非空={row['cs']} char_end 非空={row['ce']} "
              f"evidence_span 非空={row['es']}")
        keys = sess.run(
            "MATCH (e:Entity) WITH e LIMIT 200 UNWIND keys(e) AS k "
            "RETURN DISTINCT k ORDER BY k"
        )
        print(f"  Entity 属性键全集: {[r['k'] for r in keys]}")

        print("\n== 5. 证据边 ==")
        row = sess.run(
            "MATCH ()-[r:HAS_CHUNK]->() RETURN count(r) AS hc"
        ).single()
        row2 = sess.run("MATCH ()-[r:MENTIONS]->() RETURN count(r) AS m").single()
        print(f"HAS_CHUNK={row['hc']} MENTIONS={row2['m']}")

        print("\n== 6. 关系上的 confidence（对比实体）==")
        row = sess.run(
            "MATCH ()-[r:RELATION]->() RETURN count(r) AS n, count(r.confidence) AS has_conf"
        ).single()
        print(f"RELATION 总数={row['n']} confidence 非空={row['has_conf']}")
    drv.close()


if __name__ == "__main__":
    main()
