# 新会话开场提示词 · P6-T（**C1 双侧 40×2 + 多跳 6 题人工判分 ⇒ 让 C1 分母变成数**）

> 🔒 **执行模式：人工判分为主**（与 P4~P6-S 的「无人值守」**不同**）——
> `docs/delivery-plan.md` §9.3 第 1 条明列：判分是**只能由人完成**的事，
> **AI 不得代做，也不许事后自己补数**（A3：脚本做关键词判分 = 假达标）。
>
> 👤 **人的部分**：照 §3 的材料**逐题判 true / false** 并写 `judged_by`。
> 🤖 **AI 的部分（只能做这些）**：准备与搬运材料、校验判分文件格式、跑**出数**命令、
> 逐题比对答案是否同源、回登口径与集成日志。**AI 不得替人填任何一个 `correct` 值**。
>
> 📦 **本文件自包含**：判分所需的材料路径、rubric、命令、已查实的陷阱都在本文里。
>
> 📌 **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 3 项](../../docs/delivery-plan.md)
> —— P6-T =「多跳答对率 / C1 双侧 40×2 人工判分（当前 `UNKNOWN`）」，**谁来 = 纯人工**。
>
> ⚠️ **依赖已满足**：P6-S（队列第 2 项）已出卷并定格 ⇒ 本批可开工。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 C1 从「两侧答卷齐了、但仍 `value=None`」推到「**判据真的出数**」：
由人照着 **P6-S 已定格的 40×2 答卷**判 true / false，再由脚本算出
`graph_accuracy` / `baseline_accuracy` / 增益，并一并判完多跳 6 题。

**不做**：代判分（红线）、改 rubric、改题集、改检索 / 采样、C1 与多跳之外的判据。

---

## 0.5 开工前必读（六份）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`backend/data/eval/MANIFEST.json` → `rubric` 字段** | **判分规则的唯一真源 = `rubric-v2`**（三条 + `correct_rule` + `tier_rule` + `judged_by_rule`）。判之前逐字读一遍，别凭印象 |
| 2 | **`backend/data/eval/judging/c1-sheets-20261009T064241Z.json`** | **被判对象（已定格）**：两侧各 40 题的题干 + `expected_points` / `secondary_points` / `should_refuse` + 答案原文 + `refused` / `citations` |
| 3 | **`backend/app/evaluation/runner.py` 的 `eval_graph_gain`（约 1011 行）** | 判分怎么被贴回、分母怎么算、`graph_spec` / `baseline_spec` 长什么样 |
| 4 | **`backend/scripts/eval_acceptance.py`** | CLI 参数（`--judgements` / `--baseline-judgements` / `--judged-by`）与两侧判分表的机检规则 |
| 5 | **`changes/P6-S/integration-log.md`** | 上一批做了什么、两趟 live 的实测读点、以及**未闭合项**（§13） |
| 6 | **`backend/data/eval/gold-multihop-v1.json`** | 多跳 6 题；判分**直接写回这个文件**的 `correct` / `judged_by` 字段 |

---

## 1. 执行模式：**人工判分** + AI 只做搬运 / 校验 / 回登

| 环节 | 谁做 | 说明 |
|---|---|---|
| 逐题判 true / false | **人** | 照 rubric-v2 三条；**AI 不得代填** |
| 写 `judged_by` | **人** | `judged_by_rule`：**禁止匿名判分** |
| 校验判分文件（键是题号、值是真布尔、两表不同文件） | AI | 脚本已会报错；AI 负责在提交前先跑一遍 |
| 跑出数命令、比对答案同源性 | AI | 见 §3 / §5 D2 |
| 回登口径（矩阵 C1 行、`dev-doc-status`、集成日志）+ 提交推送 | AI | 按角色分段 Conventional Commits |

**角色隔离**：AI 段默认只 **后端开发 B**（只改 `backend/`）；
若判定要改判据口径 / 矩阵 / `dev-doc-status` ⇒ 归**架构师**段（单独提交）。

**分支**：沿用 P4~P6-S —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P6-T / 为什么是这一刀

### 2.1 三条机械理由

1. **它是队列里下一个依赖已满足的项**：§9.2 第 3 项，前置 = P6-S 出卷**已完成**。
2. **C1 是最后一条没有数字的准入判据**：C2-a / C2-b / C2-c / 拒答误伤均已出数，
   只剩 C1 与多跳仍 `UNKNOWN` ⇒ 不判完，P6 收不了官、P8-Release 的零缺口无从对账。
3. **材料已经齐了**：40×2 答卷已定格（含题干与 rubric 锚点），判完即可出数，
   **不需要再重造任何东西**。

### 2.2 为什么**不是**这几条

| 候选 | 不做的原因 |
|---|---|
| **D4 / Sprint10.5 收口** | 队列第 4 项（P6-U），顺序在后 |
| **P5-J（M6 剩余读路径）** | 队列第 5 项（P6-V） |
| **L2 端到端 / 演练留证** | 需独立环境 + 双人执行 |
| **重判 C2-a / C2-b / C2-c** | 三条已出数且**判据层 = L1 算法层**（A8 裁决），本批不动 |
| **R27 / R30** | 挂起中；**与本批无关，不许混进来讲** |

---

## 3. 开工自检 + 判分材料（**先读材料，再判**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（29 路径）
uv run pytest -q                                      # 本地有图口径基线见 §7
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点绿
```

**判分材料（已定格，直接用，不要重跑 `--live` 再出一份新的）**：

```
backend/data/eval/judging/c1-sheets-20261009T064241Z.json
  graph[]    40 题（拒答 4）
  baseline[] 40 题（拒答 9）
  每条：index / question / should_refuse / expected_points / secondary_points
        / refused / citations / answer
  _git_hash=101773e7  _kg_version=attendance-demo-v1
  _graph_spec / _baseline_spec（两侧同源的机器凭据）
```

**rubric-v2（判分规则，逐字）**：

| 项 | 内容 |
|---|---|
| ① | 拒答判定与 `should_refuse` 一致 |
| ② | 答案覆盖 **core 要点**（`core = expected_points − secondary_points`；未标 `secondary_points` 的题，其全部要点一律为 core） |
| ③ | 无与语料矛盾的事实（幻觉） |
| `correct_rule` | ①②③ 全满足 ⇒ `true`；任一不满足 ⇒ `false`；**未判分 ⇒ `null`（不入分母，不是 0）** |
| `tier_rule` | secondary = 出处 / 算式 / 枚举细节 / 附加条件 / 例外情形；分级**必须**写在题集 JSON 里，不得临场裁量 |
| `judged_by_rule` | **禁止匿名判分** |

> ⚠️ `secondary` 要点**缺失不扣主分**（可另记「答案完整度」子指标，不参与本判据）。

---

## 4. 明确不做（**Non-goals，10 条**，逐条对照）

1. **AI 不得代填任何 `correct` 值**（A3 / §9.3 第 1 条）——本批红线，破了就是假达标。
2. **不改 rubric**：`rubric-v2` 已生效；要换 rulings ⇒ 属架构师裁决，**先停下升级**。
3. **不动题集**：`controlled-qset-v4.json` 40 题与 `gold-multihop-v1.json` 6 题
   的**题目一字不改**（只填 `correct` / `judged_by`）。
4. **不改检索 / 不回滚采样**：P6-N（字面量召回）/ P6-J（词面重排）/ P6-R（`temperature=0`）已定案。
5. **不动 C2-a / C2-b / C2-c 口径**。
6. **不用 BM25 作主基线**（A1 已裁）。
7. **不做 L2 端到端 / 演练留证**。
8. **不动 D4 / Sprint10.5**（P6-U）。
9. **不动前端**。
10. **不新增契约端点 / 错误码 / `settings.*`**（⇒ 不触发 S3）。

> ⚠️ **唯一可能要写代码的例外**：§5 的 **D3**（多跳侧没有答案导出通道）。
> 属"为了让判分这件事能做完"的必要改动，**要做就在 proposal 里显式登记理由**，
> 不许把它当成顺手做的事。

---

## 5. 决策表（**本批需要你我裁决并登记**）

| # | 决策 | 已查实的事实 / 处置 |
|---|---|---|
| **D1** ⚠️**必答** | **旧判分表能不能复用** | **不能**（已机械比对，见 §6 第 2 条）：图侧 40 题中仅 **9 题**答案与上次判分时逐位一致、基线侧 **14 题** ⇒ **重判 80 题**，不要照 `monotonicity_note` 的「80→11」乐观外推（那条只对「换 rubric、答案没变」成立，本批是**答案变了**） |
| **D2** ⚠️**必答** | **判分与出数怎么保证同源** | 判完再重跑 `--live` 会**重新生成答案** ⇒ 有「判分别人头上」的风险（正是 D1 比对发现的问题）。**处置**：出数那一趟**必须**跑 §8 判据 4 的比对脚本，逐题确认被判答案 == 出数那一趟的答案；**不一致的题要么重判、要么在报告里标注**，不许默认一致 |
| **D3** ⚠️**必答** | **多跳 6 题从哪拿答案原文** | **已查实缺口**：`eval_multihop_accuracy` 在缺判分时 detail 只有 `{"asked":6,"judged":0}`，**不吐答案原文** ⇒ 人无从判。可选：① 本批补一个导出通道（照 `export_judging_sheets.py` 扩到多跳）；② 只判 C1、多跳推下一批。**要选一条并登记理由** |
| **D4** ⚠️**必答** | **C1 与多跳能不能同一次跑** | **不能**（已查实）：两者共用同一个 `--judgements`，而受控题集 index 是 1..40、**多跳 index 也是 1..6** ⇒ 同一次跑会**题号串台**（判分别人头上）。**必须分开跑、分别给判分文件** |
| **D5** | 判分表落哪 | 历史 4 轮（p5b / p6f / p6h / p6j）都落在 **被 gitignore 的 `backend/reports/eval/`** ⇒ 判分是 A3 的核心资产却未受版本控制。**建议落 `backend/data/eval/judging/`（跟踪目录）**并带 `_rubric` / `_judged_by` / `_dataset` 元信息 |
| **D6** | 判据进不进 CI | **不进**（依赖 live LLM，且判分是一次性人工产物）。`tests/test_eval_baseline_a1.py` 等单测**已在 CI**，继续绿即可 |
| **D7** | 审计 / RBAC | 不动（`PROTECTED_ENDPOINTS` 现 **10 条**） |
| **D8** | 成本敞口 | 出数那一趟 = 40 HTTP + 40 基线 LLM。**只为「拿到数字」而跑，禁止「再跑一遍看看」**；跑前登记 |

---

## 6. 已完成 / 已查实（**前序批次，别重做**）

- ✅ **P6-S（2026-10-09）**：40×2 答卷定格并入库（`data/eval/judging/c1-sheets-20261009T064241Z.json`）；
  双侧 spec 与可比性断言提到判分闸门之前；判分值只收真布尔；A1 / C1 两行过期口径已订正。
  实测可比：池指纹 `e36322bb2d86865f` / 213 条两侧同源、`top_k` 32=32、
  `generation_model` / `prompt_id` 同源。**C1 当前 `value=None`，只差判分。**
- ✅ **旧判分表确实存在**（`backend/reports/eval/p6j-judge-graph.json` / `p6j-judge-baseline.json`，
  rubric-v2、`judged_by=architect`、graph **40/40**、baseline **34/40**）——
  ⚠️ 但**被判对象已换了一批**（P6-R 钉采样后重跑）⇒ 见 D1，**不得直接复用**。
- ✅ **C2-a / C2-b**（20/20 下界 0.8609、0/20 上界 0.1391）、**C2-c**（排除拒答 1.00）、
  **拒答误伤**（T=0 后 ≥3 趟一致为 0）。
- ⚠️ **继续有意不做**：R27（挂起）、`alert` 表（P2，**已连续多批**）。

---

## 7. 基线（**全部来自脚本 / CI 实读，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| 最近一次绿 CI | 开工时 `gh run list --limit 1` 实读。参考：P6-S 收口 run **37899319613**（四 job 全绿，EXIT=0） |
| `pytest`（本地**有图**口径） | P6-S 实读 **1154 passed / 3 skipped / 0 failed**（= P6-R 基线 1146/3 + P6-S 新增 8 条） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**29 路径**） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **10 条** |
| 题集 | `controlled-qset-v4` = **40 题**；`gold-multihop-v1` = **6 题**（`correct` 全 null） |
| 采样口径 | 接缝 3 钉 **`temperature=0`**（P6-R，常量，不许改成配置项） |
| C1 阈值 | `C1_GAIN_THRESHOLD`（`provisional`）；多跳阈值 **0.80**（`calibrated`） |

> ⚠️ **P6 系有「有图 / 无图」两套口径**（P6-P1 实测）：
> 真图三开关 `GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。
> ⚠️ 在 `Start-Process -ArgumentList` 里写 `$env:X` 会被**父壳展开成空** ⇒ 变量根本没传进去（P6-S 实测踩过）。
> 本机 Neo4j / PG 若停：`docker start graphrag-neo graphrag-pg`；
> `--live` 需后端与本地 embedding：`uv run uvicorn app.main:app --host 127.0.0.1 --port 8002`
> 与 `uv run python scripts/local_embedding_server.py --port 8009`。

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **C1 出数** | 贴 `graph_accuracy` / `baseline_accuracy` / 增益 / 阈值 / verdict；`status` 不再是 `UNKNOWN` |
| 2 | **`baseline_spec` 与基线分同时在报告里** | 防刷绿 ①②：贴报告 detail 的 `baseline_spec` + 基线分字段 |
| 3 | **反向守卫未破** | `tests/test_eval_baseline_a1.py` 全绿；基线侧 `k` **不小于**图侧、未换模型 / prompt（贴两侧 spec 比对） |
| 4 | **判分与出数同源** | 跑比对脚本：sheets 的 `answer` 与出数那一趟报告里 `awaiting_*` 的 `answer` **逐题逐位**比对，贴一致题数；不一致的题登记处置 |
| 5 | **判分表合规** | 两表**不同文件**、键为纯题号、值为真布尔、`judged_by` 非空、带 `_rubric` / `_dataset` 元信息 |
| 6 | **多跳判分完成或已登记延期** | 贴 `gold-multihop-v1.json` 的 `correct` 分布（true/false/null）与 `judged_by`；若按 D3 选了「推下一批」⇒ 在 `integration-log` 与矩阵里写明 |
| 7 | **契约零漂移** | `export_openapi.py --check` 零 diff |
| 8 | **pytest 不降 + 护栏不倒退** | CI ≥ 起点读数；`check_seams` 仍 OK 12；readiness 仍 17/0/0；**既有断言不许为让它绿而改** |
| 9 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登集成日志 |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

- **出数 ≠ 达标**：C1 阈值是 `provisional`，出数只是**有分母**；达标与否另行判定，
  且**不得**因出数就宣称 C1 达成。
- **一次判分 ≠ 永久有效**：答案一换（改检索 / 改采样 / 改 prompt / 改池）⇒ 判分即作废
  （D1 已经用 31/40 的变化量证明了这一点）。
- **本地绿 ≠ CI 绿**：以 CI 为终裁（R-10）。
- **rubric-v2 下的数字 ≠ rubric-v1 的数字**：v1 下 C1 = 0.0294（35/40 vs 34/40），
  **不得与 v2 结果混用**（MANIFEST 已写死）。
- **本批若碰到租户隔离相关路径**：须带上 **ADR-0003 §4.1** 的 **T1 跨 org 越权**（G-9）
  与 **T2 并发串租户**（G-10）—— **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only`**；
  既有断言**不许放宽**。

---

## 10. 提交推送纪律 + 升级用户的四类情况

**提交**：按 **人判分产物 / 后端（B）/ 架构师（矩阵 · dev-doc-status）** 分段 Conventional Commits，
跨侧改动**不得混在一个提交**。推送后**以 CI 为终裁**（R-10）；CI 红了先看是不是批次摊太大，
**不许先改测试让它绿**。

**只在以下四类停下找用户**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 自检与 §7 基线不符且不属已知环境债（如 dev license 缺失 ⇒ 全线 403） |
| 2 | **要动裁决 / rubric / 判据口径才能继续**（**先缩范围再报告**） | 判 rubric-v2 有系统性偏误要换 v3；或 D3 要改判据实现 |
| 3 | **边界冲突** | 实现中必须触碰 §4 某条 Non-goal（尤其**第 1 条：AI 代判分**） |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？
3. 真不行了 —— **报告时带上**：哪份文档 / 裁决的哪一行、要改什么、为什么绕不过去、
   **你试过的替代方案**。不接受「没写所以做不了」这种笼统结论。

---

## 11. 下一批指针（**本批收口时按实际结果更新，别照抄**）

> ⚠️ 队列唯一活版口径在 [`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md)，
> 编号固定为 **P6-T → P6-U → P6-V → P6-W → P6-X → P6-Y → P7-B → P8-Release**。

1. **P6-U：D4 / Sprint10.5 收口**（知识时效 L2 ②③）—— 同批须更正两处过期口径：
   `delivery-requirements-and-guardrails.md` **DR-D7** 仍写「⏳ 未做」、
   `delivery-plan.md` P5 出口判据③ 未标已达成。
2. **P6-V：P5-J（M6 剩余读路径 + `agents.py` 接线 + `cost_metrics`）** ⇒ 解开 C3-a / C3-b 的 `BLOCKED`。
   后续 P6-W（DR-E4 安装验收十项脚本化）→ P6-X（演练留证，**独立环境 + 双人**）→ P6-Y（L2 端到端）
   → P7-B → **P8-Release**（tag `v2.0.0`）。
3. **⚠️ P6-R 遗留未闭合项**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**。
4. **P6-S 新增的遗留项**（顺延）：`baseline_spec.embedding_dimension` 恒为 `null`
   （spec 构造早于首次 embed）；后端 8002 与本地 embedding 8009 的启停**没有脚本化**
   ⇒ 每批开工都可能重踩「旧进程 / 服务没起」两个坑。
5. **若 D3 选了「多跳推下一批」**：必须在集成日志与矩阵 §5.1 多跳行登记，别让它静默消失。
6. **TBD-7（成本阈值）** 与队列并行、**但要用户拍板** —— 它是 C3 能否从"趋势"变"达标"的开关。
7. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
8. **`alert` 表 + 限流超阈值联动**（P2，**已连续多批**有意不做）。
