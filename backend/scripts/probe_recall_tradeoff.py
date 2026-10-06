"""召回方向 **¥0 比选探针**（只读、可复跑、只出机械量）——把 R22 的三个候选方向放在同一把尺子上量。

为什么要有这个脚本
------------------
``docs/dev-doc-status.md`` R22 原文给召回定了三条纪律，其中一条是硬前置：

    候选方向（**开工前先做 ¥0 探针比选，勿凭猜测定案**）：
    ① 字面量召回（BM25 / 关键词倒排）② 实体链接召回 ③ 向量召回

即：**不许因为"①最便宜"就去做①** —— 便宜不等于赢，赢面要用数说话。
本脚本就是那把尺子：把三档候选构造方式放到**同一组查询、同一条选片规则**上，
量“目标片段到底能不能进最终 32 条”。

为什么现在才做得起：``changes/P6-L`` 之前没有可证伪的场地 ——
本语料（213 chunk）上候选 **100%** 完整，任何召回改动都量不出 diff（这正是
P6-K 否决 O3 的理由）。P6-L 在 ``affiliation-demo-v2``（988 chunk）上实测
**生产采样口径只有 35.93%** ⇒ 第一次有了"会丢"的场地。

查询集是**机械构造**的，不是人工出题
------------------------------------
``affiliation-demo-v2`` 的实体带结构化属性（``trade_ref`` / ``counterparty_name``），
而同样的键也写在 chunk 文本里 ⇒ **gold 由语料机械确定**：

    gold(key) = 文本 CONTAINS key 的那几条 chunk

**零判分**：没有一个数字需要人来判断"这个答案对不对"（D2 的要求）。

三档候选（唯一变量 = 候选从哪来）
--------------------------------
| 档 | 候选怎么来 |
|---|---|
| **B 现状** | 500 采样实体 → ``MENTIONS`` → chunk（P6-L 实测 355 条），**与问句无关** |
| **① 字面量** | ``c.text CONTAINS $key`` ⇒ chunk |
| **② 实体链接** | ``Entity.<attr> = $key`` → ``MENTIONS`` → chunk（**全图匹配，不受 500 采样限制**） |
| **P 生产（P6-N 落地后）** | 真调 :meth:`fetch_evidence_chunks` 并**传 ``question``** ⇒ 图候选 **∪** 字面量候选，再由 P6-J 的词面重排选 32 条 |

前三档是**比选**（P6-M）；``P`` 档是**落地后的端到端验收**（P6-N）—— 它走的是
真实生产函数，不是探针自己拼的 Cypher ⇒ 唯一可信的"改完了真有用"读数。

三档随后过**同一条**选片规则 :func:`select_evidence_chunks`（含 P6-J 的词面重排，
``question`` / ``snippets`` 都给）⇒ 比的确实只是"候选从哪来"。

③向量召回**不跑**：需嵌入模型 + 向量库 ⇒ 引入依赖 + ¥，与既有 Non-goals 第 4 条
冲突；本脚本只在结尾打印它的触发条件。

⚠️ **适用范围（M-D5，输出里会原样打印）**：本探针测的是**键级 / 名称级查询**
（问句里含明确单号或主体名）。字面量召回在这类查询上是**最有利场景**，
故结论**不**自动推广到开放性提问（如 P6-J 的 Q20 / Q22 / Q26 纯概念题）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/probe_recall_tradeoff.py \
        --kg-version affiliation-demo-v2 \
        --org-id 5dea8f62-0c67-579a-9509-8b4ce98eadea

退出码恒为 **0**：它是**报告**不是门禁；连不上 Neo4j 会直接抛错（**不**打印一串 0）。
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _EVIDENCE_CHUNK_SNIPPET_CHARS,
    _LEXICAL_CANDIDATE_LIMIT,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
    select_evidence_chunks,
)

#: 演示库默认租户（与既有探针 / 评测脚本一致）
ORG_ID = "00000000-0000-4000-8000-000000000001"

#: 机械查询集：**(名字, 实体属性名, 取多少个键)**。
#: 属性必须同时存在于实体与 chunk 文本，gold 才能机械确定。
QUERY_SETS = (
    ("trade_ref 键级", "trade_ref", 100),
    ("counterparty_name 名称级", "counterparty_name", 20),
)

#: 取最终注入条数（= 生产 ``_EVIDENCE_CHUNK_LIMIT``）
FINAL_LIMIT = 32

_QUERY_KEYS = """
MATCH (e:Entity {kg_version: $v})
WHERE ($org IS NULL OR e.org_id IS NULL OR e.org_id = $org)
  AND e[$attr] IS NOT NULL
RETURN DISTINCT e[$attr] AS k
LIMIT $n
"""

_QUERY_GOLD_CHUNKS = """
MATCH (c:Chunk {kg_version: $v})
WHERE ($org IS NULL OR c.org_id IS NULL OR c.org_id = $org)
  AND c.text CONTAINS $key
RETURN c.id AS id
"""

_QUERY_TEXT_HIT_CHUNKS = """
MATCH (c:Chunk {kg_version: $v})
WHERE ($org IS NULL OR c.org_id IS NULL OR c.org_id = $org)
  AND c.text CONTAINS $key
RETURN c.id AS id
LIMIT $cap
"""

_QUERY_ENTITY_LINK_CHUNKS = """
MATCH (e:Entity {kg_version: $v})
WHERE ($org IS NULL OR e.org_id IS NULL OR e.org_id = $org)
  AND e[$attr] = $key
MATCH (c:Chunk {kg_version: $v})-[:MENTIONS]->(e)
WHERE $org IS NULL OR c.org_id IS NULL OR c.org_id = $org
RETURN DISTINCT c.id AS id
LIMIT $cap
"""

#: 由 chunk_id 集合反查选片所需的**同款列**（与生产索引 Cypher 一致 ⇒ 可比）
_QUERY_ROWS_BY_IDS = """
MATCH (c:Chunk {kg_version: $v})
WHERE c.id IN $ids
  AND ($org IS NULL OR c.org_id IS NULL OR c.org_id = $org)
OPTIONAL MATCH (d:Document {kg_version: $v})-[:HAS_CHUNK]->(c)
RETURN
  c.id AS chunk_id,
  d.id AS doc_id,
  size([(c)-[:MENTIONS]->(:Entity {kg_version: $v}) | 1]) AS mentions,
  size([(c)-[:MENTIONS]->(e2:Entity {kg_version: $v})
        WHERE e2.char_start IS NOT NULL | 1]) AS spans,
  coalesce(c.char_start, 0) AS char_start,
  substring(coalesce(c.text, ''), 0, $snippet_chars) AS snippet
"""

_QUERY_TEXT_LEN = """
MATCH (c:Chunk {kg_version: $v})
WHERE c.id IN $ids
RETURN sum(size(coalesce(c.text, ''))) AS chars
"""


def force_utf8_console() -> None:
    """Windows GBK 控制台会吃掉中文（与 ``import_to_neo4j.py`` 同款处理）。"""
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if stream and enc and enc.lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="召回方向 ¥0 比选探针（只读 / 只出机械量 / 零判分）"
    )
    parser.add_argument(
        "--kg-version",
        default=None,
        help="要诊断的 kg_version；不给 ⇒ 取 --org-id 的 active 版本",
    )
    parser.add_argument("--org-id", default=ORG_ID, help=f"租户 id（默认 {ORG_ID}）")
    return parser.parse_args()


def _pct(num: int, den: int) -> str:
    return f"{num / den:.2%}" if den else "N/A"


def main() -> None:
    force_utf8_console()
    args = parse_args()
    org = args.org_id

    settings = get_settings()
    graph = GraphService.instance()
    if args.kg_version:
        version = args.kg_version
    else:
        version = graph.fetch_active_kg_version(org_id=UUID(org), db=None).version

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    def rows_of(chunk_ids: list[str]) -> tuple[list[tuple], dict[str, str]]:
        """按生产同款列取回候选行（+ 词面重排要用的 snippet）。"""
        if not chunk_ids:
            return [], {}
        with driver.session() as session:
            recs = list(
                session.run(
                    _QUERY_ROWS_BY_IDS,
                    v=version,
                    org=org,
                    ids=chunk_ids,
                    snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
                )
            )
        rows = [
            (
                str(r["chunk_id"]),
                str(r["doc_id"]) if r["doc_id"] else None,
                int(r["mentions"]),
                int(r["spans"]),
                int(r["char_start"]),
            )
            for r in recs
        ]
        snippets = {str(r["chunk_id"]): str(r["snippet"] or "") for r in recs}
        return rows, snippets

    def selected_of(chunk_ids: list[str], question: str) -> list[str]:
        """过**同一条**生产选片规则（含 P6-J 词面重排）⇒ 最终注入的 32 条。"""
        rows, snippets = rows_of(chunk_ids)
        return select_evidence_chunks(
            rows, FINAL_LIMIT, question=question, snippets=snippets
        )

    def chars_of(chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        with driver.session() as session:
            rec = session.run(_QUERY_TEXT_LEN, v=version, ids=chunk_ids).single()
        return int(rec["chars"] or 0) if rec else 0

    try:
        nodes, _edges, _truncated = graph.fetch_all_subgraph(
            kg_version=version, org_id=UUID(org), node_limit=_GRAPH_NODE_LIMIT
        )
        sampled_entities = [n.id for n in nodes if n.label == "Entity"]
        #: P 档要用生产那个**同一份**索引（进程内缓存）⇒ 与线上口径一致
        _lexical_index = graph._lexical_index_for(  # noqa: SLF001 - 诊断脚本
            kg_version=version, org_param=org
        )

        # 现状基线候选：生产那条索引 Cypher（**与问句无关**，故只算一次）
        with driver.session() as session:
            base_rows = list(
                session.run(
                    _QUERY_EVIDENCE_CHUNK_INDEX,
                    kg_version=version,
                    org_id=org,
                    entity_ids=sampled_entities,
                    index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
                    snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
                )
            )
        baseline_ids = [str(r["chunk_id"]) for r in base_rows]

        print(f"kg_version               = {version}")
        print(f"org_id                   = {org}")
        print(f"生产子图采样实体数 |S_e| = {len(sampled_entities)}")
        print(f"现状基线候选池（与问句无关） = {len(baseline_ids)}")
        print(f"最终注入条数             = {FINAL_LIMIT}")
        print()

        for set_name, attr, n_keys in QUERY_SETS:
            with driver.session() as session:
                keys = [
                    str(r["k"])
                    for r in session.run(
                        _QUERY_KEYS, v=version, org=org, attr=attr, n=n_keys
                    )
                ]
            print("=" * 78)
            print(f"查询集：{set_name}（键由实体属性机械抽取，共 {len(keys)} 个）")
            print("=" * 78)
            if not keys:
                print(
                    "N/A：该版本没有这个实体属性 ⇒ 造不出机械查询集"
                    "（**不**编键、**不**给 0：没测就是没测）\n"
                )
                continue

            stats: dict[str, dict[str, list[float]]] = {
                "B 现状": {"cand": [], "in_cand": [], "in_final": [], "chars": []},
                "① 字面量": {"cand": [], "in_cand": [], "in_final": [], "chars": []},
                "② 实体链接": {"cand": [], "in_cand": [], "in_final": [], "chars": []},
                "P 生产": {"cand": [], "in_cand": [], "in_final": [], "chars": []},
            }

            for key in keys:
                with driver.session() as session:
                    gold = {
                        str(r["id"])
                        for r in session.run(
                            _QUERY_GOLD_CHUNKS, v=version, org=org, key=key
                        )
                    }
                if not gold:
                    continue  # 键没落在任何 chunk 文本里 ⇒ 该键不构成查询

                with driver.session() as session:
                    text_ids = [
                        str(r["id"])
                        for r in session.run(
                            _QUERY_TEXT_HIT_CHUNKS,
                            v=version,
                            org=org,
                            key=key,
                            cap=_EVIDENCE_CHUNK_INDEX_LIMIT,
                        )
                    ]
                    ent_ids = [
                        str(r["id"])
                        for r in session.run(
                            _QUERY_ENTITY_LINK_CHUNKS,
                            v=version,
                            org=org,
                            attr=attr,
                            key=key,
                            cap=_EVIDENCE_CHUNK_INDEX_LIMIT,
                        )
                    ]

                for arm, cand_ids in (
                    ("B 现状", baseline_ids),
                    ("① 字面量", text_ids),
                    ("② 实体链接", ent_ids),
                ):
                    final = selected_of(list(cand_ids), question=key)
                    hit_cand = len(gold & set(cand_ids))
                    hit_final = len(gold & set(final))
                    stats[arm]["cand"].append(len(cand_ids))
                    stats[arm]["in_cand"].append(hit_cand / len(gold))
                    stats[arm]["in_final"].append(hit_final / len(gold))
                    stats[arm]["chars"].append(chars_of(final))

                # **P 生产档**：真调生产函数并传 ``question`` ⇒ 图候选 ∪ 字面量候选。
                # 两个数**分开记**，因为它们卡在不同的层：
                # - ``in_cand`` = gold 是否进了**合并候选**（本批 P6-N 的职责）；
                # - ``in_final`` = gold 是否进了最终 **32 条**（还要过 P6-J 的词面重排，
                #   它对本探针这类**短键查询**区分度为零 ⇒ 见结尾说明）。
                merged_cand = set(baseline_ids) | set(
                    _lexical_index.search(key, _LEXICAL_CANDIDATE_LIMIT)
                )
                prod = graph.fetch_evidence_chunks(
                    kg_version=version,
                    org_id=UUID(org),
                    entity_ids=sampled_entities,
                    limit=FINAL_LIMIT,
                    question=key,
                )
                prod_ids = [c.chunk_id for c in prod]
                stats["P 生产"]["cand"].append(len(merged_cand))
                stats["P 生产"]["in_cand"].append(len(gold & merged_cand) / len(gold))
                stats["P 生产"]["in_final"].append(
                    len(gold & set(prod_ids)) / len(gold)
                )
                stats["P 生产"]["chars"].append(sum(len(c.text) for c in prod))

            n = len(stats["B 现状"]["cand"])
            if n == 0:
                print("N/A：没有任何键的 gold 落在 chunk 文本里 ⇒ 本查询集测不出数\n")
                continue

            print(f"（有效查询 {n} 个 —— gold = 文本含该键的 chunk，机械确定）")
            print()
            print(
                f"{'档':<12}{'候选池中位':>10}{'gold在候选内':>14}"
                f"{'gold进32条':>12}{'字符成本均值':>14}"
            )
            for arm, s in stats.items():
                print(
                    f"{arm:<12}{int(statistics.median(s['cand'])):>10}"
                    f"{sum(s['in_cand']) / n:>14.2%}"
                    f"{sum(s['in_final']) / n:>12.2%}"
                    f"{sum(s['chars']) / n:>14.0f}"
                )
            print()

        print("=" * 78)
        print("⚠️ 适用范围（M-D5）：本探针只测**键级 / 名称级查询**（问句含明确单号")
        print("   或主体名）。字面量召回在此类查询上是**最有利场景** ⇒ 结论**不**自动")
        print("   推广到开放性提问（P6-J 的 Q20 / Q22 / Q26 那类纯概念题另行验证）。")
        print()
        print("③向量召回**未跑**：需嵌入模型 + 向量库 ⇒ 引入第三方依赖 + ¥，与既有")
        print("   Non-goals 第 4 条冲突。触发条件：若上面 ① / ② 的 gold 进 32 条率")
        print("   仍不达标，才另议（须先拍依赖与部署成本）。")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
