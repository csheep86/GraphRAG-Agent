"""¥0 探针：R4-b 之后，主链上还剩哪些**无日期**的桥接边，以及它们的**来源**。

为什么要有这个文件
------------------
R4-b 落地后两个时点的路径确实不同了（as-of 翻面），但 2025 时点的落点是
``加班与调休管理办法`` —— 一份 **2026 版**制度。它没有日期，所以在任何时点都可达。
这在演示台上的读法是：「2025 年问话，系统把人指向了一部还没出台的办法」。

这种错误的**成因**必须分清，处置完全不同：

1. **RULE 派生边**（id 前缀 ``rel-bridge-`` / ``GOVERNED_BY:``）—— 我们自己生成的，
   没日期只可能是口径没覆盖到 ⇒ **可以补**，且必须补；
2. **模型抽取边**（其余 id）—— 端点对了但日期是 LLM 抽的，抽不到就真没有
   ⇒ 确定性规则管不着，再补就要重抽（¥ + 抖动）或放宽 R4 ⇒ **不在本口径范围**。

用法::

    uv run python changes/P6-U/probe_undated_edges.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

KG = "attendance-demo-v1"

#: 共享登记册（由制度入图器写入、CSV 入图器读取）
SCOPE_STORE = ROOT / "backend" / "scripts" / "_clause_doc_scopes.json"

#: 主链那一跳：工时制 → 条款。按 **id 前缀**分来源统计缺日期的情况。
Q_BY_SOURCE = """
MATCH (w:Entity {entity_type: 'WORK_TIME_SYSTEM', kg_version: $kg})
      -[r:RELATION {relation_type: 'GOVERNED_BY', kg_version: $kg}]->
      (c:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg})
WITH r,
     CASE
       WHEN r.id STARTS WITH 'rel-bridge-' THEN 'RULE(制度入图器)'
       WHEN r.id STARTS WITH 'GOVERNED_BY:' THEN 'RULE(CSV 入图器)'
       ELSE 'MODEL(模型抽取)'
     END AS source
RETURN source,
       count(r) AS total,
       sum(CASE WHEN r.valid_from IS NULL AND r.valid_to IS NULL
                THEN 1 ELSE 0 END) AS undated
ORDER BY source
"""

#: 图上有多少 POLICY_CLAUSE，比「登记册条数」多的部分即为**无出处的陈旧实体**
#: （早几轮语料修订遗留：语句删改写过一轮后，旧 span 节点没被删除）
Q_CLAUSE_TOTAL = """
MATCH (c:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg})
RETURN count(c) AS c
"""

#: 具体反例：主演路径落到"来自其它时代却无日期"的那些条款
Q_SAMPLES = """
MATCH (w:Entity {entity_type: 'WORK_TIME_SYSTEM', kg_version: $kg})
      -[r:RELATION {relation_type: 'GOVERNED_BY', kg_version: $kg}]->
      (c:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg})
WHERE r.valid_from IS NULL AND r.valid_to IS NULL
RETURN w.canonical_name AS wts, c.canonical_name AS clause, r.id AS rid
ORDER BY wts, clause
LIMIT 15
"""


def main() -> int:
    REGISTER = (
        json.loads(SCOPE_STORE.read_text(encoding="utf-8"))
        if SCOPE_STORE.is_file()
        else {}
    )
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = [dict(row) for row in session.run(Q_BY_SOURCE, kg=KG)]
            samples = [dict(row) for row in session.run(Q_SAMPLES, kg=KG)]
            clause_total = int(session.run(Q_CLAUSE_TOTAL, kg=KG).single()["c"])

            print(f"=== {KG}｜主链那一跳（WTS → POLICY_CLAUSE）按来源统计 ===")
            total_all = sum(int(row["total"]) for row in rows)
            undated_all = sum(int(row["undated"]) for row in rows)
            for row in rows:
                print(
                    f"  {row['source']:<22} 总数 {int(row['total']):>4} "
                    f"｜无日期 {int(row['undated']):>4}"
                )
            print(
                f"  {'合计':<22} 总数 {total_all:>4} ｜无日期 {undated_all:>4}"
                f"（{'%.0f' % (undated_all / total_all * 100 if total_all else 0)}%）"
            )

            print("\n=== 无日期实例（前 15 条）===")
            for row in samples:
                print(f"  {row['wts']} → {row['clause']}   [{row['rid']}]")
    finally:
        driver.close()

    print("\n=== 判据 ===")
    print("  RULE 行仍无日期 ⇒ 口径没覆盖到，必须继续补（属我方责任）")
    print("  MODEL 行无日期 ⇒ 确定性规则管不到，不得为它牺牲 R4（属重抽范围）")
    print(
        f"\n  图上 POLICY_CLAUSE 共 {clause_total} 个；登记册 {len(REGISTER)} 条"
        f" ⇒ 多出的 {clause_total - len(REGISTER)} 个是**无当前出处**的陈旧实体，"
        "它们不可能登记到文档窗口（源头就不知道它们出自哪份文档）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
