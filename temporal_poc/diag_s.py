"""诊断 Track S 写入的图：把时态边按时间序打印出来。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

QUERIES = [
    ("LEGAL_REP", "法定代表人"),
    ("REGISTERED_AT", "注册地址"),
    ("HAS_FINANCIAL_INDICATOR", "财务指标"),
]


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    with driver.session(database=settings.neo4j_database) as session:
        for rel_type, label in QUERIES:
            print(f"--- {label} ({rel_type}) ---")
            rows = session.run(
                "MATCH (a:POCS_Entity)-[r:" + rel_type + "]->(b:POCS_Entity) "
                "RETURN a.name AS head, b.name AS tail, r.valid_from AS vf, "
                "r.valid_to AS vt, r.source_episode AS ep ORDER BY r.valid_from"
            )
            found = False
            for row in rows:
                found = True
                head = (row["head"] or "")[:14]
                tail = row["tail"] or ""
                print(
                    f"  {head:16s} -> {tail[:18]:20s} from={row['vf']} "
                    f"to={row['vt']} ep={row['ep']}"
                )
            if not found:
                print("  (无)")
    driver.close()


if __name__ == "__main__":
    main()
