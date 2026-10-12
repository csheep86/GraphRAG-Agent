# P6-V6：拆掉 CI 上的 flaky 定时炸弹（`pg_terminate_backend` 权限竞态）

> 计划真源：**无上游 plan 条目** —— 本批由 P6-V4 收尾时的**机器实测**发现
> （run `38196713884`，2026-10-12）。这类"不是任何人的需求、但会让所有人踩"的
> 缺陷，之前的处置习惯是"登记一下" ⇒ 于是它留成了定时炸弹。
> 立批裁决：**2026-10-12 用户**（在 AI 建议修之后）。

---

## 0. 一句话

修掉 `tests/pg_scratch.py::drop_database()` 里那条**会随机让 CI 变红**的
`pg_terminate_backend` 权限竞态 —— 它每次发作都伪装成"你这次改动把测试搞红了"。

---

## 1. 为什么做（**全是机器读数，不是转述文档**）

| # | 证据 | 说明 |
|---|---|---|
| 1 | run `38196713884`（head `60a5bbb`，**docs-only**）后端 job **failure** | 日志：`InsufficientPrivilege: permission denied to terminate process`；`DETAIL: Only roles with the SUPERUSER attribute may terminate processes of roles with the SUPERUSER attribute`；`1 failed, 1282 passed` |
| 2 | 失败用例 = `backend/tests/test_rbac.py:459` `test_migration_seeds_preset_roles_and_is_replayable` | 唯一失败项 |
| 3 | 该 run 的代码树 = docs-only | ⇒ **与本批（P6-V4）改动无关**；代码没变，只能是**竞态 / 环境** |
| 4 | 下一个 run `38198414806`（head `382be27`，**含代码改动**）**四项全绿** | 同一个测试这次过了 ⇒ 坐实 flaky |
| 5 | `backend/tests/pg_scratch.py:124-141` `drop_database()` | 元凶：`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name` —— 杀目标库**所有**连接 |
| 6 | `.github/workflows/ci.yml:115` `DATABASE_URL_OWNER=...app_owner...` | 执行者是 **`app_owner`（非 superuser）** |
| 7 | `.github/workflows/ci.yml:66` `POSTGRES_USER: graphrag` + `:156` `--admin-url ...graphrag:graphrag...` | 超级用户是 `graphrag`，只在「建 RLS 角色」那一步用一次 |
| 8 | `backend/tests/pg_scratch.py:172` `name = f"{prefix}_{uuid4().hex[:12]}"` | 临时库名**一次性随机**（`graphrag_rbac_<uuid12>`）⇒ **排除**"外部 superuser 连接连到这个库" |

**为什么必须修，而不能继续"登记一下"**：

1. 它会让**任意**后续批次的 CI 随机红。红的时候最容易被读成"我这次改错了"，
   而**最顺手的解法正好是改测试让它绿** —— 那正是纪律 **R-10** 反复防的那条路。
2. 它与 P6-V4 刚登记的第 4 个坑（「CI 红先看挂在哪一步」）是同一类病：
   **机器的结论在说谎**，形式是"看起来像失败、其实无关"。
3. 越晚修，它污染过的 run 越多 ⇒ 后面每一次"CI 红"都要先花时间排除它。

---

## 2. 根因假设（⚠️ **是假设，不是结论** —— 开工第一件事就是证实 / 证伪它）

排除法之后剩下最可能的一条：**PG 后台进程**。

- 迁移刚跑完（建表 + 播数据）⇒ 可能触发 **autovacuum / autoanalyze**
  在该库上挂载 worker；
- `pg_stat_activity` 里这些 worker 的 `backend_type` 是
  `autovacuum worker` / `background worker`，**不是** `client backend`；
- 它们通常以 **superuser** 身份出现 ⇒ 非 superuser 的 `app_owner` 去
  `pg_terminate_backend` 它们 ⇒ `InsufficientPrivilege`；
- 而 autovacuum 的触发**取决于时机** ⇒ 完美解释偶发性。

**开工必须先把它打出来看，不许照着假设直接改。** 具体做法见 §4 V6-a。

---

## 3. Non-goals（边界，**不许越过**）

1. **不许 `try/except` 吞掉这个异常** —— 那是最危险的一条路：删库失败但测试继续
   ⇒ 临时库残留 ⇒ 下一次跑测以「名字冲突 / 状态不干净」回来报复
   （`pg_scratch.py:169-170` 的原话：*残留的库最容易在下一次跑测时回来报复*）。
   **宁可红，也不静默。**（纪律 **R-9「恒绿即失效」**）
2. **不许给 `app_owner` 加 `SUPERUSER`** —— 违反 ADR-0003 最小权限；且会让
   RLS 相关判据（T1 / T2 / G-26 判据 4）失去意义（`ci.yml:107-113` 写明了原因）。
3. **不许改这个测试的断言或判据让它绿**（**R-10**）—— 本批修的是**基础设施**，
   不是把失败藏起来。
4. **不顺带重构 `pg_scratch.py`** —— 只改 `drop_database()` 这一段；
   `ensure_database` / `scratch_database` / `_check_identifier` 一律不动。
5. **不动 CI 的 PG 镜像 / 端口 / 三方一致性**（`ci.yml:56-59` 明写"改任一处都要
   改另外两处"）—— 除非查证后**证明确实在那里**，那属边界冲突，**先停上来报告**。
6. **不做交付动作**，不碰任何判据阈值 / 量纲 / 契约。

---

## 4. 做法切片

| 切片 | 内容 |
|---|---|
| **V6-a** | **查证**（不许跳过）：在**能复现的条件下**把 `pg_stat_activity` 的实际行打出来 —— 至少包含 `pid` / `backend_type` / `usename` / `application_name` / `state` / `query`，确认到底是谁以 superuser 挂在那个库上。**若假设被证伪 ⇒ 停下，按真实根因重报** |
| **V6-b** | **按根因修 `drop_database()`**：候选方向（**待 V6-a 确认后二选一或组合**）① 只杀**客户端后端**（`backend_type = 'client backend'`）并跳过自己（`pid <> pg_backend_pid()`）；② 杀不掉的连接**不硬杀**，改用等待 / 重试后仍存在则**明确报错**（不是静默）。⚠️ 修完必须仍保证「删库失败要响」 |
| **V6-c** | **稳定性验证**：本机**连跑多次**该用例（含与迁移测试相邻的顺序）确认不再偶发；CI 上至少**再观察一次**全量 run；回登 integration-log |

---

## 5. 出口判据（**跑完才能收口**）

| # | 判据 | 期望 |
|---|---|---|
| **K1** | V6-a 的输出里有**真实行证据**（不是推理） | 能指名"是谁" |
| **K2** | `drop_database()` 修完，`test_migration_seeds_preset_roles_and_is_replayable` **连跑 ≥ 5 次全过** | 不再偶发 |
| **K3** | **删库失败仍会响**（造一个杀不掉连接的场景 ⇒ 必须报错，**不许**静默通过） | 反向守卫 |
| **K4** | `pytest tests -q` 全量**不降**（1249 / 43） | 不倒退 |
| **K5** | `ruff check` + `ruff format --check .`（**全量**）绿；`check_seams.py` OK 12 / ERROR 0 | 门禁不破 |
| **K6** | CI 全量 run **四项 success** | 远程验到 |

---

## 6. 停机条件

- V6-a 证伪假设、且真实根因落在 **CI 的 PG 配置**（属 Non-goal 5）⇒ **停下报告**，不自行改 CI。
- 发现要动 `app_owner` 权限才解得掉（属 Non-goal 2）⇒ **停下报告**。
- 修法只剩"吞掉异常"才绿 ⇒ **停下报告**（那还不如不修）。
