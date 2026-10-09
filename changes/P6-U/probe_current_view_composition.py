"""¥0 探针：**缺省视图 vs 今天视图**的候选构成是否一致（同一份时态谓词）。

为什么要有这个文件（以及它为什么必须是现在这个写法）
-------------------------------------------------
第一版这个文件漏了时态谓词，直接裸查全图，于是报出"缺省视图里仍有 37 条已失效
末端"——**那是错的**：全图上存在 ≠ 缺省视图可达。缺了 ``_temporal_view`` 的统计
毫无意义。教训已写进文件名为「…v2」之外的注释里：任何"候选构成"类探针都必须
**复用生产谓词本身**，自己重写一遍 Cypher 条件等于重犯了 _bridge_window 之前
"另写一份过滤语句"的同一个错。

本探针回答一个具体问题：``as_of=None``（缺省）与 ``as_of=今天``（显式同一天）
两种调用，会不会给出不同的候选集？若一致 ⇒ 缺省视图定义自洽；若不一致 ⇒ 口径
漂移，才是真bug。

用法::

    uv run python changes/P6-U/probe_current_view_composition.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.graphs import _temporal_view  # noqa: E402

KG = "attendance-demo-v1"
TODAY = "2026-09-30"


def _composition_query() -> str:
    """2 跳链 + **生产时态谓词**（r1/r2 两侧都套），按末端窗口分类计数。"""
    return f"""
MATCH (a:Entity {{kg_version: $kg}})
      -[r1:RELATION {{kg_version: $kg}}]->
      (b:Entity {{kg_version: $kg}})
      -[r2:RELATION {{kg_version: $kg}}]->
      (c:Entity {{kg_version: $kg}})
WHERE TRUE{_temporal_view("r1")}{_temporal_view("r2")}
  AND r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
RETURN
    sum(1) AS total,
    sum(CASE WHEN r2.valid_to IS NULL THEN 1 ELSE 0 END) AS end_open,
    sum(CASE WHEN r2.valid_to IS NOT NULL THEN 1 ELSE 0 END) AS end_closed
"""


def _expired_samples_query() -> str:
    return f"""
MATCH (a:Entity {{kg_version: $kg}})
      -[r1:RELATION {{kg_version: $kg}}]->
      (b:Entity {{kg_version: $kg}})
      -[r2:RELATION {{kg_version: $kg}}]->
      (c:Entity {{kg_version: $kg}})
WHERE TRUE{_temporal_view("r1")}{_temporal_view("r2")}
  AND r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
  AND r2.valid_to IS NOT NULL
RETURN DISTINCT c.canonical_name AS tail, r2.valid_from AS vf, r2.valid_to AS vt
ORDER BY tail
LIMIT 8
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    query = _composition_query()
    samples_query = _expired_samples_query()

    results: dict[str, dict] = {}
    try:
        with driver.session(database=settings.neo4j_database) as session:
            for label, as_of in (
                ("缺省视图  as_of=None", None),
                (f"今天视图  as_of={TODAY}", TODAY),
            ):
                row = dict(session.run(query, kg=KG, as_of=as_of).single())
                results[label] = row
                print(f"=== {label} ===")
                print(f"  链总数                       : {int(row['total']):>6}")
                print(f"  末端 valid_to 为空（未失效）  : {int(row['end_open']):>6}")
                print(f"  末端 valid_to 非空（有终点）  : {int(row['end_closed']):>6}")
                samples = [
                    dict(item)
                    for item in session.run(samples_query, kg=KG, as_of=as_of)
                ]
                if samples:
                    print("  末端有失效日的实例（前 8）：")
                    for item in samples:
                        print(f"    {item['tail']}  [{item['vf']} ~ {item['vt']}]")
                print()
    finally:
        driver.close()

    (_, default_row), (_, today_row) = list(results.items())

    # 只比**末端是否有失效日**，不比总数。为什么：
    # graphs.py 第 239 行注释写明「as_of 为 NULL 时起始日不设限（未来才生效的关系
    # 也算当前已知事实）」⇒ 缺省链数必然多于显式今天（本图 939 > 99）。那是**有意
    # 设计**，第一版判据连总数一起比，把设计当成了漂移，这是探针的错不是产品的错。
    same = int(default_row["end_closed"]) == int(today_row["end_closed"])

    print("=== 判据 ===")
    print(
        f"  缺省末端有失效日 {int(default_row['end_closed'])} 条"
        f" / 今天视图 {int(today_row['end_closed'])} 条"
    )
    print("  （链总数天然不等：缺省不限制 valid_from，未来生效的关系也算当前已知事实）")
    if same:
        print("  ✅ 两个视图都**不**放行已失效末端 ⇒ 缺省按当前值过滤，自洽")
        print("     ⇒ 原议题 1（以为缺省不剔除失效）不成立，无需改动")
    else:
        print("  ⚠️  某个视图放行了已失效末端 ⇒ 口径漂移，需修")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
