"""P6-N：**字面量召回**单测（倒排 + BM25 并入候选）。

钉死的三件事（对应 proposal 的验收判据 ③ / ① / N-D1）：

1. **默认路径零变化**：``question=None`` ⇒ **绝不**查字面量池、候选一条不变
   （既有调用点与 P6-K 的哨兵行为必须逐字节不变）；
2. **补召回**：``question`` 里写了键 ⇒ 图候选之外的那条 chunk 被捞进来；
3. **并集（N-D1）**：补召回**不**挤掉任何图候选 —— 换成"替换"会让
   Q20 / Q22 / Q26 这类概念性提问候选清空。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from app.services.graphs import (
    _QUERY_COUNT_CHUNKS_IN_VERSION,
    _QUERY_EVIDENCE_CHUNK_INDEX,
    _QUERY_EVIDENCE_CHUNK_INDEX_BY_IDS,
    _QUERY_EVIDENCE_CHUNKS_BY_IDS,
    _QUERY_LEXICAL_POOL,
    GraphService,
)
from app.services.lexical import LexicalIndex, tokenize

KG_VERSION = "lexical-test-v1"
DOC_A = "00000000-0000-4000-8000-0000000000aa"
DOC_B = "00000000-0000-4000-8000-0000000000bb"

#: 图候选：只有 c1 / c2（模拟"500 采样实体没盖住 c9"）
GRAPH_ROWS = [
    {
        "chunk_id": "c1",
        "doc_id": DOC_A,
        "mentions": 3,
        "spans": 1,
        "char_start": 0,
        "snippet": "考勤制度第一条",
    },
    {
        "chunk_id": "c2",
        "doc_id": DOC_A,
        "mentions": 2,
        "spans": 0,
        "char_start": 10,
        "snippet": "考勤制度第二条",
    },
]

#: 字面量池：c9 里有键 ``TR-0042``，但**不在**图候选里（P6-M 实测的那 64%）
POOL_ROWS = [
    {"chunk_id": "c1", "text": "考勤制度第一条 加班"},
    {"chunk_id": "c2", "text": "考勤制度第二条 调休"},
    {"chunk_id": "c9", "text": "交易 TR-0042 的合同金额为 12 万元"},
]


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """复刻 ``fetch_evidence_chunks`` 的四段查询，并**记录**跑了哪几段。"""

    def __init__(self, *, total_chunks: int = 3) -> None:
        self.total_chunks = total_chunks
        self.ran: list[str] = []
        self.lexical_ids: list[str] = []

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def run(self, query: str, **params: Any) -> Any:
        # ⚠️ **存整条**：两条 Chunk 查询的前 48 个字符一模一样
        # （``MATCH (c:Chunk {kg_version: $kg_version})\nWHERE ``）⇒ 截断比对会误判
        self.ran.append(query)
        if query == _QUERY_EVIDENCE_CHUNK_INDEX:
            return list(GRAPH_ROWS)
        if query == _QUERY_LEXICAL_POOL:
            return list(POOL_ROWS)
        if query == _QUERY_EVIDENCE_CHUNK_INDEX_BY_IDS:
            self.lexical_ids = list(params["ids"])
            by_id = {row["chunk_id"]: row for row in POOL_ROWS}
            return [
                {
                    "chunk_id": cid,
                    "doc_id": DOC_B,
                    "mentions": 1,
                    "spans": 0,
                    "char_start": 0,
                    "snippet": by_id.get(cid, {}).get("text", ""),
                }
                for cid in params["ids"]
                if cid in by_id
            ]
        if query == _QUERY_EVIDENCE_CHUNKS_BY_IDS:
            return [
                {
                    "chunk_id": chunk_id,
                    "doc_id": DOC_A if chunk_id in {"c1", "c2"} else DOC_B,
                    "text": f"{chunk_id} 正文",
                    "page": None,
                    "char_start": 0,
                    "char_end": 4,
                    "spans": [],
                }
                for chunk_id in params["chunk_ids"]
            ]
        if query == _QUERY_COUNT_CHUNKS_IN_VERSION:
            return _FakeResult([{"n": self.total_chunks}])
        raise AssertionError(f"未预期的查询: {query[:40]}")


@pytest.fixture
def session() -> Iterator[_FakeSession]:
    fake = _FakeSession()
    service = GraphService()
    # 每个用例都从干净缓存开始（否则进程内缓存会跨用例串味）
    from app.services import graphs

    graphs._LEXICAL_INDEX_CACHE.clear()  # noqa: SLF001 - 单测显式清缓存
    service._session = lambda: fake  # type: ignore[method-assign]
    yield fake


# ---------------------------------------------------------------------------
# ① 切分与检索本身（纯函数，不连图）
# ---------------------------------------------------------------------------


def test_tokenize_keeps_serial_number_whole() -> None:
    """单号必须**整串**入索引 —— 拆开就没法命中 `TR-0042` 了。"""
    # 顺序：ASCII 串在前（`tokenize` 先扫 ASCII 再扫中文）；顺序对检索无影响
    # （检索用 ``set``），这里只是把**实际行为**钉住，防止日后有人顺手改动。
    assert tokenize("交易 TR-0042 的金额") == ["tr-0042", "交易", "的金", "金额"]


def test_tokenize_cjk_bigram() -> None:
    assert tokenize("加班时长") == ["加班", "班时", "时长"]


def test_search_returns_key_hit_first() -> None:
    index = LexicalIndex.build([(row["chunk_id"], row["text"]) for row in POOL_ROWS])
    assert index.size == 3
    assert index.search("TR-0042", 10)[0] == "c9"


def test_search_empty_query_or_top_k() -> None:
    index = LexicalIndex.build([(row["chunk_id"], row["text"]) for row in POOL_ROWS])
    assert index.search("", 10) == []
    assert index.search("TR-0042", 0) == []


def test_search_is_deterministic_on_tie() -> None:
    """同分按 id 升序 ⇒ 多次调用结果一致（评测要可复现）。"""
    docs = [("b", "加班"), ("a", "加班")]
    index = LexicalIndex.build(docs)
    assert index.search("加班", 2) == ["a", "b"]


# ---------------------------------------------------------------------------
# ② 服务层：默认路径零变化 + 补召回 + 并集
# ---------------------------------------------------------------------------


def test_no_question_never_touches_lexical(session: _FakeSession) -> None:
    """**验收判据 ③**：不传 ``question`` ⇒ 绝不查字面量池、候选一条不变。"""
    service = GraphService()
    service._session = lambda: session  # type: ignore[method-assign]

    chunks = service.fetch_evidence_chunks(
        kg_version=KG_VERSION, org_id=None, entity_ids=["e1"], limit=32
    )

    assert _QUERY_LEXICAL_POOL not in session.ran, (
        "question=None 时不得查字面量池：那会让所有既有调用点（含 P6-K 的哨兵行为）"
        "平白多一次全池查询"
    )
    assert session.lexical_ids == []
    assert {c.chunk_id for c in chunks} == {"c1", "c2"}


def test_question_pulls_in_chunk_outside_graph_candidates(
    session: _FakeSession,
) -> None:
    """**验收判据 ①**：问句里的键把图候选之外的 chunk 捞进来（P6-M 实测的那 64%）。"""
    service = GraphService()
    service._session = lambda: session  # type: ignore[method-assign]

    chunks = service.fetch_evidence_chunks(
        kg_version=KG_VERSION,
        org_id=None,
        entity_ids=["e1"],
        limit=32,
        question="TR-0042 的合同金额是多少？",
    )

    assert "c9" in session.lexical_ids, "字面量召回必须命中 c9（它不在图候选里）"
    ids = {c.chunk_id for c in chunks}
    assert "c9" in ids, "补召回的 chunk 必须真进最终注入"


def test_lexical_union_keeps_every_graph_candidate(session: _FakeSession) -> None:
    """**N-D1 并集**：补召回**不**许挤掉任何图候选。

    换成"替换" ⇒ Q20 / Q22 / Q26 这类"句中没有实体锚点"的概念性提问会被清空候选。
    """
    service = GraphService()
    service._session = lambda: session  # type: ignore[method-assign]

    chunks = service.fetch_evidence_chunks(
        kg_version=KG_VERSION,
        org_id=None,
        entity_ids=["e1"],
        limit=32,
        question="考勤制度",
    )

    ids = {c.chunk_id for c in chunks}
    assert {"c1", "c2"} <= ids, "图候选一条都不能少（并集，不是替换）"


def test_lexical_candidates_are_deduped(session: _FakeSession) -> None:
    """已在图候选里的 chunk 不重复查第二遍（去重 ⇒ 不浪费索引行）。"""
    service = GraphService()
    service._session = lambda: session  # type: ignore[method-assign]

    service.fetch_evidence_chunks(
        kg_version=KG_VERSION,
        org_id=None,
        entity_ids=["e1"],
        limit=32,
        #: 同时命中两侧：``加班`` 在图候选里、``TR-0042`` 只在 c9 里 ⇒
        #: 补召回**非空**，才能验证"已在图候选里的不再补一遍"
        question="加班 TR-0042",
    )

    assert session.lexical_ids, "字面量召回必须真的跑了（否则本条是假绿）"
    # c1 已在图候选里 ⇒ 不该再出现在字面量补召回里
    assert "c1" not in session.lexical_ids
