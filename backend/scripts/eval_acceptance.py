"""**M6 出口判据评测入口**（DR-D10 / TBD-7 的承载脚本）。

用法::

    uv run python scripts/eval_acceptance.py                    # offline（默认，CI 可跑、断网可跑）
    uv run python scripts/eval_acceptance.py --live             # 打真实链路（需后端已起）
    uv run python scripts/eval_acceptance.py --live --criteria c2_c_citation_coverage
    uv run python scripts/eval_acceptance.py --live --judgements data/eval/judgements.json
    uv run python scripts/eval_acceptance.py --compare A.json B.json
    uv run python scripts/eval_acceptance.py --calibrate --cost-records path.json

**三条纪律（不要改掉）**：

1. ``--offline`` **不产出判据数字**。断网跑出来的"召回 0.8"必然是假的；
   offline 只验证管道（数据集 / 指标 / 报告 / 幂等），依赖真机的判据如实标
   ``UNKNOWN`` / ``BLOCKED``。口径演练走报告里的 ``self_test``（标 ``synthetic: true``）。
2. ``BLOCKED`` / ``UNKNOWN`` 的 ``value`` **恒为 null**，**不是 0**
   （0 会被读成"召回为 0"，误触发反证 F2）。
3. ``--calibrate`` **只输出建议值，绝不改 config / .env**
   （禁止脚本自己把阈值调松——阈值必须由人裁决）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from app.evaluation.metrics import (  # noqa: E402
    DocumentCostRecord,
    dedupe_document_costs,
)
from app.evaluation.report import (  # noqa: E402
    build_report,
    compare,
    git_hash,
    render,
    write_report,
)
from app.evaluation.runner import (  # noqa: E402
    ALL_CRITERIA,
    RunnerContext,
    run,
    self_test,
    upgrade_todo,
)

#: 报告默认落点：`backend/reports/eval/`（**已被 .gitignore 忽略** ⇒ 运行产物不入库）
DEFAULT_OUT_DIR = BACKEND_DIR / "reports" / "eval"


def _default_out(mode: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_OUT_DIR / f"eval-{mode}-{stamp}.json"


def _load_judgements(path: Path) -> dict[int, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): bool(v) for k, v in payload.items()}


def _percentile(values: list[int], pct: float) -> float:
    """线性插值分位（**不引入 numpy**：脚本要能裸跑）。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _calibrate(cost_records: Path | None) -> int:
    """TBD-7 校准：**只输出建议值**（RK-E7：绝不改 config / .env）。"""
    print("== TBD-7 校准（只输出建议，不改任何配置） ==")
    if cost_records is None:
        print(
            "无 --cost-records ⇒ **无法校准**。\n"
            "原因：真实成本数据要等 P5-M6 落 cost_metrics 表（token 目前只进日志、未落库）。\n"
            "⇒ TBD-7 维持 provisional（默认 eval_single_doc_token_ceiling = 32 000，见 config.py 注释）。"
        )
        return 0

    payload = json.loads(cost_records.read_text(encoding="utf-8"))
    records = tuple(
        DocumentCostRecord(
            doc_id=str(item["doc_id"]),
            token_usage_total=int(item["token_usage_total"]),
            outcome=str(item.get("outcome", "completed")),
            sequence=int(item.get("sequence", 0)),
        )
        for item in payload
    )
    per_doc = dedupe_document_costs(records)
    values = list(per_doc.values())
    p50, p90 = _percentile(values, 0.5), _percentile(values, 0.9)
    suggested = int(round(p90 * 1.2 / 100.0)) * 100
    print(f"文档数（去重后）      : {len(values)}")
    print(f"P50 / P90（token/文档）: {p50:.0f} / {p90:.0f}")
    print(f"建议 ceiling（P90×1.2）: {suggested}")
    print(
        "\n⚠️ 本命令**不写** config.py / .env；阈值必须由人裁决后手动设置"
        "（eval_single_doc_token_ceiling）。"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        action="store_true",
        help="默认：不依赖 LLM / 网络 / Neo4j（CI 可跑）；**不产出判据数字**",
    )
    mode.add_argument(
        "--live", action="store_true", help="打真实 HTTP 链路（需后端已起）"
    )
    parser.add_argument(
        "--criteria",
        help=f"只跑指定判据（逗号分隔）；可选：{','.join(ALL_CRITERIA)}",
    )
    parser.add_argument("--out", help="报告落点 JSON（默认 backend/reports/eval/）")
    parser.add_argument(
        "--judgements",
        help="人工判分 JSON（{题号: true/false}）——A3：脚本不自动判分",
    )
    parser.add_argument(
        "--judged-by", default="architect", help="判分人（写入 provenance）"
    )
    parser.add_argument(
        "--base-url",
        help=f"live 模式的后端地址（默认 {RunnerContext(mode='live', git_hash='x').base_url}）",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("A", "B"),
        help="比对两份报告（忽略 generated_at）；有差异 ⇒ 退出码 1",
    )
    parser.add_argument(
        "--calibrate", action="store_true", help="TBD-7 校准：只输出建议值"
    )
    parser.add_argument("--cost-records", help="--calibrate 用的文档成本打点 JSON")
    args = parser.parse_args()

    if args.compare:
        left = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        right = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        diffs = compare(left, right)
        if not diffs:
            print("[OK] 两份报告一致（除 generated_at）⇒ 幂等通过")
            return 0
        print(f"[DIFF] {len(diffs)} 处差异（除 generated_at）：")
        for line in diffs:
            print(f"  {line}")
        return 1

    if args.calibrate:
        return _calibrate(Path(args.cost_records) if args.cost_records else None)

    run_mode = "live" if args.live else "offline"
    criteria = (
        tuple(c.strip() for c in args.criteria.split(","))
        if args.criteria
        else ALL_CRITERIA
    )
    ctx = RunnerContext(
        mode=run_mode,  # type: ignore[arg-type]
        git_hash=git_hash(),
        base_url=args.base_url or RunnerContext(mode=run_mode, git_hash="x").base_url,
        judgements=_load_judgements(Path(args.judgements)) if args.judgements else None,
        judged_by=args.judged_by,
    )

    results = run(ctx, criteria=criteria)
    report = build_report(
        ctx=ctx,
        results=results,
        self_test_block=self_test(),
        upgrade_todo=upgrade_todo(),
    )
    out = Path(args.out) if args.out else _default_out(run_mode)
    write_report(report, out)

    print(render(report))
    print(f"\n报告已落盘: {out}")

    #: 退出码：**有 FAIL 才非 0**。BLOCKED / UNKNOWN **不算失败**（它们不是"没达标"，
    #: 是"没测出来"——把它当失败会逼人用假数据凑绿）。
    failed = [r.criterion for r in results if r.verdict and r.verdict.value == "FAIL"]
    if failed:
        print(f"\n[FAIL] 未达标判据: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
