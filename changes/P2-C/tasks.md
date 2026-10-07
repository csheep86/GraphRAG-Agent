# P2-C 任务清单（可独立验证 = 排计划的直接依据）

> 来源：`changes/P2/tasks.md:204-216` 的 P2-C 五项子任务 + `new-session-prompt.md` §5 决策表。
> 每完成一项：跑该项声明的验证 → `check_session_drift.py` → Conventional Commits 提交。

## 子任务

- [ ] **T1 口令校验**（P6-P1 遗留"算法终选"）
      `app/services/auth/password.py`（新增）：`hash_password` / `verify_password`，PBKDF2-SHA256 600k / stdlib；
      `scripts/seed_dev_rbac.py` 改为 import，消除两份实现。
      验证：`ruff check` + `ruff format --check`；`pytest tests/test_auth.py -q` 不回归。

- [ ] **T2 登录查找的受控旁路**
      `app/db/rls.py` 增 `app.find_login_user`（SECURITY DEFINER / 属主 `rls_probe` / 只认 `public.users`）
      + `system_function_statements()` 建函数与授权 + Python 包装 `find_login_user()`；
      `tests/test_guardrails_rls.py::test_g26_6` 受控函数 2 → 3、表白名单改**逐函数**、登记调用点。
      验证：`uv run python scripts/init_rls_roles.py --admin-url <superuser>` 重跑；
      `pytest tests/test_guardrails_rls.py -q` 全绿。

- [ ] **T3 JWT 签发 / 校验 + `parse_bearer_token` 认 JWT**
      `app/services/auth/token.py`（新增，HS256 / stdlib）+ `app/core/auth.py`；
      `settings.auth_jwt_secret` / `auth_jwt_ttl_minutes` + 生产沿用默认值的启动守卫 + `.env.example` 同步。
      验证：`pytest tests/test_auth.py -q`（含新增 JWT 三例：签发→校验往返 / 过期拒绝 / 篡改拒绝）；
      `uv run python scripts/check_seams.py` ERROR 0（两个新配置**都有**消费者）。

- [ ] **T4 `POST /api/v1/auth/login` 进契约**（契约先行 5 步）
      `app/schemas/auth.py` + `app/api/v1/routes/auth.py` + `router.py` 注册 → `export_openapi.py` 重导 →
      `tests/test_openapi_contract.py`：`CORE_PATHS` 27→**28**、operationId 计数 27→**28**、
      `TENANT_PROTECTED_PATHS` 排除 `/auth/login`（**写明理由与失效条件**）→ 前端 `npm run gen:api`。
      验证：`uv run python scripts/export_openapi.py --check` **零 diff**；`pytest tests/test_openapi_contract.py -q` 全绿。

- [ ] **T5 `activated_at` 唯一回填点**（子任务 ④ 的差分证据）
      `app/services/auth/login.py`（新增）：登录成功且 `activated_at IS NULL` ⇒ 回填**一次**；
      失败 / 目录同步 / 导入**不**回填。登记 `USERS_CONSUMER_MODULES`。
      验证（**真跑，不读代码**）：`tests/test_login_flow.py` —— 登录成功后查库 `activated_at` **非 NULL**，
      且 `count_seats()` **≥ 1**（P4 时恒 0）。

- [ ] **T6 `users.status` 接 RBAC**（子任务 ③ / D4）
      `services/rbac/service.py` 增 `REASON_ACCOUNT_DISABLED`；`rbac/deps.py` 在 RBAC 判定前查一次；
      **有行且非 active ⇒ 拒**，**无行 ⇒ 沿用现状**。登记 `USERS_CONSUMER_MODULES`。
      验证：`disabled` 后新请求 **403** 且 `detail.reason == "account_disabled"`，`disabled_at` 落值 ⇒
      `count_seats()` 回落；未改动任何既有用例的拒绝原因。

- [ ] **T7 R30 严格视图孤儿 = 0 + 孤儿 actor**
      `tests/conftest.py`：两个租户各播**一个独立主体**（`users.id` 是 PK ⇒ 不能复用同一 UUID）；
      `cross_tenant_headers` 的 actor 改为 org B 自己的主体（仍授 admin）。新增 `tests/test_identity_anchor.py`：
      逐租户断言 `user_roles` 在**严格视图**（`id` 与 `org_id` 都相等）下孤儿数 = **0**，并断言锚点行已存在（防恒绿）。
      验证：`pytest tests/test_guardrails.py tests/test_documents.py tests/test_audit.py -q` 不回归。

- [ ] **T8 外部身份字段**（子任务 ②）
      `users.issuer` / `users.subject` 两列（**nullable**）+ Alembic 迁移 + `docs/adr/0004-integration-seams.md` 预留登记；
      `tests/test_guardrails.py::EXTERNAL_IDENTITY_COLUMNS` 纳入 G-18 期望集合。
      验证：`pytest tests/test_migrations_baseline.py tests/test_guardrails.py -q`；`export_openapi.py --check` 零 diff（不进契约）。

- [ ] **T9 出口：门禁全量 + CI 终裁**
      `ruff check` / `ruff format --check` / `pytest -q`（≥ 基线）/ `export_openapi.py --check` / `check_seams.py` ERROR 0 /
      `check_startup_readiness.py` 不倒退 / 前端 lint + tsc；回登 run id 到 `integration-log.md`。

## 已裁决的顺延（**不得宣称达成**）

- 子任务 ①（扩写 ADR-0004 §2.1 再改 `get_auth_provider()`）⇒ **D1 顺延**；接缝 1 实现集合仍为 1。
- `delivery-plan.md:77`④「`check_seams.py` 登记接缝 1 第二实现」⇒ **仍挂起**。
- DR-D9（SSO / AD）⇒ **D5 不做**，状态保持 ⏳。
