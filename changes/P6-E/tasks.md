# P6-E · 任务清单（Q8 拒答误伤）

> 对应 [`proposal.md`](./proposal.md)；边界已在 §3 Non-goals 冻结。
> 判据：`refusal_false_refusal`（阈值 **0**，当前 FAIL = 1 条 Q8）。
> **顺序铁律：先重测 → 归因 → 才谈修。**

## 第一步：文档

- [x] **T0.1** 写 proposal：判据定义引出原文 + 「先重测」的顺序裁决 + Non-goals 8 条
- [x] **T0.2** 写明三种重测结果（仍误伤 / 自愈 / 冒出新误伤）各自的"怎么算完成"
- [x] **T0.3** 采纳口径：≥3 遍、**取最坏值**、报告写 `runs=3, worst=`

## 第二步：重测（**还没改一行代码就先跑**）

- [ ] **T1** 起后端（真 Neo4j + PG + 真 LLM），跑受控 14 题 **≥3 遍**
      `uv run python scripts/eval_acceptance.py --live --criteria refusal_false_refusal,c2_c_citation_coverage`
      逐遍记录：误伤条数与题号 / 漏拒 / 请求失败 / C2-c 两档（含拒答档、不含拒答档）/ kg_version
- [ ] **T1.1** 判断落在 A / B / C 哪一种（proposal §2 表），**不要先看结论再凑判据**

## 第三步：归因与修复

- [ ] **T2** 归因（**要证据，不猜**）：三选一定位
      —— ① **检索没召回** Q8 相关 chunk（打点看注入的 chunk_id）
      —— ② **拒答判定**分支把它判成"证据不足"
      —— ③ **prompt** 口径问题
      若为 B（自愈）⇒ 归因到 ③ 的哪一跳变化，并回答"下次重建图会不会复发"
- [ ] **T3** 按 T2 定位做**最小修改**（只动那一处），改完重跑 T1
      ⚠️ 不许放宽拒答判定 / 不许改题集 / 不许靠 C2-c 顶替（Non-goals 2–4）
- [ ] **T4** **反向验证**：故意造一个误伤场景 ⇒ 判据必须判红（给出变异 + RED 记录）

## 收尾

- [ ] **T5** 日志里并列「变化前（2026-10-03，旧图）」与「变化后（本批，新图）」，
      **注明两者图 / 语料 / 本体均已变化**，不可直接对照
- [ ] 门禁：`uv run pytest -q`（passed **不减**，基线 **957**）／`ruff check .`／`ruff format --check .`
      ／`scripts/check_seams.py`／`scripts/export_openapi.py --check`／`scripts/check_session_drift.py`（S1–S5）
- [ ] 集成日志：实测数字 + 收尾三问（有没有顺便做的 / 有没有绕路 / 真跑还是读代码）
