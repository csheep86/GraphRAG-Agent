"""M6 §3.1 验收 1 的**冷启动建议 PoC** 测试（`changes/P0-m6-finalization` F1）。

**为什么单独成文件**：它验的不是某个端点，而是「域描述 → LLM 建议 → 可被抽取链路消费」
这条**通路是否走得通**（P1-5 硬闸门 / 风险 R2：schema-suggestion 模式此前未实测验证）。

**真机 vs fake 的分工**（决策点 D1）：
- 本文件**只用 fake**：CI 零成本、可复现，且不依赖 LLM 余额；
- 真 LLM 只跑**一次**留证，走 ``scripts/probe_ontology_suggest.py``（有 key 才跑）。
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models import OntologySchema
from app.db.session import SessionLocal, init_db
from app.services.ontology import (
    OntologySuggestError,
    extraction_type_vocabulary,
    suggest_ontology_types,
)

#: fake 返回的**合法**建议（故意混入脏条目，看规范化是否扛得住）
_FAKE_PAYLOAD = {
    "entity_types": [
        {"name": "COMPANY", "description": "法人主体"},
        {"name": "COMPANY"},  # 重复名 ⇒ 去重
        {"name": "  POLICY_CLAUSE  ", "description": "制度条款"},  # 带空白 ⇒ 修剪
        {"name": "EMPLOYEE"},  # 无 description ⇒ 不得凭空补一个
        {"name": ""},  # 空名 ⇒ 丢弃
        "not-a-dict",  # 非对象 ⇒ 丢弃
    ],
    "relation_types": [
        {
            "name": "PARTY_TO",
            "head_types": ["COMPANY"],
            "tail_types": ["COMPANY", 123],  # 含非字符串 ⇒ 过滤
            "description": "关联关系",
        },
        {"name": "CITES", "head_types": "not-a-list"},  # 脏 ⇒ 置空数组，不丢整条
    ],
}


def _fake_invoke(payload: object) -> object:
    """造一个**可注入**的 LLM 调用（签名 ``(prompt) -> str``）。

    ``payload`` 传 **str** 时原样返回（用来模拟"模型直接吐了一段带围栏的文本"）；
    传 dict 时才 ``json.dumps``——否则会把字符串再编码一层，测的就不是解析韧性了。
    """

    def _invoke(prompt: str) -> str:  # noqa: ARG001 - PoC 不关心 prompt 内容
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False)

    return _invoke


def test_suggest_normalizes_dirty_payload() -> None:
    """建议结果必须**规范化**后才可交给抽取链路：去重 / 修剪 / 丢脏条目。"""
    suggestion = suggest_ontology_types(
        domain_description="财务关联交易识别",
        llm_invoke=_fake_invoke(_FAKE_PAYLOAD),
    )

    assert [item["name"] for item in suggestion.entity_types] == [
        "COMPANY",
        "POLICY_CLAUSE",
        "EMPLOYEE",
    ]
    assert suggestion.entity_types[0]["description"] == "法人主体"
    # 缺 description 的条目不得凭空补一个（补了就是我们在替 LLM 编内容）
    assert "description" not in suggestion.entity_types[2]

    assert [item["name"] for item in suggestion.relation_types] == ["PARTY_TO", "CITES"]
    assert suggestion.relation_types[0]["head_types"] == ["COMPANY"]
    assert suggestion.relation_types[0]["tail_types"] == ["COMPANY"]
    assert suggestion.relation_types[1]["head_types"] == []  # 脏 ⇒ 空，**不**编造

    assert suggestion.prompt_name == "ontology_suggest"
    assert suggestion.prompt_version == 1


def test_suggest_tolerates_markdown_fence() -> None:
    """LLM 十有八九会包一层 ```json —— 剥不掉就把"成功"判成失败，不可接受。"""
    fenced = "```json\n" + json.dumps(_FAKE_PAYLOAD, ensure_ascii=False) + "\n```"
    suggestion = suggest_ontology_types(
        domain_description="考勤合规", llm_invoke=_fake_invoke(fenced)
    )
    assert suggestion.entity_types[0]["name"] == "COMPANY"


def test_suggest_raises_instead_of_silent_fallback() -> None:
    """解析失败必须**报错**，不得静默回落一组"看起来合理"的类型。

    理由写在 ``OntologySuggestError`` 的 docstring 里：冷启动是用户**显式**动作，
    悄悄编造建议 = 用户以为系统在给建议，实际是我们替他决定了。
    """
    with pytest.raises(OntologySuggestError):
        suggest_ontology_types(
            domain_description="财务", llm_invoke=_fake_invoke("抱歉，我无法完成该请求")
        )
    with pytest.raises(OntologySuggestError):
        # JSON 合法但一条可用类型都没有 ⇒ 同样不许当成"成功"
        suggest_ontology_types(
            domain_description="财务", llm_invoke=_fake_invoke({"entity_types": []})
        )


def test_suggest_writes_nothing_to_database() -> None:
    """**验收 1 的硬约束**：未确认的 schema **不写入** ``ontology_schemas``。

    机械保证是签名（``suggest_ontology_types`` 不接会话参数），这里再用**真库**复核一遍：
    换一个全新的 org，建议前后该 org 的行数都必须是 0。
    """
    init_db()
    org_id = uuid.uuid4()

    with SessionLocal() as session:
        before = (
            session.query(OntologySchema)
            .filter(OntologySchema.org_id == org_id)
            .count()
        )
    suggest_ontology_types(
        domain_description="财务关联交易识别", llm_invoke=_fake_invoke(_FAKE_PAYLOAD)
    )
    with SessionLocal() as session:
        after = (
            session.query(OntologySchema)
            .filter(OntologySchema.org_id == org_id)
            .count()
        )

    assert (before, after) == (0, 0)


def test_suggested_types_are_consumable_by_extraction_vocabulary() -> None:
    """端到端：建议出来的类型**能**被抽取链路的词表消费（验收 1 → 验收 2 的接缝）。

    用未落库的 ``OntologySchema`` 实例喂给 ``extraction_type_vocabulary``：
    写库（确认生效）归 P5-M6 批次，本 PoC 只验证"这个形状能被消费"。
    """
    suggestion = suggest_ontology_types(
        domain_description="财务关联交易识别", llm_invoke=_fake_invoke(_FAKE_PAYLOAD)
    )

    class _FakeSession:
        """只实现 ``scalar``：验证词表消费不需要真会话，也**不会**顺手写库。"""

        def scalar(self, *_args: object, **_kwargs: object) -> OntologySchema:
            return OntologySchema(
                org_id=uuid.uuid4(),
                version=1,
                entity_types=list(suggestion.entity_types),
                relation_types=list(suggestion.relation_types),
                domain_description="财务关联交易识别",
                suggested_by_llm=True,
            )

    entity_types, relation_types = extraction_type_vocabulary(
        db=_FakeSession(), org_id=uuid.uuid4()
    )
    assert entity_types == ("COMPANY", "POLICY_CLAUSE", "EMPLOYEE")
    assert relation_types == ("PARTY_TO", "CITES")
