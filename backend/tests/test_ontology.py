"""本体读取与图例分类（Sprint 9.5 批次 B1-follow）。

**为什么单列一个文件**：``app/services/ontology.py`` 是新增的本体读取入口，
B2 的 M6 §5.2 参数化注入也要复用它；把契约行为钉在这里，避免"本体改了但图例
没变"这类**静默失配**再次发生（2026-09-26 已因同族错配出过演示事故）。

覆盖四条纪律：
1. 本体**优先于**内置硬编码表；
2. 本体缺 ``category`` / 值非法 ⇒ 跳过并回落，**绝不**把脏值透给契约；
3. 无 db / 无 org_id ⇒ 空表，不抛异常（展示增强不阻断查询）；
4. 内置表（如 ``ORG``）**不受本体覆盖影响**。
"""

from __future__ import annotations

import uuid

from app.db.models import OntologySchema
from app.db.session import SessionLocal, init_db
from app.services.graphs import _resolve_category
from app.services.ontology import entity_type_categories

#: 每个用例用独立 org，避免相互污染（ontology_schemas 是每 org 一套）
_ORG_A = uuid.uuid4()
_ORG_B = uuid.uuid4()
_ORG_EMPTY = uuid.uuid4()


def _seed_ontology(
    org_id: uuid.UUID, entity_types: list[dict], *, status: str = "active"
) -> None:
    init_db()
    with SessionLocal() as db:
        db.add(
            OntologySchema(
                org_id=org_id,
                version=1,
                entity_types=entity_types,
                relation_types=[],
                domain_description="test",
                suggested_by_llm=False,
                confirmed_by_user=uuid.uuid4(),
                status=status,
                trace_id=uuid.uuid4(),
            )
        )
        db.commit()


def _categories(org_id: uuid.UUID, *, db=None) -> dict[str, str]:
    if db is None:
        with SessionLocal() as session:
            return entity_type_categories(db=session, org_id=org_id)
    return entity_type_categories(db=db, org_id=org_id)


def test_ontology_categories_are_read() -> None:
    """正常本体：每个带合法 category 的类型都应被读出。"""
    _seed_ontology(
        _ORG_A,
        [
            {"name": "EMPLOYEE", "category": "org", "description": ""},
            {"name": "POLICY_CLAUSE", "category": "norm", "description": ""},
            {"name": "WORK_TIME_SYSTEM", "category": "system", "description": ""},
            {"name": "ATTENDANCE_RECORD", "category": "topic", "description": ""},
        ],
    )
    assert _categories(_ORG_A) == {
        "EMPLOYEE": "org",
        "POLICY_CLAUSE": "norm",
        "WORK_TIME_SYSTEM": "system",
        "ATTENDANCE_RECORD": "topic",
    }


def test_missing_and_invalid_category_are_skipped() -> None:
    """缺字段 / 值非契约 4 值 ⇒ 跳过，由内置表兜底，**脏值不得透传**。"""
    _seed_ontology(
        _ORG_B,
        [
            {"name": "NO_CATEGORY", "description": ""},  # 缺字段：合法，静默跳过
            {"name": "BAD_VALUE", "category": "not-a-category"},  # 非法值：跳过
            {"name": "GOOD", "category": "org"},
        ],
    )
    assert _categories(_ORG_B) == {"GOOD": "org"}


def test_superseded_ontology_is_invisible() -> None:
    """``superseded`` 是换域的旧版本终态，**不得**参与着色。"""
    org = uuid.uuid4()
    _seed_ontology(org, [{"name": "OLD", "category": "org"}], status="superseded")
    assert _categories(org) == {}


def test_no_org_or_no_db_returns_empty() -> None:
    """无 db / 无 org_id ⇒ 空表（降级纪律：不抛、不阻断）。"""
    assert entity_type_categories(db=None, org_id=_ORG_A) == {}
    assert entity_type_categories(db=SessionLocal(), org_id=None) == {}
    # 该 org 完全没有本体行
    assert _categories(_ORG_EMPTY) == {}


def test_resolve_prefers_ontology_over_builtin() -> None:
    """本体优先：``EMPLOYEE`` 内置表里没有，本体给出 ``org`` 就必须用 ``org``。"""
    assert _resolve_category("EMPLOYEE") == "topic"  # 内置表无此类型
    assert _resolve_category("EMPLOYEE", categories={"EMPLOYEE": "org"}) == "org"


def test_resolve_keeps_builtin_when_ontology_silent() -> None:
    """本体没覆盖时内置表仍然生效，且空类型恒兜底 ``topic``。"""
    assert _resolve_category("ORG", categories={"EMPLOYEE": "org"}) == "org"
    assert _resolve_category("", categories={"EMPLOYEE": "org"}) == "topic"
    assert _resolve_category("MONEY", categories={"EMPLOYEE": "org"}) == "topic"
