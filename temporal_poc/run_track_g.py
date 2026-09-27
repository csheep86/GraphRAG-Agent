"""Track G：Graphiti 路线验证（独立虚拟环境运行，见 README §环境）。

跑法（必须在 temporal_poc/.venv 里）：
    .venv\\Scripts\\python.exe run_track_g.py

与 Track S 用**同一份 corpus、同一组期望答案**，差别只在"时态引擎"：
- Track S：自己写 valid_from/valid_to + 自己写失效仲裁；
- Track G：Graphiti 内建双时态 + 自动矛盾失效（我们只负责喂 episode）。

⚠️ 已知保真度限制：本机无 Embedding 服务也无本地模型，故用 **HashEmbedder**
（确定性字符 n-gram 哈希向量）。它足以验证**机制**（双时态字段、自动失效、
增量更新、血缘），但**不**代表语义检索质量——生产需换成中文向量模型
（如 bge-small-zh），接口一行替换即可。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.cross_encoder.client import CrossEncoderClient  # noqa: E402
from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig  # noqa: E402
from graphiti_core.llm_client.config import LLMConfig  # noqa: E402
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient  # noqa: E402
from graphiti_core.nodes import EpisodeType  # noqa: E402

from corpus import EPISODES, EXPECTED_CURRENT  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "backend" / ".env"
GROUP_ID = "track-g-poc"
DIM = 1024


def load_env() -> dict[str, str]:
    """读 backend/.env（只取本实验需要的键，不打印密钥内容）。"""
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        raise SystemExit(f"找不到 {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class HashEmbedder(EmbedderClient):
    """确定性字符 bigram 哈希向量（**仅用于验证机制，非语义质量**）。"""

    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self.config = config or EmbedderConfig(embedding_dim=DIM)

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        text = input_data if isinstance(input_data, str) else " ".join(map(str, input_data))
        vector = [0.0] * DIM
        grams = [text[i : i + 2] for i in range(len(text) - 1)] or [text]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            slot = int.from_bytes(digest[:2], "big") % DIM
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[slot] += sign
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm for v in vector] if norm else vector

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Graphiti 在批量建边时会调用；逐条委托给 :meth:`create`。"""
        return [await self.create(text) for text in input_data_list]


class LexicalCrossEncoder(CrossEncoderClient):
    """词面重合度排序器（**仅用于跑通链路**，不代表语义排序质量）。"""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        query_chars = set(query)
        scored: list[tuple[str, float]] = []
        for passage in passages:
            overlap = len(query_chars & set(passage))
            scored.append((passage, overlap / max(len(query_chars), 1)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


def dump_edges(driver_uri: str, user: str, password: str) -> list[dict[str, str]]:
    """直接查 Neo4j，看 Graphiti 落了哪些边及其双时态字段。"""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(driver_uri, auth=(user, password))
    rows: list[dict[str, str]] = []
    with driver.session() as session:
        result = session.run(
            "MATCH (a:Entity {group_id: $gid})-[r:RELATES_TO]->(b:Entity {group_id: $gid}) "
            "RETURN a.name AS head, b.name AS tail, r.fact AS fact, "
            "r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
            "r.created_at AS created_at, r.expired_at AS expired_at "
            "ORDER BY r.created_at",
            gid=GROUP_ID,
        )
        for row in result:
            rows.append(
                {
                    "head": row["head"] or "",
                    "tail": row["tail"] or "",
                    "fact": (row["fact"] or "")[:60],
                    "valid_at": str(row["valid_at"]),
                    "invalid_at": str(row["invalid_at"]),
                    "created_at": str(row["created_at"])[:19],
                    "expired_at": str(row["expired_at"]),
                }
            )
    driver.close()
    return rows


async def main() -> None:
    env = load_env()
    llm_config = LLMConfig(
        api_key=env.get("LLM_API_KEY", ""),
        model=env.get("LLM_MODEL", "deepseek-chat"),
        small_model=env.get("LLM_MODEL", "deepseek-chat"),
        base_url=env.get("LLM_BASE_URL", "https://api.deepseek.com"),
    )
    # DeepSeek 不支持 json_schema 结构化输出（实测 400），必须切 json_object：
    # Graphiti 源码注释点名 DeepSeek 属于这一类，此时它把 schema 注入 prompt 引导。
    llm_client = OpenAIGenericClient(config=llm_config, structured_output_mode="json_object")
    embedder = HashEmbedder()
    cross_encoder = LexicalCrossEncoder()
    # Graphiti 内部部分组件默认走 openai SDK 的全局凭据兜底，这里把 DeepSeek key
    # 透给 OPENAI_API_KEY，避免"没用 OpenAI 却被要求 OpenAI key"的假报错。
    os.environ.setdefault("OPENAI_API_KEY", env.get("LLM_API_KEY", ""))

    graphiti = Graphiti(
        env.get("NEO4J_URI", "bolt://localhost:7687"),
        env.get("NEO4J_USER", "neo4j"),
        env.get("NEO4J_PASSWORD", "password"),
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    metrics: dict[str, object] = {"track": "G(Graphiti)", "episodes": []}

    # 清理上一轮实验数据
    async with graphiti.driver.session() as session:
        await session.run("MATCH (n {group_id: $gid}) DETACH DELETE n", gid=GROUP_ID)
    try:
        await graphiti.build_indices_and_constraints()
    except Exception as exc:  # 索引已存在时会报，无害
        print(f"[warn] build_indices: {type(exc).__name__}: {str(exc)[:80]}")

    total_ms = 0
    for episode in EPISODES:
        started = time.perf_counter()
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
        elapsed = round((time.perf_counter() - started) * 1000)
        total_ms += elapsed
        metrics["episodes"].append({"id": episode["id"], "elapsed_ms": elapsed})

    edges = dump_edges(
        env.get("NEO4J_URI", "bolt://localhost:7687"),
        env.get("NEO4J_USER", "neo4j"),
        env.get("NEO4J_PASSWORD", "password"),
    )
    metrics["total_ms"] = total_ms
    metrics["edge_count"] = len(edges)
    metrics["edges"] = edges

    # ---- 判分（与 Track S 同口径）----
    alive = [e for e in edges if e["invalid_at"] in ("None", "")]
    facts_alive = " || ".join(e["fact"] for e in alive)
    metrics["answers"] = {
        "alive_edge_count": len(alive),
        "current_facts": facts_alive[:400],
    }
    metrics["score"] = {
        "has_temporal_fields": any(e["valid_at"] not in ("None", "") for e in edges),
        "auto_invalidated": any(e["invalid_at"] not in ("None", "") for e in edges),
        "history_preserved": len(edges) > len(alive),
        "current_ok": EXPECTED_CURRENT["LEGAL_REP"] in facts_alive,
        "current_addr_ok": "陆家嘴环路 500 号" in facts_alive,
    }

    await graphiti.close()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
