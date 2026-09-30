"""Sprint 10.4 开工前探查（¥0，不调 LLM）——知识时效 L2 可行性。

**为什么分版本探查**：时序字段（ADR-0005 L1）只在 **M4 主体层**的两条边上写
（``(:Subject)-[:LEGAL_REP]->(:LegalPerson)`` / ``(:Subject)-[:REGISTERED_AT]->(:Address)``，
见 ``builder.py`` stage-3.1 / 3.2），而**通用抽取边**（`:Entity`）并不带这些属性；
且当前 active 的演示库是**考勤域**（`attendance-demo-v1`），关联方域是另一个版本。
⇒ 必须分别量，否则会得出"时序能力没落地"的错误结论。

回答三个问题：
1. 哪个版本**真的有**时序数据 ⇒ L2 可用于哪个域；
2. 有没有**失效边**（`valid_to` 非空）⇒ 前端「失效视觉语义」有没有东西可画；
3. 多跳路径查询（``_CYPHER_PATHS``，走 **`:Entity`**）与时序边（**M4 主体层**）
   是否**相交** ⇒ L2「路径时序一致性」有没有适用对象。

用法：``cd backend && uv run python ../changes/Sprint10.4/probe_l2_temporal.py``
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 脚本在 changes/Sprint10.4/ 下，需把 backend/ 加进 sys.path 才能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

# Windows 控制台默认 GBK，输出里的 ``↔`` / ``→`` 会抛 UnicodeEncodeError
# （脚本跑到一半崩 ⇒ 结论只剩一半，比不能跑更糟）。统一按 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

settings = get_settings()

VERSIONS = ["attendance-demo-v1", "affiliation-demo-v1"]


def stat_version(s, kg: str) -> None:
    print(f"\n{'=' * 60}\n=== kg_version = {kg} ===")

    stat = s.run(
        """
        MATCH ()-[r]->()
        WHERE r.kg_version = $kg
        RETURN count(r) AS total,
               count(r.valid_from) AS has_valid_from,
               count(r.valid_to) AS has_valid_to,
               count(r.expired_at) AS has_expired_at,
               count(r.source_document_id) AS has_source_doc
        """,
        kg=kg,
    ).data()[0]
    total = stat["total"]
    print("=== 关系时序字段覆盖 ===")
    for k, v in stat.items():
        pct = (v / total * 100) if total else 0
        print(f"  {k:<16} = {v:<6} ({pct:.1f}%)  / 总 {total}")

    # 时序字段出现在哪些边类型上
    by_type = s.run(
        """
        MATCH ()-[r]->()
        WHERE r.kg_version = $kg AND (r.valid_from IS NOT NULL OR r.valid_to IS NOT NULL)
        RETURN type(r) AS rel, count(*) AS c ORDER BY c DESC
        """,
        kg=kg,
    ).data()
    print("=== 带时序字段的边类型 ===")
    for row in by_type:
        print(f"  {row['rel']} = {row['c']}")

    # 失效边样本
    expired = s.run(
        """
        MATCH (a)-[r]->(b)
        WHERE r.kg_version = $kg AND r.valid_to IS NOT NULL
        RETURN labels(a) AS a_l, coalesce(a.name, a.id) AS a_n, type(r) AS rel,
               labels(b) AS b_l, coalesce(b.name, b.id) AS b_n,
               toString(r.valid_from) AS vf, toString(r.valid_to) AS vt,
               r.invalidated_reason AS reason
        LIMIT 10
        """,
        kg=kg,
    ).data()
    print(f"=== 失效边样本（valid_to 非空，最多 10 条；共 {stat['has_valid_to']} 条）===")
    for row in expired:
        print(
            f"  {row['a_l']}{row['a_n']} -[{row['rel']}]-> {row['b_l']}{row['b_n']}"
            f"  vf={row['vf']} vt={row['vt']} reason={row['reason']}"
        )

    # 时序边的端点标签 ⇒ 判断多跳路径（:Entity）能否走到
    endpoint_labels = s.run(
        """
        MATCH (a)-[r]->(b)
        WHERE r.kg_version = $kg AND (r.valid_from IS NOT NULL OR r.valid_to IS NOT NULL)
        RETURN DISTINCT labels(a) AS a_l, labels(b) AS b_l, type(r) AS rel LIMIT 5
        """,
        kg=kg,
    ).data()
    print("=== 时序边的端点标签（判断与 :Entity 路径查询是否相交）===")
    for row in endpoint_labels:
        print(f"  {row['a_l']} -[{row['rel']}]-> {row['b_l']}")

    # 该版本里 :Entity 边的规模（路径查询的作用域）
    entity_edges = s.run(
        """
        MATCH (a:Entity {kg_version:$kg})-[r]->(b:Entity {kg_version:$kg})
        RETURN count(r) AS c, count(r.valid_from) AS vf, count(r.valid_to) AS vt
        """,
        kg=kg,
    ).data()[0]
    print(
        f"=== :Entity↔:Entity 边（_CYPHER_PATHS 作用域）：共 {entity_edges['c']} 条，"
        f"带 valid_from {entity_edges['vf']} 条、valid_to {entity_edges['vt']} 条 ==="
    )


def main() -> None:
    # SQL 侧：版本真源 + L0 的 document_date 覆盖
    db_path = str(settings.database_url).replace("sqlite:///", "")
    con = sqlite3.connect(db_path)
    tot = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    has = con.execute(
        "SELECT count(*) FROM documents WHERE document_date IS NOT NULL"
    ).fetchone()[0]
    print(f"=== L0 上游：documents.document_date 有值 {has} / 共 {tot} ===")
    for row in con.execute(
        "SELECT version, status, entity_count, relation_count FROM kg_versions"
    ):
        print(f"  版本 {row[0]} status={row[1]} 实体={row[2]} 关系={row[3]}")
    con.close()

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    with driver.session() as s:
        for kg in VERSIONS:
            stat_version(s, kg)

        # 全库兜底：有没有别的版本带时序字段（防止我漏了某个版本）
        others = s.run(
            """
            MATCH ()-[r]->()
            WHERE r.valid_from IS NOT NULL OR r.valid_to IS NOT NULL
            RETURN DISTINCT r.kg_version AS kg, count(*) AS c ORDER BY c DESC
            """
        ).data()
        print("\n=== 全库：哪些 kg_version 带时序字段 ===")
        for row in others:
            print(f"  {row['kg']} = {row['c']} 条")

    driver.close()


if __name__ == "__main__":
    main()
