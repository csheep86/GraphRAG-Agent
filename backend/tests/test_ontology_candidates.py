"""P5-I：`GET /api/v1/ontology/candidates` —— 校正 GUI 的实体来源（真 PG）。

**为什么单列一个文件**：它是本批**唯一新增**的端点，也是唯一一条**读**
`entity_merge_candidates` 的路径。三动作（merge / split / rename）的用例在
`test_ontology_correction_actions.py` 里已经钉住，**那里不重做**（Non-goal 1）；
这里只钉「候选从哪来」这一件事。

四条判据：

1. **`status` 过滤真的生效**（不是拿到全量再在前端过滤）；
2. **`org_id` 强制**（ADR-0003 §3.3）：以 B org 身份读 ⇒ **读不到 A org 的行**；
3. **非法 `status` ⇒ 400 `VALIDATION_ERROR`**（不静默当全量）；
4. **分页参数回显**（`page` / `page_size` 真的是请求里的值）。

⚠️ **断言口径**：本仓测试库是**持久** PostgreSQL（`graphrag_test`），库里可能有
别的用例残留的候选行 ⇒ 所有断言一律**按本用例种下的 id 做子集判断**，
**不**写 `total == N` 这种全表计数（P5-I0 §6.4：全表计数会被残留击穿，
症状看起来像"最近的改动把它弄坏了"）。

跑法（本地）：

```powershell
cd backend
$env:GRAPH_REAL_NEO4J_URI="bolt://localhost:7687"
$env:GRAPH_REAL_NEO4J_USER="neo4j"
$env:GRAPH_REAL_NEO4J_PASSWORD="ci-graph-pw-2026"
uv run pytest tests/test_ontology_candidates.py -q
```
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.db.models import EntityMergeCandidate
from app.db.session import session_scope

_SETTINGS = get_settings()
_ORG_ID = _SETTINGS.default_org_id
_OTHER_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")

_CANDIDATES_PATH = "/api/v1/ontology/candidates"


def _seed_candidate(
    *, org_id: uuid.UUID, left: str, right: str, status: str
) -> uuid.UUID:
    row_id = uuid.uuid4()
    with session_scope(org_id=org_id) as session:
        session.add(
            EntityMergeCandidate(
                id=row_id,
                org_id=org_id,
                left_entity_id=left,
                right_entity_id=right,
                similarity=0.82,
                status=status,
                signals={"name_sim": 0.82, "struct_bonus": 0.0},
                created_at=datetime.now(UTC),
                trace_id=uuid.uuid4(),
            )
        )
        session.commit()
    return row_id


@pytest.fixture
def seeded_candidates() -> dict[str, Any]:
    """A org 三行（`human_review` ×2 / `applied` ×1）+ B org 一行（`human_review`）。

    **为什么 B org 也要种一行**：只断言「B 看不到 A 的行」是不够的——
    一个恒返回空集的端点也能过那条断言。种一行 B 自己的候选，才能同时证明
    「B 能看到**自己的**」与「B 看不到**别人的**」。
    """
    stamp = uuid.uuid4().hex[:8]
    own_ids = [
        _seed_candidate(
            org_id=_ORG_ID,
            left=f"p5i-{stamp}-a1",
            right=f"p5i-{stamp}-a2",
            status="human_review",
        ),
        _seed_candidate(
            org_id=_ORG_ID,
            left=f"p5i-{stamp}-b1",
            right=f"p5i-{stamp}-b2",
            status="human_review",
        ),
        _seed_candidate(
            org_id=_ORG_ID,
            left=f"p5i-{stamp}-c1",
            right=f"p5i-{stamp}-c2",
            status="applied",
        ),
    ]
    other_id = _seed_candidate(
        org_id=_OTHER_ORG_ID,
        left=f"p5i-{stamp}-x1",
        right=f"p5i-{stamp}-x2",
        status="human_review",
    )

    try:
        yield {
            "stamp": stamp,
            "own_ids": own_ids,
            "other_id": other_id,
        }
    finally:
        # 按 id **精确**删除（不留残留，也不误删别人的行）
        with session_scope(org_id=_ORG_ID) as session:
            session.execute(
                delete(EntityMergeCandidate).where(EntityMergeCandidate.id.in_(own_ids))
            )
            session.commit()
        with session_scope(org_id=_OTHER_ORG_ID) as session:
            session.execute(
                delete(EntityMergeCandidate).where(EntityMergeCandidate.id == other_id)
            )
            session.commit()


def test_candidates_are_filterable_by_status(
    client,
    dev_headers: dict[str, str],
    seeded_candidates: dict[str, Any],
) -> None:
    """判据 1 / 4：`status` 过滤**在后端**生效，且分页参数原样回显。"""
    own_ids = set(seeded_candidates["own_ids"])

    response = client.get(
        _CANDIDATES_PATH,
        params={"status": "human_review", "page": 1, "page_size": 2},
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert len(payload["items"]) <= 2

    # 过滤真的生效：回来的每一行都必须是 human_review
    assert payload["items"], "本用例自己种了 2 行 human_review，不该是空集"
    assert {item["status"] for item in payload["items"]} == {"human_review"}

    # 回来的行必须是**本租户**种下的那两行（不是别人的残留）
    returned = {item["id"] for item in payload["items"]}
    assert returned <= {str(row_id) for row_id in own_ids}
    assert returned <= {
        str(seeded_candidates["own_ids"][0]),
        str(seeded_candidates["own_ids"][1]),
    }


def test_other_org_rows_are_invisible_to_current_tenant(
    client,
    cross_tenant_headers: dict[str, str],
    seeded_candidates: dict[str, Any],
) -> None:
    """判据 2：以 **B org** 身份读 ⇒ **读不到 A org 的行**，但**能读到自己的**。

    空集语义登记见 proposal **P5I-1**：列表类端点返回空集而不是 403，
    否则「队列为空」与「无权访问」在 UI 上无法区分。
    """
    own_ids = {str(row_id) for row_id in seeded_candidates["own_ids"]}
    other_id = str(seeded_candidates["other_id"])

    response = client.get(_CANDIDATES_PATH, headers=cross_tenant_headers)

    assert response.status_code == 200, response.text
    payload = response.json()

    returned = {item["id"] for item in payload["items"]}
    assert other_id in returned, "B org 连自己的候选都读不到 ⇒ 过滤条件写错了"
    assert not (returned & own_ids), "跨租户泄漏：A org 的候选出现在 B org 的视野里"


def test_invalid_status_filter_is_validation_error(
    client,
    dev_headers: dict[str, str],
    seeded_candidates: dict[str, Any],
) -> None:
    """判据 3：非法 `status` ⇒ **400 `VALIDATION_ERROR`**，不静默当全量返回。"""
    response = client.get(
        _CANDIDATES_PATH, params={"status": "not-a-status"}, headers=dev_headers
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value


def test_candidates_endpoint_is_rbac_protected(
    client,
    seeded_candidates: dict[str, Any],
) -> None:
    """判据 5（**护栏**）：候选行是租户内本体资产 ⇒ **不带身份 ⇒ 403**。

    与 `tests/test_rbac.py::PROTECTED_ENDPOINTS` 那条参数化用例是同一条纪律，
    这里补一条**显式**断言（该端点读到的是 `entity_merge_candidates` 真数据，
    「被保护了但没人验过拒绝」这种假绿不能出现在本批）。
    """
    response = client.get(_CANDIDATES_PATH)

    assert response.status_code in (401, 403), response.text
