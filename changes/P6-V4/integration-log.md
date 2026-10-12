# P6-V4 集成日志（让 C3-a / C3-b 真正出数）

> 基线：`e77b2ed`（立批提交）。本文件记的是**本机实跑读数**，不是转述 proposal。
> 用户裁决（2026-10-11 开工前）：**D1 未勾 ⇒ V4-c（真 LLM 实测）暂不批**；
> **D3 未勾 ⇒ 按「是」处理，不碰 `private.pem`**。

---

## 1. 开工复核（§2 三件事，**全部实测，不靠记忆**）

| # | 复核项 | 机器读数 | 结论 |
|---|---|---|---|
| 1 | 那两个函数还在被调用吗 | `runner.py:1310-1315` `_register_builtin_criteria()` 显式注册 `C_COST` / `C_COST_RATIO`，且刻意**不用** `PlaceholderEvaluator` | **活函数**，不是死代码 ⇒ 动刀位置正确 |
| 2 | `cost_metrics` 有没有真数据 | 本机 / CI 均**空**（CI 每次起新 PG） | **没数据是正常的** ⇒ 正确行为是「`BLOCKED` + 真实理由 + `value=null`」，**不是 0** |
| 3 | `--cost-records` 期望什么结构 | `eval_acceptance.py:176-185`：JSON **数组**，元素需 `doc_id` / `token_usage_total`，可选 `outcome` / `sequence` | **先读格式再写导出器**（顺序没反） |

**§0.5 开工自检**：`uv run python scripts/check_startup_readiness.py --self-test`
⇒ 用例 7 条（正向 4 / 反向 3）**全过**，退出码 0。

---

## 2. V4-a：两个 evaluator 出数化

### 2.1 改了什么

| 文件 | 改动 |
|---|---|
| `backend/app/services/cost_metrics.py` | 新增 `aggregate_stage()`（**按 stage 聚合的读侧唯一入口**）+ `to_cost_records()`（日聚合 → 逐文档摊平） |
| `backend/app/evaluation/metrics.py` | 新增 `UNIT_COST_RATIO = "ratio"`（C3-b 无量纲，别再借用 `token/doc`） |
| `backend/app/evaluation/runner.py` | 新增 `_cost_blocked()` / `_cost_reading()` / `_cost_window()`；`eval_single_doc_cost` / `eval_incremental_cost_ratio` 由**硬 `BLOCKED`** 改为**三态**；`upgrade_todo()` 文案订正 |

### 2.2 三态（这是本批的核心形状）

| 形态 | 行为 |
|---|---|
| **offline** | **不读库**（offline 不产出判据数字是既有铁律）⇒ `BLOCKED` + 真实缺口 |
| **live + 有样本行** | **出数**，按阈值判 `PASS / FAIL` / `PASS(provisional)` |
| **live + 无样本行** | 仍 `BLOCKED`，理由写「**没跑过**」而不是「**缺落点**」 |

**为什么只取 `stage='extraction'`**：C3-a 的口径是「单文档**抽取**成本」。问答那一行是
检索级开销，混进来会让分子（抽取 token）与分母（抽取过的文档）不是同一个过程——
混口径的数比没有数更糟，它看起来像一个正常的成本。

### 2.3 措辞纪律（**本批的立批原因就在这**）

旧 `blocked_by` 写的是「缺 M2 抽取侧 token 落点」/「`incremental_cost` /
`full_rebuild_cost` **无写入方**」。这两个落点分别在 **P6-V2 / P6-V3 就落地了**，
但**没有任何东西通知过 runner** ⇒ 机器继续对全世界宣布"还差一整段实现"。
新文案一律写成「**有落点，但还没跑过**」。

⇒ **J1 由此变成可机检的断言**：`STALE_COST_PHRASES = ("缺 M2 抽取侧", "无写入方", "P5-M6")`
不得出现在任何 C3 的 `blocked_by` 里。

---

## 3. V4-b：取样器（闭掉死循环）

新增 `backend/scripts/export_cost_records.py`：从 `cost_metrics` 导出
`--calibrate` 能吃的 JSON；同时把 `eval_acceptance.py:167-173` 那条**已过期**的提示
（「token 只进日志、未落库」）换成指向取样器的可执行命令。

**⚠️ 有损摊平，不掩饰**：`cost_metrics` 行粒度是「一天 × 一个 stage」，
**表里没有逐文档 token 明细**（要明细 = 新表 + 迁移 + ADR-0004 登记，属另批）
⇒ 每条记录的 token = **当日均值** ⇒ 喂进 `--calibrate` 后 **P50 == P90 == 均值**，
建议值只是**量级参考**，不是分布上界。这一点写在脚本 docstring、运行时输出、
以及测试断言（`assert "P50 / P90（token/文档）: 20000 / 20000"`）**三处**。

---

## 4. 实测读数（全是本机跑出来的）

### 4.1 ¥0 真读探针（**注入样本，不是真抽取**）

向 `cost_metrics` 注入 1 行 `stage='extraction'`
（60 000 token / 3 份文档 / `incremental_cost=25` / `full_rebuild_cost=100`），
跑 `eval_acceptance.py --live --criteria c3_a_single_doc_cost,c3_b_incremental_cost_ratio`：

```
[measured_provisional] c3_a_single_doc_cost         value=20000.0000  unit=token/doc  verdict=PASS(provisional)
[measured_provisional] c3_b_incremental_cost_ratio  value=0.2500      unit=ratio      verdict=PASS
```

⇒ 端到端（RLS 会话 → `aggregate_stage` → 判据判定）**真的通了**，且**零 LLM 花费**。
探针行已当场删除（`cleaned rows= 1`），报告产物未入库（`reports/` 已 gitignore）。

⚠️ **这两个数不是 V4-c 的真值** ——分子分母是手写注入的。它证明的是
「读口会出数」，**不是**「系统真的花 20 000 token 抽一篇」。

### 4.2 取样器 + 校准闭环（J5，真跑）

```
uv run python scripts/export_cost_records.py --out ...   ⇒ 已写出 3 条记录 / 1 行 / 1 天 / 累计 60000 token
uv run python scripts/eval_acceptance.py --calibrate --cost-records ...
  文档数（去重后）      : 3
  P50 / P90（token/文档）: 20000 / 20000
  建议 ceiling（P90×1.2）: 24000
  实测均值 vs 当前阈值  : 20000 vs 32000 ⇒ PASS(provisional)
```

`config.py` / `.env.example` **逐字未变**（既有 `test_calibrate_never_touches_config`
+ 本批新增断言双重覆盖）。

### 4.3 五项门禁

| 门禁 | 读数 |
|---|---|
| `ruff check` / `ruff format --check`（6 个改动文件） | All checks passed / already formatted |
| `pytest tests -q`（全量） | **1247 passed, 43 skipped, 0 failed** —— 基线 1236 / 43 ⇒ **+11，不降** |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| `check_startup_readiness.py --self-test` | 7 条全过，退出码 0 |
| `check_session_drift.py` | S1 读到 **6 条边界**；S2 4 文件 / 339 行；S3~S5 未触发 |

### 4.4 CI（**R-10 终裁**）

```
run 38145467348 @ c89c4eb —— 全绿
  前端（lint + gen:api）        success
  后端（ruff + pytest）         success
  契约校验（前后端漂移门禁）     success
  流水线汇总                    success
```

⚠️ **本批开工时 CI 已经是红的**，且红在**本批之前**：

- `38143457592`（`e77b2ed` 立批提交，**只有 docs**）与
  `38145365111`（`b392423`）两次都红在同一处 ——
  `tests/test_license_guardrails.py:76` 未格式化 ⇒ **Ruff 格式检查** exit 1，
  后端 job 在 **pytest 之前**就挂了 ⇒ 本批改动**一步都没被验到**。
- 根因提交：`47632be`（P6-Z Z-b/Z-c，**人工提交**）漏跑 `ruff format`。
- 处置（`c89c4eb`，**单独一个 `style` 提交，不与本批混在一起**）：跑项目自带的
  `ruff format` 修那一行，**语义零改动**；该文件 8 条用例本地全过；
  修完 `ruff format --check .` ⇒ 292 files already formatted。

**这是本批唯一一件「顺便做的」事**，它不属于 P6-V4 的任何一条需求，
只是为了让 R-10 的终裁门禁真正跑到本批改动上——单独提交、单独说明理由。

---

## 5. 本批踩到 / 避开的坑（**留给下一批**）

1. **offline 绝不能读库**（本批新踩，差点踩实）：本机测试库是**持久库**
   （P6-V2 / P6-V3 都记过），一旦 offline 去读 `cost_metrics`，真图写入的成本行会让
   offline 报告**产出判据数字** ⇒ `test_offline_yields_no_criterion_numbers` 当场红，
   且报告不再幂等。⇒ 判据的读库**只在 live 分支**，offline 走 `BLOCKED`。
2. **既有断言 76-78 / 125-126 没崩，也没改**（V5 达成）：它们锚的是
   `"M2"` / `"TBD-7"` / `"增量重算"` 三个**词**，而真实缺口的措辞从
   「缺落点」变成「**没跑过**」之后，这三个词**仍然在**（缺的还是 M2 抽取**这一跑**、
   还是增量重算**这一跑**）⇒ **没有触发 ② 停机条件**，未改任何既有断言。
3. **`check_startup_readiness.py` 在本机 PowerShell 下会因 GBK 崩**（打印 `⇒`）：
   跑它要带 `$env:PYTHONIOENCODING="utf-8"`。**这是环境问题，不是护栏问题**；
   `--self-test` 在 CI 里是门禁且全过。
4. **CI 红不等于你改错了**（本批开工时就是红的）：`ruff format` 挂在**别人的文件**上时，
   后端 job **在 pytest 之前**就挂 ⇒ 日志里看不到任何测试失败，很容易被误读成
   "我的改动把测试搞红了"。⇒ **先看挂在哪一步**，再看挂的是谁的文件。
   另：本地只跑改动文件的 `ruff format --check` **查不出这类红**——门禁跑的是
   `ruff format --check .`（全量），收口前要跑一次全量。

---

## 6. 残留风险（**不许被读成「C3 已达标」**）

1. **V4-c 未做**（D1 未勾 ⇒ 未批准）：C3-a / C3-b 的**真值**仍是 `BLOCKED`。
   本批给的是「出数**能力**」，不是「出数**结果**」。
2. **§4.1 的 20000 / 0.25 是注入样本的算术结果**，不得登记为实测真值。
3. **日聚合摊平 ⇒ 分位数退化**：取样器给出的 `24000` 是量级参考，不是校准结论。
4. **TBD-7 采纳哪个阈值由用户裁决** —— 本批只给数据与命令，不代裁决。
5. 仪表盘**无 `stage` 切片**（P6-V3 §6.3 遗留）⇒ 区间视图仍是混合口径，本批未动。
6. 增量**失败**那次已写出的图操作记不到（`_fail` 拿不到计数）⇒ 分子偏保守。
7. ~~矩阵未同步~~ **已同步**（本批末追加的**架构师侧**提交）：
   `docs/acceptance-traceability-matrix.md` **四处**过期文案已订正 ——
   L55（M6 的「❌ 仍未做」清单**四项其实全已落地**，而同格后段自己就记着）、
   L109（M2-7「无成本表」）、L205（C3-a「值待 P5-M6」）、L206（C3-b「待 P5-M6
   增量重算」）。**订正只改清单 / 措辞，不重估达成度**：C3 真值仍如实写 `BLOCKED`，
   未核实项保持原状。
8. **同类过期在别处还有，本批未动**（跨文档扩散 = 蔓延，且部分分项未核实）：
   `docs/prd-mvp-takeup.md:46`（「仍缺 … C3 成本聚合 / 事件与成本表未排期」）、
   `docs/delivery-requirements-and-guardrails.md:115`（DR-D2「剩余四块」的 ②③）、
   `:123`（DR-D10「C3-a·C3-b（BLOCKED，**P5-M6**）」）⇒ **P8 对账前要一并核**。

---

## 7. 下一批指针

见 [`new-session-prompt.md`](./new-session-prompt.md)（按本批**实际结果**写，未照抄上一版）。
