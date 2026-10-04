"""**统计口径**：二项比例的 **Clopper-Pearson 精确单侧置信界**（A8 裁决 2）。

**为什么需要它（这是 A8 最硬的发现，不是精度微调）**：
现有 9 组 gold 测出 recall = 1.00，直觉上"满分 ⇒ 达标"。但

    9/9 的 95% 单侧**下界** = 0.05^(1/9) ≈ **0.717 < 0.80**

⇒ **即便观测到满分，统计上也支持不了「召回 ≥ 0.80」**。同理 0/9 的误报**上界**
= 1 − 0.05^(1/9) ≈ 0.283 >> 0.15 ⇒ 完全不支持「误报 ≤ 0.15」。
这不是"精度差一点"，是**样本量根本不足以判该判据**。

**判定用界，不只用点估计**（`changes/P0-m6-eval/integration-log.md` L10-A8 第 2 条）：

| 判据 | 用哪一侧 | 20 组时须满足 |
|---|---|---|
| C2-a 召回 ≥ 0.80 | **下界** | ≥19 组命中（19/20 下界 ≈0.82 ✓）；18/20 ≈0.75 ✗；16/20 ≈0.62 ✗ |
| C2-b 误报 ≤ 0.15 | **上界** | 误报 **0 条**（0/20 上界 ≈0.139 ✓）；1 条即 ✗（≈0.18） |

⇒ 这条把「**踩线达标**」机械地挡在外面：卡在 0.80 / 0.15 上通过，统计上不成立。

**为什么是"精确"而不是正态近似**：n = 20 且命中常为满 / 零 ⇒ 正态近似（Wald）
在 p ≈ 0 或 1 处会给出**越界或退化**的区间（0/20 的 Wald 上界 = 0 ⇒ 假绿）。
Clopper-Pearson 是精确二项区间，**在边界处仍然保守** ⇒ 不放水。
实现用**二分 + `math.comb`**（n 只有几十 ⇒ 无需求助 scipy，也不引入新依赖）。
"""

from __future__ import annotations

from math import comb

#: 单侧显著性（95% 单侧置信界）
DEFAULT_ALPHA = 0.05

#: 二分迭代次数：2^-80 的精度，远超报告需要的 4 位小数
_MAX_ITER = 80


def _cdf(k: int, n: int, p: float) -> float:
    """``P(X <= k)``（二项分布 CDF）。"""
    total = 0.0
    for i in range(0, k + 1):
        total += comb(n, i) * (p**i) * ((1.0 - p) ** (n - i))
    return total


def _sf(k: int, n: int, p: float) -> float:
    """``P(X >= k)``（上尾）。"""
    return 1.0 - _cdf(k - 1, n, p)


def clopper_pearson_lower(k: int, n: int, *, alpha: float = DEFAULT_ALPHA) -> float:
    """**下界**：观测到 ``k / n`` 时，真值**至少**是多少（95% 单侧）。

    Args:
        k: 成功数（如"命中的 gold 组数"）。
        n: 试验数（如"gold 组总数"）。
        alpha: 单侧显著性。

    Returns:
        ``p`` 使得 ``P(X >= k | n, p) = alpha``；``k = 0`` ⇒ 0.0。
    """
    if n <= 0:
        raise ValueError(f"n 必须 > 0（拿到 {n}）⇒ 无分母，界不存在")
    if not 0 <= k <= n:
        raise ValueError(f"k 必须落在 [0, n]（k={k}, n={n}）")
    if k == 0:
        return 0.0
    if k == n:
        return alpha ** (1.0 / n)

    low, high = 0.0, 1.0
    for _ in range(_MAX_ITER):
        mid = (low + high) / 2.0
        if _sf(k, n, mid) < alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def clopper_pearson_upper(k: int, n: int, *, alpha: float = DEFAULT_ALPHA) -> float:
    """**上界**：观测到 ``k / n`` 时，真值**至多**是多少（95% 单侧）。

    误报率这类"越低越好"的指标用它：``k=0`` ⇒ ``1 - alpha^(1/n)``（20 条 ⇒ ≈0.139）。
    """
    if n <= 0:
        raise ValueError(f"n 必须 > 0（拿到 {n}）⇒ 无分母，界不存在")
    if not 0 <= k <= n:
        raise ValueError(f"k 必须落在 [0, n]（k={k}, n={n}）")
    if k == n:
        return 1.0
    if k == 0:
        return 1.0 - alpha ** (1.0 / n)

    low, high = 0.0, 1.0
    for _ in range(_MAX_ITER):
        mid = (low + high) / 2.0
        if _cdf(k, n, mid) > alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def one_sided_bound(
    k: int, n: int, *, higher_is_better: bool, alpha: float = DEFAULT_ALPHA
) -> float:
    """按判据方向取**该用的那一侧**界：越高越好 ⇒ 下界；越低越好 ⇒ 上界。"""
    if higher_is_better:
        return clopper_pearson_lower(k, n, alpha=alpha)
    return clopper_pearson_upper(k, n, alpha=alpha)


__all__ = [
    "DEFAULT_ALPHA",
    "clopper_pearson_lower",
    "clopper_pearson_upper",
    "one_sided_bound",
]
