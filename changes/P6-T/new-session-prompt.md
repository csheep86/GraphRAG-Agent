# 新会话开场提示词 · P6-U（**D4 / Sprint10.5 收口：知识时效 L2 ②③** + 两处过期口径更正）

> 🔒 **执行模式：无人值守**（`unattended-sprint-execution` 技能；默认采纳文档建议项，
> **只有 4 类情况停下找用户**：① 前置不成立 ② 要动裁决 / rubric / 判据口径（**先缩范围再报告**）
> ③ 边界冲突（要碰 Non-goal）④ CI 红了且复核两遍仍红）。
>
> 📌 **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 4 项](../../docs/delivery-plan.md)
> —— P6-U =「D4 / Sprint10.5 收口（知识时效 L2 ②③）+ 顺手修 `delivery-plan.md:80` 与 `DR&G:120` 两处过期口径」，**谁来 = AI**。
>
> ⚠️ **依赖已满足**：P6-T 已收口（判分材料与工具齐备）。
>
> 📦 **本文件自包含**：基线读数、纪律、遗留项都在本文里。**边界（Non-goals 10 条）由你在开工第一步写进 `changes/P6-U/proposal.md`**（drift S1 会去读它）。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把**在途未提交**的知识时效 L2 ②③（= **DR-D4**）收口：按 §6.4 的裁决把 `changes/Sprint10.5/`
改指新阶段编号（`git mv` 到 `changes/P6-U/`）、承接 `backend/` 的未提交改动、
把 P5 四条出口判据补齐，并更正两处已过期的口径。

**不做**：动 C1 / 多跳判分（那是**人**的事）、改 rubric / 题集、动 C2-a / C2-b / C2-c 口径、动前端。

---

## 0.5 开工前必读（五份）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | [`changes/P6-T/integration-log.md`](./integration-log.md) | **上一批做了什么 / 没做什么**：判分**未执行** ⇒ C1 与多跳仍 `UNKNOWN`（§13 第 1 条是**必须传承**的遗留） |
| 2 | `docs/delivery-requirements-and-guardrails.md` **§6.4**（约 380-392 行） | 在途工作与**旧编号 `Sprint10.5` 冲突**的裁决原文：工作内容保留、编号作废、`git mv` 时机 = **本批开工第一步** |
| 3 | `docs/delivery-requirements-and-guardrails.md` **DR-D4 行（117）** + **DR-D7 行（120）** | D4 = 知识时效 L2 ②③；DR-D7（`question` 参与检索）仍写「⏳ 未做」⇒ **两处过期口径之一** |
| 4 | `docs/delivery-plan.md` **第 80 行**（P5 阶段行） | P5 出口判据 ①~④；判据 ④ 即 D4 承接，判据 ③ 原写 `qa_logs` 建表**已于 2026-09-26 达成** ⇒ **过期口径之二** |
| 5 | `changes/Sprint10.5/` 目录内的 `00-recon.md` / `proposal.md`（若仍在） | 在途工作的真实范围：`11-derived-window-inheritance` / `12-document-scope-inheritance` / `13-as-of-evidence-rank` + probe 脚本 |

---

## 1. 执行模式与纪律

- **角色隔离**：AI 段默认只 **后端开发 B**（只改 `backend/`）；
  改判定口径 / 矩阵 / `dev-doc-status` / `delivery-plan` ⇒ 归**架构师**段（**单独提交**）。
- **分支**：沿用 P4~P6-T —— **在 `main` 上直推**，不另开分支。
- **提交**：按 **后端（B）/ 架构师（文档回登）/ 人判分产物** 分段 Conventional Commits，跨侧**不得**混在一个提交。
- **推送**：⚠️ **本仓库 GitHub 推送通道不稳**（P6-T 期间连续 3 次 `curl 28` 443 超时，最终由用户推成功）。
  推送失败 ⇒ **重试一次**，仍失败就**把完整命令交给用户**，**不许**改 remote / 绕道。
- **终裁**：以 CI 为终裁（R-10）；CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。

---

## 2. 为什么是 P6-U / 为什么不是这几条

| 候选 | 判断 |
|---|---|
| **D4 / Sprint10.5 收口** ✅ | 队列第 4 项，顺序在 P6-T 之后；**在途未提交 + 编号冲突**已挂很久（2026-10-01 发现） |
| P6-V（P5-J：M6 剩余读路径 + `cost_metrics`） | 队列第 5 项，顺序在后 |
| **P6-T 判分 86 题** | **人是瓶颈**：材料与工具已齐备，用户决定**顺延至项目末期** ⇒ **不在本批做**，但**必须传承**（§11 第 1 条） |
| L2 端到端 / 演练留证 | P6-X / P6-Y，需**独立环境 + 双人** |
| R27 / R30 | 挂起中，**不许混进来讲** |

---

## 3. 开工自检（**先跑，再动手**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（29 路径）
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点绿
git status --short                                    # ⚠️ 先看清**在途未提交改动**有哪些
```

⚠️ **在途未提交改动是本批的作业面，不是噪声**：开工第一步先 `git status`，
把 `backend/` 的未提交改动逐项归因（属于 D4 的收进来；不属于的**登记后保留原状**，不许顺手改）。

---

## 4. Non-goals（**开工第一步写进 `changes/P6-U/proposal.md`，登记 10 条**）

至少包含这 6 条硬约束（其余由你按实际作业面补齐到 10 条）：

1. **AI 不得代填任何 `correct` 值**（A3 / §9.3 第 1 条）——**永久红线**，P6-T 已守，本批继续守。
2. **不改 rubric / 题集**（`rubric-v2` / `controlled-qset-v4` / `gold-multihop-v1` 题目一字不改）。
3. **不动 C2-a / C2-b / C2-c 口径**（三条已出数，判据层 = L1 算法层，A8 裁决）。
4. **不改检索 / 不回滚采样**（P6-N / P6-J / P6-R 已定案；`temperature=0` 是常量，不许改配置项）。
5. **不动前端**。
6. **不新增契约端点 / 错误码 / `settings.*`**（⇒ 不触发 S3）；若确需 ⇒ 属 §10 第 2 类，**先停下升级**。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ 属 **§10 第 3 类边界冲突**：
> **先缩范围**（能不能整体推下一批并登记），再报告时带上「哪份文档哪一行 / 要改什么 / 为什么绕不过去 / 试过的替代方案」。

---

## 5. 决策表（**开工时按实际作业面填并登记**）

| # | 决策 | 现状 / 提示 |
|---|---|---|
| **U1** ⚠️ | `changes/Sprint10.5/` 的**落点与编号** | §6.4 已裁：内容保留、`Sprint10.5` 编号失效 ⇒ `git mv changes/Sprint10.5 changes/P6-U/`（**P5 开工第一步**，即本批）并同步目录内编号引用。**只改名，不重排内容**（R-5） |
| **U2** ⚠️ | `backend/` 在途未提交改动怎么接 | 先 `git status` 归因；属 D4 的收进来，**不属的登记保留**；**不许**顺手格式化 / 重构 |
| **U3** | P5 四条出口判据的达成度 | 判据 ③（`qa_logs` 建表）2026-09-26 已达成 ⇒ 与 §6.4 一并更正；判据 ①②④ 逐条核对并**只追加**登记 |
| **U4** | 两处过期口径更正 | `DR&G:120`（DR-D7 仍写「⏳ 未做」）与 `delivery-plan.md:80`（P5 出口判据③）⇒ **只追加不重排（R-5）**，写明「上一句已过期，勿再引用」 |
| **U5** | 判据进不进 CI | 沿用 D6：**判据不进 CI**（依赖 live LLM）；新增 / 改动的单测**本来就在 CI** |

---

## 6. 已完成 / 已查实（**前序批次，别重做**）

- ✅ **P6-T（2026-10-09）**：C1 双侧 40×2 判分表模板 + 86 题工作单 + 交互判分脚本 + 多跳 6 题答案原文**已齐备**；
  **判分未完成**（已判 2 题于 `judge-progress.json`）⇒ C1 与多跳仍 `UNKNOWN`。
  D2 / D3 已落地（出数分支带 `answer_texts_*`；多跳带 `answer_texts`）。
- ✅ **P6-S**：40×2 答卷定格（`c1-sheets-20261009T064241Z.json`），双侧可比（池指纹 `e36322bb2d86865f` / 213 条、`top_k` 32=32）。
- ✅ **C2-a / C2-b / C2-c / 拒答误伤**已出数；**C1 / 多跳仍 `UNKNOWN`**（本批不动）。
- ⚠️ **继续有意不做**：R27（挂起）、`alert` 表（P2，**已连续多批**）。

---

## 7. 基线（**P6-T 收口实读，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| 最近一次绿 CI | run **37912090743**（`4887c32`）success；`gh run watch --exit-status` EXIT=0 |
| `pytest`（本地**有图**口径） | **1157 passed / 3 skipped / 0 failed**（= P6-S 1154 + P6-T 新增 3） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**29 路径**） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **10 条** |
| 采样口径 | 接缝 3 钉 **`temperature=0`**（P6-R，常量） |

> ⚠️ **P6 系有「有图 / 无图」两套口径**：真图三开关 `GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。
> ⚠️ 在 `Start-Process -ArgumentList` 里写 `$env:X` 会被**父壳展开成空**（P6-S 实测）。
> 本机 Neo4j / PG 若停：`docker start graphrag-neo graphrag-pg`。

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **`changes/Sprint10.5/` 已改指新编号** | `git mv` 后的目录存在且目录内编号引用已同步；工作区无残留旧编号引用（贴 `git status` / grep 结果） |
| 2 | **P5 四条出口判据逐条对账** | 贴 `delivery-plan.md:80` 的对账结果（✅/⏳ + 证据） |
| 3 | **两处过期口径已更正** | 贴 `DR&G:120` 与 `delivery-plan.md:80` 的**追加**前后文本（**只追加不重排**） |
| 4 | **契约零漂移** | `export_openapi.py --check` 零 diff（若在途改动动了契约 ⇒ 先同步契约再过这关） |
| 5 | **pytest 不降 + 护栏不倒退** | ≥ **1157 passed**；`check_seams` 仍 OK 12；readiness 仍 17/0/0；**既有断言不许为让它绿而改** |
| 6 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登集成日志 |

---

## 9. 本批不许外推

- **收口 ≠ 达标**：D4 收口不等于「知识时效 L2 端到端达标」（L2 端到端 = P6-Y）。
- **判分未完成 ⇒ C1 / 多跳无分数**：`UNKNOWN` ≠ 0，**不得**用任何旁证推 C1 达标或失守。
- **在途改动 ≠ 已验证**：未提交的 probe 脚本不是证据；要进判据必须**真跑并贴输出**。
- **本地绿 ≠ CI 绿**：以 CI 为终裁（R-10）。

---

## 10. 只在四类情况停下找用户（**同 P6-T §10**）

1. **前置不成立**（自检与 §7 基线不符且不属已知环境债）；
2. **要动裁决 / rubric / 判据口径**（**先缩范围再报告**）；
3. **边界冲突**（必须碰 §4 某条 Non-goal）；
4. **CI 红了且复核两遍仍红**（带 job 名 + 失败行 + 你自己的归因）。

---

## 11. 下一批指针（**收口时按实际结果更新，别照抄**）

> ⚠️ 队列唯一活版口径在 [`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md)，
> 编号固定为 **P6-T → P6-U → P6-V → P6-W → P6-X → P6-Y → P7-B → P8-Release**。

1. **⚠️ P6-T 判分遗留（必须传承到每一批，直到完成）**：
   86 题人工判分**顺延至项目末期**，**P8-Release「零缺口」对账前必须判完**。
   - 入口：填 `backend/data/eval/judging/judging-sheet-20261009T084532Z.md`（86 个填写位），
     或跑 `cd backend; uv run python scripts/judge_interactive.py --judged-by <署名>`（一次一题按 y/n，可中断续判）。
   - 已判 **2 题**（`judge-progress.json`：G-01 / G-02）⇒ 续判时不重判。
   - 判完 ⇒ 出数两趟：`--live --criteria c1_graph_gain --judgements <graph表> --baseline-judgements <baseline表>`
     （40 HTTP + 40 基线 LLM）+ `--live --criteria multihop_accuracy`（6 HTTP，**判分已写回 gold ⇒ 不需 `--judgements`**）。
   - 出数后**必须**执行判据 4：报告里的 `answer_texts_*` 与被判的 sheets 原文**逐题**比对，不一致的登记处置。
   - ⚠️ 判分表**必须是两个文件**；值只能真布尔（`null` 会报错，防「未判当答错」）。
   - ⚠️ 基线侧**不许全判 false**：`graph_gain` 分母 = 基线分，≤0 ⇒ 增益无定义（`metrics.py:234`）。
2. **P6-V：P5-J（M6 剩余读路径 + `agents.py` 接线 + `cost_metrics`）** ⇒ 解开 C3-a / C3-b 的 `BLOCKED`。
3. **P6-W**（DR-E4 安装验收十项脚本化）→ **P6-X**（演练留证，**独立环境 + 双人**）→ **P6-Y**（L2 端到端）→ **P7-B** → **P8-Release**（tag `v2.0.0`）。
4. **P6-R 遗留**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**。
5. **P6-S 遗留（顺延，已连续两批）**：`baseline_spec.embedding_dimension` 恒 `null`；
   后端 8002 与本地 embedding 8009 的启停**没有脚本化** ⇒ 每批开工都可能重踩「旧进程 / 服务没起」。
6. **TBD-7（成本阈值）**：与队列并行、**但要用户拍板** —— 它是 C3 能否从"趋势"变"达标"的开关。
7. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
8. **`alert` 表 + 限流超阈值联动**（P2，**已连续多批**有意不做）。
