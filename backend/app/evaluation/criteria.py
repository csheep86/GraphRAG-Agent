"""C1–C3 的**四态状态机**：把「现在能否自证」变成**机器可判**的状态。

为什么不是一句判断：口头判断会随人变，且**无法被 CI 断言**。
状态机让"未完成"无处藏身——`BLOCKED` 必须是 `value=None` + `blocked_by`，
**结构上**不许携带数字（`0.0` 会被读成"召回为 0"，直接误触发反证 **F2**）。

四态（`changes/P0-m6-eval/proposal.md` §4.1）：

| 状态 | 含义 |
|---|---|
| ``MEASURED`` | 真跑出数，且数据集 / 判分口径均已定 |
| ``MEASURED_PROVISIONAL`` | 跑了，但语料或基线**非终局**（演示语料 / fixture 基线） |
| ``BLOCKED`` | 依赖 M6 或 RAG 基线，走占位执行点 |
| ``UNKNOWN`` | 口径未定或数据缺失 |

**三条自证线**（§4.2 第 3 条）：链路已实现 **且** 数据集已标注 **且** 判分口径已定义
⇒ `MEASURED`；缺任一自动降级，并由 :func:`resolve_status` 给出降级原因。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol

#: 阈值来源（**§5.2 第 2 条**：报告强制打印，防 provisional 阈值被当达标线）。
THRESHOLD_PROVISIONAL = "provisional"
THRESHOLD_ENV_OVERRIDE = "env-override"
THRESHOLD_CALIBRATED = "calibrated"


class CriterionStatus(StrEnum):
    """判据的四种状态（**不是**一个数）。"""

    MEASURED = "measured"
    MEASURED_PROVISIONAL = "measured_provisional"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    """达标判定。``PASS_PROVISIONAL`` 的值**刻意带括号**——让它无法被读成"已达标"。"""

    PASS = "PASS"
    FAIL = "FAIL"
    #: 阈值仍是 provisional（未校准）时的 PASS：**不构成 TBD-7 收敛证据**。
    PASS_PROVISIONAL = "PASS(provisional)"
    #: 值缺失或阈值未定 ⇒ 不判（既不是 PASS 也不是 FAIL）。
    INDETERMINATE = "INDETERMINATE"
    #: **A8（2026-10-04）**：点估计达标，但 **95% 单侧置信界不达标** ⇒
    #: **样本效力不足以宣称达标**，**不得**当成 PASS。
    #:
    #: 由来：9/9 的召回点估计 = 1.00，而它的下界只有 **0.717 < 0.80**
    #: ⇒ "满分"根本支持不了"达标"。没有这个语义，报告会把"判不出"写成
    #: "PASS(provisional)"——那正是 L11(b)1 登记的「报告打架」。
    UNDERPOWERED = "UNDERPOWERED"


@dataclass(frozen=True)
class Provenance:
    """结论的**归因**（必填）：两次运行可比的前提。"""

    dataset_version: str
    mode: Literal["offline", "live"]
    git_hash: str
    kg_version: str | None = None
    corpus: str | None = None
    #: **A8（2026-10-04）**：语料层（``L1`` 算法层 / ``L2`` 端到端）。
    #: 写进归因是为了**防止把 L1 的结果说成端到端**（A8 裁决 4 / G5 声明）。
    corpus_layer: str | None = None
    rubric: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CriterionResult:
    """单条判据的结果。**构造即校验**（不靠调用方自觉）。"""

    criterion: str
    status: CriterionStatus
    value: float | None
    provenance: Provenance
    unit: str | None = None
    blocked_by: str | None = None
    threshold: float | None = None
    threshold_source: str | None = None
    verdict: Verdict | None = None
    detail: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status is CriterionStatus.BLOCKED:
            if self.value is not None:
                raise ValueError(
                    f"{self.criterion}: BLOCKED 不得携带数字（会被读成真实测量值）"
                )
            if not self.blocked_by:
                raise ValueError(f"{self.criterion}: BLOCKED 必须给出 blocked_by")
        if self.status in (
            CriterionStatus.MEASURED,
            CriterionStatus.MEASURED_PROVISIONAL,
        ):
            if self.value is None:
                raise ValueError(
                    f"{self.criterion}: {self.status.value} 必须有值（无值应降级为 UNKNOWN）"
                )
        if self.status is CriterionStatus.UNKNOWN and self.value is not None:
            raise ValueError(f"{self.criterion}: UNKNOWN 不得携带数字")
        if self.threshold_source is not None and self.threshold is None:
            raise ValueError(
                f"{self.criterion}: 有 threshold_source 就必须有 threshold"
            )


def resolve_status(
    *,
    link_ready: bool,
    dataset_ready: bool,
    rubric_defined: bool,
    corpus_is_final: bool = False,
) -> tuple[CriterionStatus, str | None]:
    """按**三条自证线**判定状态，并给出降级原因。

    - 链路未实现 ⇒ ``BLOCKED``（原因 = 缺链路）；
    - 数据集未标注 / 判分口径未定 ⇒ ``UNKNOWN``；
    - 三条全绿但语料非终局 ⇒ ``MEASURED_PROVISIONAL``；否则 ``MEASURED``。
    """
    if not link_ready:
        return CriterionStatus.BLOCKED, "被测链路未实现"
    if not dataset_ready:
        return CriterionStatus.UNKNOWN, "数据集缺失或未标注"
    if not rubric_defined:
        return CriterionStatus.UNKNOWN, "判分口径（rubric）未定义"
    if not corpus_is_final:
        return CriterionStatus.MEASURED_PROVISIONAL, "语料或基线非终局"
    return CriterionStatus.MEASURED, None


def judge(
    value: float | None,
    *,
    threshold: float | None,
    threshold_source: str | None = None,
    higher_is_better: bool = True,
    ci_bound: float | None = None,
) -> Verdict:
    """按阈值判定；``threshold_source`` 决定是否降级为 ``PASS(provisional)``。

    **§5.2 第 3 条（防假绿）**：阈值来源为 ``provisional`` 时，
    即便达标也只给 ``PASS(provisional)``，并在报告中标注"不构成 TBD-7 收敛证据"。

    **A8（2026-10-04）：判定用置信界**。``ci_bound`` 给的是**该用的那一侧**
    95% 单侧界（越高越好 ⇒ 下界；越低越好 ⇒ 上界，见
    :func:`app.evaluation.stats.one_sided_bound`）：

    - 点估计不达标 ⇒ ``FAIL``（与以前一致）；
    - 点估计达标但**界**不达标 ⇒ ``UNDERPOWERED``（**不是** PASS——
      9/9 的 1.00 就是这么被读成达标的）；
    - 两者都达标 ⇒ 按 ``threshold_source`` 给 PASS / PASS(provisional)。
    """
    if value is None or threshold is None:
        return Verdict.INDETERMINATE
    ok = value >= threshold if higher_is_better else value <= threshold
    if not ok:
        return Verdict.FAIL
    if ci_bound is not None:
        bound_ok = ci_bound >= threshold if higher_is_better else ci_bound <= threshold
        if not bound_ok:
            return Verdict.UNDERPOWERED
    if threshold_source == THRESHOLD_PROVISIONAL:
        return Verdict.PASS_PROVISIONAL
    return Verdict.PASS


class CriterionEvaluator(Protocol):
    """判据执行器：给定上下文，产出一个 :class:`CriterionResult`。

    **与 P5-M6 的交接面**：实现 M6 后只需**替换 evaluator**，
    不动指标函数、不改报告格式。
    """

    def __call__(self, ctx: dict[str, Any]) -> CriterionResult: ...


class PlaceholderEvaluator:
    """占位执行点：产出 ``BLOCKED``，**永不产出数字**。

    它是"依赖 M6 / 基线"的判据在 P5-M6 之前的**唯一**合法实现——
    目的就是让"还没做"与"测得 0"在报告里**长得不一样**。
    """

    def __init__(
        self, criterion: str, *, blocked_by: str, detail: dict[str, Any] | None = None
    ):
        self.criterion = criterion
        self.blocked_by = blocked_by
        self.detail = detail

    def __call__(self, ctx: dict[str, Any]) -> CriterionResult:  # noqa: ARG002
        provenance = Provenance(
            dataset_version=str(ctx.get("dataset_version", "n/a")),
            mode=str(ctx.get("mode", "offline")),  # type: ignore[arg-type]
            git_hash=str(ctx.get("git_hash", "unknown")),
            notes="占位执行点：等待 blocked_by 指明的前置工作完成后替换 evaluator",
        )
        return CriterionResult(
            criterion=self.criterion,
            status=CriterionStatus.BLOCKED,
            value=None,
            provenance=provenance,
            blocked_by=self.blocked_by,
            verdict=Verdict.INDETERMINATE,
            detail=self.detail,
        )


#: 判据注册表（**唯一真源**）：新增判据必须登记，避免"脚本里跑了但没人知道"。
CRITERIA: dict[str, CriterionEvaluator] = {}


def register_criterion(name: str, evaluator: CriterionEvaluator) -> None:
    """登记一个判据执行器（**不允许**静默覆盖：改名须显式 ``unregister``）。"""
    if name in CRITERIA:
        raise ValueError(f"判据 {name} 已登记（重复登记会让旧结论失去归因）")
    CRITERIA[name] = evaluator


def unregister_criterion(name: str) -> None:
    """移除登记（**仅**用于 P5-M6 替换占位执行点，或测试清理）。"""
    CRITERIA.pop(name, None)
