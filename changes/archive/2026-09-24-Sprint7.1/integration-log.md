# Sprint 7.1 批次 A 实测记录（M4 数据与规则型疑点算法）

> 每个结论都要能复跑，记录"怎么测的"。本文件随批次收尾移入 `changes/archive/<日期>-Sprint7.1/`。
> 门禁口径：接缝门禁 = **默认档 + ERROR = 0**（`--strict` 仅 v1.4.0 完成点）。
> **花钱纪律**：本文件每花一笔钱都要写清「命令 + token 数 + 估算金额」，禁止事后补记大概数。

---

## 1. T0 环境基线（2026-09-23）

| 项 | 实测 |
|---|---|
| 分支 / 基线 | `main` @ `773d666d`（Sprint 7.0 已推送，CI #21 绿），`git status` clean |
| 基线门禁 | 沿用 7.0 收尾：pytest 315 passed / ruff 全绿 / `check_seams` ERROR 0 / `export_openapi --check` 无 diff |
| 配置 | `app_version=1.2.0`、`extraction_engine=llm`、`extraction_prompt_version=kg_extraction_v1`、`extraction_max_chars_per_chunk=4000`（默认）、实体 / 关系上限 500 / 1000 |
| 凭据（只打长度） | `llm_api_key len=35`、`mineru_token len=51`、`neo4j_password len=8` |
| Neo4j | 开工前 `Exited (137)` → `docker start neo4j` 后 `Up`；库内 `:Entity=41` / `:Chunk=1` / `:Document=1` / `:KgVersion=2` |
| PG 真源（SQLite 开发态替身） | `documents=1`（仅 `complex_table.pdf`，4KB）、`kg_versions=1`（`v-3e381d36`，`ready`，entity=6 / relation=1） |
| 预算 | 用户给定 **¥67.96** |

**「库内仍是旧正则产物」的量化**：全库只有 1 份 4KB 的测试 PDF，图谱 41 个 `:Entity` 中 23 个来自
`bridge_web_demo/output.json` 的历史导入（type 为「财务指标 / 业务板块 / 公司」），6 个来自
`complex_table.pdf` 的 **mock 正则抽取**。即：**M2 演示图谱里没有任何一份真实公司材料**。

盘点脚本（零成本、可复跑）：

```
cd backend
uv run --with pypdf python ../changes/Sprint7.1/inspect_state.py
```

---

## 2. 事前核实（D6 已定论，本节只做落地确认）

| 项 | 结论 | 依据 |
|---|---|---|
| 能否抽出法人 / 地址 | **能**（v1 枚举无 `LEGAL_PERSON` / `ADDRESS` 标签，只能落 `PERSON` / `VENUE`） | `Sprint7.0/integration-log.md` §4.4 / §7 |
| 文档间是否存在真实交叉 | **有，限「共享法人」一类**：三家（蛇口 / 公路 / 轮船）同以招商局集团为控股股东，法定代表人同为 **缪建民**；集团成立日期 1986-10-14 在蛇口与轮船两处一致 → **同名消歧有据** | 同上 §7.2 / §7.3 |
| 共享地址 | **不成立**：公路 / 轮船全文 0 处「建国路」（集团住所仅蛇口募集说明书披露） | 同上 §7.2 |
| 伪交叉陷阱 | 「东方广场」= 会计师事务所地址（三份年报共有）；本轮不用年报做地址疑点 | 同上 §4.4 |
| 演示语料 | 蛇口 2024 公司债募集说明书（314p）/ 公路 2024 科创债募集说明书（290p）/ 轮船 2025 年报（246p） | 用户已人工取得，落 `docs/annualreport/` |

规模与成本模型（零成本统计，`inspect_state.py` §5）：三份合计 **280091 + 245475 + 255976 ≈ 781K 字**；
成本基准取 Sprint 7.0 §7.2 真机值（8368 字 / 8 chunk = ¥0.2815 → 每千字 ¥0.0336）。

---

## 3. 第一步：重抽演示数据（真机）

### 3.1 驱动方式（沿用 Sprint 6.1 §4 第 3 条口径）

- 上传走**真实 HTTP API**：`POST /api/v1/documents/upload`（带 `X-Org-Id` / `X-Actor-Id` 开发态兜底头），
  由在线服务（uvicorn 8123）跑 `document.parse` → MinerU 云解析；
- 在线链路**不自串联**（既有缺口）：`document.extract` / `kg.build` 由
  `changes/Sprint7.1/redemo_pipeline.py` 直接调 `app.tasks.registry` 里登记的执行体；
- `trace_id` 复用 `documents.trace_id`（H4：解析 / 抽取 / 建图同号）；
- 三家公司写入**同一个 `kg_version`**（跨公司两跳算法的前提）：执行体默认「一文档一版本」，
  故显式传 `kg_version_id`（`kg_version_strategy` 文档口径是 `per_org`）。

### 3.2 真机发现 A：MinerU 云解析 **200 页上限**

三份素材整份上传全部 `failed`（`document.parse`，三次尝试后落 `failed`）：

```
error_detail=app.services.parsing.mineru.MineruApiError: 解析失败:
number of pages exceeds limit (200 pages), please split the file and try again
```

处置：**按真实页码拆分**（`changes/Sprint7.1/split_pdf.py`，pypdf，不改动页面内容），
每片 ≤190 页留安全边界，产物落 `backend/storage/demo-slice/parts/`（已被 .gitignore 忽略）：

| 源材料 | 页数 | 分片 |
|---|---|---|
| 招商蛇口 2024 公司债募集说明书 | 314 | `招商蛇口_p1-190.pdf` / `招商蛇口_p191-314.pdf` |
| 招商公路 2024 科创债募集说明书 | 290 | `招商公路_p1-190.pdf` / `招商公路_p191-290.pdf` |
| 招商轮船 2025 年年度报告 | 246 | `招商轮船_p1-190.pdf` / `招商轮船_p191-246.pdf` |

6 片重传后 `document.parse` **全部 completed**，`full.md` 规模：

| 分片 | full.md |
|---|---|
| 公路 p1-190 | 445.7 KB |
| 公路 p191-290 | 151 KB |
| 轮船 p1-190 | 522.6 KB |
| 轮船 p191-246 | 165.8 KB |
| 蛇口 p1-190 | 489.3 KB |
| 蛇口 p191-314 | 206.3 KB |
| **合计** | **≈ 1.98 MB（≈ 660K 字）** |

### 3.3 真机发现 B：默认 4000 字/chunk 撞模型输出上限，整份文档失败并 3× 重试

第一份分片（蛇口 p1-190）按默认 `EXTRACTION_MAX_CHARS_PER_CHUNK=4000` 跑真实抽取：

```
extract_status=failed elapsed=502.3s
error=app.services.extraction.langextract.LangextractError:
      LLM 输出非法 JSON: Expecting ',' delimiter: line 1046 column 6 (char 23657)
llm_calls=46 prompt_tokens=250598 completion_tokens=195477 llm_time=499.1s
estimated_cost=¥2.0650   ← 三次尝试合计，全部作废
```

要点：

- 单次调用平均 completion ≈ 4250 tokens，个别 chunk 的输出撞上模型输出上限被**截断** → JSON 解析失败；
- `_RETRYABLE_EXCEPTIONS` 含 `LangextractError`，一次 chunk 失败 ⇒ **整份文档** tenacity 重跑（≤3 次），
  成本直接 ×3，且三试皆败即整份作废；
- 这与 Sprint 7.0 的切片验证不冲突：7.0 用的是 **1200 字/chunk**（`verify_slice.py` 显式注入），
  28 个 chunk 无一失败。**仓库默认 4000 未在真机全量场景验证过**。

处置：本轮重抽显式声明 **1200 字/chunk**（`--chunk-chars 1200`，7.0 真机验证档位），
并在脚本里把 `engine` / `prompt_version` / `chunk_chars` 写进环境变量后再导入 `app.*`
（防「改 .env 切 v2」与批量重抽并行时**同库混档**）。

### 3.4 真机发现 C：1200 字/chunk **同样会失败**，且失败是「整份文档 ×3 重跑」

把 chunk 降到 Sprint 7.0 验证过的 1200 字后重跑公路 p1-190（≈148K 字 ≈ 124 chunk）：

```
extract_status=failed elapsed=1758.8s
error=app.services.extraction.langextract.LangextractError:
      LLM 输出非法 JSON: Expecting ',' delimiter: line 951 column 6 (char 23839)
llm_calls=205 prompt_tokens=542594 completion_tokens=683114 llm_time=1755.4s
estimated_cost=¥6.5501   ← 三次尝试合计，全部作废（无 entities.json 产物）
extract_retry_count=2（第 3 次尝试后 failed）
```

两次失败的错误位置高度一致（4000 字档 `char 23657` / 1200 字档 `char 23839`）——
指向**输出长度上限（≈8K tokens）导致的截断**，而不是随机抖动。

**真正的坑不是单价，是容错缺失**：

- `_RETRYABLE_EXCEPTIONS` 含 `LangextractError` ⇒ 单个 chunk 解析失败会让
  **整份文档**重跑（≤3 次），每次重跑把前面已成功的 chunk 全部重算一遍；
- 全量三家公司 ≈ 660K 字 ≈ **550 个 chunk**（1200 字档），只要有一个 chunk 抽风，
  这一份就作废且成本 ×3 —— 这是**结构性**问题，不是运气问题。

### 3.5 真实扣费对账（估算偏高约 2 倍）

```
GET https://api.deepseek.com/user/balance → 200
{"is_available":true,"balance_infos":[{"currency":"CNY",
 "total_balance":"63.69","granted_balance":"0.00","topped_up_balance":"63.69"}]}
```

| 口径 | 金额 |
|---|---|
| 用户开工前给定余额 | ¥67.96 |
| 当前余额（真机读取） | **¥63.69** |
| 实际扣费（两次失败 run：46 + 205 次调用） | **¥4.27** |
| 脚本按官方刊例价估算（¥2 / ¥8 每百万） | ¥8.62 |

差额来自 DeepSeek 的**上下文缓存命中**（同一 prefix 的 prompt tokens 打折），
因此脚本里的 `estimated_cost` 只当上界用，**真实账以余额为准**（今后每轮都读一次余额）。

> 换算：一次 124-chunk 的完整成功抽取，真实成本约 **¥2**（不是 ¥6.5）——
> 失败重跑才是真正烧钱的地方。

### 3.6 第一步未完成（等待拍板）

- 已完成：6 片 <200 页重传 + MinerU 解析（全部 completed）、`kg_version=v-s71a-fe1c4dc3`（pending，尚未建图）；
- 未完成：`document.extract`（0/6 成功）、`kg.build`、ADR-0002 重建 active 版本；
- 卡点：**见 §3.4** —— 需要先决定「容错改造 / 语料口径」，否则继续跑就是把钱烧在结构性缺陷上。

---

## 4. 抽取侧改造（用户 2026-09-23 拍板后实施，代码已落）

拍板结论：**① 改 `langextract.py` 加单 chunk 容错**（语料保持全量 6 片）；
**② 先落 §2.1 的 `kg_extraction_v2`，再只抽一次**（不先用 v1 抽一遍）。

### 4.1 单 chunk 容错（`app/services/extraction/langextract.py`）

| 改动 | 内容 |
|---|---|
| `_CHUNK_MAX_ATTEMPTS = 2` | 坏 chunk 就地**重试 1 次**（不是无限重试：真机失败形态是输出被截断，多试只是烧钱） |
| `_extract_chunk_tolerant()` | 只兜 `LangextractError`；注入抽取器抛的其它异常（= bug）**一律冒泡**，吞掉会让缺陷隐形 |
| `FailedChunk` + `ExtractionResult.failed_chunks` | 跳过的 chunk 记账（index / char_offset / reason），并提供 `langextract_chunk_retry` / `langextract_chunk_failed` 两条 WARNING 日志——**跳过必须留痕，不是静默降级** |
| 全败仍报错 | 所有 chunk 都失败 ⇒ 抛 `LangextractError`（首个原因原样带出）交外层 tenacity——**不许把「没抽到」伪装成「这份文档没有实体」**（LC1-9） |
| `langextract_done` 增绑 `failed_chunk_count` | 真机可直接读「这一份丢了多少证据」 |

### 4.2 `kg_extraction_v2`（Prompt 只增不改）

- 新增 `prompts/kg_extraction_v2.md`：枚举参数化为 `{{entity_types}}` / `{{relation_types}}`，
  新增示例 3（法定代表人 / 注册地址）；字段硬约束 / 拒答兜底 / 裁剪沿用 v1；
  **`kg_extraction_v1.md` 一字未改**（单测 `test_v1_template_is_untouched` 守着）；
- `langextract.py` 新增 `_render_extraction_prompt()`：**按模板实际声明的占位符**给值
  （v1 只声明 `text` / `language`，不会收到 v2 的变量 → 加版本不必改代码）；
- 类型枚举扩：`LEGAL_PERSON` / `ADDRESS`；关系枚举扩：`LEGAL_REP` / `REGISTERED_AT`
  （未知类型降级 `RELATED` 的兜底**保留**）；
- 三处文档同步：`dev-doc-status.md` §5（新增一段 v2 台账）、矩阵 H9 行、`.env.example`；
  `config.py` 默认与本地 `.env` 一并切 v2。

### 4.3 `char_offset` 口径（7.0 遗留，用户已拍板采纳）

模型自报区间**与 `mention` 不符**时丢弃模型偏移、改按 `mention` 回查，并打
`langextract_char_span_mismatch` WARNING；一致时原样保留。理由：7.0 真机 top20 里
14/20 的模型偏移并不指向它自己的 `mention`，照单全收会让 §2.3 的证据回查漂位。

### 4.4 门禁证据（后端，全部真机跑出）

```
uv run pytest -q                       → 326 passed, 1 warning
uv run ruff check .                    → All checks passed!
uv run ruff format --check .           → 97 files already formatted
uv run python scripts/check_seams.py   → ERROR 0 / WARN 6 / OK 7
uv run python scripts/export_openapi.py --check → 与模块一致（无 diff）
```

新增 / 修改的用例：`tests/test_extraction_sprint71.py`（11 例：v2 占位符与渲染、v1 未被改、
新类型不降级、原类型不回归、坏 chunk 重试→跳过→记账、全败仍抛错、注入 bug 不吞、
偏移不符以 mention 为准、偏移相符则保留）；`test_extraction_llm_engine.py`
（原「未知类型」样例用的 `LEGAL_PERSON` 在 v2 下已合法 → 换成 `SHAREHOLDER_ORG`）；
`test_prompt_loader.py`（`load_prompt("kg_extraction")` 不指定版本取最大版本 = 2）。

### 4.5 v2 真机跑数（进行中）

命令（显式声明档位，防「改 .env 切版本」与批量重抽并行导致**同库混档**）：

```
uv run python ../changes/Sprint7.1/redemo_pipeline.py extract \
  --doc <document_id> --chunk-chars 1200 --prompt-version kg_extraction_v2
```

### 4.6 真机发现 D：500 实体上限会把 M4 的法人 / 地址挤掉（已校准）

v2 第一份分片（蛇口 p1-190）跑通后零成本核对产物：

```
uv run python ../changes/Sprint7.1/redemo_pipeline.py probe --doc a711dc7f --top 12
--- entities=500（**顶到单文档上限**）---
  probe 缪建民           hits=0     ← 也被 is 裁掉
  probe 招商局集团有限公司 hits=8
  probe 建国路           hits=0
  top12 全是 ORG（证券公司 / 主承销商），confidence 0.99
```

即：**M4 要的 LEGAL_PERSON / ADDRESS 恰好是"低密度高价值"实体**，按 confidence
降序裁剪时会被几百个券商名 / 承销商名挤掉。校准决定（写下来接受质询，因为它确实动了配置）：

| 项 | 旧 | 新 | 理由 |
|---|---|---|---|
| `extraction_max_entities_per_doc` | 500 | **2000** | 190 页级文档的全部候选远超 500，500 会把`缪建民` / 注册地址裁掉 |
| `extraction_max_relations_per_doc` | 1000 | **4000** | 同上：`LEGAL_REP` / `REGISTERED_AT` 不能被挤掉 |

- 这是**容量护栏**，不是疑点阈值：放宽它不会制造任何疑点，只会少丢真实实体；
- 为让这件事可审计，`langextract_done` 日志新增 `entity_count_before_clamp` /
  `relation_count_before_clamp`——**没有这两个字段，事后看不出"到底丢了多少"**；
- 提高上限意味着要**重新抽一遍**（裁剪发生在写产物之前，省下的实体已经没了）。

---

## 5. §2.2 图写入：M4 三类节点 + 两条边（`backend/app/services/kg/builder.py`）

`specs/m4-affiliation-detection.md` §4.1 / §4.2 的增量建模，作为**可跳过段**接进
既有的五段式（`request` 里没有 `LEGAL_PERSON` / `ADDRESS` 就一段都不跑，
老调用方与老单测观察到的行为不变）：

| 段 | Cypher | 产物 |
|---|---|---|
| stage-2.6 | `_CYPHER_STAGE2C_LOAD_SUBJECTS` / `_2D_ADDRESSES` / `_2E_LEGAL_PERSONS` | `:Subject` / `:Address` / `:LegalPerson` |
| stage-3.2 | `_CYPHER_STAGE3B_LEGAL_REP` / `_3C_REGISTERED_AT` | `(:Subject)-[:LEGAL_REP]->(:LegalPerson)` / `(:Subject)-[:REGISTERED_AT]->(:Address)` |

四个关键决策（都可被单测回放）：

1. **节点 id = `sha256(规范化名称)[:16]`**（前缀 `sub` / `adr` / `lpr`）。抽取侧的
   实体 id 是 `ent_<uuid>`，**每次抽取都不同**，跨文档必然连不上；而 M4 的共享法人
   是两跳查询（`s1 -[:LEGAL_REP]-> p <-[:LEGAL_REP]- s2`），它能否成立完全取决于
   「不同文档里同名的法人必须合成同一个节点」→ 只能按名称算稳定 id。
2. **不与 `:Entity` 桥接**：不额外补节点、不往 `:Entity` 打补丁（tasks §2.2 决策）。
   两套坐标混用会让"同一家公司到底在图里是几个点"失去确定性。
3. **缺失即 null，严禁兜底生成**：`tax_id` / `region_code` / `id_type` / `id_hash`
   在分销材料里拿不到就写 `null`——拿名字凑哈希会让同名不同人误合并，比缺失危险。
4. **`acl_scope` 继承**（`:Subject` / `:Address` / `:LegalPerson` 都带）：沿用 `:Chunk`
   口径从 `documents.acl_scope` 继承，为 S11 的 RLS 穿透留属性。

连带修的手段：`_CYPHER_STAGE1B_INDEXES` 补三条社区版可用的复合唯一约束；既有单测里
按**写死下标**断言 stage 顺序的两处改为按 Cypher 内容定位（约束条数会随建模增长）。

**单测 336 passed**（新增 `tests/test_kg_builder_affiliation.py` 11 例：行构造 / 同名跨文档
合并 / 类型不符与悬空端点丢弃 / 无关关系不出行 / 段落顺序 / `kg_version` 与 `acl_scope`
继承 / 无数据不跑 M4 段 / 不与 Entity 桥接 / 批切片 / 驱动异常包装 `GraphUnavailableError`）；
`ruff check` / `check_seams` / `export_openapi --check` 全绿。

**真机核验**（建图后补）：Neo4j 三类节点计数与 `valueType()` 类型抽样 → §7。

---

## 6. §2.3 规则算法 + §2.4 `risk.detect` 挂管线

### 6.1 算法（`app/services/kg/affiliation.py` + `graphs.py` 的两跳 Cypher）

| 项 | 落点 |
|---|---|
| 共享法人 | `_QUERY_SHARED_LEGAL_REP`（**照抄** spec §5.4 第 159 行） |
| 共享地址 | `_QUERY_SHARED_ADDRESS`（照抄第 154 行） |
| 疑点结构 | `Suspicion{type, severity, entities[], entity_names, evidence[]}`（对齐 M4 §3 验收 3） |
| 证据 | `_QUERY_AFFILIATION_EVIDENCE`：主体层节点 → `source_entity_ids` → `:Entity` → `(:Chunk)-[:MENTIONS]->` 原文片段 |

对 spec 原文的两处**偏离**（都写在查询注释里，不是自由发挥）：

1. `s1 <> s2` → **`s1.id < s2.id`**：否则 (A,B) 与 (B,A) 会产出两条一模一样的疑点；
2. 追加 `org_id` 租户过滤：spec 只按 `kg_version` 过滤，但**版本不等于租户边界**（ADR-0003）。

两条硬纪律：

- **无证据不产疑点**：取不到 `:Chunk` 证据的命中直接丢，并打
  `affiliation_suspicion_dropped_no_evidence` WARNING + 计数——引用覆盖率 100% 是硬要求，
  且"丢了"这件事必须看得见（否则就是静默降级）；
- **严重度固定 `medium`**，本批次**不引入任何可调阈值**（阈值调参 = 给"凑够 3 条"留后门，
  tasks §2.3 D6 前置卡口明令禁止）。

证据链的关键设计：**新增 `source_entity_ids` 溯源属性**（spec §4.1 属性表之外）。
`:Chunk` 只 `MENTIONS` 到 `:Entity`，而不允许 `:Entity` ↔ `:Subject` 桥接（§2.2 决策），
所以疑点想回原文只能靠这层 id 溯源；**不**退化为"按名字模糊匹配 Entity"（那是在两层之间
偷偷搭文本桥）。多文档抽到同一法人时溯源**累加去重**（Cypher `reduce`，社区版无 apoc）。

### 6.2 `risk.detect` 执行体（`app/tasks/registry.py`）

- 作用域是 **`kg_version`** 不是单文档（共享类疑点只有跨公司才成立）；
- 只在 `kg_versions.status == 'ready'` 上跑；无版本 / 非 ready → 显式跳过 + 记账
  （`risk_detect_skipped_no_kg_version` / `_version_not_ready`），**不**当成"无嫌疑"；
- 产物 = 逐条日志（`affiliation_suspicion_detected`）+ `{org}/{doc}/kg/suspicions.json`；
  **本批次不落 PG**（`affiliation_suspicions` 表属 Sprint 8 批次 B）；
- 失败 → 整体 `status = failed`。**特意不借用 `kg_build_status`**：把"疑点检出失败"
  标成"建图失败"比不标更糟。

### 6.3 真机发现 E：**管线没有跨阶段投递**

`tasks.md` §2.4 要求"先读 `document_parse_executor` 实际的下一阶段投递写法再照做"。
读了，结论是**没有这个写法**：

- `documents.py` 上传时只提交 `first_pipeline_stage()`（管线**首个**已启用阶段）；
- `TaskManager.submit()` 依赖请求级 `BackgroundTasks`（`add_task`），请求结束即失效，
  **无法**在阶段之间续投；
- 于是现状是：parse → extract → kg.build 全靠**脚本 / 人工按序驱动**
  （本批次的 6 片数据就是 `redemo_pipeline.py` 逐阶段跑的）。

⇒ `risk.detect` 登记进 `EXECUTOR_REGISTRY` 后，`resolve_pipeline_stages()` 已包含它，
**但上传链路不会自动跑到第四段**。本批次不臆造一套调度机制（那超出批次范围），
改为：登记 + 脚本驱动 + **登记缺口**（承接 Sprint 8）。
真机端到端因此按"同一 `trace_id` 逐阶段驱动"的方式取证，见 §7。

### 6.4 门禁（后端）

```
uv run pytest -q                       → 350 passed
uv run ruff check . / format --check   → All checks passed / 101 files already formatted
uv run python scripts/check_seams.py   → ERROR 0 / WARN 6 / OK 7
uv run python scripts/export_openapi.py --check → 与模块一致（无 diff）
```

新增用例：`tests/test_affiliation_detect.py`（10 例：两类疑点产出 / 无证据即丢 /
证据归属与原文定位 / 非法 `doc_id` 归 `None` / 证据条数上限 / Neo4j 挂了必抛 /
`to_dict` 结构 / `source_entity_ids` 溯源累加）；
`tests/test_risk_detect_executor.py`（5 例：无版本跳过 / 非 ready 跳过 / 成功写产物 /
Neo4j 挂了整体 failed / 登记后可解析）。既有 `test_seams_a2.py` 的
「`resolve_pipeline_stages` = parse+extract+kg.build」两处断言按新登记集合更新。

---

## 7. 真机跑数结果（抽取 / 建图 / 检出 / 激活）

### 7.1 抽取（6 片全，`changes/Sprint7.1/redemo_pipeline.py extract-all`）

```
===== extract-all done elapsed=5645.8s failed=[] =====
```

| 切片 | 文档 id 前 8 位 | entities | relations | chunks | llm_calls | 代币（prompt+completion） | 目录价 |
|---|---|---|---|---|---|---|---|
| 蛇口 p1–190 | `a711dc7f` | 2000 | 268 | 251 | 289 | 1,058,565（617,559+441,006） | ¥6.1146 |
| 蛇口 p191–314 | `d80d9c62` | 2000 | 875 | 90 | 90 | 545,793（329,966+215,827） | ¥2.3865 |
| 公路 p1–190 | `f88f6a58` | 2000 | 493 | 210 | 211 | 1,318,302（772,964+545,338） | ¥5.9086 |
| 公路 p191–290 | `a31982f3` | 1082 | 491 | 56 | 56 | 312,916（204,446+108,470） | ¥1.2767 |
| 轮船 p1–190 | `ecbba312` | 2000 | 552 | 275 | 276 | 1,470,730（999,434+471,296） | ¥5.7692 |
| 轮船 p191–290 | `56a49265` | 2000 | 819 | 104 | 104 | 601,604（373,062+228,542） | ¥2.5745 |
| **合计** | | **11,082** | **3,498** | **986** | **1,026** | **5,307,910** | **¥24.03** |

单价取自 DeepSeek `models.list()` API（同 S7.0 口径），`deepseek-chat` 目录价：
未命中缓存输入 ¥2 / 百万、缓存命中 ¥0.5 / 百万、输出 ¥8 / 百万。
以上为**目录价**（阶段一有赠额 / 缓存折扣，实付更低），与 S7.0 §7 同口径记账。

两处**不粉饰**的事实：

1. 5 份切片 entities 触到 `EXTRACTION_MAX_ENTITIES_PER_DOC=2000` 上限被裁剪
   （提高上限 = 更高时延 / 成本；本批次维持 2000，成本：大家关心的只是
   **法人 / 地址是否被抽到**，本节 7.2 为真机核验）；
2. `公路 p191–290` 只有 1082 实体（未触顶），说明该片内容本身就薄。

### 7.2 §2.2 建图 + 真机计数核验

```
redemo_pipeline.py build-all --version 879232d4… --docs <6 片>   → failed=[] elapsed=11.6s
redemo_pipeline.py finalize  --version 879232d4…
  version=v-s71a-fe1c4dc3 status=ready entity_count=11082 relation_count=3498 chunk_total=986
redemo_pipeline.py neo4j-counts --version v-s71a-fe1c4dc3
  Subject 节点 = 46 / Address 节点 = 45 / LegalPerson 节点 = 25
  LEGAL_REP 边 = 26 / REGISTERED_AT 边 = 51
  Entity 节点（M2 对照）= 11082 / Chunk 节点（证据层）= 986
  valueType 抽样：name=STRING NOT NULL
                 source_entity_ids=LIST<STRING NOT NULL> NOT NULL len=1..6
```

`source_entity_ids` 在 Neo4j 里是 **LIST&lt;STRING NOT NULL&gt;**（不是字符串，也不是 Integer），
且跨 6 份文档累加到 len=6 —— 这是「少了一条边 ≠ 少了一份证据」的地基（见 7.4）。

### 7.3 §2.3 / §2.4 检出结果（`risk.detect` 执行体）

```
redemo_pipeline.py detect --doc a711dc7f…
--- suspicions total=10 kg_version=v-s71a-fe1c4dc3 ---
```

| # | 类型 | 涉及主体 | 共享节点 | 证据条数 |
|---|---|---|---|---|
| 1 | 共享法人 | 招商局集团有限公司 / 招商局轮船有限公司 | 缪建民 | 6 |
| 2 | 共享地址 | 旺景置业有限公司 / 中国经贸船务(香港)有限公司 | 香港特别行政区 | 4 |
| 3–8 | 共享地址 | 招商轮船散货船控股 / 招商轮船 LNG 运输投资 / 招商轮船油轮控股 / CMES PCTC HOLDINGS（两两组合 6 条） | 利比里亚 | 每条 3–4 |
| 9 | 共享地址 | 恒祥控股有限公司 / 招商局能源运输投资有限公司 | 英属维尔京群岛 | 5 |
| 10 | 共享地址 | 中外运集装箱运输有限公司 / 上海招商明华船务有限公司 | 上海 | 4 |

- **引用覆盖率 = 100%**：每条疑点 3–6 条 `:Chunk` 原文证据（合计 42 条，**无 0 证据条目**）。
  取证方式也一并写下：实现纪律是「取不到证据的命中直接丢弃并打
  `affiliation_suspicion_dropped_no_evidence` WARNING」——既然日志里该 WARNING 命中 **0 次**
  （`affiliation_suspicion_detected` 命中 10 次），产出的 10 条就都带证据。
  只数「产出的疑点有几条带证据」会被自己骗过去：**被丢掉的那些不在产物里**；
- **≥3 条疑点**达成，且**没有调任何阈值**（严重度固定 `medium`，见 §6.1）；
- `trace_id` 贯穿：documents.trace_id = `c2f02151-9989-46f3-b1c2-33789ef8b7e4`
  = build-all 日志该片打印的 trace_id = `suspicions.json` 产物里的 trace_id。

**一处必须诚实指出的质量局限**：第 2–10 条「共享地址」的共享值都是**粗粒度地名**
（利比里亚 / BVI / 香港特别行政区 / 上海），来自年报「主要经营地 / 注册地」那一栏，
**不是门牌级地址**——同一层写字楼、同一离岸注册地才会是 demo 想要的那种强线索，
这些顶多算「同一注册辖区」。因此它们的**证据强度弱于**第 1 条共享法人
（"两家公司的法定代表人同为缪建民"）。

根因是两条，都**不在本批次范围内**，登记而非顺手做：

1. 抽取侧没把地址拆成「省 / 市 / 门牌」，整串当成一个 `ADDRESS` 值；
2. 本批次**不做地址归一化**——即便做，也只是修好"写法不一致"（如 `'中国 北京'` vs
   `'中国北京'`），而上表这些已经是同一写法合出来的节点，**归一化救不了粒度**。
   真正的治理（主体对齐 + 地址解析 + 统一社会信用代码缺失下的实体消解）属
   **S9 批次 D**（plan 第 582 行），本批次不越界。

### 7.4 真机发现 F：并行边 → 疑点重复出条（已修）

首轮检出 **13 条**，其中同一疑点重复 3 遍：

```
[1][2][3] shared_legal_rep 招商局集团有限公司 / 招商局轮船有限公司 / 缪建民   ← 同一条
[8][9]    shared_address   恒祥控股 / 招商局能源运输投资 / 英属维尔京群岛     ← 同一条
```

**根因**：两条 M4 边的 MERGE 键是 `{id, kg_version}`，而边 id 当时用的是
**抽取侧的 relation id**（`f"{version}:lr:{relation_id}"`）——同一条事实在 3 份文档里
被抽到 3 次，就长成 **3 条并行边**；两跳 Cypher 是按**路径**匹配的，于是报 3 遍。

**修**：边 id 改为**按端点生成**（与节点 id 同源：`{subject_id}:{person_id}`），
并用 dict 去重行。修复后并行边 43→26、57→51，**13 → 10 条且无重复**。
重复命中不丢信息：证据汇聚在节点的 `source_entity_ids`（累计到 len=6）。

顺带一条教训：**这个 bug 是本批次经真机才发现**——既有用例
`test_same_name_across_documents_collapses_into_one_node` 原本断言「同一 (公司, 法人)
跨文档 → 2 条边且 id 不同」，恰好把错误口径钉成了"标准答案"。本批次把它改写为
`test_same_fact_across_documents_collapses_into_one_edge`（断言 1 条边 +
两个 source entity 都留在 `source_entity_ids`），并为 `REGISTERED_AT` 侧补了同一条纪律。

### 7.5 激活 + 旧版本不误报（tasks §2.4 第 3 条的处置）

```
activate_version.py（照抄 routes/graph.py::activate_kg_version 的顺序：先 PG 真源，再 Neo4j 镜像）
  [PG]    version=v-s71a-fe1c4dc3 status=ready
  [Neo4j] active=v-s71a-fe1c4dc3 superseded=['20260917T090000Z-phase09', 'v-3e381d36']
```

tasks §2.4 第 3 条担心「登记后上传链路自动跑 M4 → 老文档误报一堆疑点」。真机结论分两层：

1. **不会自动跑**：见 §6.3——本仓库**没有**跨阶段投递，上传链路只提交管线**首个**阶段，
   `risk.detect` 目前**只能**由脚本显式驱动；
2. **就算显式跑也不会误报**：拿无 M4 数据的旧演示文档（4 KB dummy，
   kg_version = `v-3e381d36`）跑 `detect` → `suspicions total=0`，不抛错、不改状态机。
   顺带证明跨版本隔离有效（该版本图里没有 `:Subject`，不会串到新版本的数据上）。

遗留一处**未清理**：PG 里 `v-3e381d36` 与新版本同为 `ready`（`get_active` 按
`ready_at desc` 取最新，故读侧拿到的是新版本 ✓），但严格说旧版本被镜像层置
`superseded` 后 PG 也该同步。本批次**不动历史演示数据**，登记给 Sprint 8 一并处理。

---

## 8. 本批次登记的缺口（承接方已定）

| 编号 | 缺口 | 承接 |
|---|---|---|
| **S7.1-5** | **管线无跨阶段投递**：上传只提交首个阶段，`risk.detect` 无法自动被触发（§6.3） | Sprint 8 |
| **S7.1-6** | **疑点无持久化**：无 `affiliation_suspicions` / `affiliation_tasks` 表，产物只有日志 + `kg/suspicions.json` | Sprint 8 批次 B（与对外端点同批） |
| **S7.1-7** | ✅ **2026-09-24 收尾已落**：`docs/release-notes/v1.3.0.md` §6.9 已登记「两层并存」（`:Entity` + `:Subject`）为已知限制 | 已关闭；统一工作归 **S9 批次 D 实体消解** |

另有一条**未裁决**（非缺口、属用户侧口径决策）：`char_offset` 以偏移为准还是以
`mention` 回查为准（tasks §2.1 末条）。本批次未改它；§2.3 的证据链路不依赖实体级偏移
（走 chunk 区间），故不阻塞。

## 9. 未触碰项 + 收尾确认

**未触碰**：`frontend/`（零改动）、`contracts/openapi.yaml`（零 diff）、
`app_version`（仍 `1.2.0`）、接缝 5 / 7 / 8、`affiliation_*` 任何端点与表、
M4 的另三类算法（连通分量 / 环路 / 金额不一致）、四源主体对齐（含 CSV）。

**收尾确认**（逐条对着 tasks.md）：

```
uv run pytest -q                       → 352 passed
uv run ruff check .                    → All checks passed!
uv run ruff format --check .           → 101 files already formatted
uv run python scripts/check_seams.py   → ERROR 0 / WARN 6 / OK 7
uv run python scripts/export_openapi.py --check → [OK] 与模块一致
```

真机侧：6 片抽取 `failed=[]` / 建图 `failed=[]` / 计数核验见 §7.2 /
检出 10 条且引用覆盖率 100% 见 §7.3 / 版本已激活见 §7.5。
**提交前仍未做的动作**：UI 未验证（`npm run typecheck` / `lint` 本批次无须跑——前端零改动）；
`app_version` 未 bump（按 task §5 第 5 条）。

