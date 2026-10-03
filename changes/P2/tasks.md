# P2 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §4 Non-goals 为准**。
> 每批收尾都要跑：`uv run python scripts/check_startup_readiness.py`，确认对应护栏**真的从「挂起」变「已生效」**。
> 只删 xfail、测试没真通过 —— **不算转正**（proposal 所引行动指引第 2 条）。

**状态（2026-10-01）**：**P2-A 已完成**（表 + 迁移 + G-18 转正，已提交 + 已 push）；P2-B / P2-C 未开工。

> 🧭 **执行顺序（2026-10-01 用户确认「研发阶段、无客户」后调整）**：
> **P2-B（RBAC）→ P2.5（插件形态）→ P3（租户隔离）→ P2-C（SSO/AD）→ P4 → P5 → P6**。
> 原「签单优先」在无客户阶段失效 ⇒ 改**风险优先**；**P2-C 因此后移到 P3 之后**（它需自建 IdP 真机验证，
> mock 不算完成）。🔒 另叠加**「零缺口」裁决**：正式版门槛 = `check_startup_readiness.py` 所有 G 进 🟢，
> 不做带缺口的发布（五项清零方式见 `docs/delivery-requirements-and-guardrails.md` §5 📌）。

---

## ⛳ 开工前置（2026-10-03 补 —— **无人值守 / 新对话开工必读**）

> 这一段专为「换一个新对话直接开工」准备：**上下文不会带过来**，缺任一条都会让第一步**假失败**
> （看起来像代码坏了，其实是环境没起来）。

### 1. 本机必须先起 PostgreSQL —— 否则 pytest **全红**

`backend/tests/conftest.py` 已把测试库写死为 PG 上的固定库
（`postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test`，用 `setdefault` 注入），
**不再用 SQLite**（**G-8** 已转正：SQLite 既无 RLS 也无 `SET LOCAL` ⇒ 在它上面跑通的隔离**什么都不证明**）。

```bash
docker run -d --rm --name graphrag-pg \
  -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag_test \
  -p 5432:5432 postgres:16-alpine
# 必须等就绪再跑测试，否则前几秒 connection refused ⇒ 会被误读成代码错误
until docker exec graphrag-pg pg_isready -U graphrag -d graphrag_test; do sleep 1; done
```

> CI **不需要**这段——`ci.yml` 的 backend job 自带 `postgres:16-alpine` service。
> **本机样例状态（2026-10-03）**：`graphrag-pg` Up（11h）、`kg-poc-neo4j` Up（10h）。
> Windows / PowerShell 下请把上面的 shell 片段换成等价命令。

### 2. 先跑开工自检，再动手

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

它输出「**已生效 / 部分生效 / 挂起 / 开工地雷**」四档 ⇒ **先看挂起与地雷里有没有本批要动的那条**，
再决定能不能开工（P2-A 开工时正是这么用的，见 `integration-log.md` §0 / 本文件 P2-A 的 A0）。
⚠️ 注意它**恒退 0**（只报告、非门禁）⇒ **别把它的输出当"通过"**，要自己读数字。

### 3. P2-B 的两个**机械**闸门（不是人工约定，红了就是没做到）

| 闸门 | 位置与现状 | 触发条件 |
|---|---|---|
| `USERS_CONSUMER_MODULES` 登记 | `backend/tests/test_guardrails.py`，当前 = **空集** | `app/` 下**任一模块引用 `User`** 却未登记 ⇒ `test_g18_users_consumers_are_registered` 红；**反向也拦**——登记了却查不到引用（僵尸登记）同样红 |
| **G-24** 转正 | `test_g24_rbac_three_granularity_matrix`，当前 **xfail 挂起** | 出口 = 摘 xfail，**但必须先让它真通过**（proposal 行动指引第 2 条：**只删标记不算转正**） |

### 4. 迁移纪律（**DR-E1**）

新增 `roles` / `user_roles` **必须带可幂等 Alembic 迁移**（基线已由 P1 建立：`00f44b912817`）；
**禁手工改客户库**。
事后实测证据与遗留事项记 [`integration-log.md`](./integration-log.md)
（本文件是事前计划，两者不可互相替代）。

---

## P2-A — DR-B13 `users` 表（✅ 已完成）

### A0 开工前实测（2026-10-01）

| 探测量 | 实测结果 |
|---|---|
| `users` 是否有 spec | ✅ `specs/m5-permission-audit.md` §4.1，7 列口径明确 |
| Alembic head | `b3e5a1c70d42`（s9.13） |
| G-18 判据 | `test_guardrails.py:141`，只判「表存在」，`xfail(strict=True)` |
| G-24 连带风险 | 其 missing 列表含 `users` ⇒ 建表后**必须实测**它是否仍 XFAIL（不得假设） |
| `users` 的消费者 | **0 个** ⇒ 本批不接线、不加 API |

### A1 模型 —— `backend/app/db/models.py`

- [x] 加 `USER_STATUS_VALUES = ("active", "disabled")` + `class User(Base)`，
      `__tablename__ = "users"`，字段**逐字照 spec §4.1 的 7 列**
- [x] `__table_args__`：`ck_users_status`（两档）、`uq_users_username`（spec 的 unique）、
      `ix_users_org_id_status`（ADR-0003 §3.1：复合索引 `org_id` 打头）
- [x] `created_at` / `updated_at` 用既有 `utcnow` 惯例；模块文档补本批说明
- [x] 遗留登记：`username` 全局 unique（照 spec）与多租户同名账号的张力 —— 见 proposal RK-2
      （已登记至 `integration-log.md` §3 遗留 1 / `delivery-requirements-and-guardrails.md` §5 📌）

### A2 迁移 —— `backend/migrations/versions/`

- [x] 新增 `a1f3c9d27b08_add_users_dr_b13.py`，`down_revision = "b3e5a1c70d42"`
- [x] `upgrade()` 建表 + 三个索引/约束；`downgrade()` 对称 `drop_table`（含索引先删）
- [x] 验证：`alembic upgrade head` 后 `psql -Atc '\d users'` 见 7 列 + 约束齐备；
      `tests/test_migrations_baseline.py` 通过（迁移结果 == ORM 元数据）
- [x] 验证：downgrade 回 `b3e5a1c70d42` 后 `users` 消失（`\dt` 仅剩 12 张）

### A3 G-18 转正 —— `backend/tests/test_guardrails.py`

- [x] 摘掉 `test_g18_users_table_exists` 的 `@pytest.mark.xfail(strict=True)`
      （建表后它会 XPASS ⇒ CI 必红，**必须**当场处理）
- [x] **判据补强**（决策点 1）：表存在 **+** 列集合 == spec §4.1 的 7 列 **+**
      `org_id` 打头索引存在 **+** `username` 唯一约束存在
- [x] **RK-4 机械化**（你 2026-10-01「G-18 转正 ≠ 账号体系落地，看看怎么处理好」）：
      `test_g18_users_consumers_are_registered` —— `app/` 下任何引用 `User` 的模块
      必须先登记进 `USERS_CONSUMER_MODULES`（当前为**空**），并交代 ① 归属哪条 DR
      ② 所需列随本批迁移 ③ 接缝 1 是否需扩写 ADR-0004 §2.1 ④ 护栏是否同步转正；
      另在 `check_startup_readiness.py` 增 `SCOPE_CAVEATS`，G-18 绿灯旁**直接印出**这条边界
- [x] 同步改写 `docs/delivery-requirements-and-guardrails.md` 里 **G-18 那行的判据描述**（不许只改代码）
- [x] 反向确认：`test_g24_rbac_three_granularity_matrix` **仍 XFAIL**（实测不是 XPASS）

### A4 陈旧口径同步

- [x] `app/services/auth/local.py:5` —— 「users 表按 T10 裁决不建」改为「T10 已被 DR-B13 推翻，
      users 已于 P2-A 建表；本实现暂不查库，接线归 P2-C」
- [x] `docs/delivery-requirements-and-guardrails.md`：DR-B13 行状态更新；§5 状态清单把 G-18
      由「骨架已就位（挂起）」移入「已生效」区
- [x] `docs/delivery-plan.md` §8.1 的「ORM 表 = 12 张，没有 users」标注为开工前快照
- [ ] ⚠️ **未动** ADR-0003 原文（守 R5）：§3.1 第 77 行「users 本批次未建」是历史陈述，登记在本批日志

### A5 收尾三件套 + 留证 ✅

- [x] `uv run pytest -q` ⇒ **712 passed / 3 skipped / 7 xfailed**
      （基线 710 / 3 / 8：G-18 由 xfailed 转 passed，另新增敏感字段 1 条 ⇒ **xfailed 8 → 7、passed +2**，无失败）
- [x] `uv run ruff check .` + `uv run ruff format --check .`（186 files）⇒ 双绿
      ⚠️ 新迁移文件**不进 lint**（`pyproject.toml` 的 `extend-exclude = ["migrations"]` 既有裁决，非本批引入）
- [x] `uv run python scripts/check_startup_readiness.py` ⇒ **G-18 进 🟢**（已生效 **8 → 9** 条，G-18 共 2 项）；
      地雷区「users 表已建」❌ → **[OK]**（4 → 3 项）
- [x] `export_openapi.py --check` ⇒ **零漂移**（Non-goals 要求契约零 diff，实测达成）；`check_seams.py` 仍 ERROR 0 / OK 10
- [x] 实测证据写入 `changes/P2/integration-log.md`（含 `probe_users_migration.py` 的三步走留证）
- [x] 环境项（你 2026-10-01「改吧，未来也不用 sqlite 了」）：本机 `backend/.env` 的
      `DATABASE_URL` 由 `sqlite:///./dev.db` 改为 `postgresql+psycopg://...@localhost:5432/graphrag`
      （实测 `get_settings().database_url` 已读成 PG）。⚠️ 本机 dev 库需 `alembic upgrade head` 重建建表

### A-出口判据（一句话）

`check_startup_readiness.py` 里 **G-18 进「🟢 已生效」**，且 G-24 **仍是 XFAIL**。

### A-Non-goals（边界提醒）

- **不**做 RBAC（`roles` / `user_roles`）—— P2-B
- **不**接 SSO / 不新增接缝 1 实现 / **不改** `LocalAuthProvider` 语义 —— P2-C
- **不**加 API（契约零 diff）、**不**做用户 CRUD / 登录端点（0 消费者）
- **不**加 `documents.uploaded_by` 外键、**不**做数据回填
- **不**动 ADR 原文（R5）；**不**做 RLS（P3）、License（P4）

---

## P2-B — DR-B9 RBAC 三粒度

> 🚧 **开工闸门（新增，2026-10-01）**：本批第一次在 `app/` 里引用 `User` 时，
> 必须先把它登记进 `test_guardrails.py::USERS_CONSUMER_MODULES` 并交代四件事（见 A3 / 日志 §1.4），
> 否则 `test_g18_users_consumers_are_registered` 会红。

**规格来源（唯一真源 —— 先读，再动手）**
- `specs/m5-permission-audit.md`：**§4.2 `roles`**（`id / name / description`）、
  **§4.3 `user_roles`**（`org_id / user_id / role_id / doc_scope / scene_scope / granted_by / granted_at`）、
  **§3 验收 1**（行为判据：无权限 ⇒ **403 + `FORBIDDEN`** + `audit_log` 的 `action=permission.denied`）
- **三粒度** = 角色（`role_id`）+ 文档（`doc_scope`）+ 场景（`scene_scope`），
  出处 `docs/02-product-outline.md` §3.2 第 1 条「RBAC + ABAC 最小组合」

- [x] `roles` 表（全局字典表，**RLS 显式豁免**）⇒ 📌 **按 2026-10-03 履行方式裁决（用户选 A）**：
      **代码内显式声明 + 机械断言 + 事后 CR 抽检**（本批无人值守 ⇒ 过程中无人类 CR，故变更履行载体），
      三条断言见 `specs/m5-permission-audit.md` §4.2；`ADR-0003` §4.1 表与 `ADR-0006` 已同步登记
      ⇒ 实测：声明写在 `app/db/models.py::Role` docstring；三条断言落在
      `test_g24_roles_rls_exemption_is_declared_and_bounded`（2026-10-03 全绿）
- [x] `user_roles` 表（含 `doc_scope` / `scene_scope` JSONB，`org_id` 打头索引）
      ⇒ `doc_scope` / `scene_scope` 用 SQLAlchemy `JSON`（类型差异按 **A9** 收敛登记）；
      索引 `ix_user_roles_org_id_user_id` / `ix_user_roles_org_id_role_id` 均 `org_id` 打头
- [x] 路由层**强制校验入口**（依赖 / 中间件）—— **没有它，权限只是库里的一列装饰**
      ⇒ `app/services/rbac/deps.py::require_permission`，挂在 **8 个**受保护端点上；
      逐条核对见 `tests/test_rbac.py::test_protected_routes_declare_the_enforcement_entry`
- [x] 拒绝时写 `audit_log`（`action=permission.denied`）—— §3 验收 1 的**显式要求**；
      **只返 403 而不留痕 = 未完成**
      ⇒ `app/services/rbac/service.py::record_permission_denied`，已登记为
      `app/services/audit.py` 调用方集合第 ④ 项
- [x] 出口：`test_g24_rbac_three_granularity_matrix` 转正（**先真通过，再摘 xfail**）
      ⇒ 2026-10-03：先跑到真通过（XPASS），再摘 xfail 并**补强判据**，另加 2 条；
      行为侧 14 条落在新增的 `tests/test_rbac.py`

**实施边界（无人值守 ⇒ 先把自由度钉死，防自由发挥）**

| 边界 | 规定 |
|---|---|
| **角色集合** | **只允许** §4.2 的 4 种预置角色 `admin / auditor / analyst / viewer`；**不得**新增角色名 |
| **资源清单** | 只能取自**契约中已存在的端点**（`contracts/openapi.yaml`）；**不得**凭空造资源类型 |
| **契约** | **必须零 diff**——`403 FORBIDDEN` **已在契约里**（`contracts/openapi.yaml` 38 处引用，且 `test_openapi_contract.py::ADR_REQUIRED_CODES` 已含它）⇒ **复用现有错误码**，**不加新端点、不加新错误码** |
| **矩阵内容** | **G-24 只断言**「矩阵**存在** + 强制校验入口**存在**」，**不断言**具体权限值 ⇒ 具体赋权属实现决策，**必须在 `integration-log.md` 登记并写明理由** |
| **迁移** | 两张表**必须**带可幂等 Alembic 迁移（**DR-E1**）；**禁手工改客户库** |
| **不碰 RLS** | 本批**不做** RLS 策略（DR-B4 归 **P3**）；只做 `roles` 的**豁免登记**，`user_roles` 仅补 `org_id` 与索引 |
| **不改 ADR 原文** | 守 **R5**：新增 / 变更一律**追加登记**，不删改历史记述 |

## P2-C — DR-D9 SSO / AD

- [ ] **`先`扩写 `docs/adr/0004-integration-seams.md` §2.1 接缝 1 登记行**，再改 `get_auth_provider()`
      （漏改任一侧 CI 必红）
- [ ] 外部身份字段（`issuer` / `subject`）进 `users` + 自带迁移
- [ ] 出口：`check_seams.py` 接缝 1 实现集合 == 登记集合；AD / OIDC 登录可用

---

## 待你决策 ✅ 已按建议处置（2026-10-01）

1. ✅ 字段范围 ⇒ 逐字照 spec §4.1 的 7 列（外部身份 / 席位关联字段各自随 P2-C / P4 来）
2. ✅ `documents.uploaded_by` ⇒ **本批不加** FK（演示库有真实数据，回填不可逆）
3. ✅ `local.py` 的 T10 陈旧注释 ⇒ 改为「T10 已被 DR-B13 推翻」，**不删历史**
4. ✅ 类型与 spec TEXT 的差异 ⇒ 照既有先例 A9：按本仓惯例收敛并**登记**（守 R5）
