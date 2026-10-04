# P3-E 提案 —— **G-25：评测判据（C2-a / C2-b）进 CI 成真门禁**

| 项 | 内容 |
|---|---|
| **批次** | P3-E（G-25 本体） |
| **日期** | 2026-10-04 |
| **触发** | 需求基线 **G-25** 行（⏳ 零代码，2026-10-03 登记）；排期 `delivery-plan.md` P6 行已订「本体归 P3-C」⇒ 实际落本批 |
| **前置已备** | P3-B 已给 CI 的 backend job 起 `neo4j:5.26-community` service（与 G-9 共用的工程项） |
| **状态** | 🟡 进行中 |

---

## 0. G-25 的五条判据（`delivery-requirements-and-guardrails.md` G-25 行）

| # | 判据 | 本批落点 |
|---|---|---|
| ① | CI 的 backend job 起 `neo4j` service | ✅ **已由 P3-B 完成** |
| ② | 导入**受控、可复现**的种子语料 | 用**仓库内**的 `demo/affiliation/*.csv` + 既有 `scripts/ingest_affiliation_sources.py --purge`（入库 ⇒ 可复现，不是"某次真机留下的库"） |
| ③ | 跑 `--live --criteria c2_a…,c2_b…` **出真值** | 既有 CLI 已支持；本批加 `--gate` 模式 |
| ④ | CI **只判「不退化」**（基线 delta + 容差），**不判达标** | 新增 `app/evaluation/gate.py`（纯逻辑、可单测）+ 基线文件入库 |
| ⑤ | **空图守卫**（空图 ⇒ 检测到 0 疑点 ⇒ 召回 0 ⇒ 假红，此时必须 **fail**） | gate 规则显式一条：gold 非空而 `detected_count == 0` ⇒ fail |

**可行性（P0-m6-eval 已实测）**：C2-a / C2-b 走 `AffiliationService().detect()`，**只读 Neo4j、零 LLM、零 HTTP**，2.72 秒出真值 ⇒ 进 CI 成本可忽略。
**本批复测（2026-10-04，空库导入种子后）**：`recall=1.0000 / fpr=0.0000`，与 P0-m6-eval 的实测一致 ⇒ 语料可复现。

---

## 1. 本批做什么

| # | 落点 | 内容 |
|---|---|---|
| **E1** | `backend/app/evaluation/gate.py`（新增） | 门禁**纯逻辑**：① `value is None` ⇒ fail（没测出来 ≠ 通过）；② 基线缺项 ⇒ fail（**不许跳过比对**）；③ 空图守卫：`gold_count > 0` 而 `detected_count == 0` ⇒ fail；④ 退化：recall 下降 / fpr 上升超容差 ⇒ fail；⑤ **不达标不 fail**（只记 warning——CI 只判不退化） |
| **E2** | `scripts/eval_acceptance.py` | 新增 `--gate`（按 gate 结果给退出码）/ `--baseline PATH` / `--tolerance`（默认 0.02）/ `--update-baseline`（**显式**写基线，打印警告：基线刷新会掩盖退化） |
| **E3** | `backend/data/eval/baselines/ci-c2-v1.json`（新增，入库） | 由**实测**生成（本批复测值），带 `git_hash` / `generated_at` / 语料版本 |
| **E4** | `.github/workflows/ci.yml` | backend job 新增步骤：导入种子语料 → 跑 `--gate`；失败摘要补本地复现命令 |
| **E5** | `backend/tests/test_eval_ci_gate.py`（新增） | 纯逻辑 6 条（退化红 / 不退化绿 / 缺基线红 / value=None 红 / 空图红 / **不达标不红**）+ 真图端到端 1 条（沿用 P3-B 的"不可达 ⇒ fail 不 skip"口径） |
| **E6** | 文档 | 需求基线 G-25 行转 ✅；`delivery-plan.md` P6 行；集成日志 |

## 2. 出口判据

1. `pytest` passed 不减（892 起跑，+7）；
2. gate 的 6 条纯逻辑**各自反向验证判红**；
3. **真图端到端**：导入种子 → `--gate` 绿；**故意清空**（purge 后不导入）⇒ `--gate` **红**（空图守卫生效）；
4. 全部门禁：ruff 双绿 / 接缝 OK 10 / 契约零漂移。

---

## 3. Non-goals（本批**不做**）

1. ❌ **不判达标**：CI 只判不退化；"召回 ≥ 0.80 / 误报 ≤ 0.15"仍属 P6 出口（且需 A8 扩标后才可宣称）；
2. ❌ **不改**指标函数（`app/evaluation/metrics.py`）、不改报告格式、不改四态状态机；
3. ❌ **不给 CI 加 LLM key**，也不让 C2-c / 多跳（B 类）进 CI——LLM 输出非确定性 ⇒ flaky 门禁比恒绿更伤；
4. ❌ **不做** A8 语料扩标（8/60/30/9 → 200/500/100/20），基线值仍是 provisional 语料上的值；
5. ❌ **不做** TBD-7 收敛口径（与 G-25 同批由人裁，另议）；
6. ❌ **不改**契约 / ADR 原文；不动租户隔离相关代码。
