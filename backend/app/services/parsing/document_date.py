"""文档**业务日期**的解析（ADR-0005 §4：关系 ``valid_from`` 的兜底源）。

为什么要有这个模块
------------------
``documents.document_date`` 列已落地，抽取侧（`tasks/registry.py`）和问答侧
（`services/agents.py`）都在读它，但**没有任何写入路径**——实测 13 份文档
**无一**有日期，于是抽取恒渲染 ``unknown``、问答的「依据截至哪天」恒答不上来。

本模块提供写入路径的两档来源，优先级固定：

1. **人工指定**（上传接口的可选字段）——人说的算，解析只在它缺席时登场；
2. **正文解析**（本模块）——只在**高置信**模式命中时填写。

纪律（与抽取侧 R4 同口径）：**认不出就返回 ``None``**，不猜、不用"今天"兜底。
假日期比没日期危险得多：它会让关系带上一个看起来很确定、实际是编出来的生效日，
而 ``unknown`` 至少会在答案里如实表现为「说不清」。

**文件名不参与解析**：库里只落 ``filename_hash``（M5 §4.5 禁原文），
没有文件名可解析——这不是偷懒，是数据本身不在。

解析到的三种粒度与约定（都记在返回的 ``source`` 里，供日志追溯）：

- 精确到日：``2025年6月30日`` / ``2025-06-30`` → 该日；
- 精确到月：``2025年6月`` → **该月最后一天**（报告期取期末，不是期初）；
- 精确到年：``2025年度`` → **12-31**（财年期末）。

后两条是**约定**而非事实，因此必须由人工指定覆盖——这也是上传接口那个
可选字段存在的理由之一。

--------------------------------------------------------------------------
2026-09-30 追加（Sprint 10.4 批次 A）：**后置锚点**——制度类文档的第二类写法
--------------------------------------------------------------------------
上一版只认「关键词在前、日期在后」（``披露日期：2025-06-30``）。实测演示语料
``demo/attendance/policies/*.md`` **4/4 认不出**，但四份文档**都有日期**，写法是
**日期在前**：``第十三条 本制度自 2026 年 1 月 1 日起施行。``
⇒ 词表再多也救不了形式不对——这是实证，不是猜测。

因此新增**后置锚点**（``日期 + 间隔 + 关键词``）与它配套的词表：

- 认：``施行`` / ``实施`` / ``生效`` / ``发布`` / ``颁布`` / ``印发`` / ``通过`` / ``修订``；
- **不认** ``废止``：「《某规定（2025 版）》同时废止」说的是**另一份文档**
  什么时候结束，**不是本文档**的日期；把它认领过来等于给本文档编一个日期。

优先级保持「前置锚点 → 后置锚点」：已有行为**不变**，只补原来漏掉的一类。
两种形式共用同一条间隔纪律（``_GAP`` / ``_TAIL_GAP``）：关键词与日期之间
只允许极少量语气字符，禁止跨句认领。
"""

from __future__ import annotations

import calendar
import re
from datetime import date

#: 只有在这些词之后出现的日期才认：文档里的日期太多（成立日期、合同日期、
#: 其他公司的披露日…），**没有出处的日期一律不算文档日期**。
#: 这是"宁可 None"的具体落实——放宽这一条很容易，放错了却会让关系带上错生效日。
_DATE_KEYWORDS = (
    "报告期",
    "报告期间",
    "披露日期",
    "披露日",
    "签署日期",
    "签署日",
    "出具日期",
    "出具日",
    "公告日期",
    "公告日",
    "财务报表日",
    "资产负债表日",
    "审计日期",
    "截止",
    "截至",
)

#: 关键词与日期之间只允许这些字符（防止跨句 / 跨段把别人的日期认领过来）
_GAP = r"[：:\s，,、（(]{0,6}"

#: 后置锚点的日期与关键词之间只允许这些语气字符——同样是为了不跨句认领。
#: 典型形态：``2026 年 1 月 1 日起施行``（``起``）、``2025 年 6 月 30 日公布``（无）。
#: **句号 / 分号不在其列**：``……2026年1月1日。本办法自发布之日起施行`` 因此不被认领。
_TAIL_GAP = r"[起之\s，,、]{0,4}"

#: 后置锚点词表（**日期在前、关键词在后**）。
#: 只收「该日期就是本文档日期」的强信号词：施行 / 实施 / 生效 = 文档开始适用；
#: 发布 / 颁布 / 印发 = 文档对外发出的日子；通过 / 修订 = 审议动作落在本文档上。
#: **不含** ``废止``：那句话描述的是**另一份**旧文档何时结束（见模块 docstring）。
_TAIL_KEYWORDS = (
    "施行",
    "实施",
    "生效",
    "发布",
    "颁布",
    "印发",
    "通过",
    "修订",
)

#: 三类粒度，按精度从高到低；**先匹配到的先采用**
_YMD = r"(?P<y>\d{4})\s*[年\-/.]\s*(?P<m>\d{1,2})\s*[月\-/.]\s*(?P<d>\d{1,2})\s*日?"
_YM = r"(?P<y>\d{4})\s*[年\-/.]\s*(?P<m>\d{1,2})\s*月(?!\s*\d)"
_YEAR = r"(?P<y>\d{4})\s*年?\s*度"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("text:ymd", re.compile(_YMD)),
    ("text:ym", re.compile(_YM)),
    ("text:year", re.compile(_YEAR)),
)

#: 关键词 + 间隔 + 日期 的组合模式（逐个关键词生成，避免一条巨型正则难维护）
_HEAD_ANCHORED = tuple(
    (
        source,
        re.compile(f"{re.escape(keyword)}{_GAP}(?:{pattern.pattern})"),
    )
    for source, pattern in _PATTERNS
    for keyword in _DATE_KEYWORDS
)

#: 日期 + 间隔 + 关键词（后置锚点）。``source`` 加 ``_tail`` 后缀 ⇒ 日志能区分
#: 这个日期是"关键词带出来的"还是"句子句尾的施行日"。
_TAIL_ANCHORED = tuple(
    (
        f"{source}_tail",
        re.compile(f"(?:{pattern.pattern}){_TAIL_GAP}{re.escape(keyword)}"),
    )
    for source, pattern in _PATTERNS
    for keyword in _TAIL_KEYWORDS
)

#: 先前置、后后置：既有语料的行为**逐字不变**，只在原来漏掉的那类文档上新增命中。
_ANCHORED = _HEAD_ANCHORED + _TAIL_ANCHORED

#: 年份的可信区间下限（早于此视为解析噪声，如"成立于 1899 年"）
_MIN_YEAR = 1900
#: 年份上限：允许文档日期比"今天"晚一年（预算 / 计划书），再多就是噪声
_FUTURE_YEAR_MARGIN = 1

#: 来源标记（返回值第二部分）；``none`` 表示**没有认出来**——这是合法结果，不是错误
SOURCE_EXPLICIT = "explicit"
SOURCE_NONE = "none"


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _build(source: str, match: re.Match[str], *, max_year: int) -> date | None:
    """把正则匹配构造成 ``date``；**构造不出来返回 None**（如 2025-02-30）。"""
    # 后置锚点的 source 带 ``_tail`` 后缀，粒度判定看去掉后缀后的部分
    granularity = source.removesuffix("_tail")
    year = int(match.group("y"))
    if not _MIN_YEAR <= year <= max_year:
        return None
    if granularity == "text:year":
        return date(year, 12, 31)
    month = int(match.group("m"))
    if not 1 <= month <= 12:
        return None
    if granularity == "text:ym":
        return date(year, month, _last_day_of_month(year, month))
    try:
        return date(year, month, int(match.group("d")))
    except ValueError:
        # 2025-02-30 这类：宁可 None，也不"就近修正"成 2-28——那是在编数据
        return None


def resolve_document_date(
    *,
    text: str,
    explicit: date | None = None,
    today: date | None = None,
) -> tuple[date | None, str]:
    """定出文档的业务日期；返回 ``(日期, 来源)``，认不出时为 ``(None, "none")``。

    :param text: 文档正文（Markdown 即可，无需结构化）。
    :param explicit: 人工指定的日期（上传接口传入）；**非空则直接采用**，
        不做任何校验覆盖——人说的算。
    :param today: 仅用于计算年份上限（默认取系统当天，测试可注入）。
    """
    if explicit is not None:
        return explicit, SOURCE_EXPLICIT

    if not text:
        return None, SOURCE_NONE

    max_year = (today or date.today()).year + _FUTURE_YEAR_MARGIN
    for source, pattern in _ANCHORED:
        match = pattern.search(text)
        if match is None:
            continue
        built = _build(source, match, max_year=max_year)
        if built is not None:
            return built, source
    return None, SOURCE_NONE
