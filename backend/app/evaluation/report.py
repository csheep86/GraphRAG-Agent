"""评测**报告**落盘与比对（E2）。

**幂等契约（硬）**：同一输入两次运行 ⇒ 报告**逐字一致**（唯一例外 `generated_at`）。
这是"结论可归因"的地基：报告对不上 = 要么有随机性，要么有隐藏状态。

**为什么要 `synthetic` 分区**：口径演练值（:func:`app.evaluation.runner.self_test`）
与判据结果**分区存放**，演练块显式标 `synthetic: true`——
放在同一个键下，演练值迟早会被当成测量结果读走。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.evaluation.criteria import CriterionResult
from app.evaluation.runner import RunnerContext

#: 比对时**忽略**的键（时间戳每次都变，不是差异）：
IGNORED_IN_COMPARE = {"generated_at"}


def git_hash() -> str:
    """当前 HEAD 短哈希（拿不到 ⇒ ``"unknown"``，**不编造**）。"""
    try:
        out = subprocess.run(  # noqa: S603 - 固定参数，无 shell
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - 报告不应因拿不到 hash 而崩
        return "unknown"


def _plain(value: Any) -> Any:
    """把 dataclass / 枚举 / 元组递归转成 JSON 可序列化结构（**顺序稳定**）。"""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}  # type: ignore[arg-type]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def build_report(
    *,
    ctx: RunnerContext,
    results: list[CriterionResult],
    self_test_block: dict[str, Any],
    upgrade_todo: list[str],
) -> dict[str, Any]:
    """组装报告（**键序固定**，便于 diff）。"""
    return {
        "schema": "eval-acceptance/v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_hash": ctx.git_hash,
        "mode": ctx.mode,
        "dataset_versions": _dataset_versions(),
        "criteria": [_plain(r) for r in results],
        "self_test": self_test_block,
        "upgrade_todo": upgrade_todo,
        "legend": {
            "measured": "真跑出数，数据集与判分口径均已定",
            "measured_provisional": "跑了，但语料 / 基线非终局",
            "blocked": "依赖未落地，value 恒为 null（**不是 0**）",
            "unknown": "口径未定或数据缺失，value 恒为 null",
            "PASS(provisional)": "阈值未校准时的达标，**不构成 TBD-7 收敛证据**",
        },
    }


def _dataset_versions() -> dict[str, str]:
    from app.evaluation.runner import dataset_version_map  # noqa: PLC0415

    return dataset_version_map()


def write_report(report: dict[str, Any], path: Path) -> Path:
    """落盘（UTF-8 / 缩进 2 / **不排序键**，保持语义顺序）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in IGNORED_IN_COMPARE:
                continue
            flat.update(_flatten(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            flat.update(_flatten(value, f"{prefix}[{index}]"))
    else:
        flat[prefix] = payload
    return flat


def compare(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    """比对两份报告，返回**差异描述**（空列表 = 幂等通过）。"""
    a, b = _flatten(left), _flatten(right)
    diffs: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            diffs.append(f"+ {key} = {b[key]!r}（右有左无）")
        elif key not in b:
            diffs.append(f"- {key} = {a[key]!r}（左有右无）")
        elif a[key] != b[key]:
            diffs.append(f"~ {key}: {a[key]!r} → {b[key]!r}")
    return diffs


def render(report: dict[str, Any]) -> str:
    """人可读摘要（**不替代 JSON**：判据以 JSON 为准）。"""
    lines = [
        f"mode={report['mode']}  git={report['git_hash']}  "
        f"generated_at={report['generated_at']}",
        "",
        "判据：",
    ]
    for item in report["criteria"]:
        value = item["value"]
        shown = "null" if value is None else f"{value:.4f}"
        lines.append(
            f"  [{item['status']:<20}] {item['criterion']:<28} value={shown}"
            + (f"  unit={item['unit']}" if item.get("unit") else "")
            + (f"  verdict={item['verdict']}" if item.get("verdict") else "")
            + (f"  blocked_by={item['blocked_by']}" if item.get("blocked_by") else "")
        )
    lines.append("")
    lines.append(f"口径演练（synthetic={report['self_test'].get('synthetic')}）：")
    for key, value in report["self_test"].get("metrics", {}).items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("升为 MEASURED 还缺什么：")
    lines.extend(f"  - {item}" for item in report["upgrade_todo"])
    return "\n".join(lines)
