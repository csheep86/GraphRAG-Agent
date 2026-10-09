# P6-T · 集成日志（C1 双侧 40×2 + 多跳 6 题人工判分：**材料与工具齐备，判分未完成 ⇒ 仍 `UNKNOWN`**）

> **日期**：2026-10-09 ｜ **边界文档**：[`proposal.md`](./proposal.md)（Non-goals **10 条**）
> **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 3 项](../../docs/delivery-plan.md)
> **一句话**：把「判分所需的**材料 / 工具 / 通道**」全部交付到位；
> **判分本身没有完成**（用户判了 2 题后决定顺延至项目末期）⇒ C1 与多跳答对率**仍 `UNKNOWN`**。
>
> **≡ 引用本批结论时的硬前置**：本批**没有产生任何一个 `correct` 值**，也**没有新增任何判据数字**。
> 出数 ≠ 达标；`UNKNOWN` ≠ 0。判分完成前，C1 与多跳**都不存在分数**。
>
> ⚠️ **必须传承的遗留**：86 题判分**顺延**至项目末期，但**P8-Release「零缺口」对账前必须判完**
> （已在矩阵 §5.1 C1 行 / 多跳行、`dev-doc-status` A3 行、`delivery-plan` §9.2 第 3 项四处登记）。

---

## 1. 本批做了什么（六件，全部可复跑）

| # | 产物 | 花费 |
|---|---|---|
| ① | **开工自检**（readiness / seams / openapi / pytest / CI）与 §7 基线对账 | ¥0 |
| ② | **D1 复核**：旧判分表 vs 定格答卷**逐位**比对 ⇒ 图侧 **9/40**、基线侧 **15/40** | ¥0 |
| ③ | **判分材料**：两张判分表模板（80 题，值全 `null`）+ 80 题阅读视图 | ¥0 |
| ④ | **多跳取答案**：一趟 `--live --criteria multihop_accuracy` ⇒ 6 条答案原文（**D3 缺口补齐**） | **6 次 HTTP**（无基线 LLM） |
| ⑤ | **代码改动 2 处 + 单测 3 条**：多跳 `answer_texts`（D3）、C1 出数 `answer_texts_graph` / `answer_texts_baseline`（D2） | ¥0 |
| ⑥ | **86 题工作单 + 交互式判分脚本** `scripts/judge_interactive.py`（D9：降门槛，**不代判**） | ¥0 |

> **Non-goals 第 1 条核销**：全流程一次都没让脚本算过「对 / 错」——
> 判分表模板 80 个值全是 `null`，`gold-multihop-v1.json` 的 `correct` 至今仍全 `null`，
> 交互脚本只搬运人按下的键，**不提示对错、不做关键词匹配**。

## 2. 开工自检（结论只来自脚本）

| 项 | 读数 | 与 §7 基线 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** | 一致 |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** | 一致 |
| `export_openapi.py --check` | **零 diff** | 一致 |
| `gh run list --limit 1` | run **37900063364** success（commit `0216a040`） | 起点绿 |
| `pytest`（有图口径） | **1154 passed / 3 skipped / 0 failed** | 与 P6-S 基线一致 |
| 容器 / 服务 | `graphrag-neo` / `graphrag-pg` Up；8002 / 8009 在监听 | — |

## 3. D1 复核：**旧判分表不可复用**（本批自己再跑一遍）

被判对象已换（P6-R 钉 `temperature=0` 后重跑）⇒ 拿唯一含 `awaiting_*` 的 `p6j-dryrun.json`
与当前定格答卷 `c1-sheets-20261009T064241Z.json` **逐位**比对：

| 侧 | 逐位一致 | 结论 |
|---|---|---|
| 图侧 | **9 / 40** | 旧表一律作废 |
| 基线侧 | **15 / 40** | 旧表一律作废 |

⚠️ 与 P6-S 集成日志记载的「基线 14」**差 1 题**：本批以**实跑**的 15 登记（严格 / 去空白两口径同为 9 / 15）。
差异**不影响**结论（都远低于「可复用」所需的 40/40），但**不许再引用 14 这个数**。

## 4. D2 / D3 的落地（**本批唯一的代码改动，已登记例外**）

| # | 缺口（已查实） | 处置 |
|---|---|---|
| **D3** | `eval_multihop_accuracy`（`runner.py`）缺判分时 detail 只有 `{"asked":6,"judged":0}`，**不吐答案原文** ⇒ 人无从判 | 缺判分**与出数两个分支**都带 `answer_texts`；`blocked_by` 补一句「可写回 `gold-multihop-v1.json` 的 `correct`」 |
| **D2** | §8 判据 4「判分与出数同源」**当时无法执行**——出数那一趟的 detail **不含答案原文** | `eval_graph_gain` 出数分支 detail 新增 `answer_texts_graph` / `answer_texts_baseline`（与既有 `awaiting_*` 同形状）⇒ 逐题可比 |

- **单测 +3 条**（`tests/test_eval_baseline_a1.py`：22 → **25 passed**，既有断言**一条未放宽**）：
  C1 出数带两侧原文 / 多跳缺判分吐原文 / 多跳出数带原文。
- 写测试时查实一个坑并钉住：**`graph_gain` 的分母是基线分**，`baseline_score <= 0 ⇒ 增益无定义**
  （`metrics.py:234`）⇒ 基线侧 40 题若全判 false，C1 照样出不了数。这条已写进材料给用户。

## 5. D9：门槛太高 ⇒ **降门槛，不转移责任**

用户反馈「86 题不会判、不知在哪看」。处置顺序严格照 §10 第 3 类：

1. 卡住的那条**本来就在 Non-goal 第 1 条**（AI 不得代填 `correct`）⇒ **红线不动**；
2. 能不能推到下一批 ⇒ 可以，但本批先**把门槛降到最低**再判断；
3. 于是新增 `scripts/judge_interactive.py`（384 行）：一次一题、人只按 **y / n**、
   `s` 跳过、`q` / Ctrl-C 退出且**进度落盘**（`data/eval/judging/judge-progress.json`，可续判），
   **86 题全判完才落盘**（半张表喂给 `--judgements` 会报错——故意的：未判 ≠ 判错）。

**冒烟证据（¥0）**：中断即保存进度；未全判不写判分表；全判路径生成 40 键真布尔 + `_judged_by` + gold 写回。
端到端测试用 `--gold-out` 指向临时目录，**真实 `gold-multihop-v1.json` 复查过仍是 `correct=null`**。

**结果**：用户判了 **2 题**（`G-01: true`、`G-02: true`）后决定**顺延至项目末期** ⇒ 按 D9 兜底收口。

## 6. 判分材料与工具清单（**都不含任何 `correct` 值**）

| 路径 | 内容 |
|---|---|
| `backend/data/eval/judging/c1-judge-graph-20261009T075906Z.json` | 图侧判分表模板，题号 `"1".."40"` 值**全 `null`** + rubric 元信息 |
| `backend/data/eval/judging/c1-judge-baseline-20261009T075906Z.json` | 基线侧判分表模板，同上（**与图侧必须是两个文件**） |
| `backend/data/eval/judging/c1-judging-view-20261009T075906Z.md` | 80 题阅读视图（题干 + core/secondary 要点 + 答案原文），**只读** |
| `backend/data/eval/judging/multihop-view-20261009T083610Z.md` | 多跳 6 题阅读视图（含 live 取回的答案原文） |
| `backend/data/eval/judging/judging-sheet-20261009T084532Z.md` | **86 题判分工作单**（唯一要填的文件，86 个填写位） |
| `backend/scripts/judge_interactive.py` | 交互式判分脚本（一次一题，人只按 y/n） |
| `backend/data/eval/judging/judge-progress.json` | 判分进度：**已判 2 题**（G-01 / G-02），可续 |
| `backend/reports/eval/eval-live-20261009T083547Z.json` | 多跳取答案那一趟的报告（`git=17351c69`，`answer_texts` 6 条） |

## 7. 决策登记（D1~D9）

| # | 决策 | 结果 |
|---|---|---|
| **D1** | 旧判分表能不能复用 | **不能**（图侧 9/40、基线侧 15/40）⇒ 重判 86 题，**不许**照 `monotonicity_note` 的「80→11」外推 |
| **D2** | 判分与出数怎么保证同源 | 用户裁决**选 ①** ⇒ 出数分支 detail 带 `answer_texts_graph` / `answer_texts_baseline`（已落地 + 单测） |
| **D3** | 多跳 6 题从哪拿答案原文 | 用户裁决**选 ①** ⇒ 补导出通道（已落地）+ 跑一趟取原文（6 HTTP）；判分写回 `gold-multihop-v1.json` 的 `correct` ⇒ 出数不必传 `--judgements`，**D4 串台自动消解** |
| **D4** | C1 与多跳能否同跑 | **不能**（共用 `--judgements`，index 1..40 与 1..6 串台）。选 D3 ① 后**多跳出数不必传判分文件** ⇒ 风险自动消解 |
| **D5** | 判分表落哪 | 落 `backend/data/eval/judging/`（**跟踪入库**），带 `_rubric` / `_judged_by` / `_dataset` 元信息（与历史上被 gitignore 的 `reports/eval/` 分置） |
| **D6** | 判据进不进 CI | **不进**（依赖 live LLM）。新增/改动的单测**本来就在 CI**，继续绿 |
| **D7** | 审计 / RBAC | 未动（`PROTECTED_ENDPOINTS` 仍 **10 条**） |
| **D8** | 成本敞口 | 只跑 **1 趟 × 6 次 HTTP**（多跳取答案）；**出数那一趟未跑**（判分未完成 ⇒ 跑了也只出 `UNKNOWN`）⇒ 无第二趟 |
| **D9** | 判分门槛太高怎么办 | **红线不动**：AI 不代填。降门槛 = 交互脚本（一次一题、y/n、可续判）；**人最终不判 ⇒ 兜底收口：材料齐备、判据仍 `UNKNOWN`、四处登记阻塞** |

## 8. 收尾三问自答

1. **有没有顺便做的东西？** 除 D2 / D3 / D9 三处**已登记**的例外，没有：
   阈值、题集、rubric、检索、采样、契约**一行未改**；`awaiting_*` 等既有字段**未重命名**
   （`export_judging_sheets.py` 有消费者）。
2. **有没有为躲坑而绕路的实现？** 没有。D2 选的是「出数分支**多带一份原文**」而不是「放宽同源判据」；
   D9 选的是「降低人的操作门槛」而不是「AI 代判」。
3. **验收判据是跑出来的还是读代码得出的？** D1 是**机械比对**实跑；多跳取答案是**真跑 6 次 HTTP**；
   D2 / D3 的行为由**单测**（+3 条）钉住 —— 属单测而非实测，此处明写；
   **判据 1（C1 出数）未达成**（判分未完成），判据 4（同源比对）**通道已备、待判分后执行**。

## 9. Non-goals 核销（10 条）

| # | 结论 |
|---|---|
| 1 不代填 `correct`（红线） | ✅ 判分表全 `null`、gold `correct` 全 `null`、脚本不产出判分意见 |
| 2 不改 rubric | ✅ `rubric-v2` 未动 |
| 3 不动题集 | ✅ `controlled-qset-v4.json` / `gold-multihop-v1.json` 题目一字未改 |
| 4 不改检索 / 不回滚采样 | ✅ 未触碰 |
| 5 不动 C2-a / C2-b / C2-c 口径 | ✅ 未触碰 |
| 6 不用 BM25 作主基线 | ✅ 连敏感性对照都没跑 |
| 7 不做 L2 端到端 / 演练留证 | ✅ 未做 |
| 8 不动 D4 / Sprint10.5 | ✅ 未触碰 |
| 9 不动前端 | ✅ 未触碰 |
| 10 不新增端点 / 错误码 / `settings.*` | ✅ 无 ⇒ **未触发 S3** |

## 10. 全部门禁（收尾）

| 项 | 读数 |
|---|---|
| `ruff check` / `ruff format --check` | **All checks passed** |
| `export_openapi.py --check` | **零 diff** |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `pytest`（有图口径） | **1157 passed / 3 skipped / 0 failed** = 基线 1154/3 **+ 新增 3 条** |
| CI（收口） | run **37911774412**（`1b610fc`）**success**，`gh run watch --exit-status` **EXIT=0**；中段 run **37902257091** / **37906937964** / **37909829798** 均 success |
| `tests/test_eval_baseline_a1.py` | **25 passed**（22 → 25） |

## 11. `check_session_drift`（实跑输出，五个判据全 OK）

| 判据 | 输出 |
|---|---|
| **S1** | `[OK] changes\P6-T\proposal.md 已登记 10 条边界` |
| **S2** | `[OK] 5 个文件 / 新增 378 行`（docs 回登 4 处 + 本批集成日志与下一批提示词，未超阈值）|
| **S3** | `[OK] 未发现 Settings 字段需要同步 .env.example` ⇒ 未触发 S3 |
| **S4** | `[OK] 未改动契约路由` ⇒ 契约不用同步 |
| **S5** | `[OK] 新增模块均已被 app 引用或未新增模块` ⇒ `scripts/judge_interactive.py` 属 `scripts/`，消费者是**人工判分流程**（§13 第 1 条已登记）|

## 12. 本批新查实、但**不在本批处理**的口径 / 环境债

1. **`graph_gain` 分母 = 基线分** ⇒ 基线侧全判 false（基线分 0）时**增益无定义**（`metrics.py:234`）。
   已写进材料提示，**不属缺陷**，但判分须知。
2. **GitHub 推送 443 超时**（本批连续 3 次 `curl 28`），最终由用户推送成功；
   本地 8002 / 8009、`api.deepseek.com`（401 = TLS 通）**均可达** ⇒ 判据跑数不受影响，只是**推送通道不稳**。
3. **P6-S 遗留顺延**：`baseline_spec.embedding_dimension` 恒 `null`；后端 8002 / embedding 8009 启停**未脚本化**
   （本批开工又踩到「旧进程 / 服务是否已起」的判断成本）。

## 13. 下一批指针（按实际结果更新）

1. **⚠️ P6-T 判分遗留（本批最大未闭合项）**：86 题人工判分**顺延至项目末期**，
   **P8-Release 前必须判完**（否则 §5.1 的 C1 行与多跳行无法从 `UNKNOWN` 翻成数，"零缺口"无从对账）。
   - 入口二选一：填 `backend/data/eval/judging/judging-sheet-20261009T084532Z.md`（86 题，判分行填 `true`/`false`）；
     或跑 `uv run python scripts/judge_interactive.py --judged-by <署名>`（一次一题按 y/n）。
   - 已判 **2 题**在 `judge-progress.json`（续判时不重判）。
   - **判完 ⇒ 出数只需两趟**：`--live --criteria c1_graph_gain --judgements <graph表> --baseline-judgements <baseline表>`
     （40 HTTP + 40 基线 LLM）+ `--live --criteria multihop_accuracy`（6 HTTP，判分已写回 gold ⇒ **不需** `--judgements`）。
   - 出数后**必须**执行判据 4：用报告里的 `answer_texts_*` 与被判的 sheets 原文**逐题**比对，不一致的题登记处置。
   - **未来每批的 `new-session-prompt` 都要传承这一条**，不许让它静默消失。
2. **P6-U：D4 / Sprint10.5 收口**（知识时效 L2 ②③），同批更正两处过期口径：
   `delivery-requirements-and-guardrails.md` **DR-D7** 仍写「⏳ 未做」、`delivery-plan.md` P5 出口判据③ 未标已达成。
3. **P6-V**（P5-J：M6 剩余读路径）⇒ 解开 C3-a / C3-b 的 `BLOCKED`；
   后续 P6-W → P6-X（演练留证，**独立环境 + 双人**）→ P6-Y（L2 端到端）→ P7-B → **P8-Release**（tag `v2.0.0`）。
4. **P6-R 遗留**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**。
5. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
6. **`alert` 表 + 限流超阈值联动**（P2）：**已连续多批**有意不做。
