"""P6-V1 判据 1：两侧排序键的**逐维比对**（机器输出，可复跑）。

它读的是**生产本身**，不另写一份判断：

- Python 侧维名 ← :data:`app.services.reasoning.PATH_SORT_DIMENSIONS`
- Cypher 侧 ``ORDER BY`` ← 从 :func:`app.services.reasoning._cypher_paths` 的
  返回字符串里**解析**出来（不是背下来的）

.. warning::
   本探针**不做**候选构成统计。P6-U 的教训（`13-as-of-evidence-rank.md` §「本次
   踩到的坑」）：任何"候选构成"类探针必须复用生产谓词本身，自己重写一遍过滤
   条件 ⇒ 必然误报。本探针只比对**排序键**，且键来自生产字符串 ⇒ 不重犯。

跑法（backend 目录）：

    uv run python ../../changes/P6-V1/probe_sort_key_alignment.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.reasoning import (  # noqa: E402
    DB_ORDER_BY_DIMENSIONS,
    PATH_SORT_DIMENSIONS,
    _cypher_paths,
)

#: 每个 Python 维"值从哪来"（**登记**，与 `_select_shortest_path` 的 sort key 同序）
_DIM_SOURCE = {
    "terminal_priority": "0 if terminal == TERMINAL_PRIORITY_TYPE else 1（只认 POLICY_CLAUSE）",
    "terminal_rank": "_TERMINAL_RANK.get(terminal, len(_TERMINAL_RANK))（8 档）",
    "hops": "len(rels)",
    "temporal_verdict": "_TEMPORAL_RANK[verdict]（consistent/unknown/inconsistent）",
    "as_of_evidence": "_AS_OF_EVIDENCE_RANK[_last_hop_as_of_evidence(row, as_of)]",
    "path_ids": "tuple(ids)（**整链** id 元组）",
    "position": "原始位次",
}

#: 该维在 Cypher 侧对应的片段（``None`` ⇒ DB 侧**不做**这一维）
_DIM_CYPHER = {
    "terminal_priority": "$prio_type",  # 与下一维合并成同一个 CASE 表达式
    "terminal_rank": "$terminal_rank",
    "hops": "size(rels)",
    "temporal_verdict": None,
    "as_of_evidence": None,
    "path_ids": "ids[-1]",  # 粗化：只看终点
    "position": None,
}

_ORDER_BY_RE = re.compile(r"ORDER BY\s+(.*?)\s*\n?LIMIT", re.DOTALL)


def _db_order_by_terms() -> list[str]:
    """从**生产的** Cypher 里解析出 ORDER BY 的每一维。"""
    match = _ORDER_BY_RE.search(_cypher_paths())
    if match is None:
        raise SystemExit("Cypher 里没有 ORDER BY ⇒ 截断就是随机抽样")
    return [term.strip() for term in re.split(r",\s*\n\s*", match.group(1).strip())]


def main() -> int:
    # ⚠️ Windows 控制台是 GBK ⇒ 输出一律 ASCII 标记（✔ / ✘ / ⇒ 会 UnicodeEncodeError）
    terms = _db_order_by_terms()
    print("=" * 78)
    print("P6-V1 判据 1：两侧排序键逐维比对")
    print("=" * 78)

    print("\n--- Cypher 侧 ORDER BY（从 _cypher_paths() 解析，共 %d 项） ---" % len(terms))
    for index, term in enumerate(terms, start=1):
        print(f"  {index}. {' '.join(term.split())}")

    print("\n--- 逐维比对 ---")
    print(f"{'维':<3} {'Python 侧':<18} {'DB 侧':<12} {'结论'}")
    print("-" * 78)
    for index, dim in enumerate(PATH_SORT_DIMENSIONS, start=1):
        hint = _DIM_CYPHER[dim]
        if hint is None:
            db_side, verdict = "--", "DB 侧不做（残留风险，见 proposal 第 6 节）"
        elif any(hint in term for term in terms):
            db_side, verdict = hint, "一致" if dim != "path_ids" else "粒度不同（粗化）"
        else:
            db_side, verdict = "--", "!! 缺失"
        flag = "[DB]" if dim in DB_ORDER_BY_DIMENSIONS else "[  ]"
        print(f"{index:<3} {dim:<18} {db_side:<12} {verdict}  {flag}")

    print("\n--- 前缀性质（判据：DB 侧必须是**连续**前缀，跳维比不做更糟） ---")
    expected = PATH_SORT_DIMENSIONS[: len(DB_ORDER_BY_DIMENSIONS)]
    print(f"  DB_ORDER_BY_DIMENSIONS = {DB_ORDER_BY_DIMENSIONS}")
    print(f"  PATH_SORT_DIMENSIONS[:{len(DB_ORDER_BY_DIMENSIONS)}] = {expected}")
    ok = DB_ORDER_BY_DIMENSIONS == expected
    print(f"  -> {'[OK] 连续前缀成立' if ok else '[FAIL] 跳维 => 截断会丢真胜者'}")

    gap = [dim for dim in PATH_SORT_DIMENSIONS[len(DB_ORDER_BY_DIMENSIONS) :]]
    print(f"\n  DB 侧未覆盖的维：{gap}")
    print("  -> 当这些维之前的维**全打平**且候选 > LIMIT 时，真胜者仍可能被截；")
    print("     此刻丢的是「同档内次优」，不改变答案的解释力层级（proposal 第 6 节）。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
