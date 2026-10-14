#!/usr/bin/env python
"""**注入证据观测探针**（P7-S，出口判据 2 + 3）

**它做什么**：把「**本轮注入 Prompt 的 chunk_id 序列**」这条新出口（P7-S 落在
``AgentService._execute_query`` 里的 ``agent_query_injected_evidence`` 日志事件）
按题连跑 N 次、逐题比对 ⇒ 回答 **漂移来自检索侧还是生成侧**。

**它不做什么**：**判分**（A3）——它回答「同一份代码同一份数据，注入的证据和
答案稳不稳」，不回答「答得对不对」。

为什么必须新造这条出口，而不是继续用 ``citations``：

> ``citations`` **不是检索的输出**，而是 LLM ``evidence`` 数组的投影
> （``_build_citations`` 只按模型给的顺序逐条回查）。它回答的是「**模型说它
> 用了什么**」，而不是「**我们注入了什么**」⇒ 拿它当检索侧的读数，
> 「chunk 选择漂」与「LLM 措辞漂」**判不开**（P7-R §6.1 的核心教训）。

本探针抓的事件位于 **LLM 调用之前** ⇒ 不含生成侧非确定性，是检索侧的
**直接读数**。两侧读数一摆，判别就变成机械比较：

| 注入序列 | 答案 | 结论 |
|---|---|---|
| 稳 | 漂 | **生成漂**（同一份证据，模型每次说法不同） |
| 漂 | 稳 | **检索漂**（换了证据，模型反而说得一样） |
| 漂 | 漂 | **两者都漂** |
| 稳 | 稳 | 本轮未观测到漂移 |

用法::

    uv run python scripts/check_injected_evidence.py --repeat 3 --limit 3 \\
        --out reports/eval/injected-<ts>.json

⚠️ 它会**真跑 LLM + Neo4j + PG**（与 HTTP 链路同一条代码路径，只是不经过
网络层）⇒ 会烧 token，不要盲跑大批量。

⚠️ **连的必须是「后端进程所用的那个库」**：本脚本按 ``DATABASE_URL``（或
``backend/.env``）连 PG，而 PG 真源里「哪个版本 ready」决定了检索落在哪一版
chunk 池 ⇒ 连错库会得到**空的注入序列**，读数是假的（P7-R §6.4 就是这么翻车的）。
用之前先确认目标后端实例实际用的是哪个库；连错时本脚本会把 ``missing_exit``
打出来，而不是静默给一个「稳定」的结论。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

#: Windows 控制台默认 GBK（cp936）：打印 ``⇒`` 这类非 GBK 字符会抛
#: ``UnicodeEncodeError`` —— 而 CI 跑在 Linux 上**永远不会复现**（纪律 R-9）。
#: 门禁 `tests/test_script_stdio_utf8.py` 要求源码里出现 `reconfigure` + `utf-8`；
#: **刻意内联**而不抽公共模块 —— 本脚本会被测试按文件路径 import，此时 `scripts/`
#: 不在 `sys.path` 上 ⇒ 公共模块本身会 ImportError，兜底反成新的崩溃源。
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from loguru import logger  # noqa: E402

from app.evaluation.dataset import load_multihop_set  # noqa: E402
from app.evaluation.report import git_hash  # noqa: E402
from app.schemas.agent import AgentQueryRequest  # noqa: E402
from app.services.agents import INJECTED_EVIDENCE_EVENT, AgentService  # noqa: E402

#: 与 `app/evaluation/runner.py` 同口径（live 模式默认打这个租户）。
ORG_ID = UUID("00000000-0000-4000-8000-000000000001")


#: 与 `check_answer_stability.py` 同一套归一化：**只压空白**，不做语义模糊。
def _normalise(text: str) -> str:
    return " ".join((text or "").split())


def _point_covered(answer: str, point: str) -> bool:
    """要点是否被答案覆盖（保守匹配：原文命中，或要点里的数字命中）。"""
    haystack = _normalise(answer)
    needle = (point or "").strip()
    if not needle:
        return False
    if needle in haystack:
        return True
    digits = ["".join(ch for ch in tok if ch.isdigit()) for tok in needle.split()]
    return any(d and d in haystack for d in digits)


def _coverage(answer: str, points: tuple[str, ...]) -> tuple[bool, ...]:
    return tuple(_point_covered(answer, p) for p in points)


def _short(ids: tuple[str, ...] | None) -> str:
    """chunk_id 序列的短显示（去掉 ``chunk-`` 前缀，取前 12 位）。"""
    if ids is None:
        return "<无出口读数>"
    if not ids:
        return "[]"
    return "[" + ", ".join(str(cid).replace("chunk-", "")[:12] for cid in ids) + "]"


def _collect(items: list[Any], *, org_id: UUID, run_index: int) -> dict[int, dict]:
    """跑一遍题集，返回 ``{题号: 记录}`` —— 抓的是**注入序列**这条新出口。

    为什么走**进程内直调**而不是 HTTP：出口是日志事件，落在**服务端进程**里
    ⇒ 走 HTTP 的探针只能看到响应体，看不到它。直调 ``AgentService.query``
    与路由层走的是**同一个函数**（路由只是转发），故路径等价。

    ⚠️ 必须传 **PG 会话**（``session_scope``）：``fetch_active_kg_version`` 在
    ``db`` 非空时以 PG ``kg_versions`` 为真源；不传会走 Neo4j 兜底 ⇒ 可能落到
    **另一个版本**上（P7-R §6.4 复现失败正是踩了这个）。
    """
    from app.db.session import session_scope

    records: list[Any] = []
    handler_id = logger.add(lambda m: records.append(m.record), level="INFO", format="")
    out: dict[int, dict] = {}
    try:
        for item in items:
            trace_id = str(uuid5(NAMESPACE_URL, f"p7s-r{run_index}-q{item.index}"))
            try:
                with session_scope(org_id=org_id) as db:
                    response = asyncio.run(
                        AgentService.instance().query(
                            request=AgentQueryRequest(
                                question=item.question, scope="cross_doc"
                            ),
                            org_id=org_id,
                            trace_id=trace_id,
                            db=db,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - 探针必须跑完并给出结论
                out[item.index] = {
                    "error": repr(exc),
                    "injected": None,
                    "citations": (),
                    "answer": "",
                    "refused": True,
                    "kg_version": None,
                }
                continue

            injected: tuple[str, ...] | None = None
            for record in records:
                extra = record["extra"]
                if (
                    record["message"] == INJECTED_EVIDENCE_EVENT
                    and str(extra.get("trace_id")) == trace_id
                ):
                    injected = tuple(str(cid) for cid in extra["chunk_ids"])
            out[item.index] = {
                "error": None,
                "injected": injected,
                "citations": tuple(c.chunk_id for c in response.citations),
                "answer": str(response.answer or ""),
                "refused": bool(response.refused),
                "kg_version": str(response.kg_version),
            }
    finally:
        logger.remove(handler_id)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="注入证据观测探针（抓 LLM 之前的 chunk_id 序列；只测量、不判分）"
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--limit", type=int, default=3, help="只取前 N 题（0=全部）")
    parser.add_argument(
        "--org-id", default=str(ORG_ID), help="租户 id（默认同 runner live 口径）"
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    org_id = UUID(str(args.org_id))
    items = list(load_multihop_set())
    if args.limit > 0:
        items = items[: args.limit]

    runs = [_collect(items, org_id=org_id, run_index=i) for i in range(args.repeat)]

    #: 出口缺失**必须**显式报出来：静默当空序列会让结论看起来像"检索稳定"。
    missing = [
        index
        for index in (item.index for item in items)
        if any(run[index]["injected"] is None for run in runs)
    ]

    per_item: dict[int, dict] = {}
    for item in items:
        index = item.index
        injected = [run[index]["injected"] for run in runs]
        texts = [_normalise(run[index]["answer"]) for run in runs]
        cites = [tuple(run[index]["citations"]) for run in runs]
        coverage = [
            _coverage(run[index]["answer"], item.expected_points) for run in runs
        ]
        per_item[index] = {
            "injected_identical": len(set(injected)) == 1,
            "answer_identical": len(set(texts)) == 1,
            "citations_identical": len(set(cites)) == 1,
            "coverage_identical": len(set(coverage)) == 1,
            "kg_versions": sorted({str(run[index]["kg_version"]) for run in runs}),
            "injected_per_run": [list(x) if x is not None else None for x in injected],
            "citations_per_run": [list(x) for x in cites],
            "errors": [run[index]["error"] for run in runs],
        }

    n = len(items)
    retrieval = sum(1 for v in per_item.values() if not v["injected_identical"])
    generation = sum(1 for v in per_item.values() if not v["answer_identical"])
    summary = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repeat": args.repeat,
        "org_id": str(org_id),
        "git_hash": git_hash(),
        "n_items": n,
        "rate_injected_identical": sum(
            1 for v in per_item.values() if v["injected_identical"]
        )
        / n,
        "rate_answer_identical": sum(
            1 for v in per_item.values() if v["answer_identical"]
        )
        / n,
        "rate_citations_identical": sum(
            1 for v in per_item.values() if v["citations_identical"]
        )
        / n,
        "rate_coverage_identical": sum(
            1 for v in per_item.values() if v["coverage_identical"]
        )
        / n,
        "drift_counts": {"retrieval": retrieval, "generation": generation},
        "verdict": _verdict(retrieval, generation),
        "missing_exit": missing,
        "per_item": per_item,
    }

    print(f"重复次数 N={args.repeat}，题目数 n={n}，git={summary['git_hash']}")
    print(f"  注入序列一致率 : {summary['rate_injected_identical']:.3f}  <- 检索侧读数")
    print(f"  答案逐字一致率 : {summary['rate_answer_identical']:.3f}  <- 生成侧读数")
    print(f"  引用序列一致率 : {summary['rate_citations_identical']:.3f}")
    print(f"  要点覆盖一致率 : {summary['rate_coverage_identical']:.3f}")
    print(f"  漂移题数       : 检索 {retrieval} / 生成 {generation}")
    for item in items:
        row = per_item[item.index]
        print(f"  #{item.index} kg={','.join(row['kg_versions'])}")
        print(
            "      注入: "
            + " | ".join(
                _short(tuple(x) if x is not None else None)
                for x in row["injected_per_run"]
            )
        )
        print(
            "      引用: "
            + " | ".join(_short(tuple(x)) for x in row["citations_per_run"])
        )
    print(f"  结论           : {summary['verdict']}")
    if missing:
        print(f"  ⚠️ 出口缺失题号 : {missing} ⇒ 这些题的检索侧结论**不可采信**")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"读数已落盘: {out_path}")
    return 0


def _verdict(retrieval: int, generation: int) -> str:
    """三选一（**机械比较**，不掺判断）。

    检索侧 = 注入序列在 N 次之间是否相同；生成侧 = 答案逐字是否相同。
    两者都按「题」计数：只要有一题漂，该侧就算漂（不做加权、不做阈值）。
    """
    if retrieval and generation:
        return "两者都漂"
    if retrieval:
        return "检索漂"
    if generation:
        return "生成漂"
    return "本轮未观测到漂移"


if __name__ == "__main__":
    raise SystemExit(main())
