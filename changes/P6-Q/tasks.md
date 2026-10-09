# P6-Q · 任务清单（拒答误伤：FAIL → PASS）

> **边界**：[`proposal.md`](./proposal.md)（Non-goals **10 条**，改一条都要先回来登记理由）
> **模式**：无人值守；只在四类升级边界停下找用户。**CI 才是终裁（R-10）**。

## T1 · 三件套 + 开工自检

- [x] `changes/P6-Q/proposal.md` + `tasks.md`（**先落边界再动代码**）
- [x] `check_startup_readiness.py` = **`[OK]` 17 / `[~~]` 0 / `[--]` 0**（与基线一致）
- [x] `check_seams.py` = ERROR 0 / WARN 0 / **OK 12**
- [x] `export_openapi.py --check` = **零 diff**
- [x] `gh run list --limit 1` ⇒ 起点绿（run `37873512778`）
- [x] 容器：Neo4j / PG 均 Up；`documents` 6 条 completed；`kg_versions` = `attendance-demo-v1 / ready`

## T2 · ¥0 根因探针（**不先看结论再看 Key**）

- [x] 新增 `scripts/probe_p6q_refusal_rootcause.py`：gold **机械确定**（`expected_points` → ≥4 字 CJK 串 ⇒ 文本 `CONTAINS` 全命中），
      逐级量 L1（版本内有无）/ L2（图候选）/ L3（∪ 字面量）/ L4（进 32 条）/ L5+（需 live）
- [x] Q8 实测：**L5+**（gold 存在、进候选、进 32 条，桶内第 1/4，词面分 0.611）
- [x] `ruff check` / `ruff format` 通过（新脚本）

## T3 · 一次 live 实测（**唯一有花费的一步**，共享缓存只跑一趟）

- [x] 登记花销（proposal §2 **D7**）：40 题 × 1 趟，判据两调一次链路，不重复跑
- [x] 起后端（`uvicorn 127.0.0.1:8002`）+ dev license 在位（PG `licenses` 1 行）
- [x] `eval_acceptance.py --live --criteria refusal_false_refusal,c2_c_citation_coverage`
      ⇒ 出 `false_refusals` / `missed_refusals` / C2-c **两档**（含拒答档 + 排除拒答档）
- [x] 报告落 `backend/reports/eval/`（已 gitignore，不入库），读数回登本文件与 §T5 文档

## T4 · 确定性护栏（**先查是否已存在，存在就不重复造**）

- [x] 复核：`tests/test_lexical_recall.py::test_question_pulls_in_chunk_outside_graph_candidates`
      **已**用注入的假 session 覆盖了「问句词面把图候选之外的 gold 拉进注入」这一环（P6-N 落）
- [x] **本批不新增重复用例**：演示语料（213 chunk）**无法在 CI 物化**（CI 只导入 `affiliation-demo-v2`，
      见 `.github/workflows/ci.yml:206-228`）⇒ 任何"针对 Q8 / Q28 的 CI 用例"都会 **skip**
      ⇒ 按 **R-9 恒绿即失效**，宁可不做。理由写入 `integration-log.md` §6 **D5**
- [x] 既有断言**一条未改**（`ruff` / `pytest` 两种口径均复跑比对）

## T5 · 文档更正（**只改"过期口径"，不改裁决**）

- [x] `dev-doc-status.md:385` **A6 行**：「含拒答档从未输出，P6 第一步补」⇒ 改为**已兑现**（`runner.py:347-351`）
- [x] A6 行**误伤状态**由 FAIL 按实测更新（PASS ⇒ 贴证据；否则保留 FAIL 并写明）
- [x] 如需同步：`delivery-plan.md` / release notes 的同一处口径

## T6 · 收尾

- [x] 全部门禁：ruff / pytest（有图 + 无图两个口径）/ 接缝 / 契约 / readiness
- [x] `check_session_drift.py`（S1 读到本批边界）
- [x] `integration-log.md`（含"收尾三问"自答 + Non-goals 核销 + 下一批指针）
- [x] 下一批提示词 `changes/P6-Q/new-session-prompt.md`（**MD 文件，不在聊天里贴**）
- [x] Conventional Commits **分段提交**（后端 B / 架构师文档）→ 推送 → `gh run watch --exit-status` = 0
