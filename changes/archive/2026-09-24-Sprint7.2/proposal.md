# Proposal: Sprint 7.2 批次 B —— M4 疑点持久化与对外端点

> **状态**：**待你签字（2026-09-24 起草）**——本文只做规划，**未动任何代码**。签字后按 `tasks.md` 顺序执行。
> **定位**：本提案只覆盖 plan §6.2 的**批次 B（接口与表）**。批次 A 已收尾于 `changes/Sprint7.1`（数据与算法）；批次 C（前端疑点页）/ 批次 D（事件出口 `domain_events` + `EventSink`）分别由 `changes/Sprint7.3` / `7.4` 承接。
> **上游依据**：`docs/v1.1.0-demo-mvp-plan.md` §6.2 批次 B、`specs/m4-affiliation-detection.md` §4.3 / §4.4 / §4.5 / §5.5、`docs/adr/0004-integration-seams.md` §2.1（接缝 7 / 8 落 S7 批次 B）、`docs/adr/ADR-0001-async-task-backend.md` 要求 3、`docs/adr/ADR-0003-tenant-isolation-rls.md` 第 54–56 行。
> **前置依赖**：`changes/Sprint7.1` 已交付 6 片真机数据 → 10 条疑点（`Sprint7.1/integration-log.md` §7.3），本批次把它从「日志 + `suspicions.json`」搬进 PG。

## Why

批次 A 收尾留下一个**消费断点**（已登记 `backend/CODEBUDDY.md` §4 缺口 **S7.1-6**）：`risk.detect` 的产物只落在日志和对象存储 `{org}/{doc}/kg/suspicions.json`，**没有表、没有端点**，因此：

1. **疑点无人能消费**：前端（批次 C）与复核流程（状态流转 open → confirmed / dismissed）都无从下手；spec §3 验收 2「疑点状态流转落库」在 S7 收尾时无法对账。
2. **spec 已把话说死**：三张表名逐字锁死（T14 / plan §6.3 第 3 条，**S9 不得再做表结构迁移**），四个端点草案也已写好（`specs/m4-affiliation-detection.md:178-183`）——本批次是**照 spec 落地**，不是新设计。
3. **1.3.0 bump 后两条接缝从 WARN 升 ERROR**：接缝 7 `external_refs`（`PresenceRule(table=external_refs, 1.3.0)`）与接缝 8 `external_data`（`PresenceRule(path=app/services/external_data, 1.3.0)`）。**这两条正是批次 B 的登记范围**——不做则 S7 收尾 CI 必红。
4. **ADR-0001 要求 3 已被 `affiliation_tasks` 触发**：该要求规定任务状态**唯一真值源 = PostgreSQL**，且 `TaskManager.recover()` 启动时须扫 **`documents` + `affiliation_tasks` 两张表**（ADR-0001 第 43 / 73 行）。所以 `affiliation_tasks` 一旦建表就必须**同批进任务状态机**，不能建成「只写不回收」的死表。

## What Changes

1. **契约先行**：四个端点（`POST /affiliation/detect`、`GET /affiliation/tasks/{id}`、`GET /affiliation/suspicions`、`PATCH /affiliation/suspicions/{id}`）按 spec §5.5 落地；先写 `backend/app/schemas/` → `export_openapi.py` 重导出 → `npm run gen:api`（`backend/CODEBUDDY.md` §3 铁律）。
2. **三张 PG 表**（表名逐字对齐 PRD §6.2 / spec §4.3–4.5，字段亦逐字）：`affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects`，**三表均带 `org_id` 且索引以 `org_id` 打头**（ADR-0003）。
3. **`risk.detect` 产物落库**：算法返回值 → `affiliation_suspicions` 行；一次检测 = 一条 `affiliation_tasks` 记录，复用 M1 的 `TaskManager` 状态机（pending → processing → completed / failed），并纳入启动回收。
4. **接缝 7 / 8**：`external_refs` 表 + `app/services/external_data/`（导入文件 schema + 手工导入 CLI，**不建表**）——建议排在批次 B **尾段**独立 sub-batch，理由见决策点 **B6**。

## 决策点（**必须你先拍板**）

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| **B1** | **路径口径不一致**：spec §5.5 是 `/affiliation/suspicions`（与表 `affiliation_suspicions` 同源），而 `plan.md:275` 写的是 `GET /affiliation/suspects` | ① 以 spec 为准，同步改 plan 文本；② 以 plan 为准改 spec | ✅ **建议 ①**。spec 是 M4 唯一 detailed 源（含完整四端点草案），plan §6.2 是摘要（只提了一个 GET）。**不裁决就开工 = 契约按 plan 写、前端按 spec 写**，把 S6「关 Mock 仍走 Mock」的形态换个地方重演。改动只有 plan 那一行，我会连同 diff 一起给你看 |
| **B2** | `affiliation_suspicions` 表（spec §4.3）**没有 `task_id` 字段**，但有了 `affiliation_tasks` 就必须回答「`GET /affiliation/suspicions` 返回哪一批疑点」 | ① 表加 `task_id`（**偏离 spec §4.3**）；② 不加，返回当前 org 下**全部**疑点（重跑必然新旧混杂）；③ 不加，只返回**最新 completed 任务**的疑点（靠 `created_at` 判定） | ⚠️ **需你裁决**。倾向 **① 并同步补 spec**（走 ADR-0001 §「需变更点」同款的人工确认流程）：③ 靠时间判定不稳（并发 / 补跑），② 会让演示点两下就一堆重复条目。① 的代价是要走一次 spec 变更登记 |
| **B3** | `POST /affiliation/detect` 的**幂等 / 重复语义**：同一 `(org_id, kg_version)` 连点两次会怎样 | ① 每次新建任务（旧疑点留着可查）；② 命中「相同入参 + 已有 completed 任务」则复用，返回同一 `task_id` | ✅ **建议 ①**（spec §3 验收 7 的口径是「提交任务返回 task_id」；幂等由**任务**承载而非算法结果）。② 会让用户「改了图再检测」读不到新结果。副作用：**演示时点两下会有两批疑点**，须在前端 UX 消化（批次 C） |
| **B4** | `PATCH /affiliation/suspicions/{id}` 的 `reviewed_by` 写谁 | ① 取现有 dev 脚手架 `X-Actor-Id`；② 留 NULL 等 M5（S11） | ✅ **建议 ①**：`X-Actor-Id` 已在 `backend/CODEBUDDY.md` §2 登记为**限期脚手架**（非 production 生效），取它即可留痕；M5 落地后自然被 token 主体替换。**不新造 AuthProvider**（会违反 ADR-0004 §2.1 登记集合） |
| **B5** | `unaligned_subjects` 的写入点 | ① 批次 B 一并写；② **只建表不写**，等 S9 批次 D 实体对齐 | ✅ **建议 ②**。四源对齐属 S9（plan 第 580 行），现在写只能靠凑。**但必须登记**（`backend/CODEBUDDY.md` §4 + 本批次 integration-log），否则就是「表存在、永远为空」的另一种 stub |
| **B6** | 接缝 7 / 8 是否与端点同批落地 | ① 混在同批；② **拆到 B 尾段独立 sub-batch** | ✅ **建议 ②**。`external_refs` 一建表，`check_seams.py` 就按「实现集合 = 登记集合」校验；`app/services/external_data/` 一落地同样被 `PresenceRule` 命中。拆开能保证端点 + 表这批「主线」不被接缝纪律的额外红打断，也便于分别贴证据 |
| **B7** | **`risk.detect` 是否要改成上传后自动跑**（缺口 **S7.1-5**：管线无跨阶段投递） | ① 本批次顺手补投递；② **不动**，由人工 / 前端点 `POST /affiliation/detect` 触发 | ✅ **建议 ②**。**关键判断**：S7.1-5 的痛点是「阶段 A 结束后无法续投阶段 B」，而 `risk.detect` 是**终点阶段**（它后面没有阶段要续投），且 `POST /affiliation/detect` 可用请求级 `BackgroundTasks` 提交 —— 因此**该缺口不阻塞本批次**。① 属 S8 的队列改造（plan §10），现在做会显著扩 S7 diff |
| **B8**（**实施期发现，2026-09-24**） | **`TaskManager.submit()` 硬绑 `documents`**：它要求 `payload["document_id"]` 必填，**且 `task_id` 恒等于 `documents.id`**（`tasks/manager.py:75-104`）；而一次关联交易检测是**多文档**任务，`task_id` 必须来自 `affiliation_tasks.id` | ① 绕过 `TaskManager`，路由层直接 `BackgroundTasks.add_task(executor, spec)`；② **扩展 `TaskManager.submit()`**：payload 携带 `affiliation_task_id` 时走新分支（校验 `affiliation_tasks` 存在 → 落 processing → 注册执行体），不再要求 `document_id`，**现有 document 类路径零改动** | ✅ **建议 ②**。① 会违反 ADR-0001 要求 2「业务代码只依赖 `TaskManager` 接口」，把第二种任务投递写在路由层等于埋了第二个真值源；② 保持在接口内部，且对既有三种 task_type **行为不变** |

## Impact

**影响的契约（`contracts/openapi.yaml`）**：**本批次有变更** —— 新增四个 `/affiliation/*` 端点及配套 schema（`DetectRequest` / `DetectAccepted` / `AffiliationTaskStatus` / `Suspicion` / `SuspicionPatch` 等，命名由后端模型决定，导出为准）。**禁止手改 yaml**，一律走 `export_openapi.py`。

**影响的前端（`frontend/`）**：**只做两件事** —— ① `npm run gen:api` 重新生成 `api.d.ts`；② **登记 `CONTRACT_COVERED_PATTERNS`**（`frontend/src/api/client.ts:32-38`）：S6 批次 B 漏登记导致「关 Mock 下仍走 Mock」，本次必须同步。**不做疑点列表 UI**（属批次 C）。

**影响的后端（`backend/`）**：`app/db/models.py`（三张新表；**本仓库无 `app/models/` 包、无 Alembic**——ORM 单文件 + 启动 `init_db()` 的 `create_all`）、`app/schemas/affiliation.py`（新增）、`app/api/v1/routes/affiliation.py`（新增）+ `app/api/v1/router.py` 注册、`app/services/affiliation.py`（PG 侧落库与查询；批次 A 的算法模块 `app/services/kg/affiliation.py` 保持**纯算法、不掺 PG**）、`app/tasks/registry.py`（`affiliation.detect` 执行体登记）、`app/tasks/manager.py`（`recover_orphan_tasks()` 扩到 `affiliation_tasks`，ADR-0001 第 73 行）。

> **复杂列类型必须沿用既有写法**：全仓**无** `postgresql.JSONB` / `ARRAY(UUID)` / `TypeDecorator`；`kg_versions.source_doc_ids` 的既有做法是 **跨方言 `sqlalchemy.JSON` + 字符串化 UUID + 服务层双向转换**。本批次的 `doc_ids` / `entities` / `evidence` / `result_summary` 一律照抄该写法 —— 引入方言类型会让 SQLite 测试库直接建表失败。

**受影响但不改的**：`app/services/kg/affiliation.py`（纯 Cypher 算法，本批次不吸 PG 依赖）、`external_refs` / `external_data` 若按 B6 ② 则排在尾段。

## Non-goals

- **不做**疑点列表 UI / 证据链高亮交互（→ 批次 C）；
- **不做** `domain_events` 表与 `EventSink`（→ 批次 D）——但要预留：`risk.suspect_created` 是它的首个真实事件源，**落库点须写成易被订阅的形状**（事件拼接的时间戳与 `trace_id` 不能丢）；
- **不做**四源主体对齐 / `unaligned_subjects` 写入（→ S9 批次 D）；
- **不做** `:Phone` / `:Invoice` / `:Voucher` / `:Contract` 节点与其余三类算法（→ S9）；
- **不引入**任何新的 `AuthProvider` 实现 / 任务队列框架（ADR-0004 §2.1 登记集合不变）；
- **不 bump `app_version`**（仍 `1.2.0`，bump 属 S7 四批次全完后的收尾动作）。
