"""S10 批次 B 前置探针：多跳的**域覆盖**真机现状（只读）。

已确认（读代码）：`reasoning.py:135` 的多跳 Cypher 是 `-[:RELATION*1..3]-`，
`_MAX_HOPS=3`，与 PRD「3 跳内」一致；且 `agents.py:396` 已把它接进
`AgentQueryResponse.reasoning_path`（契约已有）⇒ **多跳本身不是缺口**。

本探针回答剩下那个问题：**它在通用域（合同 / 年报抽取的实体）能用吗？**

`_CYPHER_PATHS` 的终点被 `b.entity_type IN $terminal_types` 卡住，而
`TERMINAL_ENTITY_TYPES` 取自**考勤本体**（POLICY_CLAUSE / ATTENDANCE_RECORD / …）。
若通用域文档里没有这些类型 ⇒ 链**必然取不到**（`reasoning_path` 空），
多跳就只在考勤域成立——而 PRD 黄金路径步骤 1 是**合同 PDF**。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.graphs import GraphService  # noqa: E402
from app.services.reasoning import TERMINAL_ENTITY_TYPES  # noqa: E402


def main() -> None:
    graphs = GraphService.instance()
    terminal = set(TERMINAL_ENTITY_TYPES)

    with graphs._session() as session:  # noqa: SLF001
        rows = list(
            session.run(
                "MATCH (e:Entity) "
                "RETURN e.entity_type AS t, e.kg_version AS v, count(*) AS n "
                "ORDER BY n DESC"
            )
        )

    print("== 全图 :Entity 的 (类型, 版本) 分布 ==")
    per_version: dict[str, dict[str, int]] = {}
    for row in rows:
        version = str(row["v"])
        bucket = per_version.setdefault(version, {})
        bucket[str(row["t"])] = bucket.get(str(row["t"]), 0) + int(row["n"])

    for version, types in per_version.items():
        covered = sorted(set(types) & terminal)
        missing = sorted(set(types) - terminal)
        print(f"\n[{version}] 类型 {len(types)} 种 / 实体 {sum(types.values())} 个")
        print(f"  命中多跳终点类型的: {covered or '（无）'}")
        print(f"  **不在**终点类型里的: {missing}")
        # 控制台是 GBK，`⇒` 会 UnicodeEncodeError（真机踩到），故用 ASCII 箭头
        verdict = "可用" if covered else "必然取不到链（空）"
        print(f"  -> 该版本下多跳: {verdict}")

    print(f"\n多跳终点类型白名单（考勤本体）: {sorted(terminal)}")


if __name__ == "__main__":
    main()
