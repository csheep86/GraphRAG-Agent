# 新会话开场提示词 · P6-V（**P5-J：M6 剩余读路径切版本继承读 + `agents.py` 接线 + `cost_metrics`**）

> 🔒 **执行模式：无人值守**（`unattended-sprint-execution` 技能；默认采纳文档建议项，
> **只有 4 类情况停下找用户**：① 前置不成立 ② 要动裁决 / rubric / 判据口径（**先缩范围再报告**）
> ③ 边界冲突（要碰 Non-goal）④ CI 红了且复核两遍仍红）。
>
> 📌 **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 5 项](../../docs/delivery-plan.md)
> —— P6-V =「P5-J：M6 剩余读路径 + `agents.py` 接线 + `cost_metrics`」，**谁来 = AI**。
>
> ⚠️ **依赖已满足**：P6-U（D4 编号改指 + P5 判据对账）已收口，CI 绿。
>
> 📦 **本文件自包含**：基线读数、纪律、遗留项都在本文里。**边界（Non-goals 10 条）由你在开工第一步写进 `changes/P6-V/proposal.md`**（drift S1 会去读它）。
>
> ⚠️ **本提示词的工量数字是 2026-10-09 机械查实的，不是照抄文档**（见 §2.1）。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 P5-H §9 指针 1 剩下的**读路径**切到**版本继承读**（ADR-0008），把 **`agents.py` 的检索**接上版本视野
（⇒ M4 端到端问答才真吃到继承读），并把 **`cost_metrics` 表 + 成本仪表盘**从 501 占位做成真实现（解开 C3-a / C3-b 的 `BLOCKED`）。

**同批必做**：回登 `docs/adr/ADR-0008-version-chain-read.md` §7 的未切换清单（切一条勾一条）
+ `specs/m6-ontology-incremental.md` §10.1.1 落地状态表（**编号不重排**，守 R-5）。

**不做**：多跳推理改 id 级图遍历（ADR-0008 §7 指针 5）、`kg_versions.parent_version` 列（指针 4）、
统计口径重裁（P5H-4）、`alert` 表（P2）、前端。

---

## 0.5 开工前必读（五份）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | [`changes/P6-U/integration-log.md`](./integration-log.md) §4 / §5 / §13 | 上一批实录；**§13 第 1 条（86 题判分遗留）必须传承** |
| 2 | **`docs/adr/ADR-0008-version-chain-read.md` §7（110-121 行）** | 那张表**就是本批任务清单**（7 行，不是 6 行，见 §2.1） |
| 3 | `backend/app/services/kg/version_view.py`（`build_read_view` / `resolve_read_versions`） | 继承读的**唯一真源**，要切的每条路径都得走它 |
| 4 | `backend/app/api/v1/routes/cost.py`（31-48 行）+ `contracts/openapi.yaml:4145` | 成本仪表盘**契约已先行**（`GET /api/v1/cost/dashboard`，响应 `CostDashboardResponse`），当前恒 501 |
| 5 | `changes/P5-J/new-session-prompt.md` | 原 P5-J 的边界与坐标（⚠️ 它 §0 写「不做成本仪表盘」，**本批队列已把它并入**，见 §2.1） |

---

## 1. 执行模式与纪律

- **角色隔离**：AI 段默认只 **后端开发 B**（只改 `backend/`）；
  改 ADR / spec / 矩阵 / `dev-doc-status` / `delivery-plan` ⇒ 归**架构师**段（**单独提交**）。
- **分支**：沿用 P4~P6-U —— **在 `main` 上直推**，不另开分支。
- **提交**：按 **后端（B）/ 架构师（文档回登）** 分段 Conventional Commits，跨侧**不得**混在一个提交。
- **推送**：⚠️ **本仓库 GitHub 推送通道不稳**（P6-T 期间连续 3 次 `curl 28` 443 超时；P6-U 一次成功）。
  推送失败 ⇒ **重试一次**，仍失败就**把完整命令交给用户**，**不许**改 remote / 绕道。
- **终裁**：以 CI 为终裁（R-10）；CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。
- **回登纪律**（P5-B §5.3 / P6-U §12）：**停止为"多记一个 run id"而提交** —— 回登 ⇒ 新 commit ⇒ 新 run ⇒ 无限递归。
  下一个 run 应由**实质改动**触发。

---

## 2. 为什么是 P6-V / 为什么不是这几条

| 候选 | 判断 |
|---|---|
| **P5-J 读路径 + cost_metrics** ✅ | 队列第 5 项，顺序在 P6-U 之后；**P5-J 提示词已写好却一直未开工**（2026-10-09 排序复核时被降级让位给 P6-Q / D4） |
| P6-W（DR-E4 安装验收十项脚本化） | 队列第 6 项，顺序在后 |
| **P6-T 判分 86 题** | **人是瓶颈**，顺延至项目末期 ⇒ **不在本批**，但**必须传承**（§11 第 1 条） |
| L2 端到端 / 演练留证 | P6-X / P6-Y，需**独立环境 + 双人** |
| R27 / R30 / `alert` 表 | 挂起 / 已连续多批有意不做 |

### 2.1 ⚠️ 工量已机械查实（**别照乐观口径外推**）

| 项 | 查实结果（2026-10-09 实读） | 出处 |
|---|---|---|
| 未切换读路径**条数** | **7 条**（`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` / `list_attendance_anomalies`+`explain_attendance_anomaly` / `fetch_document_subgraph` / `agents.py` 检索链路 / `documents.py` 图谱读）—— ⚠️ **P5-J 提示词 §0 写"六条"，ADR §7 表是 7 行**，以 ADR 表为准 | `docs/adr/ADR-0008-version-chain-read.md:112-121` |
| `cost_metrics` 表 | ❌ **不存在**（`backend/app/db/models.py` 无 Cost 类）⇒ 需**建表 + 迁移 + 落点** | 实读 `models.py` |
| `GET /cost/dashboard` | 🟡 **端点与契约已存在但恒 501** ⇒ 实现**不需要动契约**（契约先行已完成） | `routes/cost.py:31-48`、`openapi.yaml:4145` |
| 迁移目录 | `backend/migrations/versions`（**不是** `alembic/versions`） | 实读目录 |
| P5-J 原边界 | 「**不做**成本仪表盘（批次 D）」⇒ **本批队列把成本并入**，工量**比 P5-J 原计划大** | `changes/P5-J/new-session-prompt.md` §0 |

> ⇒ **如果你判断读路径 7 条 + cost 全量在一批内摊太大**，按 §10 第 3 类**先缩范围**（例如本批只做
> `agents.py` 检索接线 + cost，其余读路径留 P6-V2），并在 `proposal.md` 登记后报告 —— **不许硬撑着做完再报**。

---

## 3. 开工自检（**先跑，再动手**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（29 路径）
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点绿（见 §7）
git status --short                                    # 期望：干净
docker ps --format '{{.Names}}\t{{.Status}}'          # graphrag-neo / graphrag-pg 须 Up
```

⚠️ 若 `graphrag-neo` / `graphrag-pg` 不是 Up：`docker start graphrag-neo graphrag-pg`。

---

## 4. Non-goals（**开工第一步写进 `changes/P6-V/proposal.md`，登记 10 条**）

至少包含这 6 条硬约束（其余按实际作业面补齐到 10 条）：

1. **AI 不得代填任何 `correct` 值**（A3 / §9.3 第 1 条）——**永久红线**。
2. **不改 rubric / 题集**（`rubric-v2` / `controlled-qset-v4` / `gold-multihop-v1` 题目一字不改）。
3. **不动 C2-a / C2-b / C2-c 口径**（三条已出数，A8 裁决）。
4. **不动前端**。
5. **不动契约**（成本端点契约**已先行** ⇒ 实现不得增删字段；若必须动 ⇒ 走契约先行五步，属 §10 第 2 类**先停下升级**）。
6. **不新裁决 ADR-0008 §7 的两个遗留语义**（统计口径 P5H-4 / 版本号长度 / `parent_version` 列）—— 只登记传承。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围**再报告（带「哪份文档哪一行 / 要改什么 / 为什么绕不过去 / 试过的替代方案」）。

---

## 5. 决策表（**开工时按实际作业面填并登记**）

| # | 决策 | 现状 / 提示 |
|---|---|---|
| **V1** ⚠️ | 7 条读路径**全切**还是**分批** | 先按 §2.1 估算；摊太大 ⇒ 缩范围并登记（§10 第 3 类） |
| **V2** | `agents.py` 检索接线后，**M4 端到端**要不要出数 | 出数依赖 live LLM ⇒ **判据不进 CI**（沿用 D6）；本地出数须贴真跑输出 |
| **V3** | `cost_metrics` 的落点 | 表 + 迁移 + `routes/cost.py` 501 → 真实现；**预留字段一律不进契约**（`export_openapi.py --check` 零 diff 为判据） |
| **V4** ⚠️ | C3-a / C3-b 能否由 `BLOCKED` 转 `MEASURED` | 需 `EVAL_SINGLE_DOC_TOKEN_CEILING` **阈值校准**（TBD-7，**要用户拍板**）⇒ 未拍板前**只解 BLOCKED，不宣称达标** |
| **V5** | ADR / spec 回登 | 切一条勾一条（ADR §7 表）+ `specs/m6` §10.1.1 状态表，**编号不重排**（R-5） |

---

## 6. 已完成 / 已查实（**前序批次，别重做**）

- ✅ **P6-U（2026-10-09）**：`changes/Sprint10.5` → `changes/P6-U` 改指 + 全仓 44 行引用同步；
  P5 四判据对账（①✅ ②✅ ③🟡 ④✅）；DR-D4 / DR-D7 / `dev-doc-status:68` / `delivery-plan:80,198` 过期口径已更正。
- ✅ **D4 代码**已于 2026-10-07 由 **P5-B** 收口（J3 前端虚线 + 图谱恢复 + G3 回归）。
- ✅ **三条读路径已切**（概览 / 多跳推理 / 合规），判据在 `tests/test_version_read_view.py`。
- ✅ 成本仪表盘**契约先行**已完成（端点 + 响应模型已在 `openapi.yaml`）。
- ⚠️ **继续有意不做**：R27（挂起）、`alert` 表（P2，**已连续多批**）、多跳 id 级遍历（ADR §7 指针 5）。

---

## 7. 基线（**P6-U 收口实读，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| 最近一次绿 CI | run **37914433145**（`4c93974`）success；`gh run watch --exit-status` **EXIT=0** |
| `pytest`（本地**有图**口径） | **1157 passed / 3 skipped / 0 failed**（78.03s） |
| `ruff` | check **All checks passed**；format **274 files already formatted** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**29 路径**） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **10 条** |
| 采样口径 | 接缝 3 钉 **`temperature=0`**（P6-R，常量） |

> ⚠️ **P6 系有「有图 / 无图」两套口径**：真图三开关 `GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。
> ⚠️ 在 `Start-Process -ArgumentList` 里写 `$env:X` 会被**父壳展开成空**（P6-S 实测）——直接在当前 shell 里赋值。

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **读路径切换有真图用例** | 每条切完的路径补 1 条真图用例（照 ADR §8 现三条的写法）；`pytest` 不降 |
| 2 | **ADR §7 清单已回登** | 贴 `ADR-0008-version-chain-read.md` §7 表的前后文本（切一条勾一条，**不许只改代码不改清单**） |
| 3 | **`agents.py` 检索吃到继承读** | 贴切换前/后的读取口径证据（`build_read_view` 调用点 + 一条真图问答）；**M4 端到端**若出数须贴真实输出 |
| 4 | **`cost_metrics` 表 + 迁移** | 贴建表代码行 + 迁移文件；**迁移等价性**由 G-6 判 |
| 5 | **成本端点 501 → 真实现** | 贴 `GET /cost/dashboard` 的真实响应（本地真跑），且 `export_openapi.py --check` **零 diff** |
| 6 | **护栏不倒退** | `pytest` ≥ **1157 passed**；`check_seams` 仍 OK 12；readiness 仍 17/0/0；**既有断言不许为让它绿而改** |
| 7 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登集成日志 |

---

## 9. 本批不许外推

- **接线 ≠ 端到端达标**：`agents.py` 接上继承读不等于 M4 端到端修复（要真跑出数才算）。
- **成本端点实现 ≠ C3 达标**：阈值 **TBD-7 未拍板** ⇒ 只能解 `BLOCKED`，**不得**宣称 C3-a / C3-b 达标。
- **本地绿 ≠ CI 绿**：以 CI 为终裁（R-10）。
- **未跑的判据不是证据**：单测通过 ≠ 继承读在真图上正确。

---

## 10. 只在四类情况停下找用户（**同 P6-U §10**）

1. **前置不成立**（自检与 §7 基线不符且不属已知环境债）；
2. **要动裁决 / rubric / 判据口径**（**先缩范围再报告**）—— 典型触发：V4 的 TBD-7 阈值、ADR §7 的两个遗留语义；
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
2. **⚠️ `changes/P6-U/10-gate-report.md` §5 的 A/B/C 三条出路仍未裁决**（2026-10-01 起挂起）⇒
   要继续推进 L2 ②③ 本体（as-of 前端入口 / 端到端）前**必须请用户裁决**。
3. **P6-W**（DR-E4 安装验收十项脚本化）→ **P6-X**（演练留证，**独立环境 + 双人**）→ **P6-Y**（**L2 端到端**）→ **P7-B** → **P8-Release**（tag `v2.0.0`）。
4. **D7 / R22 剩余缺口**：`question` 只参与**候选内重排**，候选集仍是结构性窗口 ⇒ 方向②实体链接召回 / ③向量召回 + 「扩候选集」仍待排期。
5. **P6-R 遗留**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**。
6. **P6-S 遗留（顺延，已连续三批）**：`baseline_spec.embedding_dimension` 恒 `null`；后端 8002 与本地 embedding 8009 的启停**没有脚本化**。
7. **TBD-7（成本阈值）**：与队列并行、**但要用户拍板** —— 它是 C3 能否从"趋势"变"达标"的开关（本批 V4）。
8. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
9. **`alert` 表 + 限流超阈值联动**（P2，**已连续多批**有意不做）。
