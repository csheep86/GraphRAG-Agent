"""只重新生成 DOCX，不碰 CSV。

``generate_corpus.main()`` 会把 9 张业务表也一并重写；本批 Neo4j 的 CSV 侧已按
现有产物建成，没必要让重跑去动它们（且只有这 4 份 policy 的 md 被改动）。
这里复用脚本自己的 ``md_to_docx`` 保证字节口径一致，并报告哪几份真的变了。
"""

from __future__ import annotations

import sys
from pathlib import Path

DEMO_ATTENDANCE = Path(__file__).resolve().parents[2] / "demo" / "attendance"
if str(DEMO_ATTENDANCE) not in sys.path:
    sys.path.insert(0, str(DEMO_ATTENDANCE))

import generate_corpus as gc  # noqa: E402


def main() -> int:
    changed = 0
    print("只重新生成 DOCX（不动 CSV，避免污染已入库的业务数据）:")
    for md in sorted(gc.POLICIES_DIR.glob("*.md")):
        payload = gc.md_to_docx(md.read_text(encoding="utf-8"))
        out = gc.OUT_DIR / f"{md.stem}.docx"
        before = out.read_bytes() if out.exists() else b""
        if before == payload:
            print(f"  [无变化] {out.name}")
            continue
        out.write_bytes(payload)
        changed += 1
        print(f"  [已更新] {out.name:<40} {len(before)} -> {len(payload)} 字节")
    print(f"\n共更新 {changed} 份 DOCX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
