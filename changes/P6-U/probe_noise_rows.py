"""排查会污染 as-of 问答的脏时间窗口。

``probe_temporal_coverage`` 显示全域只有两类异常：

- ``2025-01-01 ~ <none>``：2025 版条款缺失效期 ⇒ 会在 2026 的答案里也命中（泄漏）
- ``2026-01-01 ~ 2026-01-01``：起止同一天 ⇒ 只在当天可见

这两条直接影响 as-of 判定，必须点名到人：打印端点名称与来源文档，
才能判断是"抽取漏了一个字段"还是"语料某条漏写了失效期"。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from neo4j import GraphDatabase  # type: ignore[import-not-found]

from app.core.config import get_settings

QUERY = """
MATCH (a)-[r]->(b)
WHERE (r.valid_from = '2025-01-01' AND r.valid_to IS NULL)
   OR (r.valid_from = '2026-01-01' AND r.valid_to = '2026-01-01')
RETURN labels(a) AS head_label, a.canonical_name AS head,
       coalesce(r.relation_type, type(r)) AS rel_type,
       r.valid_from AS vf, r.valid_to AS vt,
       labels(b) AS tail_label, b.canonical_name AS tail
ORDER BY rel_type, head, tail
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = list(session.run(QUERY))
    finally:
        driver.close()

    if not rows:
        print("没有命中脏时间窗口")
        return 0

    print(f"脏时间窗口 {len(rows)} 条：")
    for row in rows:
        labels = lambda v: "/".join(v) if v else "?"  # noqa: E731
        print(f"\n  [{row['rel_type']}] {labels(row['head_label'])} "
              f"{row['head']!r} -> {labels(row['tail_label'])} {row['tail']!r}")
        print(f"      valid_from={row['vf']}  valid_to={row['vt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
