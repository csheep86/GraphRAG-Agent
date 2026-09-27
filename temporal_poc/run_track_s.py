"""Track S：自研路线验证。

在你**现有链路**上做两件事，然后机械判分：
1. 时态抽取：DeepSeek + v3 风格 prompt，让每条关系带 valid_from / valid_to；
2. 自写仲裁：写入 Neo4j 时，同 (head, relation_type) 出现更晚的新事实 ⇒ 把旧边的
   `valid_to` 封到新事实的 `valid_from`（**保留历史**，不物理删除）。

判分口径与 Track G **完全一致**（同一份 corpus、同一组期望答案），保证可比。
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.services.providers import build_chat_model  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

from corpus import EPISODES, EXPECTED_CURRENT, expected_pairs  # noqa: E402

#: 本 PoC 专用标签，避免污染业务图谱
ENT_LABEL = "POCS_Entity"
POC_TAG = "track-s"

SYSTEM_PROMPT = """你是一名严谨的知识图谱抽取器，服务于金融 / 法律文档分析。

给定一段中文文本与该段文本的「事实截面日期」，请抽取实体与关系，并**为每条关系标注时效**。

输出严格 JSON（不要任何解释文本、不要代码围栏）：
{
  "entities": [
    {"id": "ent_1", "canonical_name": "标准化名称", "entity_type": "ORG", "mention": "原文片段", "confidence": 0.95}
  ],
  "relations": [
    {"source_entity_id": "ent_1", "target_entity_id": "ent_2", "relation_type": "LEGAL_REP",
     "fact": "原文支撑句", "valid_from": "2023-12-31", "valid_to": null, "confidence": 0.9}
  ]
}

实体类型枚举：ORG|PERSON|LEGAL_PERSON|ADDRESS|MONEY|DATE|PRODUCT|VENUE|CONTRACT_CLAUSE|REGULATION
关系类型枚举：LEGAL_REP|REGISTERED_AT|HAS_FINANCIAL_INDICATOR|AFFILIATED_WITH|EMPLOYED_BY|PARTY_TO|OPERATES_SEGMENT|SUPPLIES_TO|RELATED

时效标注规则（本实验的核心）：
1. valid_from：事实**开始成立**的日期，格式 YYYY-MM-DD。无法确定时，填下方给出的事实截面日期。
2. valid_to：事实**失效**的日期；文本没写失效则填 null。
3. 文本出现「自 XXXX 年 X 月起…变更为 / 增加至 / 迁至」这类表述时：
   - 新值：valid_from = 该变更生效日；
   - 旧值：valid_to = 同一变更生效日（旧事实在同一刻失效）。
4. 变更类表述要拆成「新值生效」与「旧值失效」两层，不要只抽成一条关系。
5. 置信度低于 0.5 的条目不要输出。
"""


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced is not None:
        return fenced.group(1)
    block = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return block.group(0) if block is not None else text


def _squeeze(value: str) -> str:
    """去空格后比较：模型对「陆家嘴环路 500 号」是否带空格并不稳定，
    用它做判分会误判"答错"（实测发现后才加，见 README §坑 3）。"""
    return re.sub(r"\s+", "", value or "")


def _norm_date(value: Any) -> str | None:
    """把模型给的各种日期写法归一到 YYYY-MM-DD；无法识别 → None（不猜）。"""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})年(\d{1,2})月$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    m = re.match(r"^(\d{4})$", text)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def extract_episode(model, episode: dict[str, str]) -> dict[str, Any]:
    """对一个 episode 做时态抽取；返回结构化结果 + 调用统计。"""
    user_text = (
        f"事实截面日期：{episode['fact_date']}\n"
        f"来源：{episode['source_name']}\n\n"
        f"{episode['text']}"
    )
    started = time.perf_counter()
    response = model.invoke(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}]
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    payload = json.loads(_strip_fences(str(response.content)))
    return {
        "payload": payload,
        "elapsed_ms": elapsed_ms,
        "id": episode["id"],
        "fact_date": episode["fact_date"],
    }


def write_episode(session, result: dict[str, Any], episode_text: str) -> dict[str, int]:
    """写入 Neo4j：同 (head, relation_type) 的新事实 ⇒ 封旧边的 valid_to。"""
    episode_id = result["id"]
    entities = result["payload"].get("entities") or []
    relations = result["payload"].get("relations") or []
    id_to_name = {str(e.get("id")): str(e.get("canonical_name") or "").strip() for e in entities}

    node_count = 0
    for entity in entities:
        name = str(entity.get("canonical_name") or "").strip()
        if not name:
            continue
        session.run(
            f"MERGE (n:{ENT_LABEL} {{name: $name, poc: $poc}}) "
            "ON CREATE SET n.entity_type = $etype, n.created_episode = $ep "
            "ON MATCH SET n.entity_type = coalesce(n.entity_type, $etype)",
            name=name,
            poc=POC_TAG,
            etype=str(entity.get("entity_type") or "RELATED"),
            ep=episode_id,
        )
        node_count += 1

    edge_count = 0
    invalidated = 0
    written: list[dict[str, str]] = []
    for relation in relations:
        head = id_to_name.get(str(relation.get("source_entity_id")))
        tail = id_to_name.get(str(relation.get("target_entity_id")))
        rel_type = str(relation.get("relation_type") or "RELATED")
        if not head or not tail:
            continue
        valid_from = _norm_date(relation.get("valid_from")) or result["fact_date"]
        valid_to = _norm_date(relation.get("valid_to"))

        # 自写仲裁：新事实生效前，把同一 (head, rel_type) 的旧边封闭
        closed = session.run(
            f"MATCH (a:{ENT_LABEL} {{name: $head, poc: $poc}})"
            f"-[r:{rel_type}]->(b:{ENT_LABEL} {{poc: $poc}}) "
            "WHERE r.valid_to IS NULL AND coalesce(r.valid_from, '') < $vf "
            "AND r.source_episode <> $ep AND NOT b.name = $tail "
            "SET r.valid_to = $vf, r.invalidated_by = $ep "
            "RETURN count(r) AS c",
            head=head,
            poc=POC_TAG,
            vf=valid_from,
            tail=tail,
            ep=episode_id,
        ).single()["c"]
        invalidated += int(closed or 0)

        session.run(
            f"MATCH (a:{ENT_LABEL} {{name: $head, poc: $poc}}), "
            f"(b:{ENT_LABEL} {{name: $tail, poc: $poc}}) "
            f"MERGE (a)-[r:{rel_type} {{valid_from: $vf, tail: $tail}}]->(b) "
            "ON CREATE SET r.valid_to = $vt, r.source_episode = $ep, r.fact = $fact "
            "ON MATCH SET r.valid_to = coalesce(r.valid_to, $vt)",
            head=head,
            tail=tail,
            poc=POC_TAG,
            vf=valid_from,
            vt=valid_to,
            ep=episode_id,
            fact=str(relation.get("fact") or "")[:300],
        )
        edge_count += 1
        written.append(
            {"head": head, "tail": tail, "rel_type": rel_type, "valid_from": valid_from}
        )

    # 同一 episode 内的「变更句」会同时带出旧值与新值（「由张三变更为李四」），
    # 两者 valid_from 相同 ⇒ 上面的跨 episode 规则管不到，需单独处理。
    invalidated += _arbitrate_same_anchor(session, written, episode_text, episode_id)

    return {"nodes": node_count, "edges": edge_count, "invalidated": invalidated}


def _arbitrate_same_anchor(
    session, written: list[dict[str, str]], episode_text: str, episode_id: str
) -> int:
    """同 (head, rel_type) 且同锚点的多条边：保留变更目标值，其余判失效。

    判定线索是**确定性的**（原文中尾部实体最后出现的位置），不依赖 LLM，
    这也是自研路线相对 Graphiti 的核心取舍：准确率换来可预测性。
    """
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for edge in written:
        groups[(edge["head"], edge["rel_type"])].append(edge)

    closed_total = 0
    for (head, rel_type), items in groups.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda e: episode_text.rfind(e["tail"]))
        keep = ordered[-1]
        for old in ordered[:-1]:
            if old["tail"] == keep["tail"]:
                continue
            session.run(
                f"MATCH (a:{ENT_LABEL} {{name: $head, poc: $poc}})"
                f"-[r:{rel_type}]->(b:{ENT_LABEL} {{name: $tail, poc: $poc}}) "
                "WHERE r.valid_from = $vf AND r.valid_to IS NULL "
                "SET r.valid_to = $vf, r.invalidated_by = $ep "
                "RETURN count(r) AS c",
                head=head,
                poc=POC_TAG,
                tail=old["tail"],
                vf=old["valid_from"],
                ep=episode_id,
            )
            closed_total += 1
    return closed_total


def query_current(session, rel_type: str) -> list[str]:
    rows = session.run(
        f"MATCH (a:{ENT_LABEL} {{poc: $poc}})-[r:{rel_type}]->(b) "
        "WHERE r.valid_to IS NULL RETURN b.name AS name",
        poc=POC_TAG,
    )
    return [r["name"] for r in rows]


def query_as_of(session, rel_type: str, as_of: str) -> list[str]:
    rows = session.run(
        f"MATCH (a:{ENT_LABEL} {{poc: $poc}})-[r:{rel_type}]->(b) "
        "WHERE r.valid_from <= $d AND (r.valid_to IS NULL OR r.valid_to > $d) "
        "RETURN b.name AS name",
        poc=POC_TAG,
        d=as_of,
    )
    return [r["name"] for r in rows]


def main() -> None:
    settings = get_settings()
    model = build_chat_model()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    metrics: dict[str, Any] = {"track": "S(自研)", "llm_calls": 0, "episodes": []}

    with driver.session(database=settings.neo4j_database) as session:
        session.run(f"MATCH (n:{ENT_LABEL} {{poc: $poc}}) DETACH DELETE n", poc=POC_TAG)

        for episode in EPISODES:
            result = extract_episode(model, episode)
            write_stats = write_episode(session, result, episode["text"])
            relations = result["payload"].get("relations") or []
            with_from = sum(1 for r in relations if _norm_date(r.get("valid_from")))
            metrics["episodes"].append(
                {
                    "id": episode["id"],
                    "entities": len(result["payload"].get("entities") or []),
                    "relations": len(relations),
                    "valid_from_rate": round(with_from / len(relations), 2) if relations else 0.0,
                    "invalidated_edges": write_stats["invalidated"],
                    "elapsed_ms": result["elapsed_ms"],
                }
            )
            metrics["llm_calls"] += 1

        # ---- 判分 ----
        current_rep = query_current(session, "LEGAL_REP")
        current_addr = query_current(session, "REGISTERED_AT")
        asof_rep = query_as_of(session, "LEGAL_REP", "2024-06-01")
        total_edges = session.run(
            f"MATCH (:{ENT_LABEL} {{poc: $poc}})-[r]->() RETURN count(r) AS c", poc=POC_TAG
        ).single()["c"]
        alive_edges = session.run(
            f"MATCH (:{ENT_LABEL} {{poc: $poc}})-[r]->() WHERE r.valid_to IS NULL "
            "RETURN count(r) AS c",
            poc=POC_TAG,
        ).single()["c"]

        metrics["answers"] = {
            "current_legal_rep": current_rep,
            "current_address": current_addr,
            "as_of_2024_06_01_rep": asof_rep,
        }
        norm = lambda values: [_squeeze(v) for v in values]  # noqa: E731
        metrics["score"] = {
            "current_ok": _squeeze(EXPECTED_CURRENT["LEGAL_REP"]) in norm(current_rep),
            "current_addr_ok": any(
                _squeeze(EXPECTED_CURRENT["REGISTERED_AT"]) in _squeeze(a)
                for a in current_addr
            ),
            "asof_ok": "张三" in asof_rep and "李四" not in asof_rep,
            "history_preserved": total_edges > alive_edges,
            "total_edges": total_edges,
            "alive_edges": alive_edges,
        }

    driver.close()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
