# P6-P0 · 集成日志（**量化 `users` 消费者缺口** —— 只读前置批，为 DR-C1 / G-23 License 铺路）

> **日期**：2026-10-06 ｜ **边界文档**：`changes/P6-P0/proposal.md`（⚠️ 草案；Non-goals **10 条**编号列表，S1 实测读到 10 条）
> **目标**：回答「`users` 缺的是什么」——**不是表没建，是主体从哪来**；产出 = 缺口量化报告 + 下一步边界坐标
> **本批零业务代码**：`git diff` 只落在 `changes/P6-P0/` 与 `docs/dev-doc-status.md`（文档）
>
> **一句话**：`users` 表**有壳、0 行、0 读者、0 写者、0 端点、0 schema**，且 `user_roles` **2/2 全是孤儿**、
> `documents.uploaded_by` **36/36 全是孤儿**、`audit_log.actor_id` **2/2 全是孤儿** ⇒ 当前 RBAC 的授权主体在
> 库里**根本不存在**。**下一步先补「主体锚点」（seed 脚本），再开 P4 License。**

---

## 0. T0 坐标复核（草案状态必做：**先复核再造结论**）

proposal §1 共 **13 条**坐标（表格 13 行；tasks.md 写「11 条」，以表格实际行数为准 —— 该处计数已漂移）。

| §1 # | 原坐标 | 本次实测 | 判定 |
|---|---|---|---|
| 1 | `models.py:773` / `:791` / `:803-815` | `773 class User(Base)`；`791 __tablename__ = "users"`；`803-815` 七字段 | ✅ |
| 2 | `app/` 下零读写（仅定义 `:773`） | `rg "\bUser\b" backend/app` ⇒ **唯一命中 `models.py:773`** | ✅ |
| 3 | `test_guardrails.py:231` / `:257` | `231 USERS_CONSUMER_MODULES: frozenset[str] = frozenset()`；`257 re.search(r"\bUser\b", ...)` | ✅ |
| 4 | `users_rows = 0`（PG 直读） | 本次实测 **0**（连接角色见 §1.1） | ✅ |
| 5 | 契约零痕迹（`:283` 断言） | `281-284` 断言契约不含 `password_hash`；`export_openapi.py --check` **零 diff** | ✅ |
| 6 | 路由 **10 个**模块（`:32-42`）；`/auth/login` 草案态 `:21` | 实测 **9 个**（`router.py:32-42` 的 import 列表：affiliation / agent / audit / compliance / cost / documents / graph / health / ontology）；`:21` 确认草案态 | ⚠️ **计数漂移 10 → 9**（**结论不变**：无 `users` / 无 `auth`） |
| 7 | `local.py:47` / `:32-38` / `:8-10`；`core/auth.py:26-32` / `:57` / `:87-90`；`rbac/deps.py:67` | `47 return LocalAuthProvider()`；`32-38` 只解析 dev token / header；`8-10` 明写「本实现仍**不查库**，接线归 P2-C」；`auth.py` **25-32** `Identity`、**57**、**88-89**；`deps.py` **68** `user_id=identity.actor_id` | ⚠️ **行号微漂移**（26→25、87-90→88-89、deps 67→68），**结论不变** |
| 8 | `config.py:27` + `.env.example:198` | `27 DEFAULT_ACTOR_ID = UUID("00000000-0000-4000-8000-0000000000aa")`；`126 default_actor_id`；`.env.example:198` | ✅ |
| 9 | `models.py:83` / `:809`；迁移 `8210590e76a5:48` / `b7c4e1f9a2d3:59` | `83 RLS_EXEMPT_TABLES = frozenset({"roles"})`（不含 users）；`809 org_id`；两迁移文件 `:48` / `:59` 均含 `"users"` | ✅ |
| 10 | 四个字段落点 | 全部命中；**另发现 3 类新落点**（脚本 / 评测 / 测试 fixture），见 §1.2 | ✅（**未穷尽**，本批补齐） |
| 11 | `ADR-0006:235` / `:294` | `235` 接缝 9「S11 落地，依赖 `users` 表」；`294`「**零代码**——`backend/` 无 `services/license/`」 | ✅ |
| 12 | 本地 `current_user = graphrag` / `rolbypassrls = True` | 本次**复现**：`graphrag` / `True` | ✅（复现，见 §1.1 可信度分级） |
| 13 | 本地 **991 passed / 11 skipped / 2 xfailed** | 本次实测 **991 passed / 11 skipped / 2 xfailed / 0 failed**（67.09s） | ✅ |

**T0 结论**：**无一条坐标失效** ⇒ 不必停下，可照本推进（两处「计数/行号漂移」已在表中订正，结论均未变）。

---

## 1. T1 只读量化（零代码，¥0）

### 1.1 真机读数（**连接角色：`current_user = graphrag`，`rolbypassrls = True**）

> 探针为**仓库外**临时脚本（`%TEMP%\p6p0_probe*.py`，`PYTHONPATH` 指向 `backend/` 后用 `engine.connect()` 只读查询）
> ⇒ **仓库内零新增文件**，`git status` 干净。
> ⚠️ 按 proposal §2 坑 4：本角色**能绕过 RLS** ⇒ ① **「行数 / 孤儿数」结论更强、可信**（绕过只会看到**更多**行）；
> ② **任何「RLS 对 `users` 是否真的拦住」的结论本地一律写「本地不可判」**，只由 CI 受限角色判。

| 读数 | 值 | 备注 |
|---|---|---|
| `users` | **0 行** | 连绕过 RLS 都只有 0 行 ⇒ 全表确为空（结论更强） |
| `users` 列（真机 `information_schema`） | **7 列**：`id / username / password_hash / org_id / status / created_at / updated_at` | ⚠️ **无 `activated_at`、无 `disabled_at`** —— 见 §1.5 |
| `user_roles` | **2 行**，`distinct user_id = 1`（两条都是 `...0000-0000-4000-8000-0000000000aa`） | 两笔分属 org `...0001` / `...0002` |
| `user_roles` 孤儿（`user_id` 在 `users` 中命中不到） | **2 / 2 = 100%** | 无 FK 校验（`models.py:892-894` 明写「**不建外键**」）⇒ 孤儿可静默存在 |
| `documents` | **36 行**，`distinct uploaded_by = 4`，**孤儿 36 / 36** | 其中 33 行 = `DEFAULT_ACTOR_ID`；另 3 个是随机 UUID |
| `audit_log` | **2 行**，`distinct actor_id = 1`（`2efb11bb-ad20-4e70-89da-0b5daf3fddf5`），**孤儿 2 / 2** | ⚠️ **不是** `DEFAULT_ACTOR_ID` ⇒ dev 口径本身也没统一 |
| `affiliation_suspicions.reviewed_by` | **0 行非空**（表 0 行） | 无实证 |
| `ontology_schemas.confirmed_by_user` | **6 行非空** | 由 `scripts/seed_attendance_ontology.py:102` 写入 |
| `users` RLS **目录事实** | `relrowsecurity = True`、`relforcerowsecurity = True`、`pg_policies` = **1 条** `tenant_isolation` / `ALL` | ⚠️ **生不生效 → 本地不可判**（bypassrls） |

### 1.2 落点穷尽（所有 `identity.actor_id` / `default_actor_id` 的**写**落点）

| # | 落点（列） | 代码坐标 | 真机状态 |
|---|---|---|---|
| 1 | `documents.uploaded_by` | `models.py:114` ← `services/documents.py:240`（`uploaded_by=identity.actor_id`） | 36 行 / **36 孤儿** |
| 2 | `affiliation_suspicions.reviewed_by` | `models.py:431` ← `api/v1/routes/affiliation.py:252` | **0 行**（无实证） |
| 3 | `audit_log.actor_id` | `models.py:664` ← `services/audit.py:131` ← `core/middleware.py:201`（`identity.actor_id`）；`services/rbac/service.py:183/202` + `services/rbac/deps.py:82`（`permission.denied`） | 2 行 / **2 孤儿** |
| 4 | `user_roles.user_id` | `models.py:894` ← `scripts/seed_dev_rbac.py:117`（`user_id=actor_id`） | 2 行 / **2 孤儿** |
| 5 | `user_roles.granted_by` | `models.py:902` ← `scripts/seed_dev_rbac.py:121` | 同上 |
| 6 | `ontology_schemas.confirmed_by_user` | `models.py:757` ← `scripts/seed_attendance_ontology.py:102` | 6 行 |
| 7 | `documents.uploaded_by`（脚本侧） | `scripts/ingest_attendance_policies.py:242` | 并入 #1 |
| 8 | 请求头入口 | `api/deps.py:53`（`x_actor_id`）/ `:70`；`core/middleware.py:18,233`；`core/auth.py:88-89` | — |
| 9 | 评测固定主体 | `app/evaluation/runner.py:110`（`ACTOR_ID` 常量）/ `:121` / `:151`（`X-Actor-Id` 头） | — |
| 10 | 测试 fixture | `tests/conftest.py:257,265,269,299,306` | — |

⇒ proposal §1 第 10 条列的 4 个落点**不穷尽**；本批补齐为 **10 类**（#6 / #7 / #9 为新增发现）。

### 1.3 `Identity` 的主体来源（T1.4）

| 项 | 证据 |
|---|---|
| `Identity` 字段 | `core/auth.py:25-32` = `org_id` / `actor_id` / `roles` / `source` ⇒ **无姓名、无邮箱、无角色来源字段** |
| `roles` 恒空 | `parse_bearer_token`（`:57`）与 `identity_from_dev_headers`（`:97`）**都不传** `roles` ⇒ 角色实际由 RBAC 现查 `user_roles`（`services/rbac/service.py:100`） |
| `actor_id` 来源 | `Bearer dev.<org_id>.<actor_id>`（`:57`）或 `X-Actor-Id` 头（`:88-89`）；缺省 `settings.default_actor_id`（`config.py:27` / `:126` / `.env.example:198`） |
| **存在性校验** | **无** —— `identity_from_dev_headers` 只做 `UUID(...)` 解析，不查库 ⇒ **请求方自报任意 UUID 都被接受** |
| `users` 表能提供的主体属性 | 真机 7 列**无 `name` / `email` / `display_name`** ⇒ 即便有行，也只拿得到 `username` |

⇒ **「第一个 user」所需字段**：`username` + `password_hash` + `org_id` + `status`（`id` / 时间戳自动生成，`models.py:803-817`）。
⇒ **若要显示姓名 / 邮箱 ⇒ 需新增列 + 迁移 ⇒ 属新批次**（见 §3 边界）。

### 1.4 开工闸门怎么开（T1.5：`USERS_CONSUMER_MODULES`）

- 判定逻辑：`test_guardrails.py:253-270`
  - `hits` = `APP_ROOT`（`backend/app`，`:49`）下所有 `.py`，**排除 `models.py`**（`:256`），正文匹配 **`\bUser\b`**（`:257`，大小写敏感 ⇒ `UserRole` / `user_id` **不算**）；
  - **正向**：`hits - 登记` 非空 ⇒ 红（**引用即红**）；
  - **反向**：`登记 - hits` 非空 ⇒ 也红（`stale`，登记必须随代码走）。
- ⇒ **闸门开法**：在 `app/` 下出现单词 `User` 的**同时**，把该模块**相对路径**写进 `USERS_CONSUMER_MODULES`（`:231`）。
- **连带条件**（注释 `:243-248` 要求，**非机械**判据，靠登记者自答）：① 归属哪条 DR；② 所需列随本批迁移补；
  ③ 接缝 1 若新增实现 ⇒ 先扩写 `ADR-0004 §2.1` 第 1 行（`0004-integration-seams.md:29`）再改 `get_auth_provider()`
  （`services/auth/local.py:41-47`）；④ 对应护栏同步转正。
- **硬约束**：`password_hash` **禁入契约**（`test_guardrails.py:282`）与日志（`models.py:786`）⇒ 新增 schema / 端点不得带该字段。
- **当前状态**：`hits = []`、`登记 = frozenset()` ⇒ 双向皆空，测试绿；**一旦有人开始用 `User`，不登记就红**。

### 1.5 新发现（proposal 未登记，直接影响 P4 License）

> **ADR-0006 §2.4 的席位口径 = `activated_at IS NOT NULL AND disabled_at IS NULL`**
> （`ADR-0006-license-control.md:115`，口径说明 `:121`；字段登记在 `0004-integration-seams.md:68`）。
> **真机 `users` 表 7 列里两列都没有**（§1.1）⇒ License 的**席位数维度当前无数据源**，
> 比 proposal §1 第 11 条写的「`users` 空表 ⇒ 席位无数据源」**更严重一层**：**补了行也还是算不出席位**。

---

## 2. T2 ·《`users` 缺口量化报告》（六维表，每格带行号证据）

| 维度 | 现状 | 证据（文件:行号） | 缺口 |
|---|---|---|---|
| **① 读**（真实读 `users`） | **0 处** | `rg "\bUser\b" backend/app` 唯一命中 = 定义处 `models.py:773`（护栏扫描排除它：`test_guardrails.py:256`）；RBAC 读的是 `user_roles` 不是 `users`（`services/rbac/service.py:100`）；认证不查库（`services/auth/local.py:32-38` + 注释 `:8-10`）；登记集合为空 `test_guardrails.py:231` | **无代码 `select(User)` ⇒ 读 = 0** |
| **② 写**（真实写 `users`） | **0 处** | `app/` 无 `User(` 构造；写侧只有 `scripts/seed_dev_rbac.py:115-121`（写的是 `UserRole`）；真机 `users` = **0 行** | **写 = 0**（唯一写入者若出现即须登记，见 §1.4） |
| **③ 端点** | **0 个** | `api/v1/router.py:32-42` 注册 **9** 个路由模块（无 `users` / 无 `auth`）；`/auth/login` 仍草案态 `:21` | **无端点**（新建端点属新批次，按 P0-D4 升级） |
| **④ schema** | **0 个** | `app/` 下无 `UserCreate` / `UserRead` 之类；契约零痕迹（`test_guardrails.py:281-284` 断言 + `export_openapi.py --check` 零 diff） | **无 schema**；且 `password_hash` **禁入**（`models.py:786` / `:282`） |
| **⑤ RLS** | 已覆盖（**目录事实**） | `users.org_id` 存在（`models.py:809`）且不在 `RLS_EXEMPT_TABLES`（`models.py:83` 只 `roles`）⇒ 属租户表；迁移显式含 `"users"`（`migrations/versions/8210590e76a5...py:48`、`b7c4e1f9a2d3...py:59`）；真机 `relrowsecurity=True` / `relforcerowsecurity=True` / 策略 `tenant_isolation`（ALL） | **缺口 = 0**（**行为侧「是否真拦住」→ 本地不可判**，本地连接角色 `rolbypassrls=True`；由 CI 受限角色 + G-26 判） |
| **⑥ 主体来源** | **不来自 `users`** | `Identity` = `org_id`/`actor_id`/`roles`/`source`（`core/auth.py:25-32`）；`actor_id` 来自 dev token（`:57`）或 `X-Actor-Id`（`:88-89`），缺省 `DEFAULT_ACTOR_ID`（`config.py:27` / `:126` / `.env.example:198`）；**无存在性校验**（`:88-89` 只 `UUID()` 解析） | **主体 = 请求方自报的任意 UUID** ⇒ `user_roles` **2/2 孤儿**、`documents.uploaded_by` **36/36 孤儿**、`audit_log.actor_id` **2/2 孤儿** |

**一句话缺口**：六个维度里 **RLS 已就绪**，其余 **五维全为 0**；根因不是「表没建」，而是「**主体锚点不存在**」——
RBAC 现在授的是一个**库里根本没有的主体**。

---

## 3. T3 · 收敛结论（**二选一，不含糊**）

### 3.1 三选一 → 收敛为 **C（先补 `users`）**

| 选项 | 判定 |
|---|---|
| **A 只做 License** | ❌ **排除**：席位数依赖 `users`（`ADR-0006:235` / `:250` / `:41-42`），且席位口径依赖 `activated_at` / `disabled_at`，**该两列当前不存在**（§1.5）⇒ A 要么席位维度落空（**假做**），要么顺手补 `users` ⇒ **A 实际不成立** |
| **B License + `users` 一批** | ❌ **排除**：一批里同时「补主体锚点（新 seed + 迁移 + 消费登记）」与「六项 License 资产 + 行为侧 403」⇒ 摊太大（drift S2 会拦），且 `users` 侧未验收就把 License 压上去，退化时无法定位 |
| **C 先补 `users`** | ✅ **采纳**：`users` 是 SSO（DR-D9）/ RBAC（DR-B9）/ License（DR-C1）**三者共同前置**（`ADR-0006:13-14`）⇒ 先补它不产生无消费者资产 |

### 3.2 下一步「可开工的最小真接线方案」（**结论选前者：给方案**）

> 建议批次号 **P6-P1**（本批**不开工**，只给坐标）。

**第一步 · 造第一个 user（三条途径的取舍）**

| 途径 | 成本 | 机械可验证 | 是否越界 | 判定 |
|---|---|---|---|---|
| **① seed 脚本**（`scripts/seed_dev_users.py`，或扩写 `seed_dev_rbac.py`） | **最小**：1 个脚本 / 1 条 INSERT | ✅ `users` 行数 0→≥1；孤儿数 2→0 | **否**（不新建端点 / schema / 注册流程） | ✅ **建议采纳** |
| ② 注册端点（`/auth/register`） | 大：端点 + schema + 口令策略 + 契约 | ✅ | **是**（= 新建端点 + schema + 注册流程） | ⏸ **按 P0-D4 升级用户**，本批/下一批不自主开工 |
| ③ SSO（DR-D9 / P2-C） | 大：接缝 1 第二实现 + ADR-0004 §2.1 扩写 | ✅ | **是**（属另一批；`local.py:8-10` 明写接线归 P2-C） | ⏸ 不在本序列 |

**第二步 · 让 dev 主体指向真实行（最小改动）**

- 以**固定 UUID** `DEFAULT_ACTOR_ID`（`config.py:27`）作为该 dev user 的主键插入 ⇒
  `user_roles` 孤儿 **2 → 0**（`seed_dev_rbac.py:117`）、`documents.uploaded_by` 中 33 行孤儿 → **0**，
  **无需改任何业务代码**，纯数据侧即可闭环。
- `password_hash` 由脚本生成并**只落库**，**不落日志、不进契约**（`models.py:786` / `test_guardrails.py:282`）；
  脚本沿用 `seed_dev_rbac.py:75-81` 的 **dev 闸门**（`ALLOW_DEV_ORG_HEADER` 未开即拒执行）。

**第三步 · 登记（漏任一侧 CI 必红）**

- 消费模块登记进 `USERS_CONSUMER_MODULES`（`test_guardrails.py:231`），并按 `:243-248` 交代四件事（DR 归属 / 迁移 / ADR-0004 §2.1 / 护栏转正）。

**明确不做（三条边界，防「假差异」重演）**

1. **不新增 `/auth/register` 端点、`UserCreate` / `UserRead` schema、注册流程** ⇒ 那属新批次（P0-D4）。
2. **不预置 `activated_at` / `disabled_at`** —— 虽是 `ADR-0006 §2.4` 席位口径的依赖列，但 ADR-0006 `:123` 明写
   「**MVP 内该字段存在但消费者只有 License 一处**」⇒ 提前补就是**无消费者字段**（预留纪律第 6 条，
   历史病例 `task_retry_multiplier` / P6-O 的 `domain_profile`）⇒ **随 P4 License 同批补**。
3. **不强行给 `audit_log.actor_id` 造主体** —— `models.py:639` 明写「系统触发没有操作者时**不编造 UUID**」⇒ 保持 nullable。

**⚠️ 该方案不宣称什么**：第一步只补**主体锚点**（数据完整性，**读维仍为 0** —— 仍无代码 `select(User)`）。
`users` 的**第一个真实读者**由 **P4 License 席位计数**（`ADR-0006:115`）或 **P2-C SSO** 提供 ⇒
若 P6-P1 想让「读」维转正，须新增真实读取点 ⇒ **那是新批次，按 P0-D4 停下**。

---

## 4. 验收判据逐条（proposal §6，5 条全机械）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| ① | 六维表每格有行号证据；查不到写「未查到」 | §2 六格 **全部有坐标**；无「未查到」格（RLS 行为侧按 §2 坑 4 写「**本地不可判**」，非猜测） | ✅ |
| ② | 真机读数齐 | `users` **0 行**；`user_roles` **2 行** / 孤儿 **2（100%）**；并附带 `documents` 36 行 / 孤儿 36、`audit_log` 2 行 / 孤儿 2；**连接角色已标注**（`graphrag` / `rolbypassrls=True`） | ✅ |
| ③ | **零代码改动** ⇒ 契约 zero diff / pytest 不减 / ruff / `check_seams` ERROR 0 | `export_openapi.py --check` **零 diff**；`pytest` **991 passed / 11 skipped / 2 xfailed / 0 failed**（= 基线，**不减**）；`ruff check` **All checks passed**、`ruff format --check` **237 files already formatted**；`check_seams` **ERROR 0 / WARN 0 / OK 10**（含「Settings 全部 55 个字段均有消费者」）。<br>**CI 终裁（R-10）**：提交 **`692cc8c8`** ⇒ run **`37450050163`** 四 job **全 success**（契约校验 / 后端 ruff+pytest / 前端 lint+gen:api / 流水线汇总）；后端 job **`112224160692`** 实测 **997 passed / 5 skipped / 2 xfailed**（= CI 基线，**不减、0 回归**） | ✅ |
| ④ | drift 的 S1 读到 **10 条** Non-goals | `check_session_drift.py` ⇒ **S1 读到 10 条**，且来源批次 = **`changes/P6-P0/`**（草案目录最近活跃） | ✅ |
| ⑤ | T3 结论二选一不含糊 | §3.2 **给出可开工的最小真接线方案**（seed 途径 + 固定 UUID 锚点 + 登记），并点名**唯一需用户拍板的项** = 「注册端点 / schema / 注册流程」与「让读维转正」属新批次 | ✅（选前者） |

---

## 5. 登记同步与「不许外推」

- **同步**：`docs/dev-doc-status.md` §0 追加 P6-P0 段 + §8 新增 **R29**（`users` 主体锚点缺失 + 席位口径两列不存在）。
- **不许外推（逐条）**：
  - G-18 绿 **≠** 账号体系落地（`users` 仍 **0 消费者**，需求基线 `:228`）—— 本批**未**宣称落地；
  - G-24 绿 **≠** 真实账号的权限体系 —— 其授权主体 `user_roles.user_id` **2/2 是孤儿**，库里没有这个主体；
  - `users` 有 RLS（目录事实）**≠** 隔离生效 —— 行为侧**本地不可判**，归 CI 受限角色。
- **本批未修**：R28（本地有图口径 8 条环境债）—— 按 Non-goal 第 8 条，本批只用 §1.1 的「角色可信度分级」把它隔离。

## 6. 升级情况

**0 起**。四类升级条件逐条对照：① 结论不要求新建端点 / schema / 注册流程（seed 途径即可）⇒ 不升级；
② 未改 Non-goals 任一条；③ 五条判据全部机械达成；④ §1 坐标**大面积有效**（仅 2 处计数 / 行号微漂移，已就地订正）。
