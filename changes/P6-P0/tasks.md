# P6-P0 · 任务清单（量化 `users` 消费者缺口）

> 上游：`changes/P6-O/`（G-12 已转正）。边界见 `proposal.md` —— ⚠️ **草案，待 sdd-assistant 定型**。
> **本批零业务代码**：产出 = 缺口量化报告 + 下一步边界坐标（给 DR-C1 / G-23 License 铺路）。
> **顺序不能反**：T1 只读，**先复核坐标再造结论**。

- [ ] **T0（新会话第一步，草案状态必做）**：复核 `proposal.md` §1 的 11 条行号坐标 —— **失效即停**，
      不得凭印象继续；坐标有漂移就先修坐标再开工
- [ ] **T1 只读量化（¥0）**
      - [ ] T1.1 复核 §1 的 11 条坐标
      - [ ] T1.2 真机读数：`users` 行数（P6-O 收尾时实测 **0**）、`user_roles` 行数 +
            `user_id` 是否在 users 中命中（**无 FK 校验 ⇒ 可能孤儿**）
      - [ ] T1.3 穷尽所有取 `identity.actor_id` / `default_actor_id` 的落点
            （`documents.uploaded_by` / `affiliation_suspicions.reviewed_by` / `audit_log.actor_id` /
            `user_roles.user_id` / `ontology_schemas.confirmed_by_user` —— 还有没有别的？）
      - [ ] T1.4 查 `Identity` 有无姓名 / 角色的可能来源（决定「第一个 user」要哪些字段）
      - [ ] T1.5 查 `USERS_CONSUMER_MODULES`（`tests/test_guardrails.py:231`）的判定逻辑：
            登记模块后是否连带要求别的条件（**引用即红**的闸门怎么开）
- [ ] **T2** 产出《`users` 缺口量化报告》：六维表
      **读 / 写 / 端点 / schema / RLS / 主体来源** —— 每格必须有行号证据，查不到就写「未查到」
- [ ] **T3** 把「A 只做 License / B License+users 一批 / C 先补 users」**收敛成一条**，
      给出最小真接线方案（先造 user 的三条途径：注册端点 / seed 脚本 / SSO —— 成本与
      `password_hash` 禁入契约的约束点）
- [ ] **T4** 回切点：`check_session_drift.py`（S1 须读到 **10 条** Non-goals）+ 门禁全绿
      （契约 zero diff ／ `pytest` passed 不减 ／ `ruff` ／ `check_seams` ERROR 0）
- [ ] **T5** 摊 diff + 提交（Conventional Commits）+ CI 实证回登
