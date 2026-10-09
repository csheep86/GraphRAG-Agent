"""**导出 C1 两侧答卷**（P6-S）—— 把一份 live 报告变成 P6-T 可直接人工判分的输入物。

为什么要有这个脚本（直接读 ``reports/eval/*.json`` 不行）
--------------------------------------------------------

1. ``reports/eval/`` **被 .gitignore 忽略** ⇒ 打出这张卷子的成本（80 次 LLM 调用）
   随时可能被一次 ``clean`` 抹掉，重建就得**再付一次钱**；
2. 更关键的是 A1 条款 3「**同一批改分**」：若两侧分别各重跑一次，采样 / 检索状态可能不同
   ⇒ 两侧答案不再是同一批产物，增益无从归因。把两侧**同时定格在一个文件**里，
   「两侧同源」才可被事后复核（配合文件里的 ``_graph_spec`` / ``_baseline_spec``）；
3. 报告里只有 ``answer`` 原文，**没有题干与 rubric 锚点**（``expected_points``）⇒
   人拿着它没法照着判（A3：判分由人做，那就得让人能把事情做完）。

⚠️ **它不是判分表**（A3 / Non-goal 2）：产物**不含任何 correct 值**，只有题面与答案原文。
它也不能被 ``--judgements`` 读——顶层键不是纯题号 ⇒ :func:`_load_judgements` 会直接报错，
这是**故意的**：宁可响亮地炸，也不要"把试题当判分表喂进去、判完后发现答対率是假的"。

用法::

    uv run python scripts/export_judging_sheets.py --report reports/eval/eval-live-XXXX.json

产物默认落在 ``data/eval/judging/``（**跟踪入库**，与 gitignore 的 ``reports/eval/`` 分置）。

:raises SystemExit: 报告里没有 c1 判据 / 缺任一侧答卷 / 题集覆盖不到某个 index
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from app.evaluation.dataset import load_manifest, load_question_set  # noqa: E402

DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "eval" / "judging"
CRITERION = "c1_graph_gain"
SHEET_SIDES = ("graph", "baseline")


def pick_criterion(report: dict[str, Any]) -> dict[str, Any]:
    """取出 C1 判据（**只认 c1_graph_gain**：别处的判据数字不该混进判分材料）。"""
    for item in report.get("criteria", ()):
        if item.get("criterion") == CRITERION:
            return item
    raise ValueError(
        f"报告里没有判据 {CRITERION}（现有："
        f"{', '.join(str(i.get('criterion')) for i in report.get('criteria', ()))}）"
    )


def _awaiting(criterion: dict[str, Any], side: str) -> list[dict[str, Any]]:
    """读某一侧的待判答卷；**空卷直接报错**（空卷 ⇒ 判完也不知道分母为什么是 0）。"""
    rows = (criterion.get("detail") or {}).get(f"awaiting_{side}")
    if not rows:
        raise ValueError(
            f"这份报告缺 awaiting_{side}（可得键："
            f"{sorted((criterion.get('detail') or {}).keys())}）⇒ 拿它导不出完整的一侧"
        )
    return rows


def join_questions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把题干与 rubric 锚点合进答卷（index 对不上 ⇒ **报错**，不许静默留空）。"""
    index_to_question = {item.index: item for item in load_question_set()}
    merged: list[dict[str, Any]] = []
    for row in rows:
        index = int(row["index"])
        question = index_to_question.get(index)
        if question is None:
            raise ValueError(
                f"受控题集里没有第 {index} 题 ⇒ 该题无从判分（宁可炸，不许漏题进分母）"
            )
        merged.append(
            {
                "index": index,
                "question": question.question,
                "should_refuse": question.should_refuse,
                "expected_points": list(question.expected_points),
                "secondary_points": list(question.secondary_points),
                "refused": row["refused"],
                "citations": row["citations"],
                "answer": row["answer"],
            }
        )
    return merged


def build_sheets(report_path: Path) -> tuple[dict[str, Any], str]:
    """产出内容 + 建议文件名（文件名带时间戳 ⇒ 两趟答卷**不许**互相覆盖）。"""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    criterion = pick_criterion(report)
    provenance = criterion.get("provenance") or {}
    detail = criterion.get("detail") or {}
    manifest = load_manifest()
    sheet: dict[str, Any] = {
        #: **元信息一律下划线开头**（与判分文件同一约定）：既让它能自解释，
        #: 又保证顶层非元信息键只有 `graph` / `baseline` ⇒ 被当判分表读时会直接报错。
        "_notice": (
            "这是 C1 的**试题 / 答卷**，不是判分表 —— 不含任何 correct 值。"
            "判分请另建文件（键为题号、值为 true/false），并与另一张表分开（A1 条款 3）。"
        ),
        "_source_report": str(report_path),
        "_criterion": CRITERION,
        "_generated_at": datetime.now(UTC).isoformat(),
        "_git_hash": provenance.get("git_hash"),
        "_dataset_version": provenance.get("dataset_version"),
        "_kg_version": provenance.get("kg_version"),
        "_blocked_by": criterion.get("blocked_by"),
        "_rubric": manifest.get("rubric"),
        "_manifest_version": manifest.get("manifest_version"),
        "_graph_spec": detail.get("graph_spec"),
        "_baseline_spec": detail.get("baseline_spec"),
    }
    for side in SHEET_SIDES:
        sheet[side] = join_questions(_awaiting(criterion, side))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return sheet, f"c1-sheets-{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="live 报告 JSON（含 C1 判据）")
    parser.add_argument(
        "--out", help=f"产物路径（默认 {DEFAULT_OUT_DIR}/c1-sheets-<时间戳>.json）"
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[FAIL] 报告不存在：{report_path}")
        return 1
    try:
        sheet, filename = build_sheets(report_path)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1

    out = Path(args.out) if args.out else DEFAULT_OUT_DIR / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[OK] 两侧答卷已落盘: {out}")
    for side in SHEET_SIDES:
        rows = sheet[side]
        print(
            f"  {side}: {len(rows)} 题 / 拒答 "
            f"{sum(1 for row in rows if row['refused'])} 题 / 均含题干与 rubric 锚点"
        )
    print(f"  git_hash={sheet['_git_hash']} kg_version={sheet['_kg_version']}")
    print(
        "  ⚠️ 本文件**不是**判分表（无 correct 值）；"
        "判分请另建两份文件并用 --judgements / --baseline-judgements 传入"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
