"""批次 E 收尾：**扩召回要扩到多少才够** —— ¥0，不调 LLM。

背景（e11 闸门模拟）：闸门开启后 Q11 / Q12 被误伤为拒答，根因不是闸门，
而是**依据片段压根没进注入**（e5 实测：LV0001 未注入）。候选集是结构性窗口
（question 文本不参与检索），所以唯一杠杆是 ``select_evidence_chunks`` 的
``limit`` 与「每文档保底」。

本脚本回答三个数，避免盲调常量：

1. 13 篇文档各有多少可达 chunk？依据 chunk 在**组内排第几**（组内序 =
   MENTIONS 降序 + chunk_id 升序，与线上 ``select_evidence_chunks`` 同口径）；
2. ``limit`` 取多少时，LV0001（Q11 依据）与 SO-2026-0912（Q12 依据）进注入；
3. 对应注入的**字符数**（token 代价）——扩召回不是免费的，要量着花。

只读取，不写库。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
    select_evidence_chunks,
)

ORG_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "attendance-demo-v1"

#: (题号, 依据关键字) —— 均来自 eval_controlled_qset.py v3 登记的出处
TARGETS = [
    ("Q11", "LV0001"),
    ("Q12", "SO-2026-0912"),
]

#: 候选 limit：20=现状；其余按 floor=limit//13 递增（13 篇文档）
LIMITS = [20, 26, 39, 52, 65, 91, 130]


def main() -> None:
    settings = get_settings()
    service = GraphService.instance()

    nodes, _edges, _tr = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    entity_ids = [n.id for n in nodes]

    index: list[tuple[str, str | None, int, int]] = []
    with service._session() as session:  # noqa: SLF001 - 探测脚本复用线上查询
        rows = session.run(
            _QUERY_EVIDENCE_CHUNK_INDEX,
            kg_version=VERSION,
            org_id=ORG_ID,
            entity_ids=entity_ids,
            index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
        )
        for row in rows:
            index.append(
                (
                    str(row["chunk_id"]),
                    str(row["doc_id"]) if row["doc_id"] else None,
                    int(row["mentions"] or 0),
                    int(row["spans"] or 0),
                    int(row["char_start"] or 0),
                )
            )

    # ---- 1. 文档分布 + 依据 chunk 的组内排名 ----
    texts: dict[str, str] = {}
    with service._session() as session:  # noqa: SLF001
        rows = session.run(
            "MATCH (c:Chunk {kg_version:$v}) RETURN c.id AS id, c.text AS text",
            v=VERSION,
        )
        for row in rows:
            texts[str(row["id"])] = str(row["text"] or "")

    buckets: dict[str, list[tuple[str, int, int]]] = {}
    for chunk_id, doc_id, mentions, spans in index:
        if doc_id is None:
            continue
        buckets.setdefault(str(doc_id), []).append((chunk_id, mentions, spans))
    for group in buckets.values():
        group.sort(key=lambda item: (-item[1], item[0]))

    print("=== 1. 文档可达 chunk 数（降序） ===")
    for doc in sorted(buckets, key=lambda d: -len(buckets[d])):
        print(f"  {doc[:8]}  chunks={len(buckets[doc])}")
    print(f"  文档数={len(buckets)}  可达 chunk={len(index)}")

    print("\n=== 2. 依据 chunk 的组内排名（组内序 = MENTIONS desc, id asc） ===")
    for label, keyword in TARGETS:
        hits = [cid for cid in texts if keyword in texts[cid]]
        for cid in hits:
            doc = next(
                (d for d, g in buckets.items() if any(c == cid for c, _m, _s in g)),
                None,
            )
            if doc is None:
                print(f"  {label} {keyword}: chunk {cid[:18]} **不在 index 内**（窗口外）")
                continue
            rank = next(
                i + 1 for i, (c, _m, _s) in enumerate(buckets[doc]) if c == cid
            )
            print(
                f"  {label} {keyword}: doc={doc[:8]} 组内第 {rank}/{len(buckets[doc])} 条"
                f"  ⇒ 保底需 ≥ {rank}"
            )

    # ---- 3. 不同 limit 下的命中情况与字符代价 ----
    print("\n=== 3. limit 模拟（floor = limit // 文档数） ===")
    for limit in LIMITS:
        selected = select_evidence_chunks(index, limit)
        chars = sum(len(texts.get(cid, "")) for cid in selected)
        flags = []
        for label, keyword in TARGETS:
            ok = any(keyword in texts.get(cid, "") for cid in selected)
            flags.append(f"{label}={'命中' if ok else '缺失'}")
        floor = limit // len(buckets) if buckets else limit
        print(
            f"  limit={limit:<4} floor={floor:<3} 注入={len(selected):<4}"
            f" 字符={chars:<7} {'  '.join(flags)}"
        )


if __name__ == "__main__":
    main()
