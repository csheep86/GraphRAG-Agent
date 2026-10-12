# 新会话开场提示词 · P6-V6（**拆掉 CI 上的 flaky 定时炸弹**）

> 👤 **用户先做一个勾选（开工前必读本段）**
>
> **D1｜若查证后根因落在「CI 的 PG 配置」（`ci.yml` 的 services / 角色），
> 是否批准改 CI？**
>   □ 批准 —— 可以改 `.github/workflows/ci.yml`（⚠️ `ci.yml:56-59` 明写
>     「三方必须一致」，改一处要改另外两处）
>   □ 不批 —— 根因落在 CI 配置时**停下报告**，本批只交付「查证结论」就收口
>   **没勾时按「不批」处理**。
>
> 其余（查证、修 `pg_scratch.py`、验证、回登）全是 **AI 段**，可无人值守。

---

> 🔒 **执行模式：混合（不是纯无人值守）**
> - **AI 段**：跑命令、查 `pg_stat_activity`、修 `drop_database()`、连跑验证、回登；
> - **人段**：只有 D1（要不要批改 CI）。
>   另外三种情况**自动停下报告**，见 §11。
>
> 📌 **计划真源**：[`changes/P6-V6/proposal.md`](./proposal.md)（Why / 根因假设 /
> Non-goals / 切片）+ [`tasks.md`](./tasks.md)（勾选表）。**已立批，不用再立**。
>
> 📦 **本文件自包含**：定位、坐标、假设、边界、验收都在本文里。
> ⏳ **写于 2026-10-12**（P6-V4 收尾当天）。开工先复核 §4 坐标表行号是否仍成立。

---

## 1. 本批一句话

修掉 `tests/pg_scratch.py::drop_database()` 里那条**会随机让 CI 变红**的
`pg_terminate_backend` 权限竞态 —— 它每次发作都伪装成"你这次改动把测试搞红了"。

---

## 2. 为什么是它（**三条机械理由**）

| # | 机器读数 | 说明 |
|---|---|---|
| 1 | run `38196713884`（head `60a5bbb`，**docs-only**）后端 job **failure**：`InsufficientPrivilege: permission denied to terminate process`，`1 failed / 1282 passed` | 代码树里**没有任何改动**却红 ⇒ 只能是竞态 |
| 2 | 下一个 run `38198414806`（head `382be27`，**含代码改动**）**四项全绿**，同一用例这次过了 | 坐实 **flaky**（偶发，非必现） |
| 3 | 它会让**任意**后续批次的 CI 随机红 | 红时最容易被读成"我改错了"，而最顺手的解法是**改测试让它绿** —— 正是 **R-10** 要防的那条路 |

---

## 3. 它不是一个"测试失败"，是一个"谎报"

失败用例：`backend/tests/test_rbac.py:459`
`test_migration_seeds_preset_roles_and_is_replayable`

它与 P6-V4 刚登记的第 4 个坑（「CI 红先看挂在哪一步」）**同一类病**：
**机器的结论在说谎**，形式是"看起来像失败、其实与改动无关"。

---

## 4. 已查证坐标表（**2026-10-12 实读，开工先复核行号**）

| 坐标 | 位置 | 用途 |
|---|---|---|
| **元凶** | `backend/tests/pg_scratch.py:124-141` `drop_database()` | `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name` —— **杀目标库所有连接** |
| 临时库命名 | `backend/tests/pg_scratch.py:172` | `name = f"{prefix}_{uuid4().hex[:12]}"` ⇒ **一次性随机名**（`graphrag_rbac_<uuid12>`）⇒ **排除**"外部 superuser 连上来" |
| 用例 | `backend/tests/test_rbac.py:459` / `:475` | `with scratch_database("graphrag_rbac") as name:` |
| 执行者 | `.github/workflows/ci.yml:115` | `DATABASE_URL_OWNER=postgresql+psycopg://app_owner:app_owner@.../graphrag_test` ⇒ **`app_owner` 非 superuser** |
| superuser 是谁 | `ci.yml:66` `POSTGRES_USER: graphrag`；`:156` `--admin-url ...graphrag:graphrag...` | 超级用户只在「建 RLS 角色」那一步用一次 |
| 为什么不能给它提权 | `ci.yml:107-113` | 业务测试走受限角色是为让 RLS 真被验证；`app_owner` 提权 ⇒ T1/T2/G-26 判据 4 失去意义 |
| 为什么不能吞异常 | `pg_scratch.py:169-170` | 原话：*残留的库最容易在下一次跑测时以「名字冲突 / 状态不干净」回来报复* |
| 三方一致性 | `ci.yml:56-59` | 改 `POSTGRES_DB` / `DATABASE_URL` / conftest 回落库名 ⇒ 三处都要改 |

---

## 5. 根因假设（⚠️ **是假设，不是结论 —— 开工第一件事是证实 / 证伪**）

排除"外部 superuser 连接"（临时库名一次性随机）之后，剩下最可能的一条：

**PG 后台进程。** 迁移刚跑完（建表 + 播数据）⇒ 触发 **autovacuum / autoanalyze**
在该库挂载 worker；它们在 `pg_stat_activity` 里的 `backend_type` 是
`autovacuum worker` / `background worker`（**不是** `client backend`），
通常以 **superuser** 身份出现 ⇒ 非 superuser 的 `app_owner` 杀不掉 ⇒ 报错。
autovacuum 的触发**取决于时机** ⇒ 完美解释偶发性。

**不许照着假设直接改。先把它打出来看。**（§8 V6-a）

---

## 6. 边界纪律（**Non-goals，不许越过**）

1. **不许 `try/except` 吞掉异常** —— 删库失败但测试继续 ⇒ 临时库残留 ⇒
   下次跑测回来报复（**R-9「恒绿即失效」**）。**宁可红，也不静默。**
2. **不许给 `app_owner` 加 `SUPERUSER`** —— 违反 ADR-0003 最小权限，
   且会让 RLS 判据失去意义。
3. **不许改这个测试的断言 / 判据让它绿**（**R-10**）—— 修的是**基础设施**，
   不是把失败藏起来。
4. **不顺带重构 `pg_scratch.py`** —— 只改 `drop_database()`；
   `ensure_database` / `scratch_database` / `_check_identifier` 一律不动。
5. **不动 CI 的 PG 镜像 / 端口 / 三方一致性** —— 除非 D1 批准。
6. **不做交付动作**，不碰任何判据阈值 / 量纲 / 契约。

---

## 7. 决策表

| 情况 | 怎么办 |
|---|---|
| V6-a 证实是后台进程 | 按 V6-b 只杀 `client backend` + 跳过自身；杀不掉的 ⇒ **明确报错**（不静默） |
| V6-a **证伪**，根因在 CI 配置 | **停下报告**；D1 批了才动 `ci.yml` |
| 只有"吞异常"才绿 | **停下报告** —— 那还不如不修 |
| 本机复现不出来 | 用 §9 的**可控复现法**，不要靠等 flaky |

---

## 8. 做法切片

| 切片 | 内容 |
|---|---|
| **V6-a** | **查证**：把 `pg_stat_activity` 的**实际行**打出来（至少 `pid` / `backend_type` / `usename` / `application_name` / `state` / `query`），指名"谁以 superuser 挂在那个库上"。**假设被证伪 ⇒ 停下，按真实根因重报** |
| **V6-b** | **按根因修 `drop_database()`**：候选 ① 只杀 `backend_type = 'client backend'` 且 `pid <> pg_backend_pid()`；② 杀不掉的改用等待 / 重试，仍存在则**明确报错** |
| **V6-c** | 稳定性验证：本机**连跑 ≥ 5 次** + 与迁移测试相邻跑；CI 再观察一次全量 run；回登 |

---

## 9. 可控复现法（**不要靠等 flaky**）

flaky 偶发，等它自己出现既慢又不可靠。**手工造出来**：

1. 起一个临时库（照 `pg_scratch` 的方式建 `graphrag_rbac_<随机>`）；
2. **用 superuser `graphrag` 连到这个库并保持连接**（`psql` / 一个 sleep 连接）；
3. 调 `drop_database(那个库名)` ⇒ **必现** `InsufficientPrivilege`。

有这个可复现场景，才能证明"修完真的好了"，也才能做 §10 的 **K3 反向守卫**。

---

## 10. 验收判据（**跑完才能收口**）

| # | 判据 | 期望 |
|---|---|---|
| **K1** | V6-a 输出里有**真实行证据**（不是推理） | 能指名"是谁" |
| **K2** | 修完该用例**连跑 ≥ 5 次全过** | 不再偶发 |
| **K3** | **反向守卫**：造"杀不掉的连接" ⇒ 必须**报错**，**不许**静默通过 | 这是本批最关键的守卫 |
| **K4** | `pytest tests -q` **不降**（1249 / 43） | 不倒退 |
| **K5** | `ruff check .` + `ruff format --check .`（**全量**）绿；`check_seams.py` OK 12 / ERROR 0 | 门禁不破 |
| **K6** | CI 全量 run **四项 success** | 远程验到 |

---

## 11. 升级用户的 4 类情况

1. 根因落在 **CI 的 PG 配置**（属 Non-goal 5）⇒ 见开头 **D1**；
2. 要动 `app_owner` 权限才解得掉（属 Non-goal 2）⇒ **停下报告**；
3. 修法只剩"吞异常"才绿 ⇒ **停下报告**；
4. V6-a **证伪**假设、且新根因超出本批边界 ⇒ **停下报告**。

---

## 12. 不许外推

- **不许**把"这次 CI 红了"归因给自己或任何批次 —— 先按 §4 坐标对名字；
- **不许**用 `try/except` 让删库失败变静默（**R-9**）；
- **不许**给 `app_owner` 提权换绿；
- **不许**因为本机跑 1 次绿了就宣称修好 —— flaky 要**连跑 ≥ 5 次**；
- **不许**顺手重构 `pg_scratch.py` 的其它函数。

---

## 13. 环境提醒（本机）

- 开工先 `docker ps` —— 本机 `graphrag-pg` / `graphrag-neo` 可能被系统停掉
  （2026-10-12 早上就遇到过：两者 `Exited (255)`，pytest 直接连不上库）。
  起法：`docker start graphrag-pg graphrag-neo`，等 ~12s。
- 本机 PowerShell 打印中文/符号**不再需要**手工设 `$env:PYTHONIOENCODING="utf-8"`
  （2026-10-12 已根治：scripts/ 内置兜底 + `tests/test_script_stdio_utf8.py` 门禁）。

---

## 14. 下一批指针

- P6-V6 收口 ⇒ 回 **P6-V5**（C3 真值 + TBD-7 裁决包，提示词在
  `changes/P6-V4/new-session-prompt.md`）；
- 修掉之后，记得**同步更正 P6-V4 提示词 §11 第 4 条**那条「已知 flaky」
  （它不再成立）—— 已写进 `tasks.md` §5 收尾项。
