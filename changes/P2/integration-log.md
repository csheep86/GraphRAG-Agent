# P2 实测集成日志

> **定位**：事后实测证据。事前计划见 [`proposal.md`](./proposal.md)、任务清单见 [`tasks.md`](./tasks.md)。
> 三者不可互相替代——**计划写"打算怎么做"，日志写"实际发生了什么"**。
>
> 批次：**P2-A（DR-B13 `users` 表）**｜日期：2026-10-01
> 追加批次：**P2-B（DR-B9 RBAC 三粒度）**｜日期：2026-10-03（无人值守）⇒ **§5 起**
> 环境：Windows 11 + Docker Desktop + `postgres:16-alpine` + Python 3.11 / uv

---

## 0. 起跑状态（`check_startup_readiness.py` 实测）

已生效 **8** 条、部分生效 **2** 条、挂起 **4** 条、开工地雷 **4** 项，
其中 **「users 表已建（DR-B13，P2 第一步）」= ❌**；G-18 与 G-24 均为 xfail 挂起。

---

## 1. P2-A 实测

### 1.1 表结构（PG 16 真机，`changes/P2/probe_users_migration.py`）

```
users 列       = ['created_at', 'id', 'org_id', 'password_hash', 'status', 'updated_at', 'username']
users 索引     = [['org_id'], ['org_id', 'status'], ['username']]
users 唯一约束 = [['username']]
users 检查约束 = ["status::text = ANY (ARRAY['active', 'disabled'])"]
alembic_version = a1f3c9d27b08
```

三条与 expected 完全一致：7 列（逐字照 `specs/m5-permission-audit.md` §4.1）、
`org_id` 打头索引（ADR-0003 §3.1）、`username` 唯一（spec §4.1）。

### 1.2 迁移三步走（同一个脚本，`downgrade base` 之外补了「只退一步」）

| 步骤 | 实测 |
|---|---|
| `upgrade head` | 13 张表，`users` 在列；`alembic_version = a1f3c9d27b08` |
| `downgrade b3e5a1c70d42`（**退一步**） | 12 张表，`users` 消失，**其余表不受影响** |
| 再 `upgrade head`（重放） | 13 张表，`users` 回来 ⇒ 不是单行道 |

为什么要单独验「退一步」：`tests/test_migrations_baseline.py` 只验了 `downgrade base`
（全退到空）——**退一步的安全性没人验**，而现场回滚正是退一步，不是退到零。

### 1.3 G-18 转正（不是"只删 xfail"）

建表后 `test_g18_users_table_exists` 由 **XFAIL 变 XPASS(strict) ⇒ FAILED**（CI 必红），
这与 P1-C 处理 G-8 / G-9 的情形相同。**同时把判据补强**到四条：

1. 表存在；
2. 列集合 **逐字等于** spec §4.1 的 7 列（不多不少）；
3. 有 `org_id` **打头**的复合索引（ADR-0003 §3.1）；
4. `username` 有唯一约束。

只摘标记不动判据的话，删掉 `org_id`、改名 `username`，G-18 依然绿 —— 那是假防御。
另加 `test_g18_password_hash_is_not_in_public_contract`：敏感字段不得出现在契约里。

**反向确认（不得假设）**：`test_g24_rbac_three_granularity_matrix` 仍 **XFAIL**
—— 它的 missing 列表虽然划掉了 `users`，但 RBAC 主体（`roles` / `user_roles` /
端点强制校验）依旧零代码 ⇒ 本批**没有**把 P2-B 逼上台面。

### 1.4 RK-4 机械化：「G-18 转正 ≠ 账号体系落地」（你 2026-10-01 交代）

只写进文档的边界**三个月后没人会翻**，而 G-18 的绿灯**看起来**就像"用户体系做完了"。
所以做了两层机械处置（对应 proposal RK-4）：

| 层 | 做法 | 实测 |
|---|---|---|
| **看得见** | `check_startup_readiness.py` 新增 `SCOPE_CAVEATS`，G-18 绿灯**正下方**印出：⚠️ 只验「users 表存在且形状正确」——它当前 0 消费者；SSO / RBAC / License 分属 P2-C / P2-B / P4 | 已实测打印出来（G-18 = 3 项） |
| **拦得住** | `test_g18_users_consumers_are_registered`：`app/` 下任何引用 `User` 的模块必须先登记进 `USERS_CONSUMER_MODULES`（**当前为空**），并交代 ① 归属哪条 DR ② 所需列随本批迁移 ③ 接缝 1 是否需扩写 ADR-0004 §2.1 ④ 护栏是否同步转正；反向也查「登记了却无引用」的僵尸登记 | **注入验证**：临时加一个引用 `User` 的文件 ⇒ 测试 **红**；删除后转绿 ⇒ 它真在拦，不是恒绿 |

与 CODEBUDDY.md「预留必须有登记」是同一条纪律，只是这里拦的是**引用**而不是字段。
它**不**拦"表还没人用"——那正是本批预期；它拦的是"有人开始用了却没登记、没交代归属"。

### 1.5 环境项（你 2026-10-01「改吧，未来也不用 sqlite 了」）

本机 `backend/.env` 的 `DATABASE_URL`：`sqlite:///./dev.db` ⇒
`postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag`（实测
`get_settings().database_url` 已读成 PG）。该文件不进 git，改它只影响本机。
⚠️ **本机 dev 库要重建**：切过去后旧 SQLite 数据自然弃用，首次使用跑
`uv run alembic upgrade head` 建表（旧 `dev.db` 我没删，留在 `backend/` 等你处置）。

### 1.6 陈旧口径同步（三类，都不动 ADR 原文）

| 位置 | 原口径 | 处置 |
|---|---|---|
| `app/services/auth/local.py:5` | 「users 表按 **T10** 裁决不建」 | 改为「T10 已被 **DR-B13** 推翻；users 已于 P2-A 建表；**本实现仍不查库**，接线归 P2-C」。**不删** T10 原始记录 |
| `docs/delivery-requirements-and-guardrails.md` | DR-B13 行「❌ 未建」、G-18 行「🟡 骨架已就位」、§3.1 B13 行「待建」、§5 状态清单 | 全部更新为 ✅ 已建 / 已生效，并登记三条差异与遗留 |
| `docs/delivery-plan.md` §4 注 / §8.1 | 「ORM 12 张，没有 users」 | 标注为**开工前快照**，P2-A 后已 13 张 |

`ADR-0003` §3.1 第 77 行「`users` 本批次未建」**未动** —— 守 **R5**（不篡改 ADR 原文），
差异与状态登记在 `delivery-requirements-and-guardrails.md` §5 的 📌 三条里。

---

## 2. 收尾三件套

| 检查 | 起跑 | P2-A 后 |
|---|---|---|
| `uv run pytest -q` | 710 passed / 3 skipped / **8 xfailed** | **713 passed / 3 skipped / 7 xfailed**（G-18 从 xfailed 转 passed，另新增 G-18 两条：敏感字段 / 消费者登记；**无失败**） |
| `ruff check .` / `ruff format --check .` | 双绿 | 双绿（186 files） |
| `check_startup_readiness.py` | 已生效 8 条、地雷 4 项 | **已生效 9 条**（G-18，**3 项**）、**地雷 3 项**，「users 表已建」✅；G-18 绿灯下方新增边界提示（§1.4） |
| `export_openapi.py --check` | 零漂移 | **零漂移**（本批 Non-goals 要求契约零 diff，实测达成） |
| `check_seams.py` | ERROR 0 / OK 10 | ERROR 0 / OK 10（未受影响） |
| `check_session_drift.py` | 指向 `changes/P1` | 指向 `changes/P2/proposal.md`（8 条边界） |

> ⚠️ 新迁移文件**不进 lint**：`backend/pyproject.toml` 的 `[tool.ruff] extend-exclude = ["migrations"]`
> 早已裁决（autogenerate 产物人工审阅入库，等价性由 `test_migrations_baseline.py` 钉死）。
> 单独跑它会报 UP035 / I001 —— 与既有 5 个迁移文件同形态，**不是**本批引入的。

---

## 3. 遗留（**不在本批边界内**）

| # | 事项 | 去向 |
|---|---|---|
| 1 | `username` 按 spec 取**全局 unique**，与多租户「同名不同 org」存在张力 | 若真出现，单开一批改 `(org_id, username)` 复合唯一（proposal RK-2） |
| 2 | `documents.uploaded_by` / `ontology_schemas.confirmed_by_user` **未**加指向 `users.id` 的外键 | 演示库已有真实数据，补 FK 属**不可逆**清洗；随 P2-C 首次真实账号链路一并处理 |
| 3 | `users` 表**仍 0 消费者** | 接线分属 P2-B（RBAC）/ P2-C（SSO）/ P4（License） |
| 4 | PG 容器 `graphrag-pg` 仍在跑（`-p 5432`），本地 pytest 需要它 | 不用时 `docker stop graphrag-pg`（`--rm` 会自动删除） |
| 5 | 本机残留旧 SQLite 文件 `backend/dev.db`（2.1 MB）与 `_alembic_empty.db`（280 KB） | 切 PG 后已无用途；**我没删** —— 若要清理等你一句话 |
| 6 | P2-B / P2-C 接线时**必须先登记** `USERS_CONSUMER_MODULES` | 判据已就位（§1.4），登记即那批的开工闸门 |

---

## 4. 边界声明（写在最后，防止被日后外推）

- **G-18 转正 ≠ 账号体系落地**。本批只证明「`users` 表存在且形状正确」：
  它没有登录、没有权限、没有席位，三者分别归 **P2-C / P2-B / P4**。
- **本批没有动任何认证语义**：`LocalAuthProvider` 仍走 dev token / dev header，
  **不查库**（一查全线测试就红）；接缝 1 的实现集合仍是 `{LocalAuthProvider}`，
  改它必须先扩写 ADR-0004 §2.1（否则 CI 必红）。
- **范围已守死**：契约零 diff、零 API、零 CRUD —— `users` 此刻是一张**没有被调用的表**，
  这是「先解阻塞」的有意为之，不是半成品。

---
---

# P2-B — DR-B9 RBAC 三粒度（2026-10-03）

> 批次：**P2-B**｜日期：2026-10-03｜**无人值守**批次（无人类 CR 环节）
> 环境：Windows 11 + Docker Desktop（`graphrag-pg` = `postgres:16-alpine`，Up 11h）+ Python 3.11 / uv

## 5. 起跑状态（实测，非引用文档）

| 项 | 起跑（P2-B 开工前实测） |
|---|---|
| `pytest -q` | **818 passed / 3 skipped / 7 xfailed**（实测） |
| `check_startup_readiness.py` | 已生效 **9** 组 / 部分生效 **2** 组 / 挂起 **4** 组（含 **G-24**）/ 反向守卫 1 条 |
| G-18 | ✅ 已生效（P2-A）；`USERS_CONSUMER_MODULES` = **空集**（0 消费者） |
| `Contracts` | `export_openapi.py --check` 零漂移 |

---

## 6. 实际做的 vs 计划的差异

| # | 计划 | 实际 | 差异性质 |
|---|---|---|---|
| 1 | `roles` 表 | ✅ 已建（`id / name / description` + `ck_roles_name` 四档 + `uq_roles_name`） | 无 |
| 2 | `user_roles` 表 | ✅ 已建（含 `doc_scope` / `scene_scope`，索引 `org_id` 打头） | **类型收敛**：spec 写 JSONB ⇒ 用 SQLAlchemy `JSON`（理由见 §7.3） |
| 3 | 路由层强制校验入口 | ✅ `app/services/rbac/deps.py::require_permission`，挂在 **10 个**端点 | **覆盖范围是新增决策**（计划没指定挂几个）——见 §7.2 |
| 4 | 拒绝写 `permission.denied` | ✅ `record_permission_denied`，登记为 `audit.py` 调用方第 ④ 项 | 无 |
| 5 | G-24 转正 | ✅ 真通过后摘 xfail，**并补强判据 + 另加 2 条**；行为侧 14 条落新增 `tests/test_rbac.py` | 超计划（判据补强，沿用 P2-A 给 G-18 补判据的做法） |
| 6 | — | 🆕 `roles` 的 **4 种预置角色在迁移里播种** | **新增**（计划未提）：不播种则系统没有角色可授 |
| 7 | — | 🆕 测试夹具给**默认 dev 主体**授 `admin` | **新增且必须显式登记**——见 §7.1（这是本批最大的一个自主决策） |

---

## 7. 实现决策（**边界要求：必须登记并写明理由**）

### 7.1 测试夹具给默认主体授 `admin` —— 本批最大的自主决策，**必须先读这段**

`conftest.py` 新增 **session 级 autouse** 夹具 `rbac_default_actor_is_admin`：
给 `DEFAULT_ACTOR_ID` 在**默认 org 与跨租户 org 各**授一份 `admin`。

**为什么必须有**：受保护端点一旦走 RBAC 强制校验，dev token / dev header 解析出来的
主体在 `user_roles` 里**天然没有任何授权**（真实账号链路归 P2-C）⇒ 不播种的话
**818 条既有用例会为了与己无关的原因集体变红**。

**它不是"绕过护栏"**：校验照常执行、矩阵照常生效，只是把「这个主体是谁」补上——
与既有的 `pg_active_kg_version` 桩掉一个 ready 版本是同一类动作
（不打桩会让基础设施故障伪装成别的语义）。

**为什么两个 org 都授**：`cross_tenant_headers` **只换 org 不换 actor**。
不授 org B ⇒ 跨租户请求会被 RBAC **抢在应用层 `org_id` 过滤之前**拦掉，
于是「跨租户返回空 / 403」的既有判据（G-9 / `test_documents.py` / `test_audit.py`）
**虽然仍然绿，验的却不再是它们要验的那层**——那才是真正的假绿。

⚠️ **代价（必须记住）**：默认主体是 admin ⇒ **默认路径验不到拒绝分支**。
拒绝分支一律由 `tests/test_rbac.py` 用**另外的 actor id** 专测（14 条）。

### 7.2 受保护端点的覆盖范围（10 个）

| 端点 | 资源 / 操作 | 说明 |
|---|---|---|
| `GET /documents` | `document:read` | 列表 |
| `POST /documents/upload` | `document:write` | 唯一写端点 |
| `GET /documents/{id}/status` | `document:read` | **文档级**粒度在此生效（路径 `document_id` 比对 `doc_scope`） |
| `GET /documents/{id}/graph` | `document:read` | 同上 |
| `GET /documents/{id}/chunks/{chunk_id}` | `document:read` | 同上 |
| `POST /affiliation/detect` | `affiliation:write` | **场景级**在此生效（scene = `affiliation`） |
| `PATCH /affiliation/suspicions/{id}` | `affiliation:write` | 同上 |
| `POST /graph/versions/{version}/activate` | `graph:write` | 版本激活属运维动作 |
| `GET /audit` | `audit:read` | 审计是留痕对象本身 |
| `GET /audit/trace/{trace_id}` | `audit:read` | 同上 |

**未保护**（登记在 §10 遗留）：`GET /graph/overview`、`GET /entities/{id}`、
`POST /agent/query`、`GET|POST /attendance/*`、`GET /cost/dashboard`、
6 个 `ontology/*`（**501 占位**）、`GET /health`（探针）。
⇒ **判据**：受保护端点集合由
`tests/test_rbac.py::test_protected_routes_declare_the_enforcement_entry`
按**路由对象**逐条核对（不是扫源码字样）——删掉某个端点的 `dependencies=[...]`，CI **红**。

### 7.3 类型收敛（沿用既有先例 **A9**：按本仓惯例收敛并登记，守 **R5**）

| spec | 实现 | 理由 |
|---|---|---|
| `doc_scope` / `scene_scope` = **JSONB** | SQLAlchemy `JSON`（PG `json`） | 既有 JSON 列（`kg_versions.source_doc_ids` 等）一律 `JSON`；方言中立即为 ADR-0003 §3.7 的**信创降级**留退路 |
| 主键类型未明写 | `Uuid`（全仓一致） | 与 `users` / 其它表一致 |

### 7.4 矩阵赋权（**G-24 不断言取值**，取值与理由在此登记）

| 角色 | 赋权 | 理由 |
|---|---|---|
| `admin` | 8 个资源全 `read` + `write` | 系统管理员：含授权、版本激活等运维动作 |
| `auditor` | 8 个资源全 **只读** | 审计员必须**看得到**才能审；但一律不得改动（审计对象尤其不能被改） |
| `analyst` | `document` / `affiliation` 可写；其余只读 | 分析师的业务动作就是「传文档 + 复核疑点」；图谱激活 / 本体 / 成本属运维与合规口径，不给写 |
| `viewer` | 只读 `document` / `graph` / `agent` / `compliance`；`affiliation` / `audit` / `ontology` / `cost` **无权限** | 最小可读集：业务对象可见，留痕对象（审计）与运维对象（本体 / 成本）不可见 |

**场景档位**：`affiliation`（挂靠）/ `qa`（问答）/ `audit`（审计）——
前两档出自 spec §4.3 的示例 `["affiliation", "qa"]`，`audit` 按同一口径补齐。

**多角色取并集**（权限是加法）：任一授权「不限」⇒ 整体不限；
`doc_scope` 的**空数组**语义是「明确限定为零个文档」，**不等于**「不限」
（两者合并成一个意思会让"授权为零"退化成"全放开"）。

**判定次序**：角色 → 资源 × 操作 → 场景 → 文档。次序是刻意的：
先判细粒度会得到「你有这个文档的权限但没有角色」这种无法解释的拒绝原因。

---

## 8. `roles` 的 RLS 豁免（按 **2026-10-03 裁决（用户选 A）** 履行）

原文要求「豁免必须在**代码评审**中被显式确认」，而本批**无人值守、无人类 CR** ⇒
裁决改为「**代码内显式声明 + 机械断言 + 事后 CR 抽检**」。三条的落地：

| 断言 | 落点 | 实测 |
|---|---|---|
| ① 该表**不得出现租户业务列** | `app/db/models.py::Role` 无 `org_id`；`test_g24_roles_rls_exemption_is_declared_and_bounded` 断言 `org_id not in roles.columns` | ✅ 红→绿（该断言确实拦得住：给 `roles` 加 `org_id` 即红） |
| ② 表内**仅允许 4 种预置角色** | DB 侧 `ck_roles_name` 钉死；测试断言 CheckConstraint 覆盖 `ROLE_NAME_VALUES` 全部四档 | ✅ |
| ③ 豁免清单 **==** 实际模型 | `RLS_EXEMPT_TABLES = frozenset({"roles"})` 与模型上的 `__rls_exempt__` 双向核对（**双向**：多一个声明 / 少一个声明都红） | ✅ |

**显式声明与理由**写在 `app/db/models.py::Role` 的 docstring 里（不是注释习惯，是
ADR-0003 §4.1 要求的"显式声明"本体），指向 spec §4.2 与 ADR-0003 §3.1 第 9 行。

⛳ **事后 CR 抽检（裁决第 3 条）待你执行**：本批无人类 CR，抽检结论请登记在本节下方。
自检命令：`uv run pytest tests/test_guardrails_compliance.py -k g24 -q` +
人工看 `app/db/models.py::Role` 的豁免段落。

⚠️ **RLS 策略一行未写**（DR-B4 归 **P3**）：本批只做豁免**登记**，不建策略。

---

## 9. 收尾三件套（实测数字）

| 检查 | 起跑 | P2-B 后 |
|---|---|---|
| `uv run pytest -q` | 818 passed / 3 skipped / **7 xfailed** | **835 passed / 3 skipped / 6 xfailed**（+17：新增 `tests/test_rbac.py` 14 条 + G-24 组新增 2 条 + G-24 主测试由 xfailed 转 passed；**无失败**） |
| `ruff check .` / `ruff format --check .` | 双绿 | 双绿（**213** files，P2-A 时 186） |
| `export_openapi.py --check` | 零漂移 | **零漂移**（本批 Non-goals 硬要求：不加端点、不加错误码 ⇒ 实测达成） |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 10 | ERROR 0 / WARN 0 / OK 10（**未新增 `settings.*` 配置**，故配置消费者核对不受影响） |
| `check_startup_readiness.py` | 已生效 9 组 / 挂起 4 组 | **已生效 10 组**（新增 **G-24，3 项**）／部分生效 2 组／挂起 **3 组**／反向守卫 `test_g21_production_sqlite_guard_still_present` ✅ **仍在** |
| 迁移 | head = `a1f3c9d27b08` | head = **`7d2e91f4ab35`**；`tests/test_rbac.py::test_migration_seeds_preset_roles_and_is_replayable` 在**临时 PG 库**上实测：播 4 角色 + 退一步 + 重放 + 重放（幂等，不重插） |

**转正流程（守 proposal 行动指引第 2 条）**：先让 `test_g24_rbac_three_granularity_matrix`
**真通过**（xfail strict ⇒ XPASS 转 FAILED），**再**摘 `@pytest.mark.xfail` 并补强判据。
不是"删标记就算转正"。

---

## 10. 遗留（**不在本批边界内**）

| # | 事项 | 去向 |
|---|---|---|
| 1 | **`users.status` 未参与判定**：`disabled` 的账号只要 `user_roles` 还在就仍有权限 | 本批**刻意不读 `users`**（一读就要登记 `USERS_CONSUMER_MODULES`）；建议随 **P2-C** 真实账号链路一并接上，届时按闸门登记四件事 |
| 2 | **授权记录全靠测试夹具播种**：没有授权管理界面 / 没有 `POST /roles` 之类端点 | 真实授权链路归 **P2-C**（契约零 diff 是本批硬约束，不允许新增端点） |
| 3 | 10 个端点受保护，其余未保护（见 §7.2） | 逐端点收紧建议随 P2-C 一起做：**每加一个端点，同步改 `PROTECTED_PATHS`**（否则 CI 红，这是有意设计的） |
| 4 | `doc_scope` 的 `tags` 维度**只落库、未参与判定**（当前只比对 `doc_ids`） | spec §4.3 的示例含 `tags`，本批未开；需要"按标签授权"时再开 |
| 5 | 拒绝时**审计会写两行**：`permission.denied` 一行 + 中间件按请求写的一行 | 有意为之（一行是拒绝事件、一行是请求留痕）；若日后要合并，须改审计中间件，属**范围外** |
| 6 | `USERS_CONSUMER_MODULES` **仍是空集** | 见遗留 1——P2-B 判定只读 `(org_id, user_id)`，不需要 `users` 表 |

---

## 11. 边界声明（写在最后，防止被日后外推）

- **G-24 转正 ≠ 租户隔离完成**。本批做的是**权限**，不是**隔离**：
  RLS 策略一行未写（DR-B4 归 **P3**）；`roles` 只登记了豁免。
- **G-24 转正 ≠ 具体权限值被认可**。G-24 **不断言**取值（按 P2-B 边界），
  取值与理由见 §7.4；改值必须同步改本日志。
- **`roles` 的 RLS 豁免只是"登记完成"**，裁决要求的第 3 条「**事后 CR 抽检**」
  **尚未执行**（无人值守批次做不到）⇒ 本节 §8 结尾留了待办。
- **默认主体是 admin**（§7.1）⇒ 任何"默认路径绿了"都**不能**用来证明拒绝分支有效；
  拒绝分支只有 `tests/test_rbac.py` 那 14 条在验。
- **契约零 diff 实测达成**：不加端点、不加错误码，403 `FORBIDDEN` 复用契约已有定义。

---

## 12. 三问自答（`check_session_drift.py` 拦不住、必须自己答的）

1. **这批里有"顺便做的"吗？** 有 **2 项**，均已登记而非默默混进：
   ① `roles` 4 种预置角色在**迁移里播种**（§6-6）——理由：不播种则系统没有角色可授；
   ② `tests/test_rbac.py::test_migration_seeds_preset_roles_and_is_replayable`
   顺带验了「**退一步 + 重放**」，而 `test_migrations_baseline.py` 只验「退到零」——
   理由：现场回滚是退一步，不重放就不能叫幂等。两者都属 **DR-E1**（迁移纪律），不越界。
2. **有没有为了躲坑而绕路的实现？** 有 **1 处**，必须点名：
   `user_roles` **不读 `users.status`**（遗留 1）——本批绕开了「读 `users` 就要登记
   `USERS_CONSUMER_MODULES`」这道闸门，代价是 `disabled` 账号仍有权限。
   **不是**为了省事，而是「判定只读 `(org_id, user_id)`」本就够用；
   但它是**欠债**，建议随 P2-C 一并接上。
3. **验收判据是真跑出来的还是读代码得出的？** **全是真跑出来的**：
   835 passed 是 `pytest` 实跑；迁移幂等是在**临时 PG 库**上真跑
   `upgrade → downgrade → upgrade → upgrade`；契约零漂移是
   `export_openapi.py --check` 实跑；G-24 三档是 `check_startup_readiness.py` 实跑
   （它恒退 0 ⇒ 我读的是四档数字，不是把输出当"通过"）。
