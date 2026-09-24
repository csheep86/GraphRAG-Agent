# Tasks: Sprint 8.1 批次 A —— 审计最小闭环

> **状态**：草稿待实施（决策 A1–A8 见 `proposal.md`，按建议采纳）。
> **前置**：Sprint 7 已收口（tag `v1.3.0` 已打、`app_version = 1.3.0`、`changes/Sprint7.*` 已归档）；S6 侧补做对账已提交（`2ad1e73`）。
> **角色**：本批次动 `backend/` + `frontend/` + `contracts/openapi.yaml`（**契约先行**）。

## 0. 事前核实（未完成不得往后走）

- [ ] **核实 A1–A16 已签字**（用户 2026-09-24 已确认"采纳建议项"，A9–A16 同）
- [ ] **核实当前基线**：跑一次 `uv run python scripts/check_seams.py` 记下输出（`ERROR 0 / WARN 2 / OK 8`，2 条 WARN = 接缝 6），作为改后对比证据
- [ ] **核实基线门禁**：`uv run pytest -q`（记 passed 数）、`uv run python scripts/export_openapi.py --check`、`npm run gen:api` 无 diff
- [ ] **核实 `qa_logs` 字段清单**（`specs/m3-graphqa-citation.md` §4.3）与 `audit_log` 字段清单（`specs/m5-permission-audit.md` §3 验收 2）逐字抄，不自创字段
- [ ] **核实 trace_id 链路现状**：`core/middleware.py` 的 `X-Trace-Id` 生成 / 回显 / `reset_trace_id` 时机，确认审计中间件挂在**其之后**才拿得到 trace_id
- [ ] **核实 `frontend/src/app/audit/page.tsx` 现状**（占位实现读到什么程度），避免覆盖掉既有 UI 骨架
- [ ] **试装 `slowapi` 可行性**（A11，批次 B 前置）：`pyproject.toml:10-23` 与 `uv.lock` 现均无 `slowapi` / `limits`；装不上**立即升级用户**，不要硬扛、不要自造中间件绕过 spec 点名
- [ ] **向用户确认 DeepSeek 余额**（A13）：真机走查里「提问」要调 LLM；**余额数字不得推测**，没有数字就没有真机判据
- [ ] **核实建表模板**（`models.py:221` UUID 主键 / `:222` `org_id` 打头索引 / `:234-236` `created_at` / `:212-215` 枚举常量 + `CheckConstraint`），两张新表照抄，不另创风格
- [ ] **核实 `router.py:15-16` 的注释**（现写"`/audit*` 留草案态、禁止提前注册"）——本批次注册 audit 路由时须一并改掉这句，否则自相矛盾
- [ ] **核实审计中间件挂载顺序**：必须挂在 `TraceIdMiddleware`（`main.py:68`）**之后**才拿得到 trace_id；注意 `main.py:58-59`「后加者在外层」

## 1. 契约先行（`contracts/openapi.yaml`）

- [ ] 新增 `GET /api/v1/audit`（按租户列表：`action` / `status` 过滤，**默认 `ts DESC`、页大小 50**）
- [ ] 新增 `GET /api/v1/audit/trace/{trace_id}`（按 trace 查全部记录）
- [ ] 新增/对齐两个 schema（`AuditLog` / `QaLog` 或 audit 响应体），字段与 §0 核实到的清单一致
- [ ] `uv run python scripts/export_openapi.py --check` 通过（契约与后端模型一致）

## 2. 两张表（ORM，`app/db/models.py`）

- [ ] 新增 `AuditLog`，`__tablename__ = "audit_log"`：`id` / `org_id` / `ts` / `action` / `actor_id` / `actor_ip` / `doc_id?` / `resource` / `status` / `trace_id` / `detail?`(JSON)
- [ ] 新增 `QaLog`，`__tablename__ = "qa_logs"`：`id` / `org_id` / `question_hash` / `answer_hash` / `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id` / `created_at`
- [ ] 两张表**均带 `org_id` 且索引以 `org_id` 打头**（ADR-0003）
- [ ] **主键用 UUID**（A9，照 `models.py:221`），**不用** `m5:99` 的 `BIGSERIAL`；差异登记到 `docs/adr/ADR-0003`
- [ ] **不**写迁移脚本（全仓无 Alembic，靠 `init_db()` 的 `create_all`）
- [ ] **不改动任何既有表**（7 张表一行不改）

## 3. `audit_log` 写入（中间件）

- [ ] 新增审计中间件，挂在 `TraceIdMiddleware` **之后**（否则拿不到 trace_id）
- [ ] 仅对 `/api/v1/*` 且**非 health** 的请求写一条（A1 的 allowlist）
- [ ] `action` 走路由元数据映射，未登记路由回落 `http.<method>.<path>`（A2），回落时留日志
- [ ] `actor_id` 取 `X-Actor-Id`，`actor_ip` 取 `request.client.host`（A6）
- [ ] `detail` **只写结构化字段，绝不写响应体原文**（A5）
- [ ] **写失败只记日志、不抛异常**（审计缺陷不得变成全站 500）

## 4. `qa_logs` 写入

- [ ] `services/agents.py` 产出 `AgentQueryResponse` 后落一条（成功 / 拒答**都落**）
- [ ] `question_hash` / `answer_hash` **不记原文**（M3 §5.3 纪律）
- [ ] `citation_count` / `refused` / `refusal_reason` / `kg_version` / `trace_id` 取自响应体，不重算

## 5. 两个只读端点

- [ ] `GET /api/v1/audit`：按 `org_id` 隔离（跨租户不返回），`action` / `status` 过滤，默认 `ts DESC`、页大小 50
- [ ] `GET /api/v1/audit/trace/{trace_id}`：返回该 trace 的全部记录，同样按 `org_id` 隔离
- [ ] 响应体字段与契约一致（`export_openapi.py --check` 守着）
- [ ] **不**做 RBAC 三粒度（S11）：本批次按租户隔离即可，权限粒度缺口显式登记

## 6. 前端（关 Mock，硬门槛）

- [ ] 新增 `src/api/audit.ts`（两个端点）
- [ ] **同步 `CONTRACT_COVERED_PATTERNS`**（`src/api/client.ts`）——漏登记会让新端点走 mock，直接违反硬门槛（S6.4 §2.1 教训）
- [ ] `src/app/audit/page.tsx` 接真实接口（列表 + 按 trace 查询 + 分页）
- [ ] 不新增依赖；不引轮询（审计页非异步任务场景）

## 7. 测试（pytest）

- [ ] 审计中间件对每个 `/api/v1/*` 请求落一条（`action` / `trace_id` / `org_id` 可断言）
- [ ] `health` **不**落审计（allowlist 生效）
- [ ] 审计写失败**不影响**主流程响应码（不 500）
- [ ] `qa_logs` 成功与拒答各落一条；`question_hash` 不含原文
- [ ] 两个端点按 `org_id` 隔离（跨租户返回空 / 403）
- [ ] `GET /audit` 默认 `ts DESC`、页大小 50

## 8. 真机（关 Mock，判据是"数得出来"）

- [ ] 走一遍演示路径（上传 → 解析 → 建图 → 提问 → 检测 → 复核），数 `audit_log` 条数 —— **≥ 7 条**（plan §7.2 步骤 6 原文）
- [ ] **口径按 proposal 风险第 7 条**：全程审计页可见 **≥7 条**、每条都带 `trace_id`、可按 `trace_id` 过滤回看任一步；**不要求"同一个 trace_id 下 7 条"**（后端任务由 `tasks/manager.py:233-241` 另生成 trace_id），解读在 integration-log 里**显式登记**
- [ ] **复用现有图谱，不重建**（A13）；图谱若已被破坏才重建，且须先问用户（要花钱）
- [ ] 受控问题集引用覆盖率仍 = 100%（**回归项**，不得被本批次破坏）

## 9. 门禁（收尾）

- [ ] `uv run ruff check .` / `uv run ruff format --check .`
- [ ] `uv run pytest -q`（全绿，记 passed 数）
- [ ] `uv run python scripts/check_seams.py` → 保持 **ERROR = 0 / WARN 2**（接缝 6 属批次 E，本批次不动）
- [ ] `uv run python scripts/export_openapi.py --check` → 零漂移
- [ ] `npm run gen:api` 无 diff；`npm run lint` / `npm run typecheck` 通过

## 10. 收尾

- [ ] 补 `changes/Sprint8.1/integration-log.md`（基线 / 核实 / 决策 / 实现 / 真机 / 门禁 / 未擅自处置声明）
- [ ] `docs/dev-doc-status.md` 补批次 A 登记
- [ ] 登记缺口：脱敏器 / RBAC / RLS（S11）、`alert` 表（P2）、`list_in_flight_task_ids()`（批次 B）
- [ ] **不** bump `app_version`（Sprint 8 收尾统一 bump 到 1.4.0 + tag）
