"""Track G 稳定性/确定性检验：同样输入重复跑 N 次，看「自动判失效」是否每次都命中。

为什么必须做这一项：单次成功只能证明"能跑"，不能证明"敢进生产"。
自研路线（Track S）的仲裁是**确定性规则**，而 Graphiti 的矛盾判定依赖 LLM，
同一份语料可能出现"这次失效了、下次没失效"——这直接影响能否用它做知识过期治理。
"""

from __future__ import annotations

import asyncio
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone

os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.llm_client.config import LLMConfig  # noqa: E402
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient  # noqa: E402
from graphiti_core.nodes import EpisodeType  # noqa: E402

from corpus import EPISODES  # noqa: E402
from run_track_g import GROUP_ID, HashEmbedder, LexicalCrossEncoder, load_env  # noqa: E402

ROUNDS = 3


async def run_once(
    env: dict[str, str], index: int, embedder: object | None = None
) -> dict[str, object]:
    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=env.get("LLM_API_KEY", ""),
            model=env.get("LLM_MODEL", "deepseek-chat"),
            small_model=env.get("LLM_MODEL", "deepseek-chat"),
            base_url=env.get("LLM_BASE_URL", "https://api.deepseek.com"),
        ),
        structured_output_mode="json_object",
    )
    os.environ.setdefault("OPENAI_API_KEY", env.get("LLM_API_KEY", ""))
    graphiti = Graphiti(
        env.get("NEO4J_URI", "bolt://localhost:7687"),
        env.get("NEO4J_USER", "neo4j"),
        env.get("NEO4J_PASSWORD", "password"),
        llm_client=llm_client,
        embedder=embedder or HashEmbedder(),
        cross_encoder=LexicalCrossEncoder(),
    )

    async with graphiti.driver.session() as session:
        await session.run("MATCH (n {group_id: $gid}) DETACH DELETE n", gid=GROUP_ID)

    started = time.perf_counter()
    for episode in EPISODES:
        await graphiti.add_episode(
            name=episode["source_name"],
            episode_body=episode["text"],
            source=EpisodeType.text,
            source_description=episode["source_name"],
            reference_time=datetime.fromisoformat(episode["fact_date"]).replace(
                tzinfo=timezone.utc
            ),
            group_id=GROUP_ID,
        )
    elapsed = round(time.perf_counter() - started)

    async with graphiti.driver.session() as session:
        result = await session.run(
            "MATCH (a:Entity {group_id: $gid})-[r:RELATES_TO]->(b:Entity {group_id: $gid}) "
            "RETURN r.fact AS fact, r.invalid_at AS ia",
            gid=GROUP_ID,
        )
        rows = [record async for record in result]
    await graphiti.close()

    def squeeze(value: str) -> str:
        """去空格判分：模型对「陆家嘴环路 500 号」是否带空格不稳定。"""
        return re.sub(r"\s+", "", value or "")

    facts = [squeeze(str(r["fact"])) for r in rows]
    alive = [f for r, f in zip(rows, facts) if r["ia"] is None]
    invalidated = [f for r, f in zip(rows, facts) if r["ia"] is not None]
    joined_alive = " ".join(alive)
    old_rep_alive = "张三" in joined_alive
    new_rep_alive = "李四" in joined_alive

    return {
        "round": index + 1,
        "seconds": elapsed,
        "edges": len(rows),
        "invalidated": len(invalidated),
        "old_rep_invalidated": not old_rep_alive,
        "new_rep_alive": new_rep_alive,
        # 判"过期治理成功"的严格口径：旧法定代表人已失效 且 新法定代表人仍有效
        "expiry_handled": (not old_rep_alive) and new_rep_alive,
    }


async def main() -> None:
    env = load_env()
    # 用法：python repeat_g.py [hash|semantic]
    # hash = 占位向量（默认，保真度低）；semantic = 真实中文语义向量（对照组）
    kind = sys.argv[1] if len(sys.argv) > 1 else "hash"
    embedder = None
    if kind == "semantic":
        from semantic_embedder import build_semantic_embedder

        embedder = build_semantic_embedder()
    print(f"=== Track G / embedder={kind} / n={ROUNDS} ===")

    results = []
    for index in range(ROUNDS):
        result = await run_once(env, index, embedder)
        results.append(result)
        print(
            f"第 {result['round']} 轮: {result['seconds']}s, 边={result['edges']}, "
            f"自动失效={result['invalidated']}, 旧法人已失效={result['old_rep_invalidated']}, "
            f"新法人在位={result['new_rep_alive']}, 过期治理OK={result['expiry_handled']}"
        )

    hits = sum(1 for r in results if r["expiry_handled"])
    print("\n=== 汇总 ===")
    print(f"过期治理命中 {hits}/{len(results)} 轮")
    print(f"耗时中位数 {statistics.median([r['seconds'] for r in results])}s")
    print(f"平均自动失效边数 {statistics.mean([r['invalidated'] for r in results]):.1f}")


if __name__ == "__main__":
    asyncio.run(main())
