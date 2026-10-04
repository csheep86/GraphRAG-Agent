# P3-A 任务清单 —— PG 侧租户隔离 RLS 落地

| 项 | 内容 |
|---|---|
| **批次** | **P3-A**（PG 侧租户隔离）｜原 P3 已按裁决拆为 **P3-A / P3-B** |
| **日期** | 2026-10-04 |
| **状态** | ✅ 五项裁决已定（见 §1），**未动任何代码** |
| **上游** | `changes/P3/proposal.md`（证据与八个坑）、ADR-0003 §3.2 / §3.3 / §3.7 / §4.1 |
| **需求** | DR-B4（RLS 全量）、DR-B5（应用层防线常设）、DR-B7（T2）、DR-B8（`SET LOCAL`）、DR-B12 附带 |
| **起跑基线** | `pytest` **853 passed / 3 skipped / 4 xfailed**；接缝 OK 10；契约零漂移；RLS **零实现** |

---

## 1. 裁决记录（2026-10-04，用户拍板，不再重开）

| # | 议题 | **裁决** |
|---|---|---|
| 1 | 跨租户 403 / 404（坑 6） | ✅ **保留 403**。契约 `openapi.yaml:3121 / 3193 / 2867 / 1910` 明文要求跨租户 = 403 且写「**而非 404**」⇒ 改 404 是**契约破坏性变更**。服务层那次「不带 org 的存在性探测」改为**受控通道**（A7） |
| 2 | 后台任务 org（坑 3） | ✅ **`TaskSpec` 携带 `org_id`**（可信来源 = 任务创建时的身份）。**不**给执行体开绕过口子 |
| 3 | 启动回收等运维跨租户操作（坑 5） | ✅ **枚举租户 + 逐租户设 org**。**不**给 `BYPASSRLS` 角色 |
| 4 | CI 会不会"全绿但 RLS 未被验证"（坑 7） | ✅ CI 建**两个角色**：owner 建表 / 迁移，受限角色跑业务测试 |
| 5 | 拆分 | ✅ **拆 P3-A（本批）/ P3-B**（图谱侧 + CI Neo4j + G-9 补齐，与 G-25 共用工程项） |

---

## 2. P0 前置（**不许跳过，不许猜**）

- [x] **P0-1**：`uv run alembic heads` **实测**确认当前 head，**不照抄**本文档里的 revision 号；新迁移的 `down_revision` 以实测为准
- [x] **P0-2**：逐表核对**含 `org_id` 的表清单**（以 `backend/app/db/models.py` 为准，不照抄提案的"14 张"）
  - **已确认**：`users` **含** `org_id`（`models.py:809` + `ix_users_org_id_status`）⇒ 需建策略
  - **已确认**：`roles` 是**唯一豁免**（`models.py:842` `__rls_exempt__ = True`，G-24 三条断言盯住）⇒ **不建策略**，且不得扩大豁免集合
  - 其余按 P0-2 实测清单逐表建；**漏表 = 整表跨租户可见**（需求基线 §226 第 1 条）
- [x] **P0-3**：确认 `app.current_org` 的取值来源——**只能**来自认证态（ADR-0003 §3.3），**严禁**从 body / query 读

---

## 3. A1 迁移：RLS 策略（DR-B4）

- [x] 新 Alembic 迁移，`down_revision` = **P0-1 实测 head**
- [x] **幂等且可重跑**（DR-E1 + `tests/test_migrations_baseline.py` 会跑）：`DROP POLICY IF EXISTS` 后再 `CREATE POLICY`；`ENABLE` / `FORCE` 用 `ALTER TABLE ...`（幂等）
- [x] 每张租户表：
  1. `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY`
  2. `ALTER TABLE <t> FORCE ROW LEVEL SECURITY` —— ⚠️ **不可漏**：不 FORCE 则**表 owner 绕过策略**，RLS 形同虚设（ADR-0003 §3.2 ①）
  3. `CREATE POLICY ... USING (org_id = current_setting('app.current_org', true)::uuid)`
     - ⚠️ **未设 org 时必须查不到任何行**（fail-closed）：`current_setting(..., true)` 返回 NULL ⇒ 比较为 NULL ⇒ 不命中 ✓
     - ⚠️ **禁止** `USING (true)`（ADR-0003 §3.3：「假装有隔离，比没有更危险」）
- [x] `roles` **不建**策略（豁免已由 G-24 声明并断言）
- [x] `downgrade()` 完整可逆（删策略 + 关 RLS），不得留半成品

---

## 4. A2 `SET LOCAL` 落点（DR-B8 / 坑 2）

- [x] `app/db/session.py`：注册 `Session` 级 **`after_begin`** 事件，从 `session.info["org_id"]` 读取并 `SET LOCAL app.current_org`
- [x] **每个新事务都要重放**：⚠️ `documents.py:246-248` 的场景——`commit()` 后 `refresh()` 会**另起事务**，只在 `get_session()` 设一次**不够**（`SET LOCAL` 事务级）
- [x] **非请求 Session**（直接 `SessionLocal()`，坑 4 那 7 处）：`info` 无 org ⇒ **不设** ⇒ 查不到行（fail-closed），不得静默放行
- [x] 读会话：`session.info["org_id"]` 是唯一来源，**不得**新增第二个来源

---

## 5. A3 依赖图顺序（坑 1）

- [x] 把「身份解析 → session 绑定 org」做成**统一依赖图**
- [x] 保证 `app/services/rbac/deps.py:61-69` 查 `user_roles` 时 **org 已就位**（RBAC 在路由体**之前**执行 ⇒ 在路由体里设 org **太晚**）
- [x] `deps.py:83-85` 的 `CurrentIdentity` / `DbSession` 两个独立依赖必须串起来

---

## 6. A4 系统通道逐点登记（坑 4）

以下**绕开请求依赖直接建 Session** 的入口，逐点二选一：① 绑 org；② **显式登记为系统通道并写明原因**
（登记依据：需求基线 §229 第 4 条——绕过必须登记，否则日后被当范例照抄）

- [x] `app/core/middleware.py:193-208`（审计中间件）
- [x] `app/core/exception_handlers.py:110-128`（限流审计）
- [x] `app/services/agents.py:327-340`（agent fail-open 审计；连带 **DR-B12 逃生阀围栏**——该处是可配置关闭隔离的**唯一**开关，须显式登记 + 落审计）
- [x] `app/tasks/registry.py:109 / 318 / 597 / 703`
- [x] `app/tasks/manager.py:99-205`
- [x] `app/services/external_data/cli.py:75-85`
- [x] 登记位置：`changes/P3/integration-log.md` 的「系统通道登记表」

---

## 7. A5 后台任务携带 org（坑 3）

- [x] `app/tasks/types.py:40-46` 的 `TaskSpec` **增加 `org_id`**
- [x] 创建任务时从**可信身份**取 org（不从 payload 取）
- [x] `app/tasks/registry.py:106-113` 执行体：开 Session 后**先设 org** 再查询
- [x] **历史任务记录**（payload 无 org）：给出回填或处置方案并登记，**不许静默失败**——否则 RLS 后合法任务被误判成"记录不存在"

---

## 8. A6 启动回收改为逐租户（坑 5）

- [x] `app/main.py:31-38` 启动时 `recover_orphan_tasks()`；`app/tasks/manager.py:183-205` 当前**不带 org** 批量更新所有租户
- [x] 改为：**枚举租户 → 逐租户设 org → 回收**
- [x] **不得**为此给应用账号开 `BYPASSRLS`（裁决 3）
- [x] 若枚举在租户规模上不可接受：登记实测数据，**报 BLOCKED 等我裁**，不许自行放开

---

## 9. A7 保留 403 语义（坑 6 / 裁决 1）

- [x] `app/services/documents.py:321-346` 与 `app/services/affiliation.py:78-95` 的「**第二次不带 org 的存在性探测**」换成受控通道
- [x] 受控函数必须同时满足（每条都要有断言）：
  1. **只返回 boolean**（存在 / 不存在），**不返回** `org_id` 或任何行数据
  2. **表白名单**（防止被当成任意表的 bypass）
  3. `SECURITY DEFINER` 且 `SET search_path` 收紧
- [x] **单独一条护栏**断言该函数未被扩大使用（只服务上述两处、白名单未变）
- [x] ⚠️ 这是全案**唯一一个为保契约语义引入的受控绕过**：必须与业务查询**完全隔离**，并在集成日志显式登记理由

---

## 10. A8 新增护栏（**关键，别漏**）

> **为什么必须新增**：需求基线第 206 行自认「B4（RLS 全量）**无独立断言**」，靠 G-9 / G-10 **间接**覆盖。
> 但 **T1 通过 ≠ RLS 生效**——**应用层 `org_id` 过滤**（DR-B5 常设防线）本就能让 T1 / T2 全绿。
> ⇒ 没有独立断言的话，P3-A 的"RLS 落地"**无法机械证明**，且会重复 G-2 / G-14 的恒绿教训。

- [x] 新增护栏 **G-26（RLS 策略机械断言）**，编号按需求基线现有最大号 **G-25 + 1** 登记（若开工时发现已占用则顺延，并在基线文档写明）
- [x] 判据（建议，可微调但**不得放宽**）：
  1. P0-2 清单中每张表：`relrowsecurity = true` **且** `relforcerowsecurity = true`（查 `pg_class`）
  2. 每张表存在 `USING` 策略，且**策略表达式不是** `true`（禁止 `USING (true)`）
  3. **行为侧**：以**受限角色**连库 —— 不设 org ⇒ 查不到任何行；设了 org ⇒ **只**看到本 org 的行
  4. **应用账号 `rolbypassrls = false`**（ADR-0003 §3.2 要求 2：非 owner、非 superuser、无 BYPASSRLS）
  5. 豁免集合 == `RLS_EXEMPT_TABLES`（当前只含 `roles`），**扩大即红**
  6. A7 的受控函数存在且**未被扩大使用**
- [x] 同步需求基线文档（`docs/delivery-requirements-and-guardrails.md`）：B4 行（把「无独立断言」改为 G-26）、B 组汇总行、挂起清单
- [x] ⚠️ **新护栏可挂起，但不得为转绿而放宽判据**

---

## 11. A9 CI 双角色（坑 7 / 裁决 4）

- [x] `.github/workflows/ci.yml` 的 `postgres` service 加初始化脚本，建**两个角色**：
  - `app_owner`：建表 / 跑 Alembic 迁移 / 建策略（表 owner）
  - `app_rls`：**`NOBYPASSRLS`**，业务测试用它连库
- [x] 业务测试一律走 `app_rls` ⇒ 否则 **owner 跑测试 = RLS 从未被验证**（假绿）
- [x] 与 `tests/conftest.py` 的建表路径（`Base.metadata.create_all`）对齐：**建表用 owner、查询用受限角色**

---

## 12. A10 测试夹具改造（坑 8）

以下夹具**直接访问租户表且没设事务租户**，`FORCE` 后会失败或只看到一个租户：

- [x] `tests/conftest.py:185-208`（直接向两个 org 写 `user_roles`）
- [x] `tests/test_guardrails.py:64-73`（全表删 `audit_log` / `qa_logs`）
- [x] `tests/test_agent_fail_closed.py:171-188`（直接查删 `AuditLog`）
- [x] 改造原则：走 **A4 登记的系统通道**，或显式设 org；**不得**为了省事把表加进豁免集合

---

## 13. A11 G-10 转正（出口）

- [x] `test_g10_t2_concurrent_requests_do_not_cross_tenants`（24 请求 / 8 并发）**先真通过**（strict xfail 下 XPASS ⇒ FAILED 即证据），**再**摘 `@pytest.mark.xfail`
- [x] ⚠️ **只删 xfail 标记不算转正**
- [x] 若转不了正：**如实挂起**，并在集成日志写清卡在哪（**不许**放宽判据或标 `local_only`）

---

## 14. Non-goals（本批**不做**）

- ❌ **不移除**应用层 `org_id` 过滤（DR-B5 / ADR-0003 §3.7：双防线并存，RLS 生效后**也不拆**）
- ❌ **不写** `USING (true)`（ADR-0003 §3.3 明令禁止）
- ❌ **不新增** RLS 豁免表（唯一合法豁免 = `roles`；`users` **含** `org_id`，是租户数据）
- ❌ 不做 **P3-B**：图谱侧真实 Neo4j 跨 org 用例、CI 起 `neo4j` service、`documents` / `qa_logs` / `storage_key` 的 T1 补齐、G-25
- ❌ 不做 P2-C（SSO）、P4（License）、G-23
- ❌ 不改 ADR-0003 原文（守 **R5**，差异追加登记）
- ❌ 不为出口**放宽**任何既有判据

---

## 15. 出口判据

- [x] **G-26 常驻**（A8 六条判据全绿，且**在受限角色下**验证）
- [x] **G-10 转正**（A11）
- [x] `pytest` **不退化**：起跑 853 passed / 3 skipped / 4 xfailed ⇒ 结束时 **passed 不减**，xfailed 数 ≤ 4
  - ⚠️ 若因 A4 / A10 必须改既有测试，**逐条登记**在集成日志（改了哪条、为什么）
- [x] `ruff check .` / `ruff format --check .` 双绿
- [x] `export_openapi.py --check` **零漂移**（A7 是为保契约语义而做，**契约不得改**）
- [x] `check_seams.py` ERROR 0（本批不改接缝签名）
- [x] **CI 双角色下全绿**（A9）
- [x] 集成日志 `changes/P3/integration-log.md`：实测前后数字、系统通道登记表、A7 受控绕过登记、G-26 判据与实测结果

---

## 16. 已知风险（开工时先复验）

| 风险 | 落点 |
|---|---|
| `FORCE` 后大量既有测试暴露（坑 7） | A9 + A10；先跑一次**只开 ENABLE 不开 FORCE** 摸底？—— **不许**：那会产出假绿。直接开 FORCE，逐个修 |
| 后台任务历史 payload 无 org（A5） | 回填方案或登记 BLOCKED，**不许静默失败** |
| 迁移在 CI 的 PG 上跑（A1） | `test_migrations_baseline.py` 已在 PG 临时库跑 ⇒ 迁移必须幂等 |
| `SECURITY DEFINER` 被扩大（A7） | A8 判据 6 独立断言 |
