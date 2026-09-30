"""一次性数据修复：清掉 **历史重复 chunk**（Sprint 10 批次 E 实测发现）。

背景（``probe_e3_dup.py``）：chunk id 原为 ``uuid4()`` 随机生成 ⇒ 同一份制度文档
每重跑一次 ingest 就多一套 ``:Chunk``（写侧 ``MERGE`` 按 id，去重失效）。
实测 ``attendance-demo-v1``：230 chunks → 去重后 205（重复 25 条，同一段最多 4 份）。

代码侧已改为**确定性 id**（``langextract.py::_new_chunk_id``，按
``document_id|char_start|text`` 取 sha256）⇒ 以后重跑不会再产生重复；
但**已经落库的重复**不会自己消失，需本脚本清理。

安全约束：
- 默认 **dry-run**，只打印将做什么；加 ``--apply`` 才真删；
- 每组重复保留 **id 最小**的那一个，且删除前把被删节点的 ``MENTIONS`` 目标
  ``MERGE`` 到保留节点（重复 chunk 的文本与区间相同 ⇒ 实体归属本应一致，
  这里显式补边，避免"清重"顺手把证据边清掉）；
- 只处理显式给出的 ``kg_version``。
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="真删（默认 dry-run）")
    parser.add_argument("--version", default=VERSION, help="要清理的 kg_version")
    args = parser.parse_args()

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    removed = 0
    try:
        with driver.session() as session:
            groups = session.run(
                "MATCH (c:Chunk {kg_version:$v})<-[:HAS_CHUNK]-(d:Document) "
                "WITH d.id AS did, c.char_start AS cs, c.text AS txt, "
                "collect(c.id) AS ids, count(c) AS n WHERE n > 1 "
                "RETURN did, cs, txt, ids, n ORDER BY n DESC",
                v=args.version,
            ).data()
            print(f"kg_version={args.version}  重复组 {len(groups)}")
            for group in groups:
                keep = sorted(group["ids"])[0]
                dups = [i for i in group["ids"] if i != keep]
                removed += len(dups)
                print(
                    f"  doc={str(group['did'])[:8]} cs={group['cs']} x{group['n']} "
                    f"保留={keep} 删除={len(dups)}"
                )
                if not args.apply:
                    continue
                for dup in dups:
                    # 1) 先把被删节点的证据边补到保留节点（幂等 MERGE）
                    session.run(
                        "MATCH (keep:Chunk {id:$keep, kg_version:$v}), "
                        "(dup:Chunk {id:$dup, kg_version:$v}) "
                        "MATCH (dup)-[:MENTIONS]->(e:Entity) "
                        "MERGE (keep)-[r:MENTIONS {id: $v + ':m:' + keep.id + ':' "
                        "+ e.id, kg_version: $v}]->(e)",
                        keep=keep,
                        dup=dup,
                        v=args.version,
                    )
                    # 2) 再删（DETACH 会一并清掉 HAS_CHUNK / MENTIONS）
                    session.run(
                        "MATCH (c:Chunk {id:$id, kg_version:$v}) DETACH DELETE c",
                        id=dup,
                        v=args.version,
                    )

            total = session.run(
                "MATCH (c:Chunk {kg_version:$v}) RETURN count(c) AS n", v=args.version
            ).single()["n"]
    finally:
        driver.close()

    print(f"\n{'已删除' if args.apply else '将删除'} {removed} 条重复 chunk")
    print(f"剩余 chunk: {total}")
    if not args.apply:
        print("（dry-run：确认无误后加 --apply）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
