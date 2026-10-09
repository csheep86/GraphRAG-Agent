# P6-S · 任务清单（A1 向量基线 + 双侧出卷 ⇒ 让 C1 分母可判）

> **边界**：[`proposal.md`](./proposal.md)（Non-goals **10 条**，改一条都要先回来登记理由）
> **模式**：无人值守；只在四类升级边界停下找用户。**CI 才是终裁（R-10）**。
> **计划真源**：`docs/delivery-plan.md` §9.2 队列第 2 项

## T1 · 边界三件套 + 开工自检

- [x] `changes/P6-S/proposal.md` + `tasks.md`（**先落边界再动代码**）
- [x] `check_startup_readiness.py` = **`[OK]` 17 / `[~~]` 0 / `[--]` 0**
- [x] `check_seams.py` = ERROR 0 / WARN 0 / **OK 12**
- [x] `export_openapi.py --check` = **零 diff**
- [x] `gh run list --limit 1` ⇒ 起点绿：run **`37890683002`**（commit `101773e7`）
- [x] 容器：Neo4j / PG 均 Up
- [x] `tests/test_eval_baseline_a1.py` = **20 passed**

## T2 · 查实 D1 + 环境复位（**第一趟 live 就在这里花掉**）

- [x] 发现 8002 上的后端是 **13:33** 起的**旧进程**（早于 P6-R 的 T=0 提交 13:46）⇒ **杀掉重启**
- [x] 发现 8009 未监听 ⇒ 拉起 `scripts/local_embedding_server.py`（本地 `bge-small-zh-v1.5`，冒烟 **dim=512**）
- [x] 跑 `--live --criteria c1_graph_gain` ⇒ 报告 `reports/eval/p6s-c1-01.json`
- [x] `blocked_by` 原文 = `A3：图侧没有一题被人工判分（用 --judgements 提供）；脚本不自动判分 ⇒ 不判就等于没跑`
- [x] **两侧均已出数**：`awaiting_graph` 40（拒答 **4**，与 P6-R 的 40/36/4 一致）／`awaiting_baseline` 40（拒答 **9**）
- [x] 否证 `dev-doc-status.md` A1 行的「协议零匹配」旧口径（`baseline.py` **494 行**已在 + 基线侧真出数）

## T3 · 重排 `eval_graph_gain`：双侧 spec + 可比性断言提到判分闸门与付费之前

- [x] 顺序改为：**specs + `comparability_error` → 判分闸门 → 付费的基线侧 → 出数**
- [x] 缺判分返回的 UNKNOWN **必带** `graph_spec` / `baseline_spec`（此前完全看不到）
- [x] 不可比 ⇒ **先报不可比**，且**不再**花 40 次 LLM 跑基线侧
- [x] `embedder is None` ⇒ 显式返回「embedding 未配置」（原本靠下游兜底，重排后会踩空指针）
- [x] ⚠️ **出数路径一行未动**：判据值 / 阈值 / 既有 detail 字段 / `comparability_error` 判定逻辑均未改

## T4 · `_load_judgements` 拒绝非布尔值

- [x] `bool(None)` = False ⇒ 半张表把未判题**静默判错**的洞已堵（报错点名题号）
- [x] `bool("false")` = True ⇒ 字符串同型通路一并堵掉
- [x] 只收 `True / False`

## T5 · 导出两侧答卷（**P6-T 的输入物，跟踪入库**）

- [x] 新增 `backend/scripts/export_judging_sheets.py`：读报告 ⇒ 拼题干 + `expected_points` / `secondary_points` / `should_refuse`
- [x] 产物 `backend/data/eval/judging/c1-sheets-20261009T064241Z.json`（**跟踪**，非 gitignore 的 `reports/eval/`）
- [x] **不含任何 `correct` 值**（Non-goal 2；单测递归锁字段名）
- [x] provenance 齐：`_git_hash=101773e7` / `_kg_version` / 两侧 spec ⇒ 「同一批改分」可复核

## T6 · 单测补齐（**只加不放宽**）

- [x] `test_missing_judgement_still_reports_both_specs`（缺判分 ⇒ `value=None` **且** detail 含两侧 spec + 同源三读点）
- [x] `test_incomparable_blocks_before_running_baseline_side`（基线侧 k=8 < 32 ⇒ 先拦且不调用基线侧）
- [x] `test_null_value_is_rejected` / `test_string_value_is_rejected`（判分值必须是真布尔）
- [x] 导出脚本 4 条：题干与锚点齐 / **无 `correct` 字段名** / 缺侧报错 / 越界题号报错
- [x] 本地全量 `pytest`（有图口径）**1154 passed / 3 skipped / 0 failed** = 基线 1146/3 **+ 8 条**

## T7 · 第二趟 live 取证 + 口径回登 + 收尾

- [x] 登记花销后跑第二趟 ⇒ `p6s-c1-02.json`：**池指纹 `e36322bb2d86865f` / 213 条两侧同源**、
      `top_k` **32 = 32**、`generation_model` / `prompt_id` 同源、`graph_context` True vs False ⇒ **可比**，`value` 仍 `None`
- [x] `dev-doc-status.md` **A1 行**追加订正块（R-5：**只追加不重排**）
- [x] `acceptance-traceability-matrix.md` §5.1 **C1 行**同步
- [x] `runner.upgrade_todo()` 的「A1 待裁决」订正为「待两侧人工判分」
- [x] `integration-log.md`（收尾三问自答 + Non-goals 核销 10 条 + 决策登记 D1~D8 + 下一批指针）
- [x] 全部门禁：ruff check/format ✅、pytest 1154/3/0、接缝 OK 12、契约零 diff、readiness 17-0-0、
      `check_session_drift` S1~S5 全 OK（6 文件 / +168 行）
- [x] Conventional Commits **分段提交**（代码 / 测试 / 导出脚本与答卷 / 口径回登 / 批次产物）→ 推送 → CI 绿
