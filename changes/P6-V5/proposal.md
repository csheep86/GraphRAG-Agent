# P6-V5：C3 真值收口（**先清脏数据**）+ TBD-7 裁决包

> 计划真源：**本批此前无 proposal** —— 由 P6-V4 §3 切片表的 **V4-c 遗留**转来，
> 并经 [`../P6-V6/new-session-prompt.md`](../P6-V6/new-session-prompt.md)（v2 · 2026-10-12，HEAD `49d8c63`）
> 复核定位。
> ⚠️ **命名疑点（未裁决）**：该提示词正文自称「本批 = P6-V5」，文件却落在 `changes/P6-V6/`，
> 且 §15 又称下份提示词应落在 `changes/P6-V5/`。**本批目录暂按提示词正文取 `P6-V5`**，
> 待用户二选一定名后再调（见 §6 停机条件第 4 条）。
>
> 🔒 **执行模式：混合**（AI 段 / 人段，**不可混**）
>
> | 段 | 谁做 | 内容 |
> |---|---|---|
> | AI 段 | AI | 跑命令、搬数字、定位脏数据、校验门禁、跑 `--calibrate`、**只给建议**、回登日志 |
> | 人段 | 用户 | ① D1 批不批真 LLM；② **TBD-7 采纳哪个阈值**（AI **不得代填**） |
>
> 📌 **2026-10-12 第二次会话决议**：D1 = **稍后再定** ⇒ 本会话**只推进零费用动作**
> （V0 清脏数据 + 拉基线），**真机实测（切片 V5-c）待用户点头再开**。

---

## 0. 一句话

P6-V4 已把 C3-a / C3-b 的**出数能力**补齐（三态 + 取样器），但**真值仍是 `BLOCKED`**；
且 2026-10-12 实测发现本机 `cost_metrics` 已被测试写脏 1 行 —— **`doc_count=0`、
`incremental_cost=NULL`**，直接 `--live` 读 C3 会吐出一个**看似真值、实为测试残留**的数。
本批**先隔离清场**，在 D1 授权前把「能不能出真值」这个问题之外的**所有前置工作做到位**。

---

## 1. 为什么做（**机械读数，2026-10-12 实读复核**）

| # | 证据 | 说明 |
|---|---|---|
| 1 | 判据读口已通：P6-V4 注入探针测得 C3-a = `20000.0` token/doc、C3-b = `0.25`；本机 pytest **1251 passed / 43 skipped**；`check_seams` **OK 12 / ERROR 0** | 挡住真值的**不是代码** |
| 2 | **真值缺口性质已变**（旧口径「`cost_metrics` 均空」**已过期，勿再引用**）：表里有 **1 行测试写进去的假数据** —— `stage='extraction'`、`org_id=DEFAULT_ORG_ID`、`metric_date=2026-10-12`、`token_usage_total=0`、`doc_count=0`、`counted_doc_ids=[]`、`incremental_cost=NULL`、`full_rebuild_cost=4`、`created_at=2026-10-12 03:47:29+00`（= 那次全量 pytest 的运行窗口） | ⇒ **先隔离，再决定是否真跑** |
| 3 | C1~C3 / 多跳 / 拒答五条准入线里**只有 C3 没有真值**；`EVAL_SINGLE_DOC_TOKEN_CEILING` 仍是 **provisional**（`backend/app/core/config.py:302` = 32 000） | 即便出数也只能 `PASS(provisional)`，**不构成达标证据** ⇒ TBD-7 必由人裁决 |

---

## 2. What Changes

- **V5-a｜隔离清场**（本会话做）：定位把那行写到 `DEFAULT_ORG_ID` 下的**测试用例**，
  把写收敛到独立 org / 事务回滚 / fixture 清理；清空已有脏行；使 `--live` 读到的
  **不再是测试残留**。
- **V5-b｜基线复核**（本会话做）：`check_startup_readiness` / `ruff` / `check_seams` /
  `pytest` 全量，确认 Harbor 未倒退，并把 P6-V6 之后的新 HEAD（`1c32d7e`）纳入核对。
- **V5-c｜真机实测**（⏸ **D1 未批，本会话不做**）：真实入库一次 → 触发一次增量重算 →
  `--live` 读 C3-a / C3-b → 导出 → `--calibrate` → 出裁决包。
- **V5-d｜矩阵回写**：拿到真值后由**架构师**单独提交改
  `docs/acceptance-traceability-matrix.md:205`（C3-a）/ `:206`（C3-b）。

## Impact

- **contracts/openapi.yaml**：无（不改 `stage` 切片契约，P6-V3 §6.3 遗留维持挂起）。
- **frontend/**：无。
- **backend/**：仅测试侧隔离改动（V5-a）；**不改** `config.py` 阈值、**不改**
  `cost_metrics.py` 聚合口径。
- **prompts/**：无。

---

## 3. Non-goals（边界，**6 条，不许越过**）

1. **不自动改阈值** —— `--calibrate` 只输出建议，**绝不写 `config.py` / `.env`**。
   写入 `EVAL_SINGLE_DOC_TOKEN_CEILING` 只能由**人**做（且须同步 `.env.example`）。
2. **不动 C3-b 的量纲裁决** —— 2026-10-10 拍板 A 组「图规模同量纲」（实体数 + 关系数）。
3. **不做 `stage` 切片契约变更 / 仪表盘改造**（P6-V3 §6.3 遗留，属契约变更）。
4. **不做交付动作** —— P6-X 演练 / release notes / 打 tag 一律不碰。
5. **不许伪造 `value`** —— 无数据 ⇒ `BLOCKED` + `value=null`，**不是 0**。
6. **不许以降低判据换绿**（纪律 **R-10**）—— 真值难看就如实登记，再交用户裁决。
7. **（本会话追加）不许起任何真 LLM 调用** —— D1 未批 ⇔ 零 LLM 费用，
   含"顺手跑一次看看能不能出数"。

---

## 4. 出口判据（**跑完才收口**）

| # | 判据 | 期望 |
|---|---|---|
| **K0** | 本机 `cost_metrics` 脏行已定位到**写入用例**并隔离/清空，`--live` 读不到它 | V0 = 本会话第一件事，**做完才谈真值** |
| **K1** | `check_startup_readiness.py --self-test` | 7 条全过，退出码 0 |
| **K2** | `ruff check` + `ruff format --check`（**全量** 294 files） | 绿 |
| **K3** | `check_seams.py` | OK 12 / ERROR 0 / WARN 0 |
| **K4** | `pytest tests -q` 全量 | **不降**（本机基线 **1251 passed / 43 skipped**） |
| **K5** | `pytest tests/test_eval_acceptance_cli.py tests/test_eval_cost_criteria.py -q` | 既有断言不崩（锚点 `:76-78` / `:125-126` / `:52`） |
| **K6** | **（仅 D1 批准时）** C3-a / C3-b 出数 | `value` 非 null；仍 `BLOCKED` 则 `blocked_by` 必须点名**当前**真实缺口 |
| **K7** | 真值出来后回改 `docs/acceptance-traceability-matrix.md:205` / `:206`（架构师单独提交） | 防第四次过期 |

---

## 5. 已查证坐标表（2026-10-12 实读，**开工先复核行号**）

| 坐标 | 位置 |
|---|---|
| 抽取侧记账（调用点 / 定义点） | `backend/app/tasks/registry.py:566` → `backend/app/services/cost_metrics.py:113` |
| 全量分母（调用点 / 定义点） | `backend/app/tasks/registry.py:837` `if fresh_build:` → `backend/app/services/cost_metrics.py:170` |
| 增量分子（调用点 / 定义点） | `backend/app/services/kg/incremental.py:305` → `backend/app/services/cost_metrics.py:202` |
| 读侧聚合 / 取样器 / 校准 | `backend/app/services/cost_metrics.py:494` `aggregate_stage` / `backend/scripts/export_cost_records.py` / `backend/scripts/eval_acceptance.py:153` `_calibrate` |
| TBD-7 阈值 | `backend/app/core/config.py:302`；`.env.example:328`；消费者 `backend/app/evaluation/runner.py:805` / `:825` |
| 真实入库入口 | `scripts/ingest_affiliation_sources.py --purge --corpus-dir ../demo/affiliation/generated --kg-version affiliation-demo-v2`（CI 同款 `.github/workflows/ci.yml:226`；⚠️ 路径**必须带 `../`**） |
| 锚点断言 | `backend/tests/test_eval_acceptance_cli.py:76/77/78`、`:125/126`、`:52` |
| 夹具 | `backend/tests/conftest.py:250` `pg_active_kg_version`（autouse，恒返回 `v-test`）、`:468` `real_pg_get_active` |
| 矩阵行 | `docs/acceptance-traceability-matrix.md:205` / `:206` |

---

## 6. 停机条件

1. 定位脏行时发现**根因在业务代码**（非测试隔离）⇒ **停下报告**，那属新缺陷、需单独立批。
2. 需要改契约 / 改量纲才能出数 ⇒ **停下报告**（Non-goals 2 / 3）。
3. CI 红了且复核两遍仍红 ⇒ **不许先改测试让它绿**（R-10），按报告路径走。
4. **`P6-V5` 目录命名**与 `changes/P6-V6/` 已有提示词冲突 ⇒ 交用户二选一，不自作主张搬目录。
