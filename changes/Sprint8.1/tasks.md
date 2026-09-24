# Tasks: Sprint 8.1 批次 A —— 审计最小闭环

> **状态**：**批次 A 已全部执行完毕**（2026-09-24），实测证据见 [`integration-log.md`](./integration-log.md)。
> **前置**：Sprint 7 已收口（tag `v1.3.0` 已打、`app_version = 1.3.0`、`changes/Sprint7.*` 已归档）；S6 侧补做对账已提交（`2ad1e73`）。
> **角色**：本批次动 `backend/` + `frontend/` + `contracts/openapi.yaml`（**契约先行**）+ `docs/adr/ADR-0003`（差异登记）+ `docs/dev-doc-status.md`（批次登记）。

## 0. 事前核实（未完成不得往后走）

- [x] **核实 A1–A16 已签字**（用户 2026-09-24 已确认"采纳建议项"，A9–A16 同）
- [x] **核实当前基线**：`check_seams.py` = **ERROR 0 / WARN 2 / OK 8**（2 条 WARN = 接缝 6），`app_version 1.3.0`；改后复跑**完全一致**
- [x] **核实基线门禁**：`pytest -q` **368 passed**、`export_openapi.py --check` OK、`npm run gen:api` 无 diff
- [x] **核实 `qa_logs` 字段清单**（`specs/m3-graphqa-citation.md` §4.3）与 `audit_log` 字段清单（`specs/m5-permission-audit.md` §4.4）逐字抄，不自创字段
- [x] **核实 trace_id 链路现状**：由 `core/middleware.py` 的 `TraceIdMiddleware` 生成 / 回显 / reset ⇒ 审计中间件挂在其**之内**才拿得到（`add_middleware` 后加者在外层）
- [x] **核实 `frontend/src/app/audit/page.tsx` 现状**（占位实现）：UI 骨架已整体重写为真实页面，非"覆盖一半"
- [x] ~~**试装 `slowapi` 可行性**（A11，批次 B 前置）~~ **已验证通过（2026-09-24）**：`slowapi 0.1.10` + `limits 5.8.0` 已入 `pyproject.toml` / `uv.lock`（**纯新增 126 行、零删改**，未牵动 fastapi 0.141.1 / starlette 1.6.0）；`368 passed` 不变；冒烟 `2/minute` 下第 3 次请求真出 **429**。
  - ⚠️ **批次 B 必做（实测结论）**：slowapi 默认 `_rate_limit_exceeded_handler` 返回 `{"error":"Rate limit exceeded: ..."}`，**不合 H3 的 `{code,message,detail,trace_id}`**，且无 `Retry-After` 头 ⇒ 必须**自定义 handler** 走 `AppError(ErrorCode.RATE_LIMITED).to_body(trace_id)`，并在 `errors.py:122-132` 加 `429: RATE_LIMITED`。**不要**直接挂默认 handler 了事。
- [x] ~~**向用户确认 DeepSeek 余额**（A13）~~ **已确认（2026-09-24，用户截图）：充值余额 ¥38.61、累计消费 ¥31.38**——已抄进 `integration-log.md` §1（以截图为准，未推测）
- [x] **核实建表模板**（`models.py` UUID 主键 / `org_id` 打头索引 / `created_at` / 枚举常量 + `CheckConstraint`），两张新表照抄，不另创风格
- [x] **核实 `router.py` 的注释**（原写"`/audit*` 留草案态、禁止提前注册"）——注册 audit 路由时**已一并改掉**，否则自相矛盾
- [x] **核实审计中间件挂载顺序**：挂在 `TraceIdMiddleware` **之内**（先 `add`）；真机以 `audit.list` 自举行反证顺序正确

## 1. 契约先行（`contracts/openapi.yaml`）

- [x] 新增 `GET /api/v1/audit`（按租户列表：`action` / `status` 过滤，**默认 `ts DESC`、页大小 50**）
- [x] 新增 `GET /api/v1/audit/trace/{trace_id}`（按 trace 查全部记录）
- [x] 新增 / 对齐两个 schema（`AuditLogItem` / `AuditLogListResponse` / `AuditTraceResponse`），字段与 §0 核实到的清单一致
- [x] `export_openapi.py --check` 通过；`git diff --stat` = **368 insertions / 0 deletions**（既有 14 条路径一行未动）
- [x] 顺手纠一处双向真值：`AuditLogItem.resource` 描述改为 `<METHOD> <实际请求路径>`（不含 query string），与实现一致

## 2. 两张表（ORM，`app/db/models.py`）

- [x] 新增 `AuditLog`（`audit_log`）：`id` / `org_id` / `ts` / `action` / `actor_id` / `actor_ip` / `doc_id?` / `resource` / `status` / `trace_id` / `detail?`(JSON)
- [x] 新增 `QaLog`（`qa_logs`）：`id` / `org_id` / `question_hash` / `answer_hash` / `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id` / `created_at`
- [x] 两张表**均带 `org_id` 且索引以 `org_id` 打头**（ADR-0003 §3.1）
- [x] **主键用 UUID**（A9），**不用** spec 的 `BIGSERIAL`；差异**已登记**到 `docs/adr/ADR-0003-tenant-isolation-rls.md` §3.1.1
- [x] **不**写迁移脚本（全仓无 Alembic，靠 `init_db()` 的 `create_all`；真机已验证新表随启动出现）
- [x] **不改动任何既有表**（7 张表一行未改；`git diff` 文件集可核）

## 3. `audit_log` 写入（中间件）

- [x] 新增 `AuditMiddleware`，挂在 `TraceIdMiddleware` **之内**（拿得到 trace_id）
- [x] 仅对 `/api/v1/*` 且**非 health** 的请求写一条（A1 的 allowlist；真机 T0 `audit_log=0` 反证）
- [x] `action` 走路由元数据映射，未登记回落 `http.<method>.<path>`（A2）并 WARNING
- [x] `actor_id` 取 `X-Actor-Id`（经接缝 1 `LocalAuthProvider`），`actor_ip` 取 `request.client.host`（A6）
- [x] `detail` **只写结构化字段**（`status_code` / `method` / `path`），绝不写响应体原文（A5）
- [x] **写失败只记日志、不抛异常**（`audit_log_write_failed`；单测用单测桩验证业务仍 200）
- [x] 登记：**无身份（401）请求不写**——`org_id` 是隔离键，不拿默认 org 顶替（日志 `audit_log_skipped_no_identity`）

## 4. `qa_logs` 写入

- [x] `services/agents.py` 产出 `AgentQueryResponse` 后落一条（成功 / 拒答**都落**）
- [x] `question_hash` / `answer_hash` **不记原文**（SHA-256，M3 §5.3）
- [x] `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id` 取自响应体，不重算
- [x] 登记：501 基础设施故障**不落** `qa_logs`（无响应体；同 HTTP 请求已由 `audit_log(failure)` 覆盖）

## 5. 两个只读端点

- [x] `GET /api/v1/audit`：按 `org_id` 隔离（跨租户空集），`action` / `status` 过滤，默认 `ts DESC`、页大小 50
- [x] `GET /api/v1/audit/trace/{trace_id}`：该 trace 的全部记录，同样按 `org_id` 隔离；**不支持分页**（契约未定义，不引入无消费者参数）
- [x] 响应体字段与契约一致（`export_openapi.py --check` 守着）
- [x] **不**做 RBAC 三粒度（S11）：本批次按租户隔离即可，权限粒度缺口见 `integration-log.md` §12
- [x] 登记：**自举行为**——本端点自身也写一条 `audit_log`，故下一次查询才会看到自己的那一行（契约 `description` 已注明）

## 6. 前端（关 Mock，硬门槛）

- [x] 新增 `src/api/audit.ts`（两个端点）+ `src/api/mock/audit.ts`（Mock 刻意可识别为假）
- [x] **同步 `CONTRACT_COVERED_PATTERNS`**（`src/api/client.ts`）
- [x] `src/app/audit/page.tsx` 接真实接口（列表 + 按 trace 查询 + 分页）＋ `components/audit/{audit-toolbar,audit-table}.tsx` ＋ `store/use-audit-store.ts`
- [x] 不新增依赖；不引轮询（审计页非异步任务场景）
- [x] 关 Mock 真机：`Next dev` 以 `NEXT_PUBLIC_USE_MOCK=false` + `API_BASE_URL=:8123` 启动，`GET /audit` SSR 200（`Ready in 6.4s`，无编译错误）；**浏览器点验待用户**（无 headless 浏览器）

## 7. 测试（pytest）

- [x] 审计中间件对每个 `/api/v1/*` 请求落一条（`action` / `trace_id` / `org_id` 可断言）
- [x] `health` **不**落审计（allowlist 生效）
- [x] 审计写失败**不影响**主流程响应码（不 500）
- [x] `qa_logs` 成功与拒答各落一条；`question_hash` 不含原文
- [x] 两个端点按 `org_id` 隔离（跨租户返回空集）
- [x] `GET /audit` 默认 `ts DESC`、页大小 50（种子行打**过去**时间戳，避免自举行干扰断言）
- [x] 全量 **368 → 380 passed**

## 8. 真机（关 Mock，判据是"数得出来"）

- [x] 走一遍演示路径（上传 → 解析 → 建图 → 提问 → 检测 → 复核），直读 `dev.db` 数 `audit_log` **= 13 条 / 13 个 trace**（判据 ≥7 ✅）
- [x] **口径按 proposal 风险第 7 条**：13 条是贯穿路径的 **13 个不同 trace**（后端任务由 `tasks/manager.py` 另生成 trace_id），**不是**同一 trace 下 13 条；解读已在 `integration-log.md` §9.2 显式登记
- [x] **复用现有图谱，不重建**（A13）：active 仍是 `v-s71a-fe1c4dc3`（2000 实体 / 819 关系）
- [ ] ⚠️ **受控问题集引用覆盖率仍 = 100%**（回归项）→ **部分达成，脚本 NOT PASS**：覆盖率 **3/3 = 100.0%**（本批次要保的那一项达成），但 `拒答口径不符 11 / 14`。
      **归因**：问题集是 Sprint 6 针对《2025 年度集团经营指标分析报告》造的，而 active 图谱已是 Sprint 7.1 重抽的**招商局系年报**语料 —— **语料漂移，与本次 diff 无因果**（未触碰抽取 / Prompt / 引用链路）。
      **登记为缺口**：受控问题集需随演示语料换版（建议批次 B / C 承接），详见 `integration-log.md` §9.4。
- [x] 登记踩坑：首次真机走查打到了**遗留旧进程**（端口 8123 被占，新进程 `Errno 10048` 起不来），结果全部作废；换进程后重跑（见 `integration-log.md` §9.1）

## 9. 门禁（收尾）

- [x] `ruff check .` = All checks passed；`ruff format --check .` = 118 files already formatted
- [x] `pytest -q` = **380 passed**（基线 368 + 新增 12）
- [x] `check_seams.py` → **ERROR 0 / WARN 2 / OK 8**（接缝 6 属批次 E，本批次未动）
- [x] `export_openapi.py --check` → 零漂移
- [x] `gen:api` 无 diff；`npm run lint` / `npm run typecheck` 通过；`prettier --check`（新增文件）通过

## 10. 收尾

- [x] 补 `changes/Sprint8.1/integration-log.md`（基线 / 核实 / 决策 / 实现 / 真机 / 花费 / 门禁 / 未擅自处置声明）
- [x] `docs/dev-doc-status.md` 补批次 A 登记（追加 leading §0 追加段）
- [x] 登记缺口：脱敏器 / RBAC / RLS（S11）、`alert` 表（P2）、`list_in_flight_task_ids()`（批次 B）、受控问题集换版（批次 B / C）、`graph.overview` 的 `entity_count=0`（真机观察）
- [x] **不** bump `app_version`（仍 **1.3.0**；Sprint 8 收尾统一 bump 到 1.4.0 + tag）
- [ ] 归档 `changes/Sprint8.1/` → `changes/archive/<日期>-Sprint8.1/`；push（由用户执行）
