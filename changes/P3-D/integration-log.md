# P3-D 集成日志 —— 「哪里会漏绑 org」审计收口（P3-C 未决 #1）

| 项 | 内容 |
|---|---|
| **批次** | P3-D |
| **日期** | 2026-10-04 |
| **触发** | P3-C 未决 #1（审计未绑 org 的查询路径） |
| **出口判据** | `proposal.md` §2：① passed 不减；② 新断言各自反向验证判红；③ **实测**"受限角色跑迁移会失败"；④ 全部门禁 |

---

## 1. 门禁实测

| 门禁 | 起跑（P3-C 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | **889 passed**（开真图开关） | **892 passed / 3 skipped / 3 xfailed**（+3 = 判据 9 / 10 / 11） |
| `check_startup_readiness.py` | G-26 **12 项** | G-26 **15 项** |
| `ruff check` / `ruff format --check` | 双绿 | 双绿（218 files） |
| `check_seams.py` | 接缝 OK 10 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |
| `check_session_drift.py` | — | S1 读到 Non-goals ✔ / S3 新配置已同步 `.env.example` ✔ |

---

## 2. 审计结论（**事实**）

| 路径 | 绑 org | 结论 |
|---|---|---|
| 全部 HTTP 路由的 `DbSession`（`api/deps.py:90`） | ✅ `identity.org_id` | 安全 |
| 后台任务 8 个入口（`tasks/registry.py:110/221/325/488/609/717/884/1051`） | ✅ `spec.org_id` | 安全 |
| 中间件 / 异常处理器 / Agent / CLI | ✅ | 安全 |
| A6 启动回收（`tasks/manager.py:197/254`，`system_session()`） | ❌ **刻意不绑** | 只调受控函数 `app.list_tenant_orgs()`（`SECURITY DEFINER` + `rls_probe NOLOGIN BYPASSRLS`）⇒ **受控通道，不是 bug**；同一 session 直接查 `documents` **依然 0 行** |
| `/api/v1/health` | ❌ | 只 `SELECT 1` ⇒ 不受影响 |
| `LocalAuthProvider` | — | **当前不查库**（dev token / header）；`/auth/login` 未实现 |

⇒ **运行时不存在"漏绑 org 却查租户表"的路径**。真正的问题在别处，共三个，见下。

---

## 3. 收口的三个缺口

### 3.1 缺口 A（**高**）：部署的**升级路径是断的**

| 事实 | 证据 |
|---|---|
| `migrations/env.py` 只认 `settings.database_url` | 修前 `env.py:38-39` |
| 仓库里**没有** `database_url_owner` 配置（`DATABASE_URL_OWNER` 只被测试侧 `os.environ` 直读） | `config.py` 全文 0 命中 |
| compose 的 backend **没有** `DATABASE_URL_OWNER` | 修前 `deploy/docker-compose.yml` 只有 `DATABASE_URL`（`app_rls`） |

**实测取证**（空库 scratch DB，跑同一条 `alembic upgrade head`）：

```text
[受限角色 app_rls] => FAILED: (psycopg.errors.InsufficientPrivilege) permission denied for schema public
[owner app_owner]  => OK
```

**修法**：`Settings.database_url_owner`（env `DATABASE_URL_OWNER`）+ `env.py` 优先取 owner
（缺则回落，本地行为不变）+ compose 注入 + `scripts/migrate_add_suspicion_causes.py` 改走
owner（**没配 owner 时明确报错**，不静默撞权限错误）。

⚠️ **症状不是"隔离失效"，而是"部署之后升不了级"**——平时毫无症状，只在升级那一刻炸。

### 3.2 缺口 B（**中**）：测试脚手架会**掩盖**漏绑

`tests/conftest.py:112-119` 给 `SessionLocal.kw["info"]` 塞默认 org ⇒ `open_session()`、
**连 `system_session()` 在内**在测试里都自动带租户：

- 把 `open_session(org_id=identity.org_id)` 改成 `open_session()` ⇒ 生产 0 行、**测试仍绿**；
- 在 `system_session()` 里直接查租户表 ⇒ 生产 0 行、**测试看得到默认租户数据**。

**修法两条**：
1. `system_session()` **显式清掉** org ⇒ 系统通道在测试与生产语义一致；
2. G-26 **判据 10（静态）**：`app/` 下所有 `open_session(` / `session_scope(` 调用点
   **必须显式传 `org_id=`**（豁免：`app/db/session.py` 自身两处）⇒ 漏传即红灯。

> 判据 3 / 8 证明的是「RLS 会拦」，**证明不了「调用点传了 org」**——这一段正是
> 两者之间唯一的缝，故必须补。

### 3.3 缺口 C（**低**，**只登记不实现**）

`/auth/login` 尚未实现，且 `users` **不是**豁免表 ⇒ 将来若以无 org 的受限会话按 username
查 `users`，会稳定得到 **0 行**。届时须设计**受控认证通道**或先确定 org，
**不得**靠放宽 `RLS_EXEMPT_TABLES` 绕过。已登记到需求基线 DR-B4 行。

---

## 4. 反向验证（**逐条判红**）

| 破坏 | 判红 |
|---|---|
| `api/deps.py` 的 `open_session(org_id=identity.org_id)` → `open_session()` | ✅ 判据 10 红 |
| 删掉 compose 的 `DATABASE_URL_OWNER` | ✅ 判据 7-5 红 |
| `env.py` 改回只认 `settings.database_url` | ✅ 判据 9 红 |
| 去掉 `system_session()` 里的 `info.pop(ORG_ID_INFO_KEY)` | ✅ 判据 11 红 |

⚠️ **一处"破坏方式不对"的教训**：判据 9 最初用**文本匹配**（`"database_url_owner" in text`），
去掉 owner 后**仍绿**——因为 `env.py` 的 **docstring 里提到了这个词**。已改成 **ast 匹配
代码里的属性访问**（注释 / docstring 不算数），改判红 ✔。这条正好是
「Dockerfile 里说了但没做」的同型病。

---

## 5. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | `/auth/login` 未实现 ⇒ 未来无 org 查 `users` 会 0 行（缺口 C） | 低 | 已登记需求基线；实现登录时必须一并设计受控认证通道 |
| 2 | `docs/adr/ADR-0003` §3.3 / `:87-88` 仍是旧谓词 | 低 | 按 **R5 不改 ADR 原文**，差异已在需求基线登记 |
| 3 | G-25（评测判据进 CI） | 中 | **下一批（P3-E）开工**；CI 的 `neo4j` service 已由 P3-B 建好 |

---

## 6. 复现命令

```bash
cd backend
uv run pytest -q tests/test_guardrails_rls.py            # 28 条
uv run python scripts/check_startup_readiness.py          # G-26 15 项
uv run python scripts/check_session_drift.py              # S1 Non-goals / S3 配置同步
```
