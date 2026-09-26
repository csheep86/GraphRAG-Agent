# Integration Log — Sprint 8.2 批次 B（限流 slowapi + 逃生阀留痕 + S7.2-2）

> 日期：2026-09-24 ｜ 基线：批次 A 提交 `cb919ab`（380 passed）｜ 花费：**¥0**

## 1. 基线核实

| 项 | 结果 |
|---|---|
| `pytest -q`（改前） | **380 passed** |
| `check_seams.py`（改前） | ERROR 0 / WARN 2 / OK 8（WARN = 接缝 6，批次 E） |
| `export_openapi.py --check`（改前） | OK |
| slowapi 依赖 | 0.1.10 已在 `uv.lock`（批次 A 开工前试装） |

## 2. 实测三坑（全部**源码逐行核对**，非文档转述；这是本批次最大价值）

### 坑 1：`SlowAPIMiddleware` 在 FastAPI 0.141 上**限流静默失效**
- 现象：`default_limits=[1/minute]` 下连打 3 次全 200，限流从未触发。
- 定位（逐步探针）：slowapi `_find_route_handler`（middleware.py:18-26）对
  `app.routes` 找 `route.endpoint` —— 而 **FastAPI 0.141 的 `include_router`
  不再摊平路由**，产生 `_IncludedRouter`（fastapi/routing.py:1586，无 `endpoint`
  属性）⇒ handler 恒为 `None` ⇒ `_should_exempt` 恒 True ⇒ **所有路由被豁免**。
- 处置：自写**纯 ASGI** `RateLimitMiddleware`（`core/limiter.py`）：公开
  `route.matches(scope)` 命中后，若 FULL 而无 endpoint，回落 `_IncludedRouter._match`
  （routing.py:1728，其 `child_scope` 带 `endpoint`），并沿嵌套 `_IncludedRouter`
  下钻（`_MAX_INCLUDE_DEPTH=4`）。限流检查本身仍复用 `limiter._check_request_limit`
  （与 slowapi 中间件同一入口，不重造限流算法）。
- 附带收益：纯 ASGI 化解了 A11 登记的"slowapi 基于 BaseHTTPMiddleware"张力
  （`core/middleware.py:3-4` 纪律本就禁用它）。

### 坑 2：slowapi 中间件对 **async handler 静默回落**到坏默认
- `sync_check_limits`（slowapi/middleware.py:59-77）：注册的 429 handler 若是
  协程函数，会被**悄悄替换**为 slowapi 默认 handler——返回
  `{"error": "Rate limit exceeded: ..."}`，不合 H3 格式且无 `Retry-After`。
- 处置：`rate_limit_exceeded_handler` 保持**同步函数**（`exception_handlers.py`），
  `test_second_request_returns_429_with_contract_body` 是这条的回归锁。

### 坑 3：`@limiter.exempt` 装饰器的**注册时机**陷阱
- 装饰器在**模块导入时**把函数名写进**当时**的 Limiter 单例 `_exempt_routes`；
  任何换例（测试 `get_limiter.cache_clear()` / 重建 app）都会把名单弄丢
  （真机复现：health 豁免失效被限流 429）。
- 处置：豁免改为**集中声明** `core/limiter.py::EXEMPT_ROUTE_NAMES`
  （`frozenset({"app.api.v1.routes.health.get_health"})`），`_should_exempt`
  同时查集中名单与 slowapi 自身两套集合。

## 3. 实现清单（契约 → 装配 → 留痕 → 对账）

1. **契约**：`errors.py` 新增 `RATE_LIMITED`（枚举 / `ERROR_HTTP_STATUS[429]` /
   默认消息 / 描述 / 来源 / `HTTP_STATUS_TO_ERROR_CODE[429]` 六处）→
   `export_openapi.py` 重导（`contracts/openapi.yaml` **+7 / −1**）→ `gen:api`
   （`api.d.ts` **+3 / −1**）。
2. **装配**：`core/limiter.py`（`get_limiter` + `RateLimitMiddleware` +
   `EXEMPT_ROUTE_NAMES`）；`config.py` 增 `rate_limit_per_minute=60`（唯一消费点
   `core/limiter.py`，`check_seams` "Settings 46 字段均有消费者" 通过）；
   `.env.example` 增 `RATE_LIMIT_PER_MINUTE=60`；`main.py` 挂中间件（审计之内）。
3. **A14**：同步 429 handler（`AppError(RATE_LIMITED).to_body(trace_id)` +
   `Retry-After` 按窗口粒度换算）+ 直写 `audit_log(action=rate_limit.triggered)`
   （身份走接缝 1，拿不到不写；写失败只记日志）。
4. **A12**：`agents.py` fail-open 分支写 `tenant_leak.warn`；`backend/CODEBUDDY.md`
   逃生阀行补口径。
5. **S7.2-2**：`list_in_flight_task_ids()` 补扫 `affiliation_tasks`；
   `backend/CODEBUDDY.md` §4 行转 ✅（S7.1-5 仍待偿还，如实保留）。
6. **`services/audit.py` 写入点登记**更新为：中间件（A1）+ 429 handler（A14）+
   逃生阀（A12），新增调用方须先登记。

## 4. 门禁输出（改后）

| 门禁 | 结果 |
|---|---|
| `ruff check .` / `format --check .` | All checks passed ／ 121 files already formatted |
| `pytest -q` | **387 passed**（基线 380 + 新增 7：限流 5 + S7.2-2 1 + A12 1） |
| `check_seams.py` | **ERROR 0 / WARN 2 / OK 8**（与基线逐字一致） |
| `export_openapi.py --check` | OK（零漂移） |
| `gen:api` | 重生成后无 diff |
| `npm run lint` / `typecheck` | 通过 |

## 5. 真机证据（RATE_LIMIT_PER_MINUTE=3，端口 8123，花费 ¥0）

```
audit#1..3  status=200                       （限内放行）
audit#4     status=429  retryAfter=60
            body={"code":"RATE_LIMITED","message":"Too many requests",
                  "detail":{"limit":"3 per 1 minute","retry_after_seconds":60},
                  "trace_id":"967ee88f-..."}
audit#5     status=429  retryAfter=60        trace_id=0eec2d1d-...
health#1..3 status=200                        （豁免，连打 3 次不 429）

dev.db 直读 audit_log：
  rate_limit.triggered 2 行（每 429 一条）
    failure GET /api/v1/audit  "3 per 1 minute"  trace 967ee88f / 0eec2d1d
```

判据（M5 §3 验收 5）：429 ✅ ／ `RATE_LIMITED` ✅ ／ `Retry-After` ✅ ／
`audit_log(action=rate_limit.triggered)` ✅ ／ `alert` 表 P2 不做（显式边界）。

## 6. 未擅自处置声明

- **未动** `alert` 表、RBAC / 脱敏 / RLS（S11）、`ExportSink`（批次 E）、受控问题集、
  `graph.overview` 的 `entity_count=0`（观察项）。
- **未 bump** `app_version`（仍 1.3.0；Sprint 8 收尾统一 1.4.0 + tag）。
- **未新增** `settings.*` 无消费者配置（新增的 `rate_limit_per_minute` 唯一消费点
  `core/limiter.py::get_limiter`，由 `check_seams.py` 消费者闸门机械核对）。
- 真机后日志文件已删（`uvicorn.log` 不入库，同批次 A 约定）。

## 7. 遗留 / 移交

- 批次 D：A16 settings 页「演示环境」标注；受控问题集换版登记。
- 观察项：`graph/overview` `entity_count=0`（既存现象，单独排查）。
- Sprint 8 收尾：`app_version` → 1.4.0 + tag + PR #3 转 ready → merge。
