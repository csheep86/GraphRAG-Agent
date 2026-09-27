"""核对 Track G 落盘结果：双时态覆盖、历史保留、当前值。

用脚本文件而非命令行，规避 PowerShell 对 $ 的转义破坏 Cypher。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

GROUP_ID = "track-g-poc"


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    with driver.session(database=settings.neo4j_database) as session:
        rows = list(
            session.run(
                "MATCH (a:Entity {group_id: $gid})-[r:RELATES_TO]->(b:Entity {group_id: $gid}) "
                "RETURN r.fact AS fact, r.valid_at AS va, r.invalid_at AS ia, "
                "r.created_at AS ca, r.expired_at AS ea",
                gid=GROUP_ID,
            )
        )
    driver.close()

    alive = [r for r in rows if r["ia"] is None]
    invalidated = [r for r in rows if r["ia"] is not None]
    print(f"edges={len(rows)}  alive={len(alive)}  invalidated={len(invalidated)}")
    print(f"双时态覆盖：valid_at 有值 {sum(1 for r in rows if r['va'] is not None)}"
          f"，expired_at 有值 {sum(1 for r in rows if r['ea'] is not None)}")
    print("--- 自动判失效（历史仍可查） ---")
    for row in invalidated:
        print(f"  * {row['fact'][:46]} | invalid_at={str(row['ia'])[:10]}")
    print("--- 当前有效 ---")
    for row in alive:
        print(f"  > {row['fact'][:46]} | valid_at={str(row['va'])[:10]}")


if __name__ == "__main__":
    main()
