"""页码索引（Sprint 6 批次 A-2：把 ``full.md`` 的字符偏移还原成 PDF 页码）。

**实测依据（CODEBUDDY.md「实测结果反哺规则」）**——本机用
``mineru_mvp/output/complex_table/`` 的**真实 MinerU 产物**验证：

1. ``full.md`` **不含任何页分隔标记**（``<!-- -->`` 0 处、``page\\d+`` 正则 0 命中）
   → 页码**无法**从 markdown 文本直接读出；
2. ``content_list.json`` 每项形如
   ``{"bbox": [...], "page_idx": 0, "text": "...", "text_level": 1, "type": "text"}``，
   ``page_idx`` 存在且**从 0 计**（单页样例 distinct = ``[0]``）；
3. 按 ``content_list`` 的**文档顺序**用 ``text`` 在 ``full.md`` 上做游标 ``find``，
   **10 / 10 命中** → 「字符偏移 → 页码」的反查可行。

**云 API 实测（同一批次真机，Sprint 6 批次 A）**：``document.parse`` 走 MinerU 云 API
拿到的 ``content_list.json`` 是 **v2 结构**——顶层为**页列表嵌套条目列表**
``[[block, ...], [block, ...]]``（与 ``docs/mineru_cloud_api_spec.md`` §3.3
「实测差异 2」一致），块内**没有** ``page_idx``，文本藏在
``content.title_content`` / ``content.paragraph_content`` 的
``{"type": "text", "content": ...}`` 叶子节点里（递归取），
**页码 = 外层页列表索引 + 1**。故本模块同时支持 v1 / v2 两种形态。

结论：本模块是 **best-effort**——命中给真实页码（1-based），
**失配返回 ``None``**，由调用方按「该 chunk 无页码」处理。
**绝不**兜底成 1：假页码会让前端把高亮指到错误的页，比「没有页码」危险得多。

公开面：
- :func:`build_page_index`：``full.md`` + ``content_list.json`` → :class:`PageIndex`；
- :meth:`PageIndex.locate`：``char_offset -> int | None``。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PageSpan:
    """``full.md`` 上一段**已知页码**的字符区间（半开区间 ``[char_start, char_end)``）。"""

    char_start: int
    char_end: int
    page: int


@dataclass(frozen=True, slots=True)
class PageIndex:
    """字符偏移 → 页码（**1-based**）的只读索引。"""

    spans: tuple[PageSpan, ...] = ()
    #: ``content_list`` 中带 ``text`` 的条目总数（对齐分母）
    total: int = 0
    #: 成功对齐到 ``full.md`` 的条目数（命中率 = ``matched / total``）
    matched: int = 0

    #: 二分查找用的起点数组（构造时派生，不参与比较 / repr）
    _starts: tuple[int, ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # frozen + slots：只能用 object.__setattr__ 写派生字段
        object.__setattr__(
            self, "_starts", tuple(span.char_start for span in self.spans)
        )

    @property
    def coverage(self) -> float:
        """对齐命中率（0.0~1.0）；``total = 0`` 时为 ``0.0``。"""
        if self.total <= 0:
            return 0.0
        return round(self.matched / self.total, 4)

    def locate(self, char_offset: int) -> int | None:
        """返回 ``char_offset`` 所在页码（1-based）；落在未知区间 → ``None``。

        落在**两个已知区间之间**（即该段未对齐）时同样返回 ``None``——
        不猜「最近的已知页」，避免把相邻页的页码安到本段上。
        """
        if not self._starts or char_offset < 0:
            return None
        index = bisect.bisect_right(self._starts, char_offset) - 1
        if index < 0:
            return None
        span = self.spans[index]
        if span.char_start <= char_offset < span.char_end:
            return span.page
        return None

    def locate_range(self, char_start: int, char_end: int) -> int | None:
        """按**重叠度**判定区间 ``[char_start, char_end)`` 所属页码。

        为什么不直接用 ``locate(char_start)``：**实测（Sprint 6 批次 A 真机）**
        ``full.md`` 开头常有一段不属于任何 ``content_list`` 条目的空白 / 标题前缀，
        于是首个 chunk 的 ``char_start = 0`` 落不到任何 span 上 → ``locate()`` 返回
        ``None``，可该 chunk 明明完整覆盖第 1 页正文（真机实测即此例：单个 chunk
        区间 ``[0, 764)``，首个 span 起点为 2 → ``page = None``）。

        按「与已知页段落重叠最长者」判定即可修正；**完全不重叠**（该 chunk 整段
        都是未对齐的表格 / 空白）时仍返回 ``None``——不猜页码。
        """
        if char_end <= char_start or not self.spans:
            return None

        best_page: int | None = None
        best_overlap = 0
        for span in self.spans:
            if span.char_start >= char_end:
                break  # spans 按起点有序，后续不可能重叠
            overlap = min(char_end, span.char_end) - max(char_start, span.char_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_page = span.page
        return best_page


def build_page_index(
    markdown: str,
    content_list: list[dict[str, Any]],
    *,
    probe_chars: int = 60,
) -> PageIndex:
    """由 ``full.md`` 与 ``content_list.json`` 建页码索引。

    **两种产物形态都要支持**（实测：离线库与云 API 结构不同，见模块 docstring）：

    - **v1**（离线 ``mineru_mvp`` 实测）：扁平条目列表，每项带 ``page_idx``；
    - **v2**（云 API 实测，``docs/mineru_cloud_api_spec.md`` §3.3「实测差异 2」）：
      顶层为**页列表嵌套条目列表** ``[[item, ...], [item, ...]]``，
      **外层索引即页码**（0-based），条目文本在 ``content.title_content`` /
      ``content.paragraph_content`` 等嵌套路径里。

    对齐算法（与实测口径一致）：按文档顺序维护游标，用条目文本在 ``markdown``
    中从游标处 ``find``：

    - 完整文本命中 → 区间 ``[pos, pos + len(text))``；
    - 完整命中失败（该段被表格转 HTML 改写）→ 退化为用前 ``probe_chars`` 字符再找，
      命中则按探针长度记区间；
    - 仍失败 → **跳过该项**（记入未命中），不给它造页码。

    :param markdown: ``full.md`` 全文（``document.parse`` 产物）
    :param content_list: MinerU ``content_list.json`` 解析后的列表（v1 或 v2）
    :param probe_chars: 退化匹配的探针长度（``<= 0`` 表示不退化）
    """
    entries = _iter_paged_entries(content_list)

    spans: list[PageSpan] = []
    cursor = 0
    total = 0
    matched = 0

    for text, page in entries:
        if not text:
            continue
        total += 1
        if page is None:
            continue  # 页码不可知（v1 缺 page_idx）→ 记入未命中，不参与对齐

        pos = markdown.find(text, cursor)
        end = pos + len(text) if pos >= 0 else -1
        if pos < 0 and probe_chars > 0:
            # 退化匹配：该段在 full.md 中被改写，用前 probe_chars 字符定位
            probe = text[:probe_chars]
            probe_pos = markdown.find(probe, cursor) if probe else -1
            if probe_pos >= 0:
                pos, end = probe_pos, probe_pos + len(probe)
        if pos < 0 or end <= pos:
            continue  # 失配：不猜页码

        matched += 1
        spans.append(PageSpan(char_start=pos, char_end=end, page=page))
        cursor = end

    spans.sort(key=lambda span: span.char_start)
    return PageIndex(spans=tuple(spans), total=total, matched=matched)


def _iter_paged_entries(
    content_list: list[dict[str, Any]],
) -> list[tuple[str, int | None]]:
    """把 v1 / v2 两种 ``content_list`` 归一成 ``[(文本, 页码), ...]``。"""
    if not content_list:
        return []

    # v2 判定：外层元素是 list（页列表）→ 页码 = 外层索引 + 1
    if any(isinstance(item, list) for item in content_list):
        entries: list[tuple[str, int | None]] = []
        for page_index, page_items in enumerate(content_list):
            if not isinstance(page_items, list):
                continue
            page = page_index + 1
            for item in page_items:
                if isinstance(item, dict):
                    entries.append((_extract_block_text(item), page))
        return entries

    # v1：扁平条目列表，页码来自 item.page_idx
    return [
        (str(item.get("text") or "").strip(), _page_from_item(item))
        for item in content_list
        if isinstance(item, dict)
    ]


def _extract_block_text(item: dict[str, Any]) -> str:
    """按 v2 实测路径取块纯文本：递归收集 ``{"type": "text", "content": "..."}``。

    表格块（``content.html``）不含 ``type=text`` 的叶子 → 返回空串，
    走「失配跳过」分支（表格在 ``full.md`` 里被转成了 HTML，本来就对不上）。
    """
    parts: list[str] = []

    def _walk(node: Any) -> None:  # noqa: ANN401 - 递归遍历任意嵌套结构
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("content"), str):
                parts.append(node["content"])
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(item)
    return "".join(parts).strip()


def _page_from_item(item: dict[str, Any]) -> int | None:
    """取 ``page_idx`` 并转成 1-based 页码；缺失 / 非法 → ``None``。

    ``page_idx`` 从 0 计（实测），故 ``+1``；``bool`` 是 ``int`` 子类，显式排除。
    """
    raw = item.get("page_idx")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        page = int(raw) + 1
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


__all__ = ["PageIndex", "PageSpan", "build_page_index"]
