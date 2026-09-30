"""S10 批次 C 缺口·第二层：候选集里**有**新实体（24/31），为什么问答仍引回 CSV？

候选集（500 实体）之后还有一道**证据片段**闸门：``fetch_evidence_chunks`` 按
``MENTIONS`` 反查 chunk，``LIMIT _EVIDENCE_CHUNK_LIMIT = 20``（**无排序、无打分**，
见 ``eval_controlled_qset.py`` 注释）。所以真相可能是：

- (a) 制度 chunk 根本没进这 20 条 ⇒ 纯召回问题（本探针要证）；
- (b) 制度 chunk 进了 20 条，但 LLM 仍引了 CSV chunk ⇒ 那是**引用选择**问题，
      与召回/候选集无关，改候选集也救不了（别把力气花错地方）。

本探针照实分这两种，不预设答案。

来源判别：制度 docx 派生 chunk 是 markdown 正文（含「第…条 / 制度 / 规定」等），
CSV 派生是逗号分隔行。仅用于**评估**，不参与任何选择逻辑。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_LIMIT,
    GraphService,
)

VERSION = "attendance-demo-v1"
_CSV_ROW = re.compile(r"^[A-Za-z]{0,3}\d{3,}[,，]")


def _kind(text: str) -> str:
    stripped = (text or "").strip()
    if _CSV_ROW.match(stripped):
        return "CSV"
    if re.search(r"第[一二三四五六七八九十百]+条|制度|规定|办法", stripped):
        return "docx"
    return "other"


def main() -> None:
    graphs = GraphService.instance()

    with graphs._session() as session:  # noqa: SLF001
        total = session.run(
            "MATCH (c:Chunk {kg_version:$v}) RETURN count(c) AS n", v=VERSION
        ).single()["n"]
        kinds: dict[str, int] = {}
        for row in session.run(
            "MATCH (c:Chunk {kg_version:$v}) RETURN c.text AS text", v=VERSION
        ):
            kind = _kind(row["text"] or "")
            kinds[kind] = kinds.get(kind, 0) + 1
    print(f"active 版本 chunk 总数 {total}：{kinds}")

    nodes, _edges, _truncated = graphs.fetch_all_subgraph(
        kg_version=VERSION, org_id=None, node_limit=500
    )
    entity_ids = [n.id for n in nodes]

    chunks = graphs.fetch_evidence_chunks(
        kg_version=VERSION, org_id=None, entity_ids=entity_ids
    )
    print(
        f"\n线上注入（候选 {len(entity_ids)} 实体 → 反查 chunk，"
        f"LIMIT {_EVIDENCE_CHUNK_LIMIT}）：实得 {len(chunks)} 条"
    )
    injected: dict[str, int] = {}
    for chunk in chunks:
        kind = _kind(chunk.text)
        injected[kind] = injected.get(kind, 0) + 1
    print(f"  注入 chunk 来源分布：{injected}")

    for index, chunk in enumerate(chunks, start=1):
        head = (chunk.text or "").replace("\n", " ")[:52]
        print(f"  {index:>2}. [{_kind(chunk.text):<5}] {chunk.id} | {head}")

    # 不限 20 条时，被候选集 MENTION 的 chunk 有多少（看 20 这条闸门砍掉了什么）
    with graphs._session() as session:  # noqa: SLF001
        row = session.run(
            "MATCH (c:Chunk {kg_version:$v})<-[:MENTIONS]-(e:Entity {kg_version:$v}) "
            "WHERE e.id IN $ids RETURN count(DISTINCT c) AS n",
            v=VERSION,
            ids=entity_ids,
        ).single()
    print(f"\n  候选集实际 MENTION 到的 chunk（不设 20 上限）：{row['n']} 条")


if __name__ == "__main__":
    main()
