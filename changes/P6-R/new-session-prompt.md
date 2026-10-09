# 新会话开场提示词 · P6-S（**A1：向量基线 + 双侧判分 ⇒ 让 C1 分母存在**）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找用户。
>
> 📦 **本文件自包含**：开工所需坐标、命令、基线、陷阱都在本文里。
>
> 📌 **计划真源**：[`docs/delivery-plan.md` §9「P6 收官队列」](../../docs/delivery-plan.md)。
> **本批 = 队列第 2 项**，目标 / 依赖 / 出口判据以该文件 §9.2 为准；本文只是它的开工扩大版。
>
> ⚠️ **依赖顺序已满足**：P6-R 动过采样（接缝 3 钉 `temperature=0`）⇒
> **本批两侧必须在同一个采样口径下跑**，否则基线不同源。P6-R 已完成 ⇒ 本批可开工。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 **A1（向量基线）** 从「协议 + fixture」推进到「**能出数**」：让 **C1 的分母真的存在**，
并按 A1 的防刷绿三条把数落盘。**判分本身仍归 P6-T（纯人工）** —— 本批只负责让「出卷」这件事成立。

**不做**：P6-T（人工判分）、D4 / Sprint10.5、P5-J、L2 端到端、演练留证、R27 / R30、C1 之外的判据。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`docs/dev-doc-status.md:380`（A1 行）** | A1 裁决**全文**（L10-A1）：唯一变量 / 基线检索方式 / 防刷绿三条 / G5 声明。⚠️ 行内「`BaselineRunner` 协议**并未建立**（`backend/` 内零匹配）」这句**疑似已过期**，见 §6 |
| 2 | **`backend/app/evaluation/baseline.py`** | A1 的**实际落点**：`BaselineSpec` / `Embedder` Protocol / `OpenAICompatibleEmbedder` / `DenseTopKRetriever` / `answer_with_dense` / `comparability_error` / `pool_fingerprint` |
| 3 | **`backend/app/evaluation/runner.py:940-1215`（`eval_graph_gain`）** | C1 的判据实现与三条硬要求；**先读它再判断还缺什么**，别照着 A1 行的旧口径开工 |
| 4 | **`backend/tests/test_eval_baseline_a1.py`**（20 条） | 已钉住的反向守卫（基线侧 `k` 不得更小 / 池不同 / prompt 或模型不同 ⇒ 拒绝） |
| 5 | **`changes/P6-R/integration-log.md`** | 上一批改了什么（钉 `temperature=0`）、为什么、以及**未闭合的一处**（§11 第 1 条） |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本文 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P6-S/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **预期不动契约**；若判定要动 ⇒ 走完同步五步（**不算升级**） |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

> ⚠️ **契约描述的真源是 `backend/app/core/openapi.py`，不是 `contracts/openapi.yaml`**。

**角色隔离**：本批默认只 **后端开发 B**（只改 `backend/`）；
若判定要改 spec / ADR / 判据口径 ⇒ 归**架构师**段（单独提交）。doc 更新同理。

**分支**：沿用 P4 / P2-C / P5-B~P5-I / P6-A~P6-R —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P6-S / 为什么是这一刀

### 2.1 三条机械理由

1. **它是队列里下一个依赖已满足的项**：`delivery-plan.md` §9.2 第 2 项，前置 = P6-R（两侧不许再动检索 / 采样）**已完成**。
2. **C1 是最后一条没有分母的准入判据**：C2-a / C2-b / C2-c 均已出数（含本批之前 P6-R 把误伤判据转 PASS），
   只剩 C1 仍 `BLOCKED` ⇒ 它是「P6 能不能收官」的实質卡点之一。
3. **大部分骨架已存在**（`baseline.py` + `eval_graph_gain` + 20 条测试）⇒ 本批是**补齐与出数**，
   不是从零造轮子；¥ 可控（embedding + 两侧各 40 题）。

### 2.2 为什么**不是**这几条

| 候选 | 不做的原因 |
|---|---|
| **P6-T（40×2 人工判分）** | **纯人工**（A3：脚本代判 = 假达标）⇒ 只能是 P6-S 出卷**之后**的独立批次 |
| **D4 / Sprint10.5 收口** | 队列第 4 项（P6-U），顺序在后 |
| **P5-J（M6 剩余读路径）** | 队列第 5 项（P6-V），内部债 |
| **L2 端到端 / 演练留证** | 需独立环境 + 双人执行（L10-ENV），不是一个批次能收的 |
| **R27 / R30** | 挂起中；**与本批无关，不许混进来讲** |

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（29 路径）
uv run pytest -q                                      # 本地口径基线见 §7
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

**然后做本批的第一件事（是盘点，不是写代码）**：

```powershell
# ① C1 现在到底被什么挡住 —— 自己读代码 + 跑一次，别信文档里的旧口径
uv run python scripts/eval_acceptance.py --live --criteria c1_graph_gain
#    ⇒ 把 blocked_by 原文抄下来（判分缺失？embedding 配置缺失？两者都有？）
# ② 确认基线侧能不能真连上 embedder
uv run pytest -q tests/test_eval_baseline_a1.py       # 期望 20 passed
```

> 本机 Neo4j / PG 容器若停了：`docker start graphrag-neo graphrag-pg`。
> 真图用例三开关：`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。
> dev license 已在 PG `licenses` 表（1 行）⇒ 不补会全线 **403 LICENSE_MISSING**（P5-B 踩过）。
> ⚠️ **起后端才能 `--live`**：`uv run uvicorn app.main:app --host 127.0.0.1 --port 8002`。

---

## 4. 明确不做（**Non-goals，10 条**，逐条对照；改一条都要先回来登记理由）

1. **不回滚 / 不改 P6-R 的采样裁决**：`build_chat_model()` 的 `temperature=0` 已落地且是**常量**，
   不许改回默认值、也不许顺势做成配置项（改了 ⇒ 本批两侧与 P6-R 的读数不同源）。
2. **不得用脚本代判分**（A3）：判分只能由人做；本批最多做到「出卷 + 落盘 `correct=null`」。
3. **不动拒答判定 / 不改题集**：`controlled-qset-v4.json` 的 40 题一字不改（改题 = 改判据基准）。
4. **不动 C2-a / C2-b / C2-c 的口径**：三条均已出数（A6 / A8 已裁）。
5. **不动召回 / 重排**：P6-N（字面量召回）与 P6-J（词面重排）已定案。
6. **不用 BM25 作主基线**：A1 已裁（中文长文档偏弱 ⇒ 基线分低 ⇒ 增益虚高 ⇒ C1 可被刷绿）；
   BM25 **仅作敏感性对照**，不作判据。
7. **不做 L2 端到端 / 演练留证**：需独立环境 + 双人执行。
8. **不动 D4 / Sprint10.5**：队列第 4 项（P6-U）。
9. **不动前端**：本批没有新的 UI 消费方。
10. **不新增契约端点 / 错误码**：判据批次。

> ⚠️ **若判定必须新增 `settings.*`（如 embedding 相关）** ⇒ 触发 S3（`.env.example` 同步）
> + 「无消费者的配置不得提交」⇒ 必须在 proposal 里显式登记理由与消费点。

---

## 5. 决策表（**本批需要你自己裁决并在 integration-log 登记**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** ⚠️**必答** | **C1 当前的真实阻塞项是什么** | 先跑 `--criteria c1_graph_gain` 拿到 `blocked_by` 原文，再定位（判分缺失 / embedding 配置缺失 / 两者）。**不许照抄 A1 行里「协议未建立」这个旧口径**（见 §6） |
| **D2** ⚠️**必答** | 本批的**完成线**划在哪 | 建议：`--live --criteria c1_graph_gain` **出数**（两侧分数 + 增益 + `baseline_spec` 全部落盘）⇒ 即达成；**人工判分留给 P6-T**。若你认为还要连带做别的 ⇒ 先登记再动 |
| **D3** ⚠️**必答** | 防刷绿三条怎么逐条验 | ① 基线分**必须落盘**（只落增益不可复核）；② `baseline_spec` 进报告；③ 反向守卫（基线侧 `k` **不得小于**图侧、不得换模型 / 换 prompt）—— 三条都要能贴机器输出，且**既有断言不许放宽** |
| **D4** ⚠️**必答** | 与 P6-R 的同源性怎么证 | 两侧必须跑在**同一个采样口径**下（P6-R 已钉 T=0）⇒ 报告里要能看出两侧 `generation_model` / prompt 版本一致 |
| **D5** | A1 那条过期口径要不要订正 | 若实测确认 `baseline.py` 已落地 ⇒ **必须订正** `dev-doc-status.md:380` 的「协议零匹配」（R-5：只追加不重排，追加订正块） |
| **D6** | 判据进不进 CI | **不进**（与 C2-c / 拒答误伤一致：依赖 live LLM + embedding；且判分未做 ⇒ 无分母）。`tests/test_eval_baseline_a1.py` 的 20 条**已在 CI**，继续绿即可 |
| **D7** | 审计 / RBAC | 不动（`PROTECTED_ENDPOINTS` 现 **10 条**） |
| **D8** | 成本敞口 | 两侧各 40 题 + embedding。**每趟都要对应一个此前拿不到的结论**，禁止「再跑一遍看看」；预估花销在实际执行前登记 |

---

## 6. 已完成（**前序批次，别重做**）

- ✅ **P6-R（2026-10-09）**：用户裁 **O1** 并落地 —— 接缝 3 钉 `temperature=0`（常量）；
  拒答误伤判据 **FAIL → PASS**（落地后 ≥3 趟一致为 0）；抽取侧由「不可复现」变为「可复现」
  （探针 `probe_p6r_extraction_drift.py`：before 14/7 vs 19/8；after 12/9 逐位一致）。
- ✅ **A1 的骨架看起来已落地**（**本批开工前刚核过，但需你复核**）：
  `app/evaluation/baseline.py` 已有 `BaselineSpec` / `Embedder` Protocol / `OpenAICompatibleEmbedder` /
  `DenseTopKRetriever` / `answer_with_dense` / `comparability_error` / `pool_fingerprint`；
  `runner.py:1011` 已有 `eval_graph_gain`；`tests/test_eval_baseline_a1.py` **20 条**。
  ⚠️ ⇒ A1 行那句「`BaselineRunner` 协议**并未建立**（`backend/` 内**零匹配**）」**疑似过期**，
  但**未做逐项核对** ⇒ 本批第一步就是把它查实（D1 / D5）。
- ✅ **C2-a / C2-b**（P6-A，20/20 下界 0.8609、0/20 上界 0.1391）、**C2-c**（排除拒答 1.00）。
- ⚠️ **继续有意不做**：R27（挂起）、`alert` 表（P2，**已连续多批**）、成本仪表盘（批次 D）。

---

## 7. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| 最近一次绿 CI | **不要照抄**：开工时 `gh run list --limit 1` 实读。参考：P6-R 起点 run **37886225303**（四 job 全绿） |
| `pytest`（本地口径） | P6-R 实读 **1146 passed / 3 skipped / 0 failed**（**有图**口径）。⚠️ 该数是**补齐本地 `affiliation-demo-v2` 之后**的口径，与更早的 1143/4/2failed 不可直接比 |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**29 路径**） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **10 条** |
| 题集 | v4 = **40 题**（灵敏度 2.5pp） |
| **采样口径（本批同源前提）** | 接缝 3 钉 **`temperature=0`**（P6-R 落地，常量） |
| C2-c | 排除拒答 **1.00**；含拒答 **0.9** |
| 拒答误伤 | 落地后 **≥3 趟一致为 0**；`missed_refusals` 恒空 |

> ⚠️ **P6 系批次有「有图 / 无图」两套口径**（P6-P1 实测）。本批 `--live` 属 **live 口径** ⇒ 两个数都要报，不许混用。

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **阻塞项已查实**（不是照抄文档） | 贴 `--criteria c1_graph_gain` 的 `blocked_by` 原文 + 你的定位结论 |
| 2 | **C1 出数**（或明确「只差判分」） | 贴两侧分数 + 增益 + `baseline_spec` + `graph_spec`；若因判分缺失出不了数 ⇒ 贴「差什么」并说明本批做到哪一步 |
| 3 | **防刷绿三条逐条验** | 基线分落盘 / `baseline_spec` 进报告 / 反向守卫三条（贴 `test_eval_baseline_a1.py` 全绿） |
| 4 | **与 P6-R 同源** | 报告里两侧 `generation_model` / prompt 版本一致；**采样未被回滚** |
| 5 | **过期口径已订正** | 若 §6 的疑点被坐实 ⇒ `dev-doc-status.md:380` 追加订正块；没坐实就写明「查了，未过期」 |
| 6 | **契约零漂移** | `export_openapi.py --check` 零 diff |
| 7 | **pytest 不降** | CI ≥ 起点读数；`check_seams` 仍 OK 12；**既有断言不许为让它绿而改** |
| 8 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 9 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

- **出数 ≠ 达标**：C1 的**判分仍然要靠人**（P6-T）；本批最多让分母**存在**。
- **`BaselineRunner` 存在 ≠ A1 全部达成**：还要看防刷绿三条是否真的验过。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常停、本地口径曾因补语料变化 ⇒ **以 CI 为终裁**（R-10）。
- **本批若碰到租户隔离相关路径**：须带上 **ADR-0003 §4.1** 的 **T1 跨 org 越权**（G-9，
  `test_guardrails_graph.py` + `test_guardrails_rls.py`）与 **T2 并发串租户**（G-10，
  `tests/test_guardrails.py:328`）—— **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only`**；
  既有断言**不许放宽**。
- **不许把 P6-R 的采样改动回滚或改成配置项**（Non-goal 1）——那会让两侧与历史读数不同源。

---

## 10. 提交推送纪律 + 升级用户的四类情况

**提交**：按 **后端（B）/ 架构师（spec · ADR · dev-doc-status · 矩阵）** 分段 Conventional Commits，
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10）；CI 红了先看是不是批次摊太大，
**不许先改测试让它绿**。

**只在以下四类停下找用户**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §7 基线不符且不属已知环境债（如 dev license 缺失 ⇒ 全线 403） |
| 2 | **要动 spec / ADR / 裁决才能继续**（**先做完三步自检再报告**） | 要改 A1 裁决的基线检索方式；或判定必须新增 `settings.*` |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal（尤其第 1 条：回滚采样；第 2 条：脚本代判分） |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？
3. 真不行了 —— **报告时带上**：哪份文档 / 裁决的哪一行、要改什么、为什么绕不过去、
   **你试过的替代方案**。不接受「没写所以做不了」这种笼统结论。

---

## 11. 下一批指针（**本批收口时按实际结果更新，别照抄**）

> ⚠️ 队列唯一活版口径在 [`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md)，
> 编号固定为 **P6-S → P6-T → P6-U → P6-V → P6-W → P6-X → P6-Y → P7-B → P8-Release**。
> 本批收口时**不再重写一份列表**，只把 §9.2 里本批之后的第一行**按实际进度核一遍**即可。

1. **P6-T：40×2 人工判分**（C1 双侧 + 多跳答对率）—— **纯人工**，A3 纪律：脚本代判 = 假达标。
   **依赖 P6-S 出卷**。
2. **P6-U：D4 / Sprint10.5 收口**（知识时效 L2 ②③）—— 同批须更正两处过期口径：
   `delivery-requirements-and-guardrails.md:120` **DR-D7** 仍写「⏳ 未做」、`delivery-plan.md:80` P5 出口判据③ 未标已达成。
3. **P6-V：P5-J（M6 剩余读路径 + `agents.py` 接线 + `cost_metrics`）** —— 它解开 C3-a / C3-b 的 `BLOCKED`。
   ⚠️ **依赖顺序**：P6-W（DR-E4 安装验收十项脚本化）→ P6-X（演练留证，**独立环境 + 双人**）→ P6-Y（L2 端到端）
   → P7-B（readiness 补 `skipif` 档）→ **P8-Release**（上线 gate 终审 + tag `v2.0.0`）。
4. **⚠️ P6-R 遗留未闭合项**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**
   （P6-R 以「图外探针 + 摄入不经 LLM 的机械论证」替代）。建议在 P6-U / P6-X 之前找机会真重入一次图。
5. **发布清单要记采样默认值**：每次发布记录 `temperature` / 采样默认 ⇒ 否则历史数字不可比。
6. **R27**（注入层 93%）：保持挂起，触发条件见 P6-N。**R30**（引用口径残留）：P6-P1 登记。
7. **`human_review` 队列读端点**（M2 的 S9.13-2）；**`ontology/confirm` / `cold-start` / `active` 仍占位**（批次 A）。
8. **成本仪表盘 / `cost_metrics`**（批次 D）：`cost_ratio` 阈值 TBD-7 **Sprint 13** 收敛前拿不到判据。
9. **`alert` 表 + 限流超阈值联动**（P2，**已连续多批**有意不做）。
