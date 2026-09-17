# LangExtract + DeepSeek 对接规范 v1.0

> **文档编号**：spec-langextract
> **版本**：v1.0
> **状态**：生效（依据阶段五实测固化）
> **实测版本**：`langextract==1.7.0`、`openai==3.14.1`、`pydantic==2.13.5`
> **落地实现**：`langextract_mvp/run_mvp.py`、`bridge_web_demo/bridge_pipeline.py`
> **上游依据**：`CODEBUDDY.md`「实测结果反哺规则」

---

## 1. 范围

规范 LangExtract 调用 DeepSeek（OpenAI 兼容端点）做中文实体关系抽取的**必传参数**与**失败模式**，任何调用方不得省略。

---

## 2. 六条铁律（必须全部满足）

| # | 参数 | 必须值 | 不满足的后果 |
|---|---|---|---|
| 1 | `provider` | `"openai"` | `deepseek*` 会被内置 **Ollama Provider** 正则抢走，要求本地 Ollama 服务，直接报连接失败 |
| 2 | `use_schema_constraints` | `False` | DeepSeek 不支持 OpenAI `json_schema` 严格模式（`strict: true`），请求被拒 |
| 3 | `fence_output` | `False` | 走原生 JSON 输出；置 `True` 会让 resolver 期望 ```json 包裹而解析失败 |
| 4 | `tokenizer` | `UnicodeTokenizer()` | 默认 `RegexTokenizer` 把**连续汉字整段当 1 个 token**，中文实体拿不到 `char_interval`（GraphRAG 溯源硬伤） |
| 5 | `base_url` | `https://api.deepseek.com` | **不带 `/chat/completions`**，OpenAI SDK 会自动拼路径 |
| 6 | `model_id` | `deepseek-chat`（`DEEPSEEK_MODEL`） | 模型名以 `deepseek` 开头，必须配合第 1 条显式 provider |

### 2.1 参数 1 的源码证据

`langextract/providers/patterns.py`：

- `OLLAMA_PATTERNS` 含 `^deepseek`；
- `OPENAI_PATTERNS` 仅匹配 `^gpt-*` / `^o[1-9]`。

因此自动路由会把 `deepseek-chat` 判给 `OllamaLanguageModel`。

### 2.2 参数 2 的源码证据

- `langextract/providers/schemas/openai.py` 的 `OpenAISchema.response_format` 会生成
  `{"type": "json_schema", ..., "strict": true}`；
- `lx.extract()` 默认 `use_schema_constraints=True`；
- 置 `False` 后 provider 回退到 `response_format={"type": "json_object"}`。

### 2.3 参数 3 的补充

LangExtract 的 OpenAI provider 会自动插入 system message
`You are a helpful assistant that responds in JSON format.`
DeepSeek 的 JSON 模式要求提示词出现 “json” 字样，已天然满足；**若自行改写 system prompt 必须保留 “json”**。

### 2.4 参数 4 的源码证据与对照实验

`langextract/core/tokenizer.py`：

```python
_LETTERS_PATTERN = r"[^\W\d_]+"      # 任意“字母”连续段 = 一个 token
_DEFAULT_TOKENIZER = RegexTokenizer()
```

汉字属 `\p{L}`，故「其中，云计算板块实现收入 30.0 亿元」被切成
`['其中', '，', '云计算板块实现收入', '30', '.', '0', '亿元']`——连续汉字整段算一个 token。

对照实验（本地实测，纯离线）：

| 分词器 | few-shot 示例对齐 | 中文实体 `char_interval` |
|---|---|---|
| `RegexTokenizer`（默认） | 3 条 `FAILED` | 4 个实体全部为 `null` |
| `UnicodeTokenizer` | 0 条 `FAILED` | 4 个实体全部 `match_exact` 且 offset 正确 |

结论：**中文抽取必须显式传 `tokenizer=UnicodeTokenizer()`**。

---

## 3. 调用模板（可直接复用）

```python
import langextract as lx
from langextract.core.tokenizer import UnicodeTokenizer
from langextract.factory import ModelConfig

config = ModelConfig(
    model_id="deepseek-chat",
    provider="openai",                       # 铁律 1
    provider_kwargs={
        "api_key": os.environ["DEEPSEEK_API_KEY"],
        "base_url": "https://api.deepseek.com",  # 铁律 5
        "temperature": 0.0,                  # 抽取要求稳定可复现
        "max_workers": 1,
    },
)

annotated = lx.extract(
    text_or_documents=text,
    prompt_description=PROMPT_DESCRIPTION,
    examples=examples,
    config=config,
    use_schema_constraints=False,            # 铁律 2
    fence_output=False,                      # 铁律 3
    tokenizer=UnicodeTokenizer(),            # 铁律 4
    max_char_buffer=1000,
    extraction_passes=1,
    show_progress=False,
)
```

---

## 4. Few-shot 示例约束

- `ExampleData.text` 与 `Extraction.extraction_text` 必须**逐字对应原文片段**，否则
  prompt 对齐校验会告警 `Prompt alignment: FAILED to align ... status=None`；
- 示例中的子串必须是原文本的**连续子串**（`UnicodeTokenizer` 下中文可精确对齐）；
- 抽取类别（`extraction_class`）与 `attributes` 键名需与业务本体对齐，Bridge v1.0 采用：
  `公司 / 财务指标 / 业务板块 / 控股关系 / 人物`。

---

## 5. 输出与落盘

- 内存对象：`AnnotatedDocument.extractions`，每条含
  `extraction_class / extraction_text / attributes / char_interval / alignment_status`；
- 标准落盘：`lx.io.save_annotated_documents(..., output_name="extractions.jsonl")`（JSONL）；
- **`char_interval` 为 `null` 即视为溯源失败**，桥接管线必须显式统计并在结果中暴露。

---

## 6. 官方文档 vs 本地实测差异汇总（反哺规则）

| # | 项 | 官方文档/直觉 | 本地实测结论 |
|---|---|---|---|
| 1 | 非 GPT 模型路由 | 仅说“需显式指定 provider” | 未点明 `^deepseek` 被 Ollama 正则命中，必须 `provider="openai"` |
| 2 | 结构化输出 | 默认启用 schema 约束 | DeepSeek 不支持 `json_schema` 严格模式，须关 |
| 3 | 输出包裹 | JSON 模式可能带 code fence | 原生 JSON，须 `fence_output=False` |
| 4 | 中文分词 | 默认分词器即可 | 默认会把连续汉字整段当 1 token，中文必须 `UnicodeTokenizer()` |
| 5 | base_url | 常被写成含路径的完整端点 | 只填到域名，SDK 自动拼 `/chat/completions` |

---

## 7. 安全

- `DEEPSEEK_API_KEY` 仅存本地 `.env`，禁止硬编码、禁止入日志；
- 仓库提供 `.env.example`，`.env` 已被根 `.gitignore` 忽略。
