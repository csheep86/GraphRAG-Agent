"""Sprint 7.0 §4 真机对照脚本（**定向切片**，禁止全量重抽整份年报）。

用法（工作目录 = `backend/`）：

```powershell
uv run python ../changes/Sprint7.0/verify_slice.py --engine mock --chunk 1200
uv run python ../changes/Sprint7.0/verify_slice.py --engine llm  --chunk 1200
```

设计说明：

- 走 ``LangextractClient.from_settings()``（与生产同一入口），档位由
  ``--engine`` 注入环境变量——**不打桩、不改代码路径**；
- 切片来源：``docs/annualreport/招商公路：2025年年度报告.pdf`` 前 30 页里的
  「第二节 公司简介和主要财务指标」+「第三节」开头，约 12K 字（10 个 chunk）；
- 每次 LLM 调用的 token 用量由 ``langextract_llm_call`` 日志累计并汇总打印，
  **真实扣费**可核对（预算护栏见 ``tasks.md`` §4）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_SLICE = BACKEND_DIR / "storage" / "demo-slice" / "gonglu_slice.txt"

#: D6① 关注点：法人 / 地址是否被抽出来（值来自 demo-docs-checklist §8 的人工预检）
PROBE_KEYWORDS: tuple[str, ...] = (
    "杨旭东",  # 法定代表人
    "天津自贸试验区",  # 注册地址
    "北京市朝阳区北土城东路",  # 办公地址（公司自身）
    "东方广场",  # ⚠ 会计师事务所地址（伪交叉陷阱）
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sprint 7.0 定向切片抽取对照")
    parser.add_argument("--engine", choices=("mock", "llm"), required=True)
    parser.add_argument("--chunk", type=int, default=1200)
    parser.add_argument("--slice", type=Path, default=DEFAULT_SLICE)
    parser.add_argument("--top", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    # 必须在导入 app.* 之前注入（get_settings 有 lru_cache，且 .env 优先级低于环境变量）
    os.environ["EXTRACTION_ENGINE"] = args.engine
    os.environ["EXTRACTION_MAX_CHARS_PER_CHUNK"] = str(args.chunk)

    from loguru import logger

    from app.services.extraction import LangextractClient

    totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "elapsed_ms": 0}

    def _sink(message) -> None:  # noqa: ANN001 - loguru Message
        record = message.record
        if record["message"] != "langextract_llm_call":
            return
        extra = record["extra"]
        totals["calls"] += 1
        totals["prompt_tokens"] += int(extra.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(extra.get("completion_tokens") or 0)
        totals["elapsed_ms"] += int(extra.get("elapsed_ms") or 0)

    logger.remove()
    logger.add(_sink, level="INFO", format="")
    logger.add(sys.stderr, level="WARNING", format="{level.icon} {message}")

    text = args.slice.read_text(encoding="utf-8")
    print(f"engine={args.engine} slice={args.slice.name} chars={len(text)} "
          f"chunk_size={args.chunk}")

    client = LangextractClient.from_settings()
    started = time.perf_counter()
    result = client.extract_entities_relations(
        document_id=uuid4(), full_md_text=text, trace_id=uuid4()
    )
    elapsed = time.perf_counter() - started

    print(f"chunk_count={len(result.chunks)} entity_count={len(result.entities)} "
          f"relation_count={len(result.relations)} elapsed={elapsed:.1f}s")
    print("type_distribution:", dict(
        Counter(e.entity_type for e in result.entities).most_common()
    ))

    print(f"--- top {args.top} entities (by confidence) ---")
    for entity in sorted(
        result.entities, key=lambda e: e.confidence, reverse=True
    )[: args.top]:
        span_ok = text[entity.char_start : entity.char_end] == entity.mention
        print(f"  {entity.confidence:.2f} {entity.entity_type:<16} "
              f"{entity.canonical_name[:38]:<38} span_ok={span_ok}")

    print("--- D6① probe：法人 / 地址是否出现在抽取产物里 ---")
    haystack = "\n".join(
        f"{e.canonical_name} {e.mention}" for e in result.entities
    )
    for keyword in PROBE_KEYWORDS:
        hit = keyword in haystack
        print(f"  {keyword:<24} hit={hit}")

    print("--- relations (最多 5 条) ---")
    name_by_id = {e.id: e.canonical_name for e in result.entities}
    for relation in result.relations[:5]:
        print(f"  {name_by_id.get(relation.source_entity_id)} "
              f"--{relation.relation_type}--> {name_by_id.get(relation.target_entity_id)} "
              f"({relation.confidence:.2f})")

    if args.engine == "llm":
        print("--- token 用量（真实扣费口径）---")
        print(f"  llm_calls={totals['calls']} "
              f"prompt_tokens={totals['prompt_tokens']} "
              f"completion_tokens={totals['completion_tokens']} "
              f"llm_time={totals['elapsed_ms'] / 1000:.1f}s")
        # deepseek-chat 现价：input ¥2/百万、output ¥8/百万
        cost = (
            totals["prompt_tokens"] * 2 + totals["completion_tokens"] * 8
        ) / 1_000_000
        print(f"  estimated_cost=¥{cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
