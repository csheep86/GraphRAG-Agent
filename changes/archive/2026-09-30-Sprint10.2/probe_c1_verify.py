"""S10 批次 C 真机验收：改动**之后**，`fetch_all_subgraph` 实际返回什么（只读）。

走**服务层入口**（不自己复刻 Cypher），量三件事：

1. 结构：节点数 / 类型数 / 内部边数 / 孤立点数；
2. **锚点召回**（R12 事故的直接指标）：问句里的实体在候选集里还剩几个；
   golden = 同一份数据取**全量**（`node_limit=10**6`）时的锚点；
3. cross-check：与 `probe_c0_recall.py` 里 quota_floor 那一行的期望对齐。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402
from app.services.reasoning import anchor_ids_for_question  # noqa: E402

VERSION = "attendance-demo-v1"
LIMIT = 500


def main() -> None:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        org_row = session.run(
            "MATCH (e:Entity {kg_version: $v}) WHERE e.org_id IS NOT NULL "
            "RETURN e.org_id AS org LIMIT 1",
            v=VERSION,
        ).single()
    if org_row is None:
        print(f"[{VERSION}] 无 org_id")
        return
    org = UUID(str(org_row["org"]))

    nodes, edges, truncated = graphs.fetch_all_subgraph(
        kg_version=VERSION, org_id=org, node_limit=LIMIT
    )
    full_nodes, _full_edges, _ = graphs.fetch_all_subgraph(
        kg_version=VERSION, org_id=org, node_limit=10**6
    )

    ids = {n.id for n in nodes}
    inner = sum(1 for e in edges if e.source in ids and e.target in ids)
    touched = {e.source for e in edges} | {e.target for e in edges}
    print(f"[{VERSION}] 截断={truncated}")
    print(f"候选集: 节点 {len(nodes)} / 类型 {len({n.entity_type for n in nodes})} / 边 {len(edges)}（内部 {inner}）")
    print(f"        孤立点 {len(ids - touched)}；全量实体 {len(full_nodes)}")

    # ---- 锚点召回：问句取图上度数最高 / 最低各 6 个实体的真实名字 -------
    seeds = sorted(
        (n for n in full_nodes if ":" in n.id and (n.canonical_name or "").strip()),
        key=lambda n: n.id,
    )
    by_degree = sorted(seeds, key=lambda n: n.id)
    degree_rank = {n.id: sum(1 for e in _full_edges if e.source == n.id or e.target == n.id) for n in seeds}
    by_degree.sort(key=lambda n: (-degree_rank[n.id], n.id))
    picked = by_degree[:6] + sorted(seeds, key=lambda n: (degree_rank[n.id], n.id))[:6]
    questions = [f"{n.canonical_name} 上个月加班了多少小时，是否超过制度上限？" for n in picked]

    lost = 0
    total_golden = 0
    recalls: list[float] = []
    for question in questions:
        golden = set(anchor_ids_for_question(question=question, nodes=full_nodes))
        if not golden:
            continue
        total_golden += len(golden)
        got = set(anchor_ids_for_question(question=question, nodes=nodes))
        hit = len(got & golden) / len(golden)
        recalls.append(hit)
        if hit == 0.0:
            lost += 1
    avg = sum(recalls) / len(recalls) if recalls else 0.0
    print(f"\n锚点召回: {avg:.0%}（{len(recalls)} 条问句，全丢 {lost} 条，总锚点 {total_golden}）")
    print("对照（改动前，探针 probe_c0_recall.py）: 50%（12 条问句，全丢 6 条）")


if __name__ == "__main__":
    main()
