"""批次 D：docx「解析 → 抽取 → 建图」产物在 active 图里的**真实现状**（只读）。

``scripts/ingest_attendance_policies.py`` 就是这条链路的现成入口（MinerU 解析 →
LangExtract 抽取 → kg.build 三段式），Sprint 9.5 跑过一次。本探针回答两个问题：

1. 四份 docx 的产物**在不在** active 图里（Chunk / span 实体 / 条款节点各多少）；
2. 若已在 ⇒ 端到端问答能否问到它们（由 ``probe_e2e_abc.py`` 佐证），
   不必再烧一遍 MinerU + LLM 额度去"重跑证明已经证明过的事"。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402

VERSION = "attendance-demo-v1"


def main() -> None:
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        for label, cypher in (
            ("Document", "MATCH (d:Document {kg_version:$v}) RETURN count(d) AS n"),
            ("Chunk", "MATCH (c:Chunk {kg_version:$v}) RETURN count(c) AS n"),
            ("Entity", "MATCH (e:Entity {kg_version:$v}) RETURN count(e) AS n"),
            (
                "带 span 的 Entity（抽取产物）",
                "MATCH (e:Entity {kg_version:$v}) WHERE e.char_start IS NOT NULL "
                "RETURN count(e) AS n",
            ),
            (
                "POLICY_CLAUSE",
                "MATCH (e:Entity {kg_version:$v, entity_type:'POLICY_CLAUSE'}) "
                "RETURN count(e) AS n",
            ),
            (
                "Chunk -[MENTIONS]-> Entity",
                "MATCH (c:Chunk {kg_version:$v})-[r:MENTIONS]->(e:Entity) "
                "RETURN count(r) AS n",
            ),
        ):
            row = session.run(cypher, v=VERSION).single()
            print(f"  {label:<28}: {row['n']}")

        print("\n  Chunk 样例（前 3 条，看是否来自 docx 制度文档）:")
        for row in session.run(
            "MATCH (c:Chunk {kg_version:$v}) RETURN c.id AS id, c.text AS text LIMIT 3",
            v=VERSION,
        ):
            text = (row["text"] or "").replace("\n", " ")
            print(f"    {row['id']}: {text[:70]}")

        # active 版本里"带 span 的实体"为 0 —— 可能是真没落，也可能是字段名不同。
        # 打印抽取产物实体（id 前缀 ent_）的**属性键**，把两种可能分开。
        row = session.run(
            "MATCH (e:Entity {kg_version:$v}) WHERE e.id STARTS WITH 'ent_' "
            "RETURN count(e) AS n",
            v=VERSION,
        ).single()
        print(f"\n  抽取产物实体（id 前缀 ent_）: {row['n']}")
        for row in session.run(
            "MATCH (e:Entity {kg_version:$v}) WHERE e.id STARTS WITH 'ent_' "
            "RETURN e.id AS id, keys(e) AS keys LIMIT 2",
            v=VERSION,
        ):
            print(f"    {row['id']} keys={row['keys']}")

        print("\n  POLICY_CLAUSE 样例（前 5 条）:")
        for row in session.run(
            "MATCH (e:Entity {kg_version:$v, entity_type:'POLICY_CLAUSE'}) "
            "RETURN e.canonical_name AS name, e.char_start AS span LIMIT 5",
            v=VERSION,
        ):
            print(f"    span={row['span']} name={str(row['name'])[:50]!r}")


if __name__ == "__main__":
    main()
