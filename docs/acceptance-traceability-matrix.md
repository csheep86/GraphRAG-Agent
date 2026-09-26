# 验收可追溯矩阵（MVP 1.0 → v2.0.0）

> **目的**：把 `docs/03-prd.md` 的每条**硬约束（H1–H12）**与**准入线（C1–C3 / F1–F5）**，唯一地落到"**哪个 spec 的哪条验收 → 用什么判据 → 谁签字 → 证据放哪**"。让"是否达成"可被机械或人工复现，而不是靠叙述。
>
> **解决什么**：PRD §4 原先只说"落实模块 + 规格章节"，`docs/v1.1.0-demo-mvp-plan.md` §3.2 B 要求"H1–H12 逐条有判据（优先机械脚本，人工判据须写明验收人）"，但该动作被排到 Sprint 13（P3-1）。**本矩阵把它前置到 Sprint 5 开工前**，使每个 Sprint 收尾即可逐行对账，而不是上线前集中补。
>
> **口径真源**（本文件不复制细节，只做映射）：
> - 需求与硬约束：`docs/03-prd.md` §2 / §4 / §5 / §8
> - 交付与门禁：`docs/v1.1.0-demo-mvp-plan.md` §3.2 B / §15 / §20 ～ §21
> - 倒推与闸门：`docs/v2.0.0-ship-backward-plan.md` §1 ～ §3
> - 验收条文：`specs/m1..m6-*.md` §3
> - 指标定义：`docs/02-product-outline.md` 附录 C；反证条件：`docs/01-research.md` §3.3
>
> **状态**：v1.2（2026-09-21 建立，架构师；**2026-09-22 更新**：S5 收尾对账——H4 / H8 两项「已知缺陷」关闭、M1 / M2 与黄金路径步骤 3 现状刷新、§5.3 `--strict` 口径更正为默认档；**2026-09-24 更新**：**S7 收尾对账**——新增 §3.3「M4 §3 验收 1–7 逐条对账」；M4 行与黄金路径步骤 4 补批次 C / D；H1 / H3 / H4 / H5 / H10 / H12 现状刷新；C2-c 补 M4 侧证据；**2026-09-24 追加（S6 侧补做）**：新增 §3.4「M2 / M3 §3 验收 1–7 逐条对账」，M2 / M3 行与 H4 / H8 现状刷新，**并更正「M2 `confidence` 未落库」这一过期口径（实测已落库）**；**2026-09-26 更新（S8 收尾对账）**：M5 行与黄金路径步骤 6 刷新（审计闭环落地、`qa_logs` 由「未建」转已建已写）、**H7 限流由 ⏳ 转 ✅**、M3-3 刷新；**Demo-MVP 十条总对账不在此表，见 [`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) §6**）

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
| **G4** 硬约束 | **H1–H12 逐条有判据** | §4 |
| **G5** 诚实性 | 外部效度与数据来源声明（RAG 基线数据集同源同题、标注口径一致） | §5.2 |

---

## 3. 验收条文索引

### 3.1 模块验收清单

| 模块 | 规格 | 条数 | 编号 | 承接 Sprint | 现状 |
|---|---|---|---|---|---|
| **M1** | `specs/m1-async-ingest.md` §3 | 8 | 1–8 | S5（docx 解析 S10） | ✅ 上传 / 状态机 / 重试**全部真实**（B1 `retry_count` 回写 + B4 退避读配置已于 S5 收口）；docx 仍只收不解析 → S10 |
| **M2** | `specs/m2-extract-kg.md` §3 | 7 | 1–7 | S5（四源字段）、S6（`:Chunk`）、S9（实体消解） | 🟡 **S5 批次 B 转正为在线服务**（上传即建图，三段式写入，`kg_versions` 为版本真源）；**S6 批次 A 落地 `:Chunk` 证据节点**（原文片段 + `page` / `char_start` / `char_end` + `acl_scope`，`(d)-[:HAS_CHUNK]->(c)` + `(c)-[:MENTIONS]->(e)`；`acl_scope` **只落属性、查询不做穿透过滤** → S11）。**`confidence` 已随 v1.2.0 落库**（节点 + 关系属性，见 §3.4 M2-2；本行原写「仍缺 `confidence` 落库」属**过期口径，已于 2026-09-24 更正**）。仍缺 实体级 `char_offset`（`Citation.char_offset` 恒 0）/ 实体消解（S9~S10）。**逐条对账见 §3.4（S6 收尾补做）** |
| **M3** | `specs/m3-graphqa-citation.md` §3 | 7 | 1–7 | S6（引用溯源）、S10（≥3 跳） | 🟡 **S6 达成 chunk 级引用溯源**：`:Chunk` 证据节点 + 引用按 `chunk_id` 真实回查（`doc_id` / `page` / `snippet`）+ 前端抽屉原文高亮；受控问题集 14 问**覆盖率 100% / 拒答误伤 0**（2026-09-24 复核：`_build_citations` 仍只认本轮注入 chunk）。仍缺 **≥3 跳遍历**（代码中**无变长 Cypher**）、`qa_logs` 打点、`route` 意图路由（恒为 `m3_graphqa`）→ 分别见 §3.4 M3-1 / M3-3 / M3-5 / M3-7 |
| **M4** | `specs/m4-affiliation-detection.md` §3 | 7 | 1–7 | S7（1 类算法）、S9（三类 + 四源） | 🟡 **S7.1 批次 A 起始落地**：三类 M4 节点（`:Subject` / `:Address` / `:LegalPerson`）+ 两条边（`LEGAL_REP` / `REGISTERED_AT`，**不与 `:Entity` 桥接**）已入图（§4.2 属性逐字，节点 id 按**规范化名称**稳定化以便跨文档合节点）；两类规则算法（共享法人 / 共享地址）照 spec §5.4 原文落实，证据经 `source_entity_ids` 溯源回 `:Chunk` 原文；`risk.detect` 执行体已登记 `EXECUTOR_REGISTRY`（但在 kg_version 作用域跑，**不是**单文档）。**S7.2 批次 B（2026-09-24）再落地「持久化 + 对外端点」**：三张 PG 表（`affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects`，表名逐字 = PRD §6.2 与 spec §4.3–4.5，三表**均带 `org_id` 且索引以 `org_id` 打头**，ADR-0003）+ 四个端点（`POST /affiliation/detect` / `GET /affiliation/tasks/{id}` / `GET /affiliation/suspicions` / `PATCH /affiliation/suspicions/{id}`，**路径口径以 spec §5.5 的 `suspicions` 为准**，plan §6.2 原写 `suspects` 已同步）。一次检测 = 一条 `affiliation_tasks`，状态机经 `TaskManager` 投递（**先行扩展到「多文档任务」**，决策 B8）并纳入启动回收（ADR-0001 第 73 行要求扫两张表）。**真机**：6 片演示数据 + `v-s71a-fe1c4dc3` → **10 条疑点落库**（与批次 A 一致：共享法人 1 + 共享地址 9），每条 `evidence` 非空（引用覆盖率 100%），`trace_id` 与任务同值，`PATCH` 复核落 `reviewed_by`（当前取 dev 脚手架 `X-Actor-Id`）。**S7.3 批次 C（2026-09-24）前端消费侧落地**：新增 `/affiliation` 疑点页（清单 / 类型 + 状态筛选 / 证据抽屉 / 复核按钮），四端点**全真实消费**（`USE_MOCK=false` 时 Mock 不参与；真机 `total=10`、**证据回查 10/10 成功**）；§3 验收 4 的「可回溯到具体原文」在 UI 侧打通（经 `GET /documents/{id}/chunks/{chunk_id}` 回查原文），§3 验收 7 的 `task_id` 异步查询与结果回传在 UI 侧打通（首个真轮询，2s → 10s 降频）。**仍未达标的部分**：`unaligned_subjects` 只建表不写（写入点随 S9 批次 D 四源对齐）、连通分量 / 环路 / 金额不一致三类算法未做（S9）、§3 验收 1 的 0.95 对齐率未做（S9）、§3 验收 6 的准入指标（召回 / 误报）**未测量**（S13）、**证据粒度是 chunk 级不是提及级**（真机 10/10 `ev_len == chunk_len`）——片段级定位（`char_offset` 恒 0）按 `plan.md:619` 归 **S10**，前端已改淡底 + 标注，**未伪造高亮** |
| **M5** | `specs/m5-permission-audit.md` §3 | 8 | 1–8 | S8（审计页）、S11（RBAC / RLS / 双轨） | 🟡 **S8 批次 A 首次端到端可用**：`audit_log`（§4.4 11 字段）/ `qa_logs`（§4.3 10 字段）两张表落地（均带 `org_id` 且索引 `org_id` 打头；**主键 UUID 而非 spec 的 `BIGSERIAL`**，差异已登记 ADR-0003 §3.1.1）+ 纯 ASGI `AuditMiddleware` 全量写（health 豁免、`detail` 只写结构化字段、写失败只记日志、401 无身份不写）+ 两个只读端点（按租户列表 / 按 trace 查）+ 前端审计页关 Mock（`CONTRACT_COVERED_PATTERNS` **12 → 14**）；**批次 B** 补 §3 验收 5 限流（`RATE_LIMITED` + `Retry-After` + `rate_limit.triggered` 留痕）与逃生阀 `tenant_leak.warn`；**真机**：演示路径走一遍后 `audit_log` **13 条 / 13 个 trace**（条数判据 ≥7 ✅）、`qa_logs` 1 条，浏览器点验审计页 30 条 / 11 类 action。**仍未达标**：RBAC 三粒度、完整脱敏、RLS、私域开关（均 → S11）；§3 验收 6 的「≥7 条**共享同一** `trace_id`」**未实测**（一请求 = 一条 `audit_log`，需客户端透传同一 `X-Trace-Id` 才聚合）⇒ 黄金路径步骤 6 仍 🟡 |
| **M6** | `specs/m6-ontology-incremental.md` §3 | 11 | 3.1–3.5（1–11） | S12 | 🟡 **v0.1 草案**（定稿闸门 = 倒推文档 §7.1 CP-3） |
| **合计** | | **48** | | | |

### 3.2 PRD §5 黄金路径 7 步 → 锚点

| 步骤 | 场景 | 锚点 | 现状 |
|---|---|---|---|
| 1 | 上传合同 PDF + 3 CSV，P95 ≤ 500ms | M1 §3 验收 1 | ✅ |
| 2 | 轮询状态 `pending → processing → completed` | M1 §3 验收 5 | ✅ |
| 3 | Neo4j 写入 + `kg_version` 落 `kg_versions` | M2 §3 验收 4 | ✅ **S5 批次 B 达成**（`kg_versions` 为版本真源，黄金路径 3/7） |
| 4 | M4 命中 ≥ 1 疑点且引用覆盖率 100% | M4 §3 验收 4 + 6 | 🟡 **S7.1 批次 A 首次产出疑点**：6 片演示数据（招商蛇口 / 招商公路募集说明书 + 招商轮船年报，切片）→ 共享版本 `v-s71a-fe1c4dc3` 命中 **10 条**疑点（共享法人 1 + 共享地址 9），每条附 3–6 条 `:Chunk` 原文证据（合计 42 条），**引用覆盖率 = 100%**（实现纪律：取不到证据的命中**直接丢弃**并打 `affiliation_suspicions_dropped_no_evidence` WARNING）。**这不等于通过验收**——数据集既非 spec 的"200 合同 + 500 发票 + 100 凭证 + 20 组植入样本"，召回 / 误报率也**未测量**（H11 / §5.1 仍 ⏳ S13）。**S7.2 批次 B 补上消费侧**：同一批疑点（10 条）落 `affiliation_suspicions` 并经四端点可读、可复核（`open → confirmed / dismissed` 落库），疑点数与批次 A 对齐 = 无重复出条 / 无丢条。**S7.3 批次 C 再补人机界面**：同一批疑点在 `/affiliation` 可见 / 可筛选 / 可开证据抽屉回原文 / 可点复核（浏览器点验落库 `confirmed=4 / dismissed=1`）；⚠️ 证据粒度为 **chunk 级**，提及级高亮归 S10 |
| 5 | M3 提问 → 引用 100% 或拒答 | M3 §3 验收 2 + 3 | 🟡 **引用侧 S6 达成**（chunk 级引用回查，受控问题集 14 问覆盖率 100% / 拒答误伤 0；**2026-09-24 复核口径不变，见 §3.4 M3-2**）；剩余**多跳 ≥3 跳** → S10 |
| 6 | 审计 ≥ 7 条且共享同一 `trace_id` | M5 §3 验收 6 | 🟡 **S8 批次 A 部分达成**：`audit_log` 全量落库 + 两个只读端点 + 审计页关 Mock **已达成**（真机 **13 条 / 13 个 trace**，条数侧 ≥7 ✅，浏览器点验审计页 30 条）；但「**共享同一** `trace_id` ≥7 条」**未实测**——当前一次 HTTP 请求写一条 `audit_log`，需客户端透传同一 `X-Trace-Id` 跨请求才聚合（闭合方式见 release notes v1.4.0 §7.1）。**未实测前不宣称达标** |
| 7 | C1–C3 准入线 | §5.1 | ❌ S13 |

### 3.3 M4 §3 验收 1–7 逐条对账（S7 收尾，2026-09-24）

> 本节按 §9.2 第 3 项对 Sprint 7 承接的 M4 §3 验收条**逐条打勾**。未达成的写明承接 Sprint，**不靠叙述糊过去**。

| 验收 | 摘要 | 判据 | 现状 | 承接 |
|---|---|---|---|---|
| **1** | 四源主体对齐，成功率 ≥ 0.95，未对齐主体入 `unaligned_subjects` | 对齐成功率统计 + `unaligned_subjects` 行数 | ❌ **未做**：表已建（spec §4.5）但**无人写入**（缺口 **S7.2-1**）；四源对齐与 0.95 成功率**未测** | S9 批次 D |
| **2** | 建「主体-地址-法人-股东-电话」多类节点，节点带 `kg_version` 且**共用 `status=active` 版本**（ADR-0002 不分裂版本） | 图中节点 label 计数；节点 `kg_version` 与 `kg_versions.status` 比对 | 🟡 **部分达成**：`:Subject` / `:Address` / `:LegalPerson` 三类已入图并带 `kg_version`，**共用 active 版本**（跨版本隔离已证：旧版本 `v-3e381d36` 无 `:Subject`，`detect` 返回 0 条、不串数据）；`:Phone` / `:Invoice` / `:Voucher` / `:Contract` 未建 | S9 批次 B（节点）；版本纪律**持续满足** |
| **3** | 三类算法（连通分量 / 共享邻居 / 环路）任一命中即出疑点，`type ∈ {shared_address, shared_legal_rep, shared_phone, cycle, amount_mismatch}` | 算法族实装 + `suspicion_type` 取值校验 | 🟡 **部分达成**：已落**两类规则**（共享法人 / 共享地址），`type` 取值在 spec 枚举内；spec 的**三类图算法**未做 | S9 |
| **4** | 每条疑点可回溯 ≥ 1 具体原文，**引用覆盖率 = 100%**，不允许「无原文证据」的疑点 | 含证据疑点数 / 总疑点数；反证 F3 | ✅ **达成（演示数据集口径）**：**10 / 10** 疑点含 3–6 条 `:Chunk` 证据（合计 42 条）= **100%**；取不到证据的命中**直接丢弃**并打 `affiliation_suspicions_dropped_no_evidence` WARNING；UI 侧可点开原文（**证据粒度为 chunk 级**，提及级定位归 S10） | 终局判据 **S13**（spec 全量样本） |
| **5** | 三方金额不一致 → `amount_mismatch` 疑点，`severity=high` | 构造合同 / 发票 / 凭证三方金额不等 | ❌ **未做**（依赖 `:Invoice` / `:Voucher` / `:Contract` 节点，均属 S9） | S9 |
| **6** | 场景准入：200 合同 + 500 发票 + 100 凭证 + 20 组植入 → 召回 ≥ 0.80、误报 ≤ 0.15、覆盖率 = 100% | 评测脚本（**待建**） | ❌ **未测量**：演示数据集为 6 片年报切片，**非** spec 样本；评测脚本未建 | S13 |
| **7** | 提交 → 异步执行返回 `task_id` → `GET /tasks/{id}` 查结果 → 结果含 `affiliation_suspicions` 列表 + 回溯引用 → 重启回收置 `failed`（`error_code = TASK_INTERRUPTED`） | 四端点联调（关 Mock）+ 重启回收用例 | ✅ **达成**：四端点已进契约并可关 Mock 消费（`USE_MOCK=false` 时 Mock 不参与）；一次检测 = 一条 `affiliation_tasks`，经 `TaskManager` 双载体投递并纳入 `recover_orphan_tasks()` 启动回收（ADR-0001 第 73 行要求扫两张表）；复用 `TASK_INTERRUPTED`。**残留**：`list_in_flight_task_ids()` 仍只扫 `documents`（缺口 **S7.2-2**） | 保持；S7.2-2 → **S8** |

**对账结论（不伪装）**：7 条中 **2 条达成**（验收 4 / 7）、**2 条部分达成**（验收 2 / 3）、**3 条未做**（验收 1 / 5 / 6）。**M4 尚未通过 §3 验收 6 的场景准入**——召回 / 误报**未测量**，见 release notes v1.3.0 §6.7 与 §5.1（C1 / C2 仍 ⏳ S13）。

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
| **M2-3** | 实体消解（≥ 0.90 自动合并 / 0.70–0.90 进人工队列 / < 0.70 保持独立） | 合并候选取值 + `entity_merge_candidates.status` | ❌ **未做**：反证就是 S6 真机——同一实体被建图 **3 次**（6 → 18 节点，实体名出现「本报告汇总了集团」这类整句），且**候选表不存在**（`models.py` 现仅 `Document` / `KgVersion` / `Affiliation*` / `UnalignedSubject` / `ExternalRef` / `DomainEvent` 七张表，无 `EntityMergeCandidate`） | **S9 批次 D** |
| **M2-4** | `kg_version` 版本化写入、**先 PG 后 Neo4j**、MERGE 幂等、历史版本不删 | 写入顺序 + `kg_versions` 记录 + 幂等键 | ✅ **达成（S5 实现，S6 加固）**：三段式写入 + `kg_versions` 字段完整；幂等键 `(id, kg_version)` ⚠️ **社区版无 `IS NODE KEY`，降级为 `IS UNIQUE`**（S6.1 §4.1，**未隐瞒**）。S6.3 定 **PG 为真源**（`ready` ≡ `active` 语义）并新增在线激活端点 `POST /graph/versions/{version}/activate`，此前**只能人工改库**（S6.3 §2.1 实测 200 + `superseded_versions`） | 版本纪律持续满足；⚠️ S6.1 §4.3 上报的「**在线链路不自串联**」（上传后 extract / kg.build 不自动触发）本次**未验证是否已闭合** |
| **M2-5** | tenacity 指数退避 ≤ 3 次（初始 1s、倍数 2），失败置 `failed` + `error_code` 落库 | 重试次数断言 + 库表回写 | ✅ **达成（S5 批次 A 闭环）**：H8 两项缺陷已关闭；S6 四批次的 integration-log **均未涉及重试链路改动**，无回归面 | 保持 |
| **M2-6** | 抽取完成且 `kg_version` 落库后**投递索引更新事件**，M3 / M4 可立即消费 | 写图后的事件 publish 调用 | ❌ **未做**：`EventBus` 的唯一使用点在 `services/affiliation.py`（**S7.4 批次 D**），`services/kg/` 下**零 publish**；当前靠调用方**显式调激活端点**衔接，不是事件驱动 | **未排期**（接缝 5 出口已于 S7.4 就位，M2 侧写入点待安排） |
| **M2-7** | `trace_id` 全链路 + token 用量 / 耗时打点（成本仪表盘 C3） | 日志 + 响应 `token_usage` + 成本聚合表 | 🟡 **部分达成**：`trace_id` ✅（`core/middleware.py` 回显并贯穿，写图各 stage 落 `trace_id`）；token 用量 ✅ 真机返回（`prompt 1733 / completion 66 / total 1799`，S6.2 §3.1）。**缺**：`C3` 聚合未建——无成本表，`models.py` 现七张表里没有它 | C3-a / C3-b → **S13** |
| **M3-1** | **≥ 3 跳**遍历 + 每跳 `kg_version` 过滤 + 单次节点数 ≤ 500 | Cypher 是否含变长路径；`node_limit` 默认值 | 🟡 **部分达成**：版本过滤 ✅（两个查询均带 `kg_version` 约束，且经 PG 真源取 active 版本）；节点上限 ✅（默认 `node_limit = 500` + `truncated`，`graphs.py:634 / 694`）。**≥ 3 跳未做**——`graphs.py` 全文**无任何变长路径模式**（`*n..m` 零命中），实际是「实体间 1 跳」与「`Document → Chunk → Entity` 2 跳」两种**定长模式**（spec §5.4 草案里的 `*1..3` 未落地） | **S10** |
| **M3-2** | 引用覆盖率 = **100%**（无溯源即拒答，F3） | 含可回溯证据的答案数 / 总答案数 | ✅ **达成（受控问题集口径）**：S6.4 §6 真机 14 问 → 非拒答 12、引用命中 **12** = **100%**，拒答误伤 0（`scripts/eval_controlled_qset.py`）。**2026-09-24 复核仍成立**：`agents.py:350-352` 的 `_build_citations` 只认本轮注入的 chunk id，回查不到**直接丢弃** | 终局判据 **S10**（多跳 + 全量问题集） |
| **M3-3** | 拒答出口返回契约体，**M5 写 `qa.refused` 审计** | 响应体结构 + 审计落库 | 🟡 **部分达成**：拒答**唯一出口** `_refuse`（`agents.py:480-509`）返回 `answer="无法回答"` / `refused=true` / `refusal_reason` / `confidence="low"`，14 问中的 2 道库外题**全部正确拒答、无误伤**。**缺（2026-09-26 刷新）**：`qa_logs` 表（spec §4.3）**S8 批次 A 已建并已写**（成功 / 拒答都落，`question_hash` / `answer_hash` 为 SHA-256 不存原文，真机 1 条）；但 `audit_log` 侧**无 `qa.refused` action**——审计 `action` 走路由映射（`http.<method>.<path>`），拒答事实只体现在 `qa_logs.refused` / `refusal_reason` 列 ⇒ 该条**仍记为部分达成** | `qa.refused` 审计 action → S11（M5 三粒度落地时统一）；`qa_logs` **已闭合** |
| **M3-4** | `scope=single_doc` 严格隔离，`citations` 仅含该文档 | 单 / 跨文档各一例 | ✅ **达成**：`agents.py:441-445` 按 scope 分流；取证据时 `doc_id is not None` → `_QUERY_EVIDENCE_CHUNKS_BY_DOCUMENT`（`graphs.py:782-784`，受 `doc_id + kg_version` **双重约束**），`cross_doc` 才走「按实体回查」 | 保持 |
| **M3-5** | 意图路由到 M4 → `route = "m4_affiliation"` + 携带 M4 `task_id` | 响应 `route` 取值 + 路由调用点 | ❌ **未做**：`route` 在两个出口**恒为 `"m3_graphqa"`**（`agents.py:378 / 506`），无 `intent_router` 调用。S7 的 M4 疑点链路走**独立页面 + 独立端点**（`POST /affiliation/detect`），**未接回 M3 路由** | **未排期** |
| **M3-6** | 输出置信度评级 `high / medium / low`，`low` 在 UI 标记「建议人工复核」 | 响应 `confidence` + 前端标记 | ✅ **达成**：`QueryConfidence` 三值（拒答固定 `low`）；前端 `chat-message-item.tsx:50-52` 对 `confidence === "low"` 打「**低置信度**」徽标。⚠️ **字面差异**：UI 文案是「低置信度」而非 spec 原文「建议人工复核」——语义一致、措辞不同，**登记不修改** | 保持 |
| **M3-7** | `trace_id` + 「问题 → 答案 → 引用条数 → 拒答原因」完整链路打点 | `qa_logs` 落库 | 🟡 **部分达成**：`trace_id` ✅（同 M2-7 / H4）；「引用条数 / 拒答原因」**在响应体内** ✅。**缺**：`qa_logs`（`question_hash` / `answer_hash` / `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id`）**表未建**，无持久化打点 | **未排期**（建议随 S10「真实引用细化」一并估） |

**对账结论（不伪装）**：

- **M2**：7 条中 **2 条达成**（验收 4 / 5）、**2 条部分达成**（验收 2 / 7）、**3 条未做**（验收 1 / 3 / 6）；
- **M3**：7 条中 **3 条达成**（验收 2 / 4 / 6）、**2 条部分达成**（验收 3 / 7）、**2 条未做**（验收 1 / 5）；
- **合计 14 条：5 达成 / 4 部分 / 5 未做**。

**本次补做的实质发现（口径更正）**：多个文档（本矩阵 §3.1 M2 行、`plan.md` §15.3 M2 行、`specs/m2` 状态行）长期写着「M2 **`confidence` 不落库**」——**2026-09-24 复核为错误**：`confidence` 已随 v1.2.0 写入 Neo4j 的节点与关系属性，且带完整取值纪律（丢弃、裁剪、不猜值）。三处已按更正后口径重写，**理由留在本节以备反查**，避免下次有人照旧口径又改回去。

**另一条要记住的**：`qa_logs` 从未建表（M3 §4.3），因此 M3 验收 3 / 7 的「打点」**今天也不成立**——这不是 S6 留下的债，而是它当时就依赖一个尚未落地的东西。

---

## 4. H1–H12 硬约束 → 验收锚点 → 判据（**本矩阵核心**）

| # | 约束（摘要，全文见 PRD §4） | 锚点 | 判据类型 | 判据 / 命令 | 验收人 | 现状 |
|---|---|---|---|---|---|---|
| **H1** | 异步任务状态机 `pending → processing → completed / failed` | M1 §3 验收 1 / 5；M1 §3 验收 8（启动回收 → `TASK_INTERRUPTED`）；**M4 §3 验收 7** | 机械 | 集成测试断言 `status` 仅在四值内 + 重启回收用例；契约 `documents.status` 枚举 | CI | ✅ M1 侧；✅ **M4 侧（S7 达成）**：`affiliation_tasks.status` 四值内、经 `TaskManager` 双载体投递并纳入 `recover_orphan_tasks()` 启动回收（置 `failed` / `error_code = TASK_INTERRUPTED`）。**残留**：`list_in_flight_task_ids()` 仍只扫 `documents`（缺口 **S7.2-2** → S8） |
| **H2** | 上传 ≤ 100MB + MIME 白名单（pdf/docx/csv） | M1 §3 验收 2 / 3 | 机械 | 集成测试各 1 例：超限 → 413 `FILE_TOO_LARGE`；非白名单 → 415 `UNSUPPORTED_MEDIA_TYPE` 且不落存储 | CI | ✅（docx 解析 S10） |
| **H3** | 错误响应统一 `{code, message, detail, trace_id}` | M1 §3 验收 2 / 3；M5 §3 验收 1；M3 §3 验收 3 | 机械 | 契约 `ErrorResponse` schema + 各错误分支响应体断言 | CI | 🟡 M1 侧已统一；**M4 侧已统一**（新增 `AFFILIATION_TASK_NOT_FOUND` / `AFFILIATION_SUSPICION_NOT_FOUND` 两个 404 均走统一 `ErrorResponse`；跨租户 **403 而非 404**）；M3 / M5 侧随模块落地 |
| **H4** | loguru JSON 日志 + `trace_id` 全链路 | M1 §3 验收 7；**M2 §3 验收 7**；M5 §3 验收 6；**M6 §3 验收 10** | 半机械 | 断言响应头 `X-Trace-Id` 回显且与 `detail.trace_id` 一致；E2E 断言同一 `trace_id` 贯穿 M1→M5 | 后端 B | ✅ **S5 已收口**：`_refuse()` 出口 `trace_id` 已补，原「已知缺陷」关闭；**M4 侧已贯穿**（`POST detect` 的 `trace_id` 与 `affiliation_tasks.trace_id` / `domain_events.trace_id` 同值，真机复核一致）；**M2 / M3 侧 2026-09-24 补做核实**：M2 §3 验收 7 已达「日志 + 响应 `token_usage`」、`trace_id` 由 `core/middleware.py` 回显并贯穿写图各 stage（缺 C3 聚合，见 §3.4 M2-7）；M3 响应体 `trace_id` ✅ 但 `qa_logs` 打点**未落**（§3.4 M3-7）；M6 侧 ⏳ S12 |
| **H5** | 敏感字段脱敏（金额 / 发票号 / 税号 / 法人 / 银行 / 身份证 / 电话 / 文件名） | **M5 §3 验收 3 + §4.5** | 机械 | 单元测试断言日志与响应中**无原文**；`filename_hash` 替代原文 | 后端 B | 🟡 部分；完整脱敏 S11。**M4 侧**：`:LegalPerson.id_hash` 在无统一社会信用代码时**为 `null`**（严禁兜底造哈希），节点属性逐字照 spec §4.2 |
| **H6** | 私域部署禁云外发（`PRIVATE_DEPLOY_ENABLED=true`） | M5 §3 验收 4 | 机械 | 单元测试断言外发被拦截（503 `PRIVATE_DEPLOY_BLOCKED`） | 后端 B + 架构师 | ⏳ S11。**当前为占位**，例外登记见 `docs/adr/0004-integration-seams.md` §3 |
| **H7** | slowapi 限流（默认 60 req/min/IP） | M5 §3 验收 5 | 机械 | 集成测试连打超阈值 → 429 `RATE_LIMITED` | CI | ✅ **S8 批次 B 已收口**：`core/limiter.py`（`rate_limit_per_minute` 默认 60）+ **自写纯 ASGI `RateLimitMiddleware`**（实测 FastAPI 0.141 的 `_IncludedRouter` 会让 slowapi 自带中间件**静默失效**，handler 恒 None ⇒ 全部请求被豁免）；`/health` 豁免；429 统一走 `AppError(RATE_LIMITED).to_body(trace_id)` + `Retry-After: 60` 并写 `audit_log(rate_limit.triggered)`。**真机**：`RATE_LIMIT_PER_MINUTE=3` → 限内 3 次 200、第 4/5 次 **429**，`/health` 全 200，`dev.db` 直读 `rate_limit.triggered` 2 行 |
| **H8** | tenacity 指数退避 ≤ 3 次（初始 1s、倍数 2） | M1 §3 验收 4；M2 §3 验收 5 | 半机械 | 注入失败后断言重试次数 = 3 且 `error_code` / `error_detail` 落库；M2 侧断言 `retry_count` 写回 | 后端 B + 架构师 | ✅ **S5 批次 A 已收口**：B1（`retry_count` 回写）+ B4（退避 `exp_base` 读配置）两项缺陷均关闭，`task_retry_multiplier` 现为**有消费者的配置**。**2026-09-24 补做核实（S6 侧）**：S6 四批次**均未改动**重试链路，两项缺陷保持关闭（见 §3.4 M2-5） |
| **H9** | Prompt 版本管理（MVP 复用 5 个 v1，P2 才新增版本） | 各 spec §"关联 Prompts" | 机械 | `prompts/` 5 份文件名带版本号；`prompt_loader.py` 加载，**代码内无硬编码 Prompt** | 架构师 | ✅ 5 个 v1 就位（S9–S13 不新增版本，plan §19.1 A）；**S6 新增 1 份 `prompts/kg_qa_v2.md`**（引用口径收窄为"只能取已注入的 `chunk-<id>`"）——按 Prompt 版本管理规范**新增版本、不覆盖 v1**，符合本条判据；`dev-doc-status.md` §5「S9~S13 复用 v1」口径**不受影响**（v2 在 S6 引入）；**S7.1 批次 A 再新增 1 份 `prompts/kg_extraction_v2.md`**（枚举参数化为 `{{entity_types}}` / `{{relation_types}}`，扩 `LEGAL_PERSON` / `ADDRESS` 与 `LEGAL_REP` / `REGISTERED_AT`，供 M4 共享法人 / 共享地址疑点；`kg_extraction_v1.md` 文件**未被修改**，单测 `test_v1_template_is_untouched` 守着），`dev-doc-status.md` §5 已同步 |
| **H10** | 契约先行 | 各 spec §"API 端点草案" + `contracts/openapi.yaml` | 机械 | `backend/`：`uv run python scripts/export_openapi.py --check`；`frontend/`：`npm run gen:api` 后 `git diff --exit-code -- frontend/src/types/api.d.ts` | CI（`contract` job） | ✅ 门禁在跑；**S7 批次 C / D 各跑一次 `gen:api` 均零 diff**；bump 1.3.0 连带重导契约（`info.version` 取自 `app_version`，不同步则必红）后仍零漂移 |
| **H11** | 准入线 C1–C3 | M4 §3 验收 6；M3 §3 验收 2 | 机械 + 人工 | 见 §5.1 | 架构师 + 用户 | ⏳ S13（评测脚本**待建**） |
| **H12** | 反证 F3 引用覆盖率 < 100% → **直接 NO-GO** | M3 §3 验收 2；M4 §3 验收 4 | 机械 + 人工 | 脚本统计"含可回溯 span 的答案数 / 总答案数"，**必须 = 1.00**；受控问题集人工复核 | 架构师 | 🟡 **S6 首次达标（F3 未触发）**：受控问题集 14 问，引用覆盖率 **100%**、拒答误伤 **0**（`scripts/eval_controlled_qset.py`）。**终局判据仍属 S10**——多跳 ≥3 跳 + 全量问题集；本轮为**演示剧本口径**（单份真机文档），不等同全量召回指标，已按 G5 在 release notes v1.2.0 §6.4 显式声明。**M4 侧首次达标（F3 未触发）**：**10 / 10** 疑点含可回溯 `:Chunk` 证据（合计 42 条，覆盖率 100%，见 §3.3 验收 4）；数据集为 6 片年报切片，**终局仍待 S13 全量样本**，已在 release notes v1.3.0 §6.7 声明 |

> **H1–H10 来自 `CODEBUDDY.md`，H11–H12 来自产品准入线**（PRD §4）。**H12 是唯一的"一票否决"项**：它不达标时不允许降级发布。

---

## 5. 准入线与反证条件

### 5.1 准入线 C1–C3（PRD §4 H11 / `02-product-outline.md` 附录 C）

| 指标 | 准入线 | 锚点 / 来源 | 判据 | 承接 | 状态 |
|---|---|---|---|---|---|
| **C1** 图谱相对 RAG 增益 | **≥ 10%** | M4 §3 验收 6；`02` 附录 C | 同一数据集跑图谱版与 RAG 基线，`(图谱 − 基线) / 基线` | S13 | ⏳ 评测脚本**待建** |
| **C2-a** 隐性关联召回 | **≥ 0.80** | M4 §3 验收 6；`01-research` §1.4 P3 | 正确识别数 / 实际植入数（gold 关系人工植入） | S13 | ⏳ |
| **C2-b** 误报率 | **≤ 0.15** | M4 §3 验收 6 | 错误识别数 / 识别出总数 | S13 | ⏳ |
| **C2-c** 引用覆盖率 | **= 1.00**（硬约束） | M3 §3 验收 2；M4 §3 验收 4 | 含可回溯 span 的答案数 / 总答案数 | S6 → S10 | 🟡 **S6 达标于受控问题集**（14 问 = 1.00）；**M4 侧 10 / 10 疑点含证据 = 1.00**（演示数据集，见 §3.3 验收 4）；S10 用全量问题集终判；**C1 / C2-a / C2-b 仍未测量** → S13 |
| **多跳答对率** | **≥ 0.80** | M3 §3 验收 1 | 3 跳内正确回答数 / 总多跳问题数 | S10 | ⏳ |
| **C3-a** 单文档处理成本 | 落入阈值（**TBD-7**） | M6 §3 验收 8；`02` 附录 C | `token_usage_total / doc_count`（每日聚合） | S13 | ⏳ |
| **C3-b** 增量 / 全量成本比 | **显著 < 1.00** | M6 §3 验收 8 | `incremental_cost / full_rebuild_cost` | S13 | ⏳ |
| **M6-b** GUI 人工确认语义 | **不得降级** | M6 §3 验收 1 / 2 | 未确认 schema **不写入** `ontology_schemas` | S12 | ⏳ |

> **TBD-7 阈值**由 plan §20.1 批次 D 在 S13 收敛（决议 **O-4**，见倒推文档 §7）。收敛前 C3 只能判"趋势"，不能判"达标"。

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
