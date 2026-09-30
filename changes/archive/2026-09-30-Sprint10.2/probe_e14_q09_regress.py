"""批次 E 收尾：**Q09 / Q10 回归** 定位 —— ¥0，不调 LLM。

``limit`` 20 → 52 后 Q11 / Q12 得救，但 Q09 / Q10（张伟，employees.csv）
**从答上变拒答**。e13 已排除两个猜测：

- 保底挤掉余量 ⇒ 不成立（20 条 ⊆ 52 条，丢失 0 条）；
- 依据片段没进注入 ⇒ 与 limit 无关（扫到 104 条仍不命中「张伟」）。

剩下两种可能，本脚本分辨：

- **A. 语料侧**：employees.csv 的片段压根不在图里 / 不在可达集合里
  （那 Q09 基线答上纯属"部分支撑"蒙的，闸门这次没放行）；
- **B. LLM 侧**：注入变多 ⇒ 注意力被分散 ⇒ 选了不含凭据的引用 ⇒ 闸门丢弃 ⇒ 拒答。

判据：① ``张伟`` / ``E001`` 在库里哪些 chunk、是否可达、是否在 52 条里；
② 两版 JSON（闸门开基线 vs 52 条重跑）Q09 / Q10 的 answer + citations 对照。
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

    selected_52 = set(select_evidence_chunks(index, 52))
    reachable = {cid for cid, _d, _m, _s in index}

    print("=== 1. 语料侧：依据片段在哪 ===")
    for keyword in ("张伟", "E001", "售后工程师"):
        hits = [cid for cid, t in texts.items() if keyword in t]
        print(f"  含「{keyword}」的 chunk: {len(hits)} 条")
        for cid in hits[:3]:
            print(
                f"    {cid[:18]} 可达={'是' if cid in reachable else '否'} "
                f"在52条={'是' if cid in selected_52 else '否'} :: {texts[cid][:70]}"
            )

    print("\n=== 2. 两版 Q09 / Q10 对照 ===")
    for name in ("eval_v3_gate_on.json", "eval_v3_recall52.json"):
        path = HERE / name
        if not path.exists():
            print(f"  {name}: 不存在")
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["index"] not in (9, 10):
                continue
            cites = ", ".join(
                str(c.get("chunk_id"))[:18] for c in (row.get("citations") or [])
            )
            print(
                f"  {name} Q{row['index']:02d} refused={row['refused']} "
                f"citations=[{cites or '-'}]"
            )
            print(f"      answer: {str(row.get('answer'))[:110]}")


if __name__ == "__main__":
    main()
