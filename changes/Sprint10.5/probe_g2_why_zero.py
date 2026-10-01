"""回答「G2 为什么还是 0」：把 152 条可判定链按**时间窗口配对**分组。

``probe_g2_inconsistent`` 报 152 条可判定链、0 条 inconsistent。按 ADR-0005 §6 的
判据 ``max(valid_from) > min(valid_to)`` ⇒ inconsistent，只要存在「一跳的
valid_from 晚于另一跳的 valid_to」的跨代组合就该判红。所以要么：

- A. 跨代组合**根本不在 152 条里**（ άλλη 中间节点不共享 —— 2025 版条款与
  2026 版条款是不同节点，未必串得起来）；要么
- B. 组合在但 ``_temporal_verdict`` 算错。

这里直接把窗口配对打印出来，一眼分清 A / B，不再猜。
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

KG_VERSION = "attendance-demo-v1"

#: 与 G2 探针同一个窄化谓词，只是把聚合放在 Cypher 侧（行数少到可全打印）。
CYPHER = """
MATCH (a:Entity {kg_version: $kg})-[r1]-(m:Entity {kg_version: $kg})-[r2]-(b:Entity {kg_version: $kg})
WHERE r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND (r1.valid_to IS NOT NULL OR r2.valid_to IS NOT NULL)
  AND r1.valid_from <= r2.valid_from
RETURN coalesce(r1.relation_type, type(r1)) AS t1,
       coalesce(r2.relation_type, type(r2)) AS t2,
       r1.valid_from AS vf1, r1.valid_to AS vt1,
       r2.valid_from AS vf2, r2.valid_to AS vt2,
       labels(m) AS mid_labels,
       m.canonical_name AS mid,
       count(*) AS n
ORDER BY n DESC
"""


def window(vf: str | None, vt: str | None) -> str:
    return f"{vf or '∞'}~{vt or '∞'}"


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = list(session.run(CYPHER, kg=KG_VERSION))
    finally:
        driver.close()

    print(f"=== 152 条可判定链按『关系类型 × 窗口』分组：{len(rows)} 组 ===")
    cross = 0
    for row in rows:
        w1, w2 = window(row["vf1"], row["vt1"]), window(row["vf2"], row["vt2"])
        # 跨代：一跳最晚开始 > 另一跳最早失效
        froms = [row["vf1"], row["vf2"]]
        tos = [v for v in (row["vt1"], row["vt2"]) if v]
        bad = max(froms) > min(tos) if tos else False
        cross += int(bad)
        print(
            f"  {row['t1']:<18} [{w1}]  --({row['mid']})-->  "
            f"{row['t2']:<18} [{w2}]   n={row['n']}"
            f"{'   <== 跨代，应判 inconsistent' if bad else ''}"
        )
    print(f"\n跨代组合组数 = {cross}（0 ⇒ 属于情形 A：数据里串不起来，不是判据算错）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
