"""P6-V：M4 端到端探针（**问一个问题**，成本 / 继承读的两条本地判据）。

判什么：

1. **端到端问答真吃到版本继承读**：`agents.py` 把 PG 会话传进检索之后，
   问答还能不能拿到**祖先版本的节点**（此前会被 active 版本过滤掉）；
2. **成本落点**：本次真实 LLM 调用的 token 有没有落到 `cost_metrics` 当日行
   （含 `doc_count` 去重）。

**必须有 `LLM_API_KEY`**：CI 不跑（沿用 D6）。跑法（backend 目录）：

    uv run python changes/P6-V/probe_m4_end_to_end.py

没有 key 就**如实跳过**，不臆造出数。
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import CostMetric
from app.db.session import session_scope
from app.schemas.agent import AgentQueryRequest
from app.services.agents import AgentService
from app.services.cost_metrics import utc_day
from app.services.graphs import GraphService

QUESTION = "张伟 2026-10-16 为什么没有打卡记录？"


def _active_version(org_id) -> str:  # noqa: ANN001
    with session_scope(org_id=org_id) as db:
        return GraphService.instance().fetch_active_kg_version(
            org_id=org_id, db=db
        ).version


async def _ask(org_id, request: AgentQueryRequest, db) -> object:  # noqa: ANN001
    # db 来自 session_scope ⇒ 与 HTTP 路由同口径（`routes/agent.py:69` 就是这样传的）
    return await AgentService.instance().query(
        request=request, org_id=org_id, trace_id="probe-p6v-m4", db=db
    )


def main() -> int:
    settings = get_settings()
    if not settings.llm_api_key:
        print("[SKIP] 没有 LLM_API_KEY ⇒ 本批不宣称 M4 端到端出数（不臆造）")
        return 0

    org_id = settings.default_org_id
    print(f"[INFO] org_id={org_id} kg_version={_active_version(org_id)}")

    request = AgentQueryRequest(
        org_id=org_id, question=QUESTION, doc_id=None, scope="cross_doc"
    )
    # 会话与 HTTP 路径同构：先读数、再在同一个会话里跑问答（含成本落点）
    with session_scope(org_id=org_id) as db:
        response = asyncio.run(_ask(org_id, request, db))
    print(f"[OUT] refused={response.refused} route={response.route}")
    print(f"[OUT] citations={[c.chunk_id for c in response.citations][:5]}")
    print(f"[OUT] token_usage={response.token_usage}")
    print(f"[OUT] answer_head={response.answer[:120]!r}")

    with session_scope(org_id=org_id) as db:
        row = db.scalar(
            select(CostMetric).where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date == utc_day(),
            )
        )
        if row is None:
            print("[COST] 当日没有成本行（拒答 ⇒ 没有真实调用，属正常）")
        else:
            print(
                f"[COST] total={row.token_usage_total} doc_count={row.doc_count} "
                f"single_doc_cost={row.single_doc_cost:.2f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
