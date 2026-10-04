# P3-D 提案 —— 「哪里会漏绑 org」审计的收口（P3-C 未决 #1）

| 项 | 内容 |
|---|---|
| **批次** | P3-D |
| **日期** | 2026-10-04 |
| **触发** | P3-C 未决 #1：审计「哪些路径会不绑 org 就去查租户表」 |
| **审计结论** | **当前 `app/` 运行时里没有"漏绑 org 却查租户表"的业务路径**（唯一不绑 org 的 `system_session()` 只调受控函数 `app.list_tenant_orgs()`）。但审计暴露出**三个结构性缺口**，本批逐个收口 |
| **状态** | 🟡 进行中 |

---

## 0. 审计结论（事实，非推测）

| 路径 | 是否绑 org | 结论 |
|---|---|---|
| HTTP 路由的 `DbSession`（`api/deps.py:90`） | ✅ `identity.org_id` | 安全 |
| 后台任务 8 个入口（`tasks/registry.py:110/221/325/488/609/717/884/1051`） | ✅ `spec.org_id` | 安全 |
| 中间件 / 异常处理器 / Agent / CLI | ✅ | 安全 |
| A6 启动回收（`tasks/manager.py:197/254`，`system_session()`） | ❌ **刻意不绑** | 只调受控函数 `app.list_tenant_orgs()`（`SECURITY DEFINER` + `rls_probe NOLOGIN BYPASSRLS`）⇒ **受控通道，不是 bug**；同一个 session 直接查 `documents` **依然 0 行** |
| `/api/v1/health` | ❌ | 只 `SELECT 1`，不碰租户表 ⇒ 不受影响 |
| `LocalAuthProvider` | — | **当前不查库**（dev token / header），`/auth/login` 尚未实现 ⇒ 无该路径 |

---

## 1. 本批要收的三个缺口

### 缺口 A（**高**）：部署的**升级路径是断的**——Alembic 以受限角色跑 DDL

P3-A 把 compose 的 `DATABASE_URL` 切成了受限角色 `app_rls`，但：

- `migrations/env.py:38-39` 只认 `settings.database_url`（= `app_rls`）；
- 仓库里**根本不存在** `database_url_owner` 这个配置（`DATABASE_URL_OWNER` 目前只被
  `tests/pg_scratch.py` / `conftest.py` 用 `os.environ` 直接读）；
- compose 的 backend **没有** `DATABASE_URL_OWNER`。

⇒ 在部署形态下跑 `alembic upgrade head`（`deployment-spec.md` §7.2 的升级路径）会以
`app_rls` 执行 `CREATE` / `ALTER` ⇒ **权限不足直接失败**（`app_rls` 只有 DML）。
**症状不是"隔离失效"，是"升级不了"**——同样是静默埋雷：没人会在平时发现它。
顺带 `scripts/migrate_add_suspicion_causes.py` 也走应用 engine（`ALTER TABLE` ⇒ 同样会失败）。

修法：新增 `Settings.database_url_owner`（env `DATABASE_URL_OWNER`）；`migrations/env.py`
**优先**用它（没有则回落到 `database_url`）；compose 的 backend 补上该变量；脚本同样改走 owner。

### 缺口 B（**中**）：测试脚手架会**掩盖**漏绑

`tests/conftest.py:112-119` 给 `SessionLocal.kw["info"]` 塞了默认 org ⇒ 任何 `open_session()`
（**连 `system_session()` 在内**）在测试里都自动带着默认租户。后果：

- 有人把 `open_session(org_id=identity.org_id)` 改成 `open_session()` ⇒ 生产 0 行、**测试仍绿**；
- 有人在 `system_session()` 里直接查租户表 ⇒ 生产 0 行、**测试看得到默认租户数据**。

修法两条（都做，各管一段）：

1. `system_session()` **显式清掉** org（不管 `SessionLocal` 有没有默认值）⇒ 系统通道在
   测试与生产**语义一致**（当前不一致，是脚手架造成的假象）；
2. **G-26 判据 9（静态）**：`app/` 下所有 `open_session(` / `session_scope(` 调用点**必须
   显式传 `org_id=`**（白名单：`app/db/session.py` 内部两处）⇒ 漏传即红灯。

### 缺口 C（**低**，本批**只登记不实现**）

`/auth/login` 尚未实现，且 `users` **不是**豁免表 ⇒ 未来若以无 org 的 `app_rls` 会话按
username 查 `users`，会稳定得到 **0 行**（不是报错）。届时必须走**受控认证通道**或先确定 org。
登记到需求基线，不在本批设计。

---

## 2. 出口判据

1. `pytest` passed 不减（889 起跑，+2 = 判据 9 + 判据 7 扩展）；
2. 判据 9 与判据 7 扩展**各自反向验证判红**（删一处 `org_id=` / 去掉 compose 的 owner 变量 / env.py 不优先 owner）；
3. **实测**：以受限角色跑 `alembic upgrade head` 会失败、以 owner 跑成功（把这个"它真的会断"变成证据）；
4. 全部门禁：ruff 双绿 / 接缝 OK 10 / 契约零漂移。

---

## 3. Non-goals（本批**不做**）

1. ❌ **不实现** `/auth/login` 或任何认证特权通道（缺口 C 只登记）；
2. ❌ **不改** `system_session()` 之外的会话语义，不改 `open_session` 的签名；
3. ❌ **不动** A6 / A7 受控函数本体与白名单；
4. ❌ **不做** G-25（评测判据进 CI）——本批之后另开批次；
5. ❌ **不改**契约 / ADR-0003 原文（守 **R5**，差异登记在需求基线）；
6. ❌ **不改**租户表清单 / 豁免表。
