"""S10 批次 C 缺口·定方案探针：证据片段（chunk）该怎么选 20 条。

已证事实（``probe_c3_evidence``）：候选集 500 实体反查 chunk，``LIMIT 20``
**无 ORDER BY** ⇒ 注入的 20 条里 **CSV 18 / docx 制度 0**（全图 docx 33 / CSV 178）。
于是问"制度"必然答不到制度内容——这是**纯召回**问题，不是 LLM 引用选错。

与候选集那层（``select_subgraph_nodes``）同族、同思路：**保底 + 余量补齐**，
但这里的分组键换成 ``doc_id``（图上的真实结构，不是文本启发式）。

对照四案：

1. ``current``      现状：无序 LIMIT 20（复刻线上 Cypher 的无序语义）；
2. ``by_mentions``  按被候选实体 MENTION 的次数降序（热度）；
3. ``doc_floor``    每个 ``:Document`` 保底 ``limit // 文档数`` 条，余量按热度补齐；
4. ``doc_floor2``   每文档保底 **2** 条，余量按热度补齐。

``doc_id`` 为 ``None`` 的 chunk（``HAS_CHUNK`` 缺失）**不参与保底**：契约层
``Citation`` 要求 ``doc_id`` 是合法 UUID，这类 chunk 本来就会被调用方丢弃。

指标：① 制度 docx chunk 条数（问答要的落点）；② 覆盖到的 Document 数；
③ **带 span 的 chunk 条数**（span 级引用的必要条件——span 实体得在被注入的片段里）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402

VERSION = "attendance-demo-v1"
LIMIT = 20
_CSV_ROW = re.compile(r"^[A-Za-z]{0,3}\d{3,}[,，]")

#: **仅用于评估**：制度 docx 派生 chunk 是 markdown 正文，CSV 派生是逗号分隔行。
_KIND_CY = """
MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->(e:Entity {kg_version:$v})
WHERE e.id IN $ids
OPTIONAL MATCH (d:Document {kg_version:$v})-[:HAS_CHUNK]->(c)
WITH DISTINCT c, d,
     size([(c)-[:MENTIONS]->(:Entity) | 1]) AS mentions,
     size([(c)-[:MENTIONS]->(e2:Entity) WHERE e2.char_start IS NOT NULL | 1]) AS spans
RETURN c.id AS chunk_id, d.id AS doc_id, c.text AS text, mentions, spans
"""


def _kind(text: str) -> str:
    stripped = (text or "").strip()
    if _CSV_ROW.match(stripped):
        return "CSV"
    if re.search(r"第[一二三四五六七八九十百]+条|制度|规定|办法", stripped):
        return "docx"
    return "other"


def pick(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "current":
        return rows[:LIMIT]
    by_heat = sorted(rows, key=lambda r: (-int(r["mentions"]), str(r["chunk_id"])))
    if mode == "by_mentions":
        return by_heat[:LIMIT]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in by_heat:
        if row["doc_id"] is None:  # 无 HAS_CHUNK：本来也构造不出 Citation
            continue
        groups.setdefault(str(row["doc_id"]), []).append(row)

    floor = 2 if mode == "doc_floor2" else max(LIMIT // max(len(groups), 1), 1)
    chosen: list[dict[str, Any]] = []
    for _doc in sorted(groups):
        chosen.extend(groups[_doc][:floor])
    chosen.sort(key=lambda r: (-int(r["mentions"]), str(r["chunk_id"])))
    chosen = chosen[:LIMIT]
    if len(chosen) < LIMIT:  # 余量补齐
        taken = {r["chunk_id"] for r in chosen}
        # ``doc_floor_span``：余量优先给**带 span** 的片段（引用能被精确定位），
        # 再按热度。span 是图上的真实结构，不针对任何特定文档 ⇒ 不是事后诸葛。
        filler = (
            sorted(
                by_heat,
                key=lambda r: (0 if int(r["spans"] or 0) > 0 else 1, -int(r["mentions"]), str(r["chunk_id"])),
            )
            if mode == "doc_floor_span"
            else by_heat
        )
        for row in filler:
            if len(chosen) >= LIMIT:
                break
            if row["chunk_id"] not in taken:
                chosen.append(row)
                taken.add(row["chunk_id"])
    return chosen[:LIMIT]


def main() -> None:
    graphs = GraphService.instance()
    nodes, _edges, _t = graphs.fetch_all_subgraph(
        kg_version=VERSION, org_id=None, node_limit=500
    )
    ids = [n.id for n in nodes]
    with graphs._session() as session:  # noqa: SLF001
        rows = [
            dict(r)
            for r in session.run(_KIND_CY, v=VERSION, ids=ids)
        ]
    with graphs._session() as session:  # noqa: SLF001
        reachable = session.run(
            "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->(e:Entity {kg_version:$v}) "
            "WHERE e.id IN $ids RETURN count(DISTINCT c) AS n",
            v=VERSION,
            ids=ids,
        ).single()["n"]
    print(f"候选集可反查到的 chunk：{reachable} 条（注入上限 {LIMIT}）")

    print(f"\n{'方案':<16}{'docx':>6}{'CSV':>6}{'other':>7}{'覆盖文档':>10}{'带span':>8}")
    for label, mode in (
        ("current", "current"),
        ("by_mentions", "by_mentions"),
        ("doc_floor", "doc_floor"),
        ("doc_floor2", "doc_floor2"),
        ("doc_floor_span", "doc_floor_span"),
    ):
        selected = pick(rows, mode)
        kinds: dict[str, int] = {}
        for row in selected:
            kind = _kind(row["text"] or "")
            kinds[kind] = kinds.get(kind, 0) + 1
        docs = len({str(r["doc_id"]) for r in selected if r["doc_id"] is not None})
        with_span = sum(1 for r in selected if int(r["spans"] or 0) > 0)
        print(
            f"{label:<16}{kinds.get('docx', 0):>6}{kinds.get('CSV', 0):>6}"
            f"{kinds.get('other', 0):>7}{docs:>10}{with_span:>8}"
        )

    print("\n--- doc_floor 选中明细 ---")
    for index, row in enumerate(pick(rows, "doc_floor"), start=1):
        head = (row["text"] or "").replace("\n", " ")[:46]
        print(
            f"  {index:>2}. [{_kind(row['text']):<5}] span={int(row['spans'] or 0)} "
            f"| {head}"
        )


if __name__ == "__main__":
    main()
