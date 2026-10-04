# P3-B 集成日志 —— 图谱侧（Neo4j）跨 org 隔离真验 + T1 补齐 + G-9 转正

| 项 | 内容 |
|---|---|
| **批次** | P3-B（P3 的第二子批） |
| **日期** | 2026-10-04 |
| **范围** | 见 `changes/P3-B/proposal.md` §2（B1 CI 起 Neo4j / B2 图谱真用例 / B3 T1 补齐 / B4 文档） |
| **出口判据** | proposal §2：① passed 不减；② `check_startup_readiness.py` 出现 **G-9 已生效**；③ 新用例全部做过反向验证；④ CI 上真跑（不可达 ⇒ fail 不 skip） |

---

## 1. 门禁实测（**跑出来的，不是读代码得出的**）

| 门禁 | 起跑（P3-A 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | **879 passed / 3 skipped / 3 xfailed** | **888 passed / 3 skipped / 3 xfailed**（+9 = 新增 G-9 用例） |
| `check_startup_readiness.py` | 报告里**根本没有 G-9**（按 `test_g<N>_` / 模块 docstring 认护栏，此前无任何 G-9 归属测试） | 🟢 **已生效 14 条新增 `G-9 [DR-B11] 10 项`** |
| `ruff check` / `ruff format --check` | 双绿 | 双绿 |
| `check_seams.py` | 接缝 OK 10 / ERROR 0 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |

> 真图用例在**本机无 `GRAPH_REAL_NEO4J_*` 时 skip、CI 上 fail** ⇒ 上表 888 是**开了真图开关**
> （本地 `neo4j:5.26-community` 容器）跑出来的；不开开关时本文件 9 条中 5 条 skip、4 条照跑
> （静态守卫 + 三个 T1）。CI 由 job env 注入开关。

---

## 2. 改动清单

| 文件 | 改动 |
|---|---|
| `.github/workflows/ci.yml` | backend job 新增 `neo4j` service（`neo4j:5.26-community`，与 `deploy/docker-compose.yml` 同 tag；`cypher-shell` health check + `start-period 60s`）；job env 新增 `GRAPH_REAL_NEO4J_URI/USER/PASSWORD`；失败摘要补本地复现命令 |
| `backend/tests/test_guardrails_graph.py`（新增） | 模块 docstring 首行 `G-9 / DR-B11：…` ⇒ 护栏报告据此认领 G-9。9 条：静态守卫 ×1、真图 ×5、T1 ×3 |
| `docs/delivery-requirements-and-guardrails.md` | G-9 行（含「**它不覆盖什么**」）、DR-B11 行 |
| `docs/delivery-plan.md` | 「CI 的 services」行、P6 的 G-25 行（工程项已建，本体归 P3-C） |
| `changes/P3-B/proposal.md` / `tasks.md` | 本批边界与任务（Non-goals 供 `check_session_drift.py` S1 读取） |

**刻意没动**：既有打桩用例（`test_agent_fail_closed.py` 等，它们验服务层分支，与本批互补）、
契约、ADR-0003 原文、图谱 Cypher 的 org 过滤（未发现缺口，见 §5 未决 #2 的 fail-open 观察）。

---

## 3. 真图用例的**实测真值**（本地真 Neo4j，非打桩）

| 用例 | 实测观察 |
|---|---|
| `test_g9_1_…` | 同 `kg_version` 混入 B 的 Entity ⇒ `validate_kg_version_tenant_boundary(A)` = **False**（fail-closed 检出） |
| `test_g9_2_…` | 只有 A 的节点 ⇒ **True**（不误报 ⇒ 不会把合法租户拒答） |
| `test_g9_3_…` | `fetch_all_subgraph(org_id=A)` 返回 A 的节点、**不含** B 的（应用层过滤 = DR-B11 的唯一防线） |
| `test_g9_4_…` | 真图泄漏 + 只桩 LLM ⇒ `AgentService.query` 抛 **AgentTenantLeakError**（路由转 403 `KG_TENANT_LEAK`） |
| `test_g9_5_…` | **裸 Cypher 直读确实能读到 B 的节点** ⇒ 把「图谱侧无 RLS、隔离弱于 PG 侧」断言成事实（不是能力，是弱点登记） |
| `test_g9_t1_qa_logs_…` | A 的身份只见 A 的行；换成 B 的身份只见到 B 的行（裸连接 + `set_config`，绕开 conftest 脚手架） |
| `test_g9_t1_storage_key_…` | 拿 B 的 `storage_key` 以 A 的身份读 ⇒ `StorageKeyError`（前缀不符，ADR-0003 §3.5）；正向对照：自己的键读得到 |
| `test_g9_t1_documents_list_…` | B 的列表不含 A 的文档；正向对照：A 自己的列表里有它 |

**分工说明**：`documents` 的**详情** 403 由既有 `tests/test_documents.py:147` 覆盖，
`audit_log` 由 P1-C 的 `tests/test_audit.py:163` 覆盖 ⇒ **T1 四对象齐了**（基线 §169 的缺口）。

---

## 4. 反向验证（**逐条判红**，证明不是恒绿）

| 破坏 | 判红 |
|---|---|
| `ci.yml` 删掉 `neo4j` service | ✅ `test_g9_0` 红 |
| `ci.yml` 的 `NEO4J_AUTH` 口令与 job env 的 `GRAPH_REAL_NEO4J_PASSWORD` 不一致 | ✅ `test_g9_0` 红 |
| `ci.yml` 的 neo4j tag 与 `deploy/docker-compose.yml` 不一致 | ✅ 同属 `test_g9_0`（tag 比对） |
| 泄漏查询改成恒返回 0（`WHERE false`） | ✅ `test_g9_1` 红 |
| 子图**两道** org 过滤全拆 | ✅ `test_g9_3` 红 |
| `agent_fail_closed` 分支改成永不触发 | ✅ `test_g9_4` 红 |
| 把 B 节点写成 A 的 org（泄漏事实不存在） | ✅ `test_g9_5` 红 |
| 策略谓词改成 `true`（**改真源** `app/db/rls.py`） | ✅ `test_g9_t1_qa_logs` 红 |
| 存储读取去掉 org 前缀校验 | ✅ `test_g9_t1_storage_key` 红 |
| 应用层列表过滤 + RLS **双防线同时**拆 | ✅ `test_g9_t1_documents_list` 红 |

⚠️ **三个"破坏方式不对"的教训**（都值得记住，否则反向验证会假成功）：

1. **子图有两道 org 过滤**（`_QUERY_SUBGRAPH_NODE_INDEX` 索引 + `_QUERY_SUBGRAPH_BY_IDS` 取节点）：
   只拆第一道**仍绿** ⇒ 这是**纵深防御**的证据，不是用例失效。
2. **文档列表有双防线**（应用层 `org_id` 过滤 + RLS）：只拆一道**仍绿**——
   这正是 ADR-0003 §3.7「双防线并存」想要的效果。
3. **手工 `ALTER TABLE … DISABLE ROW LEVEL SECURITY` 无效**：conftest 的 autouse 夹具
   每次跑测都以 **owner** 重跑 `apply_tenant_rls`（`tests/conftest.py:237-242`）⇒ 改库会被盖掉。
   要破坏就改**真源** `app/db/rls.py::_policy_predicate()`。

---

## 5. ⚠️ 本批新发现（**登记，未在本批修**）

### 未决 #1（**高**）：`SET LOCAL` 结束后 GUC 变**空串**，`''::uuid` 直接报错

**复现**（真 PG，已实测）：

```text
Session A: SELECT set_config('app.current_org', '<uuid>', true)   -- 事务级
           SELECT … FROM qa_logs …                                -- ✅ 只看到本 org
Session 关闭（事务结束）
Session B（同一个池化连接、不设 org）:
           SELECT current_setting('app.current_org', true)  ⇒  ''   ← 不是 NULL！
           SELECT … FROM qa_logs …  ⇒  ERROR 22P02 invalid input syntax for type uuid: ""
```

**为什么重要**：`app/db/rls.py` 的注释与 ADR-0003 §3.3 的设计前提写的是
「未设 org ⇒ `current_setting(..., true)` 为 NULL ⇒ 比较为 NULL ⇒ **一行都查不到**（fail-closed）」。
而 **只要这个连接上曾经跑过一次带 org 的事务**，之后 GUC 就不再"未设"、而是被重置成 **空串**
（PostgreSQL 对自定义 GUC 的 reset 值）⇒ 结果是**报错**而不是 0 行。

**影响面（已查证的边界）**：

- `/api/v1/health` **不受影响**（`check_database()` 只跑 `SELECT 1`，不碰租户表）；
- 现有 888 条用例**全绿** ⇒ 当前没有"未绑 org 却查租户表"的被测路径；
- 但凡将来出现一条这样的路径（运维脚本 / 系统通道漏绑 / 逃生阀审计），
  它会在**第二次及以后**拿到该连接时 500——**只跑一次还测不出来**（首次连接 GUC 确实是 NULL）。

**建议修法（二选一，未裁，不在本批）**：

1. 策略谓词改成 `org_id = nullif(current_setting('app.current_org', true), '')::uuid`
   （需**新迁移**，G-26 判据 2 仍成立——它不是 `USING (true)`）；
2. 或在 `app/db/session.py` 的 `after_begin` 里，org 为 `None` 时**显式 RESET / 置 NULL**。

⇒ 归 **P3-C**（与 G-25 同批）或单独一个 hotfix 批；**在修之前，"未设 org ⇒ 0 行"这句话只对
"从未设过 GUC 的连接"成立**，文档与注释都应照此理解。

### 未决 #2（低）：若干图谱查询的 org 过滤是 **fail-open** 写法

`graphs.py:743-744 / 322-324` 等处的写法是
`($org_id IS NULL OR properties(n)['org_id'] IS NULL OR properties(n)['org_id'] = $org_id)`
⇒ **节点缺 `org_id` 属性时会被放行**。本批**未发现真缺口**（写路径 stage-1/2/3 每个 MERGE 都写 `org_id`），
故按 Non-goals 第 4 条**不动**；仅登记：若日后出现"无 org_id 的遗留节点"，过滤会静默放行。

---

## 6. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | `SET_LOCAL` 后 GUC 变空串 ⇒ `''::uuid` 报错（§5） | **高** | 归 P3-C 或 hotfix；修法见 §5 |
| 2 | 图谱查询 org 过滤的 fail-open 写法（无 `org_id` 的节点会被放行） | 低 | 登记观察，无真缺口前不动 |
| 3 | **G-25 本体**（受控种子语料 / `--live` 出真值 / 只判不退化 / 空图守卫） | 中 | 归 **P3-C**：共用的 `neo4j` service 工程项已由本批建好 |
| 4 | 本地开发仍需自起 Neo4j（本批只在 CI 与本纪要做 snapshot） | 低 | 复现命令见 §7 |

---

## 7. 复现命令

```bash
cd backend
# 真图用例需要真 Neo4j（与 deploy 同 tag）
docker run --rm -d -e NEO4J_AUTH=neo4j/ci-graph-pw-2026 -p 7687:7687 neo4j:5.26-community
export GRAPH_REAL_NEO4J_URI=bolt://localhost:7687
export GRAPH_REAL_NEO4J_USER=neo4j
export GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026

uv run pytest -q                       # 全量（888 passed）
uv run pytest -q tests/test_guardrails_graph.py   # 仅本批（9 passed）
uv run python scripts/check_startup_readiness.py  # G-9 应出现在 🟢 已生效
```
