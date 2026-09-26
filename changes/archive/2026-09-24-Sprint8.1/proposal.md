# Sprint 8.1 批次 A —— 审计最小闭环

## 范围

**唯一真源**：`docs/v1.1.0-demo-mvp-plan.md:308`

> **A 审计最小闭环** | `qa_logs` + `audit_log` 两张表；2 个只读查询接口（按 trace_id / 按租户列表）；前端 audit 页关 Mock

**验收（plan §7.2，与本次相关的行，逐字）**

> - [ ] PRD §5 黄金路径**步骤 1~6** 全通（**步骤 7 = C1~C3 属 Sprint 13，本 Sprint 不得宣称 7/7**）；步骤 6：全程 `trace_id` 在 audit 页可见 **≥ 7 条**记录；
> - [ ] **关 Mock 硬门槛**：audit 页走真实接口；全站 `NEXT_PUBLIC_USE_MOCK=false` 走查通过（settings 豁免）

**关联 spec**：`specs/m5-permission-audit.md` §3 验收 2 / 6 / 7；`specs/m3-graphqa-citation.md` §4.3（`qa_logs` 字段清单一字不改）

## 现状（2026-09-24 开工前核实，非推测）

| 项 | 实测（含行号） |
|---|---|
| `backend/app/db/models.py` | **单文件 421 行**，仅 **7 张表**（`documents:46` / `kg_versions:125` / `affiliation_tasks:197` / `affiliation_suspicions:246` / `unaligned_subjects:303` / `external_refs:334` / `domain_events:379`）——**无 `audit_log`、无 `qa_logs`**；建表靠 `init_db()` 的 `create_all`（`session.py:42-49`），**全仓无 Alembic** |
| `backend/app/api/v1/routes/` | 无 audit 路由；`router.py:15-16` 注释明写「`/audit*` 留草案态，**禁止提前注册**」——本批次注册须一并改掉这句 |
| `frontend/src/api/` | 无 `audit.ts`（有 `affiliation` / `client` / `dashboard` / `documents` / `graph` / `qa`） |
| `frontend/src/app/audit/page.tsx` | 存在但为**占位**（无 API 调用） |
| `trace_id` 生成 | `core/middleware.py:17-19` `new_trace_id()`（UUIDv4）+ `:43-79` `TraceIdMiddleware`（纯 ASGI）；路由侧 `deps.py:40-42` `get_trace_id()`。⚠️ **任务侧有第二个生成器** `tasks/manager.py:233-241`——**不得再造第三份** |
| 已落 `trace_id` 的表 | 5 张：`documents:109` / `kg_versions:173` / `affiliation_tasks:243` / `affiliation_suspicions:300` / `domain_events:413` |
| **唯一真缺口：问答** | `services/agents.py:194` `query()` 全函数**零 DB 写入**（`db` 参数只用于 `fetch_active_kg_version` 读）⇒ 必须落 `qa_logs` |
| **复核环节：不必改签名** | `affiliation.py:172` `patch_suspicion_status()` 确无 `trace_id` 参数（`routes/affiliation.py:235` 取了但只进响应体），**但 PATCH 是独立 HTTP 请求 ⇒ 审计中间件（A1）会为它写一条带自身 `trace_id` 的 `audit_log`**，A2 的路由映射给它 `action=affiliation.review` 即可读。**不改 `patch_suspicion_status` 签名**——那是动既有行为，属范围蔓延 |
| 只读接口写法参照 | `routes/documents.py:76-126`（`page` 1-based、`page_size` `le=PAGE_SIZE_MAX`、纯 Python 切片免 OFFSET、`identity.org_id` 过滤）；`org_id` **唯一来源** = `CurrentIdentity`（`deps.py:45-80`，取不到即 401，**无匿名路径**） |
| 接缝门禁 | `ERROR 0 / WARN 2 / OK 8`；2 条 WARN = **接缝 6（ExportSink，1.4.0 到期）**，属**批次 E**，本批次不动 |

> 另注：`qa_logs` 未建表这一缺口已于 2026-09-24 补做 S6 对账时登记（`specs/m3-graphqa-citation.md` §6 S6.4-3），本批次正是它的偿还点。

## 盘点结论（长指南 §17.1 九项，2026-09-24 只读完成，未落盘未改码）

> 完整证据见本文件"现状"表与下节决策；此处只记**改变方案**的结论。

1. **审计表不复用 `domain_events`**：`payload` 是无结构 dict 无法建索引（`events/base.py:29`）；语义是「对外出口」（`dispatched_at`）而非「对内留痕」；且实现类被门禁锁死**恰好 2 个**（`base.py:3-6`），加不了第三个 sink。可复用的是它「**同 session、不自行 commit**」的写入范式（`events/db.py:14-17`）。
2. **`kg_nodes` / `kg_relations` / `token_usage` 不是表**，是 `AgentQueryResponse` 响应字段（`schemas/agent.py:164/171/178`，契约 `openapi.yaml:584-595/621-625` 已有）⇒ 批次 C ① 是**回填 spec / PRD 的契约层投影**，不是建表（`m3:80` 后 + `03-prd.md:157` 后）。
3. **`GraphEdge.type` 枚举无差异**：代码 9 值（`schemas/document.py:27-37`）与 `m2:73-81` **逐字一致**；真正有出入的是 `LEGAL_REP` / `REGISTERED_AT`（S7.1 真写边 `builder.py:302/312`、**不在契约枚举**，读侧兜底 `MENTIONS`，真名留 `properties.relation_name`）。
4. **PRD 状态行无需改**：`plan:310` 明写"已提前完成，本批只复核"（`03-prd.md:5` 现为"v1.0.0 仅交付工程外壳，MVP 1.0 未完成"）。
5. **接缝 6 的计数是 `min=max=1`**（`check_seams.py:132-133`）⇒ 只能有**一个类**继承 `ExportSink`（`JsonCsvExportSink(fmt=...)`），拆 Json+Csv 两个类直接 ERROR；编排器**绝不继承**基类。
6. **批次 C 漏项**：`plan:467` 第 5 项 `docs/multimodal_rag_backend_api_spec-v1.0.md` 6 处过期描述清理——本次盘点未覆盖，批次 C 须补。
7. **种子数据集当前无资产**：语料 `docs/annualreport/` 被 `.gitignore:39` 排除；驱动脚本 `redemo_pipeline.py`（831 行）在 `changes/archive/.../Sprint7.1/`；受控问题集硬编码在 `eval_controlled_qset.py:39-55` 且 `:37` 注明基于「2025 年度集团经营指标分析报告」——**与现存年报语料不同源**。

## 硬约束

1. **契约先行**：先改 `contracts/openapi.yaml` → 后端实现 → `npm run gen:api` → 前端（`sprint-calendar.md` §3「批次推进」）。
2. **关 Mock 是硬门槛，不是"顺手"**：新增端点**必须同步 `CONTRACT_COVERED_PATTERNS`**，否则 `shouldMock()` 对新端点返回 true 直接违反硬门槛——这是 Sprint 6.4 §2.1 撞过的坑（批次 B 加端点时漏登记）。
3. **表判定靠 ORM**：`check_seams.py` 的 `PresenceRule` 扫 `__tablename__`，不查真库；全仓**无 Alembic / 无 .sql**（建表靠 `init_db()` 的 `create_all`）⇒ **不写迁移脚本**。
4. **`org_id` 隔离键**：两张表均须带 `org_id` 且索引以 `org_id` 打头（ADR-0003）。
5. **只动审计 / 问答打点**：不改 `documents` / `graph` / `affiliation` 的既有行为；受控问题集引用覆盖率 100% 属**回归项**，不得被本批次破坏。
6. **接缝门禁不变**：本批次不引入任何 `EventSink` 之外的接口实现，保持 `ERROR 0 / WARN 2`。

## 决策点（建议项）

| 编号 | 决策 | 建议 | 理由 |
|---|---|---|---|
| **A1** | `audit_log` 的写入点 | **中间件全量写 + 路由 allowlist**：在现有 `TraceIdMiddleware` 同层加 `AuditMiddleware`，仅对 `/api/v1/*` 且**非 health** 的请求写一条 | M5 §3 验收 2 字面要求「**任一** API 调用成功 / 失败 → 写一条」；靠显式埋点必然漏，且"漏埋"比"多写"更难被发现。allowlist 排除 `health` 是为了不让探针噪声把演示页撑爆 |
| **A2** | `action` 取值 | 用**路由元数据映射**业务名（`document.upload` / `document.parse` / `agent.query` / `affiliation.detect` / `affiliation.review` …）；未登记的路由回落为 `http.<method>.<path>` | 验收 7 要人看得懂；回落值保证**不丢条**（宁可 action 丑，不可无记录）。回落逻辑须有日志留痕，便于后续补映射 |
| **A3** | 两个端点形状 | `GET /api/v1/audit`（按租户列表，支持 `action` / `status` 过滤，**默认 `ts DESC`、页大小 50**）+ `GET /api/v1/audit/trace/{trace_id}`（按 trace 查全部记录） | 与 plan「按 trace_id / 按租户列表」逐条对应；分页口径照 M5 §3 验收 7 原文（默认 50） |
| **A4** | `qa_logs` 写入点 | `services/agents.py` 产出 `AgentQueryResponse` 后落一条（成功 / 拒答**都落**） | M3 §4.3 字段清单一字照抄；`question_hash` / `answer_hash` **不记原文**（§5.3 纪律） |
| **A5** | 脱敏范围 | 本批次**不引入脱敏器**；`audit_log.detail` 只写**结构化字段**（`resource` / `status` / `reason`），**绝不写响应体原文** | 脱敏器属 H5 / S11，范围外。不写原文 ⇒ 本批次**不新增泄露面**，比"写进去再想办法脱"更稳。此边界须在 release notes 显式声明 |
| **A6** | `actor_id` / `actor_ip` | 沿用 dev 脚手架头（`X-Actor-Id`）；`actor_ip` 取 `request.client.host` | 与批次 B/C 既有的 dev 取证口径一致（批次 B 复核已用 `X-Actor-Id`），不另起一套 |
| **A7** | 是否需要 `design.md` | **不写**：无多方案架构取舍，A1~A6 已在本表定完 | §9.1 第 4 项「有架构决策或多方案时补」，本批次不满足 |
| **A8** | 前端形态 | 新增 `src/api/audit.ts` + 复用现有 store 模式（`use-audit-store`），**不引新依赖** | 与 `affiliation` 页保持同构；轮询**不需要**（审计页非异步任务场景） |
| **A9** | 审计表主键类型 | **用 UUID**（照 `models.py:221`），**不用** `m5:99` 写的 `BIGSERIAL`；差异在 `docs/adr/ADR-0003` 登记 | 全仓 7 张表**全部** UUID 主键；spec 的 `BIGSERIAL` 与实现风格冲突，跟随实现 + 显式登记，比改代码去迁就 spec 成本低且不引入混合主键 |
| **A10** | 是否复用 `EventBus` 写审计 | **不复用**：两张表直接「同 session + 业务 commit 前 `session.add`」（`events/db.py:14-17` 的范式照抄） | `domain_events.payload` 无索引、语义对外、实现类被锁死 2 个；审计要按 `action` / `status` / `actor_id` 过滤，塞 dict 只能全表扫 JSON |
| **A11**（Q1，批次 B） | 限流实现方式 | **用 slowapi**（PRD `:117` / `m5 §3 验收 5` 点名）；⚠️ 开工前先试装，**装不上立即升级用户** | spec 点名，偏离须在 ADR 登记；代价是它基于 `BaseHTTPMiddleware`，与 `core/middleware.py:3-4`「不用 BaseHTTPMiddleware」的选择有张力——先按 spec 走，实测有冲突再登记 |
| **A12**（Q2，批次 B） | fail-open 收口口径 | **保留逃生阀 + 补审计留痕**：`agents.py:273-277` 的 warn-only 分支写一条 `audit_log(action=tenant_leak.warn)`；同步修 `backend/CODEBUDDY.md:94` 的文档口径（现写"False 为逃生阀"，而 `config.py:146` 默认 `True`） | 删逃生阀要动 `test_agent_fail_closed.py:128-135` 的既有回归锁，且会丢掉真实运维能力；留痕比删除更可观测。**不删测试** |
| **A13**（Q3，真机） | 演示真机的数据策略 | **复用现有图谱，不重建**：只补「问答 / 复核」两个环节的审计落点；重建图谱属批次 D | 重建要全量重抽（要钱 + 要时间），而审计闭环的判据不依赖图谱内容；**LLM 余额开工前须一次性确认**（见"风险"第 5 条） |
| **A14**（Q4，批次 B） | `rate_limit.triggered` 是否写 `audit_log` | **纳入**：批次 B 做限流时同步写一条 `audit_log(action=rate_limit.triggered)`（`alert` 表仍不做，P2） | `m5 §3 验收 5` 字面要求；批次 A→B 顺序天然满足依赖，不做则 H7 只做一半。⚠️ 同时必须在 `errors.py:122-132` 加 `429: RATE_LIMITED`，否则 429 兜底成 `HTTP_ERROR`（映射 500），直接违反矩阵 `:133` 判据 |
| **A15**（Q5，批次 D） | 受控问题集与现语料不同源 | **如实登记为已知限制，不重造**：写进批次 D 基线说明与 release notes | `eval_controlled_qset.py:37` 注明基于「2025 年度集团经营指标分析报告」，与 `docs/annualreport/` 年报语料不同源；重造要人工下载 + 花钱，且属范围蔓延 |
| **A16**（Q6，批次 D） | settings 页处置 | **加「演示环境」标注**（不选"隐藏路由"） | 隐藏会让「零假数据」硬门槛失去可核性；标注既诚实又可核 |

## 明确不做（边界）

- ❌ **RBAC 三粒度 / RLS / 私域开关 / 限流**——S11（M5 §3 验收 1 / 4 / 5 / 8 不在本批次）
- ❌ **敏感字段脱敏器**——H5 / S11；本批次以"不写原文"规避（见 A5）
- ❌ **`alert` 表**——M5 §3 验收 5 明确标 P2
- ❌ 种子数据集 / 演示彩排 / settings 页处置——批次 D
- ❌ `ExportSink` 与接缝收口——批次 E（**1.4.0 到期，bump 时转 ERROR，别拖到最后一天**）
- ❌ `list_in_flight_task_ids()` 只扫 `documents`——缺口 **S7.2-2**，已登记承 **批次 B**，本批次不动
- ❌ 迁移脚本 / Alembic；❌ 新增 `settings.*` 配置项（无消费者的配置不得提交）

**M5 §3 边界确认（本 Sprint 只做这 4 条的一半，不得宣称 M5 达成）**：

| M5 §3 | 内容 | 本 Sprint |
|---|---|---|
| 验收 2 | 任一 API 调用成功 / 失败写 `audit_log` | ✅ 批次 A |
| 验收 6 | `trace_id` 全链路一致 + `X-Trace-Id` 回显 | ✅ 批次 A（回显已就位，只补贯穿） |
| 验收 7 | `GET /audit` 按 actor/org 隔离、默认 `ts DESC` 分页 50 | ✅ 批次 A |
| 验收 5 | 限流 429 `RATE_LIMITED` + `audit_log(action=rate_limit.triggered)` | 🟡 批次 B（**`alert` 表 P2 不做**） |
| 验收 1 / 3 / 4 / 8 | RBAC 三粒度 403 / 敏感字段脱敏器 / 私域阻断 / **RLS** | ❌ **S11**，显式登记缺口 |

## 风险 / 待确认

1. **「≥ 7 条」是真机判据**：依赖演示路径（上传 → 解析 → 建图 → 提问 → 检测 → 复核）**每一步都落一条**，A1 的中间件必须真的覆盖到，且要在真机上数一遍，不能靠估算。
2. **中间件写库失败不能拖垮主流程**：审计写失败应**只记日志**不抛异常（否则一个审计缺陷变成全站 500）——与批次 D「事件失败不影响主流程」同一纪律。
3. **噪声风险**：`health` 已排除，但 `gen:api` 后若新增被前端轮询的端点（如 `affiliation` 的 2s 轮询），审计表会快速增长 ⇒ 真机走查时**实测一次条数**，必要时收 allowlist。
4. ~~**批次 B 的 slowapi 需装依赖**~~ **已实测通过（2026-09-24，开工前完成）**：`uv add slowapi` → `slowapi 0.1.10` + `limits 5.8.0`（+`deprecated` / `wrapt` 共 5 包）；`uv.lock` **纯新增 126 行、零删改**（未牵动 fastapi 0.141.1 / starlette 1.6.0 / httpx）；`368 passed` 不变；冒烟 `2/minute` 下第 3 次请求真出 **429**。⇒ **A11 的"装不上要换方案"风险已消除**。
   ⚠️ **但实测暴露一个必做项**：slowapi 的默认 `_rate_limit_exceeded_handler` 返回 `{"error":"Rate limit exceeded: 2 per 1 minute"}`，**不符合 H3 统一格式 `{code, message, detail, trace_id}`**，且无 `Retry-After` 头 ⇒ 批次 B **必须自定义 handler** 走 `AppError(ErrorCode.RATE_LIMITED).to_body(trace_id)`，并同步在 `errors.py:122-132` 加 `429: RATE_LIMITED`（否则兜底成 `HTTP_ERROR`→500）。A14 由"提醒"升级为**必做**。
5. **真机要花钱（A13 的前置）**：走查里「提问」要调 LLM。**开工前须向用户确认 DeepSeek 余额**；策略已定为**复用现有图谱、不重建**，但余额数字**不得推测**——没有数字就没有真机判据。
6. **只有 `agents.py` 需要引入 session**（写 `qa_logs`）；复核环节**不改** `patch_suspicion_status()` 签名（理由见"现状"表）。若实施中发现"不改签名就落不了审计"，**先停下来升级**——那是范围蔓延，不是顺手。
7. **「≥ 7 条」的口径要在真机前定死**：plan §7.2 原文是「全程 `trace_id` 在 audit 页可见 **≥ 7 条**记录」。实测链路里有**多个** trace_id（HTTP 请求一个，后端任务由 `tasks/manager.py:233-241` 另生成一个），所以**不能**理解为"同一个 trace_id 下有 7 条"。本批次按「**审计页可见全程 ≥7 条记录，且每条都带 trace_id，且可按 trace_id 过滤回看任一步**」执行，并在 integration-log 里**显式登记这个口径解读**，不静默选一种。
