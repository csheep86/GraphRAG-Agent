"""**P6-D · T5**：L2 端到端逐跳冒烟（只读，不改任何数据）。

一句人话：把「这篇文档到底走了几跳、能不能标 L2」这个问题，
从**人嘴里的说法**变成**机器打印的事实**。

用法（工作目录 = ``backend/``，需真 Neo4j + 真 PG）::

    uv run python scripts/probe_l2_e2e.py --kg-version attendance-demo-v1

输出：逐跳「通 / 不通」+ 依据 + 最终 ``corpus_layer`` 判定。
**退出码**：全通 = 0；有未打通的跳 = 1（可用于人工复核，当前**不进 CI**，见文末说明）。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

#: 以脚本方式运行时 ``app`` 不在 ``sys.path`` 上（与其他 ``scripts/`` 下的脚本同款处理）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.disable(logging.CRITICAL)

DEFAULT_KG_VERSION = "attendance-demo-v1"

#: **M2 抽取产物的可机判标记**：抽取器生成的实体 id 前缀（``ent_<hash>``）。
#: 依据：``scripts/ingest_attendance_csv.py`` 头注释「后者产物为 ``ent_*`` span 实体」；
#: 实测（2026-10-05）：``attendance-demo-v1`` 有 180 个，``affiliation-demo-v2`` 有 0 个
#: ⇒ 该标记能把「走了 M2」与「CSV 直灌」区分开。
M2_ENTITY_ID_PREFIX = "ent_"


def _driver() -> Any:
    from neo4j import GraphDatabase  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )


def _hop(session: Any, title: str, query: str, **params: Any) -> tuple[bool, str]:
    """跑一条判据查询；返回 ``(是否通, 依据)``。"""
    try:
        value = session.run(query, **params).single()
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本要把故障说出来，不让它炸出来
        return False, f"查询失败: {exc!r}"
    n = int(value[0]) if value else 0
    return n > 0, f"{n}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L2 端到端逐跳冒烟（只读）")
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument("--org-id", default="")
    args = parser.parse_args(argv)
    kg = args.kg_version

    driver = _driver()
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Neo4j 不可达: {exc!r}", file=sys.stderr)
        return 1

    results: list[tuple[str, bool, str]] = []
    with driver.session() as session:
        results.append(
            (
                "H1/M1 解析（真机文档 -> full.md）",
                *_hop(
                    session,
                    "h1",
                    "MATCH (d:Document {kg_version: $kg}) RETURN count(d) AS n",
                    kg=kg,
                ),
            )
        )
        results.append(
            (
                "H2/M2 抽取（ent_* 产物）",
                *_hop(
                    session,
                    "h2",
                    "MATCH (e:Entity {kg_version: $kg}) "
                    f"WHERE e.id STARTS WITH '{M2_ENTITY_ID_PREFIX}' RETURN count(e) AS n",
                    kg=kg,
                ),
            )
        )
        results.append(
            (
                "H3 入图（:Chunk）",
                *_hop(
                    session,
                    "h3",
                    "MATCH (c:Chunk {kg_version: $kg}) RETURN count(c) AS n",
                    kg=kg,
                ),
            )
        )
        results.append(
            (
                "H4 检索（MENTIONS 证据链）",
                *_hop(
                    session,
                    "h4",
                    "MATCH (c:Chunk {kg_version: $kg})-[:MENTIONS]->() RETURN count(c) AS n",
                    kg=kg,
                ),
            )
        )
        results.append(
            (
                "H3+ 两链路汇合（GOVERNED_BY 跨源边）",
                *_hop(
                    session,
                    "h3b",
                    "MATCH ()-[r:RELATION {kg_version: $kg, relation_type: 'GOVERNED_BY'}]->() "
                    "RETURN count(r) AS n",
                    kg=kg,
                ),
            )
        )

    print("===== L2 端到端逐跳冒烟 =====")
    print(f"kg_version : {kg}")
    failed = 0
    for title, ok, evidence in results:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {title} —— {evidence}")
        failed += 0 if ok else 1

    #: ---- corpus_layer 判定（**随实测反推**，不写死）----
    from app.evaluation.corpus_layer import detect_corpus_layer  # noqa: PLC0415

    layer = detect_corpus_layer(
        kg_version=kg, org_id=UUID(args.org_id) if args.org_id else None
    )
    print(f"corpus_layer: {layer or 'UNKNOWN（图不可用，不猜）'}")
    driver.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
