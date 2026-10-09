# 验收可追溯矩阵（MVP 1.0 → v2.0.0）

> **目的**：把 `docs/03-prd.md` 的每条**硬约束（H1–H14）**与**准入线（C1–C3 / F1–F5）**，唯一地落到"**哪个 spec 的哪条验收 → 用什么判据 → 谁签字 → 证据放哪**"。让"是否达成"可被机械或人工复现，而不是靠叙述。
>
> **解决什么**：PRD §4 原先只说"落实模块 + 规格章节"，`docs/v1.1.0-demo-mvp-plan.md` §3.2 B 要求"H1–H12 逐条有判据（优先机械脚本，人工判据须写明验收人）"，但该动作被排到 Sprint 13（P3-1）。**本矩阵把它前置到 Sprint 5 开工前**，使每个 Sprint 收尾即可逐行对账，而不是上线前集中补。
>
> **口径真源**（本文件不复制细节，只做映射）：
> - 需求与硬约束：`docs/03-prd.md` §2 / §4 / §5 / §8
> - 交付与门禁：**排期见 [`docs/delivery-plan.md`](./delivery-plan.md)**（P1~P6）；**PRD 承接见 [`docs/prd-mvp-takeup.md`](./prd-mvp-takeup.md)**。⚠️ 原 `docs/v1.1.0-demo-mvp-plan.md` §3.2 B / §15 / §20～§21 **已随该计划全废**（2026-10-01，归档于 `changes/archive/2026-10-01-obsolete-plans/`），其中 **§15 已抢救迁移至 `prd-mvp-takeup.md`**。本文**历史记述**中对旧文件 / 旧编号（S5~S13）的引用为**史实，保留不改**。
> - 倒推与闸门：~~`docs/v2.0.0-ship-backward-plan.md` §1 ～ §3~~ **该排期已全废**（2026-10-01，见需求基线 §6.2）；现行依据 = [`delivery-plan.md`](./delivery-plan.md) **P1~P6** + [`delivery-requirements-and-guardrails.md`](./delivery-requirements-and-guardrails.md)
> - 验收条文：`specs/m1..m6-*.md` §3
> - 指标定义：`docs/02-product-outline.md` 附录 C；反证条件：`docs/01-research.md` §3.3
>
> **状态**：v1.2（2026-09-21 建立，架构师；**2026-09-22 更新**：S5 收尾对账——H4 / H8 两项「已知缺陷」关闭、M1 / M2 与黄金路径步骤 3 现状刷新、§5.3 `--strict` 口径更正为默认档；**2026-09-24 更新**：**S7 收尾对账**——新增 §3.3「M4 §3 验收 1–7 逐条对账」；M4 行与黄金路径步骤 4 补批次 C / D；H1 / H3 / H4 / H5 / H10 / H12 现状刷新；C2-c 补 M4 侧证据；**2026-09-24 追加（S6 侧补做）**：新增 §3.4「M2 / M3 §3 验收 1–7 逐条对账」，M2 / M3 行与 H4 / H8 现状刷新，**并更正「M2 `confidence` 未落库」这一过期口径（实测已落库）**；**2026-09-26 更新（S8 收尾对账）**：M5 行与黄金路径步骤 6 刷新（审计闭环落地、`qa_logs` 由「未建」转已建已写）、**H7 限流由 ⏳ 转 ✅**、M3-3 刷新；**Demo-MVP 十条总对账不在此表，见 [`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) §6**；**2026-09-28 更新（Sprint 9.5 收尾对账）**：**更正 M3 行与 §3.4 M3-1 的过期口径**——原写「代码中**无变长 Cypher**」「≥3 跳未做」，S9.5 批次 D1 已落地 `services/reasoning.py`（`:RELATION*1..3`）与响应字段 `reasoning_path`，**按纪律必须更正而非留着误导**；黄金路径步骤 5 同步刷新；`docs/dev-doc-status.md` §8 新增 **R9~R13**、`docs/sprint-calendar.md` §5 新增 **S9.5** 行）

---

## 1. 读法

| 列 | 含义 |
|---|---|
| **锚点** | 该要求在规格里的唯一落点（`M<x> §3 验收 <n>`）。**写不出锚点 = 该要求无人承接**。 |
| **判据类型** | `机械`（CI/脚本可判定）/ `半机械`（脚本产出 + 人工判读）/ `人工`（必须写明验收人） |
| **判据 / 命令** | 可复现的判定动作 |
| **验收人** | 该行由谁签字；`机械` 项由 CI 签字 |
| **现状** | 2026-09-21 核实。`✅` 已在 v1.0.0 交付 / `🟡` 部分交付 / `⏳` 待对应 Sprint / `⚠️` 已知缺陷 |

**勾选口径**：任一行**判据为空**或**验收人为空** → 该 Sprint **不得宣布收尾**（`docs/dev-doc-status.md` §9.2）。**降级必须显式**：不达标走 F1–F5 决议并落 release notes，**不得静默通过**。

---

## 2. 上线 Gate → 本矩阵章节

| Gate | 判据（倒推文档 §1） | 本矩阵 |
|---|---|---|
| **G1** 模块级 | `specs/m1..m6` §3 验收**逐条通过** | §3.1 + §4 |
| **G2** 端到端 | PRD §5 黄金路径 **7/7** | §3.2 |
| **G3** 准入线 | C1 增益 / C2 召回·误报·引用覆盖 / C3 成本 / 多跳答对率 | §5.1 |
| **G4** 硬约束 | **H1–H14 逐条有判据**（H13 / H14 于 2026-09-27 追加） | §4 |
| **G5** 诚实性 | 外部效度与数据来源声明（RAG 基线数据集同源同题、标注口径一致） | §5.2 |

---

## 3. 验收条文索引

### 3.1 模块验收清单

| 模块 | 规格 | 条数 | 编号 | 承接 Sprint | 现状 |
|---|---|---|---|---|---|
| **M1** | `specs/m1-async-ingest.md` §3 | 8 | 1–8 | S5（docx 解析 S10） | ✅ 上传 / 状态机 / 重试**全部真实**（B1 `retry_count` 回写 + B4 退避读配置已于 S5 收口）；docx 仍只收不解析 → S10 |
| **M2** | `specs/m2-extract-kg.md` §3 | **10** | 1–7 **+ 8–10（时效）** | S5（四源字段）、S6（`:Chunk`）、**S9（实体消解 + 时效 L0/L1）** | 🟡 **S5 批次 B 转正为在线服务**（上传即建图，三段式写入，`kg_versions` 为版本真源）；**S6 批次 A 落地 `:Chunk` 证据节点**（原文片段 + `page` / `char_start` / `char_end` + `acl_scope`，`(d)-[:HAS_CHUNK]->(c)` + `(c)-[:MENTIONS]->(e)`；`acl_scope` **只落属性、查询不做穿透过滤** → S11）。**`confidence` 已随 v1.2.0 落库**（节点 + 关系属性，见 §3.4 M2-2；本行原写「仍缺 `confidence` 落库」属**过期口径，已于 2026-09-24 更正**）。**2026-09-29（S9.13 批次 C3）**：**实体消解已偿还**（`entity_merge_candidates` 建表 + 消解器 + 真机 5 条候选、误并 0；判据 `specs/m2` §4.5.1，逐条对账见 §3.4 **M2-3**）——本行原写「仍缺实体消解（S9~S10）」属**过期口径，已更正**；范围限制（只在 `:Subject` 主体层、通用层未做）登记为 **S9.13-2**。**2026-09-30（S10 批次 B，`char_offset` 上游）**：实体级 `char_start` / `char_end` **已进图并可回查**（span 端到端可核，探针脚本可复算）——本行「恒 0」指 `Citation.char_offset`，其**上游 span 已偿还**；⚠️ **`Citation.char_offset` 本身仍未端到端打通**（需 PG + LLM 真机补验，见 `changes/Sprint10/integration-log.md` §4-2）⇒ 仍缺，转 **S11**（与 PG 切换一并补验） |
| **M3** | `specs/m3-graphqa-citation.md` §3 | 7 | 1–7 | S6（引用溯源）、S10（≥3 跳） | 🟡 **S6 达成 chunk 级引用溯源**：`:Chunk` 证据节点 + 引用按 `chunk_id` 真实回查（`doc_id` / `page` / `snippet`）+ 前端抽屉原文高亮；受控问题集 14 问**覆盖率 100% / 拒答误伤 0**（2026-09-24 复核：`_build_citations` 仍只认本轮注入 chunk）。**2026-09-28（S9.5 批次 D1）**：**≥3 跳遍历已落地**（新增 `services/reasoning.py` 的 `:RELATION*1..3` 变长查询 + 响应字段 `reasoning_path`，本行原写「代码中**无变长 Cypher**」属**过期口径，已更正**）；`qa_logs` 打点 **S8 已闭合**；仍缺 `route` 意图路由（恒为 `m3_graphqa`）→ 分别见 §3.4 M3-1 / M3-5 / M3-7。**2026-09-30（S10 批次 D / E，M3 检索覆盖承接 §7.9）**：候选集由「扫描序前 500 实体、无 `ORDER BY`」改为「按 `entity_type` 保底 + 组内按 `char_start` 文档序」，真机 14 题归因 75% → **100%**、库内答对率 0.83 → **1.00**、拒答口径不符 2 → **0**。⚠️ **`question` 仍不参与检索**（把"随机抽样"换成"文档序"≠ 真检索）⇒ 已登记 `docs/dev-doc-status.md` **R22**，转下一批 |
| **M4** | `specs/m4-affiliation-detection.md` §3 | 7 | 1–7 | S7（1 类算法）、S9（三类 + 四源） | 🟡 **S7.1 批次 A 起始落地**：三类 M4 节点（`:Subject` / `:Address` / `:LegalPerson`）+ 两条边（`LEGAL_REP` / `REGISTERED_AT`，**不与 `:Entity` 桥接**）已入图（§4.2 属性逐字，节点 id 按**规范化名称**稳定化以便跨文档合节点）；两类规则算法（共享法人 / 共享地址）照 spec §5.4 原文落实，证据经 `source_entity_ids` 溯源回 `:Chunk` 原文；`risk.detect` 执行体已登记 `EXECUTOR_REGISTRY`（但在 kg_version 作用域跑，**不是**单文档）。**S7.2 批次 B（2026-09-24）再落地「持久化 + 对外端点」**：三张 PG 表（`affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects`，表名逐字 = PRD §6.2 与 spec §4.3–4.5，三表**均带 `org_id` 且索引以 `org_id` 打头**，ADR-0003）+ 四个端点（`POST /affiliation/detect` / `GET /affiliation/tasks/{id}` / `GET /affiliation/suspicions` / `PATCH /affiliation/suspicions/{id}`，**路径口径以 spec §5.5 的 `suspicions` 为准**，plan §6.2 原写 `suspects` 已同步）。一次检测 = 一条 `affiliation_tasks`，状态机经 `TaskManager` 投递（**先行扩展到「多文档任务」**，决策 B8）并纳入启动回收（ADR-0001 第 73 行要求扫两张表）。**S9.11 / S9.12（2026-09-29）再落地「四源对齐 + 三类算法 + 三方金额不一致」**：四源 schema **先冻结**（spec §4.6）后写确定性摄入器，真机对齐率 **86/90 = 0.9556**、4 行未对齐落 `unaligned_subjects` 且带 `reason`（缺口 **S7.2-1** 偿还）；算法判据**先冻结**（spec §4.7）后写算法，补 `:Phone` / `:Contract` 与 `SHARES_HOLDER` / `PARTY_TO`，**五类算法真机产出 9 条疑点**（法人 1 / 地址 1 / 电话 1 / 环 3 / 金额 3），与语料刻意植入的 9 组**一一对应、误报 0**；`amount_mismatch` 落 `severity=high` + `details` 三方金额明细（契约 +3 枚举、迁移 `9c1b7d2ae4f3`）。**仍未过**：§3 验收 6 场景准入（语料规模远不足）→ **S13**；合同侧仍是合成 `contracts.csv` 替身（缺口 **S9.12-1**，M2 接入 PDF 合同后回归）。**真机**：6 片演示数据 + `v-s71a-fe1c4dc3` → **10 条疑点落库**（与批次 A 一致：共享法人 1 + 共享地址 9），每条 `evidence` 非空（引用覆盖率 100%），`trace_id` 与任务同值，`PATCH` 复核落 `reviewed_by`（当前取 dev 脚手架 `X-Actor-Id`）。**S7.3 批次 C（2026-09-24）前端消费侧落地**：新增 `/affiliation` 疑点页（清单 / 类型 + 状态筛选 / 证据抽屉 / 复核按钮），四端点**全真实消费**（`USE_MOCK=false` 时 Mock 不参与；真机 `total=10`、**证据回查 10/10 成功**）；§3 验收 4 的「可回溯到具体原文」在 UI 侧打通（经 `GET /documents/{id}/chunks/{chunk_id}` 回查原文），§3 验收 7 的 `task_id` 异步查询与结果回传在 UI 侧打通（首个真轮询，2s → 10s 降频）。**仍未达标的部分**：`unaligned_subjects` 只建表不写（写入点随 S9 批次 D 四源对齐）、连通分量 / 环路 / 金额不一致三类算法未做（S9）、§3 验收 1 的 0.95 对齐率未做（S9）、§3 验收 6 的准入指标（召回 / 误报）**未测量**（S13）、**证据粒度是 chunk 级不是提及级**（真机 10/10 `ev_len == chunk_len`）——片段级定位（`char_offset` 恒 0）按 `plan.md:619` 归 **S10**，前端已改淡底 + 标注，**未伪造高亮** |
| **M5** | `specs/m5-permission-audit.md` §3 | 8 | 1–8 | S8（审计页）、S11（RBAC / RLS / 双轨） | 🟡 **S8 批次 A 首次端到端可用**：`audit_log`（§4.4 11 字段）/ `qa_logs`（§4.3 10 字段）两张表落地（均带 `org_id` 且索引 `org_id` 打头；**主键 UUID 而非 spec 的 `BIGSERIAL`**，差异已登记 ADR-0003 §3.1.1）+ 纯 ASGI `AuditMiddleware` 全量写（health 豁免、`detail` 只写结构化字段、写失败只记日志、401 无身份不写）+ 两个只读端点（按租户列表 / 按 trace 查）+ 前端审计页关 Mock（`CONTRACT_COVERED_PATTERNS` **12 → 14**）；**批次 B** 补 §3 验收 5 限流（`RATE_LIMITED` + `Retry-After` + `rate_limit.triggered` 留痕）与逃生阀 `tenant_leak.warn`；**真机**：演示路径走一遍后 `audit_log` **13 条 / 13 个 trace**（条数判据 ≥7 ✅）、`qa_logs` 1 条，浏览器点验审计页 30 条 / 11 类 action。**仍未达标**：RBAC 三粒度、RLS（均 → S11）；**完整脱敏已于 2026-10-08（P5-E）达成**：spec §5.3 的第三个统一组件 `mask(field, category)` 落地（`app/core/masking.py`，八类策略逐字照 §4.5 示例列：合同金额 `***,***.00` / 发票号 `INV2****0001` / 银行账号 `6228 **** **** 1234` / 电话 `138****1234` / 税号·法人·身份证 = SHA-256 + `mask_salt` 64 hex / 文件名 = `documents.hash_filename` 同值），接线到 `audit_log.detail` 写入**之前**与 loguru JSON 出口（patcher）两处，并由单测断言**已落库的 JSON** 与**运行期捕获的日志输出**均无八类原文（CI `pytest` +28 条；契约零漂移、26 路径不变；`check_seams` ERROR 0 / WARN 0 / OK 12）。⚠️ **覆盖边界**：只认登记表收录的 key 名，日志 `message` 正文、第九类字段、未登记 key **照样漏**；**`alert` 表仍缺（spec §3 验收 5 自标 P2）**；**私域开关已于 2026-10-08（P5-D）达成**，不再是 S11 缺口（详见下方 **H6** 行）；§3 验收 6 的「≥7 条**共享同一** `trace_id`」**后端侧 2026-09-26 已真机实测达成**（手工透传同一 `X-Trace-Id` 连走 7 步、含真实 LLM 问答 → `GET /audit/trace/{tid}` 聚合 **7 条**，PG 直读同值）；**演示路径仍未闭合**——前端 `client.ts::request()` 只读不发 `X-Trace-Id`，浏览器自然操作不聚合，且"全站共用同一 trace"与 H4 的 per-request 排障价值冲突 ⇒ 需「演示会话 trace」独立维度 → S11。黄金路径步骤 6 仍 🟡（口径同步见第 67 行 / release notes v1.4.0 §7.1） |
| **M6** | `specs/m6-ontology-incremental.md` §3 | **12** | 3.1–3.5（1–**12**） | S12 | 🟡 **spec 前置已完成**（原写「v0.1 草案」为**过期口径**，2026-10-08 更正：`specs/m6-ontology-incremental.md` 头部为 **v1.0，2026-10-02 定稿**，CP-3 闸门已打开）；**2026-10-07（P5-C）开出实现第一批**：`ontology_schemas` / `ontology_actions` 两表 + 迁移 `3f7c1b90ad24`，`GET /ontology/active` / `POST /ontology/cold-start` / `POST /ontology/confirm` 三端点**真实现**（7 个 501 占位 ⇒ 剩 4 个）。❌ **仍未做**：`merge` / `split` / `rename`（**硬前置** = 须先升 **M2 spec §4.5 加 `applied` 枚举**并走完契约同步五步，见 m6 §4.4）、增量重算（§3.3 验收 6）、`cost_metrics` 表 + `GET /cost/dashboard`（§3.4 验收 8 / 9）、前端校正 GUI。**2026-09-27 追加验收 12**：租户 ↔ 业务域初始化（内置默认 schema / 不阻断 / 不让 LLM 自定类型 / 受 `max_orgs` 约束），落点在 m6 §4.6；同步更正 §7 的"PRD §2 写 P1"**过期口径**（F9 已闭环，PRD 已为 P0） ；**2026-10-08（P5-F）：§3.3 验收 6 / 7 的「增量重算」落地**（`backend/app/services/kg/incremental.py::rebuild_incrementally`）：只把**受影响实体 + 其内部关系**按 `{id, kg_version}` 幂等键 MERGE 到**新**版本（真 Neo4j 前后计数做差 = 校正节点数，**不是**全图节点数；旧版本节点一条不动），新 `kg_versions` 行**复用** `KgVersioningService` 走完状态机且 `source_doc_ids` **只含受影响文档**，`ontology_actions.result_kg_version` 真回填（**PG 读回**）；失败**显式失败**（落 `error_code` / `error_detail`，**不**回落全量重建）。⚠️ **仍缺/不许外推**：merge / split / rename 三端点**仍是占位骨架**（接线归下一批，本批只补前置）；新版本图的**完整性**（未受影响节点不在新版本下，登记 **P5F-4**）待与端点语义同批裁决；成本仪表盘（§3.4 验收 8 / 9，批次 D）未做；`alert` 表（P2）有意不做。**2026-10-08（P5-G）：§3.2 验收 3 / 4 / 5 的 merge / split / rename 三端点接线**（`backend/app/services/kg/correction.py` + `routes/ontology.py`）：三端点由 501 占位转为**真实现**（图操作 → 写 `ontology_actions` → **调 P5-F 的增量重算** → 回 `{kg_version, status: "applied"}`；真 Neo4j 断言节点 / 属性 / 边，真 PG 读回 `result_kg_version` 与候选行 `applied`），并挂 `require_permission`（`test_rbac.py:62` 的 `PROTECTED_ENDPOINTS` **6 ⇒ 9**）；`entity_merge_candidates.status` 真写 `applied` 且与 **M2 spec §4.5 注脚升版同批**（m6 §4.4 第 ① 步）。⚠️ **仍缺 / 不许外推**：**P5F-4 消费侧完整性**按 D9 取最小形态——新版本**仍只承载受影响子图 ∪ 其 1 跳邻居**（P5G-7），已做成**显式断言**（`test_new_version_carries_only_the_corrected_subgraph`）+ 缺口登记，**版本链读侧归后续批次**；新版本 `source_doc_ids` 留空（P5G-2）；split 的关系迁移只取「默认同名」一条规则（P5G-3）；成本仪表盘（批次 D）、前端校正 GUI（另一批）、`alert` 表（P2）**继续不做**。**2026-10-08（P5-H）：**P5F-4 消费侧完整性**已做（**ADR-0008**）—— 新增**版本继承读**（`version_view.py` / `version_scope.py`）：active ∪ 祖先有序版本链沿 `ontology_actions` 反推（限深 16）、同 id 链上最新者胜、被本版本动作删掉者不再继承；三条读路径切换（`fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance`，真图用例各一条：5 节点改名后**仍读到全部 5 个**、推理链从不相关校正中恢复、合规扫描读到未被影响的员工）；概览的边改为**按 id 空间**投影 ⇒ 跨版本边不再丢失。⚠️ **仍缺 / 不许外推**：多跳推理**不**跨版本续接（**P5H-6 已知限制**，见 ADR-0008 §5）；`agents.py` 检索未接视野 ⇒ M4 端到端**仍**按单版本读；`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` / `list_attendance_anomalies` / `explain_attendance_anomaly` / `fetch_document_subgraph` 仍单版本（逐条登记 ADR-0008 §7）；概览三个统计值仍取 PG 落库计数（P5H-4，与继承投影不一致）。**2026-10-08（P5-I0）：GUI 批次的前置修疤** —— 增量版本号由「`<base>-inc-<6hex>`（每级 +11 字符）」改为**定长** `<%Y%m%dT%H%M%SZ>-inc-<8hex>`（恒 29 字符）：`kg_versions.version` 与 `ontology_actions.kg_version` / `result_kg_version` **三列都是 `String(64)`**，典型基线号 25 字符 ⇒ 原写法**连续第 4 次校正必然 500**（PG `value too long`，走不到任何业务错误码）——人手连点 4 次 rename 就会撞到，故必须在 GUI 之前做。含定长判据 + 「旧写法第 4 级 = 69 > 64」看门狗用例；两处测试辅助改为不依赖版本号前缀（P5I0-2）。**同批**：① `backend/app/core/openapi.py` 的 `ontology` tag 描述更正（原文仍写「全部占位 + 只有 confirm 会改本体」，与 P5-G 后的实现矛盾，后一句还会把 GAP-F2 讲反）⇒ 走完契约同步（重导出 + `gen:api` 零变更）；② spec §5.5 端点状态句 + §10.1 新增落地状态表（编号未重排）；③ DR-B6 / DR-B7 由「⏳ 零代码」更正为「✅ 已达成」（原写与 G-9 / G-10 已转正矛盾），保留「PG / CI 必过 / 禁 `local_only`」三条约束。⚠️ **批次 B（GUI）仍未开工**：三端点虽已实装，但**没有 UI 就走不到人工触发**这一环；批次 D（成本仪表盘）未开工（`cost_ratio` 阈值 TBD-7 归 Sprint 13）。**2026-10-09（P5-I）：批次 B「本体校正 GUI」已落地** —— 新增 `GET /api/v1/ontology/candidates`（**绑定 `entity_merge_candidates`**，m6 §1.1 第 2 条：分页 + `status` 过滤，非法值 400、跨租户 ⇒ **空集**；契约路径 **28 ⇒ 29**）+ 前端 `/ontology`（候选表 + merge / split / rename 三动作弹窗 + 回显后端返回的**新 `kg_version`** 并**真的**刷新图谱视图，`GET /graph/overview` 自 P5-H 起按版本继承读）；`PROTECTED_ENDPOINTS` **9 ⇒ 10**、`CONTRACT_COVERED_PATTERNS` **19 ⇒ 23**（漏登记 ⇒ 关 Mock 后**静默走假数据**）。⚠️ **仍缺 / 不许外推**：`GET /ontology/active` / `POST /ontology/confirm` / `POST /ontology/cold-start` **仍占位**（批次 A，本批**未接**它的 LLM 调用）；成本仪表盘（批次 D，TBD-7 未收敛）；剩余读路径与 `agents.py` 检索**仍单版本**（M4 端到端仍未吃到版本继承读）；多跳推理**仍不跨版本**（P5H-6）；`alert` 表（P2）继续不做；UI 上显示的「新版本」只是**回显后端返回值**，**不等于**读侧已完整 |
| **合计** | | **49** | | | |

### 3.2 PRD §5 黄金路径 7 步 → 锚点

| 步骤 | 场景 | 锚点 | 现状 |
|---|---|---|---|
| 1 | 上传合同 PDF + 3 CSV，P95 ≤ 500ms | M1 §3 验收 1 | ✅ |
| 2 | 轮询状态 `pending → processing → completed` | M1 §3 验收 5 | ✅ |
| 3 | Neo4j 写入 + `kg_version` 落 `kg_versions` | M2 §3 验收 4 | ✅ **S5 批次 B 达成**（`kg_versions` 为版本真源，黄金路径 3/7） |
| 4 | M4 命中 ≥ 1 疑点且引用覆盖率 100% | M4 §3 验收 4 + 6 | 🟡 **S7.1 批次 A 首次产出疑点**：6 片演示数据（招商蛇口 / 招商公路募集说明书 + 招商轮船年报，切片）→ 共享版本 `v-s71a-fe1c4dc3` 命中 **10 条**疑点（共享法人 1 + 共享地址 9），每条附 3–6 条 `:Chunk` 原文证据（合计 42 条），**引用覆盖率 = 100%**（实现纪律：取不到证据的命中**直接丢弃**并打 `affiliation_suspicions_dropped_no_evidence` WARNING）。**这不等于通过验收**——数据集既非 spec 的"200 合同 + 500 发票 + 100 凭证 + 20 组植入样本"，召回 / 误报率也**未测量**（H11 / §5.1 仍 ⏳ S13）。**S7.2 批次 B 补上消费侧**：同一批疑点（10 条）落 `affiliation_suspicions` 并经四端点可读、可复核（`open → confirmed / dismissed` 落库），疑点数与批次 A 对齐 = 无重复出条 / 无丢条。**S7.3 批次 C 再补人机界面**：同一批疑点在 `/affiliation` 可见 / 可筛选 / 可开证据抽屉回原文 / 可点复核（浏览器点验落库 `confirmed=4 / dismissed=1`）；⚠️ 证据粒度为 **chunk 级**，提及级高亮归 S10 |
| 5 | M3 提问 → 引用 100% 或拒答 | M3 §3 验收 2 + 3 | 🟡 **引用侧 S6 达成**（chunk 级引用回查，受控问题集 14 问覆盖率 100% / 拒答误伤 0；**2026-09-24 复核口径不变，见 §3.4 M3-2**）；**2026-09-28（S9.5 批次 D1）多跳已落地**：`reasoning_path` 进契约（契约路径 17→19），真机 2 跳链逐跳可回查；**剩余**为终局判据（全量受控问题集上的多跳答对率）→ S10，且受控问题集**未覆盖考勤域**（不得据此声称达标） |
| 6 | 审计 ≥ 7 条且共享同一 `trace_id` | M5 §3 验收 6 | 🟡 **S8 批次 A 部分达成**：`audit_log` 全量落库 + 两个只读端点 + 审计页关 Mock **已达成**（真机 **13 条 / 13 个 trace**，条数侧 ≥7 ✅，浏览器点验审计页 30 条）；「**共享同一** `trace_id` ≥7 条」——**2026-09-26 真机实测（后端侧）达成**：手工透传同一 `X-Trace-Id` 连走 7 步（`documents` → `overview` → `entity` → `document.graph` → `document.status` → `audit.list` → **`agent.query`（真实 LLM，¥）**）→ `GET /api/v1/audit/trace/{tid}` 聚合 **7 条**（`document.list` / `graph.overview` / `graph.entity` / `document.graph` / `document.status` / `audit.list` / `agent.query`），PG 直读 `audit_log` 同值 = 7 ⇒ 判据**后端已实测达成**。**仍 🟡 未闭合**：前端 `frontend/src/api/client.ts::request()` **只读取**响应头 `X-Trace-Id`、**不发送** ⇒ 浏览器自然操作下每请求各生成新 trace，演示路径**不会自然聚合**；且**不宜**改成"全站共用同一 trace"（会让 per-request trace 失去排障价值，与 **H4** 冲突）⇒ 需单独设计「演示会话 trace」维度 → **S11**（详见 release notes v1.4.0 §7.1） |
| 7 | C1–C3 准入线 | §5.1 | ❌ S13 |

### 3.3 M4 §3 验收 1–7 逐条对账（S7 收尾，2026-09-24）

> 本节按 §9.2 第 3 项对 Sprint 7 承接的 M4 §3 验收条**逐条打勾**。未达成的写明承接 Sprint，**不靠叙述糊过去**。

| 验收 | 摘要 | 判据 | 现状 | 承接 |
|---|---|---|---|---|
| **1** | 四源主体对齐，成功率 ≥ 0.95，未对齐主体入 `unaligned_subjects` | 对齐成功率统计 + `unaligned_subjects` 行数 | ✅ **达成（合成语料口径）**：**S9.11 批次 C1** 偿还缺口 S7.2-1——四源 schema 先冻结（spec §4.6）后写确定性摄入器 + 三级对齐器（税号 / 名称 / 地址）；真机 **86 / 90 = 0.9556**（≥ 0.95），命中级别分布 `{tax_id: 79, name: 6, address: 1}` ⇒ 三级**都被用到**，不是只落第一级；4 行未对齐入 `unaligned_subjects` 且带 `reason`（`tax_id_missing` 1 / `name_mismatch` 2 / `multiple_candidates` 1） | 终局判据 **S13**（spec 全量样本） |
| **2** | 建「主体-地址-法人-股东-电话」多类节点，节点带 `kg_version` 且**共用 `status=active` 版本**（ADR-0002 不分裂版本） | 图中节点 label 计数；节点 `kg_version` 与 `kg_versions.status` 比对 | ✅ **达成**：S9.11 / **S9.12** 补齐后落 **五类节点**（`:Subject` / `:Address` / `:LegalPerson` / `:Phone` / `:Contract`，另有 `:Invoice` / `:Voucher`）+ **五类边**（`REGISTERED_AT` / `LEGAL_REP` / `CONTACT_PHONE` / `SHARES_HOLDER` / `PARTY_TO`）；真机 `affiliation-demo-v1` 实体 **176** / 关系 **172**，全部带 `kg_version` 且**共用 active 版本**（跨版本隔离已证：旧版本无 `:Subject`，`detect` 返回 0 条、不串数据） | 保持；版本纪律**持续满足** |
| **3** | 三类算法（连通分量 / 共享邻居 / 环路）任一命中即出疑点，`type ∈ {shared_address, shared_legal_rep, shared_phone, cycle, amount_mismatch}` | 算法族实装 + `suspicion_type` 取值校验 | ✅ **达成**：**S9.12 批次 C2** 落**五类**（规则型 2 + 算法型 3），判据**先冻结**于 spec §4.7 后写算法；真机 **9 条疑点** = 共享法人 1 / 共享地址 1 / 共享电话 1 / 持股环 3（`cycle_length` 2 / 3 / 4）/ 金额不一致 3，与语料刻意植入的 **9 组一一对应、误报 0**；`suspicion_type` 取值全部在 spec 枚举内 | 终局判据 **S13**（spec 全量样本） |
| **4** | 每条疑点可回溯 ≥ 1 具体原文，**引用覆盖率 = 100%**，不允许「无原文证据」的疑点 | 含证据疑点数 / 总疑点数；反证 F3 | ✅ **达成（演示数据集口径）**：**10 / 10** 疑点含 3–6 条 `:Chunk` 证据（合计 42 条）= **100%**；取不到证据的命中**直接丢弃**并打 `affiliation_suspicions_dropped_no_evidence` WARNING；UI 侧可点开原文（**证据粒度为 chunk 级**，提及级定位归 S10） | 终局判据 **S13**（spec 全量样本） |
| **5** | 三方金额不一致 → `amount_mismatch` 疑点，`severity=high` | 构造合同 / 发票 / 凭证三方金额不等 | ✅ **达成**：**S9.12** 真机 3 条（TR-0002 凭证少 4500 / TR-0003 合同多 24000 / TR-0004 发票多 4000），**`severity=high`**，且 `details` 给出「交易号 + 三方各自金额 + 最大差额」（spec §3 验收 5 要求的明细形状）；**判据**：同一 `trade_ref` 三方**不齐 ⇒ 不产出**（不许拿两方凑一条）。⚠️ 偏离登记：语料的 `contracts.csv` 是 **PDF 合同的合成替身**（spec §4.6.6），真机合同仍须走 M2 抽取后回归 | 缺口 **S9.12-1**（M2 接入合同后回归） |
| **6** | 场景准入：200 合同 + 500 发票 + 100 凭证 + 20 组植入 → 召回 ≥ 0.80、误报 ≤ 0.15、覆盖率 = 100% | 评测脚本（**待建**） | ❌ **未测量**：现有语料只有 8 合同 / 60 发票 / 30 凭证 / **9 组**植入，**规模远不足** spec 样本；评测脚本未建。**不拿 9/9 冒充召回率**——植入 9 组全中只能说明"判据实现正确"，不能外推到召回 ≥ 0.80 | **S13**（缺口号同此行） |
| **7** | 提交 → 异步执行返回 `task_id` → `GET /tasks/{id}` 查结果 → 结果含 `affiliation_suspicions` 列表 + 回溯引用 → 重启回收置 `failed`（`error_code = TASK_INTERRUPTED`） | 四端点联调（关 Mock）+ 重启回收用例 | ✅ **达成**：四端点已进契约并可关 Mock 消费（`USE_MOCK=false` 时 Mock 不参与）；一次检测 = 一条 `affiliation_tasks`，经 `TaskManager` 双载体投递并纳入 `recover_orphan_tasks()` 启动回收（ADR-0001 第 73 行要求扫两张表）；复用 `TASK_INTERRUPTED`。**残留**：`list_in_flight_task_ids()` 仍只扫 `documents`（缺口 **S7.2-2**） | 保持；S7.2-2 → **S8** |

**对账结论（不伪装，2026-09-29 S9.12 收尾重写）**：7 条中 **6 条达成**（验收 1 / 2 / 3 / 4 / 5 / 7）、**1 条未做**（验收 **6** 场景准入）。

- 验收 1 / 2 由 **S9.11 批次 C1** 偿还（四源对齐 0.9556、五类节点与五类边入图）；
- 验收 3 / 5 由 **S9.12 批次 C2** 偿还（五类算法 + 三方金额不一致，真机 9 条、误报 0）；
- **M4 仍未通过 §3 验收 6**：召回 / 误报**未测量**，语料规模远不足且评测脚本未建 → **S13**。
  本节原写「3 条未做（1 / 5 / 6）」属**过期口径**，已按真机结果更正；证据
  `changes/archive/2026-09-29-Sprint9.11/integration-log.md` 与 `changes/archive/2026-09-29-Sprint9.12/integration-log.md`。
  另见 release notes v1.3.0 §6.7 与 §5.1（C1 / C2 仍 ⏳ S13）。

### 3.4 M2 / M3 §3 验收 1–7 逐条对账（**S6 收尾补做，2026-09-24**）

> **为什么会有这一节**：§9.2 第 3 项要求每个 Sprint 收尾对本 Sprint 承接的 spec 验收条逐条打勾，但 **S6（v1.2.0）收尾当时未执行**——事实登记见 `docs/dev-doc-status.md` P2-3 的 2026-09-23 备注。本节为**历史补做**，三点规矩先讲清：
>
> 1. **核实日期统一为 2026-09-24，不冒充 2026-09-23 的当日结论**。两者虽只差一天，中间已经过 Sprint 7.0 的抽取链路改造，行为**可能**已漂移；
> 2. **判据 = 当时日志 + 现在代码**：证据取自 `changes/archive/2026-09-23-Sprint6.{1,2,3,4}/integration-log.md`，但每条都**回到 2026-09-24 的当前代码复核**，不只抄当时的结论；
> 3. ❌ / 🟡 一律写明承接，**不替 Sprint 排期做决定**——排不进的写「未排期」，不造一个假 Sprint 出来。

| 验收 | 摘要 | 判据 / 证据 | 2026-09-24 补做核实 | 承接 |
|---|---|---|---|---|
| **M2-1** | MinerU 结构化解析 **P95 ≤ 30s / 100 页**、**表格字段还原准确率 ≥ 0.85**（50 份样本） | 时延分位数统计 + 50 份样本还原率评测 | ❌ **未做**：S6 只有**单次**真机成功（`complex_table.pdf` → markdown 1358 bytes；`content_list` **v1 扁平结构 10/10 对齐**、云 API **v2 嵌套结构**判出 `page=1`），**无 P95 统计、无 50 份样本**（S6.1 §2 / §3） | **未排期**（属 A3 解析质量实测，建议随 S10 解析层一并处理） |
| **M2-2** | 三元组输出 `{entity, relation, evidence_span, confidence}`，`confidence` 落 Neo4j，`evidence_span` 含 `doc_id + chunk_id + char_offset + text` | Neo4j 节点 / 关系属性 + 契约 `Citation` 字段 | 🟡 **部分达成**：`confidence` **确已落库**——`kg/builder.py:322-330` 写实体 `n.confidence`、`:342` 写关系 `rel.confidence`，取值来自抽取侧且遵守「`< 0.5` 丢弃、超限按降序裁剪、**缺值不猜**」（`extraction/langextract.py:_MIN_CONFIDENCE` / `_coerce_confidence`）；`doc_id` / `text` / 区间**已落**（`:Chunk {char_start, char_end, page, text}` + `(d)-[:HAS_CHUNK]->(c)`）。**缺**：`char_offset` 停在 **chunk 级**——`Citation.char_offset` 恒 0，提及级定位未做（S6.4 §5） | S9 / S10（实体级 `char_offset`） |
| **M2-3** | 实体消解（≥ 0.90 自动合并 / 0.70–0.90 进人工队列 / < 0.70 保持独立） | 合并候选取值 + `entity_merge_candidates.status` | ✅ **达成（2026-09-29，S9.13 批次 C3）**：候选表 `entity_merge_candidates` 已建（迁移 `b3e5a1c70d42`），判据冻结于 `specs/m2` §4.5.1 后写消解器（纯函数、零 LLM）；真机 **5 条候选** = `auto_merged` **1**（`name_sim=0.94`、无税号冲突、唯一候选）+ `human_review` **4**（N1 税号冲突封顶 0.85 × 2、N2 多候选降级 × 2），**误并 0**（脚本内置机械判据：任何 `SUBJECT↔SUBJECT` 的 `auto_merged` ⇒ 退出码 1）。**范围限制如实登记**：① 消解跑在 **`:Subject` 主体层**（id = `SUBJECT:<税号>` 稳定），**`:Entity` 通用层未做**——`ent_<uuid>` 每次抽取都变 ⇒ 同一公司两个节点，无从配对（**S9.13-2**）；② `human_review` **无读端点**（同 S9.11 裁决 D-B）；③ 合并发生在**摄入时**，已入图的历史节点不做事后物理合并 | 保持（**S9.13-2**：通用层消解 + 人工队列读端点） |
| **M2-4** | `kg_version` 版本化写入、**先 PG 后 Neo4j**、MERGE 幂等、历史版本不删 | 写入顺序 + `kg_versions` 记录 + 幂等键 | ✅ **达成（S5 实现，S6 加固）**：三段式写入 + `kg_versions` 字段完整；幂等键 `(id, kg_version)` ⚠️ **社区版无 `IS NODE KEY`，降级为 `IS UNIQUE`**（S6.1 §4.1，**未隐瞒**）。S6.3 定 **PG 为真源**（`ready` ≡ `active` 语义）并新增在线激活端点 `POST /graph/versions/{version}/activate`，此前**只能人工改库**（S6.3 §2.1 实测 200 + `superseded_versions`） | 版本纪律持续满足；⚠️ S6.1 §4.3 上报的「**在线链路不自串联**」（上传后 extract / kg.build 不自动触发）本次**未验证是否已闭合** |
| **M2-5** | tenacity 指数退避 ≤ 3 次（初始 1s、倍数 2），失败置 `failed` + `error_code` 落库 | 重试次数断言 + 库表回写 | ✅ **达成（S5 批次 A 闭环）**：H8 两项缺陷已关闭；S6 四批次的 integration-log **均未涉及重试链路改动**，无回归面 | 保持 |
| **M2-6** | 抽取完成且 `kg_version` 落库后**投递索引更新事件**，M3 / M4 可立即消费 | 写图后的事件 publish 调用 | ❌ **未做**：`EventBus` 的唯一使用点在 `services/affiliation.py`（**S7.4 批次 D**），`services/kg/` 下**零 publish**；当前靠调用方**显式调激活端点**衔接，不是事件驱动 | **未排期**（接缝 5 出口已于 S7.4 就位，M2 侧写入点待安排） |
| **M2-7** | `trace_id` 全链路 + token 用量 / 耗时打点（成本仪表盘 C3） | 日志 + 响应 `token_usage` + 成本聚合表 | 🟡 **部分达成**：`trace_id` ✅（`core/middleware.py` 回显并贯穿，写图各 stage 落 `trace_id`）；token 用量 ✅ 真机返回（`prompt 1733 / completion 66 / total 1799`，S6.2 §3.1）。**缺**：`C3` 聚合未建——无成本表，`models.py` 现七张表里没有它 | C3-a / C3-b → **S13** |
| **M3-1** | **≥ 3 跳**遍历 + 每跳 `kg_version` 过滤 + 单次节点数 ≤ 500 | Cypher 是否含变长路径；`node_limit` 默认值 | 🟡 **部分达成**：版本过滤 ✅（两个查询均带 `kg_version` 约束，且经 PG 真源取 active 版本）；节点上限 ✅（默认 `node_limit = 500` + `truncated`，`graphs.py:634 / 694`）。**2026-09-28（S9.5 批次 D1）≥ 3 跳已落地**——原判据「`graphs.py` 全文无变长路径模式」已**过期**：新增 `services/reasoning.py`，走 `:RELATION*1..3` 变长查询（**端点与关系均**带 `kg_version` / `org_id` 约束），流程为「问句定位锚点（只认 `NAMESPACE:ID` 形态的确定性派生节点）→ 变长遍历 → 按『终点解释力 → 跳数 → id 字典序』取唯一链（确定性同解）」，结果经 `reasoning_path` 出契约（拒答 `null` / 零命中 `[]`，二者语义相反）。**真机**：`attendance-demo-v1` 上「李静的月加班超过上限了吗？」⇒ `EMPLOYEE:E002 →HAS_ATTENDANCE→ ATTENDANCE_RECORD:A00023 →OCCURRED_ON→ SHIFT:S00023`（2 跳，逐跳可回查）。⚠️ **仍不是终局达标**：终局判据是**全量受控问题集**上的多跳答对率，而受控问题集**尚未覆盖考勤域** ⇒ 不得据本条声称 S10 达成。**2026-09-30（S10.1）**：多跳查询**已域无关化**（不再硬编码考勤类型），真机 2 跳链同上逐跳可回查；**终局判据（多跳答对率 ≥ 0.80）仍未测**——受控问题集未覆盖考勤域 + 需 PG + LLM ⇒ 随 `kg_qa_v4` 端到端补验一并做 | **S11**（终局判据） |
| **M3-2** | 引用覆盖率 = **100%**（无溯源即拒答，F3） | 含可回溯证据的答案数 / 总答案数 | ✅ **达成（受控问题集口径）**：S6.4 §6 真机 14 问 → 非拒答 12、引用命中 **12** = **100%**，拒答误伤 0（`scripts/eval_controlled_qset.py`）。**2026-09-24 复核仍成立**：`agents.py:350-352` 的 `_build_citations` 只认本轮注入的 chunk id，回查不到**直接丢弃** | 终局判据 **S10**（多跳 + 全量问题集） |
| **M3-3** | 拒答出口返回契约体，**M5 写 `qa.refused` 审计** | 响应体结构 + 审计落库 | 🟡 **部分达成**：拒答**唯一出口** `_refuse`（`agents.py:480-509`）返回 `answer="无法回答"` / `refused=true` / `refusal_reason` / `confidence="low"`，14 问中的 2 道库外题**全部正确拒答、无误伤**。**缺（2026-09-26 刷新）**：`qa_logs` 表（spec §4.3）**S8 批次 A 已建并已写**（成功 / 拒答都落，`question_hash` / `answer_hash` 为 SHA-256 不存原文，真机 1 条）；但 `audit_log` 侧**无 `qa.refused` action**——审计 `action` 走路由映射（`http.<method>.<path>`），拒答事实只体现在 `qa_logs.refused` / `refusal_reason` 列 ⇒ 该条**仍记为部分达成** | `qa.refused` 审计 action → S11（M5 三粒度落地时统一）；`qa_logs` **已闭合** |
| **M3-4** | `scope=single_doc` 严格隔离，`citations` 仅含该文档 | 单 / 跨文档各一例 | ✅ **达成**：`agents.py:441-445` 按 scope 分流；取证据时 `doc_id is not None` → `_QUERY_EVIDENCE_CHUNKS_BY_DOCUMENT`（`graphs.py:782-784`，受 `doc_id + kg_version` **双重约束**），`cross_doc` 才走「按实体回查」 | 保持 |
| **M3-5** | 意图路由到 M4 → `route = "m4_affiliation"` + 携带 M4 `task_id` | 响应 `route` 取值 + 路由调用点 | ❌ **未做**：`route` 在两个出口**恒为 `"m3_graphqa"`**（`agents.py:378 / 506`），无 `intent_router` 调用。S7 的 M4 疑点链路走**独立页面 + 独立端点**（`POST /affiliation/detect`），**未接回 M3 路由** | **未排期** |
| **M3-6** | 输出置信度评级 `high / medium / low`，`low` 在 UI 标记「建议人工复核」 | 响应 `confidence` + 前端标记 | ✅ **达成**：`QueryConfidence` 三值（拒答固定 `low`）；前端 `chat-message-item.tsx:50-52` 对 `confidence === "low"` 打「**低置信度**」徽标。⚠️ **字面差异**：UI 文案是「低置信度」而非 spec 原文「建议人工复核」——语义一致、措辞不同，**登记不修改** | 保持 |
| **M3-7** | `trace_id` + 「问题 → 答案 → 引用条数 → 拒答原因」完整链路打点 | `qa_logs` 落库 | 🟡 **部分达成**：`trace_id` ✅（同 M2-7 / H4）；「引用条数 / 拒答原因」**在响应体内** ✅。~~**缺**：`qa_logs`（`question_hash` / `answer_hash` / `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id`）**表未建**，无持久化打点~~ → ⚠️ **2026-10-01 更正（本行原为过期口径）**：`qa_logs` **已于 2026-09-26（S8 批次 A）建表并写入**，上述列均已落，真机累计 **16 行**（与本节 M3-3、H4 行口径一致）⇒ **M3 验收 7 的「打点」已达成**，**不再记为部分达成** | ✅ **已闭合**（原「未排期」结论作废） |

**对账结论（不伪装）**：

- **M2**：7 条中 **3 条达成**（验收 3 / 4 / 5）、**2 条部分达成**（验收 2 / 7）、**2 条未做**（验收 1 / 6）
  —— **验收 3（实体消解）由 2026-09-29 的 S9.13 批次 C3 偿还**（本行原写「3 条达成 4/5 + 未做 3」属过期口径，已更正）；
- **M3**：7 条中 **3 条达成**（验收 2 / 4 / 6）、**2 条部分达成**（验收 3 / 7）、**2 条未做**（验收 1 / 5）；
- **合计 14 条：6 达成 / 4 部分 / 4 未做**。

**本次补做的实质发现（口径更正）**：多个文档（本矩阵 §3.1 M2 行、`plan.md` §15.3 M2 行、`specs/m2` 状态行）长期写着「M2 **`confidence` 不落库**」——**2026-09-24 复核为错误**：`confidence` 已随 v1.2.0 写入 Neo4j 的节点与关系属性，且带完整取值纪律（丢弃、裁剪、不猜值）。三处已按更正后口径重写，**理由留在本节以备反查**，避免下次有人照旧口径又改回去。

~~**另一条要记住的**：`qa_logs` 从未建表（M3 §4.3），因此 M3 验收 3 / 7 的「打点」**今天也不成立**——这不是 S6 留下的债，而是它当时就依赖一个尚未落地的东西。~~
⚠️ **2026-10-01 更正（本行原结论已过期，作废）**：`qa_logs` **已于 2026-09-26（S8 批次 A）建表并写入**，真机累计 **16 行** ⇒ M3 验收 3 / 7 的「打点」**现已成立**。**保留删除线仅为留痕**（守 R5 不篡改历史结论），**现行口径以更正后内容为准**。

### 3.5 知识时效（M2 §3 验收 8–10）→ 判据（**2026-09-27 登记，ADR-0005**）

> **为什么单列一节**：时效不是新模块（没有 `specs/m7`），而是**跨 M2 / M3 / M4 的横切能力**。
> 按 §7 第 1 条"写不出锚点 = 无人承接"，它必须有落点 ⇒ 落在 **M2 §3 验收 8 / 9 / 10**（已追加，未重排）。
> 决策依据 [`docs/adr/ADR-0005`](./adr/ADR-0005-temporal-knowledge-model.md)；PoC 证据 `temporal_poc/README.md`。

| 验收 | 摘要 | 判据类型 | 判据 / 命令 | 验收人 | 现状 | 承接 |
|---|---|---|---|---|---|---|
| **8** | `Document.document_date` 解析并落库，取不到置 `NULL`（**禁止猜测**） | 机械 | 单测：有签署日 → 落值；无 → `NULL`；**不得**由文件名 / 内容推断 | CI | ⏳ | **S9 批次 A/B** |
| **9** | 关系带 `valid_from` / `valid_to` / `created_at` / `expired_at` / `source_document_id`；`valid_from` 覆盖率 ≥ **0.90**；无显式日期取 `document_date`、`valid_to` 留 `NULL` | 半机械 | `temporal_poc/run_track_s.py` 迁入 `backend/tests/`；统计 `valid_from` 非空比例（**PoC 实测基线 1.00**） | 后端 B | ⏳ | **S9 批次 B/C** |
| **10** | 仲裁 R1–R4：旧事实 `valid_to` 被封**且仍可查**；「当前有效」查询**返回且仅返回一条**；同批次边**互不失效** | 机械 | 同一判据脚本 **n ≥ 3 要求 3/3**（当前值正确 + as-of 回溯正确 + 历史保留）；**去空格归一**后判分 | CI | ⏳ | **S9 批次 C**（闸门 **CP-T2**） |
| **11** | **L2-① 多跳路径时序一致性**：一条链上的各跳必须**存在共同成立时点**（`max(valid_from) ≤ min(valid_to)`，`valid_to` 空 ⇒ 未失效）；任一跳缺 `valid_from` ⇒ **`unknown`**，**不得并进**自洽（那等于默认"没日期 = 永远有效"）；同等终点与跳数下优先选自洽的链，**但优先级排在跳数之后**（不许为自洽挑更长的链） | 机械 | 单测 `backend/tests/test_reasoning_temporal.py`（三值语义 5 例 + 选链优先级 3 例）；¥0 真机 `changes/Sprint10.4/probe_l2_path_temporal.py`（抽 4000 条 2 跳链统计三值分布，实算 **consistent 1424 / unknown 2576 / inconsistent 0**） | CI | ✅ **2026-09-30 Sprint 10.4 交付** | 判据 `app/services/reasoning.py::_temporal_verdict` |
| **12** | **L2-② 页面「失效」视觉语义**：`valid_to` / `expired_at` 非空的边在图上应以虚线 + 置灰呈现，并可查看失效日期 | 半机械 | 前端 Storybook / 真机截图（需图上**真实存在**失效边） | 前端 A | ❌ **未交付** | **下一批**。实测卡点：演示库 `valid_to` 非空 **0 条**（同 §11 命令可复算）⇒ **无对象可画**，且此刻实现无法端到端验证。详见 `dev-doc-status.md` **R24** |
| **13** | **L2-③ 全生命周期 As-of 演示**：稳态样本 n=3，并覆盖「增 / 删 / 变更」三类事实变更，全部可 as-of 回溯到任一历史时点 | 半机械 | 判据脚本 **n ≥ 3 要求 3/3**（当前值正确 + 历史时点值正确 + 变更不丢历史） | 演示执行人 | ❌ **未交付** | **下一批**。前置：**同一主题的两份不同日期文档**（如 2025 版 + 2026 版制度）语料 + 付费重跑抽取 ⇒ 否则"失效""变更"都无从产生，见 **R24** |

> **判分口径坑（已踩）**：模型对「陆家嘴环路 500 号」是否带空格不稳定，
> 判分前**必须去空格归一**，否则会把"答对"误判成"答错"。
>
> **L2 补充项（S10，2026-09-30 于 Sprint 10.4 落地）**：路径时序一致性 + 页面「失效」视觉语义
> + 全生命周期 As-of 演示 ⇒ 已**追加**编号 **11 / 12 / 13**，不重排。
> **现状**：11 ✅（判据 + 选链 + 单测 + ¥0 真机探针）；12 / 13 ❌ —— 二者都依赖「图上真有失效边」，
> 而演示库 `valid_to` 为 0 条。若将来补了「同一主题的两份不同日期文档」语料并重跑抽取，
> **先重跑 §11 的探针确认 `inconsistent` 由 0 变非零**，再做 12 / 13 —— 顺序反了就是拿不可验证的东西假装验收通过。

### 3.6 租户隔离测试 **T1 / T2**（**2026-10-01 登记，ADR-0003 §4.1**）

> 登记目的：切 PostgreSQL 前**两类均为缺口**。二者**必须在 PG 上跑**（SQLite 无 RLS，在其上跑无意义），纳入 CI 必过项，**禁止**标 `local_only` 绕过（否则"看着绿、其实没跑"）。

| # | 用例 | 断言 | 缺口后果 |
|---|---|---|---|
| **T1** | **跨 org 越权**：以 A org 身份查询 / 读取 B org 的资源。**PG 侧**：`documents`、`audit_log`、`qa_logs`、存储 `storage_key`；**图谱侧（2026-10-01 补入，见需求基线 DR-B11）**：跨 org 子图查询 / Cypher 直读 | 返回**空**或 `403`（**图谱侧为 `403 KG_TENANT_LEAK`**）；**不得**返回 B 的数据 | 隔离只是纸面。⚠️ **图谱侧（Neo4j）无 RLS 可依赖**，应用层校验是**唯一**防线；CI 无 Neo4j ⇒ 图谱侧用例为**集成测试**，须独立环境留证，**不得**声称已由 CI 验证 |
| **T2** | **并发串租户**：多线程 / 多协程**同时**以不同 `org_id` 发起请求，**必须覆盖连接池复用路径** | 每个请求**只**看到自己 org 的数据；**不得**串号 | `SET LOCAL` 误写成 `SET`、或连接泄漏 ⇒ **A 公司看到 B 公司的考勤 / 薪酬** |

**T2 为何单独列出**：RLS + 连接池是 ADR-0003 **唯一可能产出「静默跨租户泄露」**的组合——它在**单 org、串行**测试里永远测不出来，只在真实并发下暴露。**T2 不落地 ⇒ ADR-0003 §3.2 的三前提不可宣称已守。**

---

## 4. H1–H16 硬约束 → 验收锚点 → 判据（**本矩阵核心**）

| # | 约束（摘要，全文见 PRD §4） | 锚点 | 判据类型 | 判据 / 命令 | 验收人 | 现状 |
|---|---|---|---|---|---|---|
| **H1** | 异步任务状态机 `pending → processing → completed / failed` | M1 §3 验收 1 / 5；M1 §3 验收 8（启动回收 → `TASK_INTERRUPTED`）；**M4 §3 验收 7** | 机械 | 集成测试断言 `status` 仅在四值内 + 重启回收用例；契约 `documents.status` 枚举 | CI | ✅ M1 侧；✅ **M4 侧（S7 达成）**：`affiliation_tasks.status` 四值内、经 `TaskManager` 双载体投递并纳入 `recover_orphan_tasks()` 启动回收（置 `failed` / `error_code = TASK_INTERRUPTED`）。**残留**：`list_in_flight_task_ids()` 仍只扫 `documents`（缺口 **S7.2-2** → S8） |
| **H2** | 上传 ≤ 100MB + MIME 白名单（pdf/docx/csv） | M1 §3 验收 2 / 3 | 机械 | 集成测试各 1 例：超限 → 413 `FILE_TOO_LARGE`；非白名单 → 415 `UNSUPPORTED_MEDIA_TYPE` 且不落存储 | CI | ✅（docx 解析 S10） |
| **H3** | 错误响应统一 `{code, message, detail, trace_id}` | M1 §3 验收 2 / 3；M5 §3 验收 1；M3 §3 验收 3 | 机械 | 契约 `ErrorResponse` schema + 各错误分支响应体断言 | CI | 🟡 M1 侧已统一；**M4 侧已统一**（新增 `AFFILIATION_TASK_NOT_FOUND` / `AFFILIATION_SUSPICION_NOT_FOUND` 两个 404 均走统一 `ErrorResponse`；跨租户 **403 而非 404**）；M3 / M5 侧随模块落地 |
| **H4** | loguru JSON 日志 + `trace_id` 全链路 | M1 §3 验收 7；**M2 §3 验收 7**；M5 §3 验收 6；**M6 §3 验收 10** | 半机械 | 断言响应头 `X-Trace-Id` 回显且与 `detail.trace_id` 一致；E2E 断言同一 `trace_id` 贯穿 M1→M5 | 后端 B | ✅ **S5 已收口**：`_refuse()` 出口 `trace_id` 已补，原「已知缺陷」关闭；**M4 侧已贯穿**（`POST detect` 的 `trace_id` 与 `affiliation_tasks.trace_id` / `domain_events.trace_id` 同值，真机复核一致）；**M2 / M3 侧 2026-09-24 补做核实**：M2 §3 验收 7 已达「日志 + 响应 `token_usage`」、`trace_id` 由 `core/middleware.py` 回显并贯穿写图各 stage（缺 C3 聚合，见 §3.4 M2-7）；M3 响应体 `trace_id` ✅；**`qa_logs` 打点 2026-09-26 真机核实已落**（真实 LLM 问答后新增 1 行：`refused=0`、`trace_id` 与响应同值，表内累计 **16** 行——原「未落」为过期口径，已更正）；M6 侧 ⏳ S12 |
| **H5** | 敏感字段脱敏（金额 / 发票号 / 税号 / 法人 / 银行 / 身份证 / 电话 / 文件名） | **M5 §3 验收 3 + §4.5** | 机械 | 单元测试断言日志与响应中**无原文**；`filename_hash` 替代原文 | 后端 B | ✅ **2026-10-08（P5-E）达成**：spec §5.3 的统一脱敏工具 `mask(field, category)` 已实现（`backend/app/core/masking.py`，八类策略逐字照 §4.5 示例列）；两处接线 = `audit.py::record_audit_entry` 写 `detail` **之前** + `core/logging.py` 的 loguru patcher；判据是**机械的**——断言**已落库的 `audit_log.detail` JSON** 与**运行期捕获的 loguru JSON 输出**均无八类原文（不是断言函数返回值，避 R-9 恒绿）。⚠️ **仍缺/不许外推**：日志 `message` 正文、第九类字段、登记表未收录的 key **不在覆盖内**；`alert` 表（P2）仍缺。**M4 侧**：`:LegalPerson.id_hash` 在无统一社会信用代码时**为 `null`**（严禁兜底造哈希），节点属性逐字照 spec §4.2 |
| **H6** | 私域部署禁云外发（`PRIVATE_DEPLOY_ENABLED=true`） | M5 §3 验收 4 | 机械 | 单元测试断言外发被拦截（503 `PRIVATE_DEPLOY_BLOCKED`） | 后端 B + 架构师 | ⏳ S11。**当前为占位**，例外登记见 `docs/adr/0004-integration-seams.md` §3。 **2026-10-08（P5-D）更正 → ✅ 已达成**：两个配置项逐字照 spec §4.6 落地（`PRIVATE_DEPLOY_ENABLED` / `ALLOWED_EGRESS_HOSTS`，均有真实消费者，`check_seams.py` 判据 2 已登记）+ **构造期**出向守卫 `app/core/egress.py`（挂在 LLM / MinerU / 评测 embedding 三处客户端**构造之前**，而非发出之后）+ 503 `PRIVATE_DEPLOY_BLOCKED` + `audit_log(action=private_deploy.violation, status=failure)`；内网 / 回环**天然放行**（本地 embedding `127.0.0.1:8009` 不被自己的守卫误杀）。证据：`changes/P5-D/integration-log.md` §6（CI run `37627112419` 四 job 全绿，pytest **1066 passed / 5 skipped / 0 failed**）+ 真机 psql 直读 violation 行（`org_id` 为回落值，见该 log §4.3 的 X-3 偏离）。⚠️ **仍未做**：`alert` 表与限流超阈值联动 —— spec §3 验收 5 自标 **P2**，有意不做 |
| **H7** | slowapi 限流（默认 60 req/min/IP） | M5 §3 验收 5 | 机械 | 集成测试连打超阈值 → 429 `RATE_LIMITED` | CI | ✅ **S8 批次 B 已收口**：`core/limiter.py`（`rate_limit_per_minute` 默认 60）+ **自写纯 ASGI `RateLimitMiddleware`**（实测 FastAPI 0.141 的 `_IncludedRouter` 会让 slowapi 自带中间件**静默失效**，handler 恒 None ⇒ 全部请求被豁免）；`/health` 豁免；429 统一走 `AppError(RATE_LIMITED).to_body(trace_id)` + `Retry-After: 60` 并写 `audit_log(rate_limit.triggered)`。**真机**：`RATE_LIMIT_PER_MINUTE=3` → 限内 3 次 200、第 4/5 次 **429**，`/health` 全 200，`dev.db` 直读 `rate_limit.triggered` 2 行 |
| **H8** | tenacity 指数退避 ≤ 3 次（初始 1s、倍数 2） | M1 §3 验收 4；M2 §3 验收 5 | 半机械 | 注入失败后断言重试次数 = 3 且 `error_code` / `error_detail` 落库；M2 侧断言 `retry_count` 写回 | 后端 B + 架构师 | ✅ **S5 批次 A 已收口**：B1（`retry_count` 回写）+ B4（退避 `exp_base` 读配置）两项缺陷均关闭，`task_retry_multiplier` 现为**有消费者的配置**。**2026-09-24 补做核实（S6 侧）**：S6 四批次**均未改动**重试链路，两项缺陷保持关闭（见 §3.4 M2-5） |
| **H9** | Prompt 版本管理（MVP 复用 5 个 v1，P2 才新增版本） | 各 spec §"关联 Prompts" | 机械 | `prompts/` 5 份文件名带版本号；`prompt_loader.py` 加载，**代码内无硬编码 Prompt** | 架构师 | ✅ 5 个 v1 就位（S9–S13 不新增版本，plan §19.1 A）；**S6 新增 1 份 `prompts/kg_qa_v2.md`**（引用口径收窄为"只能取已注入的 `chunk-<id>`"）——按 Prompt 版本管理规范**新增版本、不覆盖 v1**，符合本条判据；`dev-doc-status.md` §5「S9~S13 复用 v1」口径**不受影响**（v2 在 S6 引入）；**S7.1 批次 A 再新增 1 份 `prompts/kg_extraction_v2.md`**（枚举参数化为 `{{entity_types}}` / `{{relation_types}}`，扩 `LEGAL_PERSON` / `ADDRESS` 与 `LEGAL_REP` / `REGISTERED_AT`，供 M4 共享法人 / 共享地址疑点；`kg_extraction_v1.md` 文件**未被修改**，单测 `test_v1_template_is_untouched` 守着），`dev-doc-status.md` §5 已同步 |
| **H10** | 契约先行 | 各 spec §"API 端点草案" + `contracts/openapi.yaml` | 机械 | `backend/`：`uv run python scripts/export_openapi.py --check`；`frontend/`：`npm run gen:api` 后 `git diff --exit-code -- frontend/src/types/api.d.ts` | CI（`contract` job） | ✅ 门禁在跑；**S7 批次 C / D 各跑一次 `gen:api` 均零 diff**；bump 1.3.0 连带重导契约（`info.version` 取自 `app_version`，不同步则必红）后仍零漂移 |
| **H11** | 准入线 C1–C3 | M4 §3 验收 6；M3 §3 验收 2 | 机械 + 人工 | 见 §5.1 | 架构师 + 用户 | ⏳ S13（评测脚本**待建**） |
| **H12** | 反证 F3 引用覆盖率 < 100% → **直接 NO-GO** | M3 §3 验收 2；M4 §3 验收 4 | 机械 + 人工 | 脚本统计"含可回溯 span 的答案数 / 总答案数"，**必须 = 1.00**；受控问题集人工复核 | 架构师 | 🟡 **S6 首次达标（F3 未触发）**：受控问题集 14 问，引用覆盖率 **100%**、拒答误伤 **0**（`scripts/eval_controlled_qset.py`）。**终局判据仍属 S10**——多跳 ≥3 跳 + 全量问题集；本轮为**演示剧本口径**（单份真机文档），不等同全量召回指标，已按 G5 在 release notes v1.2.0 §6.4 显式声明。**M4 侧首次达标（F3 未触发）**：**10 / 10** 疑点含可回溯 `:Chunk` 证据（合计 42 条，覆盖率 100%，见 §3.3 验收 4）；数据集为 6 片年报切片，**终局仍待 S13 全量样本**，已在 release notes v1.3.0 §6.7 声明 |
| **H13** | **License 每请求校验**：四维度（租户数 / 席位数 / 功能模块 / 有效期）组合校验，超限按分级拒绝，**拒绝必落审计** | **全局中间件**（横向，无模块 spec）→ [`ADR-0006`](./adr/ADR-0006-license-control.md) §2.4 / §2.5 / §2.6 | 机械 | ① 移除 license 文件 → 受保护端点 403 `LICENSE_MISSING`（仅 `/health` 与 `/license/status` 可访问）；② 过期 → 宽限期只读、超期 403 `LICENSE_EXPIRED`；③ 模块未授权 → 403 `LICENSE_MODULE_DISABLED`；④ 席位超限 → 拒绝新建 / 启用用户且已有用户只读可用；⑤ 每次拒绝落 `audit_log`（`license.denied`）；⑥ 每请求校验的 P95 增量 **< 1ms** | CI + 后端 B | ⏳ **零代码**（2026-09-27 登记）→ **`delivery-plan.md` P4**（DR-C1）；**护栏 G-23 骨架已就位**（xfail 挂起）。**原 S11 编号已废** |
| **H14** | **离线可交付**：可离线安装、可备份恢复、可版本升级（含数据库迁移） | [`docs/deployment-spec.md`](./deployment-spec.md) §4 / §6 / §7 | 半机械 | 安装验收清单 10 项逐条（compose healthy / license active / 上传建图 / 问答溯源 / 审计 ≥7 条 / 租户隔离 / 备份 manifest / **恢复演练** / 生产配置）；迁移脚本存在且可重执行；**D-1 容器化**与 **D-2 数据库迁移**两缺口闭合 | DevOps + 架构师 | ⏳ **零代码**（2026-09-27 登记）→ **`delivery-plan.md` P6**（DR-E2~E4）；D-1 / D-2 未补齐前**不得对外承诺可私有化交付**。**原 S11 编号已废** |
| **H15** | **可定制交付（插件式）**：构建期烘焙；单一代码库 + variant（镜像 N 份、代码 1 份）；插件**不污染基座契约**；定制 **L0/L1/L2** 分档 | [`ADR-0007`](./adr/ADR-0007-plugin-delivery.md) §3.1–§3.5（**无模块 spec，锚点为 ADR**） | 半机械 | ① 存在 `deploy/variants/<客户>.yaml` 且**不含业务代码**；② 基座 `contracts/openapi.yaml` 中**无**任何客户专属字段（人工 + 零漂移门禁）；③ 构建产物 tag 形如 `<base_version>-<variant>`；④ 一次基座改动 ⇒ CI 遍历**全部** variant 构建成功 | CI + 架构师 | ⏳ **零代码**（2026-10-01 登记）；`deploy/variants/` 未建 → **`delivery-plan.md` P1**（DR-A1~A3）。**护栏 G-12 / G-14 / G-19 / G-22 骨架已就位**（xfail 挂起）。**原 S11 编号已废** |
| **H16** | **补丁可升级且不破坏插件**：补丁位 = **第三位 PATCH**（当前 `1.6.0` 的补丁 = `1.6.1`；**完整版本语义见需求基线 §7**）**不改契约 / 不改八个接缝接口签名 / DB 只向后兼容加法** | [`ADR-0007`](./adr/ADR-0007-plugin-delivery.md) §3.8.3 / §3.9 | 机械 | ① **接缝签名快照**：打 PATCH / MINOR 时快照**逐字相同** ⇒ **✅ 已建 = 护栏 G-11**（`uv run python backend/scripts/extract_seam_signatures.py --check`）；② 补丁 PR 中 `contracts/openapi.yaml` **零 diff** ⇒ **✅ 已建 = 护栏 G-15**（`check_patch_contract_freeze.py`，**已接入 `ci.yml`**）；③ 迁移脚本评审 + 升级演练（**人工判据**，须留证据） | CI | ✅ **①②已建并生效**（2026-10-01）；③ 演练属人工判据，待 **DR-E3** 兑现 |

> **H1–H10 来自 `CODEBUDDY.md`，H11–H12 来自产品准入线**（PRD §4），**H13–H14 来自商业化与交付形态**（ADR-0006 / deployment-spec，2026-09-27 追加）。**H12 是唯一的"一票否决"项**：它不达标时不允许降级发布。
>
> **H13 / H14 的特殊性**：二者是**横向 + 交付侧**约束，**不落在任一模块 spec 的 §3 验收**（没有 M7），因此锚点是 ADR / 部署规格而非模块 —— 这是"锚点可以不是 spec"的两条例外，**已在 PRD §4 同步登记**。

---

## 5. 准入线与反证条件

### 5.1 准入线 C1–C3（PRD §4 H11 / `02-product-outline.md` 附录 C）

| 指标 | 准入线 | 锚点 / 来源 | 判据 | **可执行命令（`P0-m6-eval`）** | 承接 | 状态 |
|---|---|---|---|---|---|---|
| **C1** 图谱相对 RAG 增益 | **≥ 10%** | M4 §3 验收 6；`02` 附录 C | **A1 已裁决（2026-10-03）**：「同一数据集跑图谱版与 RAG 基线」的**唯一变量 = 检索方式**——两侧**同 chunk 池**（同文档 / 同切分 / 同 chunk id）／**同 `k`**（喂给 LLM 的 chunk 数）／**同生成模型与温度**／**同 prompt 版本**／**同问题集与判分口径**（A3）；**基线检索 = 向量检索（dense top-`k`）**；**分数 = 受控问题集上的答对率**；`(图谱 − 基线) / 基线`。⚠️ **基线分必须与增益一同落盘**（只落增益则无法复核）；**`baseline_spec`**（检索方式 / `k` / 模型 / prompt 版本 / chunk 池版本）**须进报告**。详见 `changes/P0-m6-eval/integration-log.md` **L10-A1** | `uv run python scripts/eval_acceptance.py --live --criteria c1_graph_gain` | S13 → **P6** | ⏳ **A1 已裁决、实现未做（归 P6 开工第一步）** ⇒ 分母仍不存在，判据仍 `BLOCKED`。**防刷绿三条**：① 基线分落盘；② `baseline_spec` 进报告；③ 反向守卫——基线侧 `k` **不得小于**图谱侧、且**不得**换模型 / 换 prompt（单测钉住）。**不选 BM25 作主基线**：中文长文档上偏弱 ⇒ 基线分低 ⇒ 增益虚高 ⇒ C1 可被刷绿（BM25 仅作敏感性对照，不作判据）。⚠️ **事实订正**：`BaselineRunner` 协议**并未建立**（`backend/` 内零匹配；proposal §6 称"出协议 + fixture 基线"，实际**只落了后者**）。**📌 2026-10-09 P6-S 事实订正（上一句已过期，勿再引用）**：`app/evaluation/baseline.py`（494 行）已落地并接进 `eval_graph_gain`；本地 embedding 起来后一次 `--live --criteria c1_graph_gain` 即出**两侧各 40 题答卷**（`p6s-c1-01.json`，`git_hash=101773e7`）⇒ 出卷已通，**唯一缺的是 A3 人工判分**（归 **P6-T**，纯人工；脚本代判分 = 假达标）。**另补一处此前缺口的机器证据**：双侧 spec 与可比性断言已提到**判分闸门之前**（否则判完 80 题才发现不可比 ⇒ 人工作废）⇒ 实测 `p6s-c1-02.json`：池指纹 `e36322bb2d86865f` / **213 条两侧同源**、`top_k` **32 = 32**、两侧 `generation_model` = `deepseek-chat` / `prompt_id` = `kg_qa_v5`、`graph_context` True vs False ⇒ **可比**，判据仍 `value=null`（未给数字）。**防刷绿三条现状**：② 已由本批补齐（spec 进报告）；①③ 的计算通道本就在，待 P6-T 出分后一并给出。证据 [`changes/P6-S/integration-log.md`](../changes/P6-S/integration-log.md)；判分材料 `backend/data/eval/judging/c1-sheets-20261009T064241Z.json` |
| **C2-a** 隐性关联召回 | **≥ 0.80** | M4 §3 验收 6；`01-research` §1.4 P3 | 正确识别数 / 实际植入数（gold 关系人工植入）。**A8 已裁决（2026-10-03）补统计口径**：报告必出 `n` + **95% 单侧置信下界**；spec「命中 ≥16 组」保留为**点估计门槛**（<16 即 FAIL），但**宣称达标还须下界 ≥ 0.80** | `--live --criteria c2_a_hidden_relation_recall` | S13 → **P6** | ✅ **已达标（2026-10-04 P6-A 扩标后）** —— 语料扩至 200/500/100/20 + 植入 **20 组**（受控生成器 `scripts/gen_affiliation_corpus.py`，seed 固定可复现），`--live --gold v2` 实测召回 **1.0000（20/20）**、95% 单侧下界 **0.8609 ≥ 0.80** ✓ ⇒ 不再是 `provisional`。⚠️ **判据层 = L1 算法层**（P6-A/A8 裁决）：**L2 端到端仍未做**（归 P6-Y），在 L2 补证之前**不得对外宣称端到端达标**。📌 **历史过期口径已更正**：本行原写「🟡 扩标未做 / 9/9 下界 0.72 不支持达标」——按 9/9 其实是对的，**但那是扩标前**；扩标后门槛反而更严：20 组须 **20/20 全中**（命中 19 组下界仅 ≈0.82 边缘、18 组必不成立）。详见 **L10-A8** + `changes/P6-A/integration-log.md` |
| **C2-b** 误报率 | **≤ 0.15** | M4 §3 验收 6 | 错误识别数 / 识别出总数。**A8 已裁决（2026-10-03）补统计口径**：**越小越好 ⇒ 用 95% 单侧置信「上界」**判定（与 C2-a 方向相反）；spec 的 0.15 保留为**点估计门槛**，**宣称达标还须上界 ≤ 0.15** | `--live --criteria c2_b_false_positive_rate` | S13 → **P6** | ✅ **已达标（2026-10-04 P6-A 扩标后）** —— 20 组植入下实测误报 **0.0000（0/20）**、95% 单侧上界 **0.1391 ≤ 0.15** ✓ ⇒ 不再是 `provisional`。⚠️ 同 C2-a：**判据层 = L1 算法层**，L2 端到端待 P6-Y。📌 **历史过期口径已更正**：本行原写「🟡 扩标未做 / 0/9 上界 0.28」同为**扩标前**读数；扩标后**阈值余量只有 0.011** ⇒ **误报 1 条（1/20 上界 ≈0.18）即立刻失守**，任何涉及疑点算法或语料的改动都**必须重跑这条**，不得凭上一次的 0 推定仍然成立。详见 **L10-A8** + `changes/P6-A/integration-log.md` |
| **C2-c** 引用覆盖率 | **= 1.00**（硬约束） | M3 §3 验收 2；M4 §3 验收 4 | **A6 已裁决（2026-10-03）：分母 = 排除拒答**（约束的是「**给出的答案**须可回溯」，拒答没给答案 ⇒ 无"它的引用"可言）；报告**须同时给出含拒答档**作对照 | `--live --criteria c2_c_citation_coverage` | S6 → S10 → **P6** | 🟡 演示语料**实测 1.00**（40 题口径：35~36 条作答全部有引用；含 span 口径亦 1.00，2026-10-09 P6-Q 三次 `--live`）⇒ **PASS**。⚠️ **同批发现的拒答误伤**——它**不属** C2-c，而属「**拒答 0 误伤**」判据（Sprint 6 §5.3 验收 1），已立为独立判据。**📌 P6-Q（2026-10-09）复测更正**：误伤**仍在且读数不稳定**（同一代码 / 同一数据三次连跑 ⇒ **1 / 0 / 0** 条），观测到的偶发误伤**已由 Q8 换成 Q28**；检索层**不是**根因（gold chunk 均已进注入 32 条），真因是 `build_chat_model()` 未钉 temperature ⇒ LLM 偶发不产出可溯源 evidence ⇒ 仍记 **FAIL**。⚠️ **若分母改含拒答 ⇒ 35/40 = 0.875（或 0.9）< 1.00 ⇒ 触发 H12 反证 F3，MVP 直接 NO-GO**。✅ **实现缺陷已修**：`runner.py:347-351` 补出 `with_refused` / `strict_with_refused` ⇒ **含拒答档已输出**（实测 0.875 / 0.9，见 L11(b)2）。详见 **L10-A6** + [`changes/P6-Q/integration-log.md`](../changes/P6-Q/integration-log.md)。**📌 P6-R（2026-10-09）再更正**：误伤判据经用户裁决 **O1**（接缝 3 钉 `temperature=0`，**常量**）后**转 PASS** —— 落地后 **≥3 趟一致为 0**、`missed_refusals` 恒空、C2-c 两档不退化（排除拒答 **1.00** / 含拒答 **0.9**）。⚠️ **仍不进 CI**（依赖 live LLM；钉温度只**降低**不**消除**抖动）⇒ 演练时人工复跑留证。详见 [`changes/P6-R/integration-log.md`](../changes/P6-R/integration-log.md) |
| **多跳答对率** | **≥ 0.80** | M3 §3 验收 1 | 3 跳内正确回答数 / 总多跳问题数 | `--live --criteria multihop_accuracy --judgements <file> --judged-by <人>` | S10 | ⏳ **待人工判分**（**A3**：脚本不做关键词判分，否则假达标）⇒ 当前 `UNKNOWN`，**不是 0** |
| **C3-a** 单文档处理成本 | 落入阈值（**TBD-7**） | M6 §3 验收 8；`02` 附录 C | `token_usage_total / doc_count`（单位 **token/文档**） | `--criteria c3_a_single_doc_cost`；校准：`--calibrate --cost-records <file>` | S13 | ⏳ **阈值已落** `EVAL_SINGLE_DOC_TOKEN_CEILING = 32 000`（`config.py` + `.env.example`，**有消费者**），来源 provisional；**值**待 P5-M6 落 `cost_metrics` ⇒ 当前 `BLOCKED` |
| **C3-b** 增量 / 全量成本比 | **显著 < 1.00** | M6 §3 验收 8 | `incremental_cost / full_rebuild_cost` | `--criteria c3_b_incremental_cost_ratio` | S13 | ⏳ 待 P5-M6 增量重算；阈值按矩阵定值（`metrics.COST_RATIO_SIGNIFICANT`，**D3：不落 config**——无消费者即幽灵配置） |
| **M6-b** GUI 人工确认语义 | **不得降级** | M6 §3 验收 1 / 2 | 未确认 schema **不写入** `ontology_schemas` | **不适用**（人工确认语义，非评测脚本范畴） | S12 | ⏳ |

> **TBD-7 阈值**由 plan §20.1 批次 D 在 S13 收敛（决议 **O-4**，见倒推文档 §7）。收敛前 C3 只能判"趋势"，不能判"达标"。
>
> **上表命令的出处**：`backend/scripts/eval_acceptance.py`（批次 `changes/P0-m6-eval/`，2026-10-03）。
> **实测证据**：`backend/reports/eval/`（运行产物，**已 gitignore**）；过程与遗留见
> `changes/P0-m6-eval/integration-log.md` §E2.7 / §E3。
> **口径纪律**：`BLOCKED` / `UNKNOWN` 的 `value` **恒为 `null`**（不是 0——0 会被读成"召回为 0"，误触发反证 **F2**）。

### 5.2 反证条件 F1–F5（`01-research.md` §3.3）

| # | 触发条件 | 触发后处置 | 关联锚点 |
|---|---|---|---|
| **F1** | 图谱相对 RAG 增益 **< 10%** | **退回 RAG-first 产品形态**，从路线图移除图谱依赖 | C1 / M4 §3 验收 6 |
| **F2** | 多跳答对率 / 影响面召回 **< 0.80** | **暂缓图谱化投入**，优先补抽取与实体消解质量 | M3 §3 验收 1 |
| **F3** | 引用覆盖率 **< 100%** | **直接 NO-GO**（不可降级） | H12 / M3 §3 验收 2 |
| **F4** | 单位成本无法收敛到可接受区间 | **降级为"仅解析 + 结构化抽取"轻量产品** | C3 / M6 §3 验收 9 |
| **F5** | 目标客户付费意愿 < 替换现有工具成本 | 重算 Top 5 排序，重评立项 | PRD §1.3 不做清单 |

**G5 诚实性要求**：C1 的"RAG 基线"必须与图谱版**同数据集、同问题集、同标注口径**；否则增益不可归因（本轮无外部效度校验，须在 release notes 显式声明）。

### 5.3 机械门禁命令（Sprint 收尾必跑，全绿才可 tag）

```bash
# backend/
uv sync --all-groups --frozen
uv run ruff check . && uv run ruff format --check .
uv run python scripts/check_seams.py            # 收尾用【默认档】，要求 ERROR = 0
uv run pytest -q
uv run python scripts/export_openapi.py --check

# frontend/
npm ci && npm run lint
npm exec next typegen && npm run typecheck
npm run gen:api
git diff --exit-code -- frontend/src/types/api.d.ts
```

> **口径更正（2026-09-22，以脚本实测为准，原表述作废）**：`--strict` **不是** Sprint 收尾口径。`check_seams.py` docstring 第 5–6 行与 `--strict` 分支的报错文案均明示——「`--strict` 只适用于 Demo-MVP 完成点（**v1.4.0**，接缝全部到期）；Sprint 收尾请用默认档并要求 **ERROR = 0**」。
>
> 实测佐证：v1.1.0 跑 `--strict` 必红（exit 1），其 6 条 WARN **全部是未到期接缝**（5 事件出口 / 6 导出 / 7 外部映射 / 8 外部导入，按 `required_from` 分属 v1.3.0~v1.4.0），属"尚未到期"而**非越界**——若据此判 Sprint 5 收尾失败，逻辑上等于要求 S5 提前交付 S7~S8 的内容。
>
> **默认档不会漏项**：未到期项由脚本按 `required_from` 自动上闸，一旦越过当前版本即自动升为 ERROR；`--strict` 的用途是 v1.4.0 收尾时确认"接缝全部就位"，不是常规 Sprint 的放行条件。

---

## 6. 证据落点

| 证据类型 | 落点 |
|---|---|
| 批次事前设计 | `changes/Sprint<N>.<M>/proposal.md` + `tasks.md`（+ `design.md`） |
| 实测证据链 | `changes/Sprint<N>.<M>/integration-log.md` |
| 归档 | `changes/archive/<日期>-Sprint<N>.<M>/`（只归档 `.md` / `.py`） |
| 契约 | `contracts/openapi.yaml` + `frontend/src/types/api.d.ts`（生成物，禁止手改） |
| 接缝登记 | `docs/adr/0004-integration-seams.md`（新增预留必登记） |
| 版本说明 | `docs/release-notes/v1.x.0.md` |
| 本矩阵状态列 | 每个 Sprint 收尾同步更新（见 §7） |

---

## 7. 维护纪律

1. **spec 验收编号一经定稿不得重排**——重排会让本矩阵全部锚点失效。新增验收**只能追加编号**（如 M1 追加为验收 9），不得插入或删除中间项。
2. **新增/修改硬约束**：先改 PRD §4 → 再改 spec §3 → 最后改本矩阵 §4，三处必须同步；漏任一处视为文档未完成。
3. **每个 Sprint 收尾**核对两件事：① 本 Sprint 承接的 spec 验收条**逐条打勾**；② 本矩阵 §4 / §5.1 对应行的**现状列**刷新。
4. **本文件不复制参数值**：阈值、算法细节、字段清单一律回引原文档，避免第二真源。
5. **降级不静默**：F1–F5 任一触发或任一准入线不达标，必须在 release notes + 本矩阵 §5.1 显式登记处置结论。

---

> **一句话**：**H1–H12 每行都能回答"谁验、怎么验、现在到哪一步"**——这是"不偏离 + 可按原始文档验收"的最低标准。
