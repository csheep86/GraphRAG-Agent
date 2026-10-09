"""为「派生边继承条款窗口」口径提供**决策依据**：每条条款有几个候选窗口。

口径 A（桥接边继承条款自身抽出的窗口）能成立的前提是：条款本体存在一个**唯一、
无歧义**的时间窗口。本文不在于数据好不好看，而在于回答：

- 有多少条款**恰好一个**窗口 ⇒ 可继承；
- 有多少条款**多个**窗口 ⇒ 继承哪个都是猜 ⇒ 必须留空并可见；
- 有多少条款**零个**窗口 ⇒ 桥接边保持无日期（属正常：不是每条都写到日期）。

候选窗口的取法：条款节点**所有邻接 RELATION** 上出现过的
``(valid_from, valid_to)`` 去重后的集合。这些值全部来自抽取侧的_timestamp family
function（文本明确写了才填），所以继承它们不构成"凭空推断"。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

KG = "attendance-demo-v1"

Q_BUCKET = """
MATCH (p:Entity {entity_type:'POLICY_CLAUSE', kg_version:$kg})
      -[r:RELATION {kg_version:$kg}]-()
WITH p, collect(DISTINCT [toString(r.valid_from), toString(r.valid_to)]) AS raw
WITH p, [w IN raw WHERE w[0] IS NOT NULL OR w[1] IS NOT NULL] AS wins
RETURN count(p) AS clauses,
       sum(CASE WHEN size(wins) = 1 THEN 1 ELSE 0 END) AS one,
       sum(CASE WHEN size(wins) > 1 THEN 1 ELSE 0 END) AS many,
       sum(CASE WHEN size(wins) = 0 THEN 1 ELSE 0 END) AS none
"""

Q_WINDOWS = """
MATCH (p:Entity {entity_type:'POLICY_CLAUSE', kg_version:$kg})
      -[r:RELATION {kg_version:$kg}]-()
WITH p, collect(DISTINCT [toString(r.valid_from), toString(r.valid_to)]) AS raw
WITH p, [w IN raw WHERE w[0] IS NOT NULL OR w[1] IS NOT NULL] AS wins
WHERE size(wins) = 1
UNWIND wins AS w
RETURN w[0] AS vf, w[1] AS vt, count(*) AS clauses
ORDER BY clauses DESC
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            row = session.run(Q_BUCKET, kg=KG).single()
            windows = list(session.run(Q_WINDOWS, kg=KG))
    finally:
        driver.close()

    clauses = int(row["clauses"])
    one, many, none_ = int(row["one"]), int(row["many"]), int(row["none"])
    print(f"=== POLICY_CLAUSE 共 {clauses} 条：候选窗口数分桶 ===")
    print(f"  恰好 1 个窗口（可继承）   {one:>5}  {one / clauses:>6.0%}")
    print(f"  多个窗口（不猜，留空）    {many:>5}  {many / clauses:>6.0%}")
    print(f"  无窗口（桥接边无日期）    {none_:>5}  {none_ / clauses:>6.0%}")

    print("\n=== 唯一窗口的分布 ===")
    print(f"  {'valid_from':<14}{'valid_to':<14}{'条款数':>7}")
    for w in windows:
        print(f"  {str(w['vf'] or '<none>'):<14}{str(w['vt'] or '<none>'):<14}"
              f"{int(w['clauses']):>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
