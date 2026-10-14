#!/usr/bin/env python
"""**答案稳定性探针**（P7-R §2.1）

**它做什么**：同一批题**连跑 N 次**，逐题比对，回答「两次跑得一样不一样」。
**它不做什么**：**判分** —— A3 铁律：脚本不代判。它不回答「答得对不对」，
只回答「同一份代码同一份数据，答案稳不稳」。

为什么要单独一个脚本，而不是塞进 ``eval_acceptance.py``：

    稳定性是**跨运行**的属性，而既有的 ``eval_acceptance.py`` 是**单次运行**的。
    P7-K 的出口判据 1 恰恰是在跨运行比对上失败的（`--compare` EXITCODE=1，
    图侧 13/40 不同）；当时只能靠手工比对两份报告 ⇒ 不可复跑、容易漏项。
    做成探针 ⇒ 一条命令产出同格式读数 ⇒ 改了东西才知道有没有效。

三个读数（**分开设，不许合并**）：

1. **答案逐字一致率** —— 同一题 N 次的答案原文是否完全相同；
2. **要点覆盖一致率** —— 同一题 N 次覆盖的要点集合是否相同（**这才是判分真正关心的**）；
3. **引用一致率** —— ``citations`` 条数是否相同 ⇒ 用来**定位漂移来自检索还是生成**。

⇒ 三者的落差本身就是结论：若「引用稳、措辞不稳、要点稳」⇒ 需要改的是**判分口径**，
而不是去修检索。

用法::

    uv run python scripts/check_answer_stability.py --repeat 3 \\
        --base-url http://127.0.0.1:8100 --out reports/eval/stability-<ts>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

#: Windows 控制台默认 GBK（cp936）：打印 ``⇒`` 这类非 GBK 字符会抛
#: ``UnicodeEncodeError`` —— 而 CI 跑在 Linux 上**永远不会复现**（纪律 R-9「恒绿即失效」）。
#: 门禁 `tests/test_script_stdio_utf8.py` 要求源码里出现 `reconfigure` + `utf-8`；
#: **刻意内联**而不抽公共模块 —— 本脚本会被测试按文件路径 import，此时 `scripts/`
#: 不在 `sys.path` 上 ⇒ 公共模块本身会 ImportError，兜底反成新的崩溃源。
#: `stderr` 一并兜住：异常 traceback 里带中文时同样会崩。
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.evaluation.dataset import load_multihop_set  # noqa: E402
from app.evaluation.report import git_hash  # noqa: E402
from app.evaluation.runner import RunnerContext, ask_safe  # noqa: E402


def _normalise(text: str) -> str:
    """比对前归一化：**只压空白**。

    **刻意不做**更激进的归一化（去标点 / 数字模糊 / 语义相似）：那会把
    「36 小时 vs 42 小时」这种**真错误**洗成一致 ⇒ 探针当场失去意义。
    """
    return " ".join((text or "").split())


def _point_covered(answer: str, point: str) -> bool:
    """要点是否被答案覆盖（**保守**匹配）。

    两档：① 要点原文出现在答案里；② 退一步，要点里的**数字**出现在答案里
    （如「加班 42h」 ⇒ 42）。

    为什么粗糙的规则也能用：本探针比的是**同一题在 N 次之间覆盖集合是否相同**，
    是相对比较 ⇒ 绝对判定的粗糙度不污染「稳不稳」这个结论。
    """
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


def _classify(first: dict, other: dict) -> str:
    """同一题两次之间，差异属于哪一类（**互斥且覆盖**）。"""
    if first["refused"] != other["refused"]:
        return "c_refusal_flip"
    #: 判据用**序列**（哪个 chunk、什么顺序），不是条数 —— 见 ``_collect`` 里的注记。
    if first.get("citation_ids") != other.get("citation_ids"):
        return "a_evidence_drift"
    if _normalise(first["answer"]) != _normalise(other["answer"]):
        return "b_wording_drift"
    return "identical"


def _collect(ctx: RunnerContext, items) -> dict[int, dict]:
    """跑一遍全集的问答，返回 ``{题号: 记录}``（**不做任何判分**）。"""
    out: dict[int, dict] = {}
    for item in items:
        response, error = ask_safe(item.question, ctx=ctx)
        if response is None:
            out[item.index] = {
                "refused": True,
                "citations": 0,
                "answer": "",
                "error": error,
            }
            continue
        #: 与 ``runner._to_answer`` 同一套字段约定（不 import 私有函数）。
        #: ⚠️ ``citation_ids`` **必须记序列，不能只记条数**：证据"条数相同"≠"证据相同"。
        #: 若 top-k 的**顺序**在跑动中漂移，注入 LLM 的上下文顺序随之变化 ⇒
        #: 答案措辞会变，而条数纹丝不动 ⇒ 只比条数会把"检索漂"误判成"生成漂"。
        out[item.index] = {
            "refused": bool(response.get("refused")),
            "citations": len(response.get("citations") or ()),
            "citation_ids": tuple(
                str(c.get("chunk_id") or "") for c in (response.get("citations") or ())
            ),
            "answer": str(response.get("answer") or ""),
            "error": None,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="答案稳定性探针（只测量、不判分）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 题（0=全部）")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    items = list(load_multihop_set())
    if args.limit > 0:
        items = items[: args.limit]
    ctx = RunnerContext(mode="live", base_url=args.base_url, git_hash=git_hash())

    runs = [_collect(ctx, items) for _ in range(args.repeat)]

    per_item: dict[int, dict] = {}
    for item in items:
        idx = item.index
        texts = [_normalise(run[idx]["answer"]) for run in runs]
        cites = [run[idx]["citations"] for run in runs]
        evidence = [tuple(run[idx].get("citation_ids") or ()) for run in runs]
        refusals = [run[idx]["refused"] for run in runs]
        coverage = [_coverage(run[idx]["answer"], item.expected_points) for run in runs]
        classes = {_classify(runs[0][idx], run[idx]) for run in runs[1:]}
        per_item[idx] = {
            "identical": len(set(texts)) == 1,
            "citations_identical": len(set(cites)) == 1,
            "evidence_identical": len(set(evidence)) == 1,
            "coverage_identical": len(set(coverage)) == 1,
            "refusal_flipped": any(r != refusals[0] for r in refusals),
            "variant_count": len(set(texts)),
            "citations": cites,
            "coverage_per_run": [sum(c) for c in coverage],
            "class": sorted(classes)[0] if classes else "identical",
        }

    n = len(items)
    summary = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repeat": args.repeat,
        "base_url": args.base_url,
        "n_items": n,
        "rate_answer_identical": sum(1 for v in per_item.values() if v["identical"])
        / n,
        "rate_citations_identical": (
            sum(1 for v in per_item.values() if v["citations_identical"]) / n
        ),
        "rate_evidence_identical": (
            sum(1 for v in per_item.values() if v["evidence_identical"]) / n
        ),
        "rate_coverage_identical": (
            sum(1 for v in per_item.values() if v["coverage_identical"]) / n
        ),
        "classification": {
            key: sum(1 for v in per_item.values() if v["class"] == key)
            for key in (
                "identical",
                "a_evidence_drift",
                "b_wording_drift",
                "c_refusal_flip",
            )
        },
        "per_item": per_item,
    }

    print(f"重复次数 N={args.repeat}，题目数 n={n}")
    print(f"  答案逐字一致率 : {summary['rate_answer_identical']:.3f}")
    print(f"  引用条数一致率 : {summary['rate_citations_identical']:.3f}")
    print(f"  证据序列一致率 : {summary['rate_evidence_identical']:.3f}  <- 判据用这个")
    print(f"  要点覆盖一致率 : {summary['rate_coverage_identical']:.3f}")
    print(f"  差异分类       : {summary['classification']}")
    if summary["rate_evidence_identical"] > summary["rate_answer_identical"]:
        print("  -> 证据序列比措辞稳 -> 漂移来自**生成侧**（去改检索是白费劲）")
    elif summary["rate_evidence_identical"] < 1.0:
        print("  -> 证据序列本身在漂移 -> **检索侧就不稳**，先别怪模型")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"读数已落盘: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
