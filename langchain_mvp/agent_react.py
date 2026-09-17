# -*- coding: utf-8 -*-
"""LangChain ReAct Agent MVP：DeepSeek + 本地知识图谱工具。

流程：用户提问 -> ReAct Agent 思考 -> 调用 search_knowledge_graph ->
      观察工具返回 -> 生成最终回答。

用法（在 langchain_mvp/ 目录下，独立 uv 虚拟环境）：
    uv run python agent_react.py
    uv run python agent_react.py "帮我查一下华辰智能的营收"
    uv run python agent_react.py "新能源板块的营业收入和净利润"

依赖：langchain 1.x（create_agent，LangGraph 底座）/ langchain-openai / python-dotenv。
本文件为独立 MVP，不依赖也不修改 backend/ frontend/ contracts/ mineru_mvp/ bridge_web_demo/。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Windows GBK 控制台兜底：必须在任何 print 之前执行
# --------------------------------------------------------------------------- #
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

# 只加载本目录 .env，避免误读仓库其它位置的环境文件
load_dotenv(BASE_DIR / ".env")

import os  # noqa: E402

from langchain.agents import create_agent  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI  # noqa: E402

from kg_tools import KG_PATH, search_knowledge_graph  # noqa: E402 (需在 load_dotenv 之后导入)

DEFAULT_QUESTION = "帮我查一下华辰智能的营收"

API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
MODEL_ID = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

SYSTEM_PROMPT = """你是企业知识图谱问答助手，只能依据工具 search_knowledge_graph 的返回内容作答。

工作规则：
1. 用户询问任何主体/板块的营收、收入、净利润、同比增速、占比等指标时，必须先调用
   search_knowledge_graph 获取图谱数据，禁止凭记忆直接回答。
2. 工具支持模糊匹配（实体名包含查询词即可命中），因此可能返回多个候选实体或
   「关键词部分命中」的结果，请明确说明命中的是哪个实体、匹配是否为部分匹配。
3. 如果查询对象没有在工具返回的命中实体中出现（例如图谱只覆盖集团整体与业务板块），
   必须直接说明「知识图谱中没有名为 X 的实体」，不得把图谱内其它主体的数据说成 X 的数据；
   如需给出参考信息，必须显式标注这些数据属于图谱中的哪个主体。
4. 引用数值时必须保留原文单位（万元 / %）与口径，并注明数据来源为 output.json 及其 trace_id。
5. 所有文字输出（包括工具调用前的思考说明）必须使用简体中文，先给结论，再列关键数据。"""


# --------------------------------------------------------------------------- #
# 输出辅助
# --------------------------------------------------------------------------- #
def _text(content: Any) -> str:
    """兼容 str / content blocks（LangChain 1.x 多模态 content 结构）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "") or block.get("content", "") or ""))
        return "\n".join(p for p in parts if p)
    return str(content or "")


def _rule(title: str) -> str:
    return f"\n{'=' * 72}\n{title}\n{'=' * 72}"


def _describe(message: BaseMessage) -> tuple[str, str]:
    """把一条消息翻译成人可读的 (阶段标签, 正文)。"""
    if isinstance(message, HumanMessage):
        return "用户提问", _text(message.content)
    if isinstance(message, AIMessage):
        thinking = _text(message.content).strip()
        calls = getattr(message, "tool_calls", None) or []
        if calls:
            action = "\n".join(
                f"  -> 调用工具 {c.get('name')}  参数 {json.dumps(c.get('args'), ensure_ascii=False)}"
                for c in calls
            )
            return "Agent 思考 / 行动", (thinking or "（本轮无文字思考，直接发起工具调用）") + "\n" + action
        return "Agent 最终回答", thinking or "（空回答）"
    if isinstance(message, ToolMessage):
        body = _text(message.content)
        return f"工具观察 ( {message.name} )", body
    return type(message).__name__, _text(getattr(message, "content", ""))


def _usage(message: BaseMessage) -> dict[str, Any] | None:
    meta = getattr(message, "usage_metadata", None)
    return dict(meta) if meta else None


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def build_agent() -> Any:
    if not API_KEY:
        raise RuntimeError(
            "缺少 DEEPSEEK_API_KEY。请复制 .env.example 为 .env 并填写真实密钥（.env 已被 .gitignore 忽略）。"
        )
    llm = ChatOpenAI(
        model=MODEL_ID,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0,
        timeout=60,
        max_retries=2,
        use_responses_api=False,  # DeepSeek 为 OpenAI 兼容的 Chat Completions 端点
    )
    # LangChain 1.x 官方推荐入口：create_agent（ReAct 循环，LangGraph 底座）
    return create_agent(model=llm, tools=[search_knowledge_graph], system_prompt=SYSTEM_PROMPT)


def run(question: str, verbose: bool = True) -> dict[str, Any]:
    agent = build_agent()
    trace_id = str(uuid.uuid4())
    started = time.perf_counter()

    if verbose:
        print(_rule("LangChain ReAct Agent MVP"))
        print(f"模型      : {MODEL_ID} @ {BASE_URL}")
        print(f"工具      : search_knowledge_graph")
        print(f"数据源    : {KG_PATH}")
        print(f"trace_id  : {trace_id}")
        print(f"问题      : {question}")

    steps: list[dict[str, Any]] = []
    messages: list[BaseMessage] = []
    seen = 0

    # stream_mode="values" 每步返回完整 state，便于逐步打印 ReAct 思考过程
    for state in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
    ):
        current = state.get("messages", []) if isinstance(state, dict) else []
        messages = current
        for message in current[seen:]:
            label, body = _describe(message)
            steps.append(
                {
                    "type": type(message).__name__,
                    "label": label,
                    "tool_calls": [
                        {"name": c.get("name"), "args": c.get("args")}
                        for c in (getattr(message, "tool_calls", None) or [])
                    ],
                    "content": body,
                    "usage": _usage(message),
                }
            )
            if verbose:
                print(_rule(f"步骤 {len(steps)} · {label}"))
                print(body)
        seen = len(current)

    elapsed = time.perf_counter() - started
    answer = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not (getattr(message, "tool_calls", None) or []):
            answer = _text(message.content).strip()
            break

    result = {
        "trace_id": trace_id,
        "question": question,
        "answer": answer,
        "model": {"model_id": MODEL_ID, "base_url": BASE_URL, "temperature": 0},
        "kg_source": str(KG_PATH),
        "elapsed_seconds": round(elapsed, 2),
        "message_count": len(messages),
        "tool_calls": [
            call for step in steps for call in step["tool_calls"]
        ],
        "steps": steps,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if verbose:
        print(_rule("最终回答"))
        print(answer)
        print(_rule(f"完成：{len(steps)} 步，耗时 {elapsed:.2f}s"))
    return result


def save_artifacts(result: dict[str, Any]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "last_run.json"
    md_path = OUTPUT_DIR / "last_run.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# LangChain ReAct Agent 运行记录",
        "",
        f"- trace_id: `{result['trace_id']}`",
        f"- 问题: {result['question']}",
        f"- 模型: `{result['model']['model_id']}` @ {result['model']['base_url']}",
        f"- 数据源: `{result['kg_source']}`",
        f"- 耗时: {result['elapsed_seconds']}s",
        f"- 生成时间: {result['generated_at']}",
        "",
        "## 思考过程",
        "",
    ]
    for index, step in enumerate(result["steps"], start=1):
        lines += [f"### 步骤 {index} · {step['label']}", "", "```text", step["content"], "```", ""]
    lines += ["## 最终回答", "", result["answer"], ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="LangChain ReAct Agent MVP（DeepSeek + 本地知识图谱）")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="要提问的自然语言问题")
    parser.add_argument("--no-save", action="store_true", help="不写入 output/ 运行记录")
    args = parser.parse_args()

    result = run(args.question)
    if not args.no_save:
        json_path, md_path = save_artifacts(result)
        print(f"运行记录已写入：{md_path}")
        print(f"结构化轨迹已写入：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
