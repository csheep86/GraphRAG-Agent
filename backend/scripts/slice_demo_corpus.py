"""Sprint 8 批次 D（收尾补做）：**种子语料切片脚本化**（¥0，纯本地 CPU）。

闭合 `docs/demo-seed-dataset.md` §5 限制 3——原先切片由**一次性脚本 + 外部工具**
（`qpdf` / `pdftk`）产生，「无一键脚本」被登记为降级项。本脚本用 **pypdf**（dev 依赖组，
非运行时依赖）把 §3 的页范围规则固化成可复现命令。

用法（工作目录任意）：

    uv run python scripts/slice_demo_corpus.py                      # 切到默认输出目录
    uv run python scripts/slice_demo_corpus.py --out-dir /tmp/parts # 指定输出
    uv run python scripts/slice_demo_corpus.py --json report.json

退出码：**0** = 全部校验通过／**1** = 有 FAIL／**2** = 原件缺失或依赖未装。

口径与限制（**如实登记，不粉饰**）：

- **页范围与文件名**来自 `docs/demo-seed-dataset.md` §2 / §3，文件名**一个字都不能改**——
  `documents.filename_hash = SHA-256(切片文件名)`，改名就与现库对不上；
- **内容哈希与 qpdf 产物不同**：不同工具对 PDF 的**重编码**结果不同（原 §5 限制 2）。
  因此脚本**只保证**：页数吻合、`filename_hash` 与现库一致、**内容哈希以本次输出为准**
  （记录进 `--json` 报告，供重建后复核）；
- **不做上传 / 建图**：那一步烧 MinerU + LLM 且会写库，属 §4 的重建步骤，不由本脚本代做；
- pypdf 缺失 ⇒ 退出码 2 并提示 `uv add --group dev pypdf`，**不静默降级**。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 原件清单（抄自 `docs/demo-seed-dataset.md` §2；页数与内容 SHA-256 用于**前置校验**）。
SOURCES: tuple[dict[str, Any], ...] = (
    {
        "prefix": "招商公路",
        "file": "招商公路：招商局公路网络科技控股股份有限公司2024年面向专业投资者公开发行科技创新公司债券（第一期）募集说明书.pdf",
        "pages": 290,
        "sha256": "ed7b3637a71e28170e46b0af45dbc5134d9d694ff098c38e7780fbd047b99eda",
    },
    {
        "prefix": "招商蛇口",
        "file": "招商蛇口：招商局蛇口工业区控股股份有限公司2024年面向专业投资者公开发行公司债券（第一期）募集说明书.pdf",
        "pages": 314,
        "sha256": "48c1bba15097c8559de665cd7aa28ac29fcfa1a8dd6f9feabacfd5a79f3fb2b4",
    },
    {
        "prefix": "招商轮船",
        "file": "招商轮船：招商轮船2025年年度报告.pdf",
        "pages": 246,
        "sha256": "3fe6f99980f9f0c2ac241e2f826660141d118af2fe53eafab49e146ef9464a18",
    },
)

#: 切分规则（§3）：每份原件切两段 —— `p1-190` 与 `p191-<末页>`。
SPLIT_AT = 190

#: 现库 `filename_hash = SHA-256(切片文件名)` 的**前缀 8 / 后缀 5**（§3 表，用于校验文件名未被改）。
RECORDED_NAME_HASHES: dict[str, tuple[str, str]] = {
    "招商公路_p1-190.pdf": ("9b34558c", "f7685"),
    "招商公路_p191-290.pdf": ("8490c145", "30c94"),
    "招商蛇口_p1-190.pdf": ("f505a7b9", "caca7f"),
    "招商蛇口_p191-314.pdf": ("dbb287ae", "b39c30c"),
    "招商轮船_p1-190.pdf": ("517f5b27", "d5215"),
    "招商轮船_p191-246.pdf": ("fceaf500", "286a5"),
}


@dataclass
class Row:
    """一行结果（同时用于打印与 JSON 报告）。"""

    name: str
    status: str  # PASS / FAIL
    detail: str
    pages: int = 0
    size: int = 0
    sha256: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _name_hash(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="演示种子语料按页切片（¥0）")
    parser.add_argument(
        "--source-dir",
        default=str(REPO_ROOT / "docs" / "annualreport"),
        help="原件目录（默认 docs/annualreport）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(
            REPO_ROOT / "backend" / "storage" / "demo-slice" / "parts-scripted"
        ),
        help="切片输出目录（默认 storage/demo-slice/parts-scripted）",
    )
    parser.add_argument("--json", dest="json_path", default=None, help="报告输出路径")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("缺少 pypdf：uv add --group dev 'pypdf>=5.0,<6.0'", file=sys.stderr)
        return 2

    # pypdf 对部分原件会刷「Ignoring wrong pointing object」告警（无损、但刷屏）。
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    source_dir = Path(args.source_dir)
    out_dir = Path(args.out_dir)
    rows: list[Row] = []

    for source in SOURCES:
        path = source_dir / source["file"]
        if not path.is_file():
            rows.append(Row(f"{source['prefix']}（原件）", "FAIL", f"未找到：{path}"))
            continue
        digest = _sha256(path)
        if digest != source["sha256"]:
            rows.append(
                Row(
                    f"{source['prefix']}（原件）",
                    "FAIL",
                    f"内容哈希不符：现 {digest[:16]}… ≠ 记录 {source['sha256'][:16]}…",
                )
            )
            continue
        reader = PdfReader(str(path))
        if len(reader.pages) != source["pages"]:
            rows.append(
                Row(
                    f"{source['prefix']}（原件）",
                    "FAIL",
                    f"页数 {len(reader.pages)} ≠ 记录 {source['pages']}（页范围会错位）",
                )
            )
            continue
        rows.append(
            Row(
                f"{source['prefix']}（原件）",
                "PASS",
                f"页数 {len(reader.pages)} 与哈希均一致",
            )
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        total = source["pages"]
        ranges = [(1, SPLIT_AT), (SPLIT_AT + 1, total)]
        for start, end in ranges:
            name = f"{source['prefix']}_p{start}-{end}.pdf"
            writer = PdfWriter()
            for index in range(start - 1, end):
                writer.add_page(reader.pages[index])
            target = out_dir / name
            with target.open("wb") as handle:
                writer.write(handle)

            size = target.stat().st_size
            content_hash = _sha256(target)
            name_hash = _name_hash(name)
            recorded = RECORDED_NAME_HASHES.get(name)
            if recorded and not (
                name_hash.startswith(recorded[0]) and name_hash.endswith(recorded[1])
            ):
                rows.append(
                    Row(
                        name,
                        "FAIL",
                        f"filename_hash 与现库不符：{name_hash[:8]}…{name_hash[-5:]}",
                        pages=end - start + 1,
                        size=size,
                        sha256=content_hash,
                    )
                )
                continue
            rows.append(
                Row(
                    name,
                    "PASS",
                    f"p{start}-{end} filename_hash={name_hash[:8]}…{name_hash[-5:]} 与现库一致",
                    pages=end - start + 1,
                    size=size,
                    sha256=content_hash,
                )
            )

    for row in rows:
        print(f"[{row.status:4}] {row.name}: {row.detail}")
        if row.sha256:
            print(f"       页数={row.pages} 字节={row.size} sha256={row.sha256}")

    failed = sum(1 for r in rows if r.status == "FAIL")
    print(f"\n切片结束：PASS {len(rows) - failed} / FAIL {failed}；输出目录：{out_dir}")
    print(
        "注意：内容哈希与 qpdf 产物不同（工具重编码），以本次输出为准；文件名不变 ⇒ 落库口径一致。"
    )

    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([r.__dict__ for r in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"报告已写入：{path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
