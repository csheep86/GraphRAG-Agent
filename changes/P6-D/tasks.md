# P6-D · 任务清单（L2 端到端）

> 对应 [`proposal.md`](./proposal.md)；**先定边界再实现**，边界已在 proposal §3 Non-goals 冻结。
> 第一步 = 文档（本文件 + proposal）**已完成**；第二步 = T1–T6。

## 第一步：定边界

- [x] **T0.1** 找出仓库里已有的 L1/L2 口径 ⇒ **采纳** `gold-affiliation-v2.json::source.corpus_layer_note`
      （判据 = 语料**是否经 M2 抽取**），并登记「ADR-0007 的 L0/L1/L2 是定制分档，不是同一套」
- [x] **T0.2** 产出逐跳链路表 H1–H6（输入 / 输出 / 可机判判据 / 当前是否打通 + 证据路径）
- [x] **T0.3** 给出 L1/L2 分界的**代码级证据**（`ingest_affiliation_sources.py` 绕过 M2
      vs `ingest_attendance_policies.py` 走全链）
- [x] **T0.4** 登记归因陷阱：`runner.py::QSET_CORPUS_LAYER` 目前是**写死常量** ⇒ 进 T4

## 第二步：实现（只做判为「未打通」且本批能做完的跳）

- [ ] **T1** 诊断 H3 根因：`bridge_governed_by()` 为何 0 条
      —— 逐项排除① `WORK_TIME_SYSTEM` / `POLICY_CLAUSE` 节点是否存在 ② 条款正文里是否真出现工时制名称
      ③ `relations.json` artifact 是否被读到。**要根因，不要猜测**；结果写进集成日志
- [ ] **T2** 若根因属「脚本级 / 数据级」⇒ 修，验收：跨源 `GOVERNED_BY` **> 0** 且**重跑幂等**
      （已知陷阱：MERGE 追加语义下重复跑会把边再追加一遍 ⇒ 写回前须去重）
      ⚠️ **不修**落在 `langextract.py`（M2 抽取）里的根因 ⇒ 那是另一条线，走 T6
- [ ] **T3** 打通 H5：拿到真机 `ready` `kg_version` ⇒ `POST /api/v1/agent/query` 返回 200 + citations；
      **记录跑了几遍、几遍成功**
- [ ] **T4** 归因随实测反推：`corpus_layer` 不再写死常量；补反向验证
      （把 L2 判成 L1、或把 L1 判成 L2 ⇒ 必须判红）
- [ ] **T5** 一条可复现的端到端冒烟：逐跳打印「通 / 不通」+ 最终 `corpus_layer`
- [ ] **T6** 若 H3–H5 修不好 ⇒ **如实登记 UNKNOWN + 卡在第几跳 + 下一步归谁**，
      并说明 C1 与拒答类判据因此仍不可测（**不许**用 L1 结论顶替）

## 收尾门禁（每步都要跑）

- [ ] `uv run pytest -q` —— passed 数**不减**（基线 **950**）
- [ ] `uv run ruff check .` + `uv run ruff format --check .`
- [ ] `uv run python scripts/check_seams.py`（ERROR 0 / WARN 0 / OK 10）
- [ ] `uv run python scripts/export_openapi.py --check`（契约零 diff）
- [ ] `uv run python scripts/check_session_drift.py` —— S1–S5，**S1 必须读到本文的 Non-goals**
- [ ] 集成日志：实测数字 + 收尾三问（有没有顺便做的 / 有没有绕路 / 结论是真跑的还是读代码的）
