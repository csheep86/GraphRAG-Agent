"""``select_evidence_chunks`` 单测（Sprint 10 批次 C 残留缺口）。

与 ``test_subgraph_selection.py`` 同族：**纯函数** ⇒ 确定性、可单测、不需要 Neo4j。
用例覆盖的是**实测定案的那几条口径**（每文档保底 / 并列按文档序 / 余量 span 优先
/ 热度兜底），不是"能跑就行"。

**Sprint 10 批次 E 追加**：rows 由四元组升为五元组（末位 ``char_start``），
组内并列时按**文档原始顺序**而非 chunk_id 字典序 —— 见被测函数 docstring
「并列退化」。该条是实测换来的（Q09 依据在 40 条组内排第 19，靠抬保底要全量
注入 13 万字符），改动排序键后 26 条即可覆盖。

**P6-J（2026-10-05）追加**：``question`` / ``snippets`` 两个可选入参 ——
在既有结构口径**之前**加一层「词面命中优先」。三条退化路径（空 question /
无命中 / 无片段）必须**逐字退化为既有行为**，否则等于借着重排悄悄改掉了
批次 E 定案的排序；故每条退化用例都用「与不带参的那次**完全相等**」来钉，
而不是只看"条数对"。
"""

from __future__ import annotations

from app.services.graphs import _lexical_overlap, select_evidence_chunks

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


# ---------------------------------------------------------------------------
# P6-J：词面重排（question 参与排序）
# ---------------------------------------------------------------------------

#: 本次要救的形态（与 Q20 / Q22 / Q26 同型）：目标片段在**桶内排名靠后**，
#: 纯结构口径下被保底切掉。
_RERANK_ROWS = [
    ("hot1", DOC_A, 9, 0, 0),
    ("hot2", DOC_A, 5, 0, 10),
    ("target", DOC_A, 1, 0, 20),
]
_RERANK_SNIPPETS = {
    "hot1": "S00155,E008,2026-10-01,连班,08:00,21:00,12.0,0",
    "hot2": "S00156,E008,2026-10-02,正常班,09:00,18:00,8.0,0",
    "target": "第二条 月标准工时为 174 小时，由 21.75 天乘以 8 小时得出。",
}
_RERANK_QUESTION = "月标准工时是多少小时？"


def test_lexical_hit_takes_a_floor_slot() -> None:
    """词面命中者**挤进保底名额**；同时钉住反向 —— 撤掉 question 它就被切掉。

    反向那半句是本批的硬验收（proposal §5 第 8 条）：只测"进了"验证的是别的东西
    （很可能是碰巧），必须同时证明"不修就进不来"。
    """
    structural = select_evidence_chunks(_RERANK_ROWS, 2)

    assert "target" not in structural, (
        "纯结构口径下目标应被切掉（否则本用例没在测什么）"
    )

    reranked = select_evidence_chunks(
        _RERANK_ROWS,
        2,
        question=_RERANK_QUESTION,
        snippets=_RERANK_SNIPPETS,
    )
    assert "target" in reranked, "词面命中的片段应优先占保底名额"
    assert len(reranked) == 2


def test_lexical_tie_falls_back_to_structural_order() -> None:
    """词面分**并列** ⇒ 落回既有的结构口径（热度 → 文档原始顺序 → chunk_id）。

    为什么必须钉：大量候选与提问零重叠 ⇒ 分数全为 0 ⇒ 并列是**常态**而非边界。
    并列时若退化成不稳定顺序，等于把批次 E 修好的「并列退化」又改坏了。
    """
    rows = [
        ("early", DOC_A, 1, 0, 0),  # 文档序最前
        ("late", DOC_A, 1, 0, 99),  # 文档序最后
        ("hot", DOC_A, 9, 0, 50),  # 热度最高
    ]
    #: 三条片段**同一份** ⇒ 词面分必然并列
    snippets = {cid: "同样的内容 月标准工时" for cid in ("early", "late", "hot")}

    selected = select_evidence_chunks(
        rows, 2, question=_RERANK_QUESTION, snippets=snippets
    )

    assert selected == ["hot", "early"], "并列后应按热度 → 文档原始顺序"


def test_empty_question_degenerates_to_structural() -> None:
    """``question`` 为空 / 无有效字符 ⇒ **逐字**退化为不带参的结果。"""
    rows = [(f"c{i}", DOC_A if i % 2 else DOC_B, i % 5, i % 3, i) for i in range(12)]
    expected = select_evidence_chunks(rows, 6)

    for question in ("", "   ", "？？？、。", "?"):
        actual = select_evidence_chunks(
            rows, 6, question=question, snippets=_RERANK_SNIPPETS
        )
        assert actual == expected, f"question={question!r} 应完全退化为结构口径"


def test_no_lexical_hit_degenerates_to_structural() -> None:
    """**无命中**（提问与所有片段零重叠）⇒ 结果与纯结构口径**逐字相同**。

    这条防的是「加了重排 ⇒ 连不该变的结果也变了」：重排只允许撬动**命中者**。
    """
    rows = [(f"c{i}", DOC_A if i % 2 else DOC_B, i % 5, i % 3, i) for i in range(12)]
    snippets = {cid: "S00155,E008,2026-10-01,连班,08:00,21:00" for cid, *_ in rows}
    expected = select_evidence_chunks(rows, 6)

    actual = select_evidence_chunks(
        rows, 6, question="《红楼梦》中贾宝玉的妻子是谁？", snippets=snippets
    )

    assert actual == expected, "零命中不得改变任何排序"


def test_missing_snippets_degenerates_to_structural() -> None:
    """``snippets`` 缺失 ⇒ 退化为结构口径（索引没带回片段时的真实形态）。"""
    rows = [(f"c{i}", DOC_A if i % 2 else DOC_B, i % 5, i % 3, i) for i in range(12)]
    expected = select_evidence_chunks(rows, 6)

    assert (
        select_evidence_chunks(rows, 6, question=_RERANK_QUESTION, snippets=None)
        == expected
    )
    assert (
        select_evidence_chunks(rows, 6, question=_RERANK_QUESTION, snippets={})
        == expected
    )


def test_rerank_is_deterministic() -> None:
    rows = [(f"c{i}", DOC_A if i % 2 else DOC_B, i % 7, i % 3, i) for i in range(40)]
    snippets = {cid: f"片段 {i} 月标准工时" for i, (cid, *_rest) in enumerate(rows)}

    first = select_evidence_chunks(
        rows, 20, question=_RERANK_QUESTION, snippets=snippets
    )
    second = select_evidence_chunks(
        rows, 20, question=_RERANK_QUESTION, snippets=snippets
    )

    assert first == second, "带重排后仍必须同输入同解"
    assert len(set(first)) == len(first)


def test_lexical_overlap_is_coverage_not_count() -> None:
    """:func:`_lexical_overlap` = 提问被覆盖的比例 ⇒ 值与**片段长度无关**（去重 bigram）。

    不去重的话，长片段靠重复词就能刷高分数 ⇒ 那是长度偏置，不是相关性。
    """
    question = "月标准工时是多少小时？"

    short = _lexical_overlap(question, "月标准工时")
    long_repeat = _lexical_overlap(question, "月标准工时 " * 20)

    assert short == long_repeat, "重复出现不应抬高分数（bigram 必须去重）"
    assert 0.0 < short < 1.0


def test_lexical_overlap_ignores_punctuation_and_case() -> None:
    assert _lexical_overlap("E004 加班", "e004，加班！") == 1.0, "标点与大小写应被忽略"


def test_lexical_overlap_degenerate_inputs() -> None:
    """退化输入必须给 ``0.0``，**不给 NaN** —— NaN 会把排序打乱成不确定顺序。"""
    assert _lexical_overlap("", "任意内容") == 0.0
    assert _lexical_overlap("月标准工时", "") == 0.0
    assert _lexical_overlap("？", "？") == 0.0, "去掉标点后不足 2 个有效字符 ⇒ 0.0"
    assert _lexical_overlap("月标准工时", "完全无关的内容") == 0.0
