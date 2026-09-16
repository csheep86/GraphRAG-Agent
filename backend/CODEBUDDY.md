# backend/CODEBUDDY.md — 后端作用域规则

> 本文件只作用于 `backend/`，与仓库根 `CODEBUDDY.md` 共同生效；冲突时以根规则为准。

## 1. 数据库临时兜底声明（**限期，必须偿还**）

> **SQLite 仅作为 Sprint 1 契约验证阶段的临时兜底，不支持 RLS。**
> **Sprint 3 集成 Neo4j + PostgreSQL 时，必须切换到 PostgreSQL 并启用 RLS。**

- `DATABASE_URL` 默认 `sqlite:///./dev.db` 只允许出现在 `development` / `test`。
- `production` 环境若检测到 `sqlite` 驱动，**必须直接启动失败**，禁止静默降级。
- 依据：[`docs/adr/ADR-0003-tenant-isolation-rls.md`](../docs/adr/ADR-0003-tenant-isolation-rls.md) §3.6。
- 未启用 RLS 期间，`org_id` 过滤**只由应用层保证**（`app/services/documents.py`），
  **任何新增查询都必须带 `org_id` 条件**，不得绕过。

## 2. 认证态的临时兜底（**限期，必须偿还**）

- `X-Org-Id` / `X-Actor-Id` 请求头**仅在 `ALLOW_DEV_ORG_HEADER=true` 且非 production 时生效**。
- 这是 Sprint 1 无 M5 登录接口时的脚手架，**Sprint 3 接入 `POST /auth/login` 签发的 token 后必须移除**。
- `org_id` **严禁**从请求 body / query 读取（ADR-0003 §3.3）。

## 3. 契约同步（铁律）

1. 修改任何接口字段：**先改 `backend/app/schemas/` 的 Pydantic 模型**（后端模型是契约唯一真源）。
2. 执行 `uv run python scripts/export_openapi.py` 重新生成 `contracts/openapi.yaml`。
3. 生成物**必须提交**，禁止手工编辑 `contracts/openapi.yaml`。
4. 前端类型由阶段 3.2 的 `npm run gen:api` 生成，CI 在阶段 3.3 校验漂移。

## 4. 已登记的实现缺口（Sprint 3 偿还）

| 缺口 | 现状 | 依据 |
|---|---|---|
| `TaskManager.recover()` 启动回收 | 未实现；`documents.status` 会停留 `pending` | ADR-0001 §3.2 |
| Neo4j ↔ PG Saga 写入时序 | 未实现；`kg_versions.status` 未启用 | ADR-0002 §2 |
| PostgreSQL RLS + `SET LOCAL app.current_org` | 未实现 | ADR-0003 §3.1 / §3.2 |
| `GET /documents/{id}/graph` 真实查询 | 返回 501 | 本文件 §4 |
| `POST /agent/query` 真实问答 | 返回 501 | M3 §4 |
| 文件写入存储抽象层 | 只落 PG 元数据，`storage_key` 保持 NULL | M1 §4.3 |

## 5. 常用命令

```bash
uv sync                                        # 安装依赖（提交 uv.lock）
uv run uvicorn app.main:app --reload           # 本地启动
uv run python scripts/export_openapi.py        # 导出契约
uv run python scripts/export_openapi.py --check # 校验契约是否漂移
uv run pytest                                  # 契约与行为测试
uv run ruff check . && uv run ruff format .
```
