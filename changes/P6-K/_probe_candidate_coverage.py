"""P6-K 预研探针（**¥0，不打 LLM**，只查 Neo4j + 纯函数）。

回答一个**还没量化的前提**：所谓「候选集是结构性窗口」这条剩余根因，
在**当前语料**上到底漏掉了多少东西？

为什么必须先量它：``changes/P6-J`` 之后图侧已 40/40（C1 到顶），
下一条根因被写作「目标片段若**不在候选里**，重排救不回来」。
但这句话**至今没有任何实测依据** —— 它是一条推理，不是一条测量。
若实际损失为 0 ⇒ 下一步该做的是「换语料验证泛化」，而不是「实现方向②/③」。

三档候选口径逐个量：

- ``S`` 生产口径：``entity_ids = anchors + fetch_all_subgraph(500 采样)``；
- ``A`` 锚点口径：``entity_ids = anchors`` —— 抽掉结构采样，只留问句锚点；
- ``U`` 无采样口径：``entity_ids = 版本内**全部**实体`` —— 教科书式的可达上界。

自校验：40 题图侧答案**引用的 chunk 必须全部落在 S 里**（它们是被选出来才
注入的）⇒ 若这条不成立，说明本探针没复刻生产路径，全部数字作废。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from uuid import UUID

if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
    sys.stdout.reconfigure(encoding="utf-8")

#: 本脚本放在 ``changes/P6-K/`` 下（要随批次归档），而它必须能 import ``app.*``
#: ⇒ 显式把 ``backend/`` 挂上 ``sys.path``（否则得把脚本塞进 backend 里跑）。
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.evaluation.dataset import load_question_set  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _EVIDENCE_CHUNK_SNIPPET_CHARS,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
)

ORG_ID = "00000000-0000-4000-8000-000000000001"
_CITATION = re.compile(r"chunk-[0-9a-f]{12}")

settings = get_settings()
graph = GraphService.instance()
org = UUID(ORG_ID)
version = graph.fetch_active_kg_version(org_id=org, db=None).version

driver = GraphDatabase.driver(
    settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
)

with driver.session() as session:
    total_chunks = session.run(
        "MATCH (c:Chunk {kg_version: $v}) RETURN count(c) AS n", v=version
    ).single()["n"]
    all_entity_ids = [
        r["id"]
        for r in session.run(
            "MATCH (e:Entity {kg_version: $v}) RETURN e.id AS id", v=version
        )
    ]

import json

report_path = Path("reports/eval/p6j-dryrun.json")
if not report_path.exists():
    report_path = _BACKEND / "reports/eval/p6j-dryrun.json"
answers: dict[int, str] = {}
if report_path.exists():
    data = json.loads(report_path.read_text(encoding="utf-8"))
    detail = [c for c in data["criteria"] if c["criterion"] == "c1_graph_gain"][0][
        "detail"
    ]
    answers = {a["index"]: a["answer"] for a in detail["awaiting_graph"]}
else:
    print("⚠️ 找不到 p6j-dryrun.json ⇒ 跳过自校验（S 候选的数仍然有效）")


def candidates(entity_ids: list[str]) -> tuple[set[str], bool]:
    """跑生产那条索引 Cypher。返回 (候选 chunk_id 集合, 是否撞到 1000 上限)。"""
    with driver.session() as session:
        rows = list(
            session.run(
                _QUERY_EVIDENCE_CHUNK_INDEX,
                kg_version=version,
                org_id=str(org),
                entity_ids=entity_ids,
                index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
                snippet_chars=_EVIDENCE_CHUNK_SNIPPET_CHARS,
            )
        )
    return {str(r["chunk_id"]) for r in rows}, len(rows) >= _EVIDENCE_CHUNK_INDEX_LIMIT


nodes, _edges, _truncated = graph.fetch_all_subgraph(
    kg_version=version, org_id=org, node_limit=_GRAPH_NODE_LIMIT
)
sampled_entities = [n.id for n in nodes if n.label == "Entity"]

print(f"kg_version = {version}")
print(f"语料 chunk 总数 T = {total_chunks}")
print(f"版本内实体总数 N = {len(all_entity_ids)}")
print(f"生产子图采样实体数 |S_e| = {len(sampled_entities)}")
print(f"索引行上限 = {_EVIDENCE_CHUNK_INDEX_LIMIT}")
print()

cand_all, cap_all = candidates(all_entity_ids)
print(f"[U] 无采样口径（全量 {len(all_entity_ids)} 实体）⇒ 候选 {len(cand_all)} 条"
      f"（占语料 {len(cand_all) / total_chunks:.0%}）{'  ⚠️ 撞上限' if cap_all else ''}")
print()

print(f"{'题':>4} {'锚点':>4} {'S候选':>6} {'A候选':>6} {'引用全在S':>9}")
missing_rows = []
for item in load_question_set():
    anchors = list(
        graph.fetch_anchor_entity_ids(
            kg_version=version,
            org_id=org,
            question=item.question,
            nodes=nodes,
        )
    )
    seen = dict.fromkeys([*anchors, *sampled_entities])
    cand_s, cap_s = candidates(list(seen))
    cand_a, _ = candidates(anchors) if anchors else (set(), False)

    cited = set(_CITATION.findall(answers.get(item.index, "")))
    outside = sorted(cited - cand_s)
    ok = "✅" if not outside else f"❌ {len(outside)}"

    print(
        f"{item.index:>4} {len(anchors):>4} {len(cand_s):>6} {len(cand_a):>6} {ok:>9}"
    )
    if outside:
        missing_rows.append((item.index, outside))

driver.close()

print()
print("=== 自校验 ===")
if missing_rows:
    print(f"❌ {len(missing_rows)} 题的答案引用不在 S 候选里 ⇒ 探针未复刻生产路径，数字作废：")
    for idx, ids in missing_rows[:10]:
        print(f"   Q{idx}: {ids}")
else:
    print("✅ 40 题答案引用的 chunk 全部落在 S 候选内（探针口径与生产一致）")
