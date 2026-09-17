# -*- coding: utf-8 -*-
"""知识图谱检索工具（LangChain Tool 定义）。

数据源：../bridge_web_demo/output.json（schema_version 1.0，只读，绝不修改）。
实体字段带 grounded / char_interval / alignment_status，工具中按需取用。

匹配策略（分层，越靠前分越高，全部为「模糊匹配」，不要求精确相等）：
    100  实体名 == 查询
     95  实体名包含完整查询
     90  完整查询包含实体名
     85  关键词与实体名相同
     70  关键词被实体名包含（例：查询「华辰智能」-> 关键词「智能」命中「智能制造」）
     65  实体名出现在关键词中
     40  与查询字符重叠 >= 2 个

本文件为独立 MVP，不依赖也不修改 backend/ frontend/ contracts/。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent

# 默认数据源：仓库内 bridge_web_demo/output.json（可用 KG_OUTPUT_JSON 覆盖）
_DEFAULT_KG = BASE_DIR.parent / "bridge_web_demo" / "output.json"
_env_kg = os.getenv("KG_OUTPUT_JSON", "").strip()
KG_PATH = Path(_env_kg).expanduser() if _env_kg else _DEFAULT_KG
if not KG_PATH.is_absolute():
    KG_PATH = (BASE_DIR / KG_PATH).resolve()

# 中文问法噪声词：切词后剔除，避免「查一下」之类被当作实体关键词
_STOPWORDS = (
    "帮我", "请", "麻烦", "查一下", "查询", "查查", "查", "看一下", "看",
    "一下", "的", "是多少", "多少", "怎么样", "如何", "是", "呢", "吗",
    "公司", "数据", "情况", "信息",
)
_REVENUE_HINTS = ("营收", "收入", "营业收入", "营业额", "revenue")

_cache: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def load_kg(force: bool = False) -> dict[str, Any]:
    """读取并缓存 output.json。"""
    global _cache
    if _cache is None or force:
        if not KG_PATH.exists():
            raise FileNotFoundError(
                f"未找到知识图谱数据源：{KG_PATH}\n"
                "请先在 bridge_web_demo/ 下运行 bridge_pipeline.py 生成 output.json，"
                "或通过 KG_OUTPUT_JSON 指定路径。"
            )
        _cache = json.loads(KG_PATH.read_text(encoding="utf-8"))
    return _cache


# --------------------------------------------------------------------------- #
# 模糊匹配
# --------------------------------------------------------------------------- #
def candidate_terms(query: str) -> list[str]:
    """把自然语言查询切成候选关键词（整句 + 中文 2-gram + ASCII 单词）。"""
    q = (query or "").strip()
    if not q:
        return []

    cleaned = q
    for word in _STOPWORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"[，。！？、,.!?;；:：\"'“”‘’()（）\[\]【】\s]+", " ", cleaned)

    terms: list[str] = [q]
    for chunk in cleaned.split():
        if chunk and chunk != q:
            terms.append(chunk)
        # 中文 2-gram（覆盖「华辰智能」-> 智能 这类部分命中）
        han = "".join(re.findall(r"[\u4e00-\u9fff]", chunk))
        for i in range(len(han) - 1):
            terms.append(han[i : i + 2])
        # ASCII 单词（>=2 字符），如 GLM / revenue
        for word in re.findall(r"[A-Za-z0-9]{2,}", chunk):
            terms.append(word)

    seen: set[str] = set()
    ordered: list[str] = []
    for t in terms:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def _score(name: str, query: str, terms: list[str]) -> tuple[int, str] | None:
    """返回 (分值, 命中原因)，未命中返回 None。"""
    if not name or not query:
        return None
    if query == name:
        return 100, "实体名与查询完全相同"
    if query in name:
        return 95, f"实体名包含完整查询「{query}」"
    if name in query:
        return 90, f"完整查询包含实体名「{name}」"
    for t in terms:
        if t != query and t == name:
            return 85, f"关键词「{t}」与实体名相同"
    for t in terms:
        if t != query and t in name:
            return 70, f"关键词「{t}」被实体名包含"
    for t in terms:
        if len(t) >= 2 and name in t:
            return 65, f"实体名出现在关键词「{t}」中"
    overlap = sorted(set(name) & set(query))
    # 字符重叠兜底：至少 2 字且覆盖实体名一半以上，避免长实体名被个别字误召回
    if len(overlap) >= 2 and len(overlap) / len(name) >= 0.5:
        return 40, f"与查询存在字符重叠「{''.join(overlap)}」"
    return None


def match_entities(kg: dict[str, Any], query: str, limit: int = 8) -> list[dict[str, Any]]:
    """按分层规则对实体打分排序，返回命中列表。"""
    terms = candidate_terms(query)
    hits: list[tuple[int, str, dict[str, Any]]] = []
    for entity in kg.get("entities", []) or []:
        scored = _score(str(entity.get("name", "")), (query or "").strip(), terms)
        if scored:
            hits.append((scored[0], scored[1], entity))
    hits.sort(key=lambda item: (-item[0], str(item[2].get("id", ""))))
    return [
        {"score": s, "match_reason": reason, "entity": entity}
        for s, reason, entity in hits[:limit]
    ]


# --------------------------------------------------------------------------- #
# 文本渲染
# --------------------------------------------------------------------------- #
def _fmt_attrs(attrs: dict[str, Any] | None) -> str:
    if not attrs:
        return "（无属性）"
    return "; ".join(f"{k}={v}" for k, v in attrs.items() if str(v).strip()) or "（无属性）"


def _entity_line(entity: dict[str, Any], score: int, reason: str) -> str:
    interval = entity.get("char_interval") or {}
    span = (
        f"{interval.get('start_pos')}-{interval.get('end_pos')}"
        if interval
        else "null"
    )
    return (
        f"- [{entity.get('id')}] {entity.get('name')} | 类型={entity.get('type')} "
        f"| 匹配分={score}（{reason}）\n"
        f"    grounded={entity.get('grounded')} alignment_status={entity.get('alignment_status')} "
        f"char_interval={span} auto_created={entity.get('auto_created')}\n"
        f"    属性：{_fmt_attrs(entity.get('attributes'))}\n"
        f"    原文证据：{entity.get('evidence', '')}"
    )


def _relations_of(kg: dict[str, Any], name: str) -> list[dict[str, Any]]:
    rels = kg.get("relations", []) or []
    return [r for r in rels if r.get("head") == name or r.get("tail") == name]


def _relation_line(rel: dict[str, Any]) -> str:
    attrs = rel.get("attributes") or {}
    return (
        f"    {rel.get('head')} -[{rel.get('relation')}]-> {rel.get('tail')} "
        f"({_fmt_attrs(attrs)}) | derived={rel.get('derived')} "
        f"alignment_status={rel.get('alignment_status')} 证据={rel.get('evidence', '')}"
    )


def _overview(kg: dict[str, Any]) -> list[str]:
    """图谱内全部「营业收入 / 营业收入占比」类关系，作为无实体命中时的兜底说明。"""
    lines: list[str] = []
    for rel in kg.get("relations", []) or []:
        attrs = rel.get("attributes") or {}
        metric = str(attrs.get("指标名称", ""))
        if any(hint in metric for hint in ("营业收入", "营收", "收入")):
            lines.append(_relation_line(rel))
    return lines


def _render(kg: dict[str, Any], query: str, hits: list[dict[str, Any]]) -> str:
    stats = kg.get("stats") or {}
    head = (
        f"[知识图谱检索结果]\n"
        f"数据源: {KG_PATH}\n"
        f"schema_version={kg.get('schema_version')} 生成时间={kg.get('generated_at')} "
        f"trace_id={kg.get('trace_id')}\n"
        f"规模: 实体 {stats.get('entity_count')} / 关系 {stats.get('relation_count')} "
        f"(未 grounded 实体 {stats.get('ungrounded_count')})\n"
        f"查询: {query!r} | 命中实体数: {len(hits)}\n"
    )
    if not hits:
        names = [f"{e.get('name')}({e.get('type')})" for e in kg.get("entities", []) or []]
        body = [
            "\n【未命中】图谱中不存在与查询直接/模糊对应的实体，"
            "请勿把下列图谱数据归因到查询对象，只能作为「图谱现有内容」的说明。",
            f"\n图谱现有实体（{len(names)} 个）：",
            "  " + "、".join(names),
            "\n图谱现有营收类关系（兜底参考）：",
            *(_overview(kg) or ["    （无）"]),
        ]
        return head + "\n".join(body)

    revenue_focus = any(h in query for h in _REVENUE_HINTS)
    if revenue_focus:
        head += "（查询含营收/收入意图，命中实体的营收类关系优先展示）\n"

    body = ["\n【命中实体】"]
    for hit in hits:
        entity = hit["entity"]
        body.append(_entity_line(entity, hit["score"], hit["match_reason"]))
        rels = _relations_of(kg, str(entity.get("name", "")))
        if revenue_focus:
            rels.sort(
                key=lambda r: 0
                if any(h in str((r.get("attributes") or {}).get("指标名称", "")) for h in _REVENUE_HINTS)
                else 1
            )
        if rels:
            body.append(f"    相关关系（{len(rels)} 条）：")
            body.extend(_relation_line(r) for r in rels)
        else:
            body.append("    相关关系：无")
    body.append(
        "\n【使用约束】回答时请标明数据来源（output.json / 上述 trace_id），"
        "并保留 grounded 与 alignment_status 的原文口径；未命中实体不得臆造。"
    )
    return head + "\n".join(body)


# --------------------------------------------------------------------------- #
# LangChain Tool
# --------------------------------------------------------------------------- #
@tool
def search_knowledge_graph(query: str) -> str:
    """检索本地知识图谱（bridge_web_demo/output.json 抽取的实体关系）。

    支持模糊匹配：实体名包含查询词、查询词包含实体名、或关键词部分命中均可召回，
    不要求精确相等。适合查询「某主体/某板块的营收、净利润、同比增速、占比」等问题。

    Args:
        query: 自然语言或实体关键词，例如「华辰智能的营收」「新能源 营业收入」。

    Returns:
        纯文本字符串：命中实体（含 grounded / alignment_status / char_interval / 属性）、
        相关关系与原文证据；若无命中实体则返回图谱现有实体清单与营收兜底数据。
    """
    kg = load_kg()
    hits = match_entities(kg, query)
    return _render(kg, query, hits)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 控制台兜底
    demo_query = sys.argv[1] if len(sys.argv) > 1 else "华辰智能的营收"
    print(search_knowledge_graph.invoke({"query": demo_query}))
