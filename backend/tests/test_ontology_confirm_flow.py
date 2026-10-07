"""P5-C：`cold-start → confirm → active` **闭环的真行为测试**。

**为什么单开一个文件**：`test_ontology_placeholder_endpoints.py` 管的是
「未实现的端点必须还是 501」（占位护栏），本文件管的是「已实现的端点必须**真**做事」
——两者失效方向相反，混在一个文件里会互相掩护：一边删环，另一边照样绿。

三条主判据（spec §3.1 验收 1 / 验收 2 / §3.5 验收 12）：

1. 冷启动**只建议、不写库**（`ontology_schemas` 一行都不多）；
2. 确认才转 `active`，且同一事务落一行 `ontology_actions`；
3. 无 active / 重复确认 / 跨租户 ⇒ 明确的错误语义，**不**静默降级。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import OntologyAction, OntologySchema
from app.db.session import session_scope
from app.services.ontology import OntologySuggestion

#: 测试用的**默认租户**（dev_headers 用的就是它）
_ORG_HEADER_KEY = "X-Org-Id"

_SETTINGS = get_settings()
_DEFAULT_ORG_ID = _SETTINGS.default_org_id

#: 确认体（spec §5.5：`POST /ontology/confirm` 的入参形状）
_CONFIRM_BODY: dict[str, Any] = {
    "version": 1,
    "entity_types": [
        {"name": "EMPLOYEE", "description": "员工"},
        {"name": "POLICY_CLAUSE"},
    ],
    "relation_types": [
        {
            "name": "GOVERNED_BY",
            "head_types": ["POLICY_CLAUSE"],
            "tail_types": ["EMPLOYEE"],
        }
    ],
}


@pytest.fixture(autouse=True)
def clean_default_org_ontology() -> None:
    """每个用例前后清掉默认租户的本体与审计行。

    **为什么要显式清**：本文件会往库里写真实的 `active` 本体，而别的应用层
    用例（`extraction_type_vocabulary` 的消费者）会读到它 ⇒ 脏数据会以
    "看起来无故通过的继承"形式污染别人的判据。
    """
    _purge(_DEFAULT_ORG_ID)
    yield
    _purge(_DEFAULT_ORG_ID)


def _purge(org_id: uuid.UUID) -> None:
    with session_scope(org_id=org_id) as session:
        session.execute(delete(OntologySchema).where(OntologySchema.org_id == org_id))
        session.execute(delete(OntologyAction).where(OntologyAction.org_id == org_id))
        session.commit()


def _ontology_rows(org_id: uuid.UUID) -> list[OntologySchema]:
    with session_scope(org_id=org_id) as session:
        return list(
            session.scalars(
                select(OntologySchema).where(OntologySchema.org_id == org_id)
            ).all()
        )


def _action_rows(org_id: uuid.UUID) -> list[OntologyAction]:
    with session_scope(org_id=org_id) as session:
        return list(
            session.scalars(
                select(OntologyAction).where(OntologyAction.org_id == org_id)
            ).all()
        )


def _suggestion() -> OntologySuggestion:
    """构造一个**假建议**（冷启动自己永不真调 LLM：这条 CI 必须零成本可复现）。"""
    return OntologySuggestion(
        entity_types=({"name": "COMPANY", "description": "法人主体"},),
        relation_types=(
            {"name": "PARTY_TO", "head_types": ["COMPANY"], "tail_types": ["COMPANY"]},
        ),
        prompt_name="ontology_suggest",
        prompt_version=1,
    )


# --------------------------------------------------------------------------- #
# 1) 冷启动：只建议、不写库（spec §3.1 验收 1）
# --------------------------------------------------------------------------- #
def test_cold_start_suggests_without_writing_schema(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.ontology.suggest_ontology_types",
        lambda **_kwargs: _suggestion(),
    )

    before = len(_ontology_rows(_DEFAULT_ORG_ID))

    response = client.post(
        "/api/v1/ontology/cold-start",
        json={"domain_description": "考勤合规"},
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["name"] for item in body["suggested_entity_types"]] == ["COMPANY"]
    assert [item["name"] for item in body["suggested_relation_types"]] == ["PARTY_TO"]
    assert body["trace_id"] == response.headers["X-Trace-Id"]

    # **验收 1 的硬约束**：未确认 ⇒ ontology_schemas 一行都不多
    assert len(_ontology_rows(_DEFAULT_ORG_ID)) == before
    # 冷启动之后仍然没有 active（说明它没有偷偷落半成品）
    assert client.get("/api/v1/ontology/active", headers=dev_headers).status_code == 409


def test_cold_start_surfaces_parse_failure_instead_of_fabricating(
    client: TestClient, dev_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 吐的内容解析不出类型集 ⇒ **报错**，不静默回落一组"看起来合理"的类型。"""
    from app.services.ontology import OntologySuggestError

    def _boom(**_kwargs: object) -> OntologySuggestion:
        raise OntologySuggestError("冷启动建议解析失败：LLM 未返回单个 JSON 对象")

    monkeypatch.setattr("app.api.v1.routes.ontology.suggest_ontology_types", _boom)

    response = client.post(
        "/api/v1/ontology/cold-start",
        json={"domain_description": "考勤合规"},
        headers=dev_headers,
    )

    assert response.status_code == 500, response.text
    assert response.json()["code"] == "INTERNAL_ERROR"


# --------------------------------------------------------------------------- #
# 2) 无 active ⇒ 409（**不**静默返回默认 schema）
# --------------------------------------------------------------------------- #
def test_active_returns_409_when_tenant_has_no_confirmed_schema(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/ontology/active", headers=dev_headers)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "SCHEMA_VERSION_NOT_ACTIVE"


# --------------------------------------------------------------------------- #
# 3) confirm 才转 active，且同事务写审计（spec §3.5 验收 12）
# --------------------------------------------------------------------------- #
def test_confirm_activates_schema_and_leaves_audit_row(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/ontology/confirm", json=_CONFIRM_BODY, headers=dev_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"version": 1, "status": "active"}

    rows = _ontology_rows(_DEFAULT_ORG_ID)
    assert len(rows) == 1
    assert rows[0].status == "active"
    assert rows[0].version == 1
    assert rows[0].confirmed_by_user == _SETTINGS.default_actor_id
    assert [item["name"] for item in rows[0].entity_types] == [
        "EMPLOYEE",
        "POLICY_CLAUSE",
    ]

    # 「谁确认的」与「本体生效」同事务成立 —— 这是本批把 audit 表建起来的全部理由
    actions = _action_rows(_DEFAULT_ORG_ID)
    assert len(actions) == 1
    assert actions[0].action_type == "confirm"
    assert actions[0].actor_id == _SETTINGS.default_actor_id
    assert actions[0].target_entities["entity_type_names"] == [
        "EMPLOYEE",
        "POLICY_CLAUSE",
    ]
    assert actions[0].kg_version is None  # 确认本体时图谱还不存在（X-2b）

    # 读侧随即可见：active 端点返回的正是刚确认的那套类型
    active = client.get("/api/v1/ontology/active", headers=dev_headers)
    assert active.status_code == 200, active.text
    assert active.json()["version"] == 1
    assert active.json()["status"] == "active"
    assert [item["name"] for item in active.json()["entity_types"]] == [
        "EMPLOYEE",
        "POLICY_CLAUSE",
    ]


def test_confirming_the_same_version_twice_is_409(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """重复确认 ⇒ 409：**不**静默复用旧版本（与 `KG_VERSION_NOT_ACTIVE` 同纪律）。"""
    first = client.post(
        "/api/v1/ontology/confirm", json=_CONFIRM_BODY, headers=dev_headers
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/ontology/confirm", json=_CONFIRM_BODY, headers=dev_headers
    )
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "SCHEMA_VERSION_NOT_ACTIVE"

    # 拒绝的同时没有把库改坏：仍然只有一行 active、一行审计
    rows = _ontology_rows(_DEFAULT_ORG_ID)
    assert len(rows) == 1
    assert len(_action_rows(_DEFAULT_ORG_ID)) == 1


def test_newer_version_supersedes_the_previous_active_one(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """换域（§4.6）：新版本 `active`、旧版本 `superseded`，历史图谱不回溯重算。"""
    first = client.post(
        "/api/v1/ontology/confirm", json=_CONFIRM_BODY, headers=dev_headers
    )
    assert first.status_code == 200, first.text

    second_body = {
        **_CONFIRM_BODY,
        "version": 2,
        "entity_types": [{"name": "SHIFT"}],
        "relation_types": [
            {"name": "WORKS_SHIFT", "head_types": ["EMPLOYEE"], "tail_types": ["SHIFT"]}
        ],
    }
    second = client.post(
        "/api/v1/ontology/confirm", json=second_body, headers=dev_headers
    )
    assert second.status_code == 200, second.text

    rows = {row.version: row for row in _ontology_rows(_DEFAULT_ORG_ID)}
    assert rows[1].status == "superseded"
    assert rows[2].status == "active"

    active = client.get("/api/v1/ontology/active", headers=dev_headers)
    assert active.json()["version"] == 2
    assert [item["name"] for item in active.json()["entity_types"]] == ["SHIFT"]


# --------------------------------------------------------------------------- #
# 4) 跨租户：看不到别的租户的本体（ADR-0003）
# --------------------------------------------------------------------------- #
def test_other_tenant_cannot_read_the_confirmed_schema(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
) -> None:
    """T1 口径在本体上的落点：别租户**没有** active ⇒ 409，而不是"读到对方的"。

    ⚠️ 它证明的是「另一个租户读不到」；真正证明策略在拦的是 G-26 判据 3
    （裸连接 + 不设 org），本用例是应用层视角的行为复核。
    """
    other_org_id = uuid.UUID(cross_tenant_headers[_ORG_HEADER_KEY])
    _purge(other_org_id)

    created = client.post(
        "/api/v1/ontology/confirm", json=_CONFIRM_BODY, headers=dev_headers
    )
    assert created.status_code == 200, created.text

    response = client.get("/api/v1/ontology/active", headers=cross_tenant_headers)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "SCHEMA_VERSION_NOT_ACTIVE"


# --------------------------------------------------------------------------- #
# 5) 身份与 RBAC 的下游副作用（占位护栏的反向守卫）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/ontology/cold-start", {"domain_description": "考勤合规"}),
        ("post", "/api/v1/ontology/confirm", _CONFIRM_BODY),
        ("get", "/api/v1/ontology/active", None),
    ],
)
def test_implemented_endpoints_still_require_tenant_context(
    client: TestClient, method: str, path: str, body: dict | None
) -> None:
    """实现不等于放开：无认证态仍然 401（占位期就钉住的租户隔离不能丢）。"""
    request = getattr(client, method)
    response = request(path, json=body) if body else request(path)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "UNAUTHORIZED"
