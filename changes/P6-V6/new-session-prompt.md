# 新会话开场提示词 · P6-V5（**C3 真值 + TBD-7 裁决包**）

> 🏷️ **版本：v2 · 2026-10-12** —— **P6-V5 提示词的当前有效版本**（HEAD `49d8c63`）
>
> ⛔ **已被本版取代的旧版**：`v1 · 2026-10-11` = `changes/P6-V4/new-session-prompt.md`。
> 该文件已改为**重定向存根**（不再有正文）—— 两份都有正文时无法判断哪个新，
> 故只保留**一处正文**。旧版 §2 理由 #2（「`cost_metrics` 均空」）与 §8 基线
> （1249）**均已过期，已被本版复核订正**。
>
> 📌 **正文只在当前批次目录**（`changes/<当前批次>/new-session-prompt.md`）——
> 这是本仓库的既定约定，故 v2 落在 `P6-V6/` 而不是 `P6-V4/`。

> 👤 **用户先做两个勾选（开工前必读本段）**
>
> **D1｜要不要批真机实测**（会产生 LLM 费用）：
>   □ 批准 —— 跑一轮真实抽取 + 一次增量重算，拿到 C3-a / C3-b **真值**
>   □ 仍不批 —— C3 真值维持 `BLOCKED`，本批改为「**P6-W**」（DR-E2 备份 / 恢复，W1 已裁决）
>   **两个都没勾时按「仍不批」处理**：不许自行起 LLM 账单。
>
> **D2｜TBD-7 阈值由你拍板**（AI **不得代填**）：本批只负责把
> 「实测值 / 建议值 / 各选项后果」摊到你面前，**采纳哪一个是你一个人的决定**。

---

> 🔒 **执行模式：混合（不是纯无人值守，也不是纯人工）**
>
> | 段 | 谁做 | 内容 |
> |---|---|---|
> | **AI 段**（可无人值守） | AI | 跑命令、搬数字、定位脏数据、校验门禁、跑 `--calibrate`、**只给建议**、回登日志 |
> | **人段**（**AI 不得代做**） | 用户 | ① D1 批不批真 LLM；② **TBD-7 采纳哪个阈值** |
>
> ⚠️ 两条写死：
> - **真 LLM 调用不经批准不许起**；
> - **不许"先把阈值写进 `config.py` 再请用户复核"** —— 那等于把裁决做成既成事实。
>   `eval_single_doc_token_ceiling` 的**唯一写入者是人**（且必须同步 `.env.example:328`）。
>
> 📌 **计划真源**：本批**尚无 proposal**（P6-V4 的 V4-c 切片留在这里）
> ⇒ 开工第一步是照 `specs/_template/` 立 `changes/P6-V5/proposal.md` + `tasks.md`，
> **先写边界（Non-goals）再动手**（`check_session_drift.py` S1 报「没有 Non-goals」就要停）。
> 上游真源：[`../P6-V4/proposal.md`](../P6-V4/proposal.md) §3 切片表 + §6 停机条件。
>
> 📦 **本文件自包含**：批次定位、上游状态、坐标、判据、坑都在本文里。
> ⏳ **写于 2026-10-12**（P6-V6 收口当天，HEAD `49d8c63`）。
> 🔗 旧版 v1（2026-10-11）在 `../P6-V4/new-session-prompt.md`，**已改为存根**，
>    正文一律以本文件为准。

---

## 1. 起点确认（**先对这三个再动手**）

```
HEAD（本地 == origin/main）: 49d8c63  docs(changes): P6-V6 回登实测证据 + 勾选收尾
上一条                    : 1d87a0f  fix(tests): P6-V6 拆掉 pg_terminate_backend 权限竞态（CI flaky）
工作区                    : 干净（只有 .specstory/ .vscode/ delivery-kit/ 等既有的未跟踪目录）
```

**P6-V6 已收口**（CI flaky 定时炸弹已拆），本批是它的下一批。
⚠️ 若 HEAD 不是 `49d8c63`，**先停**：本文件里的坐标与基线是照这个提交实读的。

---

## 2. 本批一句话

P6-V4 已经把 C3-a / C3-b 的**出数能力**补齐（三态 + 取样器），但**真值仍是 `BLOCKED`**。
本批要么**真跑一轮**把真值拿出来（D1 批准），要么**如实维持 `BLOCKED`** 转去做 P6-W。
⚠️ **且开工第一件事不是跑，是清场**：本机 `cost_metrics` 已经被测试写脏了（见 §6 坑 4）。

---

## 3. 为什么是它（**三条机械理由**，2026-10-12 复核，**不是排期感觉**）

| # | 机器读数 | 说明 |
|---|---|---|
| 1 | 判据**读口已通**：P6-V4 注入探针实测 C3-a = `20000.0` token/doc、C3-b = `0.25`；`pytest` 本机 **1251 passed / 43 skipped**；`check_seams` **OK 12 / ERROR 0** | 挡住真值的**不是代码** |
| 2 | **真值缺口的性质已变**（2026-10-12 实读 `cost_metrics`）：不再是「表里没数据」，而是「表里有 **1 行测试写进去的假数据**」（`doc_count=0`、`full_rebuild_cost=4`） | ⇒ 先隔离，再决定要不要真跑。旧口径「cost_metrics 均空」**已过期，勿再引用** |
| 3 | C1~C3 / 多跳 / 拒答五条准入线里**只有 C3 没有真值**；且 `EVAL_SINGLE_DOC_TOKEN_CEILING` 仍是 **provisional**（`config.py:302` = 32 000） | 即便出数也只能 `PASS(provisional)`，**不构成达标证据** ⇒ TBD-7 必由人裁决 |

---

## 4. 开工自检（**动手写代码前先跑，结论只能来自脚本输出**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

它按护栏**真实状态**分三档（`[OK]` 已生效 / `[~~]` 部分生效 / `[--]` 挂起）；
**`[--]` / `[~~]` 所对应的 DR，本批一律不得宣称完成**。
每个子任务收尾再跑：

```bash
cd backend && uv run python scripts/check_session_drift.py
```

**S1 报「没有 Non-goals」⇒ 先停下来补边界**，不许边写边定边界。

---

## 5. 已查证坐标表（**2026-10-12 逐条实读，开工先复核行号**）

| 坐标 | 位置 | 复核 |
|---|---|---|
| 抽取侧记账（**调用点**） | `backend/app/tasks/registry.py:566` `record_extraction_usage(` | ✅ |
| 抽取侧记账（**定义点**） | `backend/app/services/cost_metrics.py:113` `def record_extraction_usage` | ✅ |
| 全量分母（**调用点**） | `backend/app/tasks/registry.py:837` `if fresh_build:` → `record_full_rebuild_cost(...)` | ✅（`:837` 正是 `if fresh_build:`） |
| 全量分母（**定义点**） | `backend/app/services/cost_metrics.py:170` `def record_full_rebuild_cost` | ✅ |
| 增量分子（**调用点**） | `backend/app/services/kg/incremental.py:305` `record_incremental_rebuild_cost(` | ✅ |
| 增量分子（**定义点**） | `backend/app/services/cost_metrics.py:202` `def record_incremental_rebuild_cost` | ✅ |
| 读侧聚合 | `backend/app/services/cost_metrics.py:494` `def aggregate_stage` | ✅（旧提示词未给行号，本批补齐） |
| 取样器 | `backend/scripts/export_cost_records.py` | ✅ |
| 校准 | `backend/scripts/eval_acceptance.py:153` `def _calibrate`（**只输出建议、绝不写 config**） | ✅ |
| TBD-7 阈值 | `backend/app/core/config.py:302` `eval_single_doc_token_ceiling = 32_000`；`.env.example:328`；消费者 `backend/app/evaluation/runner.py:805` / `:825` | ✅ |
| 真实入库入口 | `scripts/ingest_affiliation_sources.py --purge --corpus-dir ../demo/affiliation/generated --kg-version affiliation-demo-v2`（CI 同款 `.github/workflows/ci.yml:226`；⚠️ 路径**必须带 `../`**） | ✅ |
| 锚点断言 | `backend/tests/test_eval_acceptance_cli.py:76/77/78`（`"M2"` / `"TBD-7"` / `"增量重算"`）、`:125/126`（`"M2"` / `"增量重算"`）、`:52` `test_offline_yields_no_criterion_numbers` | ✅ |
| 夹具 | `backend/tests/conftest.py:250` `pg_active_kg_version`（autouse，恒返回 `v-test`）、`:468` `real_pg_get_active`（撤桩用） | ✅ |
| 矩阵行 | `docs/acceptance-traceability-matrix.md:205`（C3-a）/ `:206`（C3-b） | ✅ |

---

## 6. 四个坑（**别再踩**；坑 4 是 P6-V6 期间实测新发现的）

1. **offline 绝不能读库**：本机测试库是**持久库**（P6-V2 起记过两次）。offline 一旦读
   `cost_metrics`，真图写入的成本行会让 offline 报告**产出判据数字**
   ⇒ `test_offline_yields_no_criterion_numbers`（`:52`）当场红，报告也不再幂等。
   ⇒ 判据读库**只在 live 分支**。
2. **conftest 的 `autouse` 桩会顶掉 `get_active`**（`tests/conftest.py:250` 恒返回 `v-test`）：
   要真读 PG 的 active 版本，必须显式请求 `real_pg_get_active`（`:468`）撤桩
   ——否则会以「基线版本不一致」的形态红掉，**看起来像增量失败，实为夹具问题**。
3. **`tests/test_cost_metrics.py::test_dashboard_endpoint_returns_real_rows` 有顺序耦合**：
   真图用例会**真的写**成本列 ⇒ 它读到脏值。历史修法是**改它的隔离**（先清本 org 当日行），
   **不是**改判据让它绿。
4. 🆕 **`cost_metrics` 已经不干净了（2026-10-12 实测，本批头号陷阱）**：
   本机跑完一次全量 `pytest tests -q` 后，表里多出 **1 行**——

   ```
   stage='extraction'  org_id=00000000-0000-4000-8000-000000000001（= DEFAULT_ORG_ID，.env.example:217）
   metric_date=2026-10-12   token_usage_total=0   doc_count=0   counted_doc_ids=[]
   single_doc_cost=0   incremental_cost=NULL   full_rebuild_cost=4   cost_ratio=0
   created_at=2026-10-12 03:47:29+00   ← 正是那次全量 pytest 的运行窗口
   ```

   ⇒ **危险**：直接 `--live` 读 C3 会吃到这行 —— C3-a 的分母 `doc_count=0`
   （0 或除零）、C3-b 的分子 `incremental_cost=NULL` ⇒ 会吐出一个
   **看起来像真值、其实是测试残留**的数，正撞 §12「不许外推」。
   ⇒ **开工第一步 = 定位写入用例并隔离/清空**，确认 `--live` 读到的不是它，再谈真值。
   真写库的候选（供排查，别照抄结论）：`tests/test_cost_metrics_graph.py:566` / `:573`
   （`record_full_rebuild_cost` / `record_incremental_rebuild_cost`；但 `test_dashboard_ratio_matches_row_level`
   用的是 `uuid4()` org 且有 `finally` 清理 ⇒ **需复核是不是它**）、
   `tests/test_cost_metrics_extraction.py:357`（对 `app.tasks.registry.record_extraction_usage` 打桩 `_boom`）、
   `tests/test_extraction_llm_engine.py`。

---

## 7. 边界纪律（**Non-goals，立 proposal 时不得少于 6 条**）

1. **不自动改阈值** —— `--calibrate` 只输出建议，**绝不写 `config.py` / `.env`**。
   写入 `EVAL_SINGLE_DOC_TOKEN_CEILING` 只能由**人**做（且必须同步 `.env.example`）。
2. **不动 C3-b 的量纲裁决** —— 2026-10-10 拍板 A 组「图规模同量纲」（实体数 + 关系数）。
3. **不做 `stage` 切片契约变更 / 仪表盘改造**（P6-V3 §6.3 遗留，属契约变更）。
4. **不做交付动作** —— P6-X 演练 / release notes / 打 tag 一律不碰。
5. **不许伪造 `value`** —— 无数据 ⇒ `BLOCKED` + `value=null`，**不是 0**。
6. **不许以降低判据换绿**（R-10）—— 真值难看就如实登记，再交用户裁决。

---

## 8. 决策表（**碰到就照这里办，别临场发挥**）

| 情况 | 怎么办 |
|---|---|
| D1 批准 | 起后端 → 真实入库一次 → 触发一次**增量重算** → `--live` 读 C3 → 导出 → `--calibrate` → 出裁决包 |
| D1 不批 | C3-a / C3-b 如实维持 `BLOCKED`，**不要**为让它绿而注入样本当真值（P6-V4 那次注入探针是**证明读口会出数**，不是真值） |
| 开工发现 `cost_metrics` 有残留行 | **先定位 + 清理 + 隔离**（坑 4），**不许**带着脏数据出数 |
| 实测值出来后 | **只给数据 + 各选项后果**，TBD-7 采纳由用户定 |
| 发现要改量纲才能出数 | 属 ② 裁决，**先缩范围再报告** |

---

## 9. 已完成项（**不要再重做**）

| 切片 | 状态 |
|---|---|
| V4-a 两个 evaluator 出数化（三态） | ✅ `d66bec0` |
| V4-b 取样器 `scripts/export_cost_records.py` + `--calibrate` 提示订正 | ✅ `d66bec0` |
| V4-c 真机实测 | ❌ **未做**（D1 未批准）⇒ **本批的核心** |
| `tests/test_eval_cost_criteria.py`（J1~J5，11 条） | ✅ |
| **P6-V6**（CI flaky：`pg_terminate_backend` 权限竞态） | ✅ `1d87a0f` + `49d8c63`，CI run `38201283243` 四项全绿 |

---

## 10. 基线（**CI / 本地两套口径都要记，别混用**）

```
pytest（本机，双容器 Up）: 1251 passed, 43 skipped, 0 failed
                          （= 1249 + 2；那 2 条是 P6-V6 新增的
                           tests/test_pg_scratch_drop.py 守卫）
pytest（CI，run 38201283243 / head 1d87a0f）: 1287 passed, 7 skipped
                          （= 基线 run 38198414806 的 1285/7 + 2）
ruff check / format --check: All checks passed（全量 ⇒ 294 files）
check_seams.py            : ERROR 0 / WARN 0 / OK 12
check_startup_readiness   : --self-test 7 条全过
check_session_drift       : S1 6 条 / S2 1 文件 +100 行 / S3~S5 未触发
```

⚠️ **本机 43 skipped / CI 7 skipped 是两套口径**，比较时必须同侧比。
⚠️ **别拿 1247 当基线** —— 那是 `tests/test_script_stdio_utf8.py`（GBK 门禁）补进来**之前**的数。
⚠️ 本机 PowerShell 打印中文**不再需要**手工设 `$env:PYTHONIOENCODING="utf-8"`（2026-10-12 已根治）。

---

## 11. 验收判据（**跑完才能收口**）

| # | 命令 / 判据 | 期望 |
|---|---|---|
| **V0** | **先隔离 / 清空本机 `cost_metrics` 的测试写入**（定位坑 4 那行的写入用例 + 清理），并确认 `--live` 读到的不是它 | 开工第一件事；**做完才能谈真值** |
| **V1** | `ruff check` + `ruff format --check`（**全量**） | 绿 |
| **V2** | `check_startup_readiness.py --self-test` | 7 条全过，退出码 0 |
| **V3** | `pytest tests -q`（全量） | **不降**（本机 **1251 / 43**） |
| **V4** | `check_seams.py` | OK 12 / ERROR 0 / WARN 0 |
| **V5** | `pytest tests/test_eval_acceptance_cli.py tests/test_eval_cost_criteria.py -q` | 既有断言**不得崩**（锚点 `:76-78` / `:125-126` 仍成立，已复核） |
| **V6** | **（仅 D1 批准时）** 真跑一轮后 C3-a / C3-b 出数 | `value` 非 null；若仍 `BLOCKED`，`blocked_by` 必须点名**当前**真实缺口 |
| **V7** | **真值出来后立刻回改 `docs/acceptance-traceability-matrix.md:205` / `:206`**（架构师侧**单独提交**） | 那两行刚在 2026-10-11 被 P6-V4 订正过（措辞已准、真值仍写 `BLOCKED`）⇒ **拿到真值就回写**，否则会第四次过期。C3 线已因「机器变、文案没复核」过期过三次 |

---

## 12. 提交推送纪律

- **角色隔离**：AI 段默认只**后端开发 B**（只改 `backend/`）；
  改 `specs/` / `contracts/` / `docs/` / plan ⇒ 归**架构师**段（**单独提交**）。
- **分支**：沿用 P4~P6-V6 —— **`main` 直推**，不另开分支。
- **提交**：按**后端 / 架构师 / changes** 分段 Conventional Commits，跨侧**不得**混在一起。
- **推送**：⚠️ GitHub 推送通道不稳 —— **2026-10-12 晚实测连推两次均
  `Recv failure: Connection was reset`**，最后由用户手推成功。
  ⇒ 失败重试**一次**，仍失败就**把完整命令交给用户**，**不许**改 remote / 绕道：

  ```bash
  git -C <repo> push origin main
  ```

- **回登纪律**（P5-B §5.3）：**不要为"多记一个 run id"而提交** —— 回登 ⇒ 新 commit ⇒ 新 run。

---

## 13. 升级用户的 4 类情况

1. **要不要起真 LLM**（会产生费用）⇒ 见开头 **D1**；
2. 要动**已裁决**的 rubric / 判据口径（量纲、阈值、C3 出数口径）⇒ **先缩范围再报告**；
3. 边界冲突（要碰 Non-goal，例如必须改契约才能出数）；
4. CI 红了且复核两遍仍红（**不许先改测试让它绿**）。
   ✅ **原先那条「已知 flaky」已于 P6-V6（2026-10-12）修掉，不再需要特判**：
   `test_migration_seeds_preset_roles_and_is_replayable` 的
   `InsufficientPrivilege: permission denied to terminate process` 根因是
   `tests/pg_scratch.py::drop_database()` 把 **autovacuum worker**
   （以 bootstrap superuser 挂在临时库上）也塞进了 `pg_terminate_backend`。
   现在只踢「`client backend` + 同角色 + 排除自己」，后台进程等它自己走，
   仍删不掉则**抛错**并列出残留连接（守卫 `tests/test_pg_scratch_drop.py`）。
   ⇒ **再看到这个名字的失败，它是真失败了**，按本条第 4 条处理。

---

## 14. 不许外推

- **不许**把 P6-V4 的注入探针值（`20000.0` / `0.25`）当真值登记 —— 那是**注入样本的算术**；
- 🆕 **不许**把本机 `cost_metrics` 那行 `doc_count=0` 的**测试残留**当真值（坑 4，
  本批头号陷阱）；
- **不许**把 `--calibrate` 的建议值写进 config 后说"已校准"；
- **不许**因为分位数退化（P50 == P90，日聚合摊平所致）就宣称"已拿到分布上界"；
- **不许**为了让 P8「零缺口」通过而把判据改松；
- **不许**替用户拍 TBD-7（哪怕"先写上再复核"也不行）。

---

## 15. 下一批指针

- D1 **批准** ⇒ 本批（P6-V5）跑完真值 + 裁决包 ⇒ 下一批回 **P6-W**
  （DR-E2 备份 / 恢复，W1 裁决 = 方案 I：`backup` / `restore` 两条命令 +
  `backup-manifest.json` 契约含 SHA-256）。
- D1 **不批** ⇒ 本批直接改名做 **P6-W**，C3 真值作为**遗留**带进 P8 对账。
- 届时提示词落在 **`changes/P6-V5/new-session-prompt.md`**（当前批次目录下、写给下一批），
  不要在聊天里贴全文。
