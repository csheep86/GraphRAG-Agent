# Tasks: Sprint 8.2 批次 B —— 限流（slowapi）+ 逃生阀留痕 + S7.2-2 对账收口

> **状态**：**批次 B 已全部执行完毕**（2026-09-24），实测证据见 [`integration-log.md`](./integration-log.md)。
> **前置**：批次 A（`cb919ab`）已提交并归档（`changes/archive/2026-09-24-Sprint8.1/`）。
> **范围**：proposal A11 / A12 / A14 + 缺口 S7.2-2；**不动** `alert` 表（P2）、不动接缝、不 bump `app_version`。

## 0. 事前核实（未完成不得往后走）

- [x] **核实 slowapi 已装**：`slowapi 0.1.10` + `limits 5.8.0` 在 `pyproject.toml` / `uv.lock`（批次 A 开工前试装通过）
- [x] **核实 M5 §3 验收 5 原文**：超 N 次（默认 60，可配置）→ 429 `RATE_LIMITED` + `audit_log(action=rate_limit.triggered)`；`alert` 表 P2 不做
- [x] **核实基线门禁**：`pytest -q` **380 passed**（批次 A 后）、`check_seams.py` **ERROR 0 / WARN 2 / OK 8**、`export_openapi.py --check` OK、前端 eslint/tsc 通过
- [x] **核实 `errors.py` 错误码登记口径**（枚举 / 状态码 / 消息 / 描述 / 来源 / HTTP 兜底六处）与 `HTTP_STATUS_TO_ERROR_CODE` 无 429 ⇒ 必须新增（A14：否则 429 兜底成 `HTTP_ERROR`→500，违反矩阵判据）
- [x] **核实审计写入原语**：`services/audit.py::record_audit_entry`（不自行 commit）；写入点登记制（A1），新增直写方须先登记

## 1. 契约先行（`contracts/openapi.yaml`）

- [x] `errors.py` 新增 `RATE_LIMITED`（六处登记）→ `export_openapi.py` 重导：**+7 / −1**（ErrorCode 枚举 + 描述 + 来源 3 行；health 描述随实现更新 1 处）
- [x] `429 → RATE_LIMITED` 兜底映射（任何未走自定义 handler 的 429 也落 `RATE_LIMITED`，不落 `HTTP_ERROR`）
- [x] `npm run gen:api` → `frontend/src/types/api.d.ts` **+3 / −1**；契约 `--check` 零漂移

## 2. 限流装配（决策 A11）

- [x] 新增 `core/limiter.py`：`get_limiter()`（每分钟每 IP 每接口 `rate_limit_per_minute` 次，默认 60）+ **自写纯 ASGI `RateLimitMiddleware`**（不用 `SlowAPIMiddleware`，见 integration-log §2 实测坑 1）+ `EXEMPT_ROUTE_NAMES`（health 豁免，集中声明）
- [x] `config.py` 新增 `rate_limit_per_minute: int = 60`（唯一消费点 `core/limiter.py`；`check_seams` "46 个字段均有消费者" 通过）；`.env.example` 同步 `RATE_LIMIT_PER_MINUTE=60`
- [x] `main.py` 装配：`app.state.limiter` + `add_middleware(RateLimitMiddleware)`（挂在审计**之内**：429 出栈前流经审计与 TraceId）
- [x] **不改**任何端点签名（不逐端点挂装饰器——安全底线"所有对外 API"靠默认限全量覆盖，装饰器必然漏）

## 3. 429 handler + 审计留痕（决策 A14）

- [x] `exception_handlers.py` 新增 **同步** `rate_limit_exceeded_handler`：`AppError(RATE_LIMITED).to_body(trace_id)` + `Retry-After`（按命中窗口粒度换算，minute→60）+ detail 只写结构化字段（A5）
- [x] 同步写 `audit_log(action=rate_limit.triggered)`：身份走接缝 1 解析（拿不到就不写，同中间件口径）；写失败只记日志
- [x] `services/audit.py` 写入点登记更新：中间件 + 429 handler（A14）+ 逃生阀（A12），"新增调用方必须先在此登记"

## 4. 逃生阀留痕（决策 A12）

- [x] `agents.py` fail-open 分支（`agent_fail_closed=False` 放行时）写 `audit_log(action=tenant_leak.warn)`，detail 记 `kg_version` / `fail_closed`
- [x] `backend/CODEBUDDY.md` 逃生阀行同步口径（原只写"False 为逃生阀"）

## 5. S7.2-2 偿还

- [x] `tasks/manager.py::list_in_flight_task_ids()` 补扫 `affiliation_tasks`（与 `recover_orphan_tasks` 同口径，ADR-0001 第 73 行）
- [x] `backend/CODEBUDDY.md` §4 S7.2-2 行 → ✅ 已偿还（S7.1-5 仍待偿还，如实保留）

## 6. 测试（新增 7 例）

- [x] `tests/test_rate_limit.py`（5 例）：429 契约体 + Retry-After + trace 回显；`resolve_error_code(429)`；`rate_limit.triggered` 落库；health 豁免；按接口配额隔离
- [x] `tests/test_task_recovery.py`（+1）：在途 `affiliation_tasks` 进对账结果
- [x] `tests/test_agent_fail_closed.py`（+1）：逃生阀放行写 `tenant_leak.warn`
- [x] `tests/conftest.py`：共享 client 限流实际关闭（`RATE_LIMIT_PER_MINUTE=100000`），限流行为由专测覆盖——避免全量跑测撞限

## 7. 门禁（收尾）

- [x] `ruff check .` / `ruff format --check .` 全过（121 files）
- [x] `pytest -q` = **387 passed**（基线 380 + 新增 7）
- [x] `check_seams.py` → **ERROR 0 / WARN 2 / OK 8**（与基线一致；接缝 6 属批次 E）
- [x] `export_openapi.py --check` → 零漂移
- [x] `gen:api` 无 diff（重生成后）；`npm run lint` / `npm run typecheck` 通过

## 8. 真机

- [x] `RATE_LIMIT_PER_MINUTE=3` 起服务：`/api/v1/audit` 限内 3 次 200 → 第 4/5 次 **429 + `Retry-After: 60` + 契约体**；`/api/v1/health` 3 次全 200（豁免）
- [x] 直读 `dev.db`：**`rate_limit.triggered` 2 行**（每 429 一条，trace_id 与响应体一致）
- [x] 花费：**¥0**（不触 LLM / 不触解析）

## 9. 收尾

- [x] 补 `changes/Sprint8.2/integration-log.md`（实测三坑 / 门禁输出 / 真机证据 / 未擅自处置声明）
- [x] `docs/dev-doc-status.md` 补批次 B 登记
- [x] **不** bump `app_version`（仍 1.3.0）
- [x] 提交 + push（用户过目后执行）；CI 随 PR #3 自动重跑
  - **2026-09-24 已执行**：提交 **`36d4c26`**（`feat(ratelimit)`，20 files ／ +805 ／ −13），push `7420eb3e..36d4c26c` → `origin/feature/sprint-8`。
  - **push 曾 3 次失败**：`Recv failure: Connection was reset` / `Failed to connect to github.com:443`（本机 GitHub 网络时好时坏，非 DNS 问题——`api.github.com` 同时刻正常）；第 4 次重试即成功。**结论：遇到 push 失败直接重试即可，无需改 hosts / 换 IP。**
  - **CI（PR #3，run `36001623993`，sha `36d4c26`）全绿**：后端 23s ✅ ／ 契约校验 25s ✅ ／ 前端 24s ✅ ／ 流水线汇总 3s ✅（远端 Python 3.11 / Node 22 与本地门禁结论一致）。
