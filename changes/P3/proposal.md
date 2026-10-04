# P3 提案 —— 租户隔离 RLS 落地（DR-B4 / B5 / B7 / B8 + G-9 补齐 / G-10 转正）

| 项 | 内容 |
|---|---|
| **批次** | P3（租户隔离） |
| **日期** | 2026-10-04 |
| **状态** | ✅ **已裁决（2026-10-04）**：五项**全部采纳**下表「我的建议」列（含拆分）。**裁决后仍未动任何代码**，待 `changes/P3/tasks.md` 落地后开工 |
| **执行顺序出处** | `changes/P2/tasks.md` 第 10 行：P2-B → P2.5 → **P3** → P2-C → P4 → P5 → P6 |
| **前置** | DR-B1（切 PG）已就位 ⇒ ADR-0003 §3.6 的依赖已解除，P3 **可做** |

---

## 0. 起跑状态（**实测**，本次逐项查证）

| 项 | 实测结果 |
|---|---|
| RLS 实现 | **零**：`backend/` 下 grep `CREATE POLICY` / `ROW LEVEL SECURITY` / `SET LOCAL` / `current_setting` = **0 命中** |
| `SET LOCAL` 落点 | **不存在**：`app/db/session.py` 无 event listener、无 `SET`、无 pool 配置（全文仅 71 行） |
| 豁免表 | 仅 `roles`（`models.py:76-83` `RLS_EXEMPT_TABLES = frozenset({"roles"})`；G-24 已断言该边界） |
| 需 RLS 的表 | **含 `org_id` 的业务表 14 张**（`documents` / `relation_expiry_policies` / `kg_versions` / `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects` / `entity_merge_candidates` / `external_refs` / `domain_events` / `audit_log` / `qa_logs` / `ontology_schemas` 等；逐表清单开工时以 `models.py` 为准） |
| 跨租户**常驻**测试 | **11+ 条**（`test_documents.py:147`、`test_affiliation_endpoints.py:267/279/368`、`test_document_chunk_endpoint.py:112`、`test_graph_and_agent_routes.py:167`、`test_audit.py:149/219`、`test_storage.py:52`、G-9 等） |
| 仍 xfail | **仅 G-10**（T2 并发，24 请求 / 8 并发） |
| 图谱侧 | 服务层**已有实现**（`validate_kg_version_tenant_boundary` / `KG_TENANT_LEAK`），但测试**全部打桩** ⇒ **无真实 Neo4j 跨 org 子图用例** |
| 基线 | `pytest` 853 passed / 3 skipped / **4 xfailed**；接缝 OK 10；契约零漂移 |

---

## 1. 权威口径（逐字引用，本提案不重开已决问题）

| 出处 | 原文要点 |
|---|---|
| **ADR-0003 §3.2** | 三条硬要求：① **`FORCE ROW LEVEL SECURITY`**（否则表 owner 绕过 ⇒ RLS 形同虚设）；② 应用使用**非 owner、非 superuser** 的受限角色（`BYPASSRLS=false`）；③ **每事务 `SET LOCAL app.current_org`**（**必须 `SET LOCAL`**，否则连接池复用串租户） |
| **ADR-0003 §3.3** | `org_id` 从**认证态 token** 解析，**严禁**从 body / query 读；中间件在**事务开启后、业务查询前**执行 `SET LOCAL`；**禁止把策略写成 `USING (true)`**——那是"假装有隔离，比没有更危险" |
| **ADR-0003 §3.7** | 应用层 `org_id` 过滤**不得因 RLS 存在而移除**（信创降级退路）⇒ **双防线并存** |
| **ADR-0003 §4.1** | 必补两类测试：**T1**（跨 org 越权 → 空或 403）、**T2**（并发不串租户，须覆盖连接池复用） |
| **DR-B4** | RLS 全量落地：**各业务表 `ENABLE` / `FORCE` + 事务内 `SET LOCAL app.current_org`** |
| **DR-B11** | 图谱侧（Neo4j）**没有 RLS** ⇒ 应用层过滤是**唯一**防线（不是冗余防线） |
| **基线 §278 / §97** | G-9 转正**只**代表应用层过滤生效，**不代表** RLS 落地；**禁止**因 G-24 绿而宣称"隔离已靠 RBAC 完成" |

---

## 2. ⛔ 八个已识别的坑（**均有代码证据**，不是猜测）

查证过程中逐条定位。前四个是**结构性**的，P3 绕不开。

### 坑 1：`get_session()` 拿不到身份，且在 RBAC 之后才轮到它
- `app/api/deps.py:83-85`：`CurrentIdentity` 与 `DbSession` 是**两个独立依赖**
- `app/services/rbac/deps.py:61-69`：RBAC 会在**路由体执行前**就用 DB session 查 `user_roles`
- ⇒ 若在路由体里设 `session.info["org_id"]` **太晚**（RBAC 查询已发生）
- **处置建议**：把「身份解析 → session 绑定租户」做成**统一依赖图**，保证 RBAC 查询之前 org 已就位

### 坑 2：`SET LOCAL` 每次 commit 后失效
- `app/services/documents.py:246-248`：`session.commit()` 后紧跟 `session.refresh(document)` ⇒ **开启新事务**
- `SET LOCAL` 只在当前事务有效 ⇒ 只在 `get_session()` 设一次**不够**
- **处置建议**：org 存入 `session.info`，在 **`Session` 的 `after_begin` 事件**中对**每个新事务**重放 `SET LOCAL`；同时覆盖直接 `SessionLocal()` 创建的非请求 Session

### 坑 3：**后台任务没有 request org 上下文**
- `app/tasks/types.py:40-46`：`TaskSpec` 只有 `task_type / payload / trace_id`，**不携带 org**
- `app/tasks/registry.py:106-113`：执行体**另开 Session** 再用主键裸查 `db.get(Document, document_id)`
- ⇒ RLS 启用后，**合法任务会被误判成"记录不存在"**（静默失败）
- **处置建议**：`TaskSpec` **显式携带可信 `org_id`**（任务创建时从身份取得），执行体开 Session 后先设 org。**不能**依赖请求 ContextVar 自动传播

### 坑 4：**大量绕开请求依赖、直接建 Session 的路径**
`app/core/middleware.py:193-208`（审计中间件）、`app/core/exception_handlers.py:110-128`（限流审计）、
`app/services/agents.py:327-340`（fail-open 审计）、`app/tasks/registry.py:109/318/597/703`、
`app/tasks/manager.py:99-205`、`app/services/external_data/cli.py:75-85`
- ⇒ **只改 `get_session()` 会漏掉这些入口**
- **处置建议**：逐点登记并接入同一租户绑定机制（或显式登记为系统通道）

### 坑 5：**启动回收是天然的跨租户系统操作**
- `app/main.py:31-38` 启动时调用 `recover_orphan_tasks()`；`app/tasks/manager.py:183-205` **不带 org** 批量更新所有租户的 `documents` / `affiliation_tasks`
- ⇒ RLS 后要么回收看不到任何行，要么为恢复功能给应用账号开过大旁路
- **处置建议**：见**待裁 3**

### 坑 6：**403 语义会被 RLS 改成 404**（**最需要裁决的一条**）
- `app/services/documents.py:321-346`：先带 `org_id` 查 → 未命中 → **再不带 org 探测存在性** → 存在则 **403**
- `app/services/affiliation.py:78-95`：同款模式
- RLS 生效后，**第二次探测同样看不到别的租户** ⇒ 原 403 自然变 **404**
- ⇒ 上表 **11+ 条常驻测试会直接变红**（`test_cross_tenant_access_returns_403` 等）
- **处置建议**：见**待裁 1**

### 坑 7：**表 owner 绕过 ⇒ CI 可能"全绿但 RLS 未被验证"**
- CI 用同一个 `graphrag` 用户建库并访问（`.github/workflows/ci.yml:60-82`）；测试启动直接 `Base.metadata.create_all(bind=engine)`（`session.py:47-57`）
- 若只做 `ENABLE` 不做 `FORCE` ⇒ **owner 绕过策略，测试全绿但什么都没验证**（本仓最忌的假绿）
- 开了 `FORCE` ⇒ 大量未设 org 的直接 Session 测试会暴露
- **处置建议**：见**待裁 4**

### 坑 8：**测试夹具直接访问租户表，没设事务租户**
- `tests/conftest.py:185-208`（直接向两个 org 写 `user_roles`）、`tests/test_guardrails.py:64-73`（全表删 `audit_log` / `qa_logs`）、`tests/test_agent_fail_closed.py:171-188`（直接查删 `AuditLog`）
- ⇒ `FORCE` 后这些 fixture / 清理会失败或只看到一个租户
- **处置建议**：区分「业务测试」与「RLS 自身测试」；前者改造为带 org 的受控通道，后者**专门断言策略生效**

---

## 3. ✅ 已裁决（2026-10-04）——四项**全部采纳**下表「我的建议」列

> 用户裁决：**"待裁决的内容按你建议来"**。故下表「我的建议」列即**最终决定**，不再另写结果列。

### 拆分也已裁决 ✅

用户同时采纳「**拆成 P3-A / P3-B**」。本批只做 **P3-A（PG 侧）**；P3-B（图谱侧真实用例 + CI Neo4j + G-9 补齐）随 G-25 工程项，不阻塞 P3-A。

| # | 冲突 | 选项 | 我的建议 |
|---|---|---|---|
| **1** | **跨租户 403 → 404**（坑 6） | (a) 改成 **404**；(b) 保留 **403**，另开一条**极窄的受控存在性探测**通道 | ✅ **(b)** —— **已查证，不是偏好问题**，见 §5：契约**明文且反复**要求跨租户 = 403，甚至写了「**而非 404**」。改 404 是**契约破坏性变更**，与"零漂移"纪律冲突。故必须保留 403 ⇒ 服务层那次「不带 org 的存在性探测」得换成受控通道（建议 `SECURITY DEFINER` + **表白名单** + **只返回 boolean**，并由**单独一条护栏**断言它未被扩大使用） |
| **2** | **后台任务如何带 org**（坑 3） | (a) `TaskSpec` 携带 `org_id`（可信来源 = 任务创建时的身份）；(b) 执行体用系统角色绕过 | ✅ **(a)**：不新增绕过口子；且任务本就属于某租户 |
| **3** | **启动回收 / 运维类跨租户操作**（坑 5） | (a) **枚举租户 + 逐租户设 org**；(b) 专用 `BYPASSRLS` 运维角色；(c) 严格审计的系统策略 | ✅ **(a)**：少一个 bypass 口子（ADR-0003 §3.2 要求 2 的精神是**收紧**）。若租户数增长后性能不可接受再议 (b) |
| **4** | **CI 里 RLS 会不会"假绿"**（坑 7） | (a) CI 建**两个角色**：owner 建表 + **受限角色**跑测试；(b) 沿用单一用户 | ✅ **(a)**：否则 P3 出口不可信——**owner 跑测试 = RLS 从未被验证**，与本仓 G-2 / G-14 的教训同源 |

### 附带请示：**P3 要不要拆成两批？**

**建议拆。** 理由：P3 是迄今**最大**的一批——14 张表 + 依赖图改造 + 后台任务 + 运维通道 + 11+ 条测试语义裁决 + CI 角色改造，远超 P2-B（两张表）与 P2.5（两个文件）。

| 建议分批 | 内容 | 出口 |
|---|---|---|
| **P3-A（PG 侧）** | 14 张表 `ENABLE`+`FORCE` 策略、`SET LOCAL` 落点（`after_begin`）、依赖图改造、后台任务 org、启动回收、CI 受限角色、RLS 自身断言 | **G-10 转正** + RLS 策略护栏转正 |
| **P3-B（图谱侧 + G-9 补齐）** | `documents` / `qa_logs` / `storage_key` 的 T1 用例、**真实 Neo4j 跨 org 子图用例**（现全部打桩）、CI 起 `neo4j` service（与 **G-25** 共用同一工程项） | G-9 **全部**转正 |

理由：G-9 图谱侧**必须** CI 起 Neo4j 才能真断言（基线 §169 明令"在 CI 起 Neo4j 之前不得声称已由 CI 验证"），而它与 G-25 共用工程项 ⇒ 合并做更省，不该卡住 P3-A。

---

## 4. Non-goals（本批**不做**）

- ❌ **不移除**应用层 `org_id` 过滤（ADR-0003 §3.7：双防线并存，RLS 生效后也不拆）
- ❌ **不写 `USING (true)`**（ADR-0003 §3.3 明令禁止）
- ❌ **不新增 RLS 豁免表**（当前唯一合法豁免是 `roles`；`users` / `ontology_schemas` **不是**豁免表）
- ❌ 不做 P2-C（SSO）、P4（License）、G-23
- ❌ 不改 ADR-0003 原文（守 **R5**，差异追加登记）
- ❌ 不为 P3-A 的出口**放宽**任何既有判据（若 G-10 转不了正，就如实挂起）

---

## 5. 待裁 1 的**事实查证结论**（已在写提案时完成，**推翻了我原本的倾向**）

我原本倾向"改成 404（资源隐藏更安全）"，但查完契约后**必须改口**——这是**契约事实**问题，不是偏好问题：

| 契约位置 | 原文 |
|---|---|
| `contracts/openapi.yaml:3121` | 「疑点不存在（`NOT_FOUND`）。**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1）」 |
| `contracts/openapi.yaml:3193` | 同上（检测任务）：「**跨租户访问返回 403 而非 404**」 |
| `contracts/openapi.yaml:2867`（`info.description`） | 「跨租户访问一律 `403 FORBIDDEN`」 |
| `contracts/openapi.yaml:1910` | `FORBIDDEN: 跨租户访问被拒（ADR-0003：org_id 不符），非本租户资源一律拒绝` |
| `contracts/openapi.yaml:1908` | `ENTITY_NOT_FOUND: …**与跨租户 403 区分**` |
| 多处 `403` response description | 「跨租户访问被拒（`FORBIDDEN`，ADR-0003 §3.3 / M5 §3 验收 1）」 |

⇒ **契约是"资源隐藏"的反向选择**：它**故意**用 403 暴露"资源存在但你无权"，且明文排除 404。
⇒ 因此 P3 **不得**借 RLS 顺手把 403 改成 404；那等于**用基础设施改动偷换契约语义**。

**推荐落法**：把 `documents.py:321-346` / `affiliation.py:78-95` 的「第二次不带 org 的探测」
换成一条受控函数，且**必须**满足三条（每条都要有断言）：
1. **只返回 boolean**（存在 / 不存在），**不返回** `org_id` 或任何行数据；
2. **表白名单**（防止被当成任意表的 bypass）；
3. **单独一条护栏**断言该函数未被扩大使用。

⚠️ 这是本提案里**唯一一个"为保留契约语义而引入的受控绕过"**，按 ADR-0003 §3.2「应用账号不得 bypass」的精神，它必须与业务查询**完全隔离**，并在日志中显式登记理由。

---

> ⚠️ 本文件仅做查证与建议。**裁决前不动任何代码**。
> 数据来源：本次对 `backend/` 的定向检索 + 一次 thorough 代码探索（表清单 / session / 依赖图 / 图谱侧 / 测试分布 / 逃生阀 / 迁移 / CI 八项），结论均附文件行号，可复核。
