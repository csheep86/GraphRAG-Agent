# P7-U · 评测版本锁定（显式 `kg_version` 必须被采纳）

> **日期**：2026-10-15 ｜ **批次性质**：极小批次（只改一处）
> **上游**：`P6-T` §3 P6-T-D4 / §4【阻塞 P8-Release】、`P7-G` §1 `ghost_version`、
> `P7-S` §6（分库发现）、`P7-K` §7.4 / §10
> **一句话**：契约写了「指定图谱版本」，实现却只校验不采纳 ⇒ 评测锁不住版本。

---

## 1. 起点：缺陷已经确证，不是推测

### 1.1 契约语义（**实现与它不符**）

`backend/app/schemas/agent.py:49-56`：

```python
kg_version: str | None = Field(
    default=None,
    description=(
        "指定图谱版本，缺省取最新 active 版本。"
        "若指定版本的 status ≠ active（writing / failed / superseded），"
        "一律返回 409 KG_VERSION_NOT_ACTIVE，严禁静默降级（ADR-0002 §3.2）"
    ),
)
```

响应侧 `schemas/agent.py:281`：
`kg_version: str = Field(description="本次检索实际使用的图谱版本（必为 active）")`

⇒ **「指定」= 采纳**；「缺省」才取 active。响应要回**实际用的**那个。

### 1.2 实现链路（三处代码，机械事实）

| 位置 | 代码 | 作用 |
|---|---|---|
| `backend/app/api/v1/routes/agent.py:60-61` | `if payload.kg_version is not None: await _assert_active_kg_version(...)` | **只校验** |
| `backend/app/api/v1/routes/agent.py:94-122` | `_assert_active_kg_version` 查 `fetch_kg_version_status(requested)`，非 `active` 抛 409 | 校验走 **Neo4j** |
| `backend/app/services/agents.py:271-282` | `kg_version = GraphService.instance().fetch_active_kg_version(org_id=org_id, db=db)` ⇒ `version = kg_version.version` | **无视 `request.kg_version`**，自己 resolve（走 **PG**） |

⇒ **传入的版本被校验、被丢弃、然后被系统自己 resolve 的结果覆盖。**

### 1.3 它在别处已经造成的后果（不是本批新编的）

- **P6-T §3 P6-T-D4**：「请求显式带 `kg_version=attendance-demo-v1`，后端仍解析成
  `20261012T064951Z-inc-569555ad`」⇒ 检索 0 证据、全拒答。
  P6-T §4 把它登记为 **【新增 · 阻塞 P8-Release】**。
- **P7-K §7.4 第 3 条**：本打算「在新 PG 上把那个多出来的 inc 版本置非 ready」来绕开它，
  但那里是**改数据**去迁就缺陷，且命中「无现成脚本 ⇒ 动手前先报告」。

⇒ 本批修的是**根**，不动数据。

---

## 2. 范围（**只做这一件事**）

**改 `backend/app/services/agents.py` 第 269-282 行**：`_execute_query` 解析 `version` 时，
**请求显式指定了 `kg_version` 就采纳它**；未指定才走 `fetch_active_kg_version`。

```python
# 1) kg_version：**显式指定优先**（路由层已校验 active），缺省才取 active
requested = request.kg_version
if requested:
    version = requested
else:
    ...  # 原链路：fetch_active_kg_version + AgentUnavailableError 语义不变
```

**为什么安全**（三条，逐条可查）：

1. **租户边界校验不跳过**：`agents.py:319` 的
   `validate_kg_version_tenant_boundary(kg_version=version, ...)` 用的是同一个 `version`
   ⇒ 指定版本照样过 fail-closed 校验（ADR-0003 §4）。
2. **故障语义不变**：指定版本时不再有 `fetch_active_kg_version` 调用 ⇒ 也不会把
   「Neo4j 不可用」混进来；未指定时行为**逐字不变**。
3. **契约零改动**：`AgentQueryRequest` / `AgentQueryResponse` 字段都不动
   ⇒ **不触发「改 schema ⇒ 停下报告」**。响应 `kg_version` 从「系统 resolve 的」
   变成「调用方指定的（已是 active）」——这正是契约 `description` 写的语义。

---

## 3. 非目标（**越界即停**）

| 不做 | 原因 |
|---|---|
| 不改 rubric-v2 / 判分口径 | 那是 P7-R §7.3 的岔路，等你裁 |
| 不修检索排序 | P7-S §5 已实测注入序列稳定（1.000），无证据指向它 |
| **不动任何数据**（不把 inc 版本置非 ready） | 本批修根因，不做数据层的 workaround |
| 不解 P7-S §7 的「路 A / 路 B」 | 本批只解**版本锁定**，生成侧漂移是另一条债 |
| 不引入「多版本并存」语义 | 只在「指定了就用指定的」这一层修，不重做版本体系 |
| 不在 service 层重复做 active 校验 | 会改变 409 / 501 的故障语义；路由层已校验（见 §5 权衡） |

---

## 4. 出口判据

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | 显式传 `kg_version` ⇒ 全链路（子图 / 证据 / 响应 `kg_version`）**用的是它**，不是 resolve 出来的 | 单测：`_fetch_subgraph_for_question` 收到的 `kg_version` == 传入值 |
| 2 | **未指定时行为逐字不变** | 原有用例全绿（含 `test_agent_fail_closed.py` 的 mock 链） |
| 3 | 单测经**反向验证** | 拆掉分支 ⇒ 判据 1 的用例**必须红**（R-9） |
| 4 | 三件套 + 全量 pytest 不降 | `ruff check` / `ruff format --check` / `check_seams` / `pytest -q`（基线 **1305 passed**） |
| 5 | CI 四 job 全绿 | 推送后 `gh run view` |

### 4.1 真机实测（**本批不承诺，见 §6**）

判据 1-4 全部**不依赖** Neo4j / PG（单测走 mock）⇒ 环境不可用也能交付。
真机端到端（在真环境上显式传 `attendance-demo-v1` 出数）**需要栈在跑**，见 §6。

---

## 5. 权衡（需要你知道的一个取舍）

**service 层不再自己校验 active，而是信任路由层已校验。**

- 依据：`agent.py:60-61` 是 `AgentQueryRequest.kg_version` 的**唯一 HTTP 入口**，
  且 `payload.kg_version is not None` 时**必然**先过 `_assert_active_kg_version`。
- 代价：若有**内部调用**绕过路由直接调 `AgentService.query(kg_version=<非 active>)`，
  就会用到非 active 版本。
- 缓解：`validate_kg_version_tenant_boundary` 仍在，跨租户仍 fail-closed。
- 若你要求 service 层也校验 ⇒ 属**扩大范围**，本批停下报告（情况 2）。

---

## 6. 现状：真机环境不可用（**必须登记，不掩盖**）

> ⚠️ **同日更新**：环境已恢复（`docker start graphrag-pg graphrag-neo`，启动已存在容器），
> 真机闭环**已跑通** —— 见 `integration-log.md` §4 / §6。
> 本节以下保留为**开工时**的实况，作为「当时为什么一度做不了」的记录。

开工时实测（`docker ps` + 端口探测）：

| 服务 | 昨天（P7-S 实测时） | 现在 |
|---|---|---|
| `graphrag-pg`（5432） | 在跑 | **已停** |
| `graphrag-neo`（7687） | 在跑 | **已停** |
| 后端 8100 | 在跑 | **已停** |
| drill 栈（8000 / 3000 / 7688） | 在跑 | 在跑 |

⇒ 本批的**真机端到端验证做不了**，且这不是"我没跑"，是环境不在。
判据 1-4 不依赖环境 ⇒ 仍可完整交付；判据 5（CI）也不需要本地栈。

**留待后续**：环境恢复后，用一条命令验证「显式传 `attendance-demo-v1` 出数」，
那才是 P6-T-D4 的闭环（解锁 P7-K 第 2 段）。

---

## 7. 待裁决（**不由本批决定**）

- 无。本批是纯缺陷修复，不改口径、不引入新判据。

---

## 8. 为什么它是"第 1 步"（与后续的关系）

```
根① 版本锁不住  ←── 本批（P7-U）
      └ 修好后：评测可显式锁 attendance-demo-v1，不再受"哪个版本是 ready"摆布
                ⇒ 解开 P6-T-D4【阻塞 P8-Release】
                ⇒ P7-K 第 2 段（出口判据 1 / 4）才有得跑

根② 生成侧漂移（P7-S §5 实测 0.000 × P7-K §10.2 实测 13/40）
      └ 与根①独立：即使版本锁住，答案仍会漂 ⇒ P7-K 出口判据 1 仍不成立
      └ 这条等你裁路 A / 路 B
```

⇒ **两根都要解，但根①是唯一一个「根因明确、不动口径、可独立交付」的**，故排在最前。
