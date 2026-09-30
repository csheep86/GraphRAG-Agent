"""S10 批次 A/B/C 的**端到端真机验收**（真实 DeepSeek 调用，会消耗少量额度）。

前面三批都只证到"链路中段"（写读闭环 / 路径构造 / 候选集），端到端一直挂着
"需 PG + LLM"——**这个前提是错的**：开发库是 SQLite，``AgentService.query``
只走 Neo4j + LLM，且 LLM 已配置。本探针就是把这笔账还掉。

问句**全部基于 active 图上的真实实体名**构造（不编造实体），题干分三类：

1. 单实体（查属性）：能否给出带引用的非拒答答案；
2. 多跳（员工 → 考勤记录 → 制度条款）：``reasoning_path`` 是否有 ≥1 跳且可核查；
3. 域外（图上不可能有证据）：是否**诚实拒答**（反证 F3）。

观测点直接对应三批的验收项：

- 批次 A：``citations[].char_offset / char_end`` 是否**非占位**（span 级命中）；
- 批次 B：``reasoning_path`` 跳数、每跳 source/relation/target/origin；
- 批次 C：是否不再因为"锚点被挤出候选集"而误拒答。

**不宣称**：本探针只记录真实返回，不判"答对"——答对率要人读答案与引用后判。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.schemas.agent import AgentQueryRequest  # noqa: E402
from app.services.agents import AgentService  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402


def _pick_entities(version: str, org) -> tuple[str, str]:
    """挑两个真实实体名：一个 ``EMPLOYEE``、一个 ``POLICY_CLAUSE``（用于构造问句）。"""
    graphs = GraphService.instance()
    with graphs._session() as session:  # noqa: SLF001
        rows = list(
            session.run(
                "MATCH (e:Entity {kg_version: $v, org_id: $org}) "
                "WHERE e.entity_type IN ['EMPLOYEE', 'POLICY_CLAUSE'] "
                "AND e.canonical_name IS NOT NULL "
                "RETURN e.entity_type AS t, e.canonical_name AS name "
                "ORDER BY t, name LIMIT 400",
                v=version,
                org=str(org),
            )
        )
    employees = [r["name"] for r in rows if r["t"] == "EMPLOYEE"]
    clauses = [r["name"] for r in rows if r["t"] == "POLICY_CLAUSE"]
    return employees[0] if employees else "张伟", clauses[0] if clauses else "第七条"


def _report(index: int, question: str, response: object) -> None:
    print(f"\n--- Q{index}: {question}")
    print(
        f"    refused={response.refused} route={response.route!r} "
        f"confidence={response.confidence!r} refusal_reason={response.refusal_reason!r}"
    )
    citations = getattr(response, "citations", None) or []
    print(f"    citations: {len(citations)}")
    for citation in citations:
        # 判据：``char_offset > 0`` 才算 **span 级命中**；``[0, len(text))`` 是回退档
        # （整段高亮）。**不要**写成 ``char_end != 0``——回退档的 end 也是非 0，
        # 那样判据恒真，会把"回退"读成"命中"（本探针第一版就犯了这个错）。
        print(
            f"      chunk={citation.chunk_id} "
            f"[{citation.char_offset}, {citation.char_end}) "
            f"命中形态={'span级' if citation.char_offset > 0 else '回退整段'}"
        )
        print(f"      snippet={citation.snippet[:60]!r}")
    path = getattr(response, "reasoning_path", None) or []
    print(f"    reasoning_path: {len(path)} 跳")
    for hop in path:
        print(
            f"      {hop.source.name} --{hop.relation}--> "
            f"{hop.target.name} [{hop.origin}]"
        )
    usage = getattr(response, "usage", None)
    print(f"    usage: {usage}")


async def main() -> None:
    settings = get_settings()
    graphs = GraphService.instance()
    version = graphs.fetch_active_kg_version(org_id=settings.default_org_id).version
    employee, clause = _pick_entities(version, settings.default_org_id)
    print(f"active kg_version = {version}；问句用真实实体: 员工={employee!r} 条款={clause!r}")

    questions = [
        f"{employee} 上个月加班了多少小时？",
        f"{employee} 的加班时长是否违反了{clause}的规定？",
        "量子计算在考勤排班中的最佳实践是什么？",  # 域外 ⇒ 期望诚实拒答
    ]

    for index, question in enumerate(questions, start=1):
        try:
            response = await AgentService.instance().query(
                request=AgentQueryRequest(question=question, scope="cross_doc"),
                org_id=settings.default_org_id,
                trace_id=f"e2e-s10-c{index}",
            )
        except Exception as exc:  # noqa: BLE001 - 探针要看见全部故障
            print(f"\n--- Q{index}: {question}\n    [FAIL] {type(exc).__name__}: {exc}")
            continue
        finally:
            AgentService.reset()
        _report(index, question, response)


if __name__ == "__main__":
    asyncio.run(main())
