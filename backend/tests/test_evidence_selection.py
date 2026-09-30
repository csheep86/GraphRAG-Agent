"""``select_evidence_chunks`` 单测（Sprint 10 批次 C 残留缺口）。

与 ``test_subgraph_selection.py`` 同族：**纯函数** ⇒ 确定性、可单测、不需要 Neo4j。
用例覆盖的是**实测定案的那几条口径**（每文档保底 / 并列按文档序 / 余量 span 优先
/ 热度兜底），不是"能跑就行"。

**Sprint 10 批次 E 追加**：rows 由四元组升为五元组（末位 ``char_start``），
组内并列时按**文档原始顺序**而非 chunk_id 字典序 —— 见被测函数 docstring
「并列退化」。该条是实测换来的（Q09 依据在 40 条组内排第 19，靠抬保底要全量
注入 13 万字符），改动排序键后 26 条即可覆盖。
"""

from __future__ import annotations

from app.services.graphs import select_evidence_chunks

#: (chunk_id, doc_id, mentions, spans, char_start)
DOC_A = "11111111-1111-1111-1111-111111111111"
DOC_B = "22222222-2222-2222-2222-222222222222"


def test_empty_rows() -> None:
    assert select_evidence_chunks([], 20) == []


def test_non_positive_limit() -> None:
    rows = [("c1", DOC_A, 3, 0, 0)]
    assert select_evidence_chunks(rows, 0) == []
    assert select_evidence_chunks(rows, -1) == []


def test_floor_is_per_document() -> None:
    """3 篇文档 / 上限 6 ⇒ 每篇保底 2 条，不因某篇片段热度高而被吃满。"""
    rows = [(f"a{i}", DOC_A, 10 - i, 0, i) for i in range(5)]
    rows += [(f"b{i}", DOC_B, 1, 0, i) for i in range(5)]
    rows += [
        (f"c{i}", "33333333-3333-3333-3333-333333333333", 1, 0, i) for i in range(5)
    ]

    selected = select_evidence_chunks(rows, 6)

    assert len(selected) == 6
    per_doc: dict[str, int] = {}
    for chunk_id in selected:
        per_doc[chunk_id[0]] = per_doc.get(chunk_id[0], 0) + 1
    assert per_doc == {"a": 2, "b": 2, "c": 2}


def test_tie_breaks_by_document_order() -> None:
    """MENTIONS **并列**时按 ``char_start``（文档原始顺序），不是 chunk_id 字典序。

    反面教材（批次 E 实测）：CSV 派生片段的 mentions 大量并列，按 chunk_id 排
    等价于**随机抽样** ⇒ employees 表首行（Q09 依据）在组内排到第 19/40，
    抬保底要到全量注入才捞得到。改成文档序后"每组前 N 条"= 文档开头。
    """
    rows = [
        ("zzz", DOC_A, 1, 0, 0),  # 字典序最大，但在文档里最靠前
        ("aaa", DOC_A, 1, 0, 10),  # 字典序最小，但在文档里更靠后
        ("mmm", DOC_A, 1, 0, 5),
    ]

    selected = select_evidence_chunks(rows, 2)

    assert selected == ["zzz", "mmm"], "并列应取文档序靠前的片段（不是 id 字典序）"


def test_heat_still_wins_over_document_order() -> None:
    """文档序只是**并列**时的次级键 —— 不能反过来压过热度。"""
    rows = [
        ("early", DOC_A, 1, 0, 0),  # 文档序最前，但热度低
        ("hot", DOC_A, 9, 0, 999),  # 文档序最后，但热度高
    ]

    selected = select_evidence_chunks(rows, 1)

    assert selected == ["hot"], "mentions 不同时仍按热度降序"


def test_filler_prefers_span_chunks() -> None:
    """保底用不满时，余量先补**带 span** 的片段（引用能被精确定位到句）。"""
    rows = [
        ("a0", DOC_A, 1, 0, 0),
        ("b0", DOC_B, 1, 0, 0),
        ("hot", DOC_A, 99, 0, 1),  # 热度最高，但没有 span
        ("span", DOC_B, 2, 5, 1),  # 热度低，但带 span
    ]

    selected = select_evidence_chunks(rows, 3)

    assert len(selected) == 3
    assert "span" in selected, "余量应优先给带 span 的片段"


def test_chunk_without_document_does_not_take_floor() -> None:
    """``doc_id`` 为 None（``HAS_CHUNK`` 缺失）⇒ 不占保底名额（本就构造不出 Citation）。"""
    rows = [
        ("orphan", None, 100, 9, 0),  # 热度最高 + 带 span，但没有文档
        ("a0", DOC_A, 1, 0, 0),
        ("a1", DOC_A, 1, 0, 1),
        ("b0", DOC_B, 1, 0, 0),
        ("b1", DOC_B, 1, 0, 1),
    ]

    selected = select_evidence_chunks(rows, 4)

    assert len(selected) == 4
    assert {"a0", "a1", "b0", "b1"} <= set(selected), "两篇文档各应拿到保底 2 条"


def test_more_documents_than_limit_truncates_by_heat() -> None:
    """文档数 > 名额（5 篇 / 上限 3）：保底抬到 1 后仍超额 ⇒ 按热度截断。"""
    docs = [f"doc-{i}-0000-0000-0000-000000000000" for i in range(5)]
    rows = [(f"c{i}", doc, i, 0, 0) for i, doc in enumerate(docs)]

    selected = select_evidence_chunks(rows, 3)

    assert len(selected) == 3
    assert selected == ["c4", "c3", "c2"], "超额时按 MENTIONS 降序截断"


def test_deterministic_and_bounded() -> None:
    rows = [(f"c{i}", DOC_A if i % 2 else DOC_B, i % 7, i % 3, i) for i in range(40)]

    first = select_evidence_chunks(rows, 20)
    second = select_evidence_chunks(rows, 20)

    assert first == second, "同输入必须同解（否则同一问题两次注入不同证据）"
    assert len(first) == 20
    assert len(set(first)) == len(first), "不得重复注入同一片段"
