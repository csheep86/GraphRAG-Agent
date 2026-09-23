"""Sprint 7.0 补充验证：募集说明书**定向切片预处理**（不调用 LLM，零成本）。

背景：Sprint 7.0 §4 真机结论 D6② 为「零交叉」（年报天然只披露一家公司）。
本脚本用于评估**替代素材**——公司债募集说明书（会披露发行人 / 控股股东 /
实际控制人 / 重要子公司的名称 + 法定代表人 + 住所）。

两个子命令：
- ``scan``  ——扫描关键词命中的页码分布（零成本，用于选切片范围）
- ``slice`` ——按页码区间生成切片文本，供 ``verify_slice.py`` 消费

用法（工作目录 = ``backend/``，pypdf 走临时依赖、不污染项目 pyproject）：

```powershell
uv run --with pypdf python ../changes/Sprint7.0/slice_prospectus.py scan  --pdf ../docs/annualreport/xxx.pdf
uv run --with pypdf python ../changes/Sprint7.0/slice_prospectus.py slice --pdf ../docs/annualreport/xxx.pdf --pages 1-20
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
SLICE_DIR = BACKEND_DIR / "storage" / "demo-slice"
SLICE_DIR.mkdir(parents=True, exist_ok=True)

#: 定位「多主体法人 / 住所」所在章节的探针
PROBE_KEYWORDS: tuple[str, ...] = (
    "法定代表人",
    "控股股东",
    "实际控制人",
    "注册地址",
    "办公地址",
    "子公司",
)


def _cache_path(pdf: Path) -> Path:
    return SLICE_DIR / f"{pdf.stem}.pages.json"


def _load_pages(pdf: Path) -> list[str]:
    cache = _cache_path(pdf)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    pages = [(page.extract_text() or "") for page in reader.pages]
    cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def _scan(pdf: Path, top: int) -> int:
    pages = _load_pages(pdf)
    print(f"pdf={pdf.name} pages={len(pages)}")

    for keyword in PROBE_KEYWORDS:
        hits = [i + 1 for i, text in enumerate(pages) if keyword in text]
        shown = hits[:top]
        suffix = " ..." if len(hits) > top else ""
        print(f"  {keyword:<8} 命中 {len(hits):>3} 页  前 {top}: {shown}{suffix}")

    print("\n--- 疑似「发行人 / 股东 / 子公司」章节页（含 ≥3 个关键词）---")
    for i, text in enumerate(pages):
        score = sum(1 for k in PROBE_KEYWORDS if k in text)
        if score >= 3:
            head = re.sub(r"\s+", " ", text)[:60]
            print(f"  p{i + 1:<4} score={score}  {head}")
    return 0


def _slice(pdf: Path, pages: str) -> int:
    pages_loaded = _load_pages(pdf)
    start_s, _, end_s = pages.partition("-")
    start = int(start_s)
    end = int(end_s or start_s)
    text = "\n".join(pages_loaded[start - 1 : end])

    out = SLICE_DIR / f"{pdf.stem[:24]}_p{start}-{end}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"written={out} chars={len(text)} pages={start}-{end}")
    print(f"预估 chunk 数（1200 字/chunk）≈ {len(text) // 1200 + 1}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="募集说明书定向切片预处理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--pdf", type=Path, required=True)
    p_scan.add_argument("--top", type=int, default=25)

    p_slice = sub.add_parser("slice")
    p_slice.add_argument("--pdf", type=Path, required=True)
    p_slice.add_argument("--pages", required=True, help="形如 12-30")

    args = parser.parse_args()
    pdf: Path = args.pdf
    if not pdf.exists():
        print(f"PDF 不存在: {pdf}", file=sys.stderr)
        return 1

    if args.cmd == "scan":
        return _scan(pdf, args.top)
    return _slice(pdf, args.pages)


if __name__ == "__main__":
    raise SystemExit(main())
