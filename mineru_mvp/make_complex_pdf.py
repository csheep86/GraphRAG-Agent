# -*- coding: utf-8 -*-
"""生成一个复杂 PDF（含标题、说明文字、4 列 5 行数据表格、摘要列表），
作为 MinerU 解析 MVP 的测试输入。

用法（在 mineru_mvp/ 目录下）:
    uv run python make_complex_pdf.py
输出: input/complex_table.pdf
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# 注册内置 CID 中文字体（无需外部字体文件）
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
FONT = "STSong-Light"

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_PDF = INPUT_DIR / "complex_table.pdf"

TITLE = "2025 年度集团经营指标分析报告"
SUBTITLE = "编制单位：战略发展部    数据截至：2025 年 12 月 31 日"
INTRO = (
    "本报告汇总了集团五大核心业务板块在 2025 年度的营业收入、净利润、同比增速等关键经营指标，"
    "用于评估各板块的增长质量与盈利能力。表中所有金额均为人民币万元，同比增幅为与 2024 年度相比的百分比变化。"
)

# 4 列 x 5 行数据表格（数值 + 百分比），另有表头
TABLE_DATA = [
    ["业务板块", "营业收入（万元）", "净利润（万元）", "同比增幅（%）"],
    ["智能制造", "128,560", "18,420", "23.5%"],
    ["数字服务", "96,380", "15,730", "38.2%"],
    ["供应链物流", "74,120", "6,850", "11.7%"],
    ["新能源", "52,940", "9,610", "67.4%"],
    ["海外贸易", "31,250", "2,480", "-8.3%"],
]

SUMMARY_ITEMS = [
    "智能制造与数字服务两大板块合计贡献集团营业收入的 62.3%，仍是核心增长引擎。",
    "新能源板块同比增幅达 67.4%，增速最快，但营收基数仍较小，处于投入扩张期。",
    "海外贸易板块收入同比下滑 8.3%，主要受国际需求波动及汇率影响。",
    "集团整体净利润率为 14.1%，较上年度提升 1.6 个百分点。",
]

STYLES = {
    "title": ParagraphStyle(
        "title", fontName=FONT, fontSize=18, alignment=1, spaceAfter=6
    ),
    "subtitle": ParagraphStyle(
        "subtitle", fontName=FONT, fontSize=10, alignment=1, textColor=colors.grey
    ),
    "h2": ParagraphStyle(
        "h2", fontName=FONT, fontSize=13, spaceBefore=14, spaceAfter=6
    ),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=10.5, leading=16),
    "li": ParagraphStyle(
        "li", fontName=FONT, fontSize=10.5, leading=16, leftIndent=14, bulletIndent=4
    ),
}


def build() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=TITLE,
    )

    story = [
        Paragraph(TITLE, STYLES["title"]),
        Paragraph(SUBTITLE, STYLES["subtitle"]),
        Spacer(1, 10),
        Paragraph("一、报告说明", STYLES["h2"]),
        Paragraph(INTRO, STYLES["body"]),
        Paragraph("二、各板块经营指标", STYLES["h2"]),
    ]

    table = Table(TABLE_DATA, colWidths=[42 * mm, 42 * mm, 42 * mm, 42 * mm])
    table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8496B0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EDF1F8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(table)

    story.append(Paragraph("三、要点摘要", STYLES["h2"]))
    for item in SUMMARY_ITEMS:
        story.append(Paragraph(item, STYLES["li"], bulletText="•"))

    doc.build(story)
    print(f"PDF 已生成: {OUTPUT_PDF}")


if __name__ == "__main__":
    build()
