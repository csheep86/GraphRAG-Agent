"""全域时间字段覆盖度——决定 ② 虚线与 ③ as-of 有没有东西可筛。

背景：G2 的 inconsistent 在干净图上为 0，根因是各文档实体互不共节点
（同名 7 个 id 各自独立）⇒ 跨版本链天然不存在。这对 ② 无妨（有 48 条带
valid_to 的失效边即可画虚线），但**③ as-of 完全依赖按时点筛选边**——如果
边的 valid_from 大面积缺失，as-of 分支就筛不出差异。

所以这里不看猜测，直接按 (valid_from, valid_to) 组合清点全域关系。

只读。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KG = "attendance-demo-v1"

Q_BY_WINDOW = """
MATCH ()-[r:RELATION {kg_version: $kg}]->()
RETURN coalesce(toString(r.valid_from), '<none>') AS vf,
       coalesce(toString(r.valid_to), '<none>') AS vt,
       count(*) AS c
ORDER BY c DESC
"""

Q_BY_TYPE_WINDOW = """
MATCH ()-[r:RELATION {kg_version: $kg}]->()
WHERE coalesce(r.relation_type, type(r)) = $rt
RETURN coalesce(toString(r.valid_from), '<none>') AS vf,
       coalesce(toString(r.valid_to), '<none>') AS vt,
       count(*) AS c
ORDER BY c DESC LIMIT 6
"""

TYPES = ["GOVERNED_BY", "APPLIES_WORK_TIME", "OCCURRED_ON", "HAS_SHIFT"]


def main() -> int:
    from app.core.config import get_settings
    from neo4j import GraphDatabase

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as ses:
            rows = list(ses.run(Q_BY_WINDOW, kg=KG))
            total = sum(int(r["c"]) for r in rows)
            print(f"=== 全域 RELATION 时间窗口分布（共 {total} 条）===")
            print(f"  {'valid_from':<14} {'valid_to':<14} {'条数':>7}")
            for r in rows:
                print(f"  {r['vf']:<14} {r['vt']:<14} {int(r['c']):>7}")

            print("\n=== 分关系类型（前 6 个窗口）===")
            for rt in TYPES:
                sub = list(ses.run(Q_BY_TYPE_WINDOW, kg=KG, rt=rt))
                if not sub:
                    continue
                print(f"\n  -- {rt} --")
                for r in sub:
                    print(f"     {r['vf']:<14} ~ {r['vt']:<14} {int(r['c']):>5}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
