# P6-P0 · 任务清单（量化 `users` 消费者缺口）

> 上游：`changes/P6-O/`（G-12 已转正）。边界见 `proposal.md` —— ⚠️ **草案，待 sdd-assistant 定型**。
> **本批零业务代码**：产出 = 缺口量化报告 + 下一步边界坐标（给 DR-C1 / G-23 License 铺路）。
> **顺序不能反**：T1 只读，**先复核坐标再造结论**。
> 执行留痕与六维报告：[`integration-log.md`](./integration-log.md)。

- [x] **T0（新会话第一步，草案状态必做）**：复核 `proposal.md` §1 的 11 条行号坐标 —— **失效即停**，
      不得凭印象继续；坐标有漂移就先修坐标再开工
      ⇒ ✅ **13 条坐标逐条复核：0 条失效**，2 处微漂移已订正（路由模块数 10→**9**；`deps.py` 67→**68**，
      `auth.py` 26-32→**25-32**、87-90→**88-89**），结论均未变。明细见 `integration-log.md` §0
- [x] **T1 只读量化（¥0）**
      - [x] T1.1 复核 §1 的 11 条坐标 ⇒ 见 T0（表格实际 **13** 行，tasks 写 11 亦为计数漂移）
      - [x] T1.2 真机读数：`users` 行数（P6-O 收尾时实测 **0**）、`user_roles` 行数 +
            `user_id` 是否在 users 中命中（**无 FK 校验 ⇒ 可能孤儿**）
            ⇒ `users` **0 行**；`user_roles` **2 行** / 孤儿 **2（100%）**；附加：`documents` 36 行 / 孤儿 **36**、
            `audit_log` 2 行 / 孤儿 **2**。**连接角色 = `graphrag`（`rolbypassrls=True`）**；RLS 行为侧写「本地不可判」
      - [x] T1.3 穷尽所有取 `identity.actor_id` / `default_actor_id` 的落点
            （`documents.uploaded_by` / `affiliation_suspicions.reviewed_by` / `audit_log.actor_id` /
            `user_roles.user_id` / `ontology_schemas.confirmed_by_user` —— 还有没有别的？）
            ⇒ **10 类**（proposal 的 4 个不穷尽；新增：`user_roles.granted_by`、脚本侧 `uploaded_by`、
            请求头入口、评测固定主体、测试 fixture）。另发现 `audit_log.actor_id` 实值**不是** `DEFAULT_ACTOR_ID`
      - [x] T1.4 查 `Identity` 有无姓名 / 角色的可能来源（决定「第一个 user」要哪些字段）
            ⇒ **无**：`Identity` 只有 `org_id`/`actor_id`/`roles`/`source`，`roles` 恒空（现查 `user_roles`）；
            `users` 真机 7 列**无 name / email** ⇒ 第一个 user 只需 `username`/`password_hash`/`org_id`/`status`
      - [x] T1.5 查 `USERS_CONSUMER_MODULES`（`tests/test_guardrails.py:231`）的判定逻辑：
            登记模块后是否连带要求别的条件（**引用即红**的闸门怎么开）
            ⇒ 正反双向判（`hits - 登记` 与 `登记 - hits` 都不得非空）；`\bUser\b` 大小写敏感（`UserRole` 不算）；
            连带 = 注释 `:243-248` 的四件事（DR 归属 / 迁移 / ADR-0004 §2.1 / 护栏转正，非机械）
- [x] **T2** 产出《`users` 缺口量化报告》：六维表
      **读 / 写 / 端点 / schema / RLS / 主体来源** —— 每格必须有行号证据，查不到就写「未查到」
      ⇒ `integration-log.md` §2：六格**全部有坐标、零「未查到」格**；结论 = RLS 已就绪，**其余五维全 0**；
      **新发现**：`ADR-0006 §2.4` 席位口径依赖的 `activated_at` / `disabled_at` **两列都不存在**
- [x] **T3** 把「A 只做 License / B License+users 一批 / C 先补 users」**收敛成一条**，
      给出最小真接线方案（先造 user 的三条途径：注册端点 / seed 脚本 / SSO —— 成本与
      `password_hash` 禁入契约的约束点）
      ⇒ **收敛为 C**；方案 = **seed 脚本**（固定 `DEFAULT_ACTOR_ID` 作主键 ⇒ 孤儿 2→0，零业务代码）+ 消费登记；
      注册端点 / SSO **按 P0-D4 属新批次、不自主开工**；**不预置** `activated_at` / `disabled_at`（随 P4 同批）
- [x] **T4** 回切点：`check_session_drift.py`（S1 须读到 **10 条** Non-goals）+ 门禁全绿
      （契约 zero diff ／ `pytest` passed 不减 ／ `ruff` ／ `check_seams` ERROR 0）
- [x] **T5** 摊 diff + 提交（Conventional Commits）+ CI 实证回登
      ⇒ 提交 **`692cc8c8`**（3 文件 / +227 −11，全在 `changes/P6-P0/` + `docs/dev-doc-status.md`）；
      **CI run `37450050163` 四 job 全 success**，后端 job `112224160692` **997 passed / 5 skipped / 2 xfailed**
      （= CI 基线，0 回归）。push 一次即成功（未用 `--force`、未换远程）
