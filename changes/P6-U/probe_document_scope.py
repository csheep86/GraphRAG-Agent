"""¥0 探针：**「条款 → 它所属的那一版文档」能否确定性建立**。

候选 A（文档级作用域继承）能不能落地，**只取决于这一件事**：

    一条自身无窗口的 POLICY_CLAUSE，能否不靠 LLM、不靠文件名，
    确定性地找回"它出自哪一份制度文档的哪一版"。

能 ⇒ A 是**传播**（值来自文档正文已抽出的施行日/有效期至，逐字可回查），可做；
不能 ⇒ 剩下的唯一办法是按文件名/标题猜 ⇒ 那是 R4 禁止的推断，**必须停下去报告**。

本探针分三步，每一步都要给出可复核的计数：

1. 无窗口条款有多少、它们的属性里有没有天然带线索（doc_id / source / file ...）；
2. 图里有没有代表"文档"的实体，以及条款到它有没有边（直接或一跳）；
3. 只看 Proceedings：取几条实例，把"条款 → 文档"的候选路径真走一遍。

用法::

    uv run python changes/P6-U/probe_document_scope.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

KG = "attendance-demo-v1"

#: ① 无窗口条款 + 它们的属性全集
Q_UNDATED = """
MATCH (p:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg})
WHERE NOT EXISTS { (p)-[r:RELATION {kg_version: $kg}]-()
                   WHERE r.valid_from IS NOT NULL OR r.valid_to IS NOT NULL }
RETURN p.id AS id, p.canonical_name AS name, properties(p) AS props
ORDER BY p.id
"""

#: ② 图里有没有"文档"形态的实体（标题里带"规定/制度/办法/细则"的制度级节点）
Q_DOC_LIKE = """
MATCH (d:Entity {kg_version: $kg})
WHERE d.canonical_name CONTAINS '版'
   OR d.canonical_name ENDS WITH '制度'
   OR d.canonical_name ENDS WITH '规定'
   OR d.canonical_name ENDS WITH '办法'
   OR d.canonical_name ENDS WITH '细则'
RETURN d.id AS id, d.entity_type AS etype, d.canonical_name AS name
ORDER BY d.id
"""

#: ③ 无窗口条款到"文档级实体"是否存在直接边；记录边类型以便判断语义
Q_LINK = """
MATCH (p:Entity {entity_type: 'POLICY_CLAUSE', kg_version: $kg})
      -[r:RELATION {kg_version: $kg}]-(d:Entity {kg_version: $kg})
WHERE p.id IN $ids
  AND (d.canonical_name CONTAINS '版'
       OR d.canonical_name ENDS WITH '制度'
       OR d.canonical_name ENDS WITH '规定'
       OR d.canonical_name ENDS WITH '办法'
       OR d.canonical_name ENDS WITH '细则')
RETURN p.id AS cid, p.canonical_name AS cname,
       type(r) AS rtype, coalesce(r.relation_type, type(r)) AS rel,
       d.id AS did, d.canonical_name AS dname, d.entity_type AS detype
ORDER BY cid, did
"""


def main() -> int:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            undated = [dict(row) for row in session.run(Q_UNDATED, kg=KG)]
            docs = [dict(row) for row in session.run(Q_DOC_LIKE, kg=KG)]
            links = [
                dict(row)
                for row in session.run(
                    Q_LINK, kg=KG, ids=[row["id"] for row in undated]
                )
            ]

            print(f"=== {KG} ===")
            print(f"① 自身无窗口的 POLICY_CLAUSE：{len(undated)} 条")
            if undated:
                keys = sorted(
                    {key for row in undated for key in row["props"]}
                )
                print(f"   属性全集：{keys}")
                print("   前 5 条：")
                for row in undated[:5]:
                    print(f"     {row['id']}  {row['name']}")

            print(f"\n② 文档级实体（标题带『版/制度/规定/办法/细则』）：{len(docs)} 个")
            etypes: dict[str, int] = {}
            for row in docs:
                etypes[row["etype"]] = etypes.get(row["etype"], 0) + 1
            print(f"   entity_type 分布：{etypes}")
            for row in docs[:8]:
                print(f"     {row['etype']:<16} {row['name']}")

            print(f"\n③ 无窗口条款 → 文档级实体 的直接边：{len(links)} 条")
            rels: dict[str, int] = {}
            for row in links:
                rels[row["rel"]] = rels.get(row["rel"], 0) + 1
            print(f"   边类型分布：{rels}")
            covered = {row["cid"] for row in links}
            print(f"   能挂上文档的条款：{len(covered)} / {len(undated)}")
            for row in links[:10]:
                print(f"     {row['cname']} --[{row['rel']}]--> {row['dname']}")
    finally:
        driver.close()

    print("\n=== 判据 ===")
    if links and len(covered_ok := {row["cid"] for row in links}) == len(undated):
        print(f"  ✅ 全部 {len(covered_ok)} 条无窗口条款都能确定性挂到文档 ⇒ A 可做")
        return 0
    if links:
        print(
            f"  ⚠️  只有 {len({row['cid'] for row in links})} / {len(undated)} 条能挂上，"
            "需确认剩余部分如何处理（很可能仍要留空）"
        )
        return 1
    print("  ❌ 一条都挂不上 ⇒ 条款与文档之间没有图链接 ⇒ A 不可做，必须报告")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
