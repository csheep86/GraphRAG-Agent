# P3-A 集成日志 —— PG 侧租户隔离 RLS（2026-10-04）

| 项 | 内容 |
|---|---|
| 批次 | **P3-A**（PG 侧租户隔离），P3-B（图谱侧）**不在本批** |
| 任务清单 | `changes/P3/tasks.md`（56 项，全勾） |
| 上游证据 | `changes/P3/proposal.md`、ADR-0003 §3.2 / §3.3 / §3.7 / §4.1 |
| 纪律 | 未改 ADR-0003 / 需求基线**原文**（R5），差异一律追加登记；未放宽任何判据 |

---

## 1. 实测数字（**前后都是真跑出来的**）

### 1.1 起跑基线

```
853 passed / 3 skipped / 4 xfailed        # uv run pytest
接缝 OK 10                                 # uv run python scripts/check_seams.py
export_openapi.py --check 零漂移
RLS 零实现：backend/ 下 CREATE POLICY / ROW LEVEL SECURITY / SET LOCAL / current_setting 均 0 命中
```

### 1.2 收束

```
878 passed / 3 skipped / 3 xfailed        # uv run pytest（连跑 3 轮一致）
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 217 files left unchanged
uv run python scripts/check_seams.py → 接缝 OK 10（ERROR 0）
uv run python scripts/export_openapi.py --check → 零漂移
uv run python scripts/check_startup_readiness.py → G-26 已生效 [OK]（10 条）、G-10 已生效 [OK]
```

**差值来源（+25 / xfailed −1）**：

| 变化 | 条数 | 说明 |
|---|---|---|
| 新增 G-26 | +23 | `tests/test_guardrails_rls.py`：六条判据 + 3b + 迁移一致性 + **真跑迁移** + 14 张表逐表参数化 |
| 新增 A5 行为用例 | +1 | 执行体的 org 来自 `TaskSpec`（非默认租户） |
| G-10 摘 xfail | +1 passed / −1 xfailed | 见 §8 |

### 1.3 提交

| # | hash | 内容 |
|---|---|---|
| 1 | `2720b0a` | A1/A2/A3/A4/A5/A6/A7 + A9/A10 的测试侧（迁移、逐事务 GUC、依赖图、系统通道、任务 org、受控探测、破损用例逐个修） |
| 2 | `f043ba6` | G-26 新增 + G-10 转正 + CI 双角色 + 需求基线登记 + `.env.example` |

### 1.4 一次偶发（如实登记）

第一轮全量跑时 `test_migrations_baseline.py::test_upgrade_head_matches_metadata` 红过 **1 次**；
随后**连跑 3 轮全量 + 单跑该用例**均绿，**未能复现**。嫌疑方向：临时库（scratch DB）
的建/删在同一进程内被并发连接池牵连。**未做任何"让它变绿"的改动**。登记备查。

---

## 2. P0 前置实测（不许猜）

| 项 | 实测结果 |
|---|---|
| P0-1 | `uv run alembic heads` → **`7d2e91f4ab35`**（单一 head）⇒ 新迁移 `8210590e76a5` 的 `down_revision` 取该值 |
| P0-2 | **14 张**含 `org_id` 的表（逐表核对 `models.py`）：`documents` / `relation_expiry_policies` / `kg_versions` / `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects` / `entity_merge_candidates` / `external_refs` / `domain_events` / `audit_log` / `qa_logs` / `ontology_schemas` / `users` / `user_roles`；**`roles` 是唯一豁免** |
| P0-3 | `app.current_org` **只**来自认证态：请求侧 `identity.org_id`（接缝 1 `AuthProvider.authenticate`），任务侧 `TaskSpec.org_id`（创建时的认证态）。**不**从 body / query / header 的租户字段取（header 仅用于 dev 身份注入，且须经 `authenticate()`） |

**表清单不手工抄**：`app/db/rls.py::tenant_tables()` 由 `Base.metadata` 推导（有 `org_id`
列且不在 `RLS_EXEMPT_TABLES`）⇒ 新增带 `org_id` 的表**自动**进清单；漏落策略会立即被
G-26 叫住。迁移里那份清单是**复制**的（迁移不该 import 应用代码，否则历史产物会随代码
漂移），复制的漂移由 `test_g26_migration_table_list_matches_metadata` 机械盯住。

---

## 3. 落地清单（按 A 编号）

| 项 | 落点 | 结果 |
|---|---|---|
| **A1** | `migrations/versions/8210590e76a5_rls_tenant_isolation_policies.py` | 14 张表逐张 `ENABLE` + `FORCE` + `tenant_isolation` 策略（`USING` / `WITH CHECK` 同为 `org_id = current_setting('app.current_org', true)::uuid`）；幂等（`DROP POLICY IF EXISTS`）；`downgrade()` 删策略 + `NO FORCE` + `DISABLE`；豁免表 `roles` **显式**保持无策略 |
| **A2** | `app/db/session.py` | `after_begin` 事件在**每个新事务**重放 `set_config('app.current_org', …, is_local=true)`（与 `SET LOCAL` **语义等价**（PG 文档），但可绑定参数、不必把 UUID 拼进 SQL）；`info` 里没 org ⇒ **不发** GUC ⇒ 查不到行（fail-closed） |
| **A3** | `app/api/deps.py` | `DbSession` 改为 `Depends(get_tenant_session)`，而 `get_tenant_session` **依赖 `CurrentIdentity`** ⇒ RBAC 在路由体之前查 `user_roles` 时 org 已就位（坑 1） |
| **A4** | 见 §4 登记表 | 6 处登记点全部**照绑 org**，无一处开旁路 |
| **A5** | `app/tasks/types.py` + `registry.py`（8 处）+ 2 个创建点 | `TaskSpec.org_id` **必填**；执行体 `open_session(org_id=spec.org_id)` |
| **A6** | `app/tasks/manager.py` | `recover_orphan_tasks` / `list_in_flight_task_ids` 改「枚举租户 → 逐租户设 org」；**未**给应用账号 `BYPASSRLS`（裁决 3） |
| **A7** | `app/db/rls.py` + 3 处调用点 | 受控函数 `app.tenant_row_exists`（见 §6） |
| **A8** | `tests/test_guardrails_rls.py` + 需求基线登记 | G-26，见 §7 |
| **A9** | `.github/workflows/ci.yml` + `scripts/init_rls_roles.py` | 见 §9 |
| **A10** | `conftest.py` / `pg_scratch.py` / 6 个测试文件 | 见 §10 |
| **A11** | `tests/test_guardrails.py` | G-10 转正，见 §8 |

---

## 4. 系统通道登记表（A4）

登记依据：需求基线 §229 第 4 条——绕过必须登记，否则日后被当范例照抄。
**结论：6 个登记点全部选择「① 绑 org」**，无一处需要「② 登记为无需 org 的系统通道」。

| # | 入口 | org 来源 | 处置 |
|---|---|---|---|
| 1 | `app/core/middleware.py`（审计中间件） | 接缝 1 解析出的 `identity.org_id`（**认证态**） | 绑（`open_session(org_id=identity.org_id)`） |
| 2 | `app/core/exception_handlers.py`（限流审计） | 同上 | 绑 |
| 3 | `app/services/agents.py`（DR-B12 逃生阀审计，全系统**唯一**可关闭隔离的开关） | 问答请求入参里的 `org_id`（本批未改其来源，保持原语义） | 绑 |
| 4 | `app/tasks/registry.py`（5 个执行体 + 3 个 `_do_*`） | `TaskSpec.org_id` | 绑 |
| 5 | `app/tasks/manager.py`（投递 / 回收 / 对账） | `TaskSpec.org_id`；回收与对账走**受控枚举**（§6 之 `app.list_tenant_orgs()`） | 绑 / 逐租户 |
| 6 | `app/services/external_data/cli.py`（CLI） | `--org-id` 显式入参（不给默认值、不猜） | 绑 |

**额外收口（提案里没列，但同属坑 4）**：`backend/scripts/` 下 8 个运维脚本
（`seed_*` / `ingest_*` / `backfill_*` / `probe_temporal_state`）原先直接 `SessionLocal()`，
RLS 后会**静默读不到 / 写不进**。已全部改为显式绑 org（种子/回填类绑 `settings.default_org_id`，
入图类绑脚本入参 `org_id`），并在每处留下 A4 注释。

---

## 5. A5：历史任务（payload 无 org）的处置

- **结论：无需回填**。`TaskSpec` 只在**进程内在途**存在（`FastAPI BackgroundTasks`），从不
  持久化；任务的持久化真源是 `documents` / `affiliation_tasks` 行，而这两张表**本就有
  `org_id`**（迁移前即存在，不是本批新增的列）。
- **防"静默失败"**：`org_id` 做成**必填字段**（无默认值）⇒ 漏传在**构造处**就 `TypeError`，
  不会拖到执行体里变成"记录不存在"。`TaskManager.get_status()` 同步加成必填 `org_id` 参数
  （若不强制，RLS 下"没设租户"会被误读成"任务不存在"）。

---

## 6. A7：受控绕过登记（**全案唯一**）

### 6.1 为什么必须有它

契约 `openapi.yaml:2867 / 3121 / 3193 / 3055` **明文**要求「跨租户 = **403** 而非 404」。
RLS 生效后应用账号看不到别租户的行，「不存在」与「存在但不属于本租户」在应用层**无法区分**
（都是空集）。⇒ 保留 403 就必须有一条**只回答"存在 / 不存在"**的受控通道（裁决 1）。

### 6.2 受控函数

| 函数 | 返回 | 用途 | 调用点（G-26 判据 6 机械比对） |
|---|---|---|---|
| `app.tenant_row_exists(text, uuid)` | **boolean**（不返回 `org_id`、不返回任何行数据） | 404 / 403 判别 | `app/services/documents.py`、`app/services/affiliation.py` |
| `app.list_tenant_orgs()` | `SETOF uuid`（只返回 org_id） | A6 启动回收 / 对账的租户枚举（裁决 3） | `app/tasks/manager.py` |

约束（每条都有独立断言）：表白名单、**只**返回 boolean / org_id 集合、`SECURITY DEFINER`、
`SET search_path = pg_catalog, pg_temp`、`REVOKE … FROM PUBLIC` 后仅 `GRANT EXECUTE` 给 `app_rls`。

### 6.3 ⚠️ 一个必须说清的技术事实：`rls_probe` 角色带 `BYPASSRLS`

| 事实 | 说明 |
|---|---|
| **为什么** | ADR-0003 §3.2 要求 `FORCE ROW LEVEL SECURITY`，而 **`FORCE` 会让表 owner 同样受策略约束**。于是 `SECURITY DEFINER` 挂在普通角色（含 owner）下时，函数体内**依然查不到**别租户的行——403 语义无从判定。`BYPASSRLS` 是 PG 里唯一的解法（`row_security=off` 同样要求该属性）。 |
| **收窄到什么程度** | `rls_probe`：`NOLOGIN`（无人能以它连库）+ `BYPASSRLS`；名下**只有**上面两个函数；`SELECT` 权限**只**给白名单这 3 张表。它是**全案唯一**的非超级用户 `BYPASSRLS` 角色——G-26 判据 6 逐条点名。 |
| **应用账号没受影响** | 应用/业务测试账号 `app_rls` 仍是 `NOBYPASSRLS`、非超级用户、非表 owner（判据 4 断言）。系统通道（§4）**没有**一个走这个旁路——它们都绑 org。 |

### 6.4 白名单实测扩到 3 张表（不是提案里的 2 张）

| 表 | 契约依据 |
|---|---|
| `documents` | `openapi.yaml:2867 / 3121`（文档详情 / 状态：跨租户 **403**） |
| `affiliation_tasks` | `openapi.yaml:3193`（任务详情） |
| `affiliation_suspicions` | `openapi.yaml:3055`（疑点复核：明文「疑点不存在 → 404，跨租户 → **403**」） |

第三张是**跑出来的**（`test_review_cross_tenant_suspicion_is_403` 变红才暴露），不是随手加的。
少任何一张都是**契约破坏性变更**。白名单的每次扩大都必须同时满足：契约明文 + 更新
`PROBE_TABLES` 注释里的依据行 + G-26 判据 6 自动跟上（它比对的是常量本身）。

---

## 7. G-26：判据与实测结果

文件：`backend/tests/test_guardrails_rls.py`（23 条）。编号按需求基线现有最大号 **G-25 + 1**
登记（实测 G-26 未被占用）。

| # | 判据 | 实测 | 判红时会说什么 |
|---|---|---|---|
| 1 | 每张租户表 `relrowsecurity` **且** `relforcerowsecurity` 为真 | ✅ 14/14 | 点名哪张表漏 `ENABLE` / 漏 `FORCE`（"不 FORCE 则 owner 绕过"） |
| 2 | 策略谓词**不得**为 `true`，且必须引用 `app.current_org` | ✅ 14/14 | 点名表 + 策略名 + 表达式 |
| 3 | **行为**：受限角色不设 org ⇒ **0 行**；设 org ⇒ 只看到本 org | ✅ | 见下方"为什么用裸连接" |
| 3b | 绑了 org 的 Session 在**每个新事务**重放 GUC；`commit()` 后事务级 GUC **必须失效** | ✅ | 区分 `SET LOCAL` 与会话级 `SET`（后者只有并发才测得出来） |
| 4 | 应用账号 `rolbypassrls=false`、非超级用户、非表 owner、且必须是 `app_rls` | ✅ | 直接报"用超级用户跑 ⇒ 结论全是假的" |
| 5 | 豁免集合**恰好** = `RLS_EXEMPT_TABLES`（只有 `roles`）；库里 `roles` 确实**没**装 RLS、没策略 | ✅ | 豁免被扩大即红 |
| 6 | 受控绕过足够窄：只有 2 个登记函数、都是 `SECURITY DEFINER`、属主 `rls_probe`（`NOLOGIN`）、函数体引用的表 ⊆ 白名单、非超级用户 `BYPASSRLS` 角色**恰好** `{rls_probe}`、调用点**恰好**等于登记集合 | ✅ | 多一个函数 / 多一张表 / 多一个调用点都红 |

**附加（超出六条，但都是"别再出恒绿"）**：

- `test_g26_migration_table_list_matches_metadata`：迁移里写死的清单 == 元数据推导结果
  （新增带 `org_id` 的表而没改迁移 ⇒ 红）。
- `test_g26_migration_applies_rls_on_scratch_db`：**真跑一遍 `alembic upgrade head`** 后断言
  策略在库里——只比对文件内容会被"文件写了但 SQL 写错"骗过；这是生产升级路径的端到端证明。
- `test_g26_per_table_policy_present`（参数化 14 条）：让 CI **指名道姓**报哪张表漏了。

### 7.1 判据 3 为什么用裸连接（关键设计）

conftest 有一条**测试脚手架**（§10.1）给"直接建 Session"的用例预置默认租户。
走 `Session` 的断言会被它救活 ⇒ 判据 3 **刻意用 `engine.connect()` + `set_config`**，
绕开脚手架，**不可能被糊弄**。

### 7.2 反向验证（护栏不是恒绿）

| 破坏动作 | 结果 |
|---|---|
| 把 14 张表的 RLS 全拆（`DROP POLICY` + `NO FORCE` + `DISABLE`）**并**停掉夹具的落策略 | 判据 1 / 2 / 3 + 逐表参数化 **全红**（判据 4/5/6 与迁移用例仍绿——它们不依赖测试库状态，符合预期） |
| 停掉 GUC 下发（`set_config` 换成空语句） | G-26 与 G-10 所在文件**红** |

两次破坏**都已还原**，`git diff` 确认无残留。

---

## 8. G-10 转正与断言口径修正

- 顺序：先让用例**真通过**（strict xfail 下 XPASS ⇒ FAILED 即证据），**再**摘 `@pytest.mark.xfail`
  ——不是只删标记。
- ⚠️ **断言口径改了（修正，不是放宽）**：

  > 原断言：「B org 的响应 `items == []`」。
  > **该断言在正确实现下恒不成立**：这 24 个并发请求**本身就是 B 的请求**，
  > 中间件会在响应后为 B 各写一条审计 ⇒ 靠后的 B 请求理应看到靠前的 B 行——那是
  > B **自己的**数据。「空」既不是隔离的目标，也不是隔离的结果；把它当判据，
  > 本例在正确实现下依然红，**永远转不了正**。
  >
  > 新判据：并发前给两个 org 各插一条**可区分的标记行**（`tenant.marker.a` / `tenant.marker.b`），
  > 每个响应 **必须**看到本 org 的标记、**绝不能**看到对方的标记。既判"串没串"，
  > 也不依赖并发调度的偶然顺序。

---

## 9. CI 变更（A9 / 裁决 4）

- **两个角色**（`scripts/init_rls_roles.py`，须一次超级用户连接）：
  - `app_owner`：建表 / 跑迁移 / 落策略（表 owner，仍是 `NOBYPASSRLS`）
  - `app_rls`：`NOBYPASSRLS`、非超级用户、非 owner —— **业务测试一律用它连库**
- **没走** `docker-entrypoint-initdb.d` 挂载：那会让角色/函数 DDL 出现第二份真源，必然漂移。
  改为在 Pytest 前加一步 `uv run python scripts/init_rls_roles.py --admin-url <超级用户串>`，
  **CI 与本地同一份代码、同一条命令**。
- job 级 env：`DATABASE_URL`（app_rls）/ `DATABASE_URL_OWNER`（app_owner）。
- `tests/conftest.py` 与 `tests/pg_scratch.py`：建表 / 建库 / 迁移走 owner，业务查询走受限角色。
  连不上时报错信息直接指向"先跑 `init_rls_roles.py`"。

**为什么非两个角色不可（实测）**：本机/CI 的默认库用户（`docker run -e POSTGRES_USER=graphrag`）
就是**超级用户**（实测 `rolsuper=true / rolbypassrls=true`）——超级用户**绕过一切 RLS**。
用它跑业务测试 = T1 / T2 / G-26 全部在"没装 RLS"的前提下通过，绿得毫无意义。
G-26 判据 4 就是拦住这件事的（用超级用户连接 ⇒ 该断言必红）。

---

## 10. 测试侧改动登记（A10）

### 10.1 ⚠️ 登记一条**测试脚手架**：「默认租户绑定」

`tests/conftest.py` 新增 `autouse` 夹具 `default_org_for_bare_sessions`：在 `sessionmaker`
上预置 `info["tenant_org_id"] = settings.default_org_id`。

- **为什么**：RLS + FORCE 之后，直接 `SessionLocal()` 的会话没绑 org ⇒ 业务表一行都看不到、
  一行都写不进（fail-closed）。既有用例里有一大批是「直接建 Session 造数据 + 直接查库
  断言」的**单元测试形态**，它们不经过 HTTP 请求，也就没有认证态可以给 org。逐个塞身份 =
  把整批单元测试改写成集成测试，改动量与回归风险都不可接受。
- **边界**：用例自己显式绑 org 的（`session_scope(org_id=…)` / `open_session(org_id=…)`）
  **不受影响**；没绑的落到默认租户。
- **它不验什么**（与既有 `rbac_default_actor_is_admin`、`pg_active_kg_version` 同一类脚手架边界）：
  它让"忘了绑 org"在测试里不至于全红，**因此不能用来证明"某条应用路径的租户绑定是对的"**。
  租户绑定由两处机械证明：① G-26 判据 3（裸连接，绕开本脚手架）；② A5 行为用例
  （用**非默认** org 的任务跑通 ⇒ org 来自 `TaskSpec`，不是默认值）。
- **反向风险已堵**：写**别的租户**的数据会被 `WITH CHECK` 直接拒绝 ⇒ **响亮失败**，
  不是静默串号（本批全部破损用例都是这样暴露出来的）。

### 10.2 逐条登记：改了哪些既有测试、为什么

| 文件 | 改动 | 为什么 |
|---|---|---|
| `tests/conftest.py` | 建表/落策略改走 **owner** 引擎；两个 org 的 `user_roles` **各绑各的 org** 播种 | 受限角色无权 DDL；跨租户写会被 `WITH CHECK` 拒 |
| `tests/pg_scratch.py` | `owner_url()`：建库 / 迁移 / `create_all` 走 owner | 受限角色无 `CREATEDB`，也不该有 |
| `tests/test_guardrails.py` | `clean_audit` 改**逐租户**清理；G-10 断言口径改标记行（§8） | 只清默认 org 会留下 B 的历史行 ⇒ T1 断言**假红**（看起来像泄漏） |
| `tests/test_audit.py` | `empty_audit_log` 改逐租户清理 | 同上 |
| `tests/test_agent_fail_closed.py` | 查/删 `AuditLog` **显式绑**请求 org | 不依赖脚手架解释行为（A10 明列项） |
| `tests/test_ontology.py`（5）/ `test_kg_versioning.py`（7）/ `test_domain_events.py`（3）/ `test_graph_overview_and_entity.py`（3） | 每个用例用**独立 org** ⇒ 会话绑到**本用例的 org** | 写哪个租户就绑哪个租户；`_seed_row`/`_insert_*` 按行的 `org_id` 绑 |
| `tests/test_affiliation_endpoints.py`（6） | 插入/清理/断言按 org 绑；清理拆成两个 org 各一次 | 同上 |
| 4 个执行体测试 + `test_document_date_flow.py` | `TaskSpec` 补 `org_id`；`_do_parse` / `_do_extract` 的 double 签名补 `org_id` | A5：org 必填 |
| `tests/test_document_parse_executor.py` | 新增 A5 行为用例（非默认 org 任务跑通 + 反向：别的 org 看不到） | 证明 org 来自 `TaskSpec`，兜住 §10.1 脚手架的盲区 |

**没有**为了省事把任何表加进豁免集合（Non-goals 第 3 条）。

---

## 11. 未决事项 / 风险（**不隐瞒**）

| # | 事项 | 等级 | 说明与建议 |
|---|---|---|---|
| 1 | **`deploy/docker-compose.yml` 仍以超级用户 `graphrag` 作为应用连库账号** | **高** | 超级用户**绕过一切 RLS** ⇒ 按当前 compose 部署，**RLS 在生产形态下等于没装**。本批未动 compose（不在 P3-A 的 Non-goals 内、且会牵动部署单元）。**建议下批**：compose 增加一次 `scripts/init_rls_roles.py`（或用 init 容器），backend 的 `DATABASE_URL` 切到 `app_rls`。在改之前，"部署形态已隔离"**不得宣称**。 |
| 2 | 图谱侧（Neo4j）未隔离 | 高（已知） | P3-B；本批不覆盖，G-26 判据也只覆盖 PG 侧 |
| 3 | A7 白名单扩到 3 张表 | 中 | 契约驱动（§6.4），已登记 + 断言跟随；若日后契约去掉 403 语义，应**反向收窄**白名单 |
| 4 | `rls_probe` 带 `BYPASSRLS` | 中 | §6.3 论证了必要性（`FORCE` 使 owner 也受约束）；已收窄到 `NOLOGIN` + 两个函数 + 3 张表；G-26 判据 6 点名盯住 |
| 5 | 运维脚本（8 个）默认绑 `settings.default_org_id` | 低 | 单租户部署无差别；多租户下需显式传 org（已留注释） |
| 6 | 一次未复现的迁移用例偶发红 | 低 | §1.4，登记备查 |

---

## 12. 复现命令（本机 / CI 同路径）

```bash
# 0) 起库（PostgreSQL 16.x）
docker run --rm -d -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag \
  -e POSTGRES_DB=graphrag -p 5432:5432 postgres:16-alpine

# 1) 建角色 + 受控函数 + 落 RLS（须超级用户连接；CI 里是 Pytest 前的独立步骤）
cd backend
uv run python scripts/init_rls_roles.py \
  --admin-url postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test

# 2) 门禁
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run python scripts/check_seams.py
uv run python scripts/export_openapi.py --check
uv run python scripts/check_startup_readiness.py
```

生产升级路径（**漏跑 = 库里没有隔离，且不报错**）：

```bash
uv run alembic upgrade head       # 迁移 8210590e76a5 内含 ENABLE + FORCE + 策略
```
