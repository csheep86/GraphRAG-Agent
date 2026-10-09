"""验证 G2=0 的根因假设：**规则生成的桥接边是不是无日期的**。

``ingest_attendance_csv.py`` 按 mapping 规则生成 ``WORK_TIME_SYSTEM -> POLICY_CLAUSE``
的 ``GOVERNED_BY`` 桥接边（本次 141 条）。它们是 deterministic 产物，不经 LLM，
所以很可能**一个时间字段都没有**。而演示主链

    EMPLOYEE --APPLIES_WORK_TIME--> 工时制 --GOVERNED_BY--> 条款

必须穿过这条桥接边 ⇒ 该跳 ``valid_from`` 为空 ⇒ ``_temporal_verdict`` 判 ``unknown``
⇒ 被 G2 探针的窄化谓词排除 ⇒ 永远构不出跨代组合。

本探针把「桥接形状」的边单独拎出来统计日期缺失率，把假设变成事实。
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

Q = """
MATCH (h:Entity {kg_version:$kg})-[r:RELATION {kg_version:$kg, relation_type:'GOVERNED_BY'}]->
      (t:Entity {kg_version:$kg})
RETURN h.entity_type AS head_type,
       t.entity_type AS tail_type,
       count(*) AS n,
       sum(CASE WHEN r.valid_from IS NULL THEN 1 ELSE 0 END) AS no_from,
       sum(CASE WHEN r.valid_to   IS NULL THEN 1 ELSE 0 END) AS no_to
ORDER BY n DESC
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = list(session.run(Q, kg=KG))
    finally:
        driver.close()

    print("=== GOVERNED_BY 按 (头类型 → 尾类型) 分组：日期缺失情况 ===")
    print(f"{'head -> tail':<44}{'总数':>7}{'无valid_from':>14}{'无valid_to':>13}")
    total = no_from = 0
    for row in rows:
        total += int(row["n"])
        no_from += int(row["no_from"])
        pair = f"{row['head_type']} -> {row['tail_type']}"
        print(
            f"{pair:<44}{int(row['n']):>7}{int(row['no_from']):>14}{int(row['no_to']):>13}"
        )
    print(f"\nGOVERNED_BY 总数 {total} 条，其中缺 valid_from {no_from} 条"
          f"（{no_from / total:.0%}）")
    if no_from:
        print("⇒ 缺 valid_from 的这一跳让整条链判 unknown，被 G2 可判定集排除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
