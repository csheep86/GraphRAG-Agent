# backend/CODEBUDDY.md — 后端作用域规则

> 本文件只作用于 `backend/`，与仓库根 `CODEBUDDY.md` 共同生效；冲突时以根规则为准。

## 1. 数据存储策略

| 存储 | 承担的数据 | 环境 | 状态 |
|---|---|---|---|
| **SQLite** | 关系型数据（`documents` 等）—— **PostgreSQL 的本地等价替身** | `development` / `test` | 在用 |
| **PostgreSQL** | 生产关系型数据；启用 RLS 做租户隔离 | `production` | 待 Sprint 4 接入 |
| **Neo4j** | 知识图谱：`(:KgVersion)` 版本状态机 + `(:Entity)` 实体与实体间关系 | 全环境 | 在用 |

- `DATABASE_URL` 默认 `sqlite:///./dev.db` 只允许出现在 `development` / `test`。
- `production` 环境若检测到 `sqlite` 驱动，**必须直接启动失败**，禁止静默降级。
- 依据：[`docs/adr/ADR-0003-tenant-isolation-rls.md`](../docs/adr/ADR-0003-tenant-isolation-rls.md) §3.6。
- 未启用 RLS 期间，`org_id` 过滤**只由应用层保证**（`app/services/documents.py`），
  **任何新增查询都必须带 `org_id` 条件**，不得绕过。

> SQLite 不是「临时兜底」而是 PG 的**开发态替身**：字段类型、约束与查询语义以 PG 为准，
> 两者的差异只允许出现在「RLS 是否由数据库强制」这一点上。

### 1.1 Neo4j 图谱与版本可见性（ADR-0002）

- 图谱数据**只能**经 `uv run python scripts/import_to_neo4j.py` 写入，遵循三段式：
  `(:KgVersion {status:'writing'})` → `MERGE` 实体 / 关系 → 置 `active`；
  异常路径删除该版本实体并把 `:KgVersion` 置 `failed`。
- **一致性铁律**：只消费 `status = 'active'` 的版本。
  - 读取入口唯一：`GraphService.fetch_active_kg_version()`；
  - 调用方显式传入版本时，`GraphService.fetch_kg_version_status()` 校验；
    非 `active`（`writing` / `failed` / `superseded` / 不存在）一律 **409 `KG_VERSION_NOT_ACTIVE`**，
    **严禁静默降级**到最新 active 版本。
- **故障语义边界**（三者必须严格区分，不得混为一谈）：

  | 情形 | 异常 | 对外的 HTTP |
  |---|---|---|
  | `Neo4j` 连不上 / 查询失败 | `GraphUnavailableError` | `501 NOT_IMPLEMENTED` |
  | 连得上但**没有** `active` 版本 | `NoActiveKgVersionError`（`GraphUnavailableError` 子类） | `409 KG_VERSION_NOT_ACTIVE`（`/graph`） |
  | 图谱可查但证据不足 | —（正常返回） | `200` + `refused = true` |

  `NoActiveKgVersionError` 刻意继承基类：既有的 `except GraphUnavailableError`
  不会漏网，业务层又能按需细分。混用会让前端无法区分
  「数据没准备好」与「后端挂了」。
- `:KgVersion` 状态机**暂落 Neo4j**；Sprint 4 接入 PG `kg_versions` 表后以 PG 为真源，
  Neo4j 侧节点类型与属性不变，`GraphService` 对外接口无需改动。
- 关系类型的契约投影规则见 `app/services/graphs.py::_relation_type`。

## 2. 认证态的临时兜底（**限期，必须偿还**）

- `X-Org-Id` / `X-Actor-Id` 请求头**仅在 `ALLOW_DEV_ORG_HEADER=true` 且非 production 时生效**。
- 这是 Sprint 1 无 M5 登录接口时的脚手架，**Sprint 3 接入 `POST /auth/login` 签发的 token 后必须移除**。
- `org_id` **严禁**从请求 body / query 读取（ADR-0003 §3.3）。

## 3. 契约同步（铁律）

1. 修改任何接口字段：**先改 `backend/app/schemas/` 的 Pydantic 模型**（后端模型是契约唯一真源）。
2. 执行 `uv run python scripts/export_openapi.py` 重新生成 `contracts/openapi.yaml`。
3. 生成物**必须提交**，禁止手工编辑 `contracts/openapi.yaml`。
4. 前端类型由阶段 3.2 的 `npm run gen:api` 生成，CI 在阶段 3.3 校验漂移。

## 4. 已登记的实现缺口

| 缺口 | 现状 | 依据 |
|---|---|---|
| PostgreSQL RLS + `SET LOCAL app.current_org` | 未实现；SQLite 下由应用层 `org_id` 过滤兜底 | ADR-0003 §3.1 / §3.2 |
| `kg_versions` 表（PG 真源） | 未建表；版本状态机暂落 Neo4j `(:KgVersion)` | ADR-0002 §2 |
| M3 完整 Agentic-RAG | 骨架：单轮 LLM + 图谱文本注入；**无** Tool 调用循环、**无** chunk 级引用反查 | M3 §4 |
| `AgentQueryResponse` 缺 `kg_nodes` / `kg_relations` / `token_usage` | ✅ 已偿还（Sprint 4.10.0.A）：契约已定义三字段并由 `AgentService` 填充 | 本文件 §3 |
| `GraphEdge.type` 枚举不含「实体↔实体」关系 | ✅ 已偿还（Sprint 4.10.0.B）：枚举扩展 `HAS_FINANCIAL_INDICATOR` / `OPERATES_SEGMENT` / `RELATED`，桥梁专有类型直通；未知类型仍兜底投影 `MENTIONS` + `properties.relation_name` | 本文件 §3 |
| 文件写入存储抽象层 | 只落 PG 元数据，`storage_key` 保持 NULL | M1 §4.3 |
| 契约 `description` 描述漂移 | `/upload`、`/graph`、`/agent/query` 的 `description` 仍写 Sprint 1/3 措辞，与已实装行为不符；**代码侧刻意不动**以免制造契约漂移 | 本文件 §3 |

### 4.1 阶段九已偿还的缺口

| 原缺口 | 完成情况 |
|---|---|
| `TaskManager.recover()` 启动回收 | ✅ `app/tasks/manager.py::recover_orphan_tasks`，由 lifespan startup 触发（ADR-0001 §3.2） |
| `GET /documents/{id}/graph` 真实查询 | ✅ 调 `GraphService.fetch_document_subgraph`，输出严格遵循 `DocumentGraphResponse` |
| `POST /agent/query` 真实问答 | ✅ 调 `AgentService.query`，含 409 版本校验 / 401 / 400 / 501 全分支 |
| Neo4j ↔ PG Saga 写入时序 | ⚠️ 三段式已在 `scripts/import_to_neo4j.py` 落实，但状态机落 Neo4j 而非 PG（见上表） |

> **契约零漂移**：阶段九只改路由函数体，**未动** 任何 `@router.*` 装饰器
> （`summary` / `description` / `responses` / `response_model` 全部保持原样），
> 因此 `uv run python scripts/export_openapi.py --check` 保持通过。

## 5. 常用命令

```bash
uv sync                                        # 安装依赖（提交 uv.lock）
uv run uvicorn app.main:app --reload           # 本地启动
uv run python scripts/export_openapi.py        # 导出契约
uv run python scripts/export_openapi.py --check # 校验契约是否漂移
uv run pytest                                  # 契约与行为测试
uv run ruff check . && uv run ruff format .
```
