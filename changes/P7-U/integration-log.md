# P7-U 集成日志

> **日期**：2026-10-15 ｜ **状态**：判据 1-5 **全部达成**
> **上游**：`P6-T` §3 P6-T-D4 / §4【阻塞 P8-Release】、`P7-G` §1、`P7-S` §6、`P7-K` §7.4 / §10
> **一句话**：契约写了「指定图谱版本」，实现只校验不采纳 —— 修好了，真机闭环。

---

## 0. 这批修的是什么（一句话）

`AgentQueryRequest.kg_version` 的契约语义是「**指定**图谱版本，**缺省**取最新 active」。
旧实现：路由层**校验**它是否 active，service 层**却自行 resolve 并覆盖** ⇒ **传了等于没传**。

⇒ 评测**锁不住版本**，这正是 P6-T-D4 被登记为【阻塞 P8-Release】的直接原因。

---

## 1. 起点：三处代码，机械事实（不是推测）

| 位置 | 代码 | 作用 |
|---|---|---|
| `app/api/v1/routes/agent.py:60-61` | `if payload.kg_version is not None: await _assert_active_kg_version(...)` | **只校验** |
| `app/api/v1/routes/agent.py:94-122` | 查 `fetch_kg_version_status(requested)`，非 `active` 抛 409 | 校验走 **Neo4j** |
| `app/services/agents.py:271-282` | `fetch_active_kg_version(org_id=org_id, db=db)` ⇒ `version = kg_version.version` | **无视 `request.kg_version`**（走 **PG**） |

**契约原文**（`app/schemas/agent.py:49-56`）：

> 「指定图谱版本，缺省取最新 active 版本。若指定版本的 status ≠ active
> （writing / failed / superseded），一律返回 409 KG_VERSION_NOT_ACTIVE，
> 严禁静默降级（ADR-0002 §3.2）」

⇒ 实现与契约不符 = **确证缺陷**（不是"有意保留字段"）。

---

## 2. 改了什么（逐条：文件 / 行）

| # | 文件 | 位置 | 改动 |
|---|---|---|---|
| 1 | `backend/app/services/agents.py` | `_execute_query` 第 269-303 行 | `version` 解析改为**显式指定优先**：`request.kg_version` 非空 ⇒ 直接用它；否则走原 `fetch_active_kg_version` 链路 |
| 2 | `backend/tests/test_agent_citations.py` | 文件末尾 +74 行 | 新增 2 条用例（采纳 / 缺省回退） |

**未指定时的代码**（`try/except GraphUnavailableError` + 501 语义）**逐字未动**——
只有缩进随 `else:` 变化。

**安全边界三条**（已写进代码注释，逐条可查）：

1. `agents.py:319` 的 `validate_kg_version_tenant_boundary(kg_version=version, ...)`
   用的是**同一个** `version` ⇒ 指定版本照样过跨租户 fail-closed（ADR-0003 §4）；
2. 未指定时故障语义（501 `AgentUnavailableError`）**逐字不变**；
3. 契约字段不动 ⇒ **不触发「改 schema ⇒ 停下报告」**。

---

## 3. 反向验证（纪律 **R-9「恒绿即失效」**）

| 拆掉的东西 | 变红的用例 | 接回后 |
|---|---|---|
| `_execute_query` 里「显式指定优先」那个 `if` 支 | **1 条**：`test_query_adopts_explicit_kg_version`（`response.kg_version` 退回 `v-test`） | 全绿（28 passed） |

⇒ 新用例**真在拦**，不是"补个断言图个绿"。

---

## 4. 真机验证：**P6-T-D4 闭环**（本批最关键的一节）

环境：本机 `backend/.env` ⇒ PG 库 `graphrag`（**正是会触发 D4 的那个库**）；
Neo4j 同一实例。命令：进程内直调 `AgentService.query`，从 P7-S 的观测出口取注入证据数。

| 条件 | **实际用的 `kg_version`** | **注入证据 chunk 数** |
|---|---|---|
| **A 不指定 `kg_version`** | `20261012T064951Z-inc-569555ad` | **0** ← **复现 D4** |
| **B 指定 `attendance-demo-v1`** | **`attendance-demo-v1`** ✅ | **13** |

背景读数（同时取的，¥0）：

| 版本 | Neo4j `:Chunk` 数 | Neo4j status |
|---|---|---|
| `attendance-demo-v1` | **213** | **`active`** ✅ |
| `20261012T064951Z-inc-569555ad` | **0** | — |

⇒ **三条结论，逐条有读数**：

1. **修复有效**：指定 `attendance-demo-v1` 后，链路**真的**用了它（`chunks` 从 0 → 13）；
2. **D4 根因确认**：不指定时落到那个 **0 chunk** 的增量版本 ⇒ 检索 0 证据 ⇒ 拒答。
   这就是 P6-T-D4 说的「显式带 `attendance-demo-v1`，后端仍解析成
   `20261012T064951Z-inc-569555ad`」；
3. **HTTP 路径也能用**：`attendance-demo-v1` 在 Neo4j 的 status = **`active`**
   ⇒ 路由层 `_assert_active_kg_version` 会放行 ⇒ 端到端（经 HTTP）同样成立。

### 4.1 ⚠️ 本节的边界（不许外推）

- **LLM 侧超时**（`langchain_openai` `OpenAITimeoutError` ⇒ 3 次重试后
  `AgentUnavailableError`）。这是**供应商侧**问题，与版本解析无关；
  读数取自**注入证据出口**（位于 LLM 调用**之前**）⇒ 不受影响。
  但 ⇒ **「指定版本后能出终答」这一步本轮未验**（缺的是 LLM，不是版本）。
- `chunks=13` 与 P7-S §5 记录的「每题 32 条」不同。**两处题目不同**
  （P7-S 用的是那 3 道探针题），且 32 = `_EVIDENCE_CHUNK_LIMIT` 上限。
  本批**未**去对齐这个差异（不属本批范围），如实登记。
- **`graphrag` 与 `graphrag_eval` 两个库的 ready 状态不同**（P7-S §6 已登记），
  本批**不动数据**、不去"把 inc 版本置非 ready"——修的是根，不是迁就。

---

## 5. 出口判据对照

| # | 判据 | 结果 |
|---|---|---|
| 1 | 显式传 `kg_version` ⇒ 全链路用它 | ✅ 真机：`kg=attendance-demo-v1`、`chunks=13`；单测：`response.kg_version == "v-specified"` + 租户边界校验收到的也是它 |
| 2 | 未指定时行为逐字不变 | ✅ 单测 `test_query_falls_back_to_active_when_kg_version_omitted`；真机 A 组复现旧行为 |
| 3 | 单测经反向验证 | ✅ 拆分支 ⇒ 1 红（§3） |
| 4 | 三件套 + 全量 pytest 不降 | ✅ ruff / format / seams（ERROR 0、WARN 0、OK 12）；**1305 → 1307 passed**（46 skipped） |
| 5 | CI 四 job 全绿 | 见 §6 |

---

## 6. 环境变更登记（**过程中的实际状态变化，如实记**）

开工时本机主栈**全部已停**（`graphrag-pg` / `graphrag-neo` / 后端 8100 = `Exited (255)`），
只剩 drill 栈 ⇒ 首轮 `pytest` 直接死在 `conftest.py:184`（`ensure_database("graphrag_test")`
连不上 5432）。

处置：`docker start graphrag-pg graphrag-neo`（**启动已存在的容器，未新建、未删除、未改数据**），
恢复后测试与真机验证均可跑。**后端 8100 未启动**（本批不需要：单测走 mock、真机走进程内直调）。

⇒ proposal §6 中「真机端到端做不了」这一条**在环境恢复后已推翻**，本节即为更新的实际状态。

---

## 7. 遗留（**交给后续，不自行扩大范围**）

| # | 事项 | 归属 |
|---|---|---|
| 1 | 「指定版本 ⇒ 出终答」的 LLM 段未验（供应商超时） | 环境恢复后随手补一条即可 |
| 2 | `chunks` 13 vs 32 的差异未对齐 | 不属本批 |
| 3 | ~~**service 层要不要也校验 active**~~ ⇒ **已机械核实，保持现状**（见 §8） | ✅ **已闭环**，无需你裁 |
| 4 | 生成侧漂移（P7-S §5 × P7-K §10.2） | 等你裁路 A / 路 B |

### 7.1 本批**解锁**了什么

```
根① 版本锁不住  ←── ✅ 本批修完（真机闭环）
      ⇒ P6-T-D4【阻塞 P8-Release】的**直接成因**已消除
      ⇒ 评测从此可显式锁 attendance-demo-v1，不再受"哪个库的哪个版本 ready"摆布
      ⇒ P7-K 第 2 段（出口判据 1 / 4）**前提具备了**

根② 生成侧漂移  ←── 仍在（P7-S §5 = 0.000；P7-K §10.2 = 13/40）
      ⇒ 即使版本锁住，答案仍会漂 ⇒ P7-K 出口判据 1 仍不成立
      ⇒ **这根才是 P8-Release 的真门槛**，等你裁
```

---

## 8. 「信任路由层」这个前提是**核实**过的，不是推断（2026-10-15 补）

proposal §5 把「service 层不重复校验 active」列为一个**需要你裁决的取舍**，
依据是「`agent.py:60-61` 是唯一 HTTP 入口」。那是读代码得出的**推断**；
本节把它换成**机械读数**。

### 8.1 全仓调用点清点

| 类别 | `AgentService.instance().query` 调用点 | 传 `kg_version` 吗 |
|---|---|---|
| **生产代码** | **仅 1 处**：`app/api/v1/routes/agent.py:65` | 有 → 其前 **第 60-61 行必然先过 `_assert_active_kg_version`** ✅ |
| 脚本 | `scripts/repro_agent_query.py:214` | **不传**（`:183` 只构造 `question` / `scope`）⇒ 走 active 分支 |
| 脚本 | `scripts/check_injected_evidence.py:130`（P7-S 探针） | **不传** ⇒ 走 active 分支 |
| 测试 | 19 处（mock 链） | 除本批新增用例外，均不传 |

### 8.2 结论

⇒ **当前代码库里，没有任何调用方绕过路由直接给 `AgentService.query` 传 `kg_version`**
⇒ 「信任路由层」在生产路径上**成立**，service 层不重复校验**保持现状**，
   proposal §5 的取舍项就此**关闭**，不再需要你裁决。

### 8.3 ⚠️ 但留下一个边界（**登记，不处置**）

`scripts/` 下的脚本**不受**路由校验保护。今天它们都不传 `kg_version`，所以安全；
**将来若有脚本要指定版本**（评测要锁版本 ⇒ 正是 P7-U 想做的事），它就绕过了
`_assert_active_kg_version`。

⇒ 若后续真要这么用，**应优先走 HTTP**（`eval_controlled_qset.py` 已是这个口径：
它读的是 `response.get("kg_version")`），或在脚本里显式调
`fetch_kg_version_status` 自查。**本批不改**（不属本批范围）。
