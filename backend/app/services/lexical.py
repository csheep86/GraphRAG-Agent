"""P6-N：**字面量召回** —— 字符 n-gram 倒排 + BM25（**零第三方依赖**）。

为什么是自己实现
----------------
R22 给方向①的定性是「BM25 / 关键词倒排，chunk 文本建索引，**¥0 可验、无外部依赖**」
⇒ **不装** ``rank_bm25`` / ``jieba`` / 任何分词库。中文没有空格，这里用**字符 n-gram**
切分（"张伟" ⇒ ``张伟``；"加班时长" ⇒ ``加班`` / ``班时`` / ``时长``）——
这是无依赖中文检索的常规解法。

定位（必须与 P6-J 的词面重排分清）
--------------------------------
- **本模块**：决定候选**来了哪些**（问句里写了什么 ⇒ 把谁捞进来）；
- **P6-J 的** :func:`select_evidence_chunks`：决定候选**内怎么排序**。

二者互补：重排救不了"不在候选里"的片段（P6-M 实测：键级 71%→67% 只掉 4pp，
丢失几乎全在候选层），本模块补的就是那一层。

不做的事：不落库（不写 Neo4j / 不写文件 / 不加表），索引在**进程内**构建并缓存，
由 :meth:`app.services.graphs.GraphService.fetch_evidence_chunks` 持有。
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

#: BM25 经典参数（不调参：本模块要的是"碰没碰上"，不是语义理解）
_K1 = 1.5
_B = 0.75

#: 中文切分粒度。**2** 是"既能命中双字词、又不至于把索引撑爆"的折中。
_NGRAM = 2

#: ASCII 串（数字 / 英文 / 单号，允许内部连字符与点号）⇒ **整串**入索引。
#: 键级查询靠这一条：`TR-0042` 必须作为一个整体被命中，拆开就没意义了。
_ASCII_TOKEN = re.compile(r"[0-9A-Za-z]+(?:[-_./][0-9A-Za-z]+)*")

#: 连续中文段 ⇒ 切成字符 n-gram
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """把一段文本切成检索 token（**不分词、不引入依赖**）。

    >>> tokenize("TR-0042 张伟")
    ['tr-0042', '张伟']
    """
    tokens: list[str] = []
    for match in _ASCII_TOKEN.finditer(text):
        tokens.append(match.group(0).lower())
    for match in _CJK_RUN.finditer(text):
        run = match.group(0)
        if len(run) <= _NGRAM:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + _NGRAM] for i in range(len(run) - _NGRAM + 1))
    return tokens


def _idf(n_docs: int, df: int) -> float:
    """BM25 的 IDF（带平滑，df = n 时也不会出现负数）。"""
    return math.log(1 + (n_docs - df + 0.5) / (df + 0.5))


@dataclass(frozen=True)
class LexicalIndex:
    """一个版本 / 租户下的 chunk 文本倒排索引（**只读**，构建后不变）。"""

    #: ``token -> {chunk_id: 词频}``
    postings: dict[str, dict[str, int]] = field(default_factory=dict)
    #: ``chunk_id -> token 数``（BM25 的长度归一化要用）
    doc_len: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        """索引了多少条 chunk。"""
        return len(self.doc_len)

    @classmethod
    def build(cls, docs: Sequence[tuple[str, str]]) -> LexicalIndex:
        """由 ``(chunk_id, text)`` 序列构建倒排。"""
        postings: dict[str, dict[str, int]] = {}
        doc_len: dict[str, int] = {}
        for chunk_id, text in docs:
            tokens = tokenize(text)
            doc_len[chunk_id] = len(tokens)
            for token in tokens:
                bucket = postings.setdefault(token, {})
                bucket[chunk_id] = bucket.get(chunk_id, 0) + 1
        return cls(postings=postings, doc_len=doc_len)

    def search(self, query: str, top_k: int) -> list[str]:
        """按 BM25 取 ``chunk_id``（得分降序，同分按 id 升序保证**可复现**）。

        :param top_k: 最多返回多少条；``<= 0`` ⇒ 返回空列表。
        """
        if top_k <= 0:
            return []
        query_tokens = set(tokenize(query))
        if not query_tokens or not self.doc_len:
            return []

        n_docs = len(self.doc_len)
        avgdl = sum(self.doc_len.values()) / n_docs
        scores: dict[str, float] = {}
        for token in query_tokens:
            bucket = self.postings.get(token)
            if not bucket:
                continue
            idf = _idf(n_docs, len(bucket))
            for chunk_id, tf in bucket.items():
                dl = self.doc_len[chunk_id]
                denom = tf + _K1 * (1 - _B + _B * dl / avgdl)
                scores[chunk_id] = (
                    scores.get(chunk_id, 0.0) + idf * (tf * (_K1 + 1)) / denom
                )

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [chunk_id for chunk_id, _score in ranked[:top_k]]
