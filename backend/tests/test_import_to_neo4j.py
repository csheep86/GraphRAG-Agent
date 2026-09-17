"""阶段九：Neo4j 导入脚本 + GraphService 关系投影的单元测试。

**不触碰 Neo4j**：只测纯函数（解析 / 规范化 / 类型映射），因此可在 CI 无 Neo4j
环境下运行。真实写入链路由 `scripts/import_to_neo4j.py` 的 `--dry-run`
与 `[self-check]` 自检覆盖。

回归重点：`relations[].head / tail` 是**实体名**而非 `entities[].id`，
若按 id 匹配会让所有关系**静默丢失**（曾真实发生，`count(r)` 为 0）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.graphs import _relation_type
from scripts.import_to_neo4j import (
    DEFAULT_INPUT,
    ImportError_,
    build_entity_rows,
    build_relation_rows,
    load_source,
)

# --------------------------------------------------------------------------- #
# 测试夹具
# --------------------------------------------------------------------------- #

_MINIMAL_SOURCE: dict = {
    "schema_version": "1.0",
    "entities": [
        {
            "id": "e1",
            "name": "智能制造",
            "type": "业务板块",
            "attributes": {"pii_flags": ["sensitive"], "keep": "ok"},
            "char_interval": {"start_pos": 0, "end_pos": 4},
            "alignment_status": "match_exact",
            "grounded": True,
            "auto_created": False,
            "evidence": "智能制造板块",
        },
        {
            "id": "e7",
            "name": "营业收入",
            "type": "财务指标",
            "attributes": {},
            "char_interval": None,
            "alignment_status": "match_fuzzy",
            "grounded": True,
            "auto_created": False,
            "evidence": "营业收入",
        },
    ],
    "relations": [
        {
            "id": "r1",
            "head": "智能制造",
            "head_type": "公司",
            "relation": "具有财务指标",
            "tail": "营业收入",
            "tail_type": "财务指标",
            "attributes": {"pii_flags": ["x"]},
            "derived": True,
            "char_interval": {"start_pos": 10, "end_pos": 20},
            "alignment_status": "derived",
            "evidence": "智能制造...营业收入",
        },
        {
            "id": "r2",
            "head": "智能制造",
            "head_type": "公司",
            "relation": "具有财务指标",
            "tail": "不存在的实体",
            "tail_type": "财务指标",
            "attributes": {},
            "derived": True,
            "char_interval": None,
            "alignment_status": "derived",
            "evidence": "",
        },
    ],
}


# --------------------------------------------------------------------------- #
# load_source
# --------------------------------------------------------------------------- #


def test_load_source_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"schema_version": "9.9", "entities": [], "relations": []}),
        encoding="utf-8",
    )
    with pytest.raises(ImportError_, match="schema_version"):
        load_source(path)


def test_load_source_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImportError_, match="不存在"):
        load_source(tmp_path / "nope.json")


# --------------------------------------------------------------------------- #
# build_entity_rows
# --------------------------------------------------------------------------- #


def test_build_entity_rows_strips_pii_flags() -> None:
    rows = build_entity_rows(_MINIMAL_SOURCE, org_id=None)
    assert len(rows) == 2
    # M2 §5.3：pii_flags 严禁落库
    assert "pii_flags" not in json.loads(rows[0]["attributes_json"])
    assert json.loads(rows[0]["attributes_json"]) == {"keep": "ok"}
    assert rows[0]["char_start"] == 0
    assert rows[0]["char_end"] == 4
    assert rows[1]["char_start"] is None


def test_build_entity_rows_dedupes_by_id() -> None:
    source = {
        "schema_version": "1.0",
        "entities": _MINIMAL_SOURCE["entities"] + [_MINIMAL_SOURCE["entities"][0]],
        "relations": [],
    }
    assert len(build_entity_rows(source, org_id=None)) == 2


# --------------------------------------------------------------------------- #
# build_relation_rows —— 回归：端点必须按「实体名 → 实体 id」解析
# --------------------------------------------------------------------------- #


def test_build_relation_rows_resolves_entity_names_to_ids() -> None:
    entity_rows = build_entity_rows(_MINIMAL_SOURCE, org_id=None)
    name_to_id = {row["name"]: row["id"] for row in entity_rows}

    rows, unresolved = build_relation_rows(_MINIMAL_SOURCE, name_to_id)

    assert len(rows) == 1, "r2 端点无法解析，应被记为 unresolved 而非静默丢弃"
    assert rows[0]["head"] == "e1", "head 必须解析为实体 id，而不是实体名"
    assert rows[0]["tail"] == "e7"

    assert len(unresolved) == 1, "无法解析的关系必须上报，禁止静默丢弃"
    assert "不存在的实体" in unresolved[0]


def test_build_relation_rows_maps_relation_name_to_whitelisted_token() -> None:
    entity_rows = build_entity_rows(_MINIMAL_SOURCE, org_id=None)
    name_to_id = {row["name"]: row["id"] for row in entity_rows}

    rows, _ = build_relation_rows(_MINIMAL_SOURCE, name_to_id)

    assert rows[0]["token"] == "HAS_FINANCIAL_INDICATOR"
    assert rows[0]["relation_name"] == "具有财务指标", "原始关系名必须保留"
    # pii_flags 不落库
    assert "pii_flags" not in json.loads(rows[0]["attributes_json"])


def test_build_relation_rows_unknown_relation_falls_back_to_related() -> None:
    source = {
        "schema_version": "1.0",
        "entities": _MINIMAL_SOURCE["entities"],
        "relations": [
            {
                "id": "rx",
                "head": "智能制造",
                "relation": "某种未登记的关系",
                "tail": "营业收入",
            }
        ],
    }
    name_to_id = {row["name"]: row["id"] for row in build_entity_rows(source, org_id=None)}
    rows, unresolved = build_relation_rows(source, name_to_id)

    assert unresolved == []
    assert rows[0]["token"] == "RELATED"  # 白名单兜底，绝不透传原始字符串


def test_whitelist_blocks_cypher_injection_attempt() -> None:
    """恶意关系名不得进入 Cypher 的 token 位置。"""
    source = {
        "schema_version": "1.0",
        "entities": _MINIMAL_SOURCE["entities"],
        "relations": [
            {
                "id": "rbad",
                "head": "智能制造",
                "relation": "X]->() DELETE n //",
                "tail": "营业收入",
            }
        ],
    }
    name_to_id = {row["name"]: row["id"] for row in build_entity_rows(source, org_id=None)}
    rows, _ = build_relation_rows(source, name_to_id)

    assert rows[0]["token"] == "RELATED"
    assert "DELETE" not in rows[0]["token"]


# --------------------------------------------------------------------------- #
# 真实产物回归（仓库内已提交 bridge_web_demo/output.json）
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not DEFAULT_INPUT.is_file(), reason="bridge_web_demo/output.json 不存在")
def test_real_bridge_output_is_fully_resolvable() -> None:
    """真实产物：23 实体 / 12 关系，且关系端点**全部**可解析（回归静默丢失 bug）。"""
    data = load_source(DEFAULT_INPUT)
    entity_rows = build_entity_rows(data, org_id=None)
    name_to_id = {row["name"]: row["id"] for row in entity_rows}
    relation_rows, unresolved = build_relation_rows(data, name_to_id)

    assert len(entity_rows) == 23
    assert len(relation_rows) == 12
    assert unresolved == [], f"存在无法解析的关系端点: {unresolved}"

    # 每条关系的端点必须命中实体 id
    entity_ids = {row["id"] for row in entity_rows}
    for row in relation_rows:
        assert row["head"] in entity_ids
        assert row["tail"] in entity_ids


# --------------------------------------------------------------------------- #
# GraphService 关系类型受控投影
# --------------------------------------------------------------------------- #


def test_relation_type_passes_through_contract_enum() -> None:
    for value in ("HAS_CHUNK", "MENTIONS", "SUPPORTED_BY", "AFFILIATED_WITH", "SUPPLIES_TO", "PARTY_TO"):
        assert _relation_type(value) == value


def test_relation_type_projects_bridge_types_to_contract_enum() -> None:
    """桥梁专有类型投影为 MENTIONS；真实名由 properties['relation_name'] 承载。"""
    assert _relation_type("HAS_FINANCIAL_INDICATOR") == "MENTIONS"
    assert _relation_type("OPERATES_SEGMENT") == "MENTIONS"
    assert _relation_type("RELATED") == "MENTIONS"
    assert _relation_type("AFFILIATED_WITH") == "AFFILIATED_WITH"


def test_relation_type_never_returns_invalid_value() -> None:
    """任意未知输入都必须落在契约枚举内，否则 GraphEdge 会触发校验错误。"""
    contract_enum = {
        "HAS_CHUNK",
        "MENTIONS",
        "SUPPORTED_BY",
        "AFFILIATED_WITH",
        "SUPPLIES_TO",
        "PARTY_TO",
    }
    for raw in ("", None, "X]->() DELETE n //", "未知类型", 123):
        assert _relation_type(raw) in contract_enum
