# P6-P0 · 量化 `users` 消费者缺口（**只读前置批**，为 DR-C1 / G-23 License 铺路）

> **日期**：2026-10-06 ｜ **上游**：`changes/P6-O/`（G-12 已转正，A 组零缺口）
> **关联需求**：DR-B13（`users` 表 / 账号主体）｜ **下游依赖**：**DR-C1 / G-23（License）**、DR-B9（RBAC）、DR-D9（SSO）
> **定位**：本批**不写业务代码**，产出 = **缺口量化报告 + 下一步边界坐标**
>
> ⚠️ **草案状态（2026-10-06，由执行代理起草）**：边界已作**编号列表**可供 `check_session_drift.py`
> 读取，但**尚未经 sdd-assistant 定型** ⇒ 新会话开工第一步应**先复核 §1 的行号坐标**（坐标会漂移），
> 再决定是否照本执行。**坐标失效即停**，不得凭印象继续。

---

## 1. 依据（2026-10-06 只读调查，逐条带坐标）

| # | 事实 | 坐标 |
|---|---|---|
| 1 | `users` 表**有 ORM 壳子、7 字段**（`id` / `username` / `password_hash` / `org_id` / `status` / `created_at` / `updated_at`） | `backend/app/db/models.py:773`（`__tablename__` `:791`；字段 `:803-815`） |
| 2 | **`app/` 下零读写**：无 `User(...)` 构造、无 `select(User)` ⇒ **真实读 0 / 真实写 0** | 全仓 `backend/` 扫描（仅定义 `:773` 与护栏/迁移命中） |
| 3 | 护栏**已备好开工闸门**：`USERS_CONSUMER_MODULES = frozenset()`（空 = 零消费者）＋扫 `app/` 下 `\bUser\b` ⇒ **`app/` 一旦出现 `User` 引用就会红** | `backend/tests/test_guardrails.py:231` / `:257` |
| 4 | 真机读数：表**存在**但 **`users_rows = 0`**（含演示库） | PG 直读 `select count(*) from users` |
| 5 | 契约侧**零痕迹**：`contracts/openapi.yaml` 无 `users` / `password_hash` / `/auth/login` | 由 `test_guardrails.py:283` 断言守着 |
| 6 | 无端点、无 schema：路由仅 10 个模块（**无 users / 无 auth**）；`UserCreate`/`UserRead` 之类命中 0；`/auth/login` 仍草案态 | `backend/app/api/v1/router.py:32-42` / `:21` |
| 7 | 认证**不查 users**：`LocalAuthProvider` 只解析 dev token / header；角色查的是 **`user_roles`** 表；`Identity` 只有 `org_id`/`actor_id`/`roles`/`source` ⇒ **无姓名、无角色来源** | `services/auth/local.py:47`、`:32-38`、`:8-10`；`core/auth.py:26-32`、`:57`、`:87-90`；`services/rbac/deps.py:67` |
| 8 | **`actor_id` 恒为默认 UUID**：`DEFAULT_ACTOR_ID = 00000000-0000-4000-8000-0000000000aa` | `core/config.py:27` + `.env.example:198` |
| 9 | **users 是租户表（有 RLS）**：`users.org_id` 存在且不在 `RLS_EXEMPT_TABLES`（仅 `roles`）⇒ 自动进 `TENANT_TABLES`；两笔 RLS 迁移显式含 `users` | `models.py:83`、`:809`；`migrations/versions/8210590e76a5:48`、`b7c4e1f9a2d3:59` |
| 10 | 已接线但**取脚手架值**的字段（第一个真实消费者的候选落点） | `documents.uploaded_by`（`models.py:114` ← `services/documents.py:240`）；`affiliation_suspicions.reviewed_by`（`:431` ← `api/v1/routes/affiliation.py:252`）；`audit_log.actor_id`（`:664` ← `services/audit.py:131`）；`user_roles.user_id`（`:894` ← `scripts/seed_dev_rbac.py:117`，**无 FK 校验**） |
| 11 | License 明写依赖：`LicenseProvider` 接缝 9「**S11 落地，依赖 `users` 表**」 ⇒ **users 空表 = License 席位无数据源** | `docs/adr/ADR-0006-license-control.md:235`；现状零代码 `:294` |

⇒ **本批要回答的唯一问题**：缺口不是「表没建」，而是「**主体从哪来**」——
`users` 恒空、`actor_id` 恒为默认 UUID ⇒ 若只是把 `identity.actor_id` 换成「查 users 表」，
写出的是**假接线**（读不到人）。**第一个 user 由谁造**（注册 / seed / SSO）才是真决策点。

## 2. ⚠️ 三个已查证的坑（不看必踩）

1. **引用即红**：`USERS_CONSUMER_MODULES`（`test_guardrails.py:231`）是**空登记集合** ⇒
   任何 `app/` 下新增 `User` 引用都会让该条变红，**除非**同步把模块登记进去。**顺序**：
   先扩写该登记（并交代 DR 归属 / 迁移 / ADR-0004 §2.1），**再**写实现 —— 与 ADR-0004 §3 第 4 条
   （先扩 ADR 登记、再改门禁）同款，**漏任一侧 CI 必红**。
2. **`password_hash` 禁入契约与日志**：`models.py:786` 明写「不进契约」，`test_guardrails.py:283`
   断言契约不含 `password_hash` ⇒ 任何 schema / 端点**不得**带该字段。
3. **不许造第二个「假差异」**：若只为了让 G-18 / G-23 的判定条件"看起来满足"而新增字段或端点，
   但无人真实读写 ⇒ 重演 `task_retry_multiplier` 与本次 `domain_profile` 的病例
   （CODEBUDDY.md 预留纪律第 6 条）。本批**只量化、不落地**，正是为了避开这个坑。

## 3. 决策点（建议项 —— 无人值守下默认采纳；有异义按升级条件处理）

| # | 决策 | 建议项 | 理由 |
|---|---|---|---|
| **P0-D1** | 本批范围 | **只读量化，零业务代码**；产出 = 报告 + 下一步边界坐标 | 先把「主体从哪来」问清楚，再谈写什么 |
| **P0-D2** | 认证链路 | **不动** `LocalAuthProvider`（其注释明写「接线归 P2-C」） | 属另一批，越界会同时牵动 DR-D9 |
| **P0-D3** | 「最小真接线」候选 | 让 `reviewed_by` / `uploaded_by` / `audit_log.actor_id` **指向真实 users 行**（而非默认 UUID）⇒ 前置是**先有 user 可指** | 这三个字段已接线、只差真数据源，改动面最小且可机械验证 |
| **P0-D4** | 若量化结论要求**新建端点 / schema / 注册流程** | **升级用户**，不越界自行开工 | 属新批次（与「不写无消费者字段」同款边界） |

## 4. Non-goals（**编号列表**，S1 必须读到 —— 表格读不到）

1. **不写任何业务代码**（本批只读 + 文档，产出报告）
2. 不改 `contracts/openapi.yaml`（`test_guardrails.py:283` 断言守着；`password_hash` 禁入）
3. 不新增或修改 `settings.*` 配置项
4. **不动认证链路**（`LocalAuthProvider` / `core/auth.py` / RBAC 取角色逻辑）
5. 不动 RLS 政策 / 迁移（users 已覆盖 RLS，无需改）
6. **不摘任何 `xfail`**（G-23 两条仍在挂起，按 R-9「先建真子系统再摘标记」）
7. 不新增 / 修改 CI job
8. **不修 R28**（本地有图口径 8 条环境债，CI 已兜）
9. 不顺手修其它遗留登记
10. **不得宣称「账号体系已落地」** —— G-18 绿 **≠** 落地（`users` 仍 0 消费者，需求基线 `:228`）

## 5. 任务（T1 只读 → T2 报告 → T3 建议 → T4 门禁）

- **T1 只读量化（¥0，顺序不能反）**
      - T1.1 **复核 §1 的 11 条坐标**（行号会漂移，失效即停）
      - T1.2 真机读数：`users` 行数；`user_roles` 行数 + 其 `user_id` 是否能在 users 中命中（**外键不校验 ⇒ 可能有孤儿**）
      - T1.3 列出**所有**取 `identity.actor_id` / `default_actor_id` 的落点（§1 第 10 条是否穷尽）
      - T1.4 查 `Identity` 是否有姓名/角色的可能来源（决定「第一个 user」需要哪些字段）
      - T1.5 查 `USERS_CONSUMER_MODULES` 的判定逻辑（登记后会不会连带要求别的条件）
  - **T2 产出《`users` 缺口量化报告》**：六维表（**读 / 写 / 端点 / schema / RLS / 主体来源**），
    每格必须有**行号证据**，不许写"应该/大概"
  - **T3 给出下一步建议**：把「A 只做 License / B License+users 一批 / C 先补 users」三选
    **收敛成一条**，并写明该条的最小真接线方案（先造 user 的三种途径：注册端点 / seed 脚本 / SSO，
    各自的成本与被 `password_hash` 禁令约束的点）
  - **T4** 回切点（`check_session_drift.py`，S1 须读到 **10 条**）+ 门禁全绿

## 6. 验收判据（全机械、零判分）

| # | 判据 |
|---|---|
| ① | 报告六维表**每格都有行号证据**；无证据的格子必须写「未查到」而非猜测 |
| ② | 真机读数齐：`users` 行数（实测 **0**）、`user_roles` 行数与孤儿数 |
| ③ | **零代码改动** ⇒ 契约 **zero diff**、`pytest` passed **不减**（本地 991 / CI 997 口径见 `changes/P6-O/integration-log.md` §4④）、`ruff check` + `ruff format --check`、`check_seams` **ERROR 0** |
| ④ | `check_session_drift.py` 的 S1 读到 **10 条** Non-goals |
| ⑤ | T3 的结论**二选一且不许含糊**：要么给出「可开工的最小真接线方案」，要么明确「需用户拍板的范围问题」（按 P0-D4 升级） |

## 7. 状态

- **草案**（2026-10-06 起草）｜ 关联：`docs/adr/ADR-0006-license-control.md:235`、
  `docs/delivery-requirements-and-guardrails.md:183`（G-23）/ `:228`（users 仍 0 消费者）/ `:463`（P2 排期）
