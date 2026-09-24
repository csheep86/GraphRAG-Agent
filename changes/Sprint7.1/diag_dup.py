"""临时诊断：疑点为何重复出条（真机 Neo4j 只读查询）。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

VERSION = "v-s71a-fe1c4dc3"

_QUERIES = [
    (
        "LegalPerson 含 缪",
        "MATCH (l:LegalPerson {kg_version: $v}) WHERE l.name CONTAINS '缪'\n"
        "RETURN l.id AS id, l.name AS name, "
        "size(coalesce(l.source_entity_ids, [])) AS n ORDER BY l.name",
    ),
    (
        "Subject 含 招商局集团",
        "MATCH (s:Subject {kg_version: $v}) WHERE s.name CONTAINS '招商局集团'\n"
        "RETURN s.id AS id, s.name AS name, "
        "size(coalesce(s.source_entity_ids, [])) AS n ORDER BY s.name",
    ),
    (
        "Subject 含 招商局轮船",
        "MATCH (s:Subject {kg_version: $v}) WHERE s.name CONTAINS '招商局轮船'\n"
        "RETURN s.id AS id, s.name AS name, "
        "size(coalesce(s.source_entity_ids, [])) AS n ORDER BY s.name",
    ),
    (
        "Address 含 维尔京",
        "MATCH (a:Address {kg_version: $v}) WHERE a.full_address CONTAINS '维尔京'\n"
        "RETURN a.id AS id, a.full_address AS name, "
        "size(coalesce(a.source_entity_ids, [])) AS n ORDER BY a.full_address",
    ),
]


def main() -> int:
    from app.services.graphs import GraphService

    service = GraphService.instance()
    with service._session() as session:  # noqa: SLF001
        for label, query in _QUERIES:
            print(f"== {label}")
            rows = list(session.run(query, v=VERSION))
            for row in rows:
                print(f"   {row['id']} {row['name']!r} sources={row['n']}")
            print(f"   -> 共 {len(rows)} 个节点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
