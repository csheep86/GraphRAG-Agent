# backend/CODEBUDDY.md — 后端作用域规则

> 本文件只作用于 `backend/`，与仓库根 `CODEBUDDY.md` 共同生效；冲突时以根规则为准。

## 1. 数据存储策略

| 存储 | 承担的数据 | 环境 | 状态 |
|---|---|---|---|
| **SQLite** | 关系型数据（`documents` 等）—— **PostgreSQL 的本地等价替身** | `development` / `test` | 在用 |
| **PostgreSQL** | 生产关系型数据；启用 RLS 做租户隔离 | `production` | 待 Sprint 4 接入 |
| **Neo4j** | 知识图谱：`(:KgVersion)` 版本状态机 + `(:Entity)` 实体与实体间关系 | 全环境 | 在用 |

- `DATABASE_URL` 默认 `sqlite:///./dev.db` 只允许出现在 `development` / `test`。
- `production` 环境若检测到 `sqlite` 驱动，**必须直接启动失败**，禁止静默降级。
- 依据：[`docs/adr/ADR-0003-tenant-isolation-rls.md`](../docs/adr/ADR-0003-tenant-isolation-rls.md) §3.6。
- 未启用 RLS 期间，`org_id` 过滤**只由应用层保证**（`app/services/documents.py`），
  **任何新增查询都必须带 `org_id` 条件**，不得绕过。

> SQLite 不是「临时兜底」而是 PG 的**开发态替身**：字段类型、约束与查询语义以 PG 为准，
> 两者的差异只允许出现在「RLS 是否由数据库强制」这一点上。

### 1.1 Neo4j 图谱与版本可见性（ADR-0002）

- 图谱数据**只能**经 `uv run python scripts/import_to_neo4j.py` 写入，遵循三段式：
  `(:KgVersion {status:'writing'})` → `MERGE` 实体 / 关系 → 置 `active`；
  异常路径删除该版本实体并把 `:KgVersion` 置 `failed`。
- **一致性铁律**：只消费 `status = 'active'` 的版本。
  - 读取入口唯一：`GraphService.fetch_active_kg_version()`；
  - 调用方显式传入版本时，`GraphService.fetch_kg_version_status()` 校验；
    非 `active`（`writing` / `failed` / `superseded` / 不存在）一律 **409 `KG_VERSION_NOT_ACTIVE`**，
    **严禁静默降级**到最新 active 版本。
- **故障语义边界**（三者必须严格区分，不得混为一谈）：

  | 情形 | 异常 | 对外的 HTTP |
  |---|---|---|
  | `Neo4j` 连不上 / 查询失败 | `GraphUnavailableError` | `501 NOT_IMPLEMENTED` |
  | 连得上但**没有** `active` 版本 | `NoActiveKgVersionError`（`GraphUnavailableError` 子类） | `409 KG_VERSION_NOT_ACTIVE`（`/graph`） |
  | 图谱可查但证据不足 | —（正常返回） | `200` + `refused = true` |

  `NoActiveKgVersionError` 刻意继承基类：既有的 `except GraphUnavailableError`
  不会漏网，业务层又能按需细分。混用会让前端无法区分
  「数据没准备好」与「后端挂了」。
- `:KgVersion` 状态机**暂落 Neo4j**；Sprint 4 接入 PG `kg_versions` 表后以 PG 为真源，
  Neo4j 侧节点类型与属性不变，`GraphService` 对外接口无需改动。
- 关系类型的契约投影规则见 `app/services/graphs.py::_relation_type`。

## 2. 认证态的临时兜底（**限期，必须偿还**）

- `X-Org-Id` / `X-Actor-Id` 请求头**仅在 `ALLOW_DEV_ORG_HEADER=true` 且非 production 时生效**。
- 这是 Sprint 1 无 M5 登录接口时的脚手架，**Sprint 3 接入 `POST /auth/login` 签发的 token 后必须移除**。
- `org_id` **严禁**从请求 body / query 读取（ADR-0003 §3.3）。

## 3. 契约同步（铁律）

1. 修改任何接口字段：**先改 `backend/app/schemas/` 的 Pydantic 模型**（后端模型是契约唯一真源）。
2. 执行 `uv run python scripts/export_openapi.py` 重新生成 `contracts/openapi.yaml`。
3. 生成物**必须提交**，禁止手工编辑 `contracts/openapi.yaml`。
4. 前端类型由阶段 3.2 的 `npm run gen:api` 生成，CI 在阶段 3.3 校验漂移。
5. **集成接缝预留字段不进契约**：为未来企业系统集成预留的可空字段/表（`documents` 的 8 个预留字段、`external_refs`、`domain_events`）**不导出到 OpenAPI**（根 `CODEBUDDY.md` §功能预留原则 第 4 条 / ADR-0004 §3）。`export_openapi.py --check` 与 `npm run gen:api` 无 diff 即为合规证据。

## 4. 已登记的实现缺口

| 缺口 | 现状 | 依据 |
|---|---|---|
| PostgreSQL RLS + `SET LOCAL app.current_org` | 未实现；SQLite 下由应用层 `org_id` 过滤兜底 | ADR-0003 §3.1 / §3.2 |
| `kg_versions` 表（PG 真源） | ✅ 已偿还（S5 批次 B 落 PG 真源表）；**S6 定 PG 为真源**（`ready` 即 active 语义）+ 新增 `POST /graph/versions/{version}/activate`（Neo4j 镜像双写，旧版置 `superseded`），读侧 PG 优先、**PG 说没有不回落** | ADR-0002 §2 |
| M3 完整 Agentic-RAG | 🟡 **S6 已偿还 chunk 级引用反查**：`_to_citation` 按 `chunk_id` 回查真实 `doc_id` / `page` / `snippet`，回查不到即丢弃（F3）；**仍无** Tool 调用循环（P2） | M3 §4 |
| `AgentQueryResponse` 缺 `kg_nodes` / `kg_relations` / `token_usage` | ✅ 已偿还（Sprint 4.10.0.A）：契约已定义三字段并由 `AgentService` 填充 | 本文件 §3 |
| `GraphEdge.type` 枚举不含「实体↔实体」关系 | ✅ 已偿还（Sprint 4.10.0.B）：枚举扩展 `HAS_FINANCIAL_INDICATOR` / `OPERATES_SEGMENT` / `RELATED`，桥梁专有类型直通；未知类型仍兜底投影 `MENTIONS` + `properties.relation_name` | 本文件 §3 |
| 文件写入存储抽象层 | ✅ 已偿还（S5 批次 A）：上传真实落盘，completed 回填 `storage_key`（**不再恒 NULL**） | M1 §4.3 |
| **S6-1** `Citation.char_offset` 恒为 0 | 未偿还：当前值为 **chunk 起点（0）**；实体级偏移待 `:Entity` 落 `char_start` 后细化 | M3 §4 / release notes v1.2.0 §6.2 → **S10** |
| **S6-2** `_snippet` 使「摘录长度 ≠ 原文区间长度」 | 未偿还：`text.strip()` 截断 200 字**再加 `…`**（真机 `snippet.length=201`）——strip 造成位移、省略号多算 1 字；前端改「去省略号 + `indexOf` 对齐」兜底（真机 `index_of_align_hit=True`）。建议后端改返回 `snippet_start` / `snippet_end` | release notes v1.2.0 §6.3 → **S10** |
| **S6-3** 实体抽取质量低（整句被抽成实体 / 数值独立成节点 / 同实体重复 3 份） | 🟡 **部分偿还（Sprint 7.0）**：「整句成实体」已根治（归因 = `_RE_ORG` 贪婪匹配，实测复现见 `changes/Sprint7.0/integration-log.md` §2 事实②；接真实 LLM 后同一切片实体样例由「本报告本公司」变为「招商局公路网络科技控股股份有限公司」）。**数值独立成节点 / 同实体重复 3 份**未处理 → 仍归 **S9 实体消解** | release notes v1.2.0 §6.1 → **S9 实体消解** |
| **S6-4** 抽取链路「名义 provider、实为 stub」（2026-09-23 新增） | ✅ **已偿还（Sprint 7.0）**：新增 `settings.extraction_engine`（`llm` / `mock`，未知档位显式报错、不静默回退）；`llm` 档单 chunk 真实调用 LLM（走接缝 3 `build_chat_model()`，不新建客户端），Prompt 仍由 `prompt_loader` 加载 `kg_extraction_v1`；失败 / 超时 / 非法 JSON → `LangextractError`，**严禁回落 mock**。真机对照：同一切片 mock 120 实体 / 3 类 vs llm 421 实体 / 8 类（¥0.41 / 12 chunk） | 已完成；证据 `changes/Sprint7.0/integration-log.md` §4.3 |
| **S6-5** `prompts/entity_relation_extract_v1.md` 无代码消费者（2026-09-23 新增） | 未偿还：生产链路硬绑 `load_prompt("kg_extraction", …)`（`langextract.py` 293–295 行）；该模板全仓仅出现在 `tasks/registry.py` 第 182 行注释里，与 `kg_extraction_v1.md` **语义重叠、两套抽取模板并存** | 2026-09-23 S6 收尾盘点（决策点 D4）→ **Sprint 8 批次 C 治理**（裁决销毁 / 合并） |
| **S6-6** Prompt 侧与代码侧的类型枚举不一致（2026-09-23 新增） | 未偿还：`kg_extraction_v1.md` 第 25 / 37 行的枚举含 `VENUE` / `PRODUCT`，而 `langextract.py` 的 `ENTITY_TYPES` 仅 6 类——**谁为准尚未裁决** | 2026-09-23 S6 收尾盘点 → **Sprint 8 批次 C 治理**（与 S6-5 一并收） |
| 契约 `description` 描述漂移 | ✅ 已偿还（Sprint 4.10.0.C + C2）——C 批：`/graph`、`/agent/query`；C2 批：`/upload` | 本文件 §3 |
| C2：`/upload` 的 `description` 过期 | ✅ 已偿还（Sprint 4.10.0.C2）：`routes/documents.py` 原「不注册异步执行体 / `status` 停留在 `pending` / Sprint 3 补齐」已改为真实链路措辞（含 H1 状态机、H8 重试、启动回收、骨架版局限），并同批重导出 `contracts/openapi.yaml` + `frontend/src/types/api.d.ts` | 本文件 §3 |
| S4-1：`docs/multimodal_rag_backend_api_spec-v1.0.md` L137 | `NOT_IMPLEMENTED` 行仍写「契约已定稿、实现留待 Sprint 3 / 来源：Sprint 1 边界」，与已实装的 5 个接口不符 | ✅ 已偿还（Sprint 4.13） |
| S4-2：`specs/m2-extract-kg.md` L157 | `/graph` 仍写「实现在 Sprint 3，当前占位返回 501」 | ✅ 已偿还（Sprint 4.13） |
| S4-3：`frontend/` 注释过期 | `api/client.ts` L15-16、`api/graph.ts` L41、`api/qa.ts` L61、`.env.development` L9-10 仍表述「大部分端点当前实现状态为 501 NOT_IMPLEMENTED」 | ✅ 已偿还（Sprint 4.13） |
| S4-4：`tasks/registry.py` L135-138 docstring 过期 | 仍写「Sprint 3 后段将替换为…ADR-0002 三段式写入」，而该段实现已随 D2（PG `kg_versions` 真源）移出 Sprint 4 | ✅ 已偿还（Sprint 4.13） |
| E1：财务指标孤立节点 | output.json 12/16 财务指标实体无任何边，图谱连通性差 | ⏳ **`unresolved`（Sprint 5 按 §4.4 第 3 条收口）**——见 §4.1 |
| E2：实体命名可疑 | 「智能制造与数字服务」「集团」等实体命名不符预期 | ⏳ **`unresolved`（同上）**；Prompt 抽取规范重设计归属 Sprint 13（条件吸收，见计划 §10） |
| `/agent/query` 缺 PG 前置租户隔离 | Cypher `_QUERY_ALL_ENTITY_SUBGRAPH` fail-open；route 无 PG `documents` 表前置租户校验 | ✅ **已偿还（Sprint 5 批次 B）**：`AgentService.query` 经 `GraphService.validate_kg_version_tenant_boundary` 校验 → `AgentTenantLeakError` → 路由层 **403 `KG_TENANT_LEAK`**；`settings.agent_fail_closed=False` 为逃生阀 |
| B1：Document.retry_count 列存在但 executor 从不更新 | 列已声明（Schema 有），executor 从不写；要么漏写、要么该删列 | ✅ **已偿还（Sprint 5 批次 A）**：`registry.py` 在 tenacity 重试回调与 completed 分支回写 `documents.retry_count`；阶段列 `extract_retry_count` / `kg_build_retry_count` 同步回写 |
| B4：Settings.task_retry_multiplier 在**任务退避路径**未被读取 | 字段定义 default=2.0, gt=1；`app/tasks/registry.py` 只用 `task_retry_initial_seconds` 作 multiplier——**任务重试改该配置无效果** | ✅ **已偿还（Sprint 5 批次 A）**：三个执行体（parse / extract / kg.build）的 `wait_exponential` 均改为 `exp_base=settings.task_retry_multiplier`；`test_graph_and_agent_routes.py` 断言退避随次数增长 |
| `_refuse()` 构造响应体未注入 trace_id | 10.4 联调发现：响应头 X-Trace-Id 正确，但 body.trace_id 在拒答分支为 None | ✅ **已偿还（Sprint 5 批次 A）**：`agents.py::_refuse()` 构造 `AgentQueryResponse` 时注入 `trace_id=trace_id` |
| S4-1 遗留：api-spec 同文件还有 6 处同类过期描述 | L31-32 / L191 / L273 / L334 / L343 / §7 整节（含「TaskManager.recover() 未实现」，实际已实现） | v1.1.0 文档刷新专项 |
| 集成接缝预留（`documents` 8 字段 / `AuthProvider` / provider 抽象 / `external_refs` / `domain_events` / 外部数据导入） | 未落。Sprint 5 批次 A2 落 provider 抽象 + `documents` 8 字段 + `AuthProvider` + 流水线阶段配置；Sprint 7 批次 B/D 落 `external_refs` + 外部数据导入接缝 + `domain_events`；Sprint 8 批次 E 落 `ExportSink`。**全部 nullable 且不进契约** | ADR-0004 / 本文件 §3 第 5 条 |

### 4.1 阶段九已偿还的缺口

| 原缺口 | 完成情况 |
|---|---|
| `TaskManager.recover()` 启动回收 | ✅ `app/tasks/manager.py::recover_orphan_tasks`，由 lifespan startup 触发（ADR-0001 §3.2） |
| `GET /documents/{id}/graph` 真实查询 | ✅ 调 `GraphService.fetch_document_subgraph`，输出严格遵循 `DocumentGraphResponse` |
| `POST /agent/query` 真实问答 | ✅ 调 `AgentService.query`，含 409 版本校验 / 401 / 400 / 501 全分支 |
| Neo4j ↔ PG Saga 写入时序 | ⚠️ 三段式已在 `scripts/import_to_neo4j.py` 落实，但状态机落 Neo4j 而非 PG（见上表） |

### 4.2 E1 / E2 收口（Sprint 5 批次 B，`unresolved`）

**结论：两项均登记为 `unresolved`——维持现状，不顺延到下一批次**（计划 §4.4 降级预案第 3 条）。

| 项 | 要求产出的数字 | 实际 | 结论 |
|---|---|---|---|
| E1 孤立节点率 | 财务指标类实体中「无任何边」的占比 | **未产出** | `unresolved` |
| E2 命名可疑率 | 实体名不符预期（如「集团」「智能制造与数字服务」）的占比 | **未产出** | `unresolved` |

**为什么跑不出数字（根因，非托辞）**：

1. Sprint 5 批次 B 落地的 `LangextractClient` 是**默认 mockable** 实现——`_default_extract_chunk` 为基于正则的占位抽取器（`ORG` / `DATE` / `MONEY` + `PARTY_TO` 共现），**真实 LLM 调用留 `_evaluate_client_call_llm` 占位**，受 `extraction_provider` 切换键约束（未实现别档显式报错）；
2. 该设计的目的是保证 **CI / 单元测试零外部依赖**——但代价是抽取产物由正则产生，**不反映真实 LangExtract 的抽取质量**；
3. 因此在其产物上统计出来的「孤立节点率 / 命名可疑率」是**正则抽取器的性质，不是 E1/E2 的性质**——拿它登记等于用假数据冒充结论，比不登记更糟。

**是否达演示可接受线**：**无法判定**（判定所需数据未产出）。演示剧本第 2 步（看图）依赖真实抽取，当前在 mockable 档位下可跑通链路但**抽取质量为占位水平**。

**后续归属**：E1/E2 专项按计划 §10 为**条件吸收 → Sprint 13**——若 Sprint 13 的 C2 实验结论为「召回 < 0.80」，E2 的 Prompt 抽取规范重设计升为 Sprint 13 阻塞项；否则结论后置 v2.0+。**本次只评估、不改 Prompt**（§4.2 批次 B 纪律）。

> **纪律说明**：§4.2 批次 B 要求「先写模板再跑数，禁止边看边调 Prompt」。当前模板已就位（`prompts/kg_extraction_v1.md`），
> 缺的是「真实 LLM 抽取产物」这一输入。一旦接入真实 `extraction_provider` 档位，即可用同一模板产出这两个数字，
> **无需重新设计模板**。

> **契约零漂移**：阶段九只改路由函数体，**未动** 任何 `@router.*` 装饰器
> （`summary` / `description` / `responses` / `response_model` 全部保持原样），
> 因此 `uv run python scripts/export_openapi.py --check` 保持通过。

## 5. 常用命令

```bash
uv sync                                        # 安装依赖（提交 uv.lock）
uv run uvicorn app.main:app --reload           # 本地启动
uv run python scripts/export_openapi.py        # 导出契约
uv run python scripts/export_openapi.py --check # 校验契约是否漂移
uv run python scripts/check_seams.py           # 接缝纪律门禁（实现集合 / 配置消费者 / 预留字段）
uv run python scripts/check_seams.py --strict  # Sprint 收尾：未到期项也要求全绿
uv run pytest                                  # 契约与行为测试
uv run ruff check . && uv run ruff format .
```
