**P6-P0 · 量化 users 消费者缺口（只读前置批，为 DR-C1 / G-23 License 铺路）**
边界草案已落并推送，HEAD 应为 `3703422`。以下为**新会话开场提示词**，直接整段粘贴即可开工。

你是本仓库的执行代理。新批次任务：**P6-P0 · 量化 users 消费者缺口**（只读前置批，为 DR-C1 / G-23 License 铺路）—— 边界草案已落并推送，HEAD 应为 `3703422`。

**第一步（必做）**：用 use_skill 加载 **unattended-sprint-execution** 技能，全程按其协议执行
（免请求自动提交、决策点默认采纳文档建议项，仅 4 类情况升级用户）。

**任务来源**：`changes/P6-P0/proposal.md` + `tasks.md`（⚠️ **草案**，待 sdd-assistant 定型）。
按 tasks.md 推进，**顺序不能反**：T0 复核坐标 → T1 只读量化 → T2 报告 → T3 收敛建议 →
T4 门禁 → T5 提交。**本批零业务代码**，产出 = 缺口量化报告 + 下一步边界坐标。

**开工自检（结论只能来自脚本输出，不能凭文档表格）**：
    cd backend && uv run python scripts/check_startup_readiness.py
确认：挂起（`[--]`）**只有 G-23**（G-12 已转 `[OK]`，A 组机械护栏零缺口）。

**边界纪律**：Non-goals **10 条**（proposal §4）。每个子任务收尾跑回切点：
    cd backend && uv run python scripts/check_session_drift.py
S1 必须读到 **10 条**边界；若报"没有 Non-goals" ⇒ 立即停下补边界（必须写成**编号列表**，
表格读不到）。注意：草案目录 `changes/P6-P0/` 必须是"最近活跃"的批次，否则 S1 会拿别的批次
的边界来对照本批改动 —— 报告看起来正常，对照的却是错的边界（2026-10-01 实踩过）。

**四个已查证的坑（proposal §2，不看必踩）**：

1. **引用即红**：`backend/tests/test_guardrails.py:231` 的 `USERS_CONSUMER_MODULES` 是**空登记
   集合**，扫 `app/` 下 `\bUser\b` ⇒ `app/` 一旦新增 `User` 引用就会红。**顺序**：先扩写该登记
   （交代 DR 归属 / 迁移 / ADR-0004 §2.1），**再**写实现 —— 漏任一侧 CI 必红（本批只量化，
   不走到这步，但报告必须说清楚闸门怎么开，见 T1.5）。
2. **`password_hash` 禁入契约与日志**：`test_guardrails.py:283` 断言契约不含它（`models.py:786`
   明写"不进契约"）⇒ 任何 schema / 端点**不得**带该字段。
3. **不许造假差异**：只为了让判定条件"看起来满足"而新增字段/端点、但无人真实读写 ⇒ 重演
   `task_retry_multiplier` 与 `domain_profile` 的病例（CODEBUDDY.md 预留纪律第 6 条）。
   本批**只量化不落地**正是为了避开它。
4. ⚠️ **本地读数可信度分级**（2026-10-06 实测）：本地 `system_session()` = `graphrag` 且
   **`rolbypassrls = True`** ⇒ ①「`users` = 0 行」结论**可信且更强**（绕过 RLS 只会看到更多行，
   连绕过都只有 0 行 ⇒ 全表确实空）；② 任何「RLS 对 `users` 生不生效」的结论本地**一律写
   「本地不可判」**，只由 CI（受限角色）判。**每次真机读数必须标注所用连接角色**。
   （这是 R28 对下一批的唯一污染路径 —— 本批不修 R28，只用这条纪律隔离。）

**基线（proposal §8，已体检，不必重跑）**：本地全量 **`991 passed / 11 skipped / 2 xfailed /
0 failed`**；CI 口径 **`997 passed`**（基线 996 **+1** = G-12）；容器 `graphrag-pg16` /
`graphrag-neo4j` 均 Up；`users` 表存在、**0 行**；护栏仅剩 G-23 挂起。
本地与 CI 的差值 8 条 = 真图用例在本地因无 `GRAPH_REAL_NEO4J_*` 而 skip（见 R28）。

**验收（proposal §6，5 条全机械、零判分）**：

① 六维缺口表（**读 / 写 / 端点 / schema / RLS / 主体来源**）每格都有**文件:行号**证据，
   查不到就写「未查到」，不许猜；
② 真机读数齐：`users` 行数（已实测 0）、`user_roles` 行数与其 `user_id` 孤儿数；
③ **零代码改动** ⇒ 契约 **zero diff**、`pytest` passed **不减**、`ruff check` +
   `ruff format --check`、`check_seams` **ERROR 0**；
④ drift 的 S1 读到 **10 条** Non-goals；
⑤ 结论**二选一不许含糊**：要么给出「可开工的最小真接线方案」，要么明确「需用户拍板的
   范围问题」（按 P0-D4 升级）。

**提交与推送**：自动提交（Conventional Commits）。`git push origin main` 失败就重试
（本机 GitHub 连接时好时坏，**非 DNS**；P6-O 时第 19 次才成功），仍失败就把命令给用户，
**不要**改用 `--force` 或其它远程。

**升级用户的 4 类情况**：① 量化结论要求**新建端点 / schema / 注册流程**（= 新建消费者，
属新批次，按 P0-D4 停下）；② 需要改 Non-goals 任一条；③ 判据无法机械达成；
④ §1 的行号坐标大面积失效、无法就地订正（草案状态不适合靠猜推进）。

**收尾**：报告写入 `changes/P6-P0/integration-log.md`，勾选 `tasks.md`，并同步
`docs/dev-doc-status.md`（若结论改变了既有登记）。**不得**宣称「账号体系已落地」——
G-18 绿 **≠** 落地（`users` 仍 0 消费者，需求基线 `:228`）。
