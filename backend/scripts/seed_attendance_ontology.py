"""写入考勤域本体种子（Sprint 9.5 批次 A2）。

用法::

    uv run python scripts/seed_attendance_ontology.py

行为：

1. 建表（``init_db`` → ``create_all``，本项目无 Alembic）；
2. 读取 ``demo/attendance/ontology_schema.json``；
3. 以 ``settings.default_org_id`` 写入 ``version = 1``、``status = active`` 的一行。

**幂等**：该 org 已存在 ``version = 1`` 时跳过，不重复写、不擅自升版。

**纪律（M6 §3.5 验收 12）**：``status = active`` 意味着"已经过确认"。
本脚本是**人工直接编辑**的种子，故 ``suggested_by_llm = false``，
``confirmed_by_user`` 取 ``settings.default_actor_id``——
即把种子数据视同已确认，**不得**用它绕过"未确认不生效"的约束。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import OntologySchema  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402

#: backend/scripts/ → parents[1] = backend/ → parent = 仓库根
REPO_ROOT = BACKEND_DIR.parent
SCHEMA_JSON = REPO_ROOT / "demo" / "attendance" / "ontology_schema.json"


def main() -> int:
    if not SCHEMA_JSON.exists():
        print(f"[FAIL] 找不到种子文件：{SCHEMA_JSON}")
        return 1

    payload = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    settings = get_settings()

    init_db()

    with SessionLocal() as session:
        existing = session.scalar(
            select(OntologySchema).where(
                OntologySchema.org_id == settings.default_org_id,
                OntologySchema.version == 1,
            )
        )
        if existing is not None:
            print(
                f"[SKIP] org {settings.default_org_id} 已有 version=1 "
                f"（status={existing.status}，实体 {len(existing.entity_types)} 类 / "
                f"关系 {len(existing.relation_types)} 类），不重复写入"
            )
            return 0

        row = OntologySchema(
            org_id=settings.default_org_id,
            version=1,
            entity_types=payload["entity_types"],
            relation_types=payload["relation_types"],
            domain_description=payload["domain_description"],
            suggested_by_llm=False,
            confirmed_by_user=settings.default_actor_id,
            status="active",
            trace_id=uuid.uuid4(),
        )
        session.add(row)
        session.commit()

    print(
        f"[OK  ] 已写入考勤域本体：org={settings.default_org_id} version=1 "
        f"status=active | 实体 {len(payload['entity_types'])} 类 / "
        f"关系 {len(payload['relation_types'])} 类"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
