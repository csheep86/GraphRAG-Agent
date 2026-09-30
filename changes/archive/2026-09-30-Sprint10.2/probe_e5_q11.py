"""批次 E：Q11（E004 病假）拒答误伤归因 —— ¥0，不调 LLM。

全量评测里 14 题只有 Q11 一例误伤。问答的文本**不参与检索**（结构性窗口），
所以归因只能问一句：**注入的 20 条里有没有 LV0001 那一行？**

顺带把 20 条注入逐条打印，看制度文档的**重复 chunk** 占了几条
（e3 实测：制度文档 36 chunks 去重后只剩 11，重复 25 条）。
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
    _EVIDENCE_CHUNK_LIMIT,
    GraphService,
)

ORG_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "attendance-demo-v1"


def main() -> None:
    settings = get_settings()
    service = GraphService.instance()
    nodes, _edges, _truncated = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    injected = service.fetch_evidence_chunks(
        kg_version=VERSION,
        org_id=UUID(ORG_ID),
        entity_ids=[n.id for n in nodes],
        limit=_EVIDENCE_CHUNK_LIMIT,
    )

    print(f"注入 {len(injected)} 条（LIMIT {_EVIDENCE_CHUNK_LIMIT}）\n")
    seen: dict[str, int] = {}
    for chunk in injected:
        text = (chunk.text or "").replace("\n", " ")
        seen[text] = seen.get(text, 0) + 1
        doc = str(chunk.doc_id)[:8] if chunk.doc_id else "-"
        print(f"  [{doc}] {str(chunk.chunk_id)[:18]} {text[:90]}")

    dup = sum(n - 1 for n in seen.values() if n > 1)
    print(f"\n去重后 {len(seen)} / {len(injected)} ⇒ 重复占 {dup} 条名额")

    hit = [t for t in seen if "LV0001" in t or ("E004" in t and "病假" in t)]
    print(f"\nLV0001（E004 病假）所在片段是否注入: {'是' if hit else '否'}")
    for t in hit:
        print(f"  {t[:160]}")


if __name__ == "__main__":
    main()
