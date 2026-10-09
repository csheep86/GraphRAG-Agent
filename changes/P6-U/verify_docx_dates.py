"""重抽前的免费预检：确认 4 份 2026 docx 里真的带着逐条施行日期。

不验就跑重抽 = 拿 ¥ 换一次"我以为改对了"。直接读 docx 的 word/document.xml，
数目标句式的出现次数；顺便对照 md 的行数，两边必须对得上。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "demo" / "attendance" / "corpus"
POLICIES = Path(__file__).resolve().parents[2] / "demo" / "attendance" / "policies"

TARGETS = (
    "attendance-policy-2026",
    "fieldwork-attendance-rules",
    "overtime-and-comp-off",
    "worktime-system-rules",
)

SENTENCE = "本条自 2026 年 1 月 1 日起施行"
CLAUSE_RE = re.compile(r"^第[一二三四五六七八九十]+条\s", re.M)


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    return "\n".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def main() -> int:
    print("2026 版语料生效日预检（doc vs md 必须对得上）")
    print(f"{'文件':<32}{'docx条数':>9}{'docx含日期':>11}{'md条数':>8}{'md含日期':>9}")
    all_ok = True
    for stem in TARGETS:
        docx = CORPUS / f"{stem}.docx"
        md = POLICIES / f"{stem}.md"
        text = docx_text(docx)
        md_text = md.read_text(encoding="utf-8")
        d_clause = len(CLAUSE_RE.findall(text))
        d_date = text.count(SENTENCE)
        m_clause = len(CLAUSE_RE.findall(md_text))
        m_date = md_text.count(SENTENCE)
        ok = d_clause > 0 and d_date == d_clause and d_date == m_date
        all_ok = all_ok and ok
        print(
            f"{stem:<32}{d_clause:>9}{d_date:>11}{m_clause:>8}{m_date:>9}"
            f"{'' if ok else '   <== 不一致'}"
        )
    print()
    print("结论：" + ("OK，可以开抽" if all_ok else "不一致，先别烧钱"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
