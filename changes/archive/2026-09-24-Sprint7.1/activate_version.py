"""临时：把 Sprint 7.1 批次 A 的共享版本置为 active（PG 真源 + Neo4j 镜像）。

**照抄**路由层的顺序（``api/v1/routes/graph.py::activate_kg_version``）：
先 PG ``KgVersioningService.activate_by_version``，再 Neo4j ``GraphService.activate_kg_version``
——先写 PG 是为了让 PG 成为唯一的准入判定（非 ready 直接拒绝，不会留下脏镜像）。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

VERSION = "v-s71a-fe1c4dc3"


def main() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.services.graphs import GraphService
    from app.services.kg.versioning import KgVersioningService

    settings = get_settings()
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        record = KgVersioningService(db).activate_by_version(
            org_id=settings.default_org_id, version=VERSION
        )
        print(f"[PG] version={record.version} status={record.status}")

    superseded = GraphService.instance().activate_kg_version(
        version=VERSION,
        org_id=settings.default_org_id,
        trace_id=str(uuid.uuid4()),
    )
    print(f"[Neo4j] active={VERSION} superseded={superseded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
