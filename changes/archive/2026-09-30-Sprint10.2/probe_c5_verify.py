"""S10 批次 C 残留缺口 —— 改完之后的**真机验收**（走服务层，不复刻逻辑）。

改前（``probe_c3``）：候选 500 实体反查 chunk，注入 20 条里 **CSV 18 / 制度 docx 0 /
带 span 0** ⇒ 问"制度"必然答不到制度。

改后期望（``probe_c4`` 五方案定案）：每文档保底 + 余量 span 优先 ⇒ docx ↑、带 span ↑。

验收两段，都不靠"我觉得"：

1. **服务层** ``fetch_evidence_chunks`` 真机返回：来源分布 / 覆盖文档 / 带 span 条数；
2. **端到端问答**（真实 LLM，2 问，与改前 ``probe_d3`` 同题同参）：看引用是否
   从"回退整段"变成 **span 级**（``char_offset > 0``）。
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.schemas.agent import AgentQueryRequest  # noqa: E402
from app.services.agents import AgentService  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402

VERSION = "attendance-demo-v1"
_CSV_ROW = re.compile(r"^[A-Za-z]{0,3}\d{3,}[,，]")
QUESTIONS = (
    "标准工时制的核心在岗时段是怎么规定的？",
    "不定时工作制适用于哪些岗位？",
)


def _kind(text: str) -> str:
    stripped = (text or "").strip()
    if _CSV_ROW.match(stripped):
        return "CSV"
    if re.search(r"第[一二三四五六七八九十百]+条|制度|规定|办法", stripped):
        return "docx"
    return "other"


def verify_injection() -> None:
    graphs = GraphService.instance()
    nodes, _edges, _t = graphs.fetch_all_subgraph(
        kg_version=VERSION, org_id=None, node_limit=500
    )
    chunks = graphs.fetch_evidence_chunks(
        kg_version=VERSION,
        org_id=None,
        entity_ids=[n.id for n in nodes],
    )
    kinds: dict[str, int] = {}
    for chunk in chunks:
        kind = _kind(chunk.text)
        kinds[kind] = kinds.get(kind, 0) + 1
    docs = len({str(c.doc_id) for c in chunks if c.doc_id is not None})
    with_span = sum(1 for c in chunks if c.entity_spans)
    print(f"注入 {len(chunks)} 条：{kinds}")
    print(f"覆盖文档 {docs} 篇；带 span 的片段 {with_span} 条")
    for index, chunk in enumerate(chunks, start=1):
        head = (chunk.text or "").replace("\n", " ")[:44]
        print(f"  {index:>2}. [{_kind(chunk.text):<5}] span={len(chunk.entity_spans)} | {head}")


async def verify_qa() -> None:
    settings = get_settings()
    for index, question in enumerate(QUESTIONS, start=1):
        try:
            response = await AgentService.instance().query(
                request=AgentQueryRequest(question=question, scope="cross_doc"),
                org_id=settings.default_org_id,
                trace_id=f"e2e-s10-c5-{index}",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"\nQ{index}: {question}\n  [FAIL] {type(exc).__name__}: {exc}")
            continue
        finally:
            AgentService.reset()

        print(f"\nQ{index}: {question}")
        print(f"  refused={response.refused} confidence={response.confidence!r}")
        for citation in response.citations or []:
            hit = "span级" if citation.char_offset > 0 else "回退整段"
            print(
                f"  chunk={citation.chunk_id} "
                f"[{citation.char_offset}, {citation.char_end}) → {hit}"
            )
            print(f"    snippet={citation.snippet[:64]!r}")


def main() -> None:
    print("=== ① 证据注入（服务层真机） ===")
    verify_injection()
    print("\n=== ② 端到端问答（真实 LLM） ===")
    asyncio.run(verify_qa())


if __name__ == "__main__":
    main()
