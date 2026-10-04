# P3-D 任务清单 —— 「漏绑 org」审计收口（P3-C 未决 #1）

> 边界见 `proposal.md` §3（**开工前先读 Non-goals**）。起跑：`pytest` **889 passed**。

## 缺口 A：部署升级路径（Alembic 无权 DDL）

- [x] **A1** `app/core/config.py`：新增 `database_url_owner: str | None = None`（env `DATABASE_URL_OWNER`）
- [x] **A2** `migrations/env.py`：URL **优先**取 owner（回落 `database_url`），注释写明"DDL 必须 owner"
- [x] **A3** `deploy/docker-compose.yml`：backend 补 `DATABASE_URL_OWNER`（`app_owner` + `APP_OWNER_PASSWORD`）
- [x] **A4** `scripts/migrate_add_suspicion_causes.py`：改走 owner（无 owner 配置时**明确报错**，不要静默用受限角色）
- [x] **A5** 实测取证：以 `app_rls` 跑 `alembic upgrade head` ⇒ **失败**；以 owner ⇒ 成功
- [x] **A6** G-26 **判据 7 扩展**：compose 必须给 backend 提供 `DATABASE_URL_OWNER`；`migrations/env.py`
      必须优先取 owner。反向验证：删掉 compose 那行 / env.py 改为只认 `database_url` ⇒ 各自判红

## 缺口 B：测试脚手架掩盖漏绑

- [x] **B1** `app/db/session.py::system_session()`：显式清 org ⇒ 系统通道在**测试与生产语义一致**
- [x] **B2** G-26 **判据 9（静态）**：`app/` 下所有 `open_session(` / `session_scope(` 调用点必须**显式传 `org_id=`**
      （白名单：`app/db/session.py` 内两处）。反向验证：任一调用点删掉 `org_id=` ⇒ 判红

## 缺口 C：只登记

- [x] **C1** 需求基线登记「`/auth/login` 未实现 ⇒ 未来无 org 查 `users` 会 0 行」；不实现

## 收口

- [x] **D1** 文档：需求基线 DR-B4（升级路径走 owner）/ G-26 行；`docs/deployment-spec.md` §7.2
- [x] **D2** 门禁：pytest（+2）/ ruff 双绿 / 接缝 OK 10 / 契约零漂移 / readiness 条数核对
- [x] **D3** `changes/P3-D/integration-log.md`；`changes/P3-C` 未决 #1 关闭

## 不做（改完回头逐条对照）

1. 实现 `/auth/login` 或认证特权通道
2. 改 `open_session` 签名 / 其他会话语义
3. 改 A6 / A7 受控函数本体与白名单
4. G-25（另开批次）
5. 改契约 / ADR-0003 原文
6. 改租户表清单 / 豁免表
