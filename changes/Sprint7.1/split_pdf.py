"""Sprint 7.1 批次 A：按 **MinerU 云解析 200 页上限**拆分演示素材（零成本，不调 LLM）。

真机依据（2026-09-23，`document.parse` 三份素材均 failed）：

```
app.services.parsing.mineru.MineruApiError: 解析失败:
number of pages exceeds limit (200 pages), please split the file and try again
```

拆分是**按真实页码切分原 PDF**，不改动任何页面内容、不合成新内容——产物仍是原始
公开披露材料本身（与「编数据」无关）。落盘目录 ``backend/storage/demo-slice/``
（已被 .gitignore 忽略）。

用法（工作目录 = ``backend/``，pypdf 走临时依赖、不污染项目 pyproject）：

```powershell
uv run --with pypdf python ../changes/Sprint7.1/split_pdf.py --pdf ../docs/annualreport/xxx.pdf --max-pages 190
```
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

OUT_DIR = BACKEND_DIR / "storage" / "demo-slice" / "parts"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _short_stem(pdf: Path) -> str:
    """取文件名里能标识公司的短前缀（原名过长，落盘后不便阅读）。"""
    name = pdf.stem
    for marker in ("：", ":", "招商"):
        if marker in name and marker != "招商":
            name = name.split(marker)[0]
            break
    # 去掉书名号里超长正文，保留「公司名 + 材料类型」的辨识度
    return name[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description="按 MinerU 页上限拆分 PDF")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=190,
                        help="每个分片的最大页数（<200，留安全边界）")
    args = parser.parse_args()

    pdf: Path = args.pdf
    if not pdf.is_file():
        print(f"[FAIL] 文件不存在: {pdf}", file=sys.stderr)
        return 1

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(pdf))
    total = len(reader.pages)
    stem = _short_stem(pdf)
    print(f"pdf={pdf.name}")
    print(f"pages={total} max_pages={args.max_pages}")

    parts: list[tuple[int, int, Path]] = []
    for start in range(0, total, args.max_pages):
        end = min(start + args.max_pages, total)
        writer = PdfWriter()
        for index in range(start, end):
            writer.add_page(reader.pages[index])
        # 1-based 页码（与 PDF 阅读器一致，便于人工核对证据）
        out = OUT_DIR / f"{stem}_p{start + 1}-{end}.pdf"
        with out.open("wb") as handle:
            writer.write(handle)
        print(f"  part={out.name} pages={start + 1}-{end} "
              f"({out.stat().st_size / 1_048_576:.2f} MB)")
        parts.append((start + 1, end, out))
    print(f"parts={len(parts)} out_dir={OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
