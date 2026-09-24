"""M4 关联交易疑点检出（Sprint 7.1 批次 A，``specs/m4-affiliation-detection.md``）。

只做 spec §3 验收 3 里的**两类**规则疑点：``shared_legal_rep`` / ``shared_address``
（同法人 / 同地址）。三类算法里的「环路」与「金额不一致」需要 ``SHARES_HOLDER`` /
``:Invoice`` / ``:Voucher`` / ``:Contract``——本批次语料（分销与年报材料）里
**没有**持股与三方金额数据，故**不做**（不做就是不做，不拿别的信号冒充）。

两条硬纪律（对应 tasks §2.3）：

1. **Cypher 照 spec §5.4 原文**（第 154 / 159 行），只加两处必要的偏离：
   对称对去重与租户过滤（见 ``graphs.py`` 的查询注释）；
2. **无证据不产疑点**：spec §3 验收 4 要求引用覆盖率 100%，所以取不到
   ``:Chunk`` 证据的命中**直接丢弃**并打 ``affiliation_suspicion_dropped_no_evidence``
   WARNING——**不**留一条「启发式但无原文」的疑点（G5 诚实性）。

严重度（``severity``）**固定** ``medium``：spec 只对 ``amount_mismatch`` 规定了
``high``，其余未规定；本批次**不引入任何可调阈值**（阈值调参 = 给"凑够 3 条疑点"
留后门，tasks §2.3 D6 前置卡口明令禁止）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.services.graphs import GraphService

#: 单条疑点最多挂几条证据（防一条疑点拖回整篇原文，也防日志爆掉）
_DEFAULT_MAX_EVIDENCE: int = 6
#: 日志 / 摘要里单条证据文本的截断长度（真机 chunk 约 1200 字）
_SNIPPET_LENGTH: int = 200
#: 疑点严重度：本批次固定档（**无**阈值可调，见模块 docstring）
_SEVERITY: str = "medium"


@dataclass(frozen=True, slots=True)
class SuspicionEvidence:
    """一条证据：支撑某个主体层节点的**具体原文片段**（S6 ``:Chunk``）。

    ``node_id`` 指明这条证据支撑的是谁（``:Subject`` / ``:LegalPerson`` / ``:Address``
    的 id）——没有它，证据就是一堆无主片段，前端无从"可点击"。
    ``doc_id`` 为 ``None`` 表示该 chunk 未挂 ``:Document``（**不**伪造 UUID，
    沿用 ``EvidenceChunk`` 的纪律）。
    """

    node_id: str
    chunk_id: str
    doc_id: uuid.UUID | None
    text: str
    page: int | None
    char_start: int
    char_end: int

    def to_dict(self, *, snippet: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_id": self.node_id,
            "chunk_id": self.chunk_id,
            "doc_id": str(self.doc_id) if self.doc_id else None,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }
        text = self.text if not snippet else self.text[:_SNIPPET_LENGTH]
        payload["text" if not snippet else "text_snippet"] = text
        return payload


@dataclass(frozen=True, slots=True)
class Suspicion:
    """一条疑点（结构对齐 M4 §3 验收 3：``{type, severity, entities[], evidence[]}``）。

    ``entities`` 依次是 ``[主体A, 主体B, 共享节点]``；``entity_names`` 是对应名称，
    仅供日志 / 展示——**判重与落库一律以 id 为准**（名称可能有别名写法）。
    """

    suspicion_type: str
    severity: str
    entities: tuple[str, ...]
    entity_names: tuple[str, ...]
    evidence: tuple[SuspicionEvidence, ...]

    def to_dict(self, *, snippet: bool = False) -> dict[str, Any]:
        return {
            "type": self.suspicion_type,
            "severity": self.severity,
            "entities": list(self.entities),
            "entity_names": list(self.entity_names),
            "evidence": [item.to_dict(snippet=snippet) for item in self.evidence],
        }


def _to_uuid_or_none(raw: Any) -> uuid.UUID | None:
    """数据库/图里的 id 字符串 → ``UUID``；非法或缺失返回 ``None``（**不**造占位 UUID）。"""
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        logger.bind(raw=raw).warning("affiliation_evidence_doc_id_invalid")
        return None


class AffiliationService:
    """关联交易疑点检出（读侧）。Neo4j 不可用时**抛** :class:`GraphUnavailableError`。

    与 :class:`GraphService` 的关系：本类是**规则层**，不自己拼 Cypher——两跳查询
    与证据查询都在 ``graphs.py``（与既有读侧同处一地，便于核对 spec 原文）。
    """

    def __init__(
        self,
        *,
        graph_service: GraphService | None = None,
        max_evidence: int = _DEFAULT_MAX_EVIDENCE,
    ) -> None:
        self._graph = graph_service or GraphService.instance()
        self._max_evidence = max_evidence

    def detect(
        self,
        *,
        kg_version: str,
        org_id: uuid.UUID | None = None,
        trace_id: uuid.UUID | str | None = None,
        limit: int = 100,
    ) -> list[Suspicion]:
        """跑两类两跳规则；返回**带证据**的疑点列表（无证据的命中被丢弃）。"""
        hits = self._graph.fetch_shared_affiliations(
            kg_version=kg_version, org_id=org_id, limit=limit
        )

        suspicions: list[Suspicion] = []
        dropped = 0
        for hit in hits:
            node_ids = [
                str(hit["subject_a_id"]),
                str(hit["subject_b_id"]),
                str(hit["shared_id"]),
            ]
            rows = self._graph.fetch_affiliation_evidence(
                kg_version=kg_version,
                node_ids=node_ids,
                org_id=org_id,
                limit=self._max_evidence * len(node_ids),
            )
            if not rows:
                # 引用覆盖率 = 100% 是硬要求：没有原文证据就不算疑点
                dropped += 1
                logger.bind(
                    trace_id=str(trace_id) if trace_id else None,
                    kg_version=kg_version,
                    suspicion_type=hit["suspicion_type"],
                    node_ids=node_ids,
                ).warning("affiliation_suspicion_dropped_no_evidence")
                continue

            suspicions.append(
                Suspicion(
                    suspicion_type=str(hit["suspicion_type"]),
                    severity=_SEVERITY,
                    entities=tuple(node_ids),
                    entity_names=(
                        str(hit["subject_a_name"]),
                        str(hit["subject_b_name"]),
                        str(hit["shared_name"]),
                    ),
                    evidence=tuple(
                        SuspicionEvidence(
                            node_id=str(row["node_id"]),
                            chunk_id=str(row["chunk_id"]),
                            doc_id=_to_uuid_or_none(row.get("doc_id")),
                            text=str(row.get("text") or ""),
                            page=int(row["page"])
                            if row.get("page") is not None
                            else None,
                            char_start=int(row.get("char_start") or 0),
                            char_end=int(row.get("char_end") or 0),
                        )
                        for row in rows[: self._max_evidence]
                    ),
                )
            )

        by_type: dict[str, int] = {}
        for item in suspicions:
            by_type[item.suspicion_type] = by_type.get(item.suspicion_type, 0) + 1
        logger.bind(
            trace_id=str(trace_id) if trace_id else None,
            kg_version=kg_version,
            total=len(suspicions),
            by_type=by_type,
            hit_count=len(hits),
            dropped_no_evidence=dropped,
        ).info("affiliation_detect_done")
        return suspicions


def detect_suspicions(
    *,
    kg_version: str,
    org_id: uuid.UUID | None = None,
    trace_id: uuid.UUID | str | None = None,
    limit: int = 100,
) -> list[Suspicion]:
    """模块级便捷入口（管线执行体 / 脚本用），等价于 :meth:`AffiliationService.detect`。

    :raises GraphUnavailableError: Neo4j 不可达——**绝不**降级为空列表。
    """
    return AffiliationService().detect(
        kg_version=kg_version, org_id=org_id, trace_id=trace_id, limit=limit
    )


__all__ = [
    "AffiliationService",
    "Suspicion",
    "SuspicionEvidence",
    "detect_suspicions",
]
