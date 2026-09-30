"""S10 批次 C **残留缺口**探针：候选集保不住「新入图（低度数）实体」。

真机症状（§9.2）：用新代码重跑一份 docx 后，active 版本多出 **31 个带 span 的实体**
（老数据的 139 个抽取实体一个 span 都没有 ⇒ ``char_start IS NOT NULL`` 就是"新实体"
的天然标记），但问答却引回 CSV 考勤行——**这些新实体没进 500 人候选集**。

根因假设：组内按**度数降序**取，新入图的实体度数低 ⇒ 被同类型的老实体压掉。
候选集是**问句无关**的（结构性），也没法按"入图时间"挑——线上实体根本没有时间字段
（属性键只有 id/entity_type/canonical_name/mention/confidence/trace_id…）。

于是能动的只有**结构**：在每组保底名额里给"非度数维度"留一部分位置。本探针对照：

1. ``current``  现状：保底名额**全按**度数降序；
2. ``mixed40``  保底名额 60% 按度数 + **40% 按 id 升序**（给年轻/低度数留位）；
3. ``by_id``    保底名额**全按** id 升序（均匀抽样，看纯随机的代价）；
4. ``degree``   全局度数降序（已知会饿死小类型，作对照组）。

口径纪律：**只用结构性字段**（类型 / 度数 / id）。新实体的 ``has_span`` 只用于
**评估**（数一数进了几个），**不**参与任何方案的选择逻辑——拿它挑人等于事后诸葛。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402

VERSION = "attendance-demo-v1"
LIMIT = 500


def _load_index() -> list[tuple[str, str, int, bool]]:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        rows = [
            (
                str(r["id"]),
                str(r["type"]),
                int(r["degree"] or 0),
                bool(r["has_span"]),
            )
            for r in session.run(
                "MATCH (n:Entity {kg_version: $v}) "
                "RETURN n.id AS id, coalesce(n.entity_type,'UNKNOWN') AS type, "
                "size([(n)--() | 1]) AS degree, "
                "n.char_start IS NOT NULL AS has_span "
                "ORDER BY degree DESC, id",
                v=VERSION,
            )
        ]
    return rows


def _count_edges(ids: list[str]) -> int:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        row = session.run(
            "MATCH (a:Entity {kg_version:$v})-[r]->(b:Entity {kg_version:$v}) "
            "WHERE a.id IN $ids AND b.id IN $ids RETURN count(r) AS c",
            v=VERSION,
            ids=ids,
        ).single()
    return int(row["c"]) if row else 0


def select_variant(
    rows: list[tuple[str, str, int, bool]],
    limit: int,
    *,
    mode: str,
    id_share: float = 0.0,
) -> list[str]:
    """``mode``: ``floor``（按类型保底）/ ``degree``（全局度数降序）。

    ``id_share``：保底名额里按 **id 升序**（均匀、确定）分配的比例，其余按度数降序。
    """
    if mode == "degree":
        ordered = sorted(rows, key=lambda r: (-r[2], r[0]))
        return [r[0] for r in ordered[:limit]]

    buckets: dict[str, list[tuple[str, str, int, bool]]] = {}
    for row in rows:
        buckets.setdefault(row[1], []).append(row)
    for group in buckets.values():
        group.sort(key=lambda r: (-r[2], r[0]))

    floor = max(limit // len(buckets), 1)
    chosen: list[str] = []
    leftovers: list[tuple[str, str, int, bool]] = []
    for entity_type in sorted(buckets):
        group = buckets[entity_type]
        n_by_id = int(floor * id_share)
        by_degree = group[: floor - n_by_id]
        picked = {r[0] for r in by_degree}
        by_id = sorted((r for r in group if r[0] not in picked), key=lambda r: r[0])
        chosen.extend(r[0] for r in by_degree)
        chosen.extend(r[0] for r in by_id[:n_by_id])
        leftovers.extend(group[floor:])

    if len(chosen) > limit:
        return chosen[:limit]
    if len(chosen) < limit:
        leftovers.sort(key=lambda r: (-r[2], r[0]))
        chosen.extend(r[0] for r in leftovers[: limit - len(chosen)])
    return chosen


def main() -> None:
    index = _load_index()
    newcomers = {r[0] for r in index if r[3]}
    print(f"全图实体 {len(index)}；其中**新入图（带 span）** {len(newcomers)} 个")
    deg_new = sorted(r[2] for r in index if r[3])
    deg_old = sorted(r[2] for r in index if not r[3])
    print(
        f"度数：新实体 中位 {deg_new[len(deg_new)//2]}（min {deg_new[0]} / max {deg_new[-1]}）"
        f" vs 老实体 中位 {deg_old[len(deg_old)//2]}"
    )

    # 现状：走服务层（不本地复刻，避免结论与线上分叉）
    graphs = GraphService.instance()
    current_nodes, _edges, _truncated = graphs.fetch_all_subgraph(
        kg_version=VERSION,
        org_id=None,
        node_limit=LIMIT,
    )
    current = [n.id for n in current_nodes]

    plans: list[tuple[str, list[str]]] = [("current(服务层)", current)]
    for label, mode, share in (
        ("mixed40(保底 40% 按id)", "floor", 0.4),
        ("by_id(保底全按id)", "floor", 1.0),
        ("degree(全局度数)", "degree", 0.0),
    ):
        plans.append((label, select_variant(index, LIMIT, mode=mode, id_share=share)))

    print("\n== 候选集对照 ==")
    print(f"{'方案':<22}{'节点':>6}{'类型':>6}{'新实体命中':>12}{'内部边':>8}")
    for label, ids in plans:
        types = len({t for _i, t, _d, _s in index if _i in set(ids)})
        hit = len(newcomers & set(ids))
        print(
            f"{label:<22}{len(ids):>6}{types:>6}"
            f"{hit:>8}/{len(newcomers)}{_count_edges(ids):>8}"
        )

    print("\n（新实体命中 = 31 个带 span 的实体里进了候选集的个数；"
          "边 = 候选集内部边，衡量连通性代价）")


if __name__ == "__main__":
    main()
