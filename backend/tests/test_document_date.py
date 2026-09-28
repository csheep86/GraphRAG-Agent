"""`app.services.parsing.document_date` 的行为契约。

重点不是"能解析出多少种格式"，而是**什么时候必须说 None**——解析错了会把
一个编出来的生效日写进关系，比不解析更糟（R4 纪律）。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.parsing.document_date import (
    SOURCE_EXPLICIT,
    SOURCE_NONE,
    resolve_document_date,
)

#: 固定"今天"，让年份上限判定可复现
TODAY = date(2026, 9, 28)


def resolve(text: str, explicit: date | None = None):
    return resolve_document_date(text=text, explicit=explicit, today=TODAY)


@pytest.mark.parametrize(
    ("text", "expected", "source"),
    [
        ("本报告期：2025年6月30日 的主要财务数据如下", date(2025, 6, 30), "text:ymd"),
        ("披露日期: 2025-06-30", date(2025, 6, 30), "text:ymd"),
        ("截至 2025/06/30，公司注册资本为", date(2025, 6, 30), "text:ymd"),
        ("报告期：2025年6月", date(2025, 6, 30), "text:ym"),
        ("报告期：2025年度", date(2025, 12, 31), "text:year"),
        ("审计日期2025年2月（未经审计）", date(2025, 2, 28), "text:ym"),
    ],
)
def test_recognizes_documented_date(text: str, expected: date, source: str) -> None:
    assert resolve(text) == (expected, source)


def test_explicit_wins_over_text() -> None:
    """人工指定优先：正文再像也不覆盖人给的值。"""
    given = date(2024, 1, 1)
    assert resolve("报告期：2025年6月30日", explicit=given) == (given, SOURCE_EXPLICIT)


@pytest.mark.parametrize(
    "text",
    [
        "",  # 空文本
        "本公司成立于 2018 年 3 月，注册资本 5000 万元",  # 有日期但**无出处**
        "公司与 A 公司于 2023 年 5 月 1 日签署协议",  # 签署的是协议，不是本文档日期
        "报告期：二〇二五年六月三十日",  # 中文数字日期：识别不了就 None，不猜
    ],
)
def test_returns_none_when_not_confident(text: str) -> None:
    assert resolve(text) == (None, SOURCE_NONE)


def test_invalid_calendar_date_is_none_not_coerced() -> None:
    """2025-02-30 不存在 ⇒ None，**不就近修正**成 2-28（那是在编数据）。"""
    assert resolve("报告期：2025年2月30日") == (None, SOURCE_NONE)


def test_far_future_year_is_rejected_as_noise() -> None:
    assert resolve("报告期：2099年度") == (None, SOURCE_NONE)


def test_gap_does_not_span_sentences() -> None:
    """关键词与日期之间只允许标点/空白；跨句认领会张冠李戴。"""
    text = "报告期内的重大事项详见附注。公司于 2024 年 3 月 5 日完成工商变更。"
    assert resolve(text) == (None, SOURCE_NONE)
