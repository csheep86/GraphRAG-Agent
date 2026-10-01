"""补丁期契约冻结（护栏 **G-15** / DR-C2 / PRD H16）。

**判据**：版本号**第三位（PATCH）**变更时，``contracts/openapi.yaml`` 必须**零 diff**。

版本语义见 ``docs/delivery-requirements-and-guardrails.md`` §7：
`app_version` = `MAJOR.MINOR.PATCH`，`1.6.0` 的补丁是 `1.6.1`。

与 G-4（契约零漂移）的分工：G-4 管"契约与 Pydantic 模型**是否一致**"；
本条管"**补丁期根本不许改契约**"。改了模型但同步导出契约，G-4 会通过，
而客户插件可能因此失效——只有本条拦得住。

用法::

    uv run python scripts/check_patch_contract_freeze.py --base main

退出码::

    0 = 通过，或**不适用**（非 PATCH 变更 / 无法确定 base / 取不到版本号）
    1 = PATCH 变更却改了契约

**不适用时为什么退 0**：本条只在"版本确实只 bump 了 PATCH"时有意义。
base 缺失（首个提交）或版本未变时强行判红，只会让流水线变成噪音。
但"不适用"必须**打印出来**，不能沉默——与 CI 里把 skip 原因写进日志是同一条纪律。
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

CONFIG_REL = "backend/app/core/config.py"
CONTRACT_REL = "contracts/openapi.yaml"

#: 允许前导缩进——``app_version`` 是 Settings 的**类内**字段，必然带缩进。
#: （首版写成 ``^app_version`` 取不到值 ⇒ 脚本恒判"不适用"退 0 ⇒ 退化成假护栏。）
_VERSION_RE = re.compile(
    r"""^\s*app_version:\s*str\s*=\s*["']([^"']+)["']""", re.MULTILINE
)


def _git(*args: str) -> tuple[int, str]:
    """在仓库根执行 git；返回 (退出码, 输出)。"""
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout.strip()


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    """``"1.6.0"`` → ``(1, 6, 0)``；非三段式（含 `1.6` / `v1.6.0-beta`）返回 None。"""
    if not raw:
        return None
    parts = raw.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def is_patch_bump(
    old: tuple[int, int, int] | None, new: tuple[int, int, int] | None
) -> bool:
    """是否"只 bump 了 PATCH"：MAJOR / MINOR 不变，PATCH 递增。"""
    if old is None or new is None:
        return False
    return old[:2] == new[:2] and new[2] > old[2]


def app_version_at(ref: str) -> str | None:
    """取某个 git ref 下的 ``app_version`` 字面量。"""
    code, text = _git("show", f"{ref}:{CONFIG_REL}")
    if code != 0:
        return None
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def contract_changed_since(base: str) -> bool:
    """契约相对 base 是否有改动。"""
    code, text = _git("diff", "--name-only", base, "--", CONTRACT_REL)
    if code != 0:
        return False  # 取不到 diff 时不主张"改了"
    return bool(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="",
        help="对比基准（PR base 分支或 push 前的 HEAD）；留空则本条不适用",
    )
    args = parser.parse_args()

    base = args.base.strip()
    if not base or set(base) == {"0"}:
        print(f"::notice::无可用 diff 基准（base={base!r}），补丁期契约冻结本轮不适用")
        return 0

    old_raw = app_version_at(base)
    new_raw = app_version_at("HEAD")
    old, new = parse_version(old_raw), parse_version(new_raw)

    if old is None or new is None:
        print(
            f"::notice::取不到可比的版本号（base={old_raw!r}, HEAD={new_raw!r}），"
            "补丁期契约冻结本轮不适用"
        )
        return 0

    if not is_patch_bump(old, new):
        print(
            f"[OK] 版本 {old_raw} → {new_raw} 不是 PATCH 变更"
            "（契约变更须走 MINOR / MAJOR 流程），本条不适用"
        )
        return 0

    if contract_changed_since(base):
        print(
            f"[FAIL] 版本 {old_raw} → {new_raw} 是 **PATCH** 变更，"
            f"但 {CONTRACT_REL} 有改动。\n"
            "补丁三条纪律（ADR-0007 §3.8.3）第 1 条：补丁**不改契约**。\n"
            "若确需改契约 ⇒ 升 MINOR / MAJOR（届时须评估插件是否受影响）。"
        )
        return 1

    print(f"[OK] PATCH 变更 {old_raw} → {new_raw}，契约零 diff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
