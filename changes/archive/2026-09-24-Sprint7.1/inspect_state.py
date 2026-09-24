"""Sprint 7.1 批次 A 第一步：开工前状态盘点（零成本，只读）。

用法（工作目录 = ``backend/``）：

```powershell
uv run python ../changes/Sprint7.1/inspect_state.py
```

输出四块：
1. 关键配置（**只打长度 / 是否存在，绝不落密钥原文**）；
2. PG 真源 ``kg_versions`` 与 ``documents`` 表现状（SQLite 开发态替身）；
3. Neo4j 图谱现状（各标签计数 + ``:KgVersion`` 状态分布）；
4. 演示素材文件清单与体积。

目的：在花第一分钱之前，把「库内仍是旧正则产物」这句话量化成可复跑的数字。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

REPO_ROOT = BACKEND_DIR.parent


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    return f"len={len(value)}"


def _section(title: str) -> None:
    print(f"\n===== {title} =====")


def dump_settings() -> None:
    _section("1. 关键配置（只打长度，不落密钥）")
    from app.core.config import get_settings

    s = get_settings()
    print(f"app_env                       = {s.app_env}")
    print(f"app_version                   = {s.app_version}")
    print(f"extraction_engine             = {s.extraction_engine}")
    print(f"extraction_prompt_version     = {s.extraction_prompt_version}")
    print(f"extraction_max_chars_per_chunk= {s.extraction_max_chars_per_chunk}")
    print(f"extraction_max_entities_per_doc= {s.extraction_max_entities_per_doc}")
    print(f"extraction_max_relations_per_doc= {s.extraction_max_relations_per_doc}")
    print(f"parser_provider               = {s.parser_provider}")
    print(f"llm_base_url                  = {s.llm_base_url}")
    print(f"llm_model                     = {s.llm_model}")
    print(f"llm_api_key                   = {_mask(s.llm_api_key)}")
    print(f"mineru_token                  = {_mask(s.mineru_token)}")
    print(f"neo4j_uri                     = {s.neo4j_uri}")
    print(f"neo4j_password                = {_mask(s.neo4j_password)}")
    print(f"pipeline_stages               = {s.pipeline_stages}")
    print(f"database_url                  = {s.database_url}")


def dump_pg() -> None:
    _section("2. PG 真源（开发态 SQLite 替身）：kg_versions / documents")
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.db.models import Document, KgVersion

    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        versions = list(db.execute(select(KgVersion)).scalars().all())
        print(f"kg_versions 行数 = {len(versions)}")
        for row in versions:
            print(
                f"  - version={row.version} status={row.status} "
                f"entity_count={row.entity_count} relation_count={row.relation_count} "
                f"ready_at={row.ready_at} org_id={row.org_id} id={row.id}"
            )

        docs = list(db.execute(select(Document)).scalars().all())
        print(f"documents 行数 = {len(docs)}")
        for d in docs:
            print(
                f"  - id={d.id} status={d.status} extract={d.extract_status} "
                f"kg_build={d.kg_build_status} kg_version_id={d.kg_version_id} "
                f"filename_hash={d.filename_hash} size={d.size_bytes} "
                f"created_at={d.created_at}"
            )


def dump_neo4j() -> None:
    _section("3. Neo4j 图谱现状")
    from neo4j import GraphDatabase

    from app.core.config import get_settings

    s = get_settings()
    driver = GraphDatabase.driver(
        s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=10.0
    )
    try:
        driver.verify_connectivity()
        print(f"connected: {s.neo4j_uri} (db={s.neo4j_database})")
        with driver.session(database=s.neo4j_database) as session:
            labels = [
                record["label"]
                for record in session.run("CALL db.labels() YIELD label RETURN label")
            ]
            print(f"labels = {labels}")
            for label in sorted(labels):
                count = session.run(
                    f"MATCH (n:`{label}`) RETURN count(n) AS c"
                ).single()["c"]
                print(f"  :{label:<16} = {count}")

            print("--- :KgVersion 状态分布 ---")
            for record in session.run(
                "MATCH (v:KgVersion) RETURN v.version AS version, v.status AS status, "
                "v.entity_count AS entity_count, v.relation_count AS relation_count "
                "ORDER BY v.version"
            ):
                print(
                    f"  {record['version']:<40} status={record['status']:<12} "
                    f"entity={record['entity_count']} relation={record['relation_count']}"
                )

            print("--- 关系类型分布（全库）---")
            for record in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC"
            ):
                print(f"  {record['t']:<24} = {record['c']}")

            print("--- :Entity 的 type 分布（top 15）---")
            for record in session.run(
                "MATCH (e:Entity) RETURN e.type AS t, count(e) AS c "
                "ORDER BY c DESC LIMIT 15"
            ):
                print(f"  {record['t']!s:<24} = {record['c']}")
    finally:
        driver.close()


def dump_materials() -> None:
    _section("4. 演示素材（docs/annualreport/）")
    folder = REPO_ROOT / "docs" / "annualreport"
    if not folder.exists():
        print(f"目录不存在: {folder}")
        return
    for path in sorted(folder.iterdir()):
        print(f"  {path.name[:70]:<70} {path.stat().st_size / 1_048_576:.2f} MB")


#: 三步重抽的目标素材（D6 修正后：募集说明书 / 年报控股股东章节）
TARGET_PDFS: tuple[str, ...] = (
    "招商蛇口：招商局蛇口工业区控股股份有限公司2024年面向专业投资者公开发行公司债券（第一期）募集说明书.pdf",
    "招商公路：招商局公路网络科技控股股份有限公司2024年面向专业投资者公开发行科技创新公司债券（第一期）募集说明书.pdf",
    "招商轮船：招商轮船2025年年度报告.pdf",
)

#: 成本模型基准（Sprint 7.0 §7.2 真机，非估算）：
#: 蛇口切片 8368 字 / 8 chunk / prompt 20694 + completion 30012 = ¥0.2815
#: → 每千字 ≈ ¥0.0336（input ¥2/百万、output ¥8/百万）
COST_PER_1K_CHARS = 0.2815 / 8368 * 1000


def dump_material_text_stats() -> None:
    """统计目标素材的文本规模并**估算**重抽成本（不调 LLM，零成本）。"""
    _section("5. 重抽规模与成本估算（pypdf 纯文本统计，零成本）")
    import json

    from pypdf import PdfReader

    folder = REPO_ROOT / "docs" / "annualreport"
    cache_dir = BACKEND_DIR / "storage" / "demo-slice"
    cache_dir.mkdir(parents=True, exist_ok=True)

    total_cost = 0.0
    for name in TARGET_PDFS:
        pdf = folder / name
        if not pdf.exists():
            print(f"  [MISSING] {name}")
            continue
        cache = cache_dir / f"{pdf.stem}.pages.json"
        if cache.exists():
            pages = json.loads(cache.read_text(encoding="utf-8"))
        else:
            pages = [(page.extract_text() or "") for page in PdfReader(str(pdf)).pages]
            cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        chars = sum(len(text) for text in pages)
        chunks = chars // 4000 + 1
        cost = chars / 1000 * COST_PER_1K_CHARS
        total_cost += cost
        print(f"  {pdf.name[:44]:<44}")
        print(
            f"      页数={len(pages):>4}  纯文本字数={chars:>7}  "
            f"chunk(4000)≈{chunks:>4}  估算成本≈¥{cost:.2f}"
        )
    print(f"  ---- 三份合计估算 ≈ ¥{total_cost:.2f}（单次重抽；模型见 COST_PER_1K_CHARS）")


def main() -> int:
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in (
        "utf-8",
        "utf8",
    ):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    print("===== Sprint 7.1 批次 A 开工前状态盘点 =====")
    print(f"cwd={os.getcwd()}")
    dump_settings()
    dump_pg()
    dump_neo4j()
    dump_materials()
    dump_material_text_stats()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
