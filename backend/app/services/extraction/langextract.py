"""LangExtract 客户端（Sprint 5 批次 B：document.extract 阶段输入源）。

对齐 `langextract_mvp/run_mvp.py` 实测口径（CODEBUDDY.md「实测结果反哺规则」）：
- 按 ``settings.extraction_max_chars_per_chunk`` 切分输入；
- 单 chunk 调一次 LLM 抽取（引擎由 ``settings.extraction_engine`` 显式指定）；
- 严格按 ``kg_extraction_v1`` 模板的 JSON Schema 输出；
- 超 ``extraction_max_entities_per_doc`` / ``extraction_max_relations_per_doc`` 按
  ``confidence`` 降序裁剪（防 LLM 失控批量生成）。

设计边界（Sprint 7.0 起）：
- **引擎是显式开关，不再是隐式默认**：``extraction_engine`` 只有 ``llm`` / ``mock``
  两档，未知档位 **显式报错、绝不静默回退**（plan §4.4 纪律）。
  ``mock``（``_default_extract_chunk`` 正则占位器）仅供 CI / 单测注入——
  **其产物不代表真实抽取质量**，不得冒充业务结论；``llm`` 档真实调用模型。
- **真实调用走接缝 3**：经 ``app.services.providers.build_chat_model()`` 构造客户端，
  **不新建第二套 LLM 通道**（ADR-0004 §2.1 接缝 3）。
- **失败不静默**：调用失败 / 超时 / 返回非法 JSON → :class:`LangextractError`，
  **绝不回落 mock**——那会把基础设施故障伪装成业务结论（LC1-9）。

Sprint 7.1 批次 A 新增（真机驱动，详见 ``changes/Sprint7.1/integration-log.md`` §3）：
- **单 chunk 容错**：真机上一个 chunk 撞模型输出上限（非法 JSON）会让**整份文档**
  被外层 tenacity 全量重跑 3 次（实测：一份 124-chunk 的文档烧 ¥6.55 且无产物）。
  现改为「该 chunk 就地重试 1 次 → 仍失败则**跳过并记账**」（日志
  ``langextract_chunk_failed`` + :class:`FailedChunk` 落进产物），
  **整份文档不再因为一个 chunk 重跑**；
- **但整份全败仍必须报错**：全部 chunk 都失败 ⇒ 基础设施故障（API key / 网络 / 配额），
  抛 :class:`LangextractError` 交外层重试——**不许把"没抽到"伪装成"没有实体"**；
- **``char_offset`` 以 ``mention`` 回查为准**：模型自报偏移与 ``mention`` 不符时
  （7.0 实测 top20 中 14/20 不符），丢弃模型偏移、用 ``mention`` 回查定位，
  否则 §2.3 的证据回查会漂到错误位置。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from loguru import logger

from app.core.config import get_settings
from app.prompts.prompt_loader import PromptTemplate, load_prompt
from app.services.providers import build_chat_model

#: entity_type 合法取值（与 prompts/kg_extraction_v2.md 的 ``{{entity_types}}`` 一致；
#: v1 枚举 + Sprint 7.1 批次 A 新增的 ``LEGAL_PERSON`` / ``ADDRESS``）
ENTITY_TYPES: Final[tuple[str, ...]] = (
    "PERSON",
    "ORG",
    "MONEY",
    "DATE",
    "CONTRACT_CLAUSE",
    "REGULATION",
    "VENUE",
    "PRODUCT",
    # Sprint 7.1 批次 A（M4 数据与算法）：法定代表人（自然人）与注册地址
    "LEGAL_PERSON",
    "ADDRESS",
)
#: relation_type 合法取值（与 import_to_neo4j.py RELATION_TOKEN_MAP 对齐；
#: 新增 ``LEGAL_REP`` / ``REGISTERED_AT`` 对应 :Subject 的两条边）
RELATION_TYPES: Final[tuple[str, ...]] = (
    "EMPLOYED_BY",
    "SUPPLIES_TO",
    "PARTY_TO",
    "HAS_FINANCIAL_INDICATOR",
    "OPERATES_SEGMENT",
    "RELATED",
    "AFFILIATED_WITH",
    "SUPPORTED_BY",
    # Sprint 7.1 批次 A：``(:Subject)-[:LEGAL_REP]->(:LegalPerson)`` /
    # ``(:Subject)-[:REGISTERED_AT]->(:Address)`` 的抽取侧对位
    "LEGAL_REP",
    "REGISTERED_AT",
)

#: 单 chunk 的**总尝试次数**（首次 + 就地重试 1 次；再失败即跳过）。
#: 为什么不是更多：真机失败形态是"输出被截断"，重试多半仍截断，多试只是烧钱。
_CHUNK_MAX_ATTEMPTS: Final[int] = 2

#: 抽取引擎档位（``settings.extraction_engine``；未知档位显式报错）
ENGINE_LLM: Final[str] = "llm"
ENGINE_MOCK: Final[str] = "mock"
ENGINES: Final[tuple[str, ...]] = (ENGINE_LLM, ENGINE_MOCK)

#: 未知 ``entity_type`` / ``relation_type`` 的统一降级目标
#: （``prompts/kg_extraction_v1.md`` 第 47–48 行；原始名由日志留痕）
_FALLBACK_TYPE: Final[str] = "RELATED"
#: ``confidence`` 低于此值即丢弃（``prompts/kg_extraction_v1.md`` 第 50 行）
_MIN_CONFIDENCE: Final[float] = 0.5
#: 失败原因进日志 / 产物的截断长度（防把模型原文整段写进日志）
_REASON_SNIPPET: Final[int] = 200
#: Prompt 的 ``{{language}}`` 取值（语种常量，非配置；改语种须走 Prompt 新版本）
_PROMPT_LANGUAGE: Final[str] = "chinese"
#: llm 档里跟随 System 指令的用户侧指令（约束"只输出 JSON"，不承载模板语义）
_LLM_USER_INSTRUCTION: Final[str] = (
    "请严格按上述输出约定对 System 中的文本做抽取，只输出 JSON 对象，"
    "不要附加任何解释或代码围栏说明。"
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
class ExtractedChunk:
    """抽取切块（Sprint 6 批次 A-1：Chunk 证据节点的写侧输入）。

    ``char_start`` / ``char_end`` 是相对 ``full.md`` 全文的**绝对**字符区间
    （``_split_into_chunks`` 已把块内偏移加回块起点），与 :class:`ExtractedEntity`
    的区间同一坐标系 —— 这是 stage-4 判定「实体属于哪个 chunk」的唯一依据。

    ``page`` 由调用方（``document.extract`` 执行体）用 :class:`PageIndex` 回填；
    未判到页时为 ``None``（**不**兜底成 1 —— 假页码比没有页码更危险）。
    """

    id: str
    char_start: int
    char_end: int
    text: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class FailedChunk:
    """抽取失败被**跳过**的 chunk（Sprint 7.1 批次 A：单 chunk 容错）。

    **跳过必须留痕**（否则就是静默降级）：每个失败的 chunk 都会
    ① 打 ``langextract_chunk_failed`` WARNING 日志；② 以本结构进 :class:`ExtractionResult`。
    ``reason`` 截断到 :data:`_REASON_SNIPPET` 字，避免把整段模型原文灌进日志 / 产物。
    """

    index: int
    char_offset: int
    reason: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """一次抽取的完整产物（entities + relations + chunks，按 confidence 已裁剪）。"""

    document_id: uuid.UUID
    trace_id: uuid.UUID
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    chunks: list[ExtractedChunk] = field(default_factory=list)
    #: 被跳过的 chunk（**诊断字段**：下游只消费 ``entities`` / ``relations`` /
    #: ``chunks`` 三个键，本字段供真机对账"这一份丢了多少证据"）
    failed_chunks: list[FailedChunk] = field(default_factory=list)

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
            "chunks": [
                {
                    "id": c.id,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "text": c.text,
                    "page": c.page,
                }
                for c in self.chunks
            ],
            "failed_chunks": [
                {
                    "index": f.index,
                    "char_offset": f.char_offset,
                    "reason": f.reason,
                }
                for f in self.failed_chunks
            ],
        }


#: chunk 抽取函数签名（``(chunk_text, char_offset) -> (entities, relations)``）；
#: 两档引擎与测试注入都实现这个签名，切分 / 裁剪逻辑因此完全共用
ChunkExtractorFn = Callable[
    [str, int], tuple[list[ExtractedEntity], list[ExtractedRelation]]
]
#: 可注入的 LLM 调用签名（渲染后的 Prompt 进，模型原文出）。
#: 单测注入假实现即可零外部依赖；默认实现走接缝 3 的 ``build_chat_model()``
LlmInvokerFn = Callable[[str], str]


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
    """``extraction_engine='mock'`` 档的抽取器：基于正则的**占位**实现。

    只出 ORG / PERSON / MONEY / DATE 四类，**不代表真实抽取质量**——
    仅用于 CI / 单测在零外部依赖下跑通链路（生产与演示走 ``llm`` 档）。
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


# ------------------------------------------------------------------------------
# llm 档：真实 LLM 抽取（Sprint 7.0 落地，接 _default_extract_chunk 的位）
# ------------------------------------------------------------------------------


def _default_llm_invoke(prompt: str) -> str:
    """默认 LLM 调用：经接缝 3 的 ``build_chat_model()``，**不**自建客户端。

    同步 ``invoke``（抽取链路整体是同步的；``document.extract`` 执行体把它放进
    工作线程，不阻塞事件循环）。异常由 :func:`_build_llm_chunk_extractor` 统一包装
    成 :class:`LangextractError`——**不在此静默回落 mock**。

    每次调用打点**耗时与 token 用量**（CODEBUDDY.md「日志与可观测性规则」）；
    日志只记数值，**不落** prompt 原文与密钥。
    """
    from time import perf_counter

    from langchain_core.messages import HumanMessage, SystemMessage

    started = perf_counter()
    model = build_chat_model()
    response = model.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=_LLM_USER_INSTRUCTION),
        ]
    )
    elapsed_ms = round((perf_counter() - started) * 1000)

    logger.bind(elapsed_ms=elapsed_ms, **_extract_token_usage(response)).info(
        "langextract_llm_call"
    )
    return str(response.content)


def _extract_token_usage(response: object) -> dict[str, int | None]:
    """从 LangChain 响应里取 token 用量；取不到返回 ``None``（**严禁造数据**）。"""
    metadata = getattr(response, "response_metadata", None)
    usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _render_extraction_prompt(template: PromptTemplate, *, text: str) -> str:
    """渲染 ``kg_extraction`` 模板；**按模板实际声明的占位符**给值。

    v1 只声明 ``{{text}}`` / ``{{language}}``；v2（Sprint 7.1）把类型枚举参数化为
    ``{{entity_types}}`` / ``{{relation_types}}``。这里不按版本号硬分支，而是看模板
    声明——**加版本不必改代码**，也避免把 v2 的变量喂给 v1（prompt_loader 会报
    "未声明的变量"，等于把模板升级变成运行期地雷）。
    """
    values: dict[str, str] = {"text": text, "language": _PROMPT_LANGUAGE}
    declared = set(template.placeholders)
    if "entity_types" in declared:
        values["entity_types"] = "|".join(ENTITY_TYPES)
    if "relation_types" in declared:
        values["relation_types"] = "|".join(RELATION_TYPES)
    return template.render(**values)


def _build_llm_chunk_extractor(
    *, prompt_version: str, invoker: LlmInvokerFn
) -> ChunkExtractorFn:
    """构造 llm 档的 chunk 抽取器：单 chunk → 一次 LLM 调用 → 严格解析。

    与 mock 档**共用**外层的切分 / 裁剪逻辑（``_split_into_chunks`` /
    ``_clamp_*``），本函数只替换"文本 → entities/relations"这一步。
    """

    def _extract_chunk(
        text: str, char_offset: int
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        if not text.strip():
            return [], []

        prompt = _render_extraction_prompt(
            load_prompt(
                "kg_extraction", version=_prompt_version_number(prompt_version)
            ),
            text=text,
        )

        try:
            raw = invoker(prompt)
        except LangextractError:
            raise
        except Exception as exc:  # noqa: BLE001 - 第三方异常统一包装为可重试业务错误
            raise LangextractError(
                f"LLM 调用失败（chunk_offset={char_offset}）: "
                f"{type(exc).__name__}: {str(exc)[:200]}"
            ) from exc

        payload = _parse_llm_payload(raw)
        entities, id_map = _entities_from_payload(
            payload, chunk_text=text, char_offset=char_offset
        )
        relations = _relations_from_payload(payload, id_map)

        logger.bind(
            chunk_offset=char_offset,
            entity_count=len(entities),
            relation_count=len(relations),
        ).info("langextract_llm_chunk_done")
        return entities, relations

    return _extract_chunk


def _parse_llm_payload(raw: str) -> dict[str, Any]:
    """把模型原文解析为 JSON 对象；**解析不出就抛**，绝不返回"假装空"的 dict。

    分档（与 v1 模板第 59 行拒答兜底不冲突）：
    - 合法 JSON 且 ``entities`` 为空 → **正常空结果**（模型真的没抽到）；
    - 空响应 / 非法 JSON / 顶层非对象 → :class:`LangextractError`（可重试）。
    """
    text = (raw or "").strip()
    if not text:
        raise LangextractError("LLM 返回内容为空，无法解析为 JSON")

    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced is not None else text

    try:
        payload: Any = json.loads(candidate)
    except json.JSONDecodeError:
        # 模型常在 JSON 前后加解释文字：截取首个完整 {...} 再试一次
        block = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if block is None:
            raise LangextractError(
                f"LLM 输出非法 JSON：未找到 JSON 对象（前 200 字: {text[:200]!r}）"
            ) from None
        try:
            payload = json.loads(block.group(0))
        except json.JSONDecodeError as exc:
            raise LangextractError(f"LLM 输出非法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LangextractError(
            f"LLM 输出结构非法（应为 JSON 对象，实际={type(payload).__name__}）"
        )
    return payload


def _entities_from_payload(
    payload: Mapping[str, Any], *, chunk_text: str, char_offset: int
) -> tuple[list[ExtractedEntity], dict[str, str]]:
    """按 Schema 解析实体；返回 ``(entities, 原id → 新id 映射)``。

    处置口径：
    - 未知 ``entity_type`` → 降级 ``RELATED``（原始名 log 留痕，v1 第 47 行）；
    - ``confidence`` < 0.5 或缺失 → 丢弃（v1 第 50 行，**不猜值**）；
    - ``char_start`` / ``char_end`` 合法 → 原样透传（仅加回块起点，与 mock 档同坐标系）；
      缺失 / 越界 → 用 ``mention`` 在 chunk 内回查；回查不到 → 丢弃（**不伪造偏移**）；
    - 模型给的 id **一律换新**：它会复用 few-shot 的 ``ent_001`` 之类，跨 chunk 撞 id。
    """
    raw_entities = payload.get("entities", [])
    if not isinstance(raw_entities, list):
        raise LangextractError(
            f"LLM 输出的 entities 结构非法（应为 list，实际={type(raw_entities).__name__}）"
        )

    entities: list[ExtractedEntity] = []
    id_map: dict[str, str] = {}
    malformed = 0
    low_confidence = 0

    for raw in raw_entities:
        if not isinstance(raw, dict):
            malformed += 1
            continue

        canonical_name = (
            str(raw.get("canonical_name") or "").strip()
            or str(raw.get("mention") or "").strip()
        )
        mention = str(raw.get("mention") or canonical_name).strip()
        confidence = _coerce_confidence(raw.get("confidence"))
        span = _resolve_char_span(
            raw, chunk_text=chunk_text, mention=mention, char_offset=char_offset
        )

        if not canonical_name or confidence is None or span is None:
            malformed += 1
            continue
        if confidence < _MIN_CONFIDENCE:
            low_confidence += 1
            continue

        raw_type = str(raw.get("entity_type") or "").strip()
        entity_type = raw_type if raw_type in ENTITY_TYPES else _FALLBACK_TYPE
        if raw_type and raw_type != entity_type:
            logger.bind(unknown_entity_type=raw_type).warning(
                "langextract_entity_type_downgraded"
            )

        entity_id = f"ent_{uuid.uuid4().hex[:12]}"
        original_id = str(raw.get("id") or "").strip()
        if original_id:
            id_map[original_id] = entity_id

        entities.append(
            ExtractedEntity(
                id=entity_id,
                canonical_name=canonical_name,
                entity_type=entity_type,
                mention=mention,
                char_start=span[0],
                char_end=span[1],
                confidence=confidence,
            )
        )

    if malformed or low_confidence:
        logger.bind(malformed=malformed, low_confidence=low_confidence).warning(
            "langextract_entities_dropped"
        )
    return entities, id_map


def _relations_from_payload(
    payload: Mapping[str, Any], id_map: Mapping[str, str]
) -> list[ExtractedRelation]:
    """按 Schema 解析关系；端点不在实体集合内 → 丢弃（与 ``_clamp_relations`` 同口径）。"""
    raw_relations = payload.get("relations", [])
    if not isinstance(raw_relations, list):
        raise LangextractError(
            f"LLM 输出的 relations 结构非法（应为 list，实际={type(raw_relations).__name__}）"
        )

    relations: list[ExtractedRelation] = []
    malformed = 0
    low_confidence = 0

    for raw in raw_relations:
        if not isinstance(raw, dict):
            malformed += 1
            continue

        source = id_map.get(str(raw.get("source_entity_id") or "").strip())
        target = id_map.get(str(raw.get("target_entity_id") or "").strip())
        confidence = _coerce_confidence(raw.get("confidence"))

        if source is None or target is None or confidence is None:
            malformed += 1
            continue
        if confidence < _MIN_CONFIDENCE:
            low_confidence += 1
            continue

        raw_type = str(raw.get("relation_type") or "").strip()
        relation_type = raw_type if raw_type in RELATION_TYPES else _FALLBACK_TYPE
        if raw_type and raw_type != relation_type:
            logger.bind(unknown_relation_type=raw_type).warning(
                "langextract_relation_type_downgraded"
            )

        relations.append(
            ExtractedRelation(
                id=f"rel_{uuid.uuid4().hex[:12]}",
                source_entity_id=source,
                target_entity_id=target,
                relation_type=relation_type,
                evidence=str(raw.get("evidence") or "").strip(),
                confidence=confidence,
            )
        )

    if malformed or low_confidence:
        logger.bind(malformed=malformed, low_confidence=low_confidence).warning(
            "langextract_relations_dropped"
        )
    return relations


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
        engine: str = ENGINE_LLM,
        chunk_extractor: ChunkExtractorFn | None = None,
        llm_invoker: LlmInvokerFn | None = None,
    ) -> None:
        if provider != "langextract":
            # 未知档位显式报错（与 llm_provider / parser_provider 同策略，
            # 静默回退会掩盖配置错误——plan §4.4 纪律）。
            raise LangextractError(
                f"未知 extraction_provider={provider!r}（当前仅支持 'langextract'）"
            )
        if engine not in ENGINES:
            # 同上：未知档位**绝不**静默回退到 mock（那会把配置错误伪装成"抽到了"）
            raise LangextractError(
                f"未知 extraction_engine={engine!r}（当前仅支持 'llm' / 'mock'）"
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
        self._prompt_version = prompt_version
        self._engine = engine
        # 优先级：显式注入 > 引擎档位。注入永远是第一位的（单测零外部依赖靠它）
        if chunk_extractor is not None:
            self._chunk_extractor: ChunkExtractorFn = chunk_extractor
        elif engine == ENGINE_MOCK:
            self._chunk_extractor = _default_extract_chunk
        else:
            self._chunk_extractor = _build_llm_chunk_extractor(
                prompt_version=prompt_version,
                invoker=llm_invoker or _default_llm_invoke,
            )

    # -------------------------------------------------------------- 工厂

    @classmethod
    def from_settings(cls) -> LangextractClient:
        """从 settings 构造默认客户端（``document.extract`` 执行体使用）。

        ``settings.extraction_engine`` 的**唯一消费点**（check_seams 判据 2）：
        ``llm`` 档在这里把真实 LLM 通道接进链路。
        """
        settings = get_settings()
        return cls(
            provider=settings.extraction_provider,
            max_chars_per_chunk=settings.extraction_max_chars_per_chunk,
            max_entities_per_doc=settings.extraction_max_entities_per_doc,
            max_relations_per_doc=settings.extraction_max_relations_per_doc,
            prompt_version=settings.extraction_prompt_version,
            engine=settings.extraction_engine,
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
                "kg_extraction", version=_prompt_version_number(self._prompt_version)
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

        # Sprint 6 批次 A-1：切块本身即 Chunk 证据节点的来源。
        # 与 entities 同坐标系（绝对字符区间），落 chunks.json 供 kg.build 消费。
        raw_chunks = _split_into_chunks(full_md_text, self._max_chars_per_chunk)
        chunks = [
            ExtractedChunk(
                id=_new_chunk_id(),
                char_start=chunk_start,
                char_end=chunk_start + len(chunk_text),
                text=chunk_text,
            )
            for chunk_start, chunk_text in raw_chunks
        ]

        all_entities: list[ExtractedEntity] = []
        all_relations: list[ExtractedRelation] = []
        failed_chunks: list[FailedChunk] = []
        # contextualize：让 chunk 级日志（含 llm 档的调用日志）自动带上 trace_id
        with logger.contextualize(
            trace_id=str(trace_id),
            document_id=str(document_id),
            engine=self._engine,
        ):
            for chunk_index, (chunk_start, chunk_text) in enumerate(raw_chunks):
                with logger.contextualize(
                    chunk_index=chunk_index, chunk_offset=chunk_start
                ):
                    entities, relations, reason = self._extract_chunk_tolerant(
                        chunk_text, chunk_start
                    )
                if reason is not None:
                    failed_chunks.append(
                        FailedChunk(
                            index=chunk_index,
                            char_offset=chunk_start,
                            reason=reason[:_REASON_SNIPPET],
                        )
                    )
                    continue
                all_entities.extend(entities)
                all_relations.extend(relations)

            if chunks and len(failed_chunks) == len(chunks):
                # 全败 = 基础设施故障（key / 网络 / 配额），**不许**当成"这份文档没实体"
                raise LangextractError(
                    f"全部 {len(chunks)} 个 chunk 抽取失败（首个错误: "
                    f"{failed_chunks[0].reason}）"
                )

        entities = _clamp_entities(all_entities, self._max_entities_per_doc)
        relations = _clamp_relations(
            all_relations, entities, self._max_relations_per_doc
        )

        logger.bind(
            trace_id=str(trace_id),
            document_id=str(document_id),
            engine=self._engine,
            chunk_count=len(chunks),
            failed_chunk_count=len(failed_chunks),
            # 裁剪前后都留痕：S7.1 真机发现，单文档上限会把法人 / 地址这类
            # 低密度但高价值的实体裁掉（蛇口 p1-190：裁剪后 500，缪建民 / 建国路
            # 全部落榜）。没有这个字段，事后根本看不出"丢了多少"。
            entity_count_before_clamp=len(all_entities),
            entity_count=len(entities),
            relation_count_before_clamp=len(all_relations),
            relation_count=len(relations),
        ).info("langextract_done")

        return ExtractionResult(
            document_id=document_id,
            trace_id=trace_id,
            entities=entities,
            relations=relations,
            chunks=chunks,
            failed_chunks=failed_chunks,
        )

    # -------------------------------------------------------------- 容错

    def _extract_chunk_tolerant(
        self, chunk_text: str, char_offset: int
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation], str | None]:
        """跑一个 chunk；失败就地重试 1 次，仍失败则返回 ``reason`` 交上层跳过。

        **只**兜 :class:`LangextractError`（可重试的业务错误）。注入抽取器抛出的其它
        异常一律向上冒泡——那不是"模型抽风"，是 bug，吞掉会让缺陷隐形。
        """
        reason: str | None = None
        for attempt in range(1, _CHUNK_MAX_ATTEMPTS + 1):
            try:
                entities, relations = self._chunk_extractor(chunk_text, char_offset)
            except LangextractError as exc:
                reason = str(exc)[:_REASON_SNIPPET]
                if attempt < _CHUNK_MAX_ATTEMPTS:
                    logger.bind(attempt=attempt, reason=reason).warning(
                        "langextract_chunk_retry"
                    )
                    continue
                logger.bind(
                    attempts=attempt, char_offset=char_offset, reason=reason
                ).warning("langextract_chunk_failed")
                return [], [], reason
            return entities, relations, None
        return [], [], reason  # pragma: no cover - _CHUNK_MAX_ATTEMPTS >= 1 保证不可达


# ------------------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------------------


def _new_chunk_id() -> str:
    """生成 ``chunk-<hex12>`` 形式的 ``chunk_id``。

    前缀 ``chunk-`` 与 ``agents.py`` 的引用前缀校验对齐（``doc-`` 为文档级降级档）。
    """
    return f"chunk-{uuid.uuid4().hex[:12]}"


def _prompt_version_number(prompt_version: str) -> int:
    """``kg_extraction_v1`` / ``v1`` → 1（``prompt_loader`` 的版本参数）。"""
    try:
        return int(prompt_version.rsplit("v", 1)[-1])
    except (ValueError, IndexError) as exc:
        raise LangextractError(
            f"无法解析 extraction_prompt_version={prompt_version!r}"
            "（应形如 'kg_extraction_v1' / 'v1'）"
        ) from exc


def _is_int(value: object) -> bool:
    """``bool`` 是 ``int`` 子类，必须排除（`True` 当偏移会静默错位）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _coerce_confidence(raw: object) -> float | None:
    """置信度 → float；缺失 / 非数值 → ``None``（由调用方丢弃，**不猜值**）。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            return None
    return None


def _resolve_char_span(
    raw: Mapping[str, Any], *, chunk_text: str, mention: str, char_offset: int
) -> tuple[int, int] | None:
    """定出实体在**全文**中的绝对区间；定不出来返回 ``None``（绝不伪造偏移）。

    Sprint 7.1 口径（用户已拍板，见 ``changes/Sprint7.1/tasks.md`` §2.1 末条）：
    **模型自报偏移与 ``mention`` 不符时，以 ``mention`` 回查为准**——7.0 真机
    top20 里 14/20 的模型偏移并不指向它自己的 ``mention``（LLM 自报偏移不可靠），
    照单全收会让证据回查漂到错误位置。

    1. 模型给了合法区间**且**区间文本 == ``mention`` → 采用（原文锚点一致）；
    2. 否则用 ``mention`` 在 chunk 内回查（原文定位，不是猜）；不一致时打
       ``langextract_char_span_mismatch`` WARNING 留痕；
    3. 都失败 → ``None``（调用方丢弃该实体）。
    """
    start_raw = raw.get("char_start")
    end_raw = raw.get("char_end")
    if _is_int(start_raw) and _is_int(end_raw):
        start = char_offset + int(start_raw)  # type: ignore[arg-type]
        end = char_offset + int(end_raw)  # type: ignore[arg-type]
        if 0 <= start <= end <= char_offset + len(chunk_text):
            if chunk_text[start - char_offset : end - char_offset] == mention:
                return start, end
            logger.bind(
                model_span=(int(start_raw), int(end_raw)),  # type: ignore[arg-type]
                mention=mention[:_REASON_SNIPPET],
            ).warning("langextract_char_span_mismatch")
    if mention:
        found = chunk_text.find(mention)
        if found >= 0:
            return char_offset + found, char_offset + found + len(mention)
    return None


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
    "ENGINES",
    "ENGINE_LLM",
    "ENGINE_MOCK",
    "ENTITY_TYPES",
    "ExtractedChunk",
    "FailedChunk",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractionResult",
    "LangextractClient",
    "LangextractError",
    "LlmInvokerFn",
    "RELATION_TYPES",
]
