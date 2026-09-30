"""批次 E：**引用归因**判据——现有评测测不出的那类错。

背景：全量评测（``eval_controlled_qset.py``）的判据是
「非拒答中 ``citations`` 非空且 ``chunk_id`` 均为 ``chunk-`` 前缀」⇒ 实测 100%。
但人读 ``eval_v3_after_dedup.json`` 后发现：有题**答案内容是对的，可它挂的那条
chunk 正文里根本没有答案依据**（例：Q11 答「LV0001 病假」却引用了一条门禁刷卡
记录 chunk；Q12 答「武汉光谷希尔顿酒店」却引用 E024 的工单 chunk）。

这类错**覆盖率判据一个都抓不到**（chunk_id 是真实存在的，前缀也合法），
而它恰恰是 M3「引用可溯源」的核心。故补一个机械判据：

    引用归因命中 = 该题的**期望要点关键词**出现在**任一被引用 chunk 的正文**里

关键词沿用题集里登记的出处要点（与 ``eval_controlled_qset.QUESTIONS`` 注释一致），
不新造标准。本探针**不调 LLM**（读已落盘的评测结果 + 查 chunk 正文），¥0 可复现。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from neo4j import GraphDatabase  # noqa: E402

from app.core.config import get_settings  # noqa: E402

RESULT_JSON = Path(__file__).resolve().parent / "eval_v3_after_dedup.json"

#: 题号 → 期望要点关键词（全部命中才算归因正确；与题集注释同源）
EXPECTED: dict[int, list[str]] = {
    1: ["3 次"],
    2: ["30 分钟", "事假半天"],
    3: ["因公外出"],
    4: ["不得以无门禁记录为由否定出勤"],
    5: ["36 小时"],
    6: ["不认定为加班"],
    7: ["销售经理", "不定时工作制"],
    8: ["10:00 至 16:00"],
    9: ["张伟", "售后部"],
    10: ["综合计算工时制"],
    11: ["LV0001"],
    12: ["SO-2026-0912"],
}


def main() -> None:
    settings = get_settings()
    results = json.loads(RESULT_JSON.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    hit = miss = 0
    try:
        with driver.session() as session:
            for item in results:
                index = item["index"]
                if item["refused"] or index not in EXPECTED:
                    continue
                chunk_ids = [c["chunk_id"] for c in item.get("citations") or []]
                texts = []
                for chunk_id in chunk_ids:
                    row = session.run(
                        "MATCH (c:Chunk {id:$id}) RETURN c.text AS t", id=chunk_id
                    ).single()
                    if row and row["t"]:
                        texts.append(row["t"])
                blob = "\n".join(texts)
                missing = [k for k in EXPECTED[index] if k not in blob]
                if missing:
                    miss += 1
                    print(
                        f"  [Q{index:02d}] 归因✘ 缺 {missing} "
                        f"（引用 {len(chunk_ids)} 条，正文 {len(blob)} 字符）"
                    )
                else:
                    hit += 1
                    print(f"  [Q{index:02d}] 归因✔（要点在被引 chunk 正文里）")
    finally:
        driver.close()

    total = hit + miss
    print(f"\n引用归因命中: {hit}/{total}" + (f" = {hit / total:.0%}" if total else ""))
    print(
        "口径：期望要点关键词是否出现在**被引用 chunk 的正文**里；"
        "与「引用覆盖率 100%」是两件事——后者只验 chunk_id 合法，抓不到归因错"
    )


if __name__ == "__main__":
    main()
