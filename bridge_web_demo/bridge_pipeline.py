# -*- coding: utf-8 -*-
"""Bridge Pipeline v1.0：MinerU 输出 -> LangExtract(DeepSeek) -> 实体关系 JSON。

严格遵循 docs/bridge-pipeline-specification-v1.0.md：
    step2 locate_source         遍历 mineru_mvp/output/*/ 取最新 full.md（回退 v2 JSON）
    step3 clean_text            去 HTML 标签 / HTML 实体 / 页眉页脚 / 多余空白
    step4 langextract_extract   调用 LangExtract（见 docs/langextract_spec.md 六条铁律）
    step5 build_graph           归一为 entities[] / relations[] 并落盘 output.json

用法（在 bridge_web_demo/ 目录下）：
    uv run python bridge_pipeline.py
    uv run python bridge_pipeline.py --mineru-output-dir ../mineru_mvp/output

本文件为独立 MVP，独立 uv 虚拟环境，不依赖也不修改 backend/ frontend/ contracts/。
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_JSON = BASE_DIR / "output.json"

# 只加载本目录的 .env，避免误读仓库其它位置的环境文件
load_dotenv(BASE_DIR / ".env")

import langextract as lx  # noqa: E402  (需在 load_dotenv 之后导入)
from langextract.core.tokenizer import UnicodeTokenizer  # noqa: E402
from langextract.factory import ModelConfig  # noqa: E402
from tenacity import (  # noqa: E402
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("bridge_pipeline")

# --------------------------------------------------------------------------- #
# 配置（禁止硬编码密钥，全部来自环境变量）
# --------------------------------------------------------------------------- #
_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
MODEL_ID = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

_DEFAULT_MINERU_OUTPUT = BASE_DIR.parent / "mineru_mvp" / "output"
_env_mineru_dir = os.getenv("MINERU_OUTPUT_DIR", "").strip()
MINERU_OUTPUT_DIR = (
    Path(_env_mineru_dir).expanduser()
    if _env_mineru_dir
    else _DEFAULT_MINERU_OUTPUT
)
if not MINERU_OUTPUT_DIR.is_absolute():
    MINERU_OUTPUT_DIR = (BASE_DIR / MINERU_OUTPUT_DIR).resolve()

SCHEMA_VERSION = "1.0"

# 管线步骤（规范 §2），键为 step，值为中文名
STEP_LABELS: dict[str, str] = {
    "receive_pdf": "接收 PDF",
    "mineru_parse": "MinerU 云解析",
    "locate_source": "定位最新 MinerU 产物",
    "clean_text": "文本清洗",
    "langextract_extract": "LangExtract 抽取",
    "build_graph": "构建实体关系图",
}

# --------------------------------------------------------------------------- #
# Prompt 与 Few-shot（对齐 prompts/entity_relation_extract_v1.md 的类别定义）
# 注：本 MVP 独立运行，Prompt 内联；生产化时应迁移至根目录 prompts/ 并带版本号。
# --------------------------------------------------------------------------- #
PROMPT_DESCRIPTION = """从中文文档文本中抽取实体与关系，只抽取文本中明确出现的信息，不要臆造。

可抽取的类别（extraction_class）：
- 公司：完整机构专有名称（如「XX有限公司」）；不要把业务板块名或描述性短语当作公司；
- 人物：人名；attributes 提供 {职务}；
- 业务板块：主营业务板块；attributes 提供 {收入, 占营收比例, 同比增速, 主体}；
- 财务指标：营收、净利润等指标数值；attributes 提供 {指标名称, 数值, 单位, 同比增速, 主体}；
- 控股关系：主体对标的的持股/收购关系；attributes 提供 {主体, 标的, 关系类型, 持股比例}。

对齐约束（极其重要，必须严格遵守）：
- extraction_text 必须是原文中【逐字连续出现】的片段，不得拼接、补全或改写。
- 表格中若单元格只有数字、而单位写在表头（如「营业收入(万元)」），则 extraction_text
  只填原文单元格里的数字（如 "128,560"），单位写入 attributes 的「单位」字段（如 "万元"）。
"""

EXAMPLE_TEXT = (
    "星辰科技股份有限公司 2023 年实现营业收入 50.0 亿元，同比增长 12.0%。"
    "其中，云计算板块实现收入 30.0 亿元，占营业收入比例为 60.0%。"
    "公司持有星云数据科技有限公司 70% 股权，公司董事长为王一鸣。"
)

_EXAMPLE_EXTRACTIONS = [
    lx.data.Extraction(
        extraction_class="公司",
        extraction_text="星辰科技股份有限公司",
        attributes={},
    ),
    lx.data.Extraction(
        extraction_class="财务指标",
        extraction_text="50.0 亿元",
        attributes={
            "指标名称": "营业收入",
            "数值": "50.0 亿元",
            "同比增速": "12.0%",
            "主体": "星辰科技股份有限公司",
        },
    ),
    lx.data.Extraction(
        extraction_class="业务板块",
        extraction_text="云计算板块",
        attributes={
            "收入": "30.0 亿元",
            "占营收比例": "60.0%",
            "主体": "星辰科技股份有限公司",
        },
    ),
    lx.data.Extraction(
        extraction_class="控股关系",
        extraction_text="星云数据科技有限公司",
        attributes={
            "主体": "星辰科技股份有限公司",
            "标的": "星云数据科技有限公司",
            "关系类型": "股权持有",
            "持股比例": "70%",
        },
    ),
    lx.data.Extraction(
        extraction_class="人物",
        extraction_text="王一鸣",
        attributes={"职务": "董事长"},
    ),
]

# 派生关系规则：类别 -> (关系名, tail 取值键；None 表示取 extraction_text)
DERIVED_RELATION_RULES: dict[str, tuple[str, str | None]] = {
    "财务指标": ("具有财务指标", "指标名称"),
    "业务板块": ("经营业务板块", None),
}

# 表格类 extraction 的默认主体
RELATION_CLASS = "控股关系"


class PipelineError(Exception):
    """Bridge Pipeline 业务错误。"""


ProgressCallback = Callable[[dict[str, Any]], None]


def _emit(
    on_progress: ProgressCallback | None,
    name: str,
    status: str,
    detail: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """向调用方（CLI / FastAPI）推送步骤级进度。"""
    if on_progress is None:
        return
    on_progress(
        {
            "name": name,
            "label": STEP_LABELS.get(name, name),
            "status": status,
            "detail": detail,
            "duration_ms": duration_ms,
        }
    )


# --------------------------------------------------------------------------- #
# step2：定位最新 MinerU 产物
# --------------------------------------------------------------------------- #
def find_latest_source(output_dir: Path) -> tuple[Path, str]:
    """遍历 output/ 子目录，返回 (源文件路径, input_mode)。

    优先级：任意层级的 full.md > *_content_list_v2.json（均按 mtime 取最新）。
    """

    def _newest(pattern: str, recursive: bool) -> list[Path]:
        it = output_dir.rglob(pattern) if recursive else output_dir.glob(pattern)
        return sorted((p for p in it if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)

    md_candidates = _newest("full.md", recursive=True)
    if md_candidates:
        return md_candidates[0], "full_md"

    v2_candidates = _newest("*_content_list_v2.json", recursive=True)
    if v2_candidates:
        return v2_candidates[0], "content_list_v2_fallback"

    raise PipelineError(
        f"在 {output_dir} 下未找到 full.md 或 *_content_list_v2.json，请先运行 mineru_mvp/run_mvp.py"
    )


# --------------------------------------------------------------------------- #
# step2 辅助：读取源文件为原始文本
# --------------------------------------------------------------------------- #
def _iter_v2_items(node: Any):
    """递归展平 content_list v2（页列表 -> 条目列表）与 v1（条目列表）。"""
    if isinstance(node, list):
        for child in node:
            yield from _iter_v2_items(child)
    elif isinstance(node, dict):
        yield node


def _v2_item_text(item: dict[str, Any]) -> str:
    """从 content_list v2/v1 单条目中抽取可读文本（规范 §3.3）。"""
    content = item.get("content")
    parts: list[str] = []

    # 优先取表格 HTML（v2: content.html）
    if isinstance(content, dict) and isinstance(content.get("html"), str):
        parts.append(content["html"])

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            parts.append(content["text"])
        for key in ("title_content", "paragraph_content", "text_content"):
            for sub in content.get(key) or []:
                if isinstance(sub, dict) and isinstance(sub.get("content"), str):
                    parts.append(sub["content"])
        for key in ("table_caption", "image_caption", "table_footnote"):
            for sub in content.get(key) or []:
                if isinstance(sub, str):
                    parts.append(sub)
                elif isinstance(sub, dict) and isinstance(sub.get("content"), str):
                    parts.append(sub["content"])

    # v1 扁平结构兜底
    if isinstance(item.get("text"), str):
        parts.append(item["text"])
    if isinstance(item.get("table_caption"), list):
        parts.extend(str(c) for c in item["table_caption"])
    if isinstance(item.get("body"), str):
        parts.append(item["body"])

    return "\n".join(p for p in parts if p and p.strip())


def load_raw_text(source_path: Path, input_mode: str) -> str:
    """按 input_mode 读取原始文本（含表格 HTML）。"""
    if input_mode == "full_md":
        return source_path.read_text(encoding="utf-8", errors="replace")

    if input_mode == "content_list_v2_fallback":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        blocks = [_v2_item_text(item) for item in _iter_v2_items(data)]
        return "\n".join(b for b in blocks if b.strip())

    raise PipelineError(f"未知 input_mode: {input_mode}")


# --------------------------------------------------------------------------- #
# step3：文本清洗
# --------------------------------------------------------------------------- #
_NOISE_LINE_PATTERNS = [
    re.compile(r"^第\s*\d+\s*页(\s*[/／]\s*共?\s*\d+\s*页)?$"),
    re.compile(r"^[-—–\s]*\d{1,4}[-—–\s]*$"),
    re.compile(r"^page\s*\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^[-=_*~·.]{3,}$"),
    re.compile(r"^\s*$"),
]


def _html_to_text(raw: str) -> str:
    """HTML -> 文本：表格单元格用 TAB、行用换行分隔，其余标签剥离。"""
    text = re.sub(r"(?i)</t[dh]\s*>", "\t", raw)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|table)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _is_noise_line(line: str) -> bool:
    return any(p.match(line) for p in _NOISE_LINE_PATTERNS[:4])


def clean_text(raw: str) -> str:
    """清洗规则见规范 §4。"""
    text = _html_to_text(raw)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ").replace("\ufeff", "")

    kept: list[str] = []
    for line in text.splitlines():
        # 折叠非 TAB 空白为单空格，保留表格 TAB 分隔
        line = re.sub(r"[^\S\t]+", " ", line).strip()
        if not line:
            kept.append("")
            continue
        if _is_noise_line(line):
            continue
        kept.append(line)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# --------------------------------------------------------------------------- #
# step4：LangExtract 抽取（六条铁律见 docs/langextract_spec.md）
# --------------------------------------------------------------------------- #
def build_model_config() -> ModelConfig:
    return ModelConfig(
        model_id=MODEL_ID,
        provider="openai",  # 铁律1：否则 "deepseek*" 被 Ollama 正则命中
        provider_kwargs={
            "api_key": _API_KEY,
            "base_url": BASE_URL,  # 铁律5：末尾不带 /chat/completions
            "temperature": 0.0,
            "max_workers": 1,
        },
    )


RETRY_POLICY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


@retry(**RETRY_POLICY)
def _extract_once(text: str):
    examples = [lx.data.ExampleData(text=EXAMPLE_TEXT, extractions=_EXAMPLE_EXTRACTIONS)]
    return lx.extract(
        text_or_documents=text,
        prompt_description=PROMPT_DESCRIPTION,
        examples=examples,
        config=build_model_config(),
        use_schema_constraints=False,  # 铁律2：DeepSeek 不支持 json_schema 严格模式
        fence_output=False,  # 铁律3：走原生 JSON 输出
        tokenizer=UnicodeTokenizer(),  # 铁律4：中文必须逐字切分
        max_char_buffer=1000,
        extraction_passes=1,
        show_progress=False,
    )


def extract_entities(text: str):
    if not _API_KEY or _API_KEY.startswith("sk-your"):
        raise PipelineError("未配置真实 DEEPSEEK_API_KEY，请编辑 bridge_web_demo/.env")
    return _extract_once(text)


# --------------------------------------------------------------------------- #
# step5：归一为实体关系
# --------------------------------------------------------------------------- #
def _char_interval(ext) -> dict[str, int] | None:
    interval = getattr(ext, "char_interval", None)
    if interval is None:
        return None
    start = getattr(interval, "start_pos", None)
    end = getattr(interval, "end_pos", None)
    if start is None or end is None:
        return None
    return {"start_pos": int(start), "end_pos": int(end)}


def _alignment_status(ext) -> str | None:
    status = getattr(ext, "alignment_status", None)
    if status is None:
        return None
    return str(status).split(".")[-1].lower()


def build_graph(
    annotated,
    source_meta: dict[str, Any],
    steps: list[dict[str, Any]],
    trace_id: str,
) -> dict[str, Any]:
    """extractions -> entities / relations（规范 §5）。"""
    extractions = list(getattr(annotated, "extractions", None) or [])

    entities: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    seen_relations: set[tuple] = set()

    def ensure_entity(name: Any, etype: str, *, grounded: bool = False) -> str | None:
        """保证端点实体存在，返回其 name；name 为空则返回 None。"""
        if not name or not isinstance(name, str):
            return None
        name = name.strip()
        if not name:
            return None
        if name not in entities:
            entities[name] = {
                "id": f"e{len(entities) + 1}",
                "type": etype,
                "name": name,
                "attributes": {},
                "char_interval": None,
                "alignment_status": None,
                "grounded": grounded,
                "auto_created": True,
                "evidence": name,
            }
        return name

    def add_relation(rel: dict[str, Any]) -> None:
        key = (
            rel["head"],
            rel["relation"],
            rel["tail"],
            json.dumps(rel["attributes"], ensure_ascii=False, sort_keys=True),
        )
        if key in seen_relations:
            return
        seen_relations.add(key)
        rel["id"] = f"r{len(relations) + 1}"
        relations.append(rel)

    for ext in extractions:
        cls = getattr(ext, "extraction_class", "") or ""
        text = getattr(ext, "extraction_text", "") or ""
        attrs = dict(getattr(ext, "attributes", None) or {})
        interval = _char_interval(ext)
        status = _alignment_status(ext)
        text = text.strip()
        if not text:
            continue

        if cls == RELATION_CLASS:
            head = str(attrs.get("主体", "")).strip()
            tail = str(attrs.get("标的", "") or text).strip()
            rel_type = str(attrs.get("关系类型", "") or "关联").strip()
            if not head or not tail:
                continue
            ensure_entity(head, "公司")
            ensure_entity(tail, "公司")
            extra_attrs = {
                k: v for k, v in attrs.items() if k not in ("主体", "标的", "关系类型")
            }
            add_relation(
                {
                    "head": head,
                    "head_type": "公司",
                    "relation": rel_type,
                    "tail": tail,
                    "tail_type": "公司",
                    "attributes": extra_attrs,
                    "derived": False,
                    "char_interval": interval,
                    "alignment_status": status,
                    "evidence": text,
                }
            )
            continue

        # 其余类别 -> 实体
        entity = {
            "id": f"e{len(entities) + 1}",
            "type": cls or "OTHER",
            "name": text,
            "attributes": attrs,
            "char_interval": interval,
            "alignment_status": status,
            "grounded": interval is not None,
            "auto_created": False,
            "evidence": text,
        }
        entities.setdefault(text, entity)

        # 派生关系
        rule = DERIVED_RELATION_RULES.get(cls)
        if rule:
            rel_name, tail_key = rule
            head = str(attrs.get("主体", "")).strip()
            tail = str(attrs.get(tail_key, "") if tail_key else text).strip()
            if head and tail and head != tail:
                ensure_entity(head, "公司")
                ensure_entity(tail, cls)
                extra_attrs = {k: v for k, v in attrs.items() if k != "主体"}
                add_relation(
                    {
                        "head": head,
                        "head_type": "公司",
                        "relation": rel_name,
                        "tail": tail,
                        "tail_type": cls,
                        "attributes": extra_attrs,
                        "derived": True,
                        "char_interval": interval,
                        "alignment_status": status,
                        "evidence": text,
                    }
                )

    entity_list = list(entities.values())
    entity_types: dict[str, int] = {}
    for ent in entity_list:
        entity_types[ent["type"]] = entity_types.get(ent["type"], 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_meta,
        "model": {
            "provider": "openai",
            "model_id": MODEL_ID,
            "base_url": BASE_URL,
            "use_schema_constraints": False,
            "fence_output": False,
            "tokenizer": "UnicodeTokenizer",
            "temperature": 0.0,
        },
        "steps": steps,
        "entities": entity_list,
        "relations": relations,
        "stats": {
            "entity_count": len(entity_list),
            "relation_count": len(relations),
            "derived_relation_count": sum(1 for r in relations if r["derived"]),
            "ungrounded_count": sum(1 for e in entity_list if not e["grounded"]),
            "entity_types": entity_types,
        },
    }


# --------------------------------------------------------------------------- #
# 主编排
# --------------------------------------------------------------------------- #
def run_pipeline(
    mineru_output_dir: Path | None = None,
    output_path: Path | None = None,
    on_progress: ProgressCallback | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """执行 step2 ~ step5，落盘 output.json 并返回结果字典。"""
    mineru_output_dir = Path(mineru_output_dir or MINERU_OUTPUT_DIR).resolve()
    output_path = Path(output_path or OUTPUT_JSON).resolve()
    trace_id = trace_id or str(uuid.uuid4())
    steps: list[dict[str, Any]] = []

    def _record(name: str, status: str, detail: str | None, duration_ms: int | None) -> None:
        entry = {
            "name": name,
            "label": STEP_LABELS.get(name, name),
            "status": status,
            "detail": detail,
            "duration_ms": duration_ms,
        }
        for i, existing in enumerate(steps):
            if existing["name"] == name:
                steps[i] = entry
                break
        else:
            steps.append(entry)
        _emit(on_progress, name, status, detail, duration_ms)

    # ---- step2 定位源文件 ----
    _record("locate_source", "processing", None, None)
    t0 = time.perf_counter()
    try:
        source_path, input_mode = find_latest_source(mineru_output_dir)
    except Exception as exc:  # noqa: BLE001
        _record("locate_source", "failed", str(exc), int((time.perf_counter() - t0) * 1000))
        raise
    _record(
        "locate_source",
        "completed",
        f"{input_mode}: {source_path}",
        int((time.perf_counter() - t0) * 1000),
    )
    logger.info("已定位源文件: %s (mode=%s)", source_path, input_mode)

    # ---- step3 读取 + 清洗 ----
    _record("clean_text", "processing", None, None)
    t0 = time.perf_counter()
    try:
        raw = load_raw_text(source_path, input_mode)
        cleaned = clean_text(raw)
        if not cleaned:
            raise PipelineError("清洗后文本为空，无法抽取")
    except Exception as exc:  # noqa: BLE001
        _record("clean_text", "failed", str(exc), int((time.perf_counter() - t0) * 1000))
        raise
    _record(
        "clean_text",
        "completed",
        f"原始 {len(raw)} 字符 -> 清洗后 {len(cleaned)} 字符",
        int((time.perf_counter() - t0) * 1000),
    )

    # ---- step4 抽取 ----
    _record("langextract_extract", "processing", None, None)
    t0 = time.perf_counter()
    try:
        annotated = extract_entities(cleaned)
    except Exception as exc:  # noqa: BLE001
        _record(
            "langextract_extract", "failed", str(exc), int((time.perf_counter() - t0) * 1000)
        )
        raise
    extraction_count = len(getattr(annotated, "extractions", None) or [])
    _record(
        "langextract_extract",
        "completed",
        f"抽取 {extraction_count} 条原始结果",
        int((time.perf_counter() - t0) * 1000),
    )

    # ---- step5 归一 + 落盘 ----
    _record("build_graph", "processing", None, None)
    t0 = time.perf_counter()
    try:
        source_meta = {
            "input_mode": input_mode,
            "mineru_task_dir": str(source_path.parent),
            "source_path": str(source_path),
            "text_chars": len(cleaned),
        }
        result = build_graph(annotated, source_meta, steps, trace_id)
        stats = result["stats"]
        # 先记录 build_graph 完成（steps 为同一列表对象，会同步进 result）
        _record(
            "build_graph",
            "completed",
            f"实体 {stats['entity_count']} / 关系 {stats['relation_count']} -> {output_path.name}",
            int((time.perf_counter() - t0) * 1000),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        _record("build_graph", "failed", str(exc), int((time.perf_counter() - t0) * 1000))
        raise
    logger.info("已写入: %s", output_path)
    return result


def _print_summary(result: dict[str, Any]) -> None:
    src = result["source"]
    stats = result["stats"]
    print("\n===== Bridge Pipeline 执行结果 =====")
    print(f"读取源文件 : {src['source_path']}")
    print(f"输入模式   : {src['input_mode']}")
    print(f"清洗后字符 : {src['text_chars']}")
    print(f"实体数     : {stats['entity_count']}  (类型分布: {stats['entity_types']})")
    print(f"关系数     : {stats['relation_count']}  (派生: {stats['derived_relation_count']})")
    print(f"未定位实体 : {stats['ungrounded_count']}")

    print("\n----- 实体 -----")
    for ent in result["entities"]:
        flag = "已定位" if ent["grounded"] else "未定位"
        print(f"  [{ent['type']}] {ent['name']} ({flag})")

    print("\n----- 关系 -----")
    for rel in result["relations"]:
        attrs = "，".join(f"{k}={v}" for k, v in rel["attributes"].items()) or "-"
        tag = "派生" if rel["derived"] else "显式"
        print(f"  ({rel['head']}) -[{rel['relation']}{' ' + attrs if attrs else ''}]-> ({rel['tail']}) [{tag}]")

    print(f"\n[OK] 结果已写入: {OUTPUT_JSON}")


def main() -> int:
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Bridge Pipeline (MinerU -> LangExtract)")
    parser.add_argument(
        "--mineru-output-dir",
        default=str(MINERU_OUTPUT_DIR),
        help="MinerU 输出根目录，默认取 MINERU_OUTPUT_DIR 或 ../mineru_mvp/output",
    )
    parser.add_argument("--output", default=str(OUTPUT_JSON), help="结果 JSON 输出路径")
    args = parser.parse_args()

    try:
        result = run_pipeline(Path(args.mineru_output_dir), Path(args.output))
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] Bridge Pipeline 失败: {exc}")
        return 1

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
