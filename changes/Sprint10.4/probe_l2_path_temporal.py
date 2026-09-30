"""Sprint 10.4 · L2「路径时序一致性」的 ¥0 真机探针（不调 LLM）。

回答一个问题：**演示图上真实存在的多跳路径，时序上到底分得出几档？**

方法：在 active 版本里抽 2 跳链（``:Entity`` 之间），把每跳的 ``valid_from`` /
``valid_to`` 取出来，交给**生产代码的判据** :func:`app.services.reasoning._temporal_verdict`
——不在这里另写一套口径（另写一套就失去了"验证生产代码"的意义）。

用法：``cd backend && uv run python ../changes/Sprint10.4/probe_l2_path_temporal.py``
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.reasoning import _temporal_verdict  # noqa: E402

KG_VERSION = "attendance-demo-v1"

#: 抽 2 跳链的 Cypher（与 ``reasoning._CYPHER_PATHS`` 同族口径）：
#: 中间节点必须是 ``:Entity``，两端与中间都限定同一版本 / 同一租户。
CYPHER = """
MATCH p = (a:Entity {kg_version: $kg})-[rels*2]-(b:Entity {kg_version: $kg})
WHERE ALL(n IN nodes(p) WHERE n:Entity)
  AND ALL(r IN rels WHERE r.kg_version = $kg)
RETURN [r IN relationships(p) | toString(properties(r)['valid_from'])] AS valid_froms,
       [r IN relationships(p) | toString(properties(r)['valid_to'])] AS valid_tos,
       [r IN relationships(p) | coalesce(r.relation_type, type(r))] AS rels
ORDER BY rels
LIMIT $limit
"""

SAMPLE = 4000


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    with driver.session() as session:
        rows = list(session.run(CYPHER, kg=KG_VERSION, limit=SAMPLE))

    print(f"=== kg_version = {KG_VERSION}：抽样 {len(rows)} 条 2 跳链 ===")
    verdicts = Counter(
        _temporal_verdict(row["valid_froms"], row["valid_tos"]) for row in rows
    )
    for verdict in ("consistent", "unknown", "inconsistent"):
        count = verdicts.get(verdict, 0)
        pct = (count / len(rows) * 100) if rows else 0.0
        print(f"  {verdict:<13} = {count:<6} ({pct:.1f}%)")

    print("=== unknown 样例（前 3 条：确认是「某跳缺 valid_from」而非判据失效）===")
    shown = 0
    for row in rows:
        if _temporal_verdict(row["valid_froms"], row["valid_tos"]) != "unknown":
            continue
        print(f"  {list(row['rels'])} -> froms={row['valid_froms']}")
        shown += 1
        if shown >= 3:
            break

    print("=== 全库 valid_to 非空的关系数（>0 才可能判出 inconsistent）===")
    with driver.session() as session:
        total = session.run(
            "MATCH ()-[r]->() WHERE r.kg_version = $kg AND r.valid_to IS NOT NULL "
            "RETURN count(r) AS c",
            kg=KG_VERSION,
        ).data()[0]["c"]
    print(f"  valid_to 非空 = {total}")
    driver.close()


if __name__ == "__main__":
    main()
