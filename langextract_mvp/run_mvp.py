# -*- coding: utf-8 -*-
"""LangExtract + DeepSeek(OpenAI 兼容) 最小可运行抽取 MVP。

流程：sample_text.txt（中文企业年报摘录） -> LangExtract 抽取 -> output/extractions.jsonl
运行（必须在本目录 langextract_mvp/ 下）：
    uv run python run_mvp.py

本文件为独立 MVP，独立 uv 虚拟环境，不依赖也不修改 backend/ frontend/ contracts/。

--------------------------------------------------------------------------------
实测差异记录（CODEBUDDY.md「实测结果反哺规则」：以本地实际跑通结果为准）
--------------------------------------------------------------------------------
本环境实测版本：langextract==1.7.0，openai==3.14.1（见 uv.lock）。
以下为「官方 README / 直觉用法」与「本地源码实测」的差异，逐条已在本脚本中规避：

[差异1] 模型名以 "deepseek" 开头会被内置 Ollama Provider 抢走。
    官方文档只说"非 GPT 模型需显式指定 provider"，但未点明原因。
    本地源码证据：langextract/providers/patterns.py 中 OLLAMA_PATTERNS 含 `^deepseek`，
    而 OPENAI_PATTERNS 只匹配 `^gpt-*` / `^o[1-9]`。因此 model_id="deepseek-chat"
    自动路由会命中 OllamaLanguageModel（需要本地 Ollama 服务）。
    实测结论：必须显式 provider="openai"，走 OpenAI 兼容端点。

[差异2] DeepSeek 不支持 OpenAI 的 json_schema 严格结构化输出。
    本地源码证据：langextract/providers/schemas/openai.py 的 OpenAISchema.response_format
    会生成 {"type": "json_schema", ..., "strict": true}；而 lx.extract() 默认
    use_schema_constraints=True（见 langextract/extraction.py 默认值）。
    实测结论：必须传 use_schema_constraints=False，使 provider 回退到
    response_format={"type": "json_object"}（见 openai.py
    `_build_chat_completions_params` 中 format_type=JSON 的分支）。

[差异3] DeepSeek 的 JSON 模式要求提示词里出现 "json" 字样。
    langExtract 的 OpenAI provider 会自动插入 system message
    "You are a helpful assistant that responds in JSON format."（见 openai.py），
    已天然满足，无需额外处理。若自行改写 system prompt 需注意保留 "json"。

[差异4] OpenAI provider 走原生 JSON 输出，不应再开 code fence。
    实测结论：显式 fence_output=False，避免 resolver 期望 ```json 包裹而解析失败。

[差异5] base_url 末尾不要带 /chat/completions。
    openai SDK 会自动拼接路径；DeepSeek 兼容端点填 https://api.deepseek.com 即可。

[差异6] 中文必须显式传 tokenizer=UnicodeTokenizer()，否则中文实体无法定位到原文。
    本地源码证据：langextract/core/tokenizer.py 中
        _LETTERS_PATTERN = r"[^\W\d_]+"          # 任意"字母"连续段 = 一个 token
        _TOKEN_PATTERN = regex.compile(rf"{_LETTERS_PATTERN}|{_DIGITS_PATTERN}|{_SYMBOLS_PATTERN}")
        _DEFAULT_TOKENIZER = RegexTokenizer()     # extract()/prompt 校验的默认分词器
    汉字属于 \p{L}，所以「其中，云计算板块实现收入 30.0 亿元」会被切成
        ['其中', '，', '云计算板块实现收入', '30', '.', '0', '亿元']
    即"连续汉字整段算一个 token"。后果有两个（本脚本已实测复现）：
      (a) few-shot 示例若写成"云计算板块"这类子串（非整段），prompt 对齐校验会告警
          "Prompt alignment: FAILED to align ... status=None"；
      (b) 文档里靠前的汉字实体（如"李伟明"、"深圳智芯数据科技有限公司"）会拿不到
          char_interval（JSONL 里为 null），下游无法溯源。
    对照实验（本地实测，纯离线）：
        RegexTokenizer   : 示例对齐 3 条 failed；4 个中文实体 char_interval=None
        UnicodeTokenizer : 示例对齐 0 条 failed；4 个中文实体全部 MATCH_EXACT 且 offset 正确
    UnicodeTokenizer 逐字切分 CJK（'云','计','算','板','块'），因此中文子串可精确对齐。
    结论：中文抽取必须显式传 tokenizer=UnicodeTokenizer()。
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SAMPLE_PATH = BASE_DIR / "sample_text.txt"

# 只加载本目录的 .env，避免误读仓库其它位置的环境文件
load_dotenv(BASE_DIR / ".env")

import langextract as lx  # noqa: E402  (需在 load_dotenv 之后导入，以便读取环境变量)
from langextract.core.tokenizer import UnicodeTokenizer  # noqa: E402
from langextract.factory import ModelConfig  # noqa: E402

API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
MODEL_ID = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

PROMPT_DESCRIPTION = """从中文企业年报文本中抽取实体与关系，只抽取文本中明确出现的信息，不要臆造。

可抽取的类别（extraction_class）：
- 公司：公司/机构名称；
- 财务指标：营收、净利润等指标数值；attributes 提供 {指标名称, 数值, 同比增速, 主体}；
- 业务板块：主营业务板块；attributes 提供 {收入, 占营收比例, 同比增速, 主体}；
- 控股关系：主体对标的的持股/收购关系；attributes 提供 {主体, 标的, 关系类型, 持股比例}；
- 人物：人名；attributes 提供 {职务}。

数值与比例一律用原文中的字符串表示（如 "128.6 亿元"、"23.4%"）。
"""

# Few-shot 示例：extraction_text 必须是示例文本中的原文片段，否则 prompt 对齐校验会告警。
EXAMPLE_TEXT = (
    "星辰科技股份有限公司 2023 年实现营业收入 50.0 亿元，同比增长 12.0%。"
    "其中，云计算板块实现收入 30.0 亿元，占营业收入比例为 60.0%。"
    "公司持有星云数据科技有限公司 70% 股权，公司董事长为王一鸣。"
)

EXAMPLE_EXTRACTIONS = [
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


def build_model_config() -> ModelConfig:
    """构造 DeepSeek 的 OpenAI 兼容 provider 配置（见文件头差异 1 / 5）。"""
    return ModelConfig(
        model_id=MODEL_ID,
        provider="openai",  # 差异1：必须显式指定，否则 "deepseek*" 会被 Ollama 正则命中
        provider_kwargs={
            "api_key": API_KEY,
            "base_url": BASE_URL,  # 差异5：不要带 /chat/completions
            "temperature": 0.0,  # 抽取任务要求稳定、可复现
            "max_workers": 1,
        },
    )


def print_extractions(annotated) -> None:
    """按类别打印抽取结果，并展示由 attributes 还原出的实体关系。"""
    extractions = annotated.extractions or []
    print("\n===== 抽取结果（共 %d 条）=====" % len(extractions))
    for i, ext in enumerate(extractions, 1):
        attrs = ext.attributes or {}
        attr_str = "，".join(f"{k}={v}" for k, v in attrs.items()) or "-"
        grounded = "已定位原文" if ext.char_interval else "未定位原文"
        print(f"{i:>2}. [{ext.extraction_class}] {ext.extraction_text}  ({grounded})")
        print(f"      attributes: {attr_str}")

    relations = [e for e in extractions if e.extraction_class == "控股关系"]
    if relations:
        print("\n===== 实体关系示例（控股关系）=====")
        for rel in relations:
            attrs = rel.attributes or {}
            print(
                f"  ({attrs.get('主体', '?')}) -[{attrs.get('关系类型', '?')}"
                f" {attrs.get('持股比例', '?')}]-> ({attrs.get('标的', ext_text(rel))})"
            )


def ext_text(ext) -> str:
    return ext.extraction_text


def main() -> int:
    # Windows 控制台默认 GBK，强制 UTF-8 避免打印中文报错
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    if not API_KEY or API_KEY.startswith("sk-REPLACE"):
        print("[ERROR] 未配置真实 DEEPSEEK_API_KEY，请编辑 langextract_mvp/.env（参考 .env.example）")
        return 1

    if not SAMPLE_PATH.exists():
        print(f"[ERROR] 缺少输入文本: {SAMPLE_PATH}")
        return 1

    text = SAMPLE_PATH.read_text(encoding="utf-8").strip()
    print(f"[INFO] 模型: {MODEL_ID}  Base URL: {BASE_URL}")
    print(f"[INFO] 输入文本: {SAMPLE_PATH.name}（{len(text)} 字符）")

    examples = [lx.data.ExampleData(text=EXAMPLE_TEXT, extractions=EXAMPLE_EXTRACTIONS)]

    annotated = lx.extract(
        text_or_documents=text,
        prompt_description=PROMPT_DESCRIPTION,
        examples=examples,
        config=build_model_config(),
        use_schema_constraints=False,  # 差异2：DeepSeek 不支持 json_schema 严格模式
        fence_output=False,  # 差异4：JSON 模式返回原生 JSON，无需 code fence
        tokenizer=UnicodeTokenizer(),  # 差异6：默认 RegexTokenizer 会把连续汉字整段当一个 token
        max_char_buffer=1000,
        extraction_passes=1,
        show_progress=False,
    )

    print_extractions(annotated)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lx.io.save_annotated_documents(
        annotated_documents=[annotated],
        output_dir=OUTPUT_DIR,
        output_name="extractions.jsonl",
        show_progress=False,
    )
    print(f"\n[OK] 已写入: {OUTPUT_DIR / 'extractions.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
