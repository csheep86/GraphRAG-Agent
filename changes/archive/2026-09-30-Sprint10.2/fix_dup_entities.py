"""一次性数据修复：清掉**重跑 ingest 造成的重复实体**（Sprint 10 批次 E）。

与 ``fix_dup_chunks.py`` 同源：实体 id 原为 ``ent_{uuid4()}`` 随机生成 ⇒ 写侧
``MERGE`` 按 id 去重失效。代码侧已改确定性（``langextract._stabilize_ids``），
**已落库的重复**需本脚本清理。

判据（**严格**，这是本批最容易被做错的地方）：
    ``(canonical_name, entity_type, char_start, char_end)`` 全等才算重复

**为什么不按名字判重**：``probe_e7_entity_dup.py`` 按「同名 + 同类型」得到 2224 个
"重复"，但「2026-10-19 正常班」×37 是 **37 个员工各自的排班**（不同实体，只是名字撞了，
挂在不同 chunk / 不同偏移上）。按名字清理会**误删真数据**。
严格判据下真实重复只有 **2 组 3 个**（``probe_e9_entity_edges.py`` 实测）。

另有一批「同一 chunk + 同名」但 **char_start 缺失**的实体：没有偏移就**无法证明**
是重跑重复（也可能是同一提及的多次登记）⇒ **本脚本不动**，只列出来留痕。

安全约束：
- 默认 **dry-run**，``--apply`` 才真删；
- 只处理已知边类型 ``MENTIONS`` / ``RELATION``；被删实体若挂着**其它类型**的边，
  **拒绝删除并告警**（宁可留着脏数据，也不静默丢证据）；
- 删前把边 ``MERGE`` 到保留节点，边 id 按 builder 的原规则重算
  （``MENTIONS = {kg}:m:{chunk}:{entity}``；``RELATION`` 沿用原 relation id）；
- 清理前后**对账**：实体数 / MENTIONS 数 / RELATION 数。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

VERSION = "attendance-demo-v1"
#: 已知可安全迁移的边类型；出现其它类型一律**拒绝删除**（不静默丢边）
KNOWN_EDGE_TYPES = frozenset({"MENTIONS", "RELATION"})


def _snapshot(session, version: str) -> dict[str, int]:
    return {
        "entities": session.run(
            "MATCH (e:Entity {kg_version:$v}) RETURN count(e) AS n", v=version
        ).single()["n"],
        "mentions": session.run(
            "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->(e:Entity {kg_version:$v}) "
            "RETURN count(*) AS n",
            v=version,
        ).single()["n"],
        "relations": session.run(
            "MATCH (a:Entity {kg_version:$v})-[r:RELATION]->(b:Entity {kg_version:$v}) "
            "RETURN count(r) AS n",
            v=version,
        ).single()["n"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="真删（默认 dry-run）")
    parser.add_argument("--version", default=VERSION, help="要清理的 kg_version")
    args = parser.parse_args()

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    removed = skipped = 0
    try:
        with driver.session() as session:
            before = _snapshot(session, args.version)
            groups = session.run(
                "MATCH (e:Entity {kg_version:$v}) "
                "WITH coalesce(e.canonical_name, e.name) AS k, e.entity_type AS t, "
                "e.char_start AS cs, e.char_end AS ce, collect(e.id) AS ids "
                "WHERE size(ids) > 1 AND k IS NOT NULL AND cs IS NOT NULL "
                "AND ce IS NOT NULL "
                "RETURN k, t, cs, ce, ids ORDER BY size(ids) DESC",
                v=args.version,
            ).data()

            # 证据不足的那一批：只留痕，不动
            weak = session.run(
                "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->(e:Entity {kg_version:$v}) "
                "WITH c.id AS cid, coalesce(e.canonical_name, e.name) AS k, "
                "collect(e.id) AS ids WHERE size(ids) > 1 "
                "RETURN count(*) AS groups, sum(size(ids) - 1) AS extra",
                v=args.version,
            ).single()

            print(f"kg_version={args.version}  严格判据重复组 {len(groups)}")
            print(
                f"（另有「同 chunk 同名」组 {weak['groups']} / 多出 {weak['extra']} "
                "个：偏移缺失 ⇒ 无法证明是重跑重复，本脚本**不动**）\n"
            )

            for group in groups:
                keep = sorted(group["ids"])[0]
                dups = [i for i in group["ids"] if i != keep]
                print(
                    f"  {str(group['k'])[:20]:<22}{group['t']:<18}"
                    f"[{group['cs']},{group['ce']})  保留={keep} 拟删={dups}"
                )
                if not args.apply:
                    removed += len(dups)
                    continue

                for dup in dups:
                    types = {
                        row["t"]
                        for row in session.run(
                            "MATCH (e:Entity {id:$id})-[r]-() "
                            "RETURN DISTINCT type(r) AS t",
                            id=dup,
                        ).data()
                    }
                    if not types <= KNOWN_EDGE_TYPES:
                        skipped += 1
                        print(
                            f"    !! {dup} 挂着未知边类型 {sorted(types - KNOWN_EDGE_TYPES)}"
                            " ⇒ 拒绝删除（避免静默丢证据）"
                        )
                        continue

                    # 1) MENTIONS：chunk -> 被删实体 改挂到保留实体（id 按 builder 规则）
                    session.run(
                        "MATCH (c:Chunk)-[r:MENTIONS]->(dup:Entity {id:$dup}) "
                        "MATCH (keep:Entity {id:$keep}) "
                        "MERGE (c)-[nr:MENTIONS {id: $kg + ':m:' + c.id + ':' + $keep, "
                        "kg_version: $kg}]->(keep) "
                        "ON CREATE SET nr.org_id = r.org_id, nr.trace_id = r.trace_id "
                        "DELETE r",
                        dup=dup,
                        keep=keep,
                        kg=args.version,
                    )
                    # 2) RELATION：按 (kg_version, relation_type) 合并到保留实体，
                    #    避免同端点同类型造出并行边
                    session.run(
                        "MATCH (dup:Entity {id:$dup})-[r:RELATION]-(other:Entity) "
                        "WHERE other.id <> $keep "
                        "MATCH (keep:Entity {id:$keep}) "
                        "WITH r, other, keep, "
                        "CASE startNode(r).id WHEN $dup THEN 'out' ELSE 'in' END AS dir "
                        "FOREACH (_ IN CASE dir WHEN 'out' THEN [1] ELSE [] END | "
                        "  MERGE (keep)-[nr:RELATION {kg_version: $kg, "
                        "  relation_type: r.relation_type}]->(other) "
                        "  ON CREATE SET nr.id = r.id, nr.evidence = r.evidence, "
                        "  nr.confidence = r.confidence, nr.org_id = r.org_id, "
                        "  nr.trace_id = r.trace_id) "
                        "FOREACH (_ IN CASE dir WHEN 'in' THEN [1] ELSE [] END | "
                        "  MERGE (other)-[nr:RELATION {kg_version: $kg, "
                        "  relation_type: r.relation_type}]->(keep) "
                        "  ON CREATE SET nr.id = r.id, nr.evidence = r.evidence, "
                        "  nr.confidence = r.confidence, nr.org_id = r.org_id, "
                        "  nr.trace_id = r.trace_id) "
                        "DELETE r",
                        dup=dup,
                        keep=keep,
                        kg=args.version,
                    )
                    session.run(
                        "MATCH (e:Entity {id:$id}) DETACH DELETE e", id=dup
                    )
                    removed += 1

            after = _snapshot(session, args.version)
    finally:
        driver.close()

    print(f"\n{'已删除' if args.apply else '将删除'} {removed} 个重复实体，拒绝 {skipped} 个")
    print("对账（实体 / MENTIONS / RELATION）:")
    print(f"  清理前: {before}")
    print(f"  清理后: {after}")
    if not args.apply:
        print("（dry-run：确认无误后加 --apply）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
