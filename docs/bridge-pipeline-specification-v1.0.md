# Bridge Pipeline 规范 v1.0（MinerU → LangExtract）

> **文档编号**：spec-bridge-v1
> **版本**：v1.0
> **状态**：生效
> **落地目录**：`bridge_web_demo/`（独立 MVP，不依赖 `backend/`、`frontend/`、`contracts/`）
> **上游依据**：`docs/mineru_cloud_api_spec.md`、`docs/langextract_spec.md`、`specs/m2-extract-kg.md`
> **实现映射**：`bridge_pipeline.py`（管线）、`mineru_client.py`（MinerU 对接）、`server.py`（极简 FastAPI）、`index.html`（单页可视化）

---

## 1. 目标与边界

### 1.1 In Scope

1. 读取 `mineru_mvp/output/` 下**最新**的 MinerU 解析产物；
2. 提取并清洗纯文本（去 HTML 标签、多余空白、页眉页脚）；
3. 调用 LangExtract + DeepSeek 抽取实体与关系；
4. 归一为**实体关系 JSON** 落盘 `bridge_web_demo/output.json`；
5. 提供单页面 HTML 可视化（上传 PDF、实时流程状态、结果列表、知识图谱视图）。

### 1.2 Out of Scope（沿用 `specs/m2-extract-kg.md` §1.2）

跨文档实体消解、Neo4j 写入、多模态、跨语种、自动本体生成、第三方本体对齐——**均不在本 MVP**。

### 1.3 硬约束

- 独立 MVP 目录，**不修改** `backend/`、`frontend/`、`contracts/`；
- 每个子项目仅使用 `uv` 管理虚拟环境，必须提交 `uv.lock`；
- `.env` 必须被 `.gitignore` 忽略；`output/` 保留 `.gitkeep` 并强制加入版本库；
- 所有外部输入经 Pydantic 校验。

---

## 2. 管线阶段定义（严格顺序）

| 序号 | step | 名称 | 输入 | 输出 | 失败处理 |
|---|---|---|---|---|---|
| 0 | `receive_pdf` | 接收 PDF（可选） | multipart PDF | 落盘 `uploads/<uuid>.pdf` | 《100MB、MIME 白名单》400 |
| 1 | `mineru_parse` | MinerU 云解析（可选，有 PDF 时执行） | PDF | `mineru_mvp/output/<stem>/` | tenacity 重试 3 次后 `failed` |
| 2 | `locate_source` | 定位最新源文件 | `mineru_mvp/output/*/` | `full.md` 路径或 v2 JSON 路径 | 无任何输入 -> `failed` |
| 3 | `clean_text` | 文本清洗 | 原始 Markdown/JSON | 纯文本 | 空文本 -> `failed` |
| 4 | `langextract_extract` | LangExtract 抽取 | 纯文本 | extractions | 重试 3 次后 `failed` |
| 5 | `build_graph` | 归一为实体关系 | extractions | `output.json` | 无 |

> 无 PDF 时（离线演示模式）跳过 step 0、1，直接从 step 2 开始。

---

## 3. 源文件定位规则（对应 MinerU 实测）

```
候选 full.md   = glob(mineru_mvp/output/*/full.md)           # 必须遍历子目录
若不存在       = max(glob(..., "*_content_list_v2.json"), key=mtime)
选中           = 上述候选中 mtime 最新者
```

- 若 `full.md` 存在：`input_mode = "full_md"`；
- 否则回退 v2 JSON：`input_mode = "content_list_v2_fallback"`，按页顺序抽取
  `item["content"]["text"]` 与 `item["content"]["html"]`。

---

## 4. 文本清洗规则

1. `<table>...</table>` 等 HTML 标签按**结构转文本**（`</td>` -> `\t`，`</tr>` -> `\n`），而非直接删除整块；
2. 其余 HTML 标签直接剥离；
3. HTML 实体反转义（`&amp;` -> `&`）；
4. 去除**页眉页脚**模式行：纯页码（`第 3 页`、`- 3 -`、`Page 3`）、页脚分隔线（`---`）；
5. 折叠连续空白：行内多空白 -> 单空格；3 个以上连续换行 -> 2 个；
6. 逐行 `strip` 后丢弃空行；
7. 输出不得为空，否则管线 `failed`。

---

## 5. 实体关系归一模型

### 5.1 实体 `entities[]`

```json
{
  "id": "e1",
  "type": "公司",
  "name": "华辰智能科技股份有限公司",
  "attributes": {},
  "char_interval": {"start_pos": 0, "end_pos": 12},
  "alignment_status": "match_exact",
  "grounded": true,
  "evidence": "华辰智能科技股份有限公司"
}
```

- `grounded = char_interval != null`，**溯源失败必须显式标记**（GraphRAG 溯源硬伤）。

### 5.2 关系 `relations[]`

```json
{
  "id": "r1",
  "head": "华辰智能科技股份有限公司",
  "head_type": "公司",
  "relation": "收购",
  "tail": "深圳智芯数据科技有限公司",
  "tail_type": "公司",
  "attributes": {"持股比例": "65%"},
  "derived": false,
  "char_interval": {"start_pos": 327, "end_pos": 339},
  "alignment_status": "match_fuzzy",
  "evidence": "深圳智芯数据科技有限公司"
}
```

### 5.3 归一映射表

| LangExtract 类别 | 归一处理 |
|---|---|
| `控股关系` | -> **关系**：`head = attributes.主体`，`relation = attributes.关系类型`，`tail = attributes.标的`，其余 attributes 保留 |
| `财务指标` | -> **实体** + **派生关系**：`head = attributes.主体`，`relation = "具有财务指标"`，`tail = attributes.指标名称`，`derived = true` |
| `业务板块` | -> **实体** + **派生关系**：`head = attributes.主体`，`relation = "经营业务板块"`，`tail = extraction_text`，`derived = true` |
| `公司` / `人物` | -> **实体** |
| 其它类别 | -> **实体**，`type` 原样保留 |

- 关系端点若在实体集合中不存在，则**自动补建**实体节点（`type` 取端点类型，`grounded = false`）。

### 5.4 `output.json` 顶层结构

```json
{
  "schema_version": "1.0",
  "trace_id": "uuid",
  "generated_at": "2026-09-17T12:00:00+00:00",
  "source": {
    "input_mode": "full_md",
    "mineru_task_dir": "mineru_mvp/output/complex_table",
    "source_path": ".../full.md",
    "text_chars": 1234
  },
  "model": {
    "provider": "openai",
    "model_id": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
    "use_schema_constraints": false,
    "fence_output": false,
    "tokenizer": "UnicodeTokenizer"
  },
  "steps": [
    {"name": "locate_source", "label": "定位最新 MinerU 产物", "status": "completed", "duration_ms": 1, "detail": "..."}
  ],
  "entities": [],
  "relations": [],
  "stats": {
    "entity_count": 0,
    "relation_count": 0,
    "derived_relation_count": 0,
    "ungrounded_count": 0,
    "entity_types": {}
  }
}
```

---

## 6. 状态机（异步任务）

对齐 `CODEBUDDY.md`「异步任务规范」：

```
pending -> processing -> completed
                      \-> failed
```

- 每次任务生成 `job_id`（UUID）与 `trace_id`（UUID），`trace_id` 贯穿日志；
- 长耗时任务在**后台线程**执行，接口立即返回 `job_id`；
- 前端通过 `GET /api/jobs/{job_id}` 轮询（间隔 1s）获取**步骤级**实时状态；
- 失败必须支持重试（tenacity 指数退避）。

---

## 7. HTTP 接口契约（本 MVP 内部接口，不进入对外契约）

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `GET` | `/` | - | 单页 HTML |
| `POST` | `/api/jobs` | `multipart/form-data`：`file`(可选 PDF)、`skip_mineru`(bool，默认 false) | `202 {job_id, trace_id, status}` |
| `GET` | `/api/jobs/{job_id}` | - | `200 {job_id, trace_id, status, current_step, steps[], error}`；未知 job -> `404` |
| `GET` | `/api/jobs/{job_id}/result` | - | `200 output.json`；未完成 -> `409 NOT_READY` |
| `GET` | `/api/result/latest` | - | `200 output.json`（最近一次落盘）；不存在 -> `404` |
| `GET` | `/api/health` | - | `200 {status, mineru_output_dir, has_api_key}` |

统一错误响应（对齐 `CODEBUDDY.md`「错误响应规范」）：

```json
{"code": "PIPELINE_FAILED", "message": "...", "detail": "...", "trace_id": "..."}
```

---

## 8. 可视化页面要求（`index.html`）

单文件、零构建、无外部 CDN 依赖：

1. **上传区**：拖拽/点击选择 PDF，可勾选「跳过 MinerU，使用已有输出」进行离线演示；
2. **流程状态区**：按 §2 步骤渲染时间线，实时更新 `pending / processing / completed / failed` 与耗时；
3. **结果列表区**：实体表 + 关系表，支持按类型过滤，展示 `grounded` 徽标；
4. **知识图谱区**：Canvas 力导向布局，节点按实体类型着色、关系边带标签，支持拖拽节点与滚轮缩放；
5. **元信息区**：展示本次读取的 `full.md` 路径、`input_mode`、`trace_id`、模型配置。

---

## 9. 验收标准（WHEN/THEN）

1. **WHEN** 运行 `uv run python bridge_pipeline.py`，**THEN** 自动定位 `mineru_mvp/output/` 下最新 `full.md`，**AND** 打印读取路径，**AND** 落盘 `bridge_web_demo/output.json`；
2. **WHEN** `full.md` 不存在，**THEN** 回退解析最新 `*_content_list_v2.json`，**AND** `input_mode = "content_list_v2_fallback"`；
3. **WHEN** 抽取完成，**THEN** `entities` 全部含 `grounded` 字段，**AND** 中文实体的 `char_interval` 不为 `null`（`UnicodeTokenizer` 生效）；
4. **WHEN** 上传 PDF 并触发任务，**THEN** 前端 1s 内看到步骤状态推进，**AND** 完成后自动渲染列表与图谱；
5. **WHEN** 任一步骤异常，**THEN** 任务置 `failed` 并返回统一错误结构（含 `trace_id`）。
