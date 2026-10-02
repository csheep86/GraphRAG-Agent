"""业务域本体读取（M6 §4.1；Sprint 9.5 批次 B1-follow）。

**为什么单独成文件**：本体是**每 org 一套**的域配置，消费方不止一处——

1. 图谱图例分类：``entity_type`` → ``category``（B1-follow，本文件当前主责）；
2. M2 抽取的 ``entity_types`` / ``relation_types`` 参数化注入（M6 §5.2，批次 B2 消费）。

**为什么 ``category`` 放本体而不是硬编码**：``category`` 是**契约级 4 值枚举**
（``topic`` / ``norm`` / ``org`` / ``system``，见 ``schemas/graph.py``）。
若按域往 ``graphs._ENTITY_TYPE_TO_CATEGORY`` 里堆类型名，换一个业务域就要改一次
代码，且该表会随域数**线性膨胀**——这正是 B1-follow 明确要避免的"硬编码一坨"。
放进本体 ⇒ **换域只换数据，后端代码与 API 契约均不动**。

**降级纪律（重要）**：本图例分类属**展示增强**，不是数据正确性。因此本体缺失 /
无 ``db`` 会话 / 条目缺 ``category`` / ``category`` 值非法时，一律**回落**到
``graphs._ENTITY_TYPE_TO_CATEGORY`` 硬编码表与 ``topic`` 兜底，**不**阻断查询、
**不**抛异常。但非法值必须 **warn 日志显式留痕**——静默吞掉是本项目要拦的"假做"。

**不做**跨请求缓存：本批次的调用频次是「每请求一次」（overview 与 entity_detail
各解析一次后全量复用），逐节点查库的问题已被消除；盲目加缓存会引入"换版后图例
陈旧"的新失效模式，故先不做，等实测有需要再按 ADR 登记引入。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_args

from loguru import logger
from sqlalchemy import select

from app.db.models import OntologySchema
from app.prompts import load_prompt
from app.schemas import GraphCategory

__all__ = [
    "DEFAULT_MAX_ENTITY_TYPES",
    "DEFAULT_MAX_RELATION_TYPES",
    "OntologySuggestError",
    "OntologySuggestion",
    "entity_type_categories",
    "extraction_type_vocabulary",
    "load_active_ontology",
    "suggest_ontology_types",
]

#: 冷启动建议用的 Prompt 名（``prompts/ontology_suggest_v1.md``）。
#: **为什么不复用既有 Prompt**：spec §3.1 验收 1 原文写「调用 ``kg_qa_v1.md``」，
#: 但那是**问答**模板，拿它生成本体建议属语义错配，建议质量无法归因。
#: 验收 1 的「不修改 prompt」应理解为「不篡改既有 prompt」，而非「不许新增版本」——
#: PRD H9 约束的是 P2 之前的模块，M6 在 P5，允许新增版本号。
#: ⚠️ 该差异已登记为定稿增补项（见 ``changes/archive/2026-10-02-P0-m6-finalization/integration-log.md``）。
_SUGGEST_PROMPT_NAME = "ontology_suggest"

#: 冷启动建议的**条数上限**（M6 §3.1 验收 1 的 PoC 护栏）。
#: 为什么要截断：类型名会被整段塞进抽取 Prompt 的词表，LLM 一高兴返回 40 个类型
#: ⇒ 词表膨胀、抽取误配率上升、单次调用成本翻倍。**不靠 prompt 自觉**，在这里硬截。
DEFAULT_MAX_ENTITY_TYPES = 12
DEFAULT_MAX_RELATION_TYPES = 12

#: 建议结果里每条类型**允许保留的键**（其余键一律丢弃，避免脏数据渗进词表）。
#: 与 ``OntologySchema`` 的 JSON 列形状对齐（M6 §4.1：每项 ``{name, description?}`` /
#: ``{name, head_types, tail_types, description?}``）。
_ENTITY_TYPE_KEYS = ("name", "description")
_RELATION_TYPE_KEYS = ("name", "head_types", "tail_types", "description")

#: 合法 ``category`` 取值，**由契约枚举反推**（不二次硬编码）。
#: 契约 ``GraphCategory`` 一旦增减取值，这里自动跟随，不会静默失配。
_VALID_CATEGORIES: frozenset[str] = frozenset(get_args(GraphCategory))


def load_active_ontology(*, db: Any, org_id: Any) -> OntologySchema | None:
    """取该 org 的 ``status='active'`` 本体行；无则返回 ``None``。

    **仅 active 对外可见**（M6 §4.1）：``superseded`` 是换域时旧版本的终态，
    不得参与查询，否则会出现"换了域却仍按旧本体着色"。

    :param db: SQLAlchemy 会话；``None`` 时直接返回 ``None``（脚本 / 无会话场景）。
    :param org_id: 租户 ID；``None`` 时返回 ``None``（本体按 org 隔离，ADR-0003）。
    """
    if db is None or org_id is None:
        return None

    return db.scalar(
        select(OntologySchema).where(
            OntologySchema.org_id == org_id,
            OntologySchema.status == "active",
        )
    )


def extraction_type_vocabulary(
    *, db: Any, org_id: Any
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """从本体读出 M2 抽取用的类型词表：``(entity_types, relation_types)``。

    M6 §5.2 参数化注入（Sprint 9.5 批次 B2）：``entity_types`` / ``relation_types``
    由该 org 的 active 本体给出，使得「换业务域」只改数据、不改 Prompt 版本。
    **不新增 Prompt 版本**——``kg_extraction_v2`` 早已把这两个枚举声明为占位符。

    降级口径与 :func:`entity_type_categories` 一致：**读不到就返回空元组**，
    由调用方（``LangextractClient``）回落内置枚举，不阻断抽取。
    这里**不**假设「没有本体 = 金融域」——内置默认值归抽取侧管，本体模块只管本体。
    """
    row = load_active_ontology(db=db, org_id=org_id)
    if row is None:
        return (), ()

    entity_types = _type_names(row.entity_types)
    relation_types = _type_names(row.relation_types)
    logger.bind(
        org_id=str(org_id),
        entity_type_count=len(entity_types),
        relation_type_count=len(relation_types),
    ).info("ontology_extraction_vocabulary_loaded")
    return entity_types, relation_types


def _type_names(items: Any) -> tuple[str, ...]:
    """取本体里各类 Type 的 ``name`` 元组（保序去重）。

    脏条目（非 dict / 缺 ``name``）跳过且不留痕：这里的上下文是"抽词表"，
    少一个类型名会被调用方的空词表回落整体兜住，不像 ``category`` 那样需要
    警示"配了却没生效"。
    """
    if not isinstance(items, list):
        return ()
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name)
    return tuple(names)


class OntologySuggestError(RuntimeError):
    """冷启动建议失败：LLM 返回的内容解析不出类型集。

    **为什么不静默回落**：冷启动是用户**显式**发起的动作，解析失败就该报错让他重试。
    悄悄塞一组"看起来合理"的类型 ⇒ 用户以为系统给出了建议，实际是我们编的——
    这正是本项目要拦的"假做"（与 ``entity_type_categories`` 的降级纪律**不同**：
    那条管的是**展示增强**，本条管的是**用户决策依据**）。
    """


@dataclass(frozen=True, slots=True)
class OntologySuggestion:
    """冷启动的**建议结果**（M6 §3.1 验收 1：仅建议、未生效）。

    ⚠️ 本对象**不含** ``org_id`` / ``db``，也不提供落库方法——构造不出
    「未确认即生效」的路径。真正的机械保证在 :func:`suggest_ontology_types`
    的**签名里根本没有会话参数**，比「记得别写库」这条注释可靠。
    """

    entity_types: tuple[dict[str, Any], ...]
    relation_types: tuple[dict[str, Any], ...]
    #: 产出该建议的 Prompt 名与版本（溯源用；M6 §3.5 验收 10 的 trace 口径）
    prompt_name: str
    prompt_version: int


def suggest_ontology_types(
    *,
    domain_description: str,
    llm_invoke: Callable[[str], str] | None = None,
    max_entity_types: int = DEFAULT_MAX_ENTITY_TYPES,
    max_relation_types: int = DEFAULT_MAX_RELATION_TYPES,
) -> OntologySuggestion:
    """按业务域描述**建议**一组实体 / 关系类型（M6 §3.1 验收 1 的端到端 PoC）。

    **只建议、不生效**：本函数**不接会话参数** ⇒ 结构上不可能写 ``ontology_schemas``。
    生效（写 ``status='active'``）只能走确认路径（``POST /ontology/confirm``，
    **归 P5-M6 批次，本 PoC 不做**）。这是验收 1「未确认的 schema 不写入」的机械落实，
    也是 GAP-F2「严禁 LLM 自动修改本体」的落点。

    :param domain_description: 业务域描述（**人工输入**；不校验非空以外的东西）。
    :param llm_invoke: 可注入的 LLM 调用 ``(prompt) -> text``。``None`` 走接缝 3 默认实现。
        注入位的存在理由：PoC 必须能在 CI 里**零成本、可复现**地跑，真 LLM 只能在
        有 key 的环境做一次留证（见 ``scripts/probe_ontology_suggest.py``）。
    :param max_entity_types: 实体类型条数上限（硬截，不靠 prompt 自觉）。
    :param max_relation_types: 关系类型条数上限。
    :raises OntologySuggestError: LLM 返回解析不出类型集（**不**回落内置枚举）。
    """
    template = load_prompt(_SUGGEST_PROMPT_NAME)
    prompt = template.render(
        domain_description=domain_description,
        max_entity_types=str(max_entity_types),
        max_relation_types=str(max_relation_types),
    )

    invoke = llm_invoke or _default_suggest_invoke
    raw = invoke(prompt)

    payload = _parse_json_object(raw)
    if payload is None:
        # 只记长度与首字符类别，**不落** prompt / 响应原文（可能含业务敏感描述）。
        raise OntologySuggestError(
            "冷启动建议解析失败：LLM 未返回单个 JSON 对象"
            f"（prompt={template.name}_v{template.version} "
            f"response_chars={len(raw)}）"
        )

    entity_types = _normalize_entity_types(
        payload.get("entity_types"), max_entity_types
    )
    relation_types = _normalize_relation_types(
        payload.get("relation_types"), max_relation_types
    )
    if not entity_types and not relation_types:
        raise OntologySuggestError(
            "冷启动建议解析为空：JSON 合法但无可用类型"
            f"（prompt={template.name}_v{template.version}）"
        )

    logger.bind(
        prompt=f"{template.name}_v{template.version}",
        entity_type_count=len(entity_types),
        relation_type_count=len(relation_types),
    ).info("ontology_suggestion_produced")
    return OntologySuggestion(
        entity_types=entity_types,
        relation_types=relation_types,
        prompt_name=template.name,
        prompt_version=template.version,
    )


def _default_suggest_invoke(prompt: str) -> str:
    """默认 LLM 调用：经**接缝 3** ``build_chat_model()``，不自建客户端。

    与 ``extraction.langextract._default_llm_invoke`` 同构，但**不复用那个私有名**——
    跨模块引用下划线名会把两个模块焊死；这里只有几行，重复成本 < 耦合成本。
    """
    from time import perf_counter

    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.providers.llm import build_chat_model

    started = perf_counter()
    response = build_chat_model().invoke(
        [SystemMessage(content=prompt), HumanMessage(content="请只输出 JSON。")]
    )
    elapsed_ms = round((perf_counter() - started) * 1000)
    content = str(response.content)

    # 只记数值，不落 prompt 原文与响应原文（CODEBUDDY 日志与可观测性规则）
    logger.bind(
        elapsed_ms=elapsed_ms,
        prompt_chars=len(prompt),
        response_chars=len(content),
    ).info("ontology_suggest_llm_call")
    return content


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出里抠出**单个 JSON 对象**；抠不出返回 ``None``（由调用方报错）。

    容忍 Markdown 代码块围栏——实测 LLM 十有八九会包一层 ```json，
    不剥掉就等于把"建议成功"判成失败。但围栏之外的解释文字**不**逐个抢救：
    那是模型没遵守格式，应当报错重来，而不是我们替它猜。
    """
    text = raw.strip()
    if text.startswith("```"):
        # 去掉首行围栏（可能带语言标记）与末尾围栏
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_entity_types(items: Any, limit: int) -> tuple[dict[str, Any], ...]:
    """规范化实体类型：保序去重、丢脏条目、超上限截断。

    脏条目（非 dict / 缺 ``name`` / ``name`` 非字符串）**跳过并 warn 留痕**：
    本体的产出方是 LLM，脏值静默丢弃会让人以为"配了就生效"。
    """
    if not isinstance(items, list):
        logger.warning(f"冷启动建议 entity_types 不是数组: type={type(items).__name__}")
        return ()

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            logger.warning(f"冷启动建议跳过非对象条目: {item!r}")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            logger.warning(f"冷启动建议跳过缺 name 的条目: {item!r}")
            continue
        name = name.strip()
        if name in seen:
            continue
        seen.add(name)

        entry: dict[str, Any] = {"name": name}
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()
        result.append(entry)

        if len(result) >= limit:
            logger.warning(
                f"冷启动建议实体类型超上限 {limit}，已截断（不静默丢弃信息）"
            )
            break

    return tuple(result)


def _normalize_relation_types(items: Any, limit: int) -> tuple[dict[str, Any], ...]:
    """规范化关系类型：同 :func:`_normalize_entity_types`，另校验首尾类型引用。

    ``head_types`` / ``tail_types`` 必须是字符串数组；缺或脏 ⇒ 记 warn 并置空数组
    （**不**因此丢弃整条关系——关系名本身仍有价值，空的首尾类型由抽取侧兜底）。
    """
    if not isinstance(items, list):
        logger.warning(
            f"冷启动建议 relation_types 不是数组: type={type(items).__name__}"
        )
        return ()

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            logger.warning(f"冷启动建议跳过非对象条目: {item!r}")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            logger.warning(f"冷启动建议跳过缺 name 的条目: {item!r}")
            continue
        name = name.strip()
        if name in seen:
            continue
        seen.add(name)

        entry: dict[str, Any] = {
            "name": name,
            "head_types": _str_list(item.get("head_types"), name, "head_types"),
            "tail_types": _str_list(item.get("tail_types"), name, "tail_types"),
        }
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()
        result.append(entry)

        if len(result) >= limit:
            logger.warning(
                f"冷启动建议关系类型超上限 {limit}，已截断（不静默丢弃信息）"
            )
            break

    return tuple(result)


def _str_list(value: Any, type_name: str, field: str) -> list[str]:
    """取字符串数组；脏值记 warn 后返回空数组（**不**编造内容）。"""
    if not isinstance(value, list):
        logger.warning(
            f"冷启动建议关系 {type_name} 的 {field} 不是数组，置空: {value!r}"
        )
        return []
    names = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(names) != len(value):
        logger.warning(
            f"冷启动建议关系 {type_name} 的 {field} 含非字符串项，已过滤: {value!r}"
        )
    return names


def entity_type_categories(*, db: Any, org_id: Any) -> dict[str, GraphCategory]:
    """从本体读出 ``{实体类型名: 图例分类}``；读不到一律返回空 dict。

    返回值**只含合法条目**——缺 ``category`` 或值非契约 4 值的条目会被跳过，
    由调用方回落到硬编码表。这样保证**契约不可能被本体里的脏数据击穿**。
    """
    row = load_active_ontology(db=db, org_id=org_id)
    if row is None:
        return {}

    entity_types = row.entity_types or []
    if not isinstance(entity_types, list):
        logger.warning(
            "本体 entity_types 不是数组，图例分类回落硬编码表: "
            f"org_id={org_id} type={type(entity_types).__name__}"
        )
        return {}

    categories: dict[str, GraphCategory] = {}
    for item in entity_types:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue

        category = item.get("category")
        if category is None:
            # 缺字段是**合法的**（旧本体 / 未标注的域）⇒ 静默跳过，交由硬编码表兜底。
            continue
        if category in _VALID_CATEGORIES:
            categories[str(name)] = category  # type: ignore[assignment]
        else:
            # 值非法必须留痕：本体是人工/LLM 产物，脏值静默兜底会让人误以为配置生效。
            logger.warning(
                "本体 category 取值非法，该类型回落硬编码表: "
                f"org_id={org_id} entity_type={name!r} category={category!r} "
                f"合法值={sorted(_VALID_CATEGORIES)}"
            )

    return categories
