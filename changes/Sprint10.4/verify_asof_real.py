"""Sprint 10.4 批次 A：**真机验文案**（真实 LLM，¥）。

验什么：``documents.document_date`` 全为 NULL 的组织提问时，答案里

- **不得**出现占位符字面量 ``unknown``（v4 的病：…依据截至 unknown 的披露文件…）；
- **不得**出现任何 as-of / 截至 日期短语；
- 必须仍带 ``[source: <chunk_id>]`` 引用（省掉日期 ≠ 省掉依据）。

用法：``cd backend && uv run python ../changes/Sprint10.4/verify_asof_real.py``
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from app.core.config import get_settings  # noqa: E402
from app.schemas.agent import AgentQueryRequest  # noqa: E402
from app.services.agents import AgentService  # noqa: E402

QUESTION = "张伟 2026-10-16 缺卡该怎么处理？"
#: 任一命中都算文案泄漏
LEAK_PATTERNS = (
    r"unknown",
    r"unknown",
    r"N/A",
    r"截至",
    r"as of",
    r"\{\{",
)
SOURCE_PATTERN = r"\[source: [^\]]+\]"


async def run() -> int:
    settings = get_settings()
    request = AgentQueryRequest(question=QUESTION, scope="cross_doc")
    response = await AgentService.instance().query(
        request=request,
        org_id=settings.default_org_id,
        trace_id="sprint104-asof-verify",
    )

    answer = response.answer or ""
    print(f"=== 问句 ===\n{QUESTION}")
    print(f"=== 答案（refused={response.refused}） ===\n{answer}")
    print(f"=== 推理路径 {len(response.reasoning_path or [])} 跳 ===")

    leaks = [p for p in LEAK_PATTERNS if re.search(p, answer, flags=re.IGNORECASE)]
    print(f"=== 泄漏检查 ===\n  命中 {leaks or '无'}")
    print(f"=== 引用检查 ===\n  引用数 {len(re.findall(SOURCE_PATTERN, answer))}")

    if response.refused:
        print("[SKIP] 本次拒答，文案检查不适用（换问句重跑）")
        return 0
    if leaks:
        print("[FAIL] 答案里仍有占位符 / as-of 文案")
        return 1
    if not re.search(SOURCE_PATTERN, answer):
        print("[FAIL] 答案没有任何 [source: ...] 引用")
        return 1
    print("[OK ] 无日期 ⇒ 无 as-of 整句，引用仍在")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
