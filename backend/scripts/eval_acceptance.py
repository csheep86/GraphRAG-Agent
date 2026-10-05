"""**M6 出口判据评测入口**（DR-D10 / TBD-7 的承载脚本）。

用法::

    uv run python scripts/eval_acceptance.py                    # offline（默认，CI 可跑、断网可跑）
    uv run python scripts/eval_acceptance.py --live             # 打真实链路（需后端已起）
    uv run python scripts/eval_acceptance.py --live --criteria c2_c_citation_coverage
    uv run python scripts/eval_acceptance.py --live --judgements data/eval/judgements.json
    uv run python scripts/eval_acceptance.py --compare A.json B.json
    uv run python scripts/eval_acceptance.py --calibrate --cost-records path.json

    # **G-25 CI 门禁**（P3-E）：只判「不退化」，不判达标（C2-a / C2-b 只读 Neo4j）
    uv run python scripts/eval_acceptance.py --live \
      --criteria c2_a_hidden_relation_recall,c2_b_false_positive_rate --gate
    # 首次 / 刻意重设刻度时才用（⚠️ 用退化后的值刷基线 = 把门禁调成恒绿）
    uv run python scripts/eval_acceptance.py --live --criteria <同上> --update-baseline

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

from app.evaluation.criteria import (  # noqa: E402
    THRESHOLD_PROVISIONAL,
    CriterionResult,
    judge,
)
from app.evaluation.gate import (  # noqa: E402
    BASELINE_DIR,
    DEFAULT_BASELINE_FILE,
    DEFAULT_TOLERANCE,
    build_baseline,
    evaluate_gate,
    load_baseline,
)
from app.evaluation.metrics import (  # noqa: E402
    DocumentCostRecord,
    dedupe_document_costs,
    single_doc_cost,
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
    resolve_cost_ceiling,
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
    """读人工判分 JSON。

    **判分文件必须能自解释**：判分表决定了 C1 的数字，而一份裸的
    ``{"5": false}`` 三个月后**无人能复核**——不知道用的哪套 rubric、谁判的、
    为什么判错。故允许 **下划线开头**的元信息键（``_rubric`` / ``_judged_by`` /
    ``_note``），它们被跳过不进判分表。

    其余非题号键**照样报错**：那多半是手滑把 rubric 说明写成了普通键，
    或是题号写错 ⇒ 静默放行会让某题"从未被判分"却看不出来。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    table: dict[int, bool] = {}
    for key, value in payload.items():
        if str(key).startswith("_"):
            continue
        try:
            index = int(key)
        except ValueError as exc:
            raise ValueError(
                f"判分文件 {path} 的键必须是题号（元信息键请用下划线开头），收到 {key!r}"
            ) from exc
        table[index] = bool(value)
    return table


def distinct_judgement_tables(graph_path: Path, baseline_path: Path) -> None:
    """**A1 裁决 3 的机器守卫**：两张判分表**不得**是同一个文件。

    抽成独立函数是为了**可测**——内联在 ``main()`` 里就只能靠跑 CLI 覆盖，
    而这里是核心？的假绿防线，必须能被单点测试反复 exercising。
    """
    if graph_path.resolve() == baseline_path.resolve():
        raise ValueError(
            f"--judgements 与 --baseline-judgements 指向同一个文件（{graph_path}）："
            "A1 裁决 3 要求两侧各判各的，共用一张表 ⇒ 替基线预设答案 ⇒ 增益无意义"
        )


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
    """TBD-7 校准：**只输出建议值**（RK-E7：绝不改 config / .env）。

    **本函数是 `EVAL_SINGLE_DOC_TOKEN_CEILING` 的消费者之一**：阈值与来源都从
    `runner.resolve_cost_ceiling()` 读（不硬编码 32 000），并**当场判一次**
    「实测均值 vs 当前阈值」——让"阈值是多少 / 从哪来 / 判出来是什么"一目了然。
    """
    print("== TBD-7 校准（只输出建议，不改任何配置） ==")
    ceiling, source = resolve_cost_ceiling()
    print(f"当前 ceiling: {ceiling} token/doc  [threshold_source={source}]")
    if source == THRESHOLD_PROVISIONAL:
        print(
            "  ⚠️ 该值是**演示语料推算的默认值**（config 默认，未经校准）⇒ "
            "判定只给 PASS(provisional)，**不构成 TBD-7 收敛证据**。"
        )
    else:
        print("  ✅ env 显式覆盖（人工裁决过）⇒ 判定可给 PASS / FAIL。")
    if cost_records is None:
        print(
            "无 --cost-records ⇒ **无法校准**。\n"
            "原因：真实成本数据要等 P5-M6 落 cost_metrics 表（token 目前只进日志、未落库）。\n"
            f"⇒ TBD-7 维持 {source}（当前 eval_single_doc_token_ceiling = {ceiling}，"
            "见 config.py 注释）。"
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

    #: **当场判一次**：实测均值 vs 当前阈值（阈值与来源都来自 config / env，不硬编码）。
    mean = single_doc_cost(records)
    if mean.value is None:
        print(f"实测均值              : 无（{mean.reason}）⇒ 不判")
    else:
        verdict = judge(
            mean.value,
            threshold=float(ceiling),
            threshold_source=source,
            higher_is_better=False,
        )
        print(
            f"实测均值 vs 当前阈值  : {mean.value:.0f} vs {ceiling} ⇒ **{verdict.value}**"
        )
        print(f"  （判定用 {source} 阈值；口径 {mean.unit} / {mean.options}）")

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
        "--gold",
        choices=("v1", "v2"),
        default="v1",
        help=(
            "C2-a / C2-b 用哪版 gold 语料：v1 = 8/60/30/9 手工语料（**默认**，"
            "规模不足以判达标）；v2 = **A8 扩标 200/500/100/20**（判达标必须用这版）"
        ),
    )
    parser.add_argument(
        "--criteria",
        help=f"只跑指定判据（逗号分隔）；可选：{','.join(ALL_CRITERIA)}",
    )
    parser.add_argument("--out", help="报告落点 JSON（默认 backend/reports/eval/）")
    parser.add_argument(
        "--judgements",
        help=(
            "**图侧**人工判分 JSON（{题号: true/false}）——A3：脚本不自动判分。"
            "（C1 还需另给 --baseline-judgements）"
        ),
    )
    parser.add_argument(
        "--baseline-judgements",
        help=(
            "**基线侧**人工判分 JSON（同一份 rubric、同一批改分人）。"
            "⚠️ **A1 裁决 3：必须是另一张表**——两侧答案由不同检索产出，同一题在两侧"
            "对错可以不同；共用一张表等于替基线「预设答案」⇒ 增益失去意义。"
            "与 --judgements 指向同一文件时本脚本直接报错退出。"
        ),
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
    # --- **G-25（P3-E）**：CI 门禁（只判不退化）---
    parser.add_argument(
        "--gate",
        action="store_true",
        help="按**不退化**判门禁（G-25）：value 缺失 / 基线缺项 / 空图 / 退化超容差 ⇒ 退出码 1",
    )
    parser.add_argument(
        "--baseline",
        help=f"基线 JSON（默认 data/eval/baselines/{DEFAULT_BASELINE_FILE}）",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=f"退化容差（绝对差值，默认 {DEFAULT_TOLERANCE}）",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="**重写**基线为本次实测值（⚠️ 用退化后的值刷基线 = 把门禁调成恒绿）",
    )
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
    graph_judgements_path = Path(args.judgements) if args.judgements else None
    baseline_judgements_path = (
        Path(args.baseline_judgements) if args.baseline_judgements else None
    )
    #: **A1 裁决 3 的机器守卫**：两张表落在同一个文件 ⇒ 直接拒绝执行。
    #: 只写在 help 里不够——万一人手滑传同一份，出来的增益值看着很正常，实则等于
    #: 拿图侧的答案预先替基线判了卷，这条判据从此失效。
    if graph_judgements_path and baseline_judgements_path:
        try:
            distinct_judgement_tables(graph_judgements_path, baseline_judgements_path)
        except ValueError as exc:
            parser.error(str(exc))

    ctx = RunnerContext(
        mode=run_mode,  # type: ignore[arg-type]
        git_hash=git_hash(),
        base_url=args.base_url or RunnerContext(mode=run_mode, git_hash="x").base_url,
        judgements=(
            _load_judgements(graph_judgements_path) if graph_judgements_path else None
        ),
        baseline_judgements=(
            _load_judgements(baseline_judgements_path)
            if baseline_judgements_path
            else None
        ),
        judged_by=args.judged_by,
        gold_version=args.gold,
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

    # --- **G-25 门禁**（只判不退化；不加 --gate 时行为与以前一致）---
    if args.update_baseline:
        return _update_baseline(results, ctx.git_hash, args.tolerance, args.baseline)
    if args.gate:
        return _gate(results, baseline_path=args.baseline, tolerance=args.tolerance)

    #: 退出码：**有 FAIL 才非 0**。BLOCKED / UNKNOWN **不算失败**（它们不是"没达标"，
    #: 是"没测出来"——把它当失败会逼人用假数据凑绿）。
    failed = [r.criterion for r in results if r.verdict and r.verdict.value == "FAIL"]
    if failed:
        print(f"\n[FAIL] 未达标判据: {', '.join(failed)}")
        return 1
    return 0


def _update_baseline(
    results: list[CriterionResult],
    git_hash_value: str,
    tolerance: float,
    baseline_path: str | None,
) -> int:
    """**写**基线（实测值）。刻意做成独立命令且**打印警告**：刷基线会掩盖退化。"""
    baseline = build_baseline(results, git_hash=git_hash_value, tolerance=tolerance)
    if not baseline["criteria"]:
        print("[FAIL] 本次没有任何实测值 ⇒ 拒绝写基线（空基线 = 门禁缺项恒红）")
        return 1
    target = (
        Path(baseline_path) if baseline_path else (BASELINE_DIR / DEFAULT_BASELINE_FILE)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] 基线已写入 {target}")
    for name, value in baseline["criteria"].items():
        print(f"  {name}: {value}")
    print(
        "\n⚠️ **刷基线即重设门禁刻度**：若本次值本身是退化后的值，"
        "写进去等于把门禁调成「退化了也绿」。请确认这些值是**受控语料上的真值**。"
    )
    return 0


def _gate(
    results: list[CriterionResult],
    *,
    baseline_path: str | None,
    tolerance: float,
) -> int:
    """按「不退化」判门禁（G-25 ④ / ⑤）。"""
    try:
        baseline = load_baseline(baseline_path)
    except FileNotFoundError as error:
        print(f"[FAIL] 基线文件不存在：{error.filename}")
        print("      先实测一次并写基线：--live --criteria <…> --update-baseline")
        return 1

    outcome = evaluate_gate(results, baseline=baseline, tolerance=tolerance)
    if outcome.compared:
        print("\n[gate] 与基线比对：")
        for line in outcome.compared:
            print(f"  {line}")
    for warning in outcome.warnings:
        print(f"[warn] {warning}")
    if not outcome.ok:
        print(f"\n[FAIL] 门禁不通过（{len(outcome.failures)} 项）：")
        for failure in outcome.failures:
            print(f"  - {failure}")
        return outcome.exit_code
    print("\n[OK] 门禁通过（**只判不退化**，不判达标）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
