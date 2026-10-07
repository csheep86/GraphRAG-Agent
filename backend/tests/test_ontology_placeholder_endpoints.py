"""M6 spec §5.5 里**尚未实现**的端点的占位测试（`changes/archive/2026-10-02-P0-m6-finalization` F2）。

**为什么给占位端点写测试**：契约先行批次最容易出的两个事故 ——

1. **占位被当成实现**：前端照 200 写消费逻辑，一接真数据全崩。所以这里钉死
   「调用即得 **501** 且 `detail.blocked_by` 写明未实现」；
2. **占位漏了租户隔离**：骨架写顺手了不加 `CurrentIdentity`，契约里就没有 401/403，
   等 M6 实现时再补就晚了（那时已有前端按"无需认证"接好了）。

**P5-C（2026-10-07）收缩**：`cold-start` / `confirm` / `active` 三个已由本批接线
（它们的真行为断言移到了 `tests/test_ontology_confirm_flow.py`——**不是删测试，
是把 oracle 换成真的**）。本文件保留**剩下四个**占位端点的护栏，并在末尾留一条
反向守卫：已实现的端点**不许偷偷退回 501**（那是把实现回滚到占位的最快方式）。

⚠️ 谁在后续批次实现了 `merge` / `split` / `rename` / `cost/dashboard`，
就把那一行从这里移走、换成真行为断言 —— **删整行 = 拆护栏**，与本文件的存在理由直接冲突。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models import OntologyAction, OntologySchema
from app.db.session import session_scope
from app.services.ontology import OntologySuggestion


def _purge_default_org() -> None:
    """清掉默认租户的本体与审计行（本文件只为了「不是 501」这个断言，不留数据）。"""
    org_id = get_settings().default_org_id
    with session_scope(org_id=org_id) as session:
        session.execute(delete(OntologySchema).where(OntologySchema.org_id == org_id))
        session.execute(delete(OntologyAction).where(OntologyAction.org_id == org_id))
        session.commit()


#: **仍未实现**的端点（方法, 路径, 请求体；GET 为 None）。
#: P5-C 已实现的三个（`cold-start` / `confirm` / `active`）**从这里移除**，
#: 断言换成了 `test_ontology_confirm_flow.py` 里的真行为。
PLACEHOLDERS: list[tuple[str, str, dict | None]] = [
    (
        "post",
        "/api/v1/ontology/merge",
        {"left_entity_id": "ent_a", "right_entity_id": "ent_b"},
    ),
    (
        "post",
        "/api/v1/ontology/split",
        {
            "entity_id": "ent_a",
            "new_entities": [{"canonical_name": "张伟"}, {"canonical_name": "张玮"}],
        },
    ),
    (
        "post",
        "/api/v1/ontology/rename",
        {"entity_id": "ent_a", "new_canonical_name": "张伟"},
    ),
    ("get", "/api/v1/cost/dashboard", None),
]

#: **已实现**的端点（反向守卫用）：它们**不再**是占位，故绝不能再返回 501
IMPLEMENTED: list[tuple[str, str, dict | None]] = [
    ("post", "/api/v1/ontology/cold-start", {"domain_description": "财务关联交易识别"}),
    (
        "post",
        "/api/v1/ontology/confirm",
        {
            "version": 1,
            "entity_types": [{"name": "COMPANY"}],
            "relation_types": [
                {
                    "name": "PARTY_TO",
                    "head_types": ["COMPANY"],
                    "tail_types": ["COMPANY"],
                }
            ],
        },
    ),
    ("get", "/api/v1/ontology/active", None),
]

PLACEHOLDER_IDS = [f"{method.upper()} {path}" for method, path, _ in PLACEHOLDERS]
_IMPLEMENTED_IDS = [f"{method.upper()} {path}" for method, path, _ in IMPLEMENTED]

#: 假建议（**不许**在本文件里真调 LLM：这条守卫必须零成本、可复现）
_FAKE_SUGGESTION = OntologySuggestion(
    entity_types=({"name": "COMPANY"},),
    relation_types=(
        {"name": "PARTY_TO", "head_types": ["COMPANY"], "tail_types": ["COMPANY"]},
    ),
    prompt_name="ontology_suggest",
    prompt_version=1,
)


@pytest.mark.parametrize(("method", "path", "body"), PLACEHOLDERS, ids=PLACEHOLDER_IDS)
def test_placeholder_returns_501_not_empty_200(
    client: TestClient,
    dev_headers: dict[str, str],
    method: str,
    path: str,
    body: dict | None,
) -> None:
    """占位端点**必须** 501：返回 200 空结果 = 前端会以为接口可用（"假做"）。

    `detail.blocked_by` 必须写明「实现归 P5-M6」，否则排障的人分不清是
    「还没做」还是「基础设施挂了」——项目里 501 的既有口径是后者。
    """
    request = getattr(client, method)
    response = (
        request(path, json=body, headers=dev_headers)
        if body
        else request(path, headers=dev_headers)
    )

    assert response.status_code == 501, response.text
    payload = response.json()
    assert payload["code"] == "NOT_IMPLEMENTED"
    assert "P5-M6" in payload["detail"]["blocked_by"]
    assert payload["detail"]["endpoint"] == f"{method.upper()} {path}"
    # trace_id 恒回显（错误响应规范）
    assert response.headers["X-Trace-Id"] == payload["trace_id"]


@pytest.mark.parametrize(("method", "path", "body"), PLACEHOLDERS, ids=PLACEHOLDER_IDS)
def test_placeholder_requires_tenant_context(
    client: TestClient, method: str, path: str, body: dict | None
) -> None:
    """骨架期就钉死租户隔离：无认证态 → 401，且响应体是统一错误体。"""
    request = getattr(client, method)
    response = request(path, json=body) if body else request(path)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "UNAUTHORIZED"


def test_cost_dashboard_accepts_date_range(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """`date_from` / `date_to` 是 spec §5.5 明列的查询参数 —— 少一个就接不上仪表盘。"""
    response = client.get(
        "/api/v1/cost/dashboard",
        params={"date_from": "2026-10-01", "date_to": "2026-10-02"},
        headers=dev_headers,
    )
    # 占位仍是 501，但**不能**是 422 / 400 —— 那说明查询参数没被契约接受
    assert response.status_code == 501, response.text


@pytest.mark.parametrize(("method", "path", "body"), IMPLEMENTED, ids=_IMPLEMENTED_IDS)
def test_implemented_endpoints_are_no_longer_placeholders(
    client: TestClient,
    dev_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    """**反向守卫**：已实现的三个端点**不许**再返回 501。

    为什么不能只靠"它们在别的文件里被断言为真行为"：那条断言挂在**别的文件**，
    有人把路由体改回 `raise _placeholder(...)` 时，`test_ontology_confirm_flow.py`
    确实会红——但它红得像"业务回归"，排障的人会先怀疑业务逻辑，
    而不是"实现被悄悄退回占位"。这里把「不许 501」说得更直接一点。

    **不**断言具体状态码上限：200 / 409 / 500 都可能合法（取决于租户有没有
    active schema、LLM 是否可用）；唯一非法的是 501（= 又变回占位）。
    """
    # 冷启动本会真调 LLM（有 key 就有成本、没 key 就有延迟），替掉：
    # 本守卫要验的是「不是占位」，不是「LLM 通不通」——后者不在 CI 的判据里。
    monkeypatch.setattr(
        "app.api.v1.routes.ontology.suggest_ontology_types",
        lambda **_kwargs: _FAKE_SUGGESTION,
    )

    # `/confirm` 会真写库 ⇒ 前后各清一次默认租户的行，别把它留给后面的用例
    _purge_default_org()
    request = getattr(client, method)
    response = (
        request(path, json=body, headers=dev_headers)
        if body
        else request(path, headers=dev_headers)
    )
    _purge_default_org()

    assert response.status_code != 501, (
        f"{method.upper()} {path} 又变成占位了（P5-C 已实现它）：{response.text}"
    )
