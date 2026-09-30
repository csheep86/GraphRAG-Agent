"""批次 D 收尾 + 批次 A 的 span 端到端：问**刚重建的那份文档**，看引用是否 span 级。

前提（前面实测得来）：active 版本原本 139 个抽取实体**一个 span 都没有**
（S9.5 老数据，属性键里根本没有 ``char_start``）⇒ 端到端引用只能是回退整段
``[0, len)``。用新代码重跑一份 docx 后，带 span 的实体 0 → 31。

于是这里问这份文档（``worktime-system-rules.docx``，工时制制度）的问题，
看 ``citations[].char_offset`` 是否 **> 0**（span 级命中，而非整段回退）。
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

QUESTIONS = (
    "标准工时制的核心在岗时段是怎么规定的？",
    "不定时工作制适用于哪些岗位？",
)


async def main() -> None:
    settings = get_settings()
    for index, question in enumerate(QUESTIONS, start=1):
        try:
            response = await AgentService.instance().query(
                request=AgentQueryRequest(question=question, scope="cross_doc"),
                org_id=settings.default_org_id,
                trace_id=f"e2e-s10-d{index}",
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
            print(f"    snippet={citation.snippet[:70]!r}")


if __name__ == "__main__":
    asyncio.run(main())
