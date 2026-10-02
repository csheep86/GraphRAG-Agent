"""M6 spec §5.5 的 7 个**占位端点**测试（`changes/P0-m6-finalization` F2）。

**为什么给占位端点写测试**：契约先行批次最容易出的两个事故 ——

1. **占位被当成实现**：前端照 200 写消费逻辑，一接真数据全崩。所以这里钉死
   「调用即得 **501** 且 `detail.blocked_by` 写明未实现」；
2. **占位漏了租户隔离**：骨架写顺手了不加 `CurrentIdentity`，契约里就没有 401/403，
   等 M6 实现时再补就晚了（那时已有前端按"无需认证"接好了）。

⇒ 这两条是**骨架期**唯一的实质内容，其余（业务逻辑）归 P5-M6 批次。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: （方法, 路径, 请求体；GET 为 None）
PLACEHOLDERS: list[tuple[str, str, dict | None]] = [
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
    ("get", "/api/v1/ontology/active", None),
    ("get", "/api/v1/cost/dashboard", None),
]

PLACEHOLDER_IDS = [f"{method.upper()} {path}" for method, path, _ in PLACEHOLDERS]


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
