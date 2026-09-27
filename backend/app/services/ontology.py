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

from typing import Any, get_args

from loguru import logger
from sqlalchemy import select

from app.db.models import OntologySchema
from app.schemas import GraphCategory

__all__ = ["entity_type_categories", "load_active_ontology"]

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
