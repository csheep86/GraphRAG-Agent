"""P6-X2（**F-P6X-5**）：把图库 ``:KgVersion`` 镜像里 ``org_id`` 为 ``NULL`` 的历史节点补齐。

**背景（本机实测，2026-10-12）**：图库 3 个 ``:KgVersion`` 节点的 ``org_id`` **全为 ``NULL``**、
``status`` **全为 ``active``** —— 它们不是经 ``GraphService.activate_kg_version`` 写的，
而是历史导入脚本（``import_to_neo4j.py`` / ``ingest_*.py``）直接 ``MERGE`` 出来的，
那些 Cypher 里没有 ``org_id`` 这一维。

**为什么要补**：``activate_kg_version`` 自 P6-X2 起只 supersede **同 org** 的镜像
（否则 A 租户激活会把 B 租户的版本一并取代）。``NULL`` 节点既不属于任何 org，
也就**永远不会**被 supersede ⇒ 会一直以 ``active`` 的身份留在库里。

**本脚本做什么**：按 ``version`` 从 **PG 真源** ``kg_versions`` 反查该版本属于哪个 org，
再把 ``org_id`` 写回图库节点。**认不出来的（PG 里没有这个 version）一律不动** ——
猜不出来就不猜，留着 ``NULL`` 也不会被兜底查询命中（fail-closed，见
``graphs._QUERY_ACTIVE_KG_VERSION``）。

**默认干跑**：不带 ``--apply`` 只打印计划，一个字节都不写。
⚠️ **本批（P6-X2）不执行它** —— Non-goal 6：不许碰生产 / 目标环境的真实数据；
是否执行、在哪套环境执行，由人在演练前裁决。

用法::

    uv run python scripts/migrate_kg_version_org.py --org-id <uuid> [--org-id <uuid>] [--apply]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

# 让脚本能直接 import app.*（与同目录其它脚本一致）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models import KgVersion  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402

# Windows 控制台默认 GBK（cp936），本脚本会打印中文与箭头 ⇒ 不强制就崩
# （`tests/test_script_stdio_utf8.py` 的门禁要求：可直接运行的脚本必须有这段）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 图库侧：列出 ``org_id`` 缺失的镜像节点
_CYPHER_NULL_ORG_VERSIONS = """
MATCH (v:KgVersion)
WHERE v.org_id IS NULL
RETURN v.version AS version
ORDER BY v.version
"""

#: 图库侧：补写 ``org_id``（**只**补为空的，不覆盖已有值）
_CYPHER_SET_ORG_ID = """
MATCH (v:KgVersion {version: $version})
WHERE v.org_id IS NULL
SET v.org_id = $org_id
RETURN v.version AS version
"""


def _pg_version_owner(raw_org_ids: list[str]) -> dict[str, UUID]:
    """从 PG 真源取 ``version -> org_id`` 映射（逐 org 走 RLS，不看全表）。"""
    mapping: dict[str, UUID] = {}
    init_db()
    for raw in raw_org_ids:
        org_id = UUID(raw)
        with session_scope(org_id=org_id) as session:
            rows = session.execute(
                select(KgVersion.version, KgVersion.org_id).where(
                    KgVersion.org_id == org_id
                )
            ).all()
        for version, row_org_id in rows:
            mapping[str(version)] = row_org_id
    return mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org-id",
        action="append",
        default=[],
        required=True,
        help="要对齐的 org（可重复；逐 org 走 RLS 查 PG 真源）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真的写图库；不带则只打印计划（默认干跑）",
    )
    args = parser.parse_args(argv)

    mapping = _pg_version_owner(args.org_id)
    graph = GraphService.instance()
    with graph._session() as session:  # noqa: SLF001 - 脚本侧读内部会话，与 restore.py 同款
        null_versions = [
            str(record["version"]) for record in session.run(_CYPHER_NULL_ORG_VERSIONS)
        ]

    print(f"PG 真源: {len(mapping)} 个 version 可归属")
    print(f"图库 org_id 为空: {len(null_versions)} 个 -> {null_versions}")

    planned = [
        (version, mapping[version]) for version in null_versions if version in mapping
    ]
    unknown = [version for version in null_versions if version not in mapping]

    print(f"\n可补齐: {len(planned)} 个")
    for version, org_id in planned:
        print(f"  - {version} -> {org_id}")
    if unknown:
        print(f"\n认不出来（PG 里没有该 version）: {len(unknown)} 个 -> {unknown}")
        print("  一律不动：猜不出来就不猜，留 NULL 也不会被兜底查询命中")

    if not args.apply:
        print("\n[DRY-RUN] 未写入任何数据；加 --apply 才会写")
        return 0

    written = 0
    with graph._session() as session:  # noqa: SLF001
        for version, org_id in planned:
            session.run(_CYPHER_SET_ORG_ID, version=version, org_id=str(org_id))
            written += 1
    logger.bind(written=written).info("kg_version_mirror_org_migrated")
    print(f"\n[APPLY] 已写入 {written} 个节点的 org_id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
