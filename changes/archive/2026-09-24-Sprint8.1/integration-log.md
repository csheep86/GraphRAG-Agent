# Sprint 8.1 批次 A 实测记录（M5 审计最小闭环）

> 每个结论都要能复跑，记录"怎么测的"。
> **花钱纪律**：每花一笔钱都写清「命令 + token 数 + 估算金额」，禁止事后补记大概数。
> **境门口径**：接缝门禁 = **默认档 + ERROR = 0**；本批次不动接缝、不 bump `app_version`。

---

## 1. T0 基线（2026-09-24，全部为命令输出）

| 项 | 实测 |
|---|---|
| 分支 / 基线 | `feature/sprint-8`（与 `origin` 同步），开工前 `git status` clean |
| `check_seams.py` | **ERROR 0 / WARN 2 / OK 8**（2 条 WARN = 未到期的接缝 6），`app_version 1.3.0` |
| `uv run pytest -q` | **368 passed** |
| `export_openapi.py --check` | OK（零漂移） |
| `npm run gen:api` | 跑后 `git status` clean（无 diff） |
| `models.py` 表数 | **7 张**（无 `audit_log` / `qa_logs`） |
| Neo4j | `docker ps` → `neo4j Up 20 hours`（**本轮无需 `docker start`**） |
| 后端凭据（只打长度） | `LLM_API_KEY len=35`、`MINERU_TOKEN len=51`、`NEO4J_PASSWORD len=8`、`STORE_BACKEND len=5` |
| PG 真源（SQLite 开发态替身） | `documents=7 completed`、`kg_versions=2 ready`（`v-s71a-fe1c4dc3` 2000 实体 / 819 关系；`v-3e381d36` 6/1）、`affiliation_tasks=3 completed`、疑点 `open 23 / confirmed 6 / dismissed 1` |
| 预算 | 用户给定：充值余额 **¥38.61**、累计消费 **¥31.38**（2026-09-24 截图） |

盘点脚本（零成本、可复跑）：`cd backend && uv run python ../changes/Sprint8.1/inspect_state.py`

---

## 2. 事前核实（§0）

| 项 | 结论 | 依据 |
|---|---|---|
| 字段清单 | `audit_log` 11 字段逐字照 `specs/m5-permission-audit.md` §4.4；`qa_logs` 10 字段逐字照 `specs/m3-graphqa-citation.md` §4.3；**未自创字段** | 逐行对读，未写代码前完成 |
| 主键口径 | 用 **UUID**（A9），**不用** spec 的 `BIGSERIAL`；差异登记 ADR-0003 | `models.py` 既有模板（`Uuid` 主键 + `CheckConstraint` + `org_id` 打头索引） |
| trace_id 链路 | 由 `core/middleware.py` 的 `TraceIdMiddleware` 生成 / 回显 / reset | 读码；**结论**：审计中间件必须挂在它**之内** |
| 挂载顺序 | Starlette `add_middleware` 是「后加者在外层」⇒ 审计**先 add** | `main.py` 实改 + 真机日志 `audit.list`  narration 印证 |
| `router.py` 注释 | 原写「`/audit*` 留草案态、禁止提前注册」——**已改写**，否则与注册动作自相矛盾 | `router.py` docstring |
| 占位页现状 | `src/app/audit/page.tsx` 是占位骨架；已整体重写为真实页面（UI 骨架全部重做，非"覆盖一半"） | `frontend/src/app/audit/page.tsx` |

---

## 3. 契约（§1，先行）

```
cd backend && uv run python scripts/export_openapi.py     # 重导
cd backend && uv run python scripts/export_openapi.py --check
cd frontend && npm run gen:api
```

- 契约路径 **14 → 16**（新增 `GET /api/v1/audit`、`GET /api/v1/audit/trace/{trace_id}`）；
- `git diff --stat contracts/openapi.yaml` = **368 insertions, 0 deletions** ⇒ 既有 14 条路径**一行未动**；
- 顺手纠一处**双向真值**：`AuditLogItem.resource` 描述原写「路径模板或 `<method> <path>`」，与实际实现（`<METHOD> <实际请求路径>`，不含 query string）不一致，已改描述并重导契约；
- `test_openapi_contract.py` 两处硬编码同步更新并留年代注释：路径集合 14→16、`operation_id` 计数 14→**16**。

---

## 4. 两张表（§2）

`backend/app/db/models.py` 新增 `AuditLog` / `QaLog`：

- 表名逐字 = spec（`audit_log` / `qa_logs`），字段逐字 = spec §4.4 / §4.3；
- **既有 7 张表一行未改**（`git diff` 确认改动集只有新增块）；
- 复合索引均以 `org_id` 打头（ADR-0003 §3.1）；`status` 带 `CheckConstraint('success','failure')`；
- 无 Alembic，靠 `init_db()` 的 `create_all`（真机已验证：服务启动后新表出现，见 §8）。

---

## 5. 中间件（§3）

`backend/app/core/middleware.py` 新增 `AuditMiddleware`（纯 ASGI，不用 `BaseHTTPMiddleware`）：

- **allowlist**：`APP_ENV` 无关，`/api/v1/*` 且非 `/health`；`.env/api_prefix` 决定前缀；
- **身份**：复用接缝 1 `LocalAuthProvider.authenticate()` 解析（`X-Org-Id` / `X-Actor-Id` / Bearer）——**不另起口径**（A6）；取不到身份（401）**不写**（`org_id` 是隔离键，不拿默认 org 顶替），命中 `audit_log_skipped_no_identity` 日志；
- **`action`**：路由登记名映射（如 `document.upload` / `agent.query` / `affiliation.review`），未登记回落 `http.<method>.<path>` 并 WARNING（A2）；
- **`detail`**：只写 `{status_code, method, path}`（A5，**无响应体原文**）；
- **失败处理**：`try/except Exception` 吞掉并记 `audit_log_write_failed`（proposal 风险 2：审计缺陷不得变全站 500）；
- **`status`**：`<400` 记 `success`，其余（含 4xx 与 5xx）记 `failure`。

---

## 6. `qa_logs` 写入（§4）

`services/agents.py`：`query()` 变薄壳 → `_execute_query()`（原函数体原样搬迁）+ `_record_qa_log()`。

- 字段**取自响应体不重算**：`citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id`；
- `question_hash` / `answer_hash` = **SHA-256 hex，不存原文**（M3 §5.3）；
- 成功 / 拒答**都落**（A4）；基础设施故障（`AgentUnavailableError` → 501）**不落**——那次调用没有 `AgentQueryResponse`，且同一 HTTP 请求已由中间件落 `audit_log(failure)`；
- **`patch_suspicion_status()` 签名未动**（复核的审计由中间件覆盖）；`agents.py` 是本批次唯一引入 session 的文件。

---

## 7. 前端（§6）

新增 `src/api/audit.ts`、`src/api/mock/audit.ts`、`src/store/use-audit-store.ts`、
`src/components/audit/{audit-toolbar,audit-table}.tsx`，重写 `src/app/audit/page.tsx`。

- **`CONTRACT_COVERED_PATTERNS` 已同步**（`client.ts`）——漏登记会让新端点走 mock，直接违反硬门槛；
- Mock 数据**刻意可识别为假**（`00000000-…-9XXX` 段、IP 用 RFC 5737 的 `203.0.113.*`、路径带 `?mock=1`），形状对齐契约 `AuditLogItem` 且不增删字段；
- **不引轮询**（A8）：审计是事后账本，不是异步任务；刷新靠手动按钮；
- **trace 回看不支持分页**（契约未定义 `page` / `page_size`，不引入无消费者参数）；空集 = 查无此租户可见记录，**不是错误**。

---

## 8. 测试（§7）

新增 `backend/tests/test_audit.py`（12 例），全量 **368 → 380 passed**：

| 断言 | 用例 |
|---|---|
| 每个 `/api/v1/*` 请求落一条（`action` / `trace_id` / `org_id` / `status` 可断言） | `test_api_request_writes_exactly_one_row` |
| `health` **不**落审计（allowlist） | `test_health_is_excluded_by_allowlist` |
| 4xx 也留痕且 `status = failure` | `test_failed_request_is_audited_as_failure` |
| 审计写失败**不影响**响应码 | `test_audit_write_failure_does_not_break_response` |
| 无身份（401）不写，不拿默认 org 顶替 | `test_unauthenticated_request_is_skipped_not_fabricated` |
| 两端点按租户隔离（跨租户空集） | `test_list_audit_returns_own_tenant_rows_only` / `test_trace_endpoint_replays_one_request_chain` |
| 默认 `ts DESC` + 页大小 50 + 分页 | `test_list_audit_defaults_to_ts_desc_and_page_size_50` |
| 非法 `status` → 400 `VALIDATION_ERROR`（不当"全不过滤"） | `test_list_audit_rejects_invalid_status_filter` |
| `qa_logs` 成功 / 拒答各落一条且哈希非原文 | `test_qa_log_records_answered_query` / `test_qa_log_records_refused_query` |
| `qa_logs` 写失败不破坏答案 | `test_qa_log_write_failure_does_not_break_answer` |

**桩数据与假-coding 的边界**：种子行刻意打**过去**时间戳——本请求自身的 `audit.list` 行写在响应之后，
若把种子打到未来，DESC 首行会变成那条自举行，断言就失去意义（用例注释已写明）。

---

## 9. 真机（§8）

### 9.1 踩坑：先把 Spirit-possessed 的旧进程换掉（**重要**）

首次 `Start-Process powershell … uvicorn … 8123` **并未真正接管端口**：

```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8123)
```

即 8123 上是**上一轮遗留的旧进程**（`pid=23032`，代码早于 Sprint 8.1）。
后果：首轮走查看似全绿（上传 / 解析 / 提问均 200），但 `audit_log` / `qa_logs` **双表 0 行**——
那些请求根本没经过新中间件。**该轮结果作废，未写入任何结论。**

处置：`Stop-Process -Id 23032 -Force` → 重启 → `uvicorn.log` 出现
`Application startup complete` / `Uvicorn running on http://127.0.0.1:8123`（`pid=9640`），
且 `GET /api/v1/health` 返回 `version: 1.3.0`。

> 登记为通用坑：**真机走查前先确认端口归属进程是不是你要的那个**，否则"看起来绿"的证据是假的。

### 9.2 演示路径（驱动脚本 `changes/Sprint8.1/demo_walkthrough.py`）

```
cd backend && uv run python ../changes/Sprint8.1/demo_walkthrough.py
```

| 步骤 | 实测（真实在线服务） |
|---|---|
| T0 | 起步前 `audit_log = 0` ⇒ **health 确实不写**（真机验证 allowlist） |
| 1 上传 | `POST /documents/upload` → 200 `task_id=adf80ce0-316d-4953-a5de-8b6c9a93cb94` `trace=548855af-…`（4KB `complex_table.pdf`，真实 MinerU 解析） |
| 2 解析 | `GET /documents/{id}/status` ×3 → `processing → processing → completed` |
| 3 列表 | `GET /documents` → `total=9` |
| 4 看图 | `GET /graph/overview` → `kg_version=v-s71a-fe1c4dc3`，`nodes=500 / edges=36 / truncated=true`；`GET /documents/{id}/graph` → `nodes=0`（新解析文档未建图，预期） |
| 5 提问 | `POST /agent/query` → `refused=False`、`citations=1`、`trace=1c9566b3-ad58-4c2e-98fa-a5869c06aa5c`；**溯源回查成功**（`chunk-799a066be6cf`，原文 1163 字） |
| 6 检测 | `POST /affiliation/detect` → **202** `task_id=1bdd49ca-…`；轮询 `#0 completed`，`summary={total:10, by_type:{shared_legal_rep:1, shared_address:9}}` |
| 7 复核 | `PATCH /affiliation/suspicions/62ba3fc6-…` → `confirmed`，`trace=1efa678e-…` |

**计数（直读 `dev.db`，不经过 `/audit` 端点——后者自身会写自举行，见风险 3 / 7）**：

```
audit_log  总条数 = 13  (distinct trace = 13)
    document.status success 3 | document.upload 1 | document.list 1 | graph.overview 1
    document.graph 1 | agent.query 1 | document.chunk 1 | affiliation.detect 1
    affiliation.task 1 | affiliation.list 1 | affiliation.review 1
qa_logs    条数   = 1   (refused=0, citations=1, kg_version=v-s71a-fe1c4dc3)
```

⇒ **plan §7.2 步骤 6 的「审计页可见 ≥7 条」判据达成（13 条 / 13 个 trace，每条都带 trace_id）**。
**口径登记（proposal 风险 7）**：这 13 条是**贯穿演示路径的 13 个不同 trace**，**不是**同一 trace 下 13 条——
后端异步任务由 `tasks/manager.py:233-241` 另生成 trace_id，plan 原文也不要求同号。

**端点自举行为**（必须是异议处理，写进契约 `description` 亦已注明）：

```
第一次 GET /api/v1/audit → total=13 items=13 page=1 page_size=50
第二次 GET /api/v1/audit → total=14 items=14   （多出来的正是前一次查询自身写的 audit.list）
GET /api/v1/audit/trace/1efa678e-… → total=1 action=['affiliation.review']
```

### 9.3 花费（真实开始）

| 动作 | 花费 |
|---|---|
| MinerU 解析（4KB PDF，1 份） | 第三方额度，未金额化 |
| LLM 提问（唯一花钱步） | `prompt_tokens=25265 / completion_tokens=247 / total=25512` ⇒ 按 deepseek-chat ¥2/1M 入 ¥8/1M 出 ≈ **¥0.053** |
| 受控问题集 14 问（见 §9.4） | 单问同量级 ⇒ 合计 ≈ **¥0.74** |

单次调用远低于 ¥1 护栏（未触发"先问用户"）。

### 9.4 受控问题集回归（tasks §8 第 4 项，**NOT PASS，如实登记**）

```
cd backend && $env:EVAL_BASE_URL="http://127.0.0.1:8123"; uv run python scripts/eval_controlled_qset.py
```

```
总题数 14 / 非拒答 3 / 引用命中(chunk-) 3
引用覆盖率 : 100.0%  (目标 100%)     ← 本批次的回归项**达成**
拒答口径不符 : 11                     ← NOT PASS
请求失败 : 0
```

**归因（证据链）**：受控问题集是 **Sprint 6** 针对《2025 年度集团经营指标分析报告》造的；
当前 active `kg_version = v-s71a-fe1c4dc3` 来自 **Sprint 7.1 重抽的招商局系年报**（2000 实体 / 819 关系），
两者**不同源** ⇒ 11 问必然落到拒答出口（Q13「这份合同里甲方是哪家公司」反而能答，
正说明图谱已换成年报/募集说明书语料）。

**与本批次无因果关系**：本批次 diff 只落在「两张新表 + 中间件 + `qa_logs` 落点 + 两个只读端点 + 前端审计页」，
**未触碰抽取 / Prompt / 引用构建链路**（`git diff` 文件集可核）。
⇒ 登记为新缺口：**受控问题集需随演示语料换版**（建议批次 B / C 承接），不当本次回归失败处理。

---

## 10. 前端关 Mock 验证（§6 硬门槛）

```
cd frontend
$env:NEXT_PUBLIC_USE_MOCK="false"; $env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8123"
$env:NEXT_PUBLIC_APP_ENV="development"
$env:NEXT_PUBLIC_DEV_DEFAULT_ORG_ID="00000000-0000-4000-8000-000000000001"
npm run dev
Invoke-WebRequest http://127.0.0.1:3000/audit → HTTP 200 len=34844，SSR 命中标题「权限审计」
```

- `next-dev.log` → `Ready in 6.4s`，**无编译错误**；
- `X-Org-Id` 与后端 `DEFAULT_ORG_ID` 一致（后端 `DEFAULT_ACTOR_ID=…-00aa`）；
- 数据侧等价证据：`curl`/脚本以同样请求头打 `GET /api/v1/audit` 拿到真实行（§9.2），
  且 `client.ts` 的 `CONTRACT_COVERED_PATTERNS` 已登记两个新端点 ⇒ `shouldMock()` 恒 false；
- **浏览器点验待用户**（无 headless 浏览器可用）：<http://localhost:3000/audit>
  （服务仍在运行：`uvicorn 8123` pid 9640 / `next dev` 3000）。

---

## 11. 门禁（§9，复跑，全部为命令输出）

| 门禁 | 结果 |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 118 files already formatted（本批次文件已格式化） |
| `uv run pytest -q` | **380 passed**（基线 368 + 新增 12） |
| `uv run python scripts/check_seams.py` | **ERROR 0 / WARN 2 / OK 8** —— **与基线完全一致**（未动接缝 6） |
| `uv run python scripts/export_openapi.py --check` | OK（零漂移） |
| `npm run gen:api` | 无 diff |
| `npm run lint` / `npm run typecheck` | 均通过（无输出） |
| `npx prettier --check`（新增前端文件） | 已按 Prettier 格式化后通过 |

---

## 12. 未擅自处置项（显式登记，不静默）

| 项 | 状态 | 说明 |
|---|---|---|
| 无身份（401）请求 | **不写 `audit_log`** | `org_id` 是隔离键，不拿默认 org 顶替；日志 `audit_log_skipped_no_identity` 可追溯。S11 RBAC 落地时补 `permission.denied` 类事件 |
| 501 基础设施故障 | **不写 `qa_logs`** | 该次调用没有 `AgentQueryResponse`；同一 HTTP 请求已由 `audit_log(failure)` 覆盖 |
| RBAC 三粒度 / 敏感字段脱敏器 / RLS | 未做（S11） | 审计页只按租户隔离，不提供角色 / 用户筛选 |
| `alert` 表（P2） | 未做 | proposal 风险 5 |
| `list_in_flight_task_ids()` | 未做（批次 B） | 与 A11 slowapi 同批 |
| A11 slowapi / A12 fail-open 逃生阀 | 未做（批次 B） | 本批次保证不冲突即可 |
| A16 settings 页「演示环境」标注 | 未做（批次 D） | |
| `app_version` | **未 bump**（仍 1.3.0） | Sprint 8 收尾统一 bump 1.4.0 + tag |
| push / 归档 | 未做 | 由用户执行 |

### 真机观察（非本批次引入，**未修**，登记待查）

1. `GET /graph/overview` 返回 `nodes=500 / edges=36 / truncated=true`，但 **`entity_count=0`、`doc_count=0`**
   （契约 `GraphOverviewResponse` 有这三字段，`schemas/graph.py:96-98`）。
   `kg_versions` 表内该版本记为 entity=2000 / relation=819 ⇒ 数量与新计数字段不一致。
   **本批次 diff 未触碰 `services/graphs.py`**，属既存现象，交后续批次核查。
2. 多次跑演示路径会累积 `audit_log` 行（含 `audit.list` 自举行）——是设计使然，不是泄漏；
   计数一律**直读库**，不经端点统计。

### 最终行数（本次真机收尾时）

```
audit_log = 30 条 / distinct trace 30
    agent.query 15 | document.status 3 | audit.list 2 | document.upload 1 | document.list 1
    graph.overview 1 | document.graph 1 | document.chunk 1 | affiliation.detect 1
    affiliation.task 1 | affiliation.list 1 | affiliation.review 1 | audit.trace 1
qa_logs = 15 条（refused=False 4 / refused=True 11）——成功与拒答两侧都被覆盖到
```
