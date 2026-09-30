"""S10 批次 A 最后一环：span 级引用为什么没成？——**抓 LLM 原始输出**。

已证：注入的 20 条里有 **3 条带 span**，且问答引用的确实就是这几条
（``chunk-dc60303810f0`` span=9 / ``chunk-332adf0eb6e5`` span=10）。
但 ``char_offset`` 仍是 0 ⇒ ``_resolve_citation_span`` 没匹配上，回退整段。

它的匹配口径**只有一条**（D-C 主档）：证据条目文本与 ``EntitySpan.mention`` **相等**
（忽略大小写与首尾空白）。所以要么：

- LLM 输出的证据条目是 **chunk id**（不是提及文本）⇒ 永远匹配不上 span；
- 或者是提及文本，但与 ``mention`` 不完全相等（多了引号 / 带了 `#提及` 前缀 / 截取不同）。

本探针不改任何源码，只把 LLM 的**原始输出**和该 chunk 的 **span 清单**并排打印，
让两相对照自己说话。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.schemas.agent import AgentQueryRequest  # noqa: E402
from app.services.agents import AgentService  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402

QUESTION = "不定时工作制适用于哪些岗位？"
_CAPTURED: list[str] = []


async def main() -> None:
    original = AgentService._invoke_chat_with_retry  # type: ignore[attr-defined]

    async def spy(  # type: ignore[no-untyped-def]
        self, *, system_prompt: str, question: str, trace_id: str
    ):
        text, usage = await original(
            self, system_prompt=system_prompt, question=question, trace_id=trace_id
        )
        _CAPTURED.append(text)
        return text, usage

    AgentService._invoke_chat_with_retry = spy  # type: ignore[attr-defined]

    settings = get_settings()
    try:
        response = await AgentService.instance().query(
            request=AgentQueryRequest(question=QUESTION, scope="cross_doc"),
            org_id=settings.default_org_id,
            trace_id="e2e-s10-c6",
        )
    finally:
        AgentService.reset()

    print("=== LLM 原始输出 ===")
    print(_CAPTURED[0][:900] if _CAPTURED else "(未捕获)")

    print("\n=== 引用结果 ===")
    for citation in response.citations or []:
        print(
            f"  chunk={citation.chunk_id} [{citation.char_offset}, {citation.char_end})"
        )

    print("\n=== 被引用片段的 span 清单（mention / 偏移） ===")
    graphs = GraphService.instance()
    nodes, _e, _t = graphs.fetch_all_subgraph(
        kg_version="attendance-demo-v1", org_id=None, node_limit=500
    )
    chunks = graphs.fetch_evidence_chunks(
        kg_version="attendance-demo-v1",
        org_id=None,
        entity_ids=[n.id for n in nodes],
    )
    cited = {c.chunk_id for c in response.citations or []}
    for chunk in chunks:
        if chunk.chunk_id in cited:
            print(f"  {chunk.chunk_id}:")
            for span in chunk.entity_spans:
                print(f"    mention={span.mention!r} [{span.char_start}, {span.char_end})")


if __name__ == "__main__":
    asyncio.run(main())
