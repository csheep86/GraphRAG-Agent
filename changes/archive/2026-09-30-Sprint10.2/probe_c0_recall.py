"""S10 批次 C 前置探针：M3 检索的**召回**实测（只读，不依赖 PG）。

背景（`backend/app/services/graphs.py`）：

- `_QUERY_ALL_ENTITY_SUBGRAPH`（:293）——**问答注入**用的子图，仍是
  `all_nodes[0..$node_limit]` **无序截断**；
- `_QUERY_GRAPH_OVERVIEW`（:561）——**图谱概览**早已改为 `ORDER BY degree DESC, n.id`
  （注释里记着真机实测「500 节点仅 36 边，画出来全是孤点噪云」）。

同一份数据两条口径 ⇒ 本探针把它们放到一起量，回答一个问题：
**问答子图的无序截断到底损失了多少召回？**

度量的两个面：

1. **结构**：候选集内的边数（连通性）、覆盖类型数、孤立节点数；
2. **锚点召回**（直接对应 R12 真机事故）：对每个问句，先在全量集上算锚点
   （golden，机械判定：名字出现在问句里的确定性派生实体），再看候选集能召回几个。
   锚点丢光 ⇒ LLM 答「资料中没有此人信息」却带引用——答案与引用不符，比拒答更危险。

问句**由执行者基于 active 图谱里的真实实体名构造**（不编造实体），golden 锚点
由全量集机械反查 ⇒ 指标可复核、不含人工判分。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.schemas.document import GraphNode  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402
from app.services.reasoning import anchor_ids_for_question  # noqa: E402

VERSION = "attendance-demo-v1"
LIMIT = 500

_CYPHER_NODES = """
MATCH (n:Entity {kg_version: $v, org_id: $org})
WITH n, size([(n)--() | 1]) AS degree
RETURN n.id AS id, n.canonical_name AS name, n.entity_type AS type, degree AS degree
"""

_CYPHER_EDGES = """
MATCH (a:Entity {kg_version: $v, org_id: $org})-[r]->(b:Entity {kg_version: $v, org_id: $org})
RETURN a.id AS s, b.id AS t
"""

#: 问句模板（``{name}`` 由图上真实实体名填入）。刻意用**同一批**实体名跑四方案，
#: 差异只来自候选集，不来自问句。
_TEMPLATES = (
    "{name} 上个月加班了多少小时，是否超过制度上限？",
    "{name} 的考勤记录里有没有异常？",
)


def _node(row: dict) -> GraphNode:
    return GraphNode(
        id=row["id"],
        label="Entity",
        entity_type=row["type"] or "UNKNOWN",
        canonical_name=row["name"],
        confidence=0.9,
        kg_version=VERSION,
    )


def _candidates(rows: list[dict]) -> dict[str, list[GraphNode]]:
    """四个候选集：现状 / 度数降序 / 按类型配额 / 全量。"""
    # 现状：驱动返回顺序（list 顺序即 Neo4j 返回顺序），前 500
    current = [_node(r) for r in rows[:LIMIT]]
    # 度数降序（与图谱概览同口径，平局按 id 保证确定性）
    by_degree = [_node(r) for r in sorted(rows, key=lambda r: (-r["degree"], r["id"]))][
        :LIMIT
    ]
    types = sorted({r["type"] or "UNKNOWN" for r in rows})
    buckets: dict[str, list[dict]] = {}
    for entity_type in types:
        bucket = [r for r in rows if (r["type"] or "UNKNOWN") == entity_type]
        bucket.sort(key=lambda r: (-r["degree"], r["id"]))
        buckets[entity_type] = bucket

    # 按类型**均分**配额（每类型 500//类型数，500 用不满）
    per_type = max(LIMIT // max(len(types), 1), 1)
    quota = [
        _node(r)
        for entity_type in types
        for r in buckets[entity_type][:per_type]
    ][:LIMIT]

    # **保底均分 + 余量按度数补满**：每种类型先保 `per_type` 个（小类型不被饿死），
    # 500 用不满的部分再按全局度数补齐（连通性不浪费）。
    chosen: dict[str, list[dict]] = {t: buckets[t][:per_type] for t in types}
    remaining = LIMIT - sum(len(v) for v in chosen.values())
    if remaining > 0:
        taken = {id(r) for group in chosen.values() for r in group}
        leftovers = sorted(
            (
                r
                for entity_type in types
                for r in buckets[entity_type]
                if id(r) not in taken
            ),
            key=lambda r: (-r["degree"], r["id"]),
        )
        chosen["__extra__"] = leftovers[:remaining]
    quota_floor = [_node(r) for group in chosen.values() for r in group]

    return {
        "current(无序截断)": current,
        "degree(度数降序)": by_degree,
        "quota(均分配额)": quota,
        "quota_floor(保底+补满)": quota_floor,
        "full(全量)": [_node(r) for r in rows],
    }


def _stats(nodes: list[GraphNode], edges: list[tuple[str, str]]) -> dict:
    ids = {n.id for n in nodes}
    inner = sum(1 for s, t in edges if s in ids and t in ids)
    touched = {s for s, t in edges if s in ids or t in ids} | {
        t for s, t in edges if s in ids or t in ids
    }
    isolated = len(ids - touched)
    return {
        "nodes": len(nodes),
        "types": len({n.entity_type for n in nodes}),
        "inner_edges": inner,
        "isolated": isolated,
    }


def main() -> None:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        org_row = session.run(
            "MATCH (e:Entity {kg_version: $v}) WHERE e.org_id IS NOT NULL "
            "RETURN e.org_id AS org LIMIT 1",
            v=VERSION,
        ).single()
        if org_row is None:
            print(f"[{VERSION}] 无 org_id，跳过")
            return
        org = org_row["org"]

        started = time.perf_counter()
        rows = [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "degree": int(r["degree"] or 0),
            }
            for r in session.run(_CYPHER_NODES, v=VERSION, org=org)
        ]
        edges = [(r["s"], r["t"]) for r in session.run(_CYPHER_EDGES, v=VERSION, org=org)]
        elapsed = time.perf_counter() - started

    print(f"[{VERSION}] 全量实体 {len(rows)} / 边 {len(edges)} （查询 {elapsed:.2f}s）")

    # ---- 构造问句：从图里挑真实实体名（确定性派生节点，`NAMESPACE:ID` 形态）----
    seeds = [r for r in rows if ":" in r["id"] and (r["name"] or "").strip()]
    seeds.sort(key=lambda r: (-r["degree"], r["id"]))
    picked = seeds[:6] + sorted(seeds, key=lambda r: r["degree"])[:6]
    questions = [
        template.format(name=r["name"])
        for r in picked
        for template in (_TEMPLATES[0],)
    ]
    print(f"问句 {len(questions)} 条（取图上度数最高 / 最低各 6 个实体的真实名字）")

    cands = _candidates(rows)
    full_nodes = cands["full(全量)"]

    print("\n== 结构指标 ==")
    print(f"{'方案':<20}{'节点':>8}{'类型':>8}{'内部边':>10}{'孤立点':>10}")
    for name, nodes in cands.items():
        s = _stats(nodes, edges)
        print(
            f"{name:<20}{s['nodes']:>8}{s['types']:>8}{s['inner_edges']:>10}{s['isolated']:>10}"
        )

    # 关键类型覆盖：回答要靠的落点（制度条款 / 考勤记录 / 加班 / 请假…）在不在候选集里
    key_types = ("POLICY_CLAUSE", "ATTENDANCE_RECORD", "OVERTIME", "LEAVE", "EMPLOYEE")
    print("\n== 关键类型节点数 ==")
    print(f"{'方案':<20}" + "".join(f"{t[:12]:>14}" for t in key_types))
    for name, nodes in cands.items():
        counts = {t: sum(1 for n in nodes if n.entity_type == t) for t in key_types}
        print(f"{name:<20}" + "".join(f"{counts[t]:>14}" for t in key_types))

    print("\n== 锚点召回（golden = 全量集上机械反查到的锚点）==")
    print(f"{'方案':<20}{'平均召回':>10}{'全丢的题':>10}{'总锚点':>10}")
    for name, nodes in cands.items():
        recalls: list[float] = []
        lost = 0
        total = 0
        for question in questions:
            golden = set(anchor_ids_for_question(question=question, nodes=full_nodes))
            if not golden:
                continue  # 该问句在全量集上就没有锚点 ⇒ 不计入（不是候选集的锅）
            total += len(golden)
            got = set(anchor_ids_for_question(question=question, nodes=nodes))
            hit = len(got & golden) / len(golden)
            recalls.append(hit)
            if hit == 0.0:
                lost += 1
        avg = sum(recalls) / len(recalls) if recalls else 0.0
        print(f"{name:<20}{avg:>10.2%}{lost:>10}{total:>10}")


if __name__ == "__main__":
    main()
