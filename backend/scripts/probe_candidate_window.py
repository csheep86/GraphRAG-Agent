"""候选窗口**哨兵诊断**（¥0、只读、可复跑）——量化 R22 里「候选集是结构性窗口」这一半。

为什么要有这个脚本
------------------
``changes/P6-J`` 之后剩下的那条根因是：「目标片段若**不在候选里**，词面重排也救
不回来」。它此前**只是一条推理，不是一次测量**。P6-K 的 ¥0 探针把它量了一遍
（原始输出回帖在 ``changes/P6-K/integration-log.md``）：

- 本语料（``attendance-demo-v1``）上 **候选 213 = 版本内 chunk 总数 213**
  ⇒ **当前规模零损失** ⇒ 它是**规模风险**，不是**当前缺陷**；
- 真正的筛选发生在 **213 → 32** 那一层（已由 P6-J 的词面重排处理）。

⇒ 本批**只建哨兵，不建召回**（裁决 D1 = O1）。这个脚本就是那个哨兵的**离线分身**：
生产路径上的留痕只说"这一刻丢了"，它说"这份语料整体上丢了多少"。

输出**只有机械量**（裁决 D2）
----------------------------
1. **窗口完整率** = 候选 / 版本内 chunk 总数（逐题 + 汇总 min / max / 均值）；
2. **撞 ``index_limit`` 的题数**（候选被截断 ⇒ 后面还有没有，本脚本也不知道）；
3. **必然丢失率** = 目标片段不在候选里的题占比 —— 需要 gold 引用标注才出数，
   未给标注时**显式打印 ``N/A``**，**不**给 0（给 0 等于把"没测"写成"没丢"）。

不做的事：**不打 LLM**、**不判分**、**不读上一批的一次性产物**
（旧探针依赖 ``reports/eval/p6j-dryrun.json`` 做自校验，那份是 P6-J 的一次性
判分产物，本脚本已彻底去掉该依赖——要出第 3 项，须显式给 ``--gold-citations``）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/probe_candidate_window.py
    uv run python scripts/probe_candidate_window.py --with-anchor-only
    uv run python scripts/probe_candidate_window.py --gold-citations gold.json

``--gold-citations`` 的 JSON 形态：``{"1": ["chunk-<id>", ...], "2": [...]}``
（题号 ⇒ 该题答案引用到的 chunk_id 列表）。

退出码恒为 **0**：它是**报告**不是门禁（与 ``check_session_drift.py`` 同款定位）；
Neo4j 连不上会直接抛错（**不**打印一串 0 冒充"窗口完整"）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.evaluation.dataset import load_question_set  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _EVIDENCE_CHUNK_SNIPPET_CHARS,
    _QUERY_COUNT_CHUNKS_IN_VERSION,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
)

#: 演示库默认租户（与既有探针 / 评测脚本一致）。
ORG_ID = "00000000-0000-4000-8000-000000000001"


def force_utf8_console() -> None:
    """Windows GBK 控制台会吃掉中文（与 ``import_to_neo4j.py`` 同款处理）。"""
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if stream and enc and enc.lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="候选窗口哨兵诊断（¥0 / 只读 / 只输出机械量）"
    )
    parser.add_argument(
        "--gold-citations",
        type=Path,
        default=None,
        help="题号 => 该题答案引用到的 chunk_id 列表（JSON）；给了才出「必然丢失率」",
    )
    parser.add_argument(
        "--with-anchor-only",
        action="store_true",
        help="额外算「只用问句锚点」那一档（A 口径；O1–O4 已定案，默认不重算）",
    )
    return parser.parse_args()


def load_gold(path: Path | None) -> dict[int, list[str]] | None:
    """读 gold 引用标注；**没给 ⇒ 返回 None**（⇒ 必然丢失率出 ``N/A``，不出 0）。"""
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): [str(c) for c in v] for k, v in payload.items()}


def main() -> None:
    force_utf8_console()
    args = parse_args()
    gold = load_gold(args.gold_citations)

    settings = get_settings()
    graph = GraphService.instance()
    version = graph.fetch_active_kg_version(org_id=UUID(ORG_ID), db=None).version

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    def candidates(entity_ids: list[str]) -> tuple[set[str], bool]:
        """跑生产那条索引 Cypher。返回 (候选 chunk_id 集合, 是否撞上 index_limit)。"""
        with driver.session() as session:
            rows = list(
                session.run(
                    _QUERY_EVIDENCE_CHUNK_INDEX,
                    kg_version=version,
                    org_id=ORG_ID,
                    entity_ids=entity_ids,
                    index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
                    snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
                )
            )
        return {str(r["chunk_id"]) for r in rows}, len(
            rows
        ) >= _EVIDENCE_CHUNK_INDEX_LIMIT

    try:
        with driver.session() as session:
            total_chunks = int(
                session.run(
                    _QUERY_COUNT_CHUNKS_IN_VERSION,
                    kg_version=version,
                    org_id=ORG_ID,
                ).single()["n"]
            )
            all_entity_ids = [
                str(r["id"])
                for r in session.run(
                    "MATCH (e:Entity {kg_version: $v})"
                    " WHERE e.org_id IS NULL OR e.org_id = $org_id"
                    " RETURN e.id AS id",
                    v=version,
                    org_id=ORG_ID,
                )
            ]

        nodes, _edges, _truncated = graph.fetch_all_subgraph(
            kg_version=version, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
        )
        sampled_entities = [n.id for n in nodes if n.label == "Entity"]

        print(f"kg_version                 = {version}")
        print(f"语料 chunk 总数 T          = {total_chunks}")
        print(f"版本内实体总数 N           = {len(all_entity_ids)}")
        print(f"生产子图采样实体数 |S_e|   = {len(sampled_entities)}")
        print(f"索引行上限                 = {_EVIDENCE_CHUNK_INDEX_LIMIT}")
        print()

        cand_u, cap_u = candidates(all_entity_ids)
        print(
            f"[U] 无采样口径（全量 {len(all_entity_ids)} 实体）⇒ 候选 {len(cand_u)} 条"
            f"（窗口完整率 {_pct(len(cand_u), total_chunks)}）"
            f"{'  ⚠️ 撞 index_limit' if cap_u else ''}"
        )
        print()

        header = f"{'题':>4} {'锚点':>4} {'S候选':>6} {'S完整率':>8} {'S截断':>6} {'U候选':>6} {'U完整率':>8}"
        if args.with_anchor_only:
            header += f" {'A候选':>6} {'A完整率':>8}"
        print(header)

        rows: list[tuple[int, int, set[str], bool]] = []
        for item in load_question_set():
            anchors = [
                str(a)
                for a in graph.fetch_anchor_entity_ids(
                    kg_version=version,
                    org_id=UUID(ORG_ID),
                    question=item.question,
                    nodes=nodes,
                )
            ]
            seen = list(dict.fromkeys([*anchors, *sampled_entities]))
            cand_s, cap_s = candidates(seen)
            rows.append((item.index, len(anchors), cand_s, cap_s))

            line = (
                f"{item.index:>4} {len(anchors):>4} {len(cand_s):>6}"
                f" {_pct(len(cand_s), total_chunks):>8} {_flag(cap_s):>6}"
                f" {len(cand_u):>6} {_pct(len(cand_u), total_chunks):>8}"
            )
            if args.with_anchor_only:
                cand_a, _cap_a = candidates(anchors) if anchors else (set(), False)
                line += f" {len(cand_a):>6} {_pct(len(cand_a), total_chunks):>8}"
            print(line)
    finally:
        driver.close()

    print()
    print("=== 汇总（机械量，不含任何人工判分）===")
    rates = [_pct_raw(len(cand), total_chunks) for _i, _a, cand, _c in rows]
    print(
        f"逐题 S 窗口完整率          ：min={min(rates):.2%} "
        f"max={max(rates):.2%} 均值={sum(rates) / len(rates):.2%}"
    )
    hit_cap = sum(1 for _i, _a, _c, cap in rows if cap)
    print(f"撞 index_limit 的题数      ：{hit_cap} / {len(rows)}")
    print(f"逐题候选数去重后的取值集合 ：{sorted({len(c) for _i, _a, c, _c in rows})}")

    if gold is None:
        print(
            "必然丢失率                 ：N/A（未提供 --gold-citations ⇒ "
            "**不**给 0：没测就是没测）"
        )
    else:
        missing = [
            index
            for index, _anchors, cand, _cap in rows
            if sorted(set(gold.get(index, [])) - cand)
        ]
        print(
            f"必然丢失率                 ：{len(missing)} / {len(rows)} "
            f"= {len(missing) / len(rows):.2%}"
            + (f"（题号 {missing}）" if missing else "")
        )


def _pct_raw(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _pct(numerator: int, denominator: int) -> str:
    return f"{_pct_raw(numerator, denominator):.2%}"


def _flag(truncated: bool) -> str:
    return "是" if truncated else "否"


if __name__ == "__main__":
    main()
