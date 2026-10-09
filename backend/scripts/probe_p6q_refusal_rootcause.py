"""**P6-Q 拒答误伤根因探针**（¥0、只读、**不退化为分段打印一堆数字**）。

为什么要有它
------------
`dev-doc-status.md` **A6** 把「拒答误伤」立为独立判据，当前读数 **FAIL（1 条 Q8）**。
要修它，**第一步不是改代码，是量化**（quantify before fix）：一条提问被拒答，
可能卡在互不相同的好几层，而在哪一层决定了该怎么修：

| 层 | 卡住的含义 | 该怎么修（本坞机械结论，不是猜测） |
|---|---|---|
| **L1** 目标 chunk 不在 `kg_version` 内 | 题集与语料不同源（v1→v2→v3 已踩两次） | 换题集，不是改检索 |
| **L2** 在图候选里捞不到（500 采样实体 → `MENTIONS`） | 候选集是**结构性窗口**（R22 已登记） | 属规模缺陷，先登记，别顺手改采样 |
| **L3** 图候选 + 字面量召回也没覆盖 | 字面量召回没生效（P6-N 的 N-D1 并集） | 查 `LexicalIndex` 与 `_LEXICAL_CANDIDATE_LIMIT` |
| **L4** 在候选里，但没进最终 **32 条** | 选片规则（`select_evidence_chunks`）把它切掉了 | 动选片规则（P6-J 词面重排那一层） |
| **L5** 进了 32 条，仍被拒答 | LLM 归因闸门（`qa_citation_gate`）丢引用 | 需 live，本探针到此为止并如实报告 |

本探针只负责 **L1~L4**（¥0、离线、可复跑）；**L5 必须 live** —— 本脚本不会假装量它。

**gold 是机械确定的，不许手工标注**
----------------------------------
`gold(keys) = 版本内 text 同时含全部 key 子串的那些 chunk`。
理由是 D1 的硬要求：**先验是对的才算真误伤**（问句问的东西语料里根本没有 ⇒
拒答是正确的，是题集标注错 —— 那是①/③，不是②）。
默认 key 由题集 `expected_points` 机械推导（取纯 CJK 且 ≥4 字的 token）；
推导不出 ⇒ **显式报错**，不许退化成"跳过这一题"（跳过 = 假绿）。

为什么不自己拼 Cypher
--------------------
三处单选 degradation 都为假第二真源：

- 图候选走**生产那条** `_QUERY_EVIDENCE_CHUNK_INDEX`；
- 字面量候选走**生产那个**进程内索引（`fetch_evidence_chunks` 内部同一份缓存）；
- 选片走**生产那个** `select_evidence_chunks`（含 P6-J 词面重排）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/probe_p6q_refusal_rootcause.py --index 8
    uv run python scripts/probe_p6q_refusal_rootcause.py --index 8 --key 核心在岗时段
    uv run python scripts/probe_p6q_refusal_rootcause.py --all

退出码恒为 **0**：它是**报告**不是门禁；连不上 Neo4j 会直接抛错（**不**打印一串 0）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.evaluation.dataset import load_question_set  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _EVIDENCE_CHUNK_LIMIT,
    _EVIDENCE_CHUNK_SNIPPET_CHARS,
    _LEXICAL_CANDIDATE_LIMIT,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
    _lexical_overlap,
)

#: 演示库默认租户（与既有探针 / 评测脚本一致）
ORG_ID = "00000000-0000-4000-8000-000000000001"

#: 最终注入条数 = 线上口径 (**不放**大：全文进 Prompt)
FINAL_LIMIT = _EVIDENCE_CHUNK_LIMIT

#: 纯 CJK（含常用标点除外的汉字），用于从 ``expected_points`` 机械取 key
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{4,}")


class ProbeError(RuntimeError):
    """探针自身无法定 gold ⇒ **显式抛**，不许静默跳过（跳过 = 假绿）。"""


def mechanical_keys(expected_points: tuple[str, ...]) -> tuple[str, ...]:
    """从题集的 ``expected_points`` **机械**取 key（纯 CJK 且 ≥4 字的连续串）。

    ⇒ 只认词条里那段中文主题词，不认时间 / 数字 / 半角写法
    （「核心在岗时段 10:00 至 16:00」⇒ ``('核心在岗时段',)``）。
    """
    keys: list[str] = []
    for point in expected_points:
        keys.extend(_CJK_RUN.findall(point))
    if not keys:
        raise ProbeError(
            f"无法从 expected_points={expected_points!r} 机械推出 key（需 ≥4 字纯中文串）"
            "⇒ 请显式传 --key；探针不许跳过这一题（跳过 = 假绿）"
        )
    return tuple(keys)


def find_gold(
    driver: Any,
    *,
    kg_version: str,
    org: str,
    keys: tuple[str, ...],
) -> list[tuple[str, str]]:
    """**L1**：版本内同时命中全部 key 的 chunk ⇒ gold（机械确定）。"""
    query = """
MATCH (c:Chunk {kg_version: $kg_version})
WHERE $org_id IS NULL OR c.org_id IS NULL OR c.org_id = $org_id
WITH c WHERE all(k IN $keys WHERE c.text CONTAINS k)
RETURN c.id AS chunk_id, c.text AS text ORDER BY chunk_id
"""
    with driver.session() as session:
        rows = list(
            session.run(query, kg_version=kg_version, org_id=org, keys=list(keys))
        )
    return [(str(r["chunk_id"]), str(r["text"])) for r in rows]


def index_rows(
    driver: Any,
    *,
    kg_version: str,
    org: str,
    entity_ids: list[str],
) -> tuple[list[tuple[str, str | None, int, int, int]], dict[str, str]]:
    """**生产那条**索引 Cypher（与 `fetch_evidence_chunks` 逐字同源）。"""
    with driver.session() as session:
        raw = list(
            session.run(
                _QUERY_EVIDENCE_CHUNK_INDEX,
                kg_version=kg_version,
                org_id=org,
                entity_ids=entity_ids,
                index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
                snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
            )
        )
    rows = [
        (
            str(r["chunk_id"]),
            str(r["doc_id"]) if r["doc_id"] else None,
            int(r["mentions"] or 0),
            int(r["spans"] or 0),
            int(r["char_start"] or 0),
        )
        for r in raw
    ]
    snippets = {str(r["chunk_id"]): str(r["snippet"] or "") for r in raw}
    return rows, snippets


def bucket_rank(
    *,
    rows: list[tuple[str, str | None, int, int, int]],
    snippets: dict[str, str],
    question: str,
    target: str,
    gold_text: str,
) -> tuple[int, int, int, float]:
    """gold 在**自己那个文档桶**里的排位（P6-J §5 同一把尺子）。

    :returns: ``(名次, 桶大小, 保底名额, gold 词面分)``；gold 不在候选 ⇒ 名次 = -1。
    """
    target_doc = next((d for cid, d, *_ in rows if cid == target), None)
    if target_doc is None:
        return (-1, 0, 0, 0.0)
    group = [r for r in rows if r[1] == target_doc]
    score = _lexical_overlap(question, gold_text)

    def key(item: tuple[str, str | None, int, int, int]) -> tuple[float, int, int, str]:
        s = _lexical_overlap(question, snippets.get(item[0]) or "")
        return (-s, -item[2], item[4], item[0])

    ordered = sorted(group, key=key)
    rank = next(
        (i + 1 for i, item in enumerate(ordered) if item[0] == target),
        -1,
    )
    return (rank, len(group), FINAL_LIMIT // 15, score)


def probe_one(
    *,
    graph: GraphService,
    driver: Any,
    question: str,
    kg_version: str,
    org: str,
    keys: tuple[str, ...],
    label: str,
) -> dict[str, Any]:
    """对**一题**逐层量化 L1 → L4，返回机械读数。"""
    gold = find_gold(driver, kg_version=kg_version, org=org, keys=keys)

    if not gold:
        return {"label": label, "layer": "L1", "gold_count": 0}

    gold_ids = {cid for cid, _ in gold}
    target_id, target_text = gold[0]

    # ① 生产子图（500 采样）→ 实体 → 锚点（含锚点直查兜底）
    nodes, _edges, _truncated = graph.fetch_all_subgraph(
        kg_version=kg_version, org_id=UUID(org), node_limit=_GRAPH_NODE_LIMIT
    )
    sampled = [n.id for n in nodes if n.label == "Entity"]
    anchors = graph.fetch_anchor_entity_ids(
        kg_version=kg_version, org_id=UUID(org), question=question, nodes=nodes
    )
    entity_ids = list(dict.fromkeys([*anchors, *sampled]))

    # ② 生产索引 Cypher ⇒ 图候选（**L2**）
    rows, snippets = index_rows(
        driver, kg_version=kg_version, org=org, entity_ids=entity_ids
    )
    graph_ids = {r[0] for r in rows}

    # ③ 生产字面量索引（进程内同一份缓存）⇒ 合并候选（**L3**）
    lexical_index = graph._lexical_index_for(  # noqa: SLF001 - 诊断脚本需同源索引
        kg_version=kg_version, org_param=org
    )
    lexical_hits = lexical_index.search(question, _LEXICAL_CANDIDATE_LIMIT)
    merged_ids = graph_ids | set(lexical_hits)

    # ④ 生产最终注入 32 条（**L4**）
    injected = graph.fetch_evidence_chunks(
        kg_version=kg_version,
        org_id=UUID(org),
        entity_ids=entity_ids,
        limit=FINAL_LIMIT,
        question=question,
    )
    injected_ids = [c.chunk_id for c in injected]

    rank, bucket_size, floor, score = bucket_rank(
        rows=rows,
        snippets=snippets,
        question=question,
        target=target_id,
        gold_text=target_text,
    )

    if not graph_ids & gold_ids:
        layer = "L2"
    elif not merged_ids & gold_ids:
        layer = "L3"
    elif not (set(injected_ids) & gold_ids):
        layer = "L4"
    else:
        layer = "L5+"

    return {
        "label": label,
        "layer": layer,
        "question": question,
        "keys": keys,
        "gold_count": len(gold),
        "target_id": target_id,
        "candidate_rows": len(rows),
        "anchors": len(anchors),
        "lexical_hits": len(lexical_hits),
        "in_graph_candidate": bool(graph_ids & gold_ids),
        "in_merged_candidate": bool(merged_ids & gold_ids),
        "in_injected": bool(set(injected_ids) & gold_ids),
        "injected_count": len(injected_ids),
        "bucket_rank": rank,
        "bucket_size": bucket_size,
        "bucket_floor": floor,
        "lexical_score": score,
    }


def render(result: dict[str, Any]) -> str:
    """逐层读数（**不塞 Materials**：只打印能支撑判据的机械量）。"""
    if result["layer"] == "L1":
        return (
            f"{result['label']}  **L1 卡住**：版本内没有同时命中 keys 的 chunk"
            " ⇒ 题集与语料**不同源**（按 A6 / D1 判为① 或 ③：应换题集，不是改检索）"
        )
    lines = [
        f"{result['label']}  {result['question']}",
        f"  keys(机械)        : {' & '.join(result['keys'])}",
        f"  gold chunk        : {result['gold_count']} 条（目标 {result['target_id']}）",
        f"  L2 图候选         : {'命中' if result['in_graph_candidate'] else '未命中'}"
        f"（候选行 {result['candidate_rows']} / 锚点 {result['anchors']}）",
        f"  L3 合并字面量候选  : {'命中' if result['in_merged_candidate'] else '未命中'}"
        f"（字面量 {result['lexical_hits']} 条）",
        f"  L4 最终注入        : {'命中' if result['in_injected'] else '未命中'}"
        f"（注入 {result['injected_count']} 条）",
        f"  文档桶排位        : 第 {result['bucket_rank']} / {result['bucket_size']} 名"
        f"（保底 {result['bucket_floor']} 条，词面分 {result['lexical_score']:.3f}）",
        f"  ⇒ **卡在 {result['layer']}**",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=int, default=8, help="题号（默认 8 = Q8）")
    parser.add_argument("--all", action="store_true", help="扫全部 40 题")
    parser.add_argument(
        "--key",
        help="显式指定 gold key（逗号分隔；缺省由 expected_points 机械推导）",
    )
    parser.add_argument("--kg-version", default="attendance-demo-v1")
    parser.add_argument("--org-id", default=ORG_ID)
    args = parser.parse_args()

    settings = get_settings()
    questions = {q.index: q for q in load_question_set()}
    targets = tuple(questions) if args.all else (args.index,)

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        graph = GraphService.instance()
        print(
            f"kg_version={args.kg_version}  org_id={args.org_id}  最终注入上限={FINAL_LIMIT}\n"
        )
        for index in targets:
            item = questions.get(index)
            if item is None:
                print(f"Q{index:02d}  题集中不存在")
                continue
            if item.should_refuse:
                print(f"Q{index:02d}  （预期拒答题，不参与误伤归因）")
                continue
            keys = (
                tuple(k.strip() for k in args.key.split(",") if k.strip())
                if args.key
                else mechanical_keys(item.expected_points)
            )
            result = probe_one(
                graph=graph,
                driver=driver,
                question=item.question,
                kg_version=args.kg_version,
                org=args.org_id,
                keys=keys,
                label=f"Q{index:02d}",
            )
            print(render(result))
            print()
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
