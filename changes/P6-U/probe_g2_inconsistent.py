"""G2 闸门 · ``inconsistent`` 链的**确定性**探针（Sprint 10.5，替代 10.4 的抽样版）。

为什么重写
----------
10.4 的 ``probe_l2_path_temporal.py`` 用 ``ORDER BY rels LIMIT 4000`` **随机抽样**，
但全库 2 跳链有 **19 万+** 条（真机 2026-09-30 实测 192180）——那 2 条跨版本冲突链
被排到样本之外 ⇒ 它报 ``inconsistent = 0`` 是**采样盲区**，不是数据不存在。

本探针不做抽样：先用窄化谓词把候选缩到「两跳都有 ``valid_from``、且至少一跳有
``valid_to``」的**可判定集**，再全量交给生产判据 ``_temporal_verdict``。
可判定集远小于 19 万（绝大多数 2 跳链含 CSV 边，缺 ``valid_from`` ⇒ unknown），
故全量判**不贵**且**可复现**。

用法：``cd backend && uv run python ../changes/P6-U/probe_g2_inconsistent.py``
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

#: 窄化谓词：只取**两跳都有 valid_from、至少一跳有 valid_to**的链。
#: - 缺 valid_from ⇒ ``_temporal_verdict`` 直接 unknown，不用拉回来；
#: - 两跳都无 valid_to ⇒ 恒 consistent，也不用拉回来。
#: 方向用 ``<=`` 去重（无向图里 (a)-(m)-(b) 与 (b)-(m)-(a) 是同一链的两种写法）。
CYPHER = """
MATCH p = (a:Entity {kg_version: $kg})-[r1]-(m:Entity {kg_version: $kg})-[r2]-(b:Entity {kg_version: $kg})
WHERE r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND (r1.valid_to IS NOT NULL OR r2.valid_to IS NOT NULL)
  AND r1.valid_from <= r2.valid_from
RETURN [r1.valid_from, r2.valid_from] AS valid_froms,
       [r1.valid_to, r2.valid_to] AS valid_tos,
       [coalesce(r1.relation_type, type(r1)), coalesce(r2.relation_type, type(r2))] AS rels,
       a.canonical_name AS a, m.canonical_name AS m, b.canonical_name AS b
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    with driver.session() as session:
        rows = list(session.run(CYPHER, kg=KG_VERSION))

    verdicts = Counter(
        _temporal_verdict(
            [str(x) for x in row["valid_froms"] if x is not None],
            [str(x) for x in row["valid_tos"] if x is not None],
        )
        for row in rows
    )

    print(f"=== 可判定 2 跳链（两跳都有 valid_from 且 ≥1 跳有 valid_to）：{len(rows)} 条 ===")
    for verdict in ("consistent", "inconsistent", "unknown"):
        print(f"  {verdict:<13} = {verdicts.get(verdict, 0)}")

    print("=== inconsistent 链明细（max(valid_from) > min(valid_to)）===")
    n = 0
    for row in rows:
        froms = [str(x) for x in row["valid_froms"] if x is not None]
        tos = [str(x) for x in row["valid_tos"] if x is not None]
        if _temporal_verdict(froms, tos) != "inconsistent":
            continue
        n += 1
        print(
            f"  [{row['a']}] -[{row['rels'][0]} {froms[0]}~{tos[0] if tos[0] else '…'}]-> "
            f"[{row['m']}] -[{row['rels'][1]} {froms[1]}~{tos[1] if len(tos) > 1 and tos[1] else '…'}]-> "
            f"[{row['b']}]"
        )

    print(
        "\nG2 判定："
        + ("✅ inconsistent 链存在（" + str(n) + " 条）—— L2-① 完整验收达成" if n else "❌ 仍为 0")
    )
    driver.close()
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
