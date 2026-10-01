"""A 路线探针：**按产物 id 精确归因**——重抽出来的这批边，有多少带了 ``valid_to``。

为什么不能看图里的总数
----------------------
通用层实体 id 是抽取产物里的 ``ent_<uuid>``，**每次抽取都变**（``builder.py:1100`` 的注释）；
``--force`` 重抽**不会**覆盖上一代，而是**追加一代**。所以「图里 ``valid_to`` 共几条」
会把上一代的 2 条混进来，**分不清是这版语料的功劳还是上一版的残影**。

本探针绕开这一点：直接读该文档**当前**的抽取产物 ``relations.json``（``--force`` 已把它
换成新代），拿这批 id 去图上查 —— 这就是 ``ingest_attendance_policies.py`` 的
「按 id 逐个核对」口径，也是**不需要删数据**就能给出结论的唯一诚实做法。

用法（工作目录任意）::

    uv run python changes/Sprint10.5/probe_regen_validity.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.storage import build_extract_artifact_key, get_storage  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

KG_VERSION = "attendance-demo-v1"

#: 与 ``backend/scripts/ingest_attendance_policies.py::_document_id`` 必须一致
#: （不一致就会读到别的文档的产物——那种错误不会报错，只会给出一份"看起来正常"的假报告）
_DOC_URN = "urn:graphrag-agent:demo:attendance:policy-doc:{stem}"

DOC_STEMS = ("attendance-policy-2025", "fieldwork-attendance-rules-2025")

_CYPHER_BY_IDS = """
UNWIND $ids AS rid
MATCH (a)-[r:RELATION {kg_version: $kg_version}]->(b)
WHERE r.id = rid
RETURN r.id AS id,
       r.relation_type AS rt,
       r.valid_from AS vf,
       r.valid_to AS vt,
       coalesce(a.canonical_name, a.id) AS head,
       coalesce(a.entity_type, '') AS head_type,
       coalesce(b.canonical_name, b.id) AS tail,
       coalesce(b.entity_type, '') AS tail_type
"""


def _document_id(stem: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, _DOC_URN.format(stem=stem))


def _load_relations(*, org_id: uuid.UUID, doc_id: uuid.UUID) -> list[dict[str, Any]]:
    key = build_extract_artifact_key(
        org_id=org_id, doc_id=doc_id, filename="relations.json"
    )
    return json.loads(get_storage().get(key, org_id=org_id).decode("utf-8"))


def main() -> int:
    settings = get_settings()
    org_id = settings.default_org_id
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    sealed_total = 0
    relation_total = 0
    try:
        with driver.session(database=settings.neo4j_database) as session:
            for stem in DOC_STEMS:
                doc_id = _document_id(stem)
                try:
                    relations = _load_relations(org_id=org_id, doc_id=doc_id)
                except Exception as exc:  # noqa: BLE001 - 缺产物必须显式可见
                    print(f"\n### {stem}\n  [FAIL] 读不到抽取产物：{exc}")
                    sealed_total += 1  # 计入失败，避免"没产物"被当成"没问题"
                    continue

                ids = [str(item.get("id")) for item in relations if item.get("id")]
                print(f"\n### {stem}（产物关系 {len(ids)} 条）")
                rows = list(
                    session.run(
                        _CYPHER_BY_IDS, ids=ids, kg_version=KG_VERSION
                    )
                )
                on_graph = len({str(row["id"]) for row in rows})
                sealed = [row for row in rows if row["vt"]]
                with_from = [row for row in rows if row["vf"]]
                print(f"  已入图 {on_graph}/{len(ids)} 条；带 valid_from {len(with_from)} 条；"
                      f"**带 valid_to {len(sealed)} 条**")
                for row in sealed[:8]:
                    print(
                        f"    [{row['rt']}] {row['vf']} → {row['vt']}  "
                        f"{row['head_type']}:{str(row['head'])[:20]} → "
                        f"{row['tail_type']}:{str(row['tail'])[:20]}"
                    )
                sealed_total += len(sealed)
                relation_total += len(ids)

        ratio = sealed_total / relation_total if relation_total else 0.0
        print(
            f"\n  两文档新代合计：关系 {relation_total} 条，valid_to 非空 {sealed_total} 条"
            f"（{ratio:.1%}）"
        )
        # **分档而不是"有就行"**：条款 mention 只有「第X条」三字 ⇒ 模型即使抽到失效日期，
        # 也很可能只把它记成"某条关于有效期的关系"（正是第一代的形态：1 条 / 26 条）。
        # 只有**大部分条款边**带上 valid_to，L2-②③ 才有对象可演示 ⇒ 判据必须落到比例上。
        if ratio >= 0.5:
            verdict = "✅ 同段明写有效期后，模型**按条**产出 valid_to —— A 路线成立，可推进 ②③"
            code = 0
        elif ratio > 0:
            verdict = (
                "⚠️ 仍只有个别关系带 valid_to ⇒ **未按条产出**；"
                "说明失效日期没被绑到各条款关系上，A 路线不足以支撑 ②③ ⇒ 转 B（口径 / 新 Prompt 版本）"
            )
            code = 1
        else:
            verdict = "❌ 一条都没有 ⇒ 抽取侧完全未产出 valid_to ⇒ 转 B（口径 / 新 Prompt 版本）"
            code = 1
        print(f"  A 路线判定：{verdict}")
        return code
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
