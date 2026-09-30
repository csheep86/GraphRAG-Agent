"""批次 E 收尾：**保底要抬到多高才捞得到「张伟」** —— ¥0，不调 LLM。

e14 实测：``张伟`` 全库只有 1 条 chunk（``chunk-6c17ea368cd3``，employees.csv 首行），
可达但**从未进过注入**（limit 扫到 104 都不含它）⇒ Q09 / Q10 与 Q11 / Q12 是
**同一类召回问题**，只是门槛不同。

本脚本给出决策所需的两个数：

1. 该片段在所属文档组内排第几（组内序 = MENTIONS desc + id asc）
   ⇒ 保底 floor 至少要到几才捞得到；
2. 对应的 ``limit`` 与**字符代价**（floor = limit // 文档数 ⇒ limit = floor × 13）。

顺带打印重跑 JSON 里各题 answer 摘要，供人工判答对率（脚本不判分）。

只读取，不写库。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
HERE = Path(__file__).resolve().parent

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
TARGET_CHUNK = "chunk-6c17ea368cd3"  # 含「张伟」的唯一片段


def main() -> None:
    settings = get_settings()
    service = GraphService.instance()

    nodes, _edges, _tr = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    entity_ids = [n.id for n in nodes]

    index: list[tuple[str, str | None, int, int]] = []
    with service._session() as session:  # noqa: SLF001
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

    buckets: dict[str, list[tuple[str, int, int]]] = {}
    for chunk_id, doc_id, mentions, spans in index:
        if doc_id is None:
            continue
        buckets.setdefault(str(doc_id), []).append((chunk_id, mentions, spans))
    for group in buckets.values():
        group.sort(key=lambda item: (-item[1], item[0]))

    print("=== 1. 「张伟」片段的组内排名 ===")
    doc = next(
        (d for d, g in buckets.items() if any(c == TARGET_CHUNK for c, _m, _s in g)),
        None,
    )
    if doc is None:
        print(f"  {TARGET_CHUNK} 不在可达集合内（结构性窗口外，加 limit 无效）")
        return
    group = buckets[doc]
    rank = next(i + 1 for i, (c, _m, _s) in enumerate(group) if c == TARGET_CHUNK)
    print(f"  doc={doc[:8]}  组内第 {rank}/{len(group)} 条 ⇒ floor 需 ≥ {rank}")
    print("  该文档组内前 6 条的 MENTIONS：")
    for i, (cid, mentions, spans) in enumerate(group[:6], start=1):
        mark = " ← 目标" if cid == TARGET_CHUNK else ""
        print(f"    {i}. mentions={mentions:<4} spans={spans}{mark} :: {texts[cid][:60]}")

    n_docs = len(buckets)
    print("\n=== 2. 捞到它所需的 limit 与字符代价 ===")
    need_floor = rank
    for floor in range(need_floor - 1, need_floor + 3):
        limit = floor * n_docs
        selected = select_evidence_chunks(index, limit)
        chars = sum(len(texts.get(cid, "")) for cid in selected)
        ok = TARGET_CHUNK in set(selected)
        print(
            f"  floor={floor:<3} limit={limit:<4} 注入={len(selected):<4} "
            f"字符={chars:<7} 张伟={'命中' if ok else '缺失'}"
        )

    print("\n=== 3. 重跑答案摘要（人工判答对率，脚本不判分） ===")
    path = HERE / "eval_v3_recall52.json"
    if path.exists():
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row["refused"]:
                continue
            print(f"  Q{row['index']:02d}: {str(row.get('answer'))[:100]}")


if __name__ == "__main__":
    main()
