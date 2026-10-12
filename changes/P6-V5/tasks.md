# Tasks: P6-V5 —— C3 真值收口（先清脏数据）+ TBD-7 裁决包

> 配 [`./proposal.md`](./proposal.md)；实测证据回登 `./integration-log.md`。
> **勾选 ≠ 通过**，每条都要有可复核的机器输出。
>
> 🔒 **2026-10-12 第二次会话范围**：D1 = 稍后再定 ⇒ **只做 T1 / T2 / T3（零 LLM 费用）**；
> T4 起**必须等用户在 D1 上点头**才许开工。
> 每个子任务收尾：`cd backend && uv run python scripts/check_session_drift.py`（S1 报无 Non-goals ⇒ 停）。

## 1. 前置（T0）

- [x] 核对起点：HEAD `1c32d7e`（本地 == origin/main）、工作区干净
      ⚠️ `backend/data/eval/judging/judge-progress.json` 为**未跟踪新产物** —— **待定性**（清 / 留）
- [x] `cd backend && uv run python scripts/check_startup_readiness.py` —— 🟢15 / 🔵2 / 🟠0 / 🟡0；地雷 0 项
- [x] 记录本机 / CI 两套 pytest 口径（本机 1251 / 43；CI run `38201283243` = 1287 / 7），**同侧比**

## 2. V5-a 隔离清场（**T1，本会话第一件事**）

- [x] 定位写脏 `cost_metrics` 的**具体用例** = **`tests/test_kg_build_executor.py`**
      （实测：单跑该文件 ⇒ `full_rebuild_cost` 4.0 → 8.0；链 = `registry.py:837`
      → `record_full_rebuild_cost`；两条成功构建用例 × (1 实体 + 1 关系) = 4.0）
- [x] 判定写法：脏行在**测试库 `graphrag_test`**（不是开发库 `graphrag`），
      夹具收尾漏删 `CostMetric`
- [x] 清空已有脏行（`DELETE ... WHERE org_id = DEFAULT_ORG` ⇒ `DELETED = 1`）
- [x] 修法：`seed_document` 夹具**快照差分**（进入前 / 收尾各拍一次 id），**按新增 id 精确删**
- [x] 复跑该文件 ⇒ `AFTER_FIX_ROWS = 0`；**全量 pytest 后 `POST_FULL_PYTEST_ROWS = 0`**
- [x] 反向：未放宽任何断言（Non-goal 6 / R-10 未越线）

## 3. V5-b 基线复核（**T2 / T3**）

- [x] `uv run ruff check .` + `uv run ruff format --check .`（**全量**）—— 绿 / 294 files formatted
- [x] `uv run python scripts/check_seams.py` —— OK 12 / ERROR 0 / WARN 0
- [x] `check_startup_readiness.py --self-test` —— 7 条全过
- [x] `pytest tests -q` 全量 —— **1251 passed / 43 skipped**（177.19s，与基线逐字相同，不降）
- [x] 锚点五文件（含 `test_eval_acceptance_cli` / `test_eval_cost_criteria`）—— **44 passed**
- [x] `check_session_drift` —— S1 读到 7 条边界；S2 = 1 文件 / +28 行；S3~S5 未触发

## 4. V5-c 真机实测（**T4，D1 已于 2026-10-12 批准 ⇒ 已做完**）

- [x] **¥0 估上限**（送批前先给数字）：锚点 `langextract.py:22` ¥6.55 / 124 chunk
      ⇒ ¥0.053/chunk；候选文档 1019 字 ⇒ 2 chunk ⇒ **上限 ≈ ¥0.11**
- [x] 起后端 `127.0.0.1:8002`（= 评测默认 `EVAL_BASE_URL`）；`/health` = ok
- [x] `POST /documents/upload`（DOCX）⇒ `document.parse` 完成；**因本仓库无跨阶段投递**
      （`registry.py:17-19`）⇒ 自行续投 `document.extract` / `kg.build`
- [x] `kg.build` **不带 `kg_version_id`** ⇒ `create_pending` ⇒ `fresh_build=True`
      ⇒ 分母 `full_rebuild_cost = 33.0`
- [x] `POST /ontology/rename` ⇒ `rebuild_incrementally` ⇒ 分子 `incremental_cost = 9.0`
- [x] `--live` 官方读数：**C3-a = 7574.0000 token/doc（PASS provisional）／
      C3-b = 0.2727（PASS）**；报告 `eval-live-20261012T065005Z.json`
- [x] `export_cost_records.py` 导出 → `--calibrate`：建议 ceiling **9100**（P90×1.2）
      —— ⚠️ **不采纳**：n=1 且文档极小 ⇒ **TBD-7 维持 provisional，交 D2（人裁决）**
- [ ] ❌ **D2 未由 AI 代填**：32000 阈值**一字未动**（`config.py` / `.env.example` 未改）

## 5. 裁决结论（**2026-10-12，用户授权 AI 提建议后定案**）

- [x] **批次命名**：保留 `changes/P6-V5/` 作为批次目录（承接 V4 遗留切片 **V4-c**；
      P6-V6 是**计划外插队**）；提示词仍留在它被写下的 `changes/P6-V6/`（顶部已加重定向）
- [x] **`backend/data/eval/judging/judge-progress.json`：保留，不删、不 ignore**
      —— 它是 `scripts/judge_interactive.py` 的**续判状态**（人工已判 `G-01` / `G-02`），
      **删它 = 销毁人工判分进度**
- [x] **补会话级守卫**：`tests/conftest.py::cost_metrics_residue_guard`
      （session 级 autouse；**反向验证**：播种脏行 ⇒ 实测会红；清掉 ⇒ 全量 1251/43 不变）
- [x] **守卫首战立功**：CI run `38209335460` 后端 job **failure**，正是它拦下了
      `incremental_cost=60.0` 的残留 ⇒ 顺藤在本地开真图开关复跑，定位到**另三处**同源 writers
      （`test_kg_incremental_rebuild.py` 15.0 / `test_ontology_correction_actions.py` 18.0 /
      `test_version_chain_readers.py` 27.0），按同一套「夹具快照差分」修法收干净。
- [x] **教训登记**：本机默认口径（43 skipped）看不见真图用例 ⇒
      **本机全量绿 ≠ CI 绿**；动到真图 / 真 PG 写入的改动，收尾必须再按 CI 口径跑一次

## 6. V5-d 收口（**依赖 T4**）

- [ ] 架构师**单独提交**：回改 `docs/acceptance-traceability-matrix.md:205` / `:206`
- [ ] 回登 `./integration-log.md`（实测输出、run id、偏差）
- [ ] 下一批提示词落成 `changes/P6-V5/new-session-prompt.md`（**MD 文件，不贴全文进聊天**）

## 7. 不许做

- [ ] ❌ 起任何真 LLM 调用（D1 未批）
- [ ] ❌ 把注入探针值（`20000.0` / `0.25`）或**测试残留行**当真值登记
- [ ] ❌ 把 `--calibrate` 建议值写进 `config.py` 后宣称"已校准"
- [ ] ❌ 替用户拍 TBD-7（"先写上再复核"也不行）
