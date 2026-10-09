# 新会话开场提示词 · P5-J（**剩余读路径切换 + `agents.py` 接线**）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。
>
> 📦 **本文件自包含**：上一批（**P5-I**）已收口（`main` = `dac5eb59`，CI run `37870995279`… 见 §7 实读；
> 四 job 全绿）。开工所需坐标、命令、基线、陷阱都在本文里。
>
> ⚠️ **本批是单角色批次（后端开发 B）**：预期**不动契约、不动前端**；若最终判定要动，
> 必须先走契约先行五步（见 §5 **D1**）。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 **P5-H §9 指针 1** 剩下的六条读路径切到**版本继承读**（ADR-0008），并把 **`agents.py` 的检索**接上
版本视野 ⇒ **M4 端到端问答**才真正吃到版本继承读，而不是只在三条已切路径上好看。

**同批必做**：更新 `docs/adr/0008-*.md` §5「未切换的读路径清单」（逐条勾掉已切的、留下仍单版本的），
并更新 `specs/m6-ontology-incremental.md` §10.1.1 的落地状态表（编号**不重排**，守 R5）。

**不做**：成本仪表盘（批次 D）、多跳推理 id 级图遍历（P5H-6）、`alert` 表（P2）。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-I/integration-log.md`** §1 / §3 / §6 | 上一批实录。**§3 是「登记点四处」**——新增端点漏登记必红；本批不新增端点，但要照它复核 |
| 2 | **`backend/app/services/kg/version_view.py`**（`build_read_view` / `resolve_read_versions`，`:140` / `:334`） | 继承读的**唯一真源**。要切的六条路径都得走它（或它的 `VersionReadView`） |
| 3 | **`backend/app/services/graphs.py:1320-1345`**（`fetch_graph_overview` 的接线范例）+ `:2373-2375`（`fetch_entity_detail` 里**明写着「接线属下一批」**的注释） | 已切路径怎么接、`fetch_entity_detail` 为什么当时没接（要传 PG 会话给 `build_read_view`） |
| 4 | **`backend/app/services/agents.py:356-360`**（`fetch_anchor_entity_ids`）+ `:594-614`（`fetch_all_subgraph`） | `agents.py` 检索侧的**两个切入点**；它现在仍按**单版本**读 |
| 5 | **`docs/adr/0008-*.md` §5「未切换的读路径清单」** | 那一份清单就是本批的**任务清单**；切一条勾一条，**不许**只改代码不改清单 |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-J/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **预期不动契约**（D1）；若判定要动 ⇒ 走完同步五步：**不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

> ⚠️ **契约描述的真源是 `backend/app/core/openapi.py`，不是 `contracts/openapi.yaml`**。

**角色隔离**：本批只 **后端开发 B**（只改 `backend/`）；ADR / spec 的更新归**架构师**段（单独提交）。

**分支**：沿用 P4 / P2-C / P5-B~P5-I —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-J / 为什么是这一刀

### 2.1 三条机械理由

1. **它是「版本继承读」这条价值链的最后一段**：P5-H 切了三条（`fetch_graph_overview` /
   `fetch_reasoning_path` / `scan_attendance_compliance`），**六条没切** ⇒ 同一个问答请求里
   概览读到新版本、实体详情却读不到 —— 这种**半继承**比全不继承更难排查。
2. **`agents.py` 检索没接视野 ⇒ M4 端到端仍未吃到**：MVP 黄金路径步骤 5 走的就是问答，
   它是**唯一还没被版本继承读覆盖的主链路**。
3. **P5-I 刚给它造出了消费者**：GUI 动作成功后会刷新图谱视图（走 `GET /graph/overview`，已切），
   但用户随后点进**实体详情 / 文档子图 / 异常归因**看到的仍是单版本 ⇒ 前后不一致**肉眼可见**。

### 2.2 为什么**不是**这两条

| 候选 | 不做的原因 |
|---|---|
| **多跳推理改 id 级图遍历**（P5H-6） | 属**读侧算法**改造，与「路径接线」不是同一刀；且它要动 `:RELATION*1..3` 的语义，判据另算 |
| **成本仪表盘 / `cost_metrics`**（批次 D） | `cost_ratio` 阈值 **TBD-7 Sprint 13** 才收敛 ⇒ 拿不到判据 |

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（**29 路径**，P5-I 起）
uv run pytest -q                                      # 本地口径基线见 §7
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

> 本机 Neo4j / PG 容器若停了：`docker start graphrag-neo graphrag-pg`。
> 真图用例三开关：`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。

---

## 4. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不动版本链的解析逻辑**：`version_view.py` 的 `resolve_read_versions` / `resolve_action_scopes` /
   `resolve_entity_selection` **主流程一行不改**（P5-H 已用真图用例钉住）。
2. **不改写侧**：`app/services/kg/incremental.py` / `correction.py` **一行不改**。
3. **不做多跳推理的 id 级图遍历**（**P5H-6** 限制本批不解）。
4. **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`**：批次 D。
5. **不新增契约端点、不新增错误码、不新增配置项**：纯读侧接线。
6. **不动前端**：本批没有新的 UI 消费方（`/ontology` 页已在 P5-I 落地，它走的是**已切**的概览）。
7. **不做 RBAC 改动**：`PROTECTED_ENDPOINTS` 现 **10 条**（P5-I 加了 `/ontology/candidates`），本批不动。
8. **不改 ADR-0008 的正文结论**：只更新 §5 那份「未切换清单」的**条目状态**（编号不重排，守 R5）。
9. **不做批量回填 / 历史数据迁移**：切了以后**旧版本数据不回溯重算**（ADR-0008 既有口径）。
10. **不做 `alert` 表 / 限流联动 / 日志脱敏**：三条都在指针清单里，属各自的批次。

---

## 5. 决策表（**本批需要你自己裁决并在 integration-log 登记**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** ⚠️**必答** | **契约会不会动** | **预期不动**（六条路径都是既有端点，响应体形状不变）。若某条切完**必须**改响应字段才能表达「跨版本」⇒ 先走契约先行五步，并在 log 写明改了什么 |
| **D2** ⚠️**必答** | 六条路径**一次全切**还是**分批切** | 建议**按调用链分批**：① `fetch_entity_detail` + `fetch_document_subgraph`（实体 / 文档视角）② `fetch_all_subgraph` + `fetch_anchor_entity_ids` ③ 考勤两条。**每批单独提交**，避免一次性摊太大（`check_session_drift` S2 会报警） |
| **D3** ⚠️**必答** | `agents.py` 怎么接 | `fetch_anchor_entity_ids`（`:358`）与 `fetch_all_subgraph`（`:612`）都要拿到 `VersionReadView`；**PG 会话从哪来**要先答（`build_read_view(db=…, session=…)` 需要两个会话 —— 这正是 `graphs.py:2373` 当年留注释说「要传 PG 会话进来，那是另一处改动」的原因） |
| **D4** ⚠️**必答** | 判据形态 | **真图用例**（不是单测桩）：校正后（改名 / 合并）再读这六条路径，断言**能读到未被影响的节点**。与 P5-H 的三条同款（5 节点改名后仍读到全部 5 个） |
| **D5** | 失败语义 | 版本链解析失败 ⇒ **显式失败**（501 / 409，沿用既有），**不**静默回落单版本 |
| **D6** | 审计 | 不新增审计点（中间件已覆盖） |
| **D7** | 成本敞口 | 预期 **¥0**（纯读侧，不调 LLM） |

---

## 6. 已完成（**前序批次，别重做**）

- ✅ **本体校正 GUI**（P5-I）：候选读端点 + `/ontology` 三动作 + 新 `kg_version` 回显 + 图谱刷新。
- ✅ **版本号定长**（P5-I0，`<stamp>-inc-<8hex>` 恒 29 字符）。
- ✅ **版本链读侧三条**（P5-H）：`fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance`
  已按**版本继承读**读图（**ADR-0008**）。
- ✅ **M6 三端点接线**（P5-G）/ **增量重算**（P5-F）/ **M5 统一脱敏**（P5-E）/ **私域出向管控**（P5-D）/ **M6 第一批**（P5-C）。
- ⚠️ **继续有意不做**：`alert` 表（P2，**已连续七批**）；成本仪表盘（批次 D）；多跳 id 级遍历（P5H-6）。

---

## 7. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1144 passed / 5 skipped / 0 failed**（run `37870995287` / commit `dac5eb59`，2026-10-09，P5-I 收口实测） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*` 三开关） | P5-I 实读 **1143 passed / 4 skipped / 2 failed** —— 2 条 failed 是**本地特有的既有环境债**（g25 两条，依赖 CI 才有的受控种子语料） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**29 路径**，P5-I 由 28 增 1） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **10 条** |
| `CONTRACT_COVERED_PATTERNS` | `frontend/src/api/client.ts:32-61`，现 **23 条** |
| `CORE_PATHS` / `operation_ids` 计数 | `backend/tests/test_openapi_contract.py`，现 **29** |
| 版本号长度 | 自 P5-I0 起 **恒 29 字符** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读 |

> ⚠️ **跑子集前先看 `changes/P5-I0/integration-log.md` §6.4**：有一条既有用例的断言是
> **全表计数**，库里有任何残留都会让它红，症状看起来像"最近的改动把它弄坏了"。

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **六条路径已切** | 真图用例：校正后读 `fetch_entity_detail` / `fetch_all_subgraph` / `fetch_anchor_entity_ids` / `fetch_document_subgraph` / `list_attendance_anomalies` / `explain_attendance_anomaly` ⇒ 能读到**未被影响的节点**（P5-H 同款断言） |
| 2 | **`agents.py` 检索接上视野** | 真图用例：校正后走问答主链路，锚点 / 子图不再是单版本 |
| 3 | **已切的三条没被打掉** | `test_version_chain_readers.py` 6 条 + `test_version_read_view.py` 13 条**全绿且断言未改** |
| 4 | **写侧判据没被打掉** | `test_kg_incremental_rebuild.py` + `test_ontology_correction_actions.py` 全绿（`use -q` 实读条数） |
| 5 | **契约零漂移** | `export_openapi.py --check` 零 diff；**29 路径不变**（D1 若判定要动 ⇒ 写明新数字） |
| 6 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0；`check_seams.py` 仍 OK 12 |
| 7 | **pytest 不降** | CI **≥ 1144 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 8 | **ADR-0008 §5 清单已更新** | 切一条勾一条；仍单版本的**逐条写明原因**（不许删条目） |
| 9 | **spec §10.1.1 已更新** | 追加本批落地事实；**编号未重排**（R5） |
| 10 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

- **六条切完 ≠ 多跳推理跨版本已通**：**P5H-6** 限制仍在。
- **六条切完 ≠ 概览统计值口径一致**：P5H-4（三个统计值仍取 PG 落库计数）**未裁**。
- **`agents.py` 接上 ≠ 检索质量提升**：它只是"读得到"，不是"排得对"。
- **读侧完整 ≠ 冷启动可用**：`cold-start` / `confirm` / `active` **仍占位**（批次 A）。
- **本批动的是租户隔离相关路径**：须带上 **ADR-0003 §4.1** 的 **T1 跨 org 越权**（G-9，
  `test_guardrails_graph.py` + `test_guardrails_rls.py`）与 **T2 并发串租户**（G-10，
  `tests/test_guardrails.py:328`）—— **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only`**；
  既有断言**不许放宽**。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败 ⇒ **以 CI 为终裁**（R-10）。

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 **后端（B）/ 架构师（ADR + spec）** 分段 Conventional Commits，跨侧改动**不得混在一个提交**。
推送后 **以 CI 为终裁**（R-10）；CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §7 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完三步自检再报告**） | 切某条路径必须改 ADR-0008 的**正文结论**（不只是清单状态） |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？（如：某条路径的接线要改 ADR 正文 ⇒ 登记为「未切 + 原因」）
3. 真不行了 —— **报告时带上**：哪份 spec / ADR 的哪一行、要加 / 改什么、为什么绕不过去、
   **你试过的替代方案**。不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **多跳推理改为 id 级图遍历**（取消 **P5H-6** 限制）。
2. **概览三个统计值口径**（P5H-4）：有了完整读侧才有消费者。
3. **`human_review` 队列读端点**（M2 的 S9.13-2）。
4. **`ontology/confirm` / `cold-start` / `active` 仍是占位**（批次 A）：
   契约不会告诉你哪些端点是占位 —— 现在只有 `backend/app/core/openapi.py` 的 tag 描述会，
   ⇒ 实现它们之前**先看那一段**。
5. **`GET /cost/dashboard` + `cost_metrics`**（m6 §3.4 验收 8 / 9）与 MVP 准入 **C3-a / C3-b**；
   `cost_ratio` 阈值 TBD-7 **Sprint 13** 收敛前拿不到判据。
6. **给 `kg_versions` 加 `parent_version` 列**（需迁移 + **G-6**）+ 裁决三列 `String(64)` 上限。
7. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续七批**有意不做）。
8. **`test_kg_build_executor.py::test_kg_build_reuses_existing_kg_version_row` 的
   `assert len(rows) == 1`**：全表计数断言容易被残留击穿 ⇒ 改成"只数与本用例有关的行"。
   **纯健壮性，建议并入任一批次顺手做，不单独开工**。
9. **`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`**：在对应批次回填，**别顺手补齐**。
10. **日志 `message` 正文的脱敏**：逐个把 `mask()` 补到写敏感值的日志语句上。
