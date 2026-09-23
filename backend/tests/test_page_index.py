"""页码索引单元测试（Sprint 6 批次 A-2）。

覆盖 :mod:`app.services.parsing.page_index`：

1. ``page_idx`` **0-based → 1-based**（实测：MinerU ``content_list.json`` 从 0 计）；
2. 完整文本命中 → 区间与页码正确；
3. 退化匹配（前 ``probe_chars`` 字符）→ 段落被改写时仍可定位；
4. 完全失配 → **跳过该段**（不给假页码），``coverage`` 反映命中率；
5. ``locate`` 边界：半开区间、区间外 → ``None``；
6. **真实 MinerU 产物实测**（``mineru_mvp/output/complex_table/``，产物缺失则 skip）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.parsing.page_index import build_page_index

#: 真实 MinerU 产物目录（repo 根 → mineru_mvp/output/complex_table）
_REAL_ARTIFACTS = (
    Path(__file__).resolve().parents[2] / "mineru_mvp" / "output" / "complex_table"
)


def test_page_idx_is_converted_to_one_based() -> None:
    """``page_idx`` 从 0 计（实测），对外一律 +1 成 1-based 页码。"""
    markdown = "第一页内容。\n\n第二页内容。"
    content_list = [
        {"page_idx": 0, "text": "第一页内容。"},
        {"page_idx": 1, "text": "第二页内容。"},
    ]

    index = build_page_index(markdown, content_list)

    assert index.locate(0) == 1
    assert index.locate(markdown.index("第二页内容。")) == 2


def test_full_text_match_builds_span() -> None:
    """完整命中的段落：区间为 ``[pos, pos + len(text))``，页码来自该段。"""
    markdown = "甲方：北京青云科技有限公司。"
    content_list = [{"page_idx": 3, "text": "北京青云科技有限公司"}]

    index = build_page_index(markdown, content_list)

    assert index.matched == 1
    assert index.total == 1
    assert index.coverage == 1.0
    assert index.locate(markdown.index("北京青云")) == 4


def test_probe_fallback_locates_partially_rewritten_segment() -> None:
    """段落被表格改写（全文对不上）→ 退化用前 60 字符定位，仍给真实页码。"""
    body = "营收数据" * 20  # 80 字符，> probe_chars(60)
    markdown = body + "改写"
    content_list = [{"page_idx": 1, "text": body + "附注说明"}]

    index = build_page_index(markdown, content_list, probe_chars=60)

    assert index.matched == 1
    assert index.locate(0) == 2
    # 被改写的尾部不在任何已知区间内 → None（不猜页码）
    assert index.locate(len(body)) is None


def test_unmatched_segment_is_skipped_not_guessed() -> None:
    """完全失配 → 不进索引（宁可没有页码，也不造一个错的）。"""
    markdown = "真实存在的段落。"
    content_list = [
        {"page_idx": 0, "text": "真实存在的段落。"},
        {"page_idx": 1, "text": "在 full.md 里被整段改写掉的表格"},
    ]

    index = build_page_index(markdown, content_list)

    assert index.total == 2
    assert index.matched == 1
    assert index.coverage == 0.5
    assert len(index.spans) == 1
    assert index.locate(len(markdown) + 5) is None


def test_locate_boundary_is_half_open() -> None:
    """区间为半开 ``[start, end)``：``end`` 本身不属于该段（避免跨段误判）。"""
    markdown = "ABCD"
    content_list = [{"page_idx": 0, "text": "AB"}, {"page_idx": 1, "text": "CD"}]

    index = build_page_index(markdown, content_list)

    assert index.locate(1) == 1
    assert index.locate(2) == 2
    # 负偏移 / 越界 → None
    assert index.locate(-1) is None
    assert index.locate(999) is None


def test_empty_or_invalid_content_list_yields_empty_index() -> None:
    """空 / 无 text / ``page_idx`` 非法 → 空索引，``locate`` 恒 ``None``（不抛错）。"""
    markdown = "任意正文"

    empty = build_page_index(markdown, [])
    assert empty.total == 0
    assert empty.coverage == 0.0
    assert empty.locate(0) is None

    no_text = build_page_index(markdown, [{"page_idx": 0, "text": "   "}])
    assert no_text.total == 0
    assert no_text.locate(0) is None

    bad_page = build_page_index(markdown, [{"page_idx": "x", "text": "任意正文"}])
    assert bad_page.total == 1
    assert bad_page.matched == 0
    assert bad_page.locate(0) is None


def test_v2_page_list_structure_uses_outer_index_as_page() -> None:
    """云 API 的 v2 结构：顶层是**页列表**，外层索引即页码（实测差异 2）。

    块内无 ``page_idx``，文本在 ``content.*_content`` 的 ``type=text`` 叶子里。
    """
    markdown = "# 第一页标题\n\n第一页正文。\n\n第二页正文。"
    content_list_v2 = [
        [  # 第 1 页
            {
                "type": "title",
                "content": {
                    "title_content": [{"type": "text", "content": "第一页标题"}],
                    "level": 1,
                },
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [{"type": "text", "content": "第一页正文。"}]
                },
            },
        ],
        [  # 第 2 页
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [{"type": "text", "content": "第二页正文。"}]
                },
            },
        ],
    ]

    index = build_page_index(markdown, content_list_v2)

    assert (
        index.locate_range(markdown.index("第一页标题"), markdown.index("第二页正文。"))
        == 1
    )
    assert index.locate_range(markdown.index("第二页正文。"), len(markdown)) == 2


def test_v2_table_block_without_text_is_skipped() -> None:
    """表格块（``content.html``，无 ``type=text`` 叶子）→ 取不到文本，不参与对齐。"""
    markdown = "正文段落。"
    content_list_v2 = [
        [
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [{"type": "text", "content": "正文段落。"}]
                },
            },
            {
                "type": "table",
                "content": {"html": "<table><tr><td>x</td></tr></table>"},
            },
        ]
    ]

    index = build_page_index(markdown, content_list_v2)

    # total 只统计「取得到文本」的块；表格块不算失配（本来就无法对齐）
    assert index.total == 1
    assert index.matched == 1
    assert index.locate_range(0, len(markdown)) == 1


def test_locate_range_uses_overlap_not_start_point() -> None:
    """按重叠判页：chunk 起点落在「首段之前的空白」时仍应拿到正确页码。

    真机实测（Sprint 6 批次 A）：单 chunk 区间 ``[0, 764)``，而首个对齐段起点为 2
    → ``locate(0)`` 返回 ``None``，但按重叠应判为第 1 页。
    """
    markdown = "\n\n第一页正文内容"
    content_list = [{"page_idx": 0, "text": "第一页正文内容"}]

    index = build_page_index(markdown, content_list)

    assert index.locate(0) is None  # 单点查询：0 不在任何已知区间内
    assert index.locate_range(0, len(markdown)) == 1  # 区间重叠：第 1 页


def test_locate_range_returns_none_without_overlap() -> None:
    """与所有已知段都不重叠（整段未对齐 / 空区间）→ ``None``，不猜页码。"""
    markdown = "已知段落"
    content_list = [{"page_idx": 0, "text": "已知段落"}]

    index = build_page_index(markdown, content_list)

    assert index.locate_range(0, 2) == 1
    assert index.locate_range(100, 200) is None
    assert index.locate_range(5, 5) is None
    assert index.locate_range(5, 1) is None


def test_real_mineru_artifacts_alignment() -> None:
    """**实测反哺**：用真实 MinerU 产物验证「文本顺序对齐」可行（T0 实测 10/10）。

    同时固化两条实测事实，防止日后有人误以为可以从 markdown 直接取页码：
    - ``full.md`` **不含**任何页分隔标记；
    - ``content_list.json`` 的 ``page_idx`` 存在且从 0 计。
    """
    markdown_path = _REAL_ARTIFACTS / "full.md"
    candidates = sorted(_REAL_ARTIFACTS.glob("*_content_list.json"))
    if not markdown_path.exists() or not candidates:
        pytest.skip(f"真实 MinerU 产物缺失：{_REAL_ARTIFACTS}")

    markdown = markdown_path.read_text(encoding="utf-8")
    content_list: list[dict[str, Any]] = json.loads(
        candidates[0].read_text(encoding="utf-8")
    )

    # 实测绘绘：full.md 无页标记 → 判页只能靠 content_list 对齐
    assert "<!--" not in markdown
    assert any(isinstance(item, dict) and "page_idx" in item for item in content_list)

    index = build_page_index(markdown, content_list)
    text_items = [
        item
        for item in content_list
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]

    assert index.total == len(text_items)
    assert index.matched == index.total, (
        f"对齐命中率退化：{index.matched}/{index.total}（coverage={index.coverage}）"
    )
    assert index.coverage == 1.0
    # 单页样例：page_idx=0 → 页码 1
    assert index.locate(index.spans[0].char_start) == 1
    # 首段之前的空白（full.md 开头的换行等）不在已知区间 → None（不猜页码）
    assert index.locate(0) is None or index.spans[0].char_start == 0
