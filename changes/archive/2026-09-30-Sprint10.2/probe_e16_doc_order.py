"""批次 E 收尾：**组内并列排序键** 离线验证 —— ¥0，不调 LLM。

病根（e15 实测）：CSV 派生文档的 chunk ``MENTIONS`` **大量并列**（employees 表
40 条全是 1）⇒ ``select_evidence_chunks`` 的组内排序 ``(-mentions, chunk_id)``
**退化成 chunk_id 字典序** ⇒ 取前 N 条等于**随机抽样**。

后果：抬全局 floor 的代价由「排名最靠后的那题」决定——Q11 依据组内第 3、
Q12 第 4、Q09「张伟」第 **19** ⇒ 想全捞到得注入 204 条 / 13 万字符（不可行）。

换个角度：**三题依据恰好都是各 CSV 的首行**（LV0001 / SO-2026-0912 / E001）。
若并列时改按**文档原始顺序**（``char_start`` 升序）排，则「每组前 N 条」= 文档
开头 ⇒ 首行必然在场，且 floor 1~2 就够 ⇒ **比现在更省**。

本脚本在**纯函数层面**对比三种组内排序键，扫 limit，输出三题命中与字符代价。
只读取，不写库、不改线上代码——先验证再动刀（项目纪律：先探针后改）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.services.agents import _GRAPH_NODE_LIMIT  # noqa: E402
from app.services.graphs import (  # noqa: E402
    _EVIDENCE_CHUNK_INDEX_LIMIT,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    GraphService,
)

ORG_ID = "00000000-0000-4000-8000-000000000001"
VERSION = "attendance-demo-v1"

#: (题号, 依据关键字) —— 沿用 probe_e6_attribution.EXPECTED 的出处要点，不新造标准。
#: 后来追加 Q08：26 条那轮它反而被误伤（floor=2 ⇒ 13×2=26，**余量归零**，
#: 而它的依据原是靠余量进来的），故一并纳入扫描。
TARGETS = [
    ("Q01", "3 次"),
    ("Q02", "30 分钟"),
    ("Q03", "因公外出"),
    ("Q04", "不得以无门禁记录为由否定出勤"),
    ("Q05", "36 小时"),
    ("Q06", "不认定为加班"),
    ("Q07", "销售经理"),
    ("Q08", "核心在岗时段"),
    ("Q09", "张伟"),
    ("Q10", "综合计算工时制"),
    ("Q11", "LV0001"),
    ("Q12", "SO-2026-0912"),
]
LIMITS = [13, 20, 26, 32, 39, 45, 52, 65]


def select_with(
    rows: list[tuple[str, str | None, int, int, int]],
    limit: int,
    group_key: Callable[[tuple[str, str | None, int, int, int]], tuple],
    filler_key: Callable[[tuple[str, str | None, int, int, int]], tuple],
) -> list[str]:
    """复刻 ``select_evidence_chunks``（保底 + 余量 span 优先），只换排序键。"""
    if limit <= 0 or not rows:
        return []
    buckets: dict[str, list[tuple[str, str | None, int, int, int]]] = {}
    for row in rows:
        if row[1] is None:
            continue
        buckets.setdefault(str(row[1]), []).append(row)
    for group in buckets.values():
        group.sort(key=group_key)

    floor = max(limit // len(buckets), 1) if buckets else limit
    chosen: list[tuple[str, str | None, int, int, int]] = []
    for doc in sorted(buckets):
        chosen.extend(buckets[doc][:floor])
    if len(chosen) > limit:
        chosen.sort(key=group_key)
        return [r[0] for r in chosen[:limit]]
    chosen.sort(key=group_key)
    if len(chosen) < limit:
        taken = {r[0] for r in chosen}
        for row in sorted(
            (r for r in rows if r[0] not in taken),
            key=filler_key,
        ):
            if len(chosen) >= limit:
                break
            chosen.append(row)
            taken.add(row[0])
    return [r[0] for r in chosen]


def main() -> None:
    settings = get_settings()
    service = GraphService.instance()

    nodes, _edges, _tr = service.fetch_all_subgraph(
        kg_version=VERSION, org_id=UUID(ORG_ID), node_limit=_GRAPH_NODE_LIMIT
    )
    entity_ids = [n.id for n in nodes]

    rows: list[tuple[str, str | None, int, int, int]] = []
    with service._session() as session:  # noqa: SLF001
        for row in session.run(
            _QUERY_EVIDENCE_CHUNK_INDEX,
            kg_version=VERSION,
            org_id=ORG_ID,
            entity_ids=entity_ids,
            index_limit=_EVIDENCE_CHUNK_INDEX_LIMIT,
        ):
            rows.append(
                (
                    str(row["chunk_id"]),
                    str(row["doc_id"]) if row["doc_id"] else None,
                    int(row["mentions"] or 0),
                    int(row["spans"] or 0),
                    0,  # char_start 下一步补
                )
            )

    meta: dict[str, tuple[int, str]] = {}
    with service._session() as session:  # noqa: SLF001
        for row in session.run(
            "MATCH (c:Chunk {kg_version:$v}) "
            "RETURN c.id AS id, coalesce(c.char_start, 0) AS s, c.text AS t",
            v=VERSION,
        ):
            meta[str(row["id"])] = (int(row["s"] or 0), str(row["t"] or ""))

    rows = [
        (cid, doc, m, sp, meta.get(cid, (0, ""))[0]) for cid, doc, m, sp, _ in rows
    ]

    schemes: list[tuple[str, Callable, Callable]] = [
        (
            "现状 (-mentions, chunk_id)",
            lambda r: (-r[2], r[0]),
            lambda r: (0 if r[3] > 0 else 1, -r[2], r[0]),
        ),
        (
            "文档序 (-mentions, char_start)",
            lambda r: (-r[2], r[4], r[0]),
            lambda r: (0 if r[3] > 0 else 1, -r[2], r[4], r[0]),
        ),
        (
            "文档序+span (-mentions,-spans,char_start)",
            lambda r: (-r[2], -r[3], r[4], r[0]),
            lambda r: (0 if r[3] > 0 else 1, -r[2], r[4], r[0]),
        ),
    ]

    for name, gkey, fkey in schemes:
        print(f"\n=== {name} ===")
        for limit in LIMITS:
            picked = select_with(rows, limit, gkey, fkey)
            chars = sum(len(meta.get(cid, (0, ""))[1]) for cid in picked)
            missed = [
                label
                for label, kw in TARGETS
                if not any(kw in meta.get(cid, (0, ""))[1] for cid in picked)
            ]
            covered = len(TARGETS) - len(missed)
            mark = "   ← 12 题依据全覆盖" if not missed else ""
            print(
                f"  limit={limit:<3} 注入={len(picked):<4} 字符={chars:<7} "
                f"覆盖={covered}/{len(TARGETS)} 缺={','.join(missed) or '-'}{mark}"
            )


if __name__ == "__main__":
    main()
