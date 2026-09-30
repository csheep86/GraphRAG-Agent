"""批次 E 收尾：**保底挤掉余量** 的定位 —— ¥0，不调 LLM。

现象（真实 14 题重跑，``eval_v3_recall52.json``）：

- ``limit`` 20 → 52 后 Q11 / Q12 从拒答变答上（依据进来了，符合 e12 预判）；
- 但 **Q09 / Q10（张伟，employees.csv）反而从答上变拒答** ⇒ 净收益为 0。

怀疑机制：``select_evidence_chunks`` 先按文档保底（floor = limit // 文档数），
**余下的名额**才按 span 优先补。limit 20 时 floor=1 ⇒ 保底 13、余量 **7**；
limit 52 时 floor=4 ⇒ 保底 46、余量只剩 **6** ⇒ 原本靠余量进来的
「带 span 但热度不高」的片段（Q09 依据疑似在此列）被挤掉。

⇒ 该函数对 limit **不单调**：limit 变大，某些已选片段反而消失。
本脚本把它量出来，并扫出「三题依据同时在场」的最小 limit 与字符代价。

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

#: 三题依据关键字（出处见 eval_controlled_qset.py v3 登记）
TARGETS = [
    ("Q09/Q10", "张伟"),
    ("Q11", "LV0001"),
    ("Q12", "SO-2026-0912"),
]

LIMITS = [20, 26, 32, 39, 45, 52, 58, 65, 78, 91, 104]


def main() -> None:
    settings = get_settings()
    service = GraphService.instance()

    nodes, _edges, _tr = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    entity_ids = [n.id for n in nodes]

    index: list[tuple[str, str | None, int, int]] = []
    with service._session() as session:  # noqa: SLF001 - 探测脚本复用线上查询
        for row in session.run(
            _QUERY_EVIDENCE_CHUNK_INDEX,
            kg_version=VERSION,
            org_id=ORG_ID,
            entity_ids=entity_ids,
            index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
        ):
            index.append(
                (
                    str(row["chunk_id"]),
                    str(row["doc_id"]) if row["doc_id"] else None,
                    int(row["mentions"] or 0),
                    int(row["spans"] or 0),
                    int(row["char_start"] or 0),
                )
            )

    texts: dict[str, str] = {}
    with service._session() as session:  # noqa: SLF001
        for row in session.run(
            "MATCH (c:Chunk {kg_version:$v}) RETURN c.id AS id, c.text AS text",
            v=VERSION,
        ):
            texts[str(row["id"])] = str(row["text"] or "")

    # ---- 1. 单调性检验：20 条里有哪些在 52 条里消失了 ----
    old = set(select_evidence_chunks(index, 20))
    new = set(select_evidence_chunks(index, 52))
    lost = old - new
    print("=== 1. 单调性检验（limit 20 → 52） ===")
    print(f"  20 条中消失的片段: {len(lost)} 条")
    for cid in sorted(lost):
        spans = next((s for c, _d, _m, s in index if c == cid), 0)
        hit = [label for label, kw in TARGETS if kw in texts.get(cid, "")]
        print(
            f"    {cid[:18]} spans={spans} 依据={hit or '-'} :: "
            f"{texts.get(cid, '')[:70]}"
        )

    # ---- 2. 扫最小可行 limit ----
    print("\n=== 2. limit 扫描（三题依据同时在场？） ===")
    feasible: list[int] = []
    for limit in LIMITS:
        selected = select_evidence_chunks(index, limit)
        chars = sum(len(texts.get(cid, "")) for cid in selected)
        flags = []
        all_hit = True
        for label, keyword in TARGETS:
            ok = any(keyword in texts.get(cid, "") for cid in selected)
            all_hit = all_hit and ok
            flags.append(f"{label}={'√' if ok else '×'}")
        if all_hit:
            feasible.append(limit)
        print(
            f"  limit={limit:<4} 注入={len(selected):<4} 字符={chars:<7} "
            f"{'  '.join(flags)}{'   ← 最小可行' if all_hit and not feasible[:-1] else ''}"
        )
    print(f"\n全部命中的 limit: {feasible or '无'}")


if __name__ == "__main__":
    main()
