"""批次 E：A 方案（服务侧硬闸门）的**离线模拟**——¥0，先算清代价再决定落地。

闸门规则（模拟，与拟落地的判据一致）：
1. 从答案里抽出**实体名**（拿图上该版本的实体名做词典，子串匹配）；
2. 每个被引 chunk 必须"撑得住"答案：chunk 正文含这些实体名，**或**该 chunk 的
   ``MENTIONS`` 命中它们；撑不住 ⇒ 这条引用不可信；
3. 不可信时**先尝试重归因**：在问答真实能看到的 20 条注入里找撑得住的 chunk，
   找到就改挂（保住正确答案）；找不到才判拒答。

为什么必须模拟：归因错的 3 题（Q9/Q11/Q12）**答案内容是对的**，只是挂错了 chunk。
闸门会把它们**变成拒答**——"更安全"的同时也在**牺牲答对率**。这个取舍必须先量化，
不能拍脑袋落地。

注意：模拟用的是上一轮已落盘的答案（模型下一轮可能答得不同）⇒ 结论是**上界估计**，
落地前仍需真实 A/B 复跑。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_LIMIT,
    GraphService,
)
from neo4j import GraphDatabase  # noqa: E402

RESULT_JSON = Path(__file__).resolve().parent / "eval_v3_after_dedup.json"
ORG_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "attendance-demo-v1"
SOURCE_RE = re.compile(r"\[source:\s*([^\]]+)\]")
#: 太短的名字（单字 / 纯数字）当词典会全是噪音
MIN_NAME_LEN = 2
#: 答案里的"硬凭据"：单号 / 工号 / 日期 / 数字（含单位）。
#: 只用实体名当判据会漏——Q12 的「武汉光谷希尔顿酒店」根本不是图上实体，
#: 但它旁边的 ``SO-2026-0912`` 是可以直接比对的凭据。
TOKEN_RE = re.compile(
    r"[A-Za-z]{1,4}-?\d[\w./:-]*"  # SO-2026-0912 / LV0001 / E001 / 10:00
    r"|\d+(?:\.\d+)?\s*(?:小时|天|次|分钟|%)"  # 36 小时 / 3 次 / 30 分钟
)


def _answer_fragments(answer: str, names: set[str]) -> set[str]:
    """答案里可机械比对的凭据：实体名 + 单号/数字。

    只取**能逐字比对**的东西；句子措辞与原文不同属正常，不拿整句做包含判断
    （那会把"换个说法"误判成"撑不住"）。
    """
    cleaned = SOURCE_RE.sub("", answer)
    fragments = {name for name in names if name in cleaned}
    fragments |= {m.group(0).strip() for m in TOKEN_RE.finditer(cleaned)}
    return {f for f in fragments if len(f) >= MIN_NAME_LEN}


def main() -> None:
    settings = get_settings()
    results = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
    service = GraphService.instance()
    nodes, _edges, _ = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    injected = service.fetch_evidence_chunks(
        kg_version=VERSION,
        org_id=UUID(ORG_ID),
        entity_ids=[n.id for n in nodes],
        limit=_EVIDENCE_CHUNK_LIMIT,
    )
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    try:
        with driver.session() as session:
            names = [
                row["k"]
                for row in session.run(
                    "MATCH (e:Entity {kg_version:$v}) "
                    "WITH coalesce(e.canonical_name, e.name) AS k "
                    "WHERE k IS NOT NULL AND size(k) >= $n RETURN DISTINCT k",
                    v=VERSION,
                    n=MIN_NAME_LEN,
                ).data()
            ]
            mentioned: dict[str, set[str]] = {}
            for chunk in injected:
                mentioned[str(chunk.chunk_id)] = {
                    row["k"]
                    for row in session.run(
                        "MATCH (c:Chunk {id:$id})-[:MENTIONS]->(e:Entity) "
                        "RETURN coalesce(e.canonical_name, e.name) AS k",
                        id=str(chunk.chunk_id),
                    ).data()
                    if row["k"]
                }
            texts = {str(c.chunk_id): (c.text or "") for c in injected}
    finally:
        driver.close()

    def supports(chunk_id: str, fragments: set[str]) -> bool:
        if chunk_id not in texts:
            return False
        body = texts[chunk_id]
        return bool(fragments & mentioned.get(chunk_id, set())) or any(
            fragment in body for fragment in fragments
        )

    kept = reattributed = refused = 0
    for item in results:
        if item["refused"]:
            continue
        answer = str(item.get("answer") or "")
        cited = {m.strip() for m in SOURCE_RE.findall(answer)}
        fragments = _answer_fragments(answer, set(names))
        if not fragments:
            kept += 1
            print(f"  [Q{item['index']:02d}] 保留（答案里没有可机械比对的凭据 ⇒ 不动，避免误杀）")
            continue
        trusted = {cid for cid in cited if supports(cid, fragments)}
        if trusted:
            kept += 1
            print(f"  [Q{item['index']:02d}] 保留（{len(trusted)}/{len(cited)} 条引用撑得住）")
            continue
        # 不可信 ⇒ 先试重归因
        alt = [cid for cid in texts if supports(cid, fragments)]
        if alt:
            reattributed += 1
            print(
                f"  [Q{item['index']:02d}] **改挂**：原引用撑不住，注入里有 {len(alt)} 条撑得住"
            )
        else:
            refused += 1
            print(
                f"  [Q{item['index']:02d}] **判拒答**：注入 20 条里没有任何一条含 "
                f"{sorted(fragments)[:4]} ⇒ 这是召回问题，不是归因问题"
            )

    total = kept + reattributed + refused
    print(f"\n模拟结果（非拒答题 {total}）: 保留 {kept} / 改挂 {reattributed} / 判拒答 {refused}")
    print(
        "读法：判拒答的题 = 答案对但**依据压根没进注入** ⇒ 闸门只是把「错引」变成「拒答」，\n"
        "      根治要靠召回（C），闸门（A）只负责不再给出撑不住的引用。"
    )


if __name__ == "__main__":
    main()
