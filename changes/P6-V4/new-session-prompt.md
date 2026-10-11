# 新会话开场提示词 · P6-V4（**让 C3-a / C3-b 真正出数**）

> 🔒 **执行模式：无人值守**（`unattended-sprint-execution` 技能；默认采纳本文档的建议项，
> **只有 4 类情况停下找用户**：① 前置不成立 ② 要动**已裁决**的 rubric / 判据口径（**先缩范围再报告**）
> ③ 边界冲突（要碰 Non-goal）④ CI 红了且复核两遍仍红）。
> ⚠️ **外加一条本批专属**：**V4-c（真 LLM 实测）不经批准不许起** —— 会产生费用。
>
> 📌 **计划真源**：[`changes/P6-V4/proposal.md`](./proposal.md)（本立批）
> —— 承接 plan §9.2 序 5d（P6-V3）之后的 C3 线。
>
> 📦 **本文件自包含**：批次定位、上游状态、判据、坑都在本文里。
>
> ⏳ **本文件写于 2026-10-11 晚**（当时 V4 尚未开工）。开工第一步是**复核 §2 的读数是否仍然成立**
> —— 别拿它当史实：`runner.py` 那两条 `blocked_by` 就是因为没人复核才过期到今天的。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 `runner.py` 里两个**写死 `BLOCKED`** 的评价函数，换成**真读 `cost_metrics`** 的实现 ——
消除「P6-V3 说已经能出数、机器却恒 `BLOCKED`」的脱节。

**为什么排在队列最前**（2026-10-11 用户裁决：**目标是"软件可上线"，不是"交付"**）：
C1~C3 / 多跳 / 拒答五条准入线里，**只有 C3 没有真值**；而挡住它的**不是缺功能** ——
是**一个没被替换掉的占位实现**。 ⇒ 这是最短路径上的"软件补缺"，不是交付动作。

---

## 0.5 开工前必读（五份）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | [`proposal.md`](./proposal.md)（本批） | 边界（Non-goals 6 条）与出口判据 J1~J6 |
| 2 | `backend/app/evaluation/runner.py:806-894` | `resolve_cost_ceiling()` + 那**两个待改造的函数**（就在这里动刀） |
| 3 | `backend/app/services/cost_metrics.py`（全文件） | 四个 `record_*` 写入方已就位 —— **出数要读的就是它们写的表** |
| 4 | [`changes/P6-V3/integration-log.md`](../P6-V3/integration-log.md) §5 / §6 | §5 是本批要躲的三个坑；§6 残留风险第 1 条就是本批的由来 |
| 5 | `backend/scripts/eval_acceptance.py:150-214` | `--calibrate` 的实现（只输出建议、**绝不写 config**），本批 V4-b 要和它对接 |

---

## 1. 执行模式与纪律

- **角色隔离**：AI 段默认只**后端开发 B**（只改 `backend/`）；
  改 `specs/` / `contracts/` / `docs/` / plan ⇒ 归**架构师**段（**单独提交**）。
- **分支**：沿用 P4~P6-U —— **`main` 直推**，不另开分支。
- **提交**：按**后端 / 架构师**分段 Conventional Commits，跨侧**不得**混在一个提交。
- **推送**：⚠️ **本仓库 GitHub 推送通道不稳**（晚间多次 `443` 超时）。失败 ⇒ **重试一次**，
  仍失败就**把完整命令交给用户**，**不许**改 remote / 绕道。
- **终裁**：以 CI 为终裁（R-10）；CI 红了**先看是不是批次摊太大**，**不许先改测试让它绿**。
- **回登纪律**（P5-B §5.3）：**不要为"多记一个 run id"而提交** —— 回登 ⇒ 新 commit ⇒ 新 run ⇒ 无限递归。
- **开工第一步**：`uv run python scripts/check_startup_readiness.py`（含新增的 🔵 档位；
  `--self-test` 必须全过，它在 CI 里是门禁）。

---

## 2. 必须先复核的三件事（**照 P6-V3 §5 的教训**）

1. **`runner.py` 那两个函数是不是真的还在被调用** —— 别改到一个没人用的死函数上
   （核实谁调用 `eval_single_doc_cost` / `eval_incremental_cost_ratio`）。
2. **`cost_metrics` 表现在有没有真数据**（本地 / CI 通常是空的）
   ⇒ **没数据是正常的**，此时正确的行为是「`BLOCKED` + 真实理由 + `value=null`」，**不是** `0`。
3. **`--calibrate` 的 `--cost-records` 期望什么 JSON 结构** —— 先读它吃的格式，再去写导出器（V4-b），
   顺序反了会产出没人能用的文件。

---

## 3. P6-V3 留给本批的三个坑（**别再踩**）

1. **conftest 有一条 `autouse` 桩会把 `get_active` 顶掉**：
   `tests/conftest.py::pg_active_kg_version` 恒返回 `KgVersionRecord(version="v-test", ...)`。
   谁要**真读 PG 的 active 版本**，必须显式请求 `real_pg_get_active` fixture 撤桩
   —— 否则会以「基线版本不一致」的形态红掉，**看起来像增量失败，实为夹具问题**。
2. **`test_cost_metrics.py::test_dashboard_endpoint_returns_real_rows` 有顺序耦合**：
   真图用例会**真的写**成本列 ⇒ 它读到脏值。
   历史修法是**改它的隔离**（先清本 org 当日行），**不是**改判据让它绿。
3. **本机测试库是持久库**：CI 每次起新 PG，本机不会 ⇒ 别指望 `create_all` 补列。

---

## 4. 验证清单（**跑完才能收口**）

| # | 命令 / 判据 | 期望 |
|---|---|---|
| V1 | `uv run ruff check` + `ruff format --check`（改动文件） | 绿 |
| V2 | `uv run python scripts/check_startup_readiness.py --self-test` | 7 条全过，退出码 0 |
| V3 | `uv run pytest tests -q`（全量） | **不降**（基线 1236 passed / 43 skipped / 0 failed） |
| V4 | `uv run python scripts/check_seams.py` | OK 12 / ERROR 0 / WARN 0 |
| V5 | `uv run pytest tests/test_eval_acceptance_cli.py -q` | 既有断言（第 76-78 行的 `BLOCKED` 形态）**不得崩** —— 若它断言的正是过期文案，属②边界冲突 ⇒ 停下报告，**不许顺手改断言** |

---

## 5. 停机条件（碰到就找用户）

1. **要不要起 V4-c 真 LLM 实测**（会产生费用）；
2. 若发现判据必须改才能出数 ⇒ 属 Non-goal 第 6 条，停下；
3. 若要动 C3-b 的量纲裁决（2026-10-10 拍板的 A 组「图元素个数」）⇒ 属②裁决，停下；
4. 实测值出来后，**TBD-7 采纳哪个阈值**由用户决定 —— 本批只给数据，**不代裁决**。
