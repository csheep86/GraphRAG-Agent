# P6-R · 任务清单（拒答判据读数稳定性 → 裁决 O1 / O2 / O3）

> **边界**：[`proposal.md`](./proposal.md)（Non-goals **10 条**，改一条都要先回来登记理由）
> **模式**：无人值守；只在四类升级边界停下找用户。**CI 才是终裁（R-10）**。
> **计划真源**：`docs/delivery-plan.md` §9.2 队列第 1 项（「谁来」= **AI + 用户裁决**）

## T1 · 三件套 + 开工自检

- [x] `changes/P6-R/proposal.md` + `tasks.md`（**先落边界再动代码**）
- [x] `check_startup_readiness.py` = **`[OK]` 17 / `[~~]` 0 / `[--]` 0**
- [x] `check_seams.py` = ERROR 0 / WARN 0 / **OK 12**
- [x] `export_openapi.py --check` = **零 diff**
- [x] `gh run list --limit 1` ⇒ 起点绿（run `37886225303`）
- [x] 容器：Neo4j / PG 均 Up
- [x] 机读事实：`temperature` 在 `backend/` 内**零匹配**；`build_chat_model()` 调用方恰 3 处
      （`agents.py:192` / `ontology.py:448` / `langextract.py:388`）

## T2 · ≥3 趟 `--live` 复现抖动（**唯一有花费的一步**）

- [x] 登记花销（proposal §2 **D7**）：改动前 3 + 改动后 3 = 6 趟 × 40 题；每趟对应一个此前拿不到的结论
- [x] 起后端（`uvicorn 127.0.0.1:8002`）
- [x] 改动前 3 趟（默认采样）：`050537Z` / `050659Z` / `050818Z` ⇒ 误伤 **0 / 0 / 0**
      （本批**未复现**翻转；合并 P6-Q ⇒ 默认采样累计 6 趟 1 次翻转，观测率 ≈ 1/6）
- [x] 每趟记录：`asked=40 / answered=36 / refused=4`、`missed_refusals=[]`、C2-c 两档 **1.00 / 0.9**

## T3 · ¥0 探针复核（**确认抖动不是检索层漂移**）

- [x] `--index 28 --key 自动补卡,月度补卡次数` ⇒ **L5+**（gold 2 条进注入 32 条，桶内第 1/2，词面分 0.500）
- [x] `--index 8` ⇒ **L5+**（gold 1 条进注入 32 条，桶内第 1/4，词面分 0.611）
- [x] 两条均与 P6-Q 逐位一致 ⇒ **检索层未漂**，无需停下

## T4 · O1 / O2 / O3 裁决落地 ⚠️ **已由用户裁决 = O1**

> `delivery-plan.md` §9.3 第 3 条明列此项「AI 不得代做」⇒ 已带数据提请裁决。

- [x] 用户裁定 **O1**（全局钉 `temperature=0`）
- [x] 落地：`app/services/providers/llm.py` 的 `build_chat_model()` 加 `temperature=0` + docstring「采样确定性」
- [x] D2：**做成常量**（不加 `settings.llm_temperature`）⇒ 不触发 S3；`check_seams` 仍 OK 12
- [x] 落地后 **≥3 趟一致为 0**：`053456Z` / `053605Z` / `053714Z`
- [x] 反向护栏：`missed_refusals` 三趟恒 `[]`（4 道库外题仍拒答）

## T5 · 连带面实测（**选 O1 必做**）

- [x] 新增 `scripts/probe_p6r_extraction_drift.py`（固定文本、**图外**跑、不写库）
- [x] **before**（默认采样）×2：14 实体/7 关系 vs **19 实体/8 关系** ⇒ `identical_across_runs=false`
      ⇒ **默认采样下入图产物本身不可复现**（本批最有价值的新事实）
- [x] **after**（T=0）×2：**12 实体/9 关系逐位一致** ⇒ `identical_across_runs=true`
- [x] C2-a / C2-b 复跑（`--gold v2 --gate`）：**20/20（下界 0.8609）** 与 **0/20（上界 0.1391）**，
      门禁 `EXIT=0`，与 P6-A 基线**逐位一致**
- [x] 机械论证：`ingest_affiliation_sources.py` **确定性、不经 LLM** ⇒ 该 gold 链不经过接缝 3
- [x] 补导 `affiliation-demo-v2`（本机图缺失所致；`--purge` 按 `kg_version` 作用域 ⇒ 不动 attendance 图）

## T6 · 口径回登 + 收尾

- [x] `dev-doc-status.md:385` **A6 行**追加 P6-R 裁决与落地（PASS 附「≥3 趟一致」证据）
- [x] `acceptance-traceability-matrix.md` **C2-c 行**同步（误伤判据转 PASS + 仍不进 CI）
- [x] `integration-log.md`（含「收尾三问」自答 + Non-goals 核销 + 决策登记 + 下一批指针）
- [x] 全部门禁：ruff（check / format）/ pytest 有图口径 **1146 passed / 3 skipped / 0 failed** /
      接缝 OK 12 / 契约零 diff / readiness 17-0-0 / `check_session_drift`（S1 读到 10 条边界）
- [x] Conventional Commits **分段提交**（4 段：llm.py / 探针 / 口径回登 / 批次产物）→ 推送
- [x] CI run **37890415841**：四 job 全 ✓，`--exit-status` = **0**，pytest **1144 passed / 5 skipped**（零增零回退）
- [x] 下一批提示词 `changes/P6-R/new-session-prompt.md`（**MD 文件，不在聊天里贴**）
