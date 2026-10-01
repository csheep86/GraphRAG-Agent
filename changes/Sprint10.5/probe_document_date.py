"""¥0 探针：六份制度文档的 ``document_date`` 抽取结果。

为什么要有这个文件
------------------
2025 版刚写好就验，避免"入库了才发现日期是错的"。两条关心：

1. **2025 版必须抽出 2025-01-01**，不能是失效日 2025-12-31；
2. **2026 版的既有结果不许变**（会是 2026-01-01）——新增语料不得改变老语料的行为。

第 1 条的风险确实存在且不是空想：前置锚点词表含 ``截至`` / ``截止``
（``document_date.py:72-73``），失效句若写成「有效期**截至** 2025 年 12 月 31 日」，
抽出来的文档日期就会是失效日。故 **2025 版一律写「有效期至」**——本探针就是这条纪律的执行者。

用法（工作目录任意）::

    uv run python changes/Sprint10.5/probe_document_date.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# noqa: E402 - 路径注入必须先于 import
from app.services.parsing.document_date import (  # noqa: E402
    resolve_document_date,
    resolve_document_expiry,
)

POLICIES = ROOT / "demo" / "attendance" / "policies"

#: 期望值：文件名 → 期望日期。**写完就要有信念**，探针的作用是证伪它
EXPECTED: dict[str, str] = {
    "attendance-policy-2025.md": "2025-01-01",
    "attendance-policy-2026.md": "2026-01-01",
    "fieldwork-attendance-rules-2025.md": "2025-01-01",
    "fieldwork-attendance-rules-2026.md": "2026-01-01",
    "overtime-and-comp-off.md": "2026-01-01",
    "worktime-system-rules.md": "2026-01-01",
}

#: 有效期终点（``resolve_document_expiry``，Sprint 10.5 R4-b 的取值源）。
#: **只有正文自称条款逐字写了**才允许有值 ⇒ 四份现行制度必须是 ``None``；
#: 若现行制度这里出现非空，意味着把「正文里别处的日期」（如交叉引用里的旧日期）
#: 认领过来了，属**必须拦下**的错误。
EXPECTED_EXPIRY: dict[str, str | None] = {
    "attendance-policy-2025.md": "2025-12-31",
    "attendance-policy-2026.md": None,
    "fieldwork-attendance-rules-2025.md": "2025-12-31",
    "fieldwork-attendance-rules-2026.md": None,
    "overtime-and-comp-off.md": None,
    "worktime-system-rules.md": None,
}


def main() -> int:
    failures = 0
    for path in sorted(POLICIES.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        got, source = resolve_document_date(text=text)
        want = EXPECTED.get(path.name)
        got_str = got.isoformat() if got else "None"
        ok = want is None or want == got_str
        failures += 0 if ok else 1
        print(
            f"  [{'OK ' if ok else 'FAIL'}] {path.name:<40} "
            f"document_date = {got_str} (source={source})"
            + ("" if ok else f"  期望 {want}")
        )

        expiry, esource = resolve_document_expiry(text=text)
        want_expiry = EXPECTED_EXPIRY.get(path.name)
        got_expiry = expiry.isoformat() if expiry else "None"
        ok_expiry = got_expiry == (want_expiry or "None")
        failures += 0 if ok_expiry else 1
        print(
            f"  [{'OK ' if ok_expiry else 'FAIL'}] {path.name:<40} "
            f"expiry       = {got_expiry} (source={esource})"
            + ("" if ok_expiry else f"  期望 {want_expiry or 'None'}")
        )
    print(f"\n  失败 {failures} 项")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
