"""破环重建：绕过两个 ingest 脚本的循环依赖，把政策侧整份重放回 Neo4j。

**为什么必须有个 bootstrap**（实读两个脚本确认的死锁）：
- ``ingest_attendance_policies.py`` 在 main 最开头调用 ``load_work_time_systems``，
  图里没有 ``WORK_TIME_SYSTEM`` 就直接抛错，``--no-bridge`` 绕不开；
- ``ingest_attendance_csv.py`` 需要已有 ``POLICY_CLAUSE`` 才能连出 ``GOVERNED_BY``，
  连边为 0 则**回滚并置 failed**。

⇒ 干净图上谁都跑不了第一步。本脚本充当那个「第一步」：直接驱动
``kg.build`` 把政策侧产物重放回图，让 CSV 脚本的桥接有条款可连。

**零 LLM / 零 MinerU 成本**的前提（已核实）：
1. 6 份政策文档在 PG 里都是 ``completed/completed/completed``，抽取产物仍完整留在存储层；
2. ``kg_build_executor`` **不像** ``document_parse_executor`` / ``document_extract_executor``
   那样对 completed 早 return——它进来就置 ``processing`` 往下跑，因此可以免
   费重放（环境问题里这一步是关键的省钱点）。

写操作仅限：删孤儿 Chunk + kg.build 三段落库。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
SCRIPTS = BACKEND / "scripts"
for p in (str(BACKEND), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

KG = "attendance-demo-v1"


def main() -> int:
    # 必须**先** import ingest 模块：它自己的 import 链会先把 app.services 侧铺好，
    # 打破 manager → registry → services.documents → manager 的循环导入。
    # 反过来（先 import app.tasks.registry）会踩 ImportError: partially initialized module。
    from ingest_attendance_policies import (
        CORPUS_DIR,
        POLICY_FILES,
        _document_id,
        load_extraction,
    )

    from app.core.config import get_settings
    from app.db.models import Document, KgVersion
    from app.db.session import SessionLocal
    from app.tasks.registry import kg_build_executor
    from app.tasks.types import TaskSpec
    from neo4j import GraphDatabase

    settings = get_settings()
    org_id = settings.default_org_id

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        driver.verify_connectivity()

        # ---- 0. 先确认"全是孤儿"才敢删 chunk：实体为 0 ⇒ 所有 MENTIONS 已随实体删掉
        with driver.session(database=settings.neo4j_database) as ses:
            entity_count = int(
                ses.run(
                    "MATCH (e:Entity {kg_version: $kg}) RETURN count(e) AS c", kg=KG
                ).single()["c"]
            )
            still_linked = int(
                ses.run(
                    "MATCH (c:Chunk {kg_version: $kg})-[:MENTIONS]->() "
                    "RETURN count(DISTINCT c) AS c",
                    kg=KG,
                ).single()["c"]
            )
            print(f"[0] Entity={entity_count} / 仍有 MENTIONS 的 Chunk={still_linked}")
            if entity_count != 0 or still_linked != 0:
                print(
                    "[FAIL] 图不是预期空态（实体非 0 或仍有 chunk 挂着提及边）⇒ 不敢删，"
                    "先人工确认，避免误删还有效的数据"
                )
                return 1

        # ---- 1. 删孤儿 chunk（此刻全部是孤儿，安全）
        with driver.session(database=settings.neo4j_database) as ses:
            deleted = ses.run(
                "MATCH (c:Chunk {kg_version: $kg}) DETACH DELETE c "
                "RETURN count(c) AS c",
                kg=KG,
            ).consume()
            print(f"[1] 已清孤儿 Chunk：{deleted.counters.nodes_deleted} 个")

        # ---- 2. 逐份：核实产物 → 重放 kg.build
        with SessionLocal() as db:
            row = db.query(KgVersion).filter(KgVersion.version == KG).first()
            if row is None:
                print(f"[FAIL] PG 里没有版本行 {KG}——请先跑一次 CSV 脚本创建版本")
                return 1
            kg_version_id = str(row.id)
            print(f"[2] kg_version_id={kg_version_id}")

        failed: list[str] = []
        for file_name in POLICY_FILES:
            path = CORPUS_DIR / file_name
            doc_id = _document_id(path.stem)
            print(f"\n----- {file_name} ({doc_id}) -----")

            # 产物在位才有资格"免费重放"——这一步同时晒出 valid_to 规模
            entities, relations = load_extraction(org_id=org_id, doc_id=doc_id)
            sealed = [r for r in relations if r.get("valid_to")]
            print(
                f"  产物：实体 {len(entities)} / 关系 {len(relations)} "
                f"（valid_to 非空 {len(sealed)}）"
            )
            if not entities or not relations:
                failed.append(file_name)
                print("  [FAIL] 产物缺失或为空 ⇒ 只能走 --force 重抽（要花钱）")
                continue

            asyncio.run(
                kg_build_executor(
                    TaskSpec(
                        task_type="kg.build",
                        payload={
                            "document_id": str(doc_id),
                            "kg_version_id": kg_version_id,
                        },
                        trace_id=str(uuid.uuid4()),
                    )
                )
            )

            with SessionLocal() as db:
                doc = db.get(Document, doc_id)
                status = doc.kg_build_status if doc else "<none>"
            print(f"  kg.build → {status}")
            if status != "completed":
                failed.append(file_name)

        # ---- 3. 回读全版本真实计数
        with driver.session(database=settings.neo4j_database) as ses:
            ent = ses.run(
                "MATCH (e:Entity {kg_version: $kg}) RETURN count(e) AS c", kg=KG
            ).single()["c"]
            rel = ses.run(
                "MATCH ()-[r:RELATION {kg_version: $kg}]->() RETURN count(r) AS c", kg=KG
            ).single()["c"]
            vt = ses.run(
                "MATCH ()-[r:RELATION {kg_version: $kg}]->() "
                "WHERE r.valid_to IS NOT NULL RETURN count(r) AS c",
                kg=KG,
            ).single()["c"]
            clause = ses.run(
                "MATCH (e:Entity {kg_version: $kg, entity_type: 'POLICY_CLAUSE'}) "
                "RETURN count(e) AS c",
                kg=KG,
            ).single()["c"]
            chunk = ses.run(
                "MATCH (c:Chunk {kg_version: $kg}) RETURN count(c) AS c", kg=KG
            ).single()["c"]
        print("\n===== 重放后 =====")
        print(f"  Entity={ent} / Relation={rel} / valid_to 非空={vt}")
        print(f"  POLICY_CLAUSE={clause} / Chunk={chunk}")

        if failed:
            print(f"\n[FAIL] 未完成：{failed}")
            return 1
        print("\n[OK] 政策侧重放完成 ⇒ 现在可以跑 CSV 脚本（桥接有条款可连了）")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
