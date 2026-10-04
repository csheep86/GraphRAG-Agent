"""**CI 门禁：C2-a / C2-b 只判「不退化」**（护栏 **G-25** / DR-D10）。

**为什么单独一个模块**：门禁规则必须能被**单测**——它要是埋在 CLI 里，就只能靠
"真起 Neo4j 跑一遍"来验证，而那条路径**太贵**（CI 上是几十秒、本地要起容器），
结果是没人验证门禁本身。规则做成纯函数后，"退化 ⇒ 红"这件事**不依赖图库**也能钉死。

**五条规则**（`delivery-requirements-and-guardrails.md` G-25 行）：

1. ``value is None`` ⇒ **fail**。没测出来 ≠ 通过：把它放行就等于"Neo4j 不可达时
   门禁恒绿"，那是 **R-9 恒绿失效**的翻版；
2. 基线**缺项** ⇒ **fail**：不许"基线里没有就跳过比对"（跳过 = 没有门禁）；
3. **空图守卫**：gold 非空而 ``detected_count == 0`` ⇒ **fail**。空图 ⇒ 检测到 0 疑点
   ⇒ 召回 0 ⇒ 会红成"退化"，但**报错信息必须直说"种子语料没导入"**，否则排查方向错；
4. **退化**超容差 ⇒ **fail**（recall 下降 / fpr 上升）；
5. **不达标 ⇒ 不 fail**，只记 warning——CI **只判不退化**，达标判定归 P6
   （且要等 A8 扩标后才可宣称，见 G-25 行的 ❌ 项）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation.criteria import CriterionResult, Verdict

#: 默认容差（**绝对差值**）。为什么是绝对差值而不是百分比：基线值在 0/1 附近
#: （recall 1.0 / fpr 0.0），百分比容差在 0 附近会退化成"零容差"，一有抖动就红。
DEFAULT_TOLERANCE = 0.02

#: 受控种子语料的基线文件（**入库**，换版有 git 痕迹）。
#: **A8（2026-10-04）**：基线语料由 v1（9 组）换成 **v2（200/500/100/20）**
#: ⇒ 基线文件同步换版；v1 那份已作废删除（留着会被误用，且它对应的是
#: "统计上判不出"的语料）。**刷基线即重设门禁刻度**，须显式执行。
DEFAULT_BASELINE_FILE = "ci-c2-v2.json"
BASELINE_DIR = Path(__file__).resolve().parents[2] / "data" / "eval" / "baselines"

#: 判据 → 方向（``True`` = 越高越好）。**未登记的判据不得进门禁**（方向不明就没法判退化）。
DIRECTIONS: Mapping[str, bool] = {
    "c2_a_hidden_relation_recall": True,
    "c2_b_false_positive_rate": False,
}


@dataclass(frozen=True)
class GateOutcome:
    """一次门禁判定的结果（``failures`` 非空 ⇒ 不通过）。"""

    ok: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    compared: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def direction_of(criterion: str) -> bool:
    """判据方向（越高越好 / 越低越好）。未登记 ⇒ **显式报错**。"""
    if criterion not in DIRECTIONS:
        raise KeyError(
            f"判据 {criterion} 未登记方向 ⇒ 无法判退化（新增判据要进 CI 必须先登记）"
        )
    return DIRECTIONS[criterion]


def load_baseline(path: Path | str | None = None) -> dict[str, float]:
    """读基线（``{"criteria": {判据名: 值}}``）。"""
    import json

    target = Path(path) if path else BASELINE_DIR / DEFAULT_BASELINE_FILE
    payload = json.loads(target.read_text(encoding="utf-8"))
    criteria = payload.get("criteria") or {}
    return {str(name): float(value) for name, value in criteria.items()}


def build_baseline(
    results: Sequence[CriterionResult],
    *,
    git_hash: str,
    tolerance: float = DEFAULT_TOLERANCE,
    note: str | None = None,
) -> dict[str, Any]:
    """由**实测结果**生成基线（不掺任何推算值）。

    ⚠️ 生成基线前必须确认：这批值是**受控语料上的真值**。
    用退化后的值刷基线 = 把门禁调到"退化了也绿"，那比没有门禁更糟
    （CLI 侧会在写基线时打印同样的警告）。
    """
    values = {r.criterion: r.value for r in results if r.value is not None}
    return {
        "id": "ci-c2-baseline",
        "criteria": values,
        "tolerance": tolerance,
        "git_hash": git_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        "note": note or "受控种子语料（demo/affiliation）上的实测值；**只判不退化**",
    }


def evaluate_gate(
    results: Sequence[CriterionResult],
    *,
    baseline: Mapping[str, float],
    tolerance: float = DEFAULT_TOLERANCE,
) -> GateOutcome:
    """按五条规则判定。

    Args:
        results: 本次运行的判据结果（**只**传要进门禁的判据）。
        baseline: 基线值（:`func:`load_baseline` 的产物）。
        tolerance: 允许的绝对差值。
    """
    failures: list[str] = []
    warnings: list[str] = []
    compared: list[str] = []

    for result in results:
        name = result.criterion
        detail = result.detail or {}

        # ③ 空图守卫（**最先判**：它是最常见的 CI 失败原因，信息必须最明确）
        gold_count = int(detail.get("gold_count") or 0)
        detected = detail.get("detected_count")
        if gold_count > 0 and detected == 0:
            failures.append(
                f"{name}：空图守卫——gold {gold_count} 组、检测产出 **0 疑点** ⇒ "
                "极可能是**种子语料没导入**或检测链路断了（此时召回必然 0，"
                "**不许**当成通过放过）"
            )
            continue

        # ① 没测出来 ⇒ 不许过
        if result.value is None:
            failures.append(
                f"{name}：没有测量值（status={result.status.value}"
                f"{f'；blocked_by={result.blocked_by}' if result.blocked_by else ''}）"
                " ⇒ CI 上「没测出来」**不是**通过（否则 Neo4j 不可达时恒绿）"
            )
            continue

        # ② 基线缺项 ⇒ 不许跳过
        if name not in baseline:
            failures.append(
                f"{name}：基线里没有这一项 ⇒ **不许跳过比对**"
                "（跳过等于这条判据没有门禁）"
            )
            continue

        base = float(baseline[name])
        delta = float(result.value) - base
        higher_is_better = direction_of(name)
        worse = -delta if higher_is_better else delta
        compared.append(f"{name}: {base:.4f} → {result.value:.4f}")

        # ④ 退化
        if worse > tolerance:
            trend = "下降" if higher_is_better else "上升"
            failures.append(
                f"{name}：**退化** {base:.4f} → {result.value:.4f}"
                f"（{trend} {abs(delta):.4f} > 容差 {tolerance}）"
            )

        # ⑤ 不达标 ⇒ 只 warning（CI 只判不退化）
        if result.verdict is Verdict.FAIL:
            warnings.append(
                f"{name}：未达阈值（{result.value:.4f} vs {result.threshold}）"
                "——CI **不判达标**，仅提示（达标判定归 P6 + A8 扩标后）"
            )

    return GateOutcome(
        ok=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        compared=tuple(compared),
    )


__all__ = [
    "BASELINE_DIR",
    "DEFAULT_BASELINE_FILE",
    "DEFAULT_TOLERANCE",
    "DIRECTIONS",
    "GateOutcome",
    "build_baseline",
    "direction_of",
    "evaluate_gate",
    "load_baseline",
]
