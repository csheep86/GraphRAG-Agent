# -*- coding: utf-8 -*-
"""由 03-技术规格说明书.md 生成同名 .docx。

用法（在 backend/ 下执行，依赖经 uv 临时环境安装，不污染项目依赖）：
    cd backend
    uv run --with python-docx python ..\\delivery-kit\\scripts\\build_tech_docx.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from md_to_docx import convert  # noqa: E402

ROOT = HERE.parents[1]
SRC = ROOT / "delivery-kit" / "03-技术规格说明书.md"
DST = ROOT / "delivery-kit" / "03-技术规格说明书.docx"


def main() -> int:
    if not SRC.exists():
        print(f"[FAIL] 源文件不存在: {SRC}")
        return 1
    convert(SRC, DST, title="GraphRAG-Agent 技术规格说明书")

    # 顺带核对产物确实可打开且非 0 字节
    if not DST.exists() or DST.stat().st_size == 0:
        print(f"[FAIL] 产物异常: {DST}")
        return 1
    print(f"     体积 {DST.stat().st_size / 1024:.1f} KB ｜ 由 Markdown 转换")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
