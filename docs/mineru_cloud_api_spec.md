# MinerU 云服务 API 对接规范 v1.0

> **文档编号**：spec-mineru-api
> **版本**：v1.0
> **状态**：生效（依据 `mineru_mvp/run_mvp.py` 本地实测结果固化）
> **上游依据**：`CODEBUDDY.md`「实测结果反哺规则」——第三方组件对接以本地实际跑通结果为唯一标准
> **落地实现**：`mineru_mvp/run_mvp.py`、`bridge_web_demo/mineru_client.py`
> **官方文档**：<https://mineru.net/apiManage/docs>

---

## 1. 范围

规范 MinerU 云端解析 API 的**调用流程、请求参数、输出目录结构与字段契约**，作为 `bridge_web_demo` 桥接管线的上游输入依据。

---

## 2. 调用流程（4 步，实测顺序）

```
1. POST /api/v4/file-urls/batch          申请 OSS 预签名上传链接 -> batch_id + file_urls[0]
2. PUT  <file_url>                       上传原始 PDF（无需设置 Content-Type）
3. GET  /api/v4/extract-results/batch/{batch_id}   轮询任务状态
4. GET  <full_zip_url>                   下载结果 zip 并解压
```

### 2.1 认证

`Authorization: Bearer <MINERU_TOKEN>`，Token 从环境变量 `MINERU_TOKEN` 读取，**禁止硬编码**。

### 2.2 申请上传链接

| 字段 | 值（实测） | 说明 |
|---|---|---|
| `files` | `[{"name": "<pdf 文件名>", "is_ocr": false}]` | 支持批量，MVP 单文件 |
| `model_version` | `vlm` | 表格效果优于 `pipeline`，默认取环境变量 |
| `enable_formula` | `true` | 保留公式 |
| `enable_table` | `true` | **必须开启**，否则表格无法结构化 |
| `language` | `ch` | 中文优先 |

响应契约：`code == 0` 为成功；`data.batch_id`、`data.file_urls[0]` 为后续所需。

### 2.3 轮询

- 间隔：`5s`；超时：`600s`（实测样例约 1–2 分钟）。
- 状态字段：`state ∈ {pending, running, done, failed}`。
- 进度字段：`extract_progress.extracted_pages / total_pages`。
- `state == done` 时取 `full_zip_url`；`state == failed` 取 `err_msg`。

### 2.4 重试策略

对齐 `specs/m2-extract-kg.md` 验收 5：`tenacity` 指数退避，最多 3 次，初始 1s、倍数 2；重试异常类型 `(httpx.HTTPError, MineruApiError)`。

---

## 3. 输出目录结构（**实测为准**）

> **实测差异 1（重要）**：MinerU 结果**不是**直接放在 `output/` 根目录，而是解压到
> `output/<任务子目录>/`，子目录名默认取 PDF 的 `stem`（如 `output/complex_table/`）。
> 因此任何下游消费者**必须遍历 `output/` 的子目录**，不能只 glob 根目录。

```
mineru_mvp/output/
└── <任务子目录>/
    ├── full.md                              # 最终 Markdown，表格以 HTML 嵌入
    ├── <uuid>_content_list.json             # v1 结构：条目列表
    ├── <uuid>_content_list_v2.json          # v2 结构：页列表 -> 条目列表
    ├── <uuid>_model.json                    # 模型中间态
    ├── <uuid>_origin.pdf                    # 回传的原始 PDF
    ├── layout.json                          # 版面
    ├── api_result.json                      # MVP 额外落盘的接口原始返回
    └── images/                              # 抽出的图片
```

### 3.1 Markdown（`full.md`）

- 标题、段落为 Markdown 文本；
- **表格为内嵌 HTML**（`<table>...</table>`），需清洗为纯文本或按 HTML 解析。

### 3.2 `*_content_list.json`（v1）

顶层为**条目列表** `[item, ...]`：

| 类型 | 内容字段 |
|---|---|
| `title` | `text` |
| `paragraph` | `text` |
| `table` | `table_caption` / `body`（HTML 字符串） |

### 3.3 `*_content_list_v2.json`（v2，**实测差异 2**）

顶层为**页列表嵌套条目列表** `[[item, ...], [item, ...]]`，即结构比 v1 **多一层**。字段路径与 v1 不同：

| 类型 | 内容字段（v2 实测路径） |
|---|---|
| `title` | `content.title_content[].content` |
| `paragraph` | `content.paragraph_content[].content` |
| `table` | `content.html`（HTML 字符串）、`content.table_caption[]`、`content.table_type`、`content.table_nest_level` |

> **实测差异 3**：表格 HTML 在 v1 的 `body`、v2 的 `content.html`。二者必须分支兼容。
> `bbox` 坐标为 `[x0, y0, x1, y1]`，可保留用于后续溯源（Bridge v1.0 暂不落库）。

---

## 4. 下游消费契约

`bridge_web_demo` 桥接管线按下述优先级取输入：

1. **首选**：遍历 `mineru_mvp/output/*/full.md`，按 `mtime` 取**最新**一份；
2. **回退**：若 `full.md` 不存在，则解析同目录最新 `*_content_list_v2.json`，按顺序抽取
   `item["content"]["text"]`（标题/段落）与 `item["content"]["html"]`（表格）拼成纯文本。

---

## 5. 官方文档 vs 本地实测差异汇总（反哺规则）

| # | 项 | 官方文档/直觉 | 本地实测结论 | 规避方式 |
|---|---|---|---|---|
| 1 | 输出路径 | 输出在 `output/` | 实际在 `output/<任务子目录>/` | 遍历子目录并取最新 |
| 2 | v2 结构 | 未明确层级 | `*_content_list_v2.json` 为页列表嵌套，**多一层** | 递归展平 `iter_items()` |
| 3 | 表格字段 | 未明确 | v1 用 `body`，v2 用 `content.html` | 分支兼容取值 |
| 4 | 上传 PUT | 常提示设置 Content-Type | **设置后易失败**，不设置即可 | 仅 PUT 裸字节 |
| 5 | 表格开启 | 选项可省略 | `enable_table=false` 时表格不结构化 | 显式 `enable_table=true` |

---

## 6. 安全与配置

- `MINERU_TOKEN` 仅存本地 `.env`，`.env` 与 `.env.*` 已被根 `.gitignore` 忽略；
- 仓库提供 `.env.example` 模板，禁止提交真实 Token；
- 上传文件大小上限 100MB、MIME 白名单校验（对齐 `CODEBUDDY.md`「存储规范」）。
