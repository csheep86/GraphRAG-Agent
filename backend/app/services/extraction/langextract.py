"""LangExtract 客户端（Sprint 5 批次 B：document.extract 阶段输入源）。

对齐 `langextract_mvp/run_mvp.py` 实测口径（CODEBUDDY.md「实测结果反哺规则」）：
- 按 ``settings.extraction_max_chars_per_chunk`` 切分输入；
- 单 chunk 调一次 LLM 抽取（默认 mockable 路径——零外部依赖）；
- 严格按 ``kg_extraction_v1`` 模板的 JSON Schema 输出；
- 超 ``extraction_max_entities_per_doc`` / ``extraction_max_relations_per_doc`` 按
  ``confidence`` 降序裁剪（防 LLM 失控批量生成）。

设计边界：
- **默认 mockable**——``_default_extract_chunk`` 用正则占位实现，保证 CI / 单元测试
  无外部依赖；生产真实 LLM 调用留 ``_evaluate_client_call_llm`` 占位（受
  ``extraction_provider`` 切换键约束，未实现别档显式报错）；
- **不**做内层 tenacity 重试——外层 ``document.extract`` 执行体已有指数退避
  （同 MineruClient 的纪律，双层重试会放大等待）。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from loguru import logger

from app.core.config import get_settings
from app.prompts.prompt_loader import load_prompt

#: entity_type 合法取值（与 prompts/kg_extraction_v1.md 输出一致）
ENTITY_TYPES: Final[tuple[str, ...]] = (
    "PERSON",
    "ORG",
    "MONEY",
    "DATE",
    "CONTRACT_CLAUSE",
    "REGULATION",
    "VENUE",
    "PRODUCT",
)
#: relation_type 合法取值（与 import_to_neo4j.py RELATION_TOKEN_MAP 对齐）
RELATION_TYPES: Final[tuple[str, ...]] = (
    "EMPLOYED_BY",
    "SUPPLIES_TO",
    "PARTY_TO",
    "HAS_FINANCIAL_INDICATOR",
    "OPERATES_SEGMENT",
    "RELATED",
    "AFFILIATED_WITH",
    "SUPPORTED_BY",
)


class LangextractError(Exception):
    """LangExtract 业务错误（未知档位 / 输入空白 / 解析失败等）。

    与 ``MineruApiError`` 对位——属可重试异常集合（外层执行体 tenacity 处理）。
    """


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    """抽取出的实体。"""

    id: str
    canonical_name: str
    entity_type: str
    mention: str
    char_start: int
    char_end: int
    confidence: float


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    """抽取出的关系。"""

    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    evidence: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """一次抽取的完整产物（entities + relations，按 confidence 已裁剪）。"""

    document_id: uuid.UUID
    trace_id: uuid.UUID
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, object]:
        """导出 ``kg_versions`` 持久化 / Neo4j 写入共用的 JSON 结构。"""
        return {
            "entities": [
                {
                    "id": e.id,
                    "canonical_name": e.canonical_name,
                    "entity_type": e.entity_type,
                    "mention": e.mention,
                    "char_start": e.char_start,
                    "char_end": e.char_end,
                    "confidence": e.confidence,
                }
                for e in self.entities
            ],
            "relations": [
                {
                    "id": r.id,
                    "source_entity_id": r.source_entity_id,
                    "target_entity_id": r.target_entity_id,
                    "relation_type": r.relation_type,
                    "evidence": r.evidence,
                    "confidence": r.confidence,
                }
                for r in self.relations
            ],
        }


#: 测试可注入的 chunk 抽取函数签名（默认 mockable，真实 LLM 调用留位）
ChunkExtractorFn = Callable[
    [str, int], tuple[list[ExtractedEntity], list[ExtractedRelation]]
]


# ------------------------------------------------------------------------------
# 正则模式（mockable 抽取器用，生产可替换为真实 LLM 调用）
# ------------------------------------------------------------------------------

#: 中文机构名（含"有限公司 / 集团 / 公司 / Inc / Ltd"）
_RE_ORG = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:有限公司|股份有限公司|集团|公司|Inc\.?|Ltd\.?|LLC)",
)
#: 中文姓名（2~4 字常见姓名，与上下文词共同出现）
_RE_PERSON = re.compile(r"(?:[\u4e00-\u9fff]{2,3}(?=\s*(?:先生|女士|教授|律师|博士)))")
#: 金额（含"元 / 亿 / 万 / $ / RMB"等后缀）
_RE_MONEY = re.compile(
    r"(?:[\$RMB￥]?\s?\d+(?:\.\d+)?\s?(?:亿|万|千|百)?\s?(?:元|美元|欧元|RMB))"
)
#: 日期（年份 / 4 位年-月-日）
_RE_DATE = re.compile(
    r"(?:\d{4}\s?年(?:\d{1,2}\s?月)?(?:\d{1,2}\s?日)?|\d{4}-\d{1,2}-\d{1,2})"
)


def _default_extract_chunk(
    text: str, char_offset: int
) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
    """mockable 默认抽取器：基于正则的占位实现。

    真实 LLM 调用留 ``_evaluate_client_call_llm``（受 settings 切换键约束）。
    输入空白 / 无任何匹配时返回空列表，由裁剪逻辑保证不污染下游。
    """
    entities: list[ExtractedEntity] = []

    for regex, entity_type in (
        (_RE_ORG, "ORG"),
        (_RE_PERSON, "PERSON"),
        (_RE_MONEY, "MONEY"),
        (_RE_DATE, "DATE"),
    ):
        for match in regex.finditer(text):
            confidence = 0.85 if entity_type in {"ORG", "MONEY"} else 0.7
            entities.append(
                ExtractedEntity(
                    id=f"ent_{uuid.uuid4().hex[:12]}",
                    canonical_name=match.group(0).strip(),
                    entity_type=entity_type,
                    mention=match.group(0),
                    char_start=char_offset + match.start(),
                    char_end=char_offset + match.end(),
                    confidence=confidence,
                )
            )

    relations: list[ExtractedRelation] = []
    # 简单兜底：前两个 ORG 实体之间建立 PARTY_TO 关系（供测试可观察）
    org_entities = [e for e in entities if e.entity_type == "ORG"]
    if len(org_entities) >= 2:
        relations.append(
            ExtractedRelation(
                id=f"rel_{uuid.uuid4().hex[:12]}",
                source_entity_id=org_entities[0].id,
                target_entity_id=org_entities[1].id,
                relation_type="PARTY_TO",
                evidence=f"{org_entities[0].mention} 与 {org_entities[1].mention} 出现在同一上下文",
                confidence=0.65,
            )
        )

    return entities, relations


class LangextractClient:
    """LangExtract 唯一实现（默认档 ``langextract``）。"""

    def __init__(
        self,
        *,
        provider: str,
        max_chars_per_chunk: int,
        max_entities_per_doc: int,
        max_relations_per_doc: int,
        prompt_version: str,
        chunk_extractor: ChunkExtractorFn | None = None,
    ) -> None:
        if provider != "langextract":
            # 未知档位显式报错（与 llm_provider / parser_provider 同策略，
            # 静默回退会掩盖配置错误——plan §4.4 纪律）。
            raise LangextractError(
                f"未知 extraction_provider={provider!r}（当前仅支持 'langextract'）"
            )
        if max_chars_per_chunk <= 0:
            raise LangextractError(
                f"max_chars_per_chunk 必须为正整数（实际={max_chars_per_chunk}）"
            )
        if max_entities_per_doc < 0 or max_relations_per_doc < 0:
            raise LangextractError(
                "max_entities_per_doc / max_relations_per_doc 必须 ≥ 0"
            )

        self._max_chars_per_chunk = max_chars_per_chunk
        self._max_entities_per_doc = max_entities_per_doc
        self._max_relations_per_doc = max_relations_per_doc
        # Prompt 版本仅用于校验存在；真实 LLM 调用留位
        self._prompt_version = prompt_version
        self._chunk_extractor = chunk_extractor or _default_extract_chunk

    # -------------------------------------------------------------- 工厂

    @classmethod
    def from_settings(cls) -> LangextractClient:
        """从 settings 构造默认客户端（``document.extract`` 执行体使用）。"""
        settings = get_settings()
        return cls(
            provider=settings.extraction_provider,
            max_chars_per_chunk=settings.extraction_max_chars_per_chunk,
            max_entities_per_doc=settings.extraction_max_entities_per_doc,
            max_relations_per_doc=settings.extraction_max_relations_per_doc,
            prompt_version=settings.extraction_prompt_version,
        )

    # -------------------------------------------------------------- 主入口

    def extract_entities_relations(
        self,
        *,
        document_id: uuid.UUID,
        full_md_text: str,
        trace_id: uuid.UUID,
    ) -> ExtractionResult:
        """对 ``full_md_text`` 做实体 + 关系抽取，按上限裁剪后返回。

        空 / 不可解析输入 → :class:`LangextractError`（外层执行体判失败并落库）。
        """
        # 校验 prompt 版本存在（fail-fast：版本错配查文档链路）
        try:
            template = load_prompt(
                "kg_extraction", version=int(self._prompt_version.rsplit("v", 1)[-1])
            )
            _ = template.placeholders  # 触发属性校验
        except Exception as exc:  # noqa: BLE001 - 校验失败统一包装
            raise LangextractError(
                f"Prompt 加载失败（extraction_prompt_version={self._prompt_version!r}）: {exc}"
            ) from exc

        if not full_md_text or not full_md_text.strip():
            raise LangextractError(
                f"document_id={document_id} 的 full.md 为空，无法抽取"
            )

        chunks = _split_into_chunks(full_md_text, self._max_chars_per_chunk)

        all_entities: list[ExtractedEntity] = []
        all_relations: list[ExtractedRelation] = []
        for chunk_start, chunk_text in chunks:
            entities, relations = self._chunk_extractor(chunk_text, chunk_start)
            all_entities.extend(entities)
            all_relations.extend(relations)

        entities = _clamp_entities(all_entities, self._max_entities_per_doc)
        relations = _clamp_relations(
            all_relations, entities, self._max_relations_per_doc
        )

        logger.bind(
            trace_id=str(trace_id),
            document_id=str(document_id),
            chunk_count=len(chunks),
            entity_count=len(entities),
            relation_count=len(relations),
        ).info("langextract_done")

        return ExtractionResult(
            document_id=document_id,
            trace_id=trace_id,
            entities=entities,
            relations=relations,
        )


# ------------------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------------------


def _split_into_chunks(text: str, max_chars: int) -> list[tuple[int, str]]:
    """按 ``max_chars`` 切分文本（按段 / 句边界就近）。

    返回 ``[(char_offset, chunk_text), ...]``，供实体 ``char_start/char_end`` 反推。
    """
    if len(text) <= max_chars:
        return [(0, text)]

    chunks: list[tuple[int, str]] = []
    offset = 0
    while offset < len(text):
        end = min(offset + max_chars, len(text))
        # 边界就近：尝试在 [end-200, end] 找最近的句末标点
        if end < len(text):
            boundary = max(
                text.rfind("\n\n", offset, end),
                text.rfind("。", offset, end),
                text.rfind(". ", offset, end),
            )
            if boundary > offset + max_chars // 2:
                end = boundary + 1
        chunks.append((offset, text[offset:end]))
        offset = end
    return chunks


def _clamp_entities(
    entities: list[ExtractedEntity], limit: int
) -> list[ExtractedEntity]:
    """按 ``confidence`` 降序保留前 ``limit`` 条；0 → 全量。"""
    if limit == 0 or len(entities) <= limit:
        return entities
    return sorted(entities, key=lambda e: e.confidence, reverse=True)[:limit]


def _clamp_relations(
    relations: list[ExtractedRelation],
    entities: list[ExtractedEntity],
    limit: int,
) -> list[ExtractedRelation]:
    """按 ``confidence`` 降序保留前 ``limit`` 条；同时丢弃端点不在 entity 集合的关系。

    0 → 全量；端点漂移关系**总是**丢弃（与 Neo4j 三段式写入 stage-3 保持一致）。
    """
    entity_ids = {e.id for e in entities}
    valid = [
        r
        for r in relations
        if r.source_entity_id in entity_ids and r.target_entity_id in entity_ids
    ]
    if limit == 0 or len(valid) <= limit:
        return valid
    return sorted(valid, key=lambda r: r.confidence, reverse=True)[:limit]


__all__ = [
    "ENTITY_TYPES",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractionResult",
    "LangextractClient",
    "LangextractError",
    "RELATION_TYPES",
]
