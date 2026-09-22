"""最小复现：定位 ``POST /api/v1/agent/query`` 返回 500 的根因。

直接调用 :meth:`AgentService.query`，把完整 traceback 打到终端。

用法（工作目录 = ``backend/``）：

    uv run python scripts/repro_agent_query.py            # 阶段 0 + 1 + 2
    uv run python scripts/repro_agent_query.py --no-llm   # 只跑阶段 0 + 1（0 额度消耗）
    uv run python scripts/repro_agent_query.py --real     # 只跑阶段 0 + 2（真实调用）

阶段划分（用于**区分**两类 500）：

- 阶段 0：机制探针 —— 证明 ``Literal`` 类型别名**不能**做属性访问。修复前后都会显示
  ``[BROKEN]``：它解释的是「为什么不能那样写」，**不是**回归测试。
- 阶段 1：把 LLM 打桩成固定输出，隔离出「图谱 OK + LLM OK」之后的**响应构造**缺陷。
  不消耗额度，**是本次修复的回归验收**（1a / 1b 都应 ``[OK]``）。
- 阶段 2：完整真实链路（会消耗 DeepSeek 额度）。

背景（9.3 诊断结论）：
``app/schemas/agent.py`` 用 ``Literal[...]`` 定义枚举取值，而 ``agents.py`` 曾写成
``QueryRoute.M3_GRAPHQA``。``Literal`` 是**类型别名**，属性访问会经
``typing._BaseGenericAlias.__getattr__`` 转发到 ``typing.Literal``，
再由 ``_SpecialForm.__getattr__`` 抛 ``AttributeError``；
该异常不在路由层的 ``except AgentUnavailableError`` 覆盖范围内，
最终由全局兜底处理器转为 ``500 INTERNAL_ERROR``（``detail=null``）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.schemas.agent import (  # noqa: E402
    AgentQueryRequest,
    AgentQueryResponse,
)
from app.services.agents import AgentService  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402

#: 与线上复现完全一致的请求体 / 租户
QUESTION = "智能制造有哪些财务指标？"
SCOPE = "cross_doc"

#: 阶段 1 假输出 A：合法 JSON + 形似 citation 的 evidence → 走「非拒答」分支
STUB_JSON_WITH_CITATION = (
    '{"answer": "示例答案 [source: chunk-1]", "evidence": ["chunk-1"],'
    ' "confidence": "high"}'
)
#: 阶段 1 假输出 B：无 citation → 走「拒答」分支
STUB_NO_CITATION = "INSUFFICIENT_CONTEXT"


def force_utf8_console() -> None:
    """Windows GBK 控制台会吃掉中文 traceback（与 import_to_neo4j.py 保持同款处理）。"""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None)
        if stream and encoding and encoding.lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def banner(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


# --------------------------------------------------------------------------- #
# 阶段 0：机制探针
# --------------------------------------------------------------------------- #
def probe_literal_aliases() -> None:
    """``Literal[...]`` 是类型别名、不是 Enum：属性访问必抛 ``AttributeError``。"""
    from app.schemas.agent import QueryConfidence, QueryRoute, RefusalReason

    banner("阶段 0：Literal 别名属性访问机制探针（预期全部 BROKEN，说明性检查）")
    for alias, attr in (
        (QueryRoute, "M3_GRAPHQA"),
        (QueryConfidence, "LOW"),
        (RefusalReason, "NO_GROUNDED_EVIDENCE"),
    ):
        try:
            value = getattr(alias, attr)
        except AttributeError as exc:
            print(f"  [BROKEN] {alias!r}.{attr} -> AttributeError: {exc}")
        else:
            print(f"  [OK]     {alias!r}.{attr} -> {value!r}")

    print("\n  机制：Literal['a','b'] 的 __origin__ 是 typing.Literal 特殊形式；")
    print("  _BaseGenericAlias.__getattr__ 会把属性转发到它上面，")
    print(
        "  而 _SpecialForm.__getattr__ 对任何非 __name__ 属性直接 raise AttributeError。"
    )
    print(
        "  → 结论：这三处只能用**字符串字面量**，取值以 contracts/openapi.yaml 为准。"
    )


def report_env() -> None:
    settings = get_settings()
    banner("运行环境")
    print("  APP_ENV                 =", settings.app_env)
    print(
        "  DATABASE_URL            =",
        settings.database_url.split("://", 1)[0] + "://...(已脱敏)",
    )
    print("  NEO4J_URI               =", settings.neo4j_uri)
    print(
        "  LLM_PROVIDER            =",
        settings.llm_provider,
        "| LLM_API_KEY =",
        "已配置" if settings.llm_api_key else "**未配置 → 只会 501，不会是 500**",
    )
    print("  LLM_BASE_URL            =", settings.llm_base_url)
    print("  LLM_MODEL               =", settings.llm_model)
    print(
        "  prompts_dir             =",
        settings.prompts_dir,
        "(存在)" if settings.prompts_dir.is_dir() else "**不存在**",
    )
    print("  task_retry_max_attempts =", settings.task_retry_max_attempts)
    print("  default_org_id          =", settings.default_org_id)


def report_graph() -> None:
    """证明第 1、2 步（Neo4j）是通的，把嫌疑范围收窄到第 4、5 步。"""
    banner("图谱链路探针（AgentService.query 的第 1、2 步）")
    graph = GraphService.instance()

    try:
        kg_version = graph.fetch_active_kg_version()
    except Exception as exc:  # noqa: BLE001 - 探针需打印全部故障
        print(f"  [FAIL] fetch_active_kg_version -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return
    print(
        f"  [OK] active kg_version = {kg_version.version!r} (scope={kg_version.scope!r})"
    )

    try:
        nodes, edges, truncated = graph.fetch_all_subgraph(
            kg_version=kg_version.version,
            org_id=get_settings().default_org_id,
            node_limit=500,
        )
    except Exception as exc:  # noqa: BLE001 - 探针需打印全部故障
        print(f"  [FAIL] fetch_all_subgraph -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return
    print(
        f"  [OK] fetch_all_subgraph -> nodes={len(nodes)} "
        f"edges={len(edges)} truncated={truncated}"
    )
    if nodes:
        sample = nodes[0]
        print(
            f"       样例节点 id={sample.id!r} label={sample.label!r} "
            f"entity_type={sample.entity_type!r} canonical_name={sample.canonical_name!r}"
        )
    else:
        print("       注意：节点为 0 时 Prompt 收到 <graph: empty>，LLM 大概率拒答；")
        print("       但**仍会走到响应构造**，照样能复现本 bug。")


# --------------------------------------------------------------------------- #
# 阶段 1 / 2：跑 query
# --------------------------------------------------------------------------- #
async def run_query(
    *, label: str, stub_answer: str | None
) -> AgentQueryResponse | None:
    """跑一次 :meth:`AgentService.query`；异常时打印 traceback 并返回 ``None``。"""
    settings = get_settings()
    request = AgentQueryRequest(question=QUESTION, scope=SCOPE)

    original_invoke = AgentService._invoke_chat_with_retry
    original_ensure = AgentService._ensure_chat

    if stub_answer is not None:

        async def _fake_invoke(
            _self: AgentService, *, system_prompt: str, question: str, trace_id: str
        ) -> str:
            return stub_answer

        def _fake_ensure(_self: AgentService) -> object:
            return object()

        AgentService._invoke_chat_with_retry = _fake_invoke  # type: ignore[method-assign]
        AgentService._ensure_chat = _fake_ensure  # type: ignore[method-assign]

    try:
        return await AgentService.instance().query(
            request=request,
            org_id=settings.default_org_id,
            trace_id=f"repro-{label}",
        )
    except Exception:  # noqa: BLE001 - 复现脚本必须打印全部异常
        print(f"  [FAIL] {label}：query() 抛出未捕获异常")
        print("         → 路由层不匹配任何 except → 全局兜底 → 500 INTERNAL_ERROR")
        print()
        traceback.print_exc(file=sys.stdout)
        print()
        return None
    finally:
        AgentService._invoke_chat_with_retry = original_invoke  # type: ignore[method-assign]
        AgentService._ensure_chat = original_ensure  # type: ignore[method-assign]
        AgentService.reset()


def verify(
    label: str,
    response: AgentQueryResponse | None,
    *,
    refused: bool,
    refusal_reason: str | None,
    route: str,
) -> bool:
    """断言响应关键字段（本次修复的回归验收点）。"""
    if response is None:
        print(f"  [FAIL] {label}：未拿到响应")
        return False

    problems: list[str] = []
    if response.refused is not refused:
        problems.append(f"refused 期望 {refused} 实际 {response.refused}")
    if response.refusal_reason != refusal_reason:
        problems.append(
            f"refusal_reason 期望 {refusal_reason!r} 实际 {response.refusal_reason!r}"
        )
    if response.route != route:
        problems.append(f"route 期望 {route!r} 实际 {response.route!r}")

    if problems:
        print(f"  [FAIL] {label}：字段校验不通过 -> " + "; ".join(problems))
        return False

    print(
        f"  [OK]   {label}：refused={response.refused} route={response.route!r} "
        f"confidence={response.confidence!r} citations={len(response.citations)}"
    )
    return True


async def main() -> int:
    force_utf8_console()

    parser = argparse.ArgumentParser(description="复现 /agent/query 的 500")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-llm", action="store_true", help="只跑打桩阶段（不消耗额度）"
    )
    group.add_argument("--real", action="store_true", help="只跑真实 LLM 阶段")
    args = parser.parse_args()

    report_env()
    report_graph()
    probe_literal_aliases()

    results: list[tuple[str, bool]] = []

    if not args.real:
        banner("阶段 1：LLM 打桩（不消耗额度）——「响应构造」回归验收")
        label_a = "1a 有 citation（非拒答分支）"
        results.append(
            (
                label_a,
                verify(
                    label_a,
                    await run_query(
                        label="stub-citation", stub_answer=STUB_JSON_WITH_CITATION
                    ),
                    refused=False,
                    refusal_reason=None,
                    route="m3_graphqa",
                ),
            )
        )
        label_b = "1b 无 citation（拒答分支）"
        results.append(
            (
                label_b,
                verify(
                    label_b,
                    await run_query(
                        label="stub-no-citation", stub_answer=STUB_NO_CITATION
                    ),
                    refused=True,
                    refusal_reason="no_grounded_evidence",
                    route="m3_graphqa",
                ),
            )
        )

    if not args.no_llm:
        banner("阶段 2：真实 DeepSeek 调用（会消耗额度）")
        label_real = "2  真实 LLM"
        results.append(
            (
                label_real,
                verify(
                    label_real,
                    await run_query(label="real", stub_answer=None),
                    refused=False,
                    refusal_reason=None,
                    route="m3_graphqa",
                ),
            )
        )

    banner("结论")
    for label, ok in results:
        print(f"  {'[OK]  ' if ok else '[FAIL]'} {label}")

    if not results:
        print("\n  未执行任何用例（请检查参数）。")
        return 1

    if all(ok for _, ok in results):
        print("\n  ✅ 响应构造阶段不再抛异常：Literal 属性访问 bug 修复生效。")
        if args.no_llm:
            print(
                "     下一步可跑真实链路：uv run python scripts/repro_agent_query.py --real"
            )
        return 0

    print("\n  ❌ 仍有异常 / 字段不符，请查看上方 traceback 与 FAIL 明细。")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
