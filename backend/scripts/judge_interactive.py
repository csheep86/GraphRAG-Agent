"""**P6-T 交互式判分**（A3：判分只能由人做，脚本只做搬运）。

为什么要有它
------------
A3 写死「脚本不自动判分」，但 86 题要人自己翻 JSON、填 ``true`` / ``false``，
门槛高到会让人放弃 ⇒ 判据永远停在 ``UNKNOWN``。本脚本把门槛降到最低：
**一次显示一题，人只按 y / n**，题号、格式、文件落点全部由脚本负责。

⚠️ **红线**：脚本**不产出任何判分意见**（不提示对错、不做关键词匹配），
只把人按下的键**原样搬运**成判分表。代填 = 假达标（A3 / Non-goal 1）。

用法::

    chcp 65001
    uv run python scripts/judge_interactive.py --judged-by architect

按键：``y`` = true ｜ ``n`` = false ｜ ``s`` = 跳过（这题先不判）｜ ``q`` = 退出。

按 ``q``（或 Ctrl-C）时**进度已落盘**，下次同一条命令接着判，已判的题不再出现。
**86 题全部判完**才写判分表与 gold —— 半张表喂给 ``--judgements`` 会报错
（这是故意的：未判 ≠ 判错）。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SHEETS = BACKEND_DIR / "data/eval/judging/c1-sheets-20261009T064241Z.json"
DEFAULT_MH_REPORT = BACKEND_DIR / "reports/eval/eval-live-20261009T083547Z.json"
DEFAULT_GOLD = BACKEND_DIR / "data/eval/gold-multihop-v1.json"
DEFAULT_PROGRESS = BACKEND_DIR / "data/eval/judging/judge-progress.json"
DEFAULT_GRAPH_OUT = (
    BACKEND_DIR / "data/eval/judging/c1-judge-graph-20261009T075906Z.json"
)
DEFAULT_BASE_OUT = (
    BACKEND_DIR / "data/eval/judging/c1-judge-baseline-20261009T075906Z.json"
)

#: （sheets 里的侧别, 题号前缀, 工作单分节）
SIDES = (("graph", "G", "A"), ("baseline", "B", "B"))
RUBRIC_HINT = (
    "rubric-v2：①拒答与 should_refuse 一致 ②覆盖 core 要点 ③无幻觉"
    " ⇒ 全满足=y，任一不满足=n"
)
PROMPT = "判分 [y/n，s=跳过，q=退出]: "


@dataclass(frozen=True)
class Task:
    """一道待判的题（题干 + 要点 + 答案原文，全部来自已定格的材料）。"""

    key: str  #: G-01 / B-01 / M-01
    side: str  #: graph / baseline / multihop
    index: int
    question: str
    meta: str
    core: list[str]
    secondary: list[str]
    answer: str


def load_tasks(sheets_path: Path, mh_report_path: Path, gold_path: Path) -> list[Task]:
    """从**已定格**的三份材料拼出 86 道题（不重新跑任何 LLM）。"""
    sheets = json.loads(sheets_path.read_text(encoding="utf-8"))
    tasks: list[Task] = []
    for side, tag, _section in SIDES:
        for row in sheets[side]:
            secondary = list(row["secondary_points"])
            core = [p for p in row["expected_points"] if p not in secondary]
            index = int(row["index"])
            tasks.append(
                Task(
                    key=f"{tag}-{index:02d}",
                    side=side,
                    index=index,
                    question=str(row["question"]),
                    meta=(
                        f"should_refuse={row['should_refuse']} ｜ "
                        f"实际 refused={row['refused']} ｜ 引用 {row['citations']}"
                    ),
                    core=core,
                    secondary=secondary,
                    answer=str(row["answer"]),
                )
            )

    report = json.loads(mh_report_path.read_text(encoding="utf-8"))
    criterion = next(
        c for c in report["criteria"] if c.get("criterion") == "multihop_accuracy"
    )
    rows = {
        int(r["index"]): r
        for r in (criterion.get("detail") or {}).get("answer_texts") or []
    }
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    for item in gold["items"]:
        index = int(item["index"])
        row = rows[index]
        tasks.append(
            Task(
                key=f"M-{index:02d}",
                side="multihop",
                index=index,
                question=str(item["question"]),
                meta=(
                    f"跳数={item['hops']} ｜ 跳路径={item['hop_path']} ｜ "
                    f"实际 refused={row['refused']} ｜ 引用 {row['citations']}"
                ),
                core=list(item["expected_points"]),
                secondary=[],
                answer=str(row["answer"]),
            )
        )
    return tasks


def section_of(task: Task) -> str:
    """工作单分节：A=图侧 / B=基线侧 / C=多跳。"""
    return {"graph": "A", "baseline": "B", "multihop": "C"}[task.side]


def show_task(task: Task, *, done: int, total: int, max_chars: int) -> None:
    """打印一题的判分材料（**不加任何对错提示**——那是人该做的事）。"""
    print("=" * 78)
    print(f"[{done + 1}/{total}] {task.key} · {task.side} · 题号 {task.index}")
    print(f"题干：{task.question}")
    print(task.meta)
    print("core 要点（必须覆盖）：")
    for point in task.core:
        print(f"  · {point}")
    if task.secondary:
        print("secondary 要点（缺失不扣分）：")
        for point in task.secondary:
            print(f"  · {point}")
    else:
        print("secondary 要点：无（⇒ 全部要点都是 core）")
    print("答案原文：")
    answer = task.answer
    if max_chars and len(answer) > max_chars:
        answer = answer[:max_chars] + f" …（已截断，完整原文见工作单 {task.key}）"
    print(answer)
    print(RUBRIC_HINT)


def ask() -> bool | None | str:
    """读一次按键；``y``/``n`` ⇒ 判分，``s`` ⇒ 跳过，``q`` ⇒ 退出。"""
    raw = input(PROMPT).strip().lower()
    if raw in {"y", "yes", "true", "t", "1"}:
        return True
    if raw in {"n", "no", "false", "f", "0"}:
        return False
    if raw in {"s", "skip", ""}:
        return None
    if raw in {"q", "quit", "exit"}:
        return "quit"
    print(f"  只认 y / n / s / q（收到：{raw!r}）")
    return "retry"


def load_progress(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def save_progress(path: Path, progress: dict[str, bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_side_table(
    out_path: Path,
    *,
    side: str,
    progress: dict[str, bool],
    prefix: str,
    judged_by: str,
    source: str,
) -> dict[int, bool]:
    """写一张判分表（键 = 题号，值 = **真布尔**；``null`` 会被 CLI 拒绝）。"""
    table: dict[str, Any] = (
        json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    )
    table.setdefault(
        "_rubric",
        "MANIFEST.json rubric-v2：①拒答与 should_refuse 一致；②覆盖 core 要点；"
        "③无与语料矛盾的事实。全满足=true，任一不满足=false。",
    )
    table.setdefault(
        "_rubric_history",
        "P6-T 全新判分（不复用 P6-J 表）：判分对象 = "
        "c1-sheets-20261009T064241Z.json 的两侧 40 条原文（_git_hash=101773e7）。",
    )
    table.setdefault("_dataset", "controlled-qset-v4（40 题）")
    table.setdefault("_source_sheets", source)
    table["_side"] = side
    table["_judged_by"] = judged_by

    values: dict[int, bool] = {}
    for key, value in progress.items():
        if not key.startswith(prefix):
            continue
        index = int(key.split("-")[1])
        values[index] = value
        table[str(index)] = value

    missing = [i for i in range(1, 41) if i not in values]
    if missing:
        raise ValueError(f"{side} 侧缺 {len(missing)} 题未判：{missing[:10]}…")
    out_path.write_text(
        json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return values


def write_outputs(
    *,
    progress: dict[str, bool],
    tasks: list[Task],
    judged_by: str,
    graph_out: Path,
    baseline_out: Path,
    gold_path: Path,
    sheets_path: Path,
    gold_out: Path | None = None,
) -> None:
    """86 题齐了才落盘：两张判分表 + 写回 gold 的 correct / judged_by。"""
    graph_values = _write_side_table(
        graph_out,
        side="graph",
        progress=progress,
        prefix="G-",
        judged_by=judged_by,
        source=sheets_path.name,
    )
    baseline_values = _write_side_table(
        baseline_out,
        side="baseline",
        progress=progress,
        prefix="B-",
        judged_by=judged_by,
        source=sheets_path.name,
    )

    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    for item in gold["items"]:
        index = int(item["index"])
        value = progress.get(f"M-{index:02d}")
        if value is None:
            raise ValueError(f"多跳第 {index} 题未判 ⇒ 不写回 gold（半张表宁可不落）")
        item["correct"] = bool(value)
        item["judged_by"] = judged_by
    gold_target = gold_out or gold_path
    gold_target.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def _tally(values: dict[int, bool]) -> str:
        return (
            f"true {sum(values.values())} / false {len(values) - sum(values.values())}"
        )

    print("-" * 78)
    print(f"图侧：{_tally(graph_values)} ⇒ {graph_out}")
    print(f"基线侧：{_tally(baseline_values)} ⇒ {baseline_out}")
    print(f"多跳：写回 {gold_target}")
    print(f"判分人：{judged_by} ｜ 共 {len(tasks)} 题")


def sync_sheet(sheet_path: Path, progress: dict[str, bool]) -> None:
    """把已判的值回填进工作单 md（**只改判分行**，其余一字不动）。"""
    if not sheet_path.exists():
        return
    current = ""
    out: list[str] = []
    for line in sheet_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            current = line[4:].split("（")[0].strip()
        if line.startswith("- **判分**：") and current in progress:
            line = f"- **判分**：{'true' if progress[current] else 'false'}"
        out.append(line)
    sheet_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judged-by", required=True, help="判分人（**禁止匿名**）")
    parser.add_argument("--section", help="只判某一节：A=图侧 / B=基线侧 / C=多跳")
    parser.add_argument("--progress", help=f"进度文件（默认 {DEFAULT_PROGRESS.name}）")
    parser.add_argument("--graph-out", help="图侧判分表落点")
    parser.add_argument("--baseline-out", help="基线侧判分表落点")
    parser.add_argument("--sheet", help="要回填的工作单 md（可选）")
    parser.add_argument("--gold-out", help="gold 落点（**仅测试用**，默认写回真文件）")
    parser.add_argument(
        "--max-chars", type=int, default=1500, help="答案原文显示上限（0 = 不截断）"
    )
    parser.add_argument("--force", action="store_true", help="重判已判过的题")
    args = parser.parse_args()

    sheets_path = DEFAULT_SHEETS
    progress_path = Path(args.progress) if args.progress else DEFAULT_PROGRESS
    all_tasks = load_tasks(sheets_path, DEFAULT_MH_REPORT, DEFAULT_GOLD)
    tasks = (
        [t for t in all_tasks if section_of(t) == args.section.upper()]
        if args.section
        else all_tasks
    )

    progress = load_progress(progress_path)
    if args.force:
        progress = {
            k: v for k, v in progress.items() if k not in {t.key for t in tasks}
        }

    print(f"待判 {len(tasks)} 题 ｜ 已判 {len(progress)} 题 ｜ 判分人 {args.judged_by}")
    print("y=true / n=false / s=跳过 / q=退出并保存进度")
    try:
        for done, task in enumerate(tasks):
            if task.key in progress:
                continue
            show_task(task, done=done, total=len(tasks), max_chars=args.max_chars)
            while True:
                try:
                    answer = ask()
                except EOFError:
                    answer = "quit"
                if answer == "retry":
                    continue
                if answer == "quit":
                    save_progress(progress_path, progress)
                    print(f"\n已保存进度 ⇒ {progress_path}（已判 {len(progress)} 题）")
                    return 0
                if answer is not None:
                    progress[task.key] = bool(answer)
                    save_progress(progress_path, progress)
                break
    except KeyboardInterrupt:
        save_progress(progress_path, progress)
        print(f"\n已保存进度 ⇒ {progress_path}（已判 {len(progress)} 题）")
        return 0

    save_progress(progress_path, progress)
    #: **按全量 86 题**算缺口（只判了一节时，判分表不许落盘）
    pending = [t.key for t in all_tasks if t.key not in progress]
    if pending:
        print(
            f"\n还有 {len(pending)} 题未判：{pending[:12]}{'…' if len(pending) > 12 else ''}"
        )
        print("⇒ 判分表**未生成**（半张表喂给 --judgements 会报错，这是故意的）。")
        print("  再跑一次同一条命令即可接着判。")
        return 0

    write_outputs(
        progress=progress,
        tasks=tasks,
        judged_by=args.judged_by,
        graph_out=Path(args.graph_out) if args.graph_out else DEFAULT_GRAPH_OUT,
        baseline_out=Path(args.baseline_out) if args.baseline_out else DEFAULT_BASE_OUT,
        gold_path=DEFAULT_GOLD,
        sheets_path=sheets_path,
        gold_out=Path(args.gold_out) if args.gold_out else None,
    )
    if args.sheet:
        sync_sheet(Path(args.sheet), progress)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
