# 多模态 RAG 后端 API 规格 v1.0（人类可读版）

| 项 | 内容 |
|---|---|
| **契约版本** | `1.0.0`（= `contracts/openapi.yaml` 的 `info.version`，由 `APP_VERSION` 常量注入） |
| **接口范围** | **严格 5 个核心接口**；specs 中其余端点草案（`/auth/login`、`/audit*`、`/affiliation/*`、`/internal/*`）留在草案态，Sprint 3 逐步纳入 |
| **机器可读真源** | [`contracts/openapi.yaml`](../contracts/openapi.yaml)（由后端 Pydantic 模型**生成**，禁止手工编辑） |
| **生成方式** | `cd backend && uv run python scripts/export_openapi.py` |
| **关联规格** | [`specs/m1-async-ingest.md`](../specs/m1-async-ingest.md)、[`specs/m2-extract-kg.md`](../specs/m2-extract-kg.md)、[`specs/m3-graphqa-citation.md`](../specs/m3-graphqa-citation.md)、[`specs/m5-permission-audit.md`](../specs/m5-permission-audit.md) |
| **关联决策** | [ADR-0001 异步任务](../docs/adr/ADR-0001-async-task-backend.md)、[ADR-0002 Neo4j/PG 一致性](../docs/adr/ADR-0002-neo4j-postgres-consistency.md)、[ADR-0003 租户隔离](../docs/adr/ADR-0003-tenant-isolation-rls.md) |

> 本文档描述**契约**（接口应该长什么样）；每个接口的**当前实现状态**单独标注（见 §5 与 §7）。契约与实现状态是两件事，**实现缺口不改变契约**。

---

## 1. 概述

- **Base URL**：同源部署，路径内嵌版本前缀 `/api/v1`。
  - 开发：`http://localhost:8000/api/v1`（`uv run uvicorn app.main:app --reload`）
  - 生产：由网关注入实际域名；OpenAPI 中 `servers` 仅声明 `/`，**避免出现双重前缀**。
- **文档入口**：Swagger UI `/docs`；原始结构 `/openapi.json`。
- **内容类型**：除上传接口为 `multipart/form-data` 外，请求 / 响应均为 `application/json; charset=utf-8`。
- **时间格式**：RFC 3339 UTC（如 `2026-09-16T08:30:00Z`）。
- **接口清单**

| # | Method | Path | 说明 | 实现状态 |
|---|---|---|---|---|
| 1 | `GET` | `/api/v1/health` | 健康检查（**豁免租户上下文**） | ✅ 真实 |
| 2 | `POST` | `/api/v1/documents/upload` | 上传文档，立即返回 `task_id`（异步） | ✅ 真实（不注册执行体） |
| 3 | `GET` | `/api/v1/documents/{document_id}/status` | 查询解析状态 | ✅ 真实 |
| 4 | `GET` | `/api/v1/documents/{document_id}/graph` | 文档图谱子图 | ⛔ 501 占位 |
| 5 | `POST` | `/api/v1/agent/query` | 图谱问答 + 引用 | ⛔ 501 占位 |

---

## 2. 认证与租户隔离（**全接口强制**）

### 2.1 认证方案

OpenAPI 中登记为 `bearerAuth`（`http bearer` / `bearerFormat: JWT`）：

```
Authorization: Bearer <token>
```

- 除 `/api/v1/health` 外，**5 个接口中的其余 4 个全部要求认证**；缺少或无法解析 → `401 UNAUTHORIZED`。
- **Sprint 1 临时实现**（限期）：token 只支持开发态格式 `Bearer dev.<org_id>.<actor_id>`。
  Sprint 3 由 M5 `POST /auth/login` 签发的 JWT 取代，见 `backend/CODEBUDDY.md` §2。

### 2.2 `org_id` 来源铁律（ADR-0003 §3.3）

- `org_id` **只能**从认证态解析；**严禁**从请求 body / query 读取（否则可被篡改）。
- **开发态兜底**（`ALLOW_DEV_ORG_HEADER=true` 且 `APP_ENV ≠ production`，默认关闭）：

  | 请求头 | 必填 | 说明 |
  |---|---|---|
  | `X-Org-Id` | 否 | 租户 id，缺省取 `DEFAULT_ORG_ID` |
  | `X-Actor-Id` | 否 | 操作者 id，缺省取 `DEFAULT_ACTOR_ID` |

  这两个头**已登记进契约参数**（因此前端可在开发态直接联调），但**必须**在 Sprint 3 随 M5 登录一并移除。

### 2.3 隔离语义

| 场景 | HTTP | `code` |
|---|---|---|
| 未认证 / token 无法解析 | 401 | `UNAUTHORIZED` |
| 访问的 `document_id` 属于**其它租户** | **403** | `FORBIDDEN` |
| 资源在**当前租户内不存在** | 404 | `DOCUMENT_NOT_FOUND` / `NOT_FOUND` |
| `/api/v1/health` | 200 | —（不要求认证、不返回业务数据） |

> **跨租户一律 403 而非 404**：这是 M5 §3 验收 1 的显式要求，代价是可探测资源是否存在（已接受，见 `backend/app/services/documents.py` 的注释）。

### 2.4 数据库层（ADR-0003）

- 目标态：PostgreSQL RLS + 事务内 `SET LOCAL app.current_org = :org_id`。
- **Sprint 1 临时兜底**：`DATABASE_URL` 默认 `sqlite:///./dev.db`，**SQLite 不支持 RLS**；
  此期间 `org_id` 过滤**只由应用层保证**，且 `APP_ENV=production` 时启动即失败（禁止静默降级）。
  详见 [ADR-0003 §3.6](../docs/adr/ADR-0003-tenant-isolation-rls.md) 与 `backend/CODEBUDDY.md` §1。

---

## 3. 通用约定

### 3.1 `trace_id`（M1 验收 7 / M5 §5.3）

| 方向 | 约定 |
|---|---|
| 请求头 | `X-Trace-Id` **可选**透传；必须是合法 UUID，否则服务端重新生成（不报错） |
| 响应头 | `X-Trace-Id` **恒回显**（含 4xx / 5xx / 500） |
| 响应体 | 成功响应与错误体中的 `trace_id` 与响应头**完全一致** |

### 3.2 统一错误响应

**所有** 4xx / 5xx 均为四字段结构（`CODEBUDDY.md`「错误响应规范」）：

```json
{
  "code": "FORBIDDEN",
  "message": "Cross-tenant access denied",
  "detail": { "document_id": "3f1a9c2e-...", "reason": "cross_tenant_access" },
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `code` | `ErrorCode` | ✅ | 业务错误码，取值见 §4 |
| `message` | `string` | ✅ | 面向调用方的简短英文摘要，便于日志检索 |
| `detail` | `object \| null` | ❌ | 结构化补充信息；**敏感字段一律不得出现** |
| `trace_id` | `string` | ✅ | 与响应头 `X-Trace-Id` 一致 |

- **HTTP 状态码与业务错误码分离**：状态码表达「传输 / 框架层」语义，`code` 表达「业务」语义。
- **校验失败统一为 `400 VALIDATION_ERROR`**，不用 422；`detail.errors` 为字段级原因数组，且**已剥离请求原文**（`input` / `ctx` / `url` 不外泄）。
- **未注册路由**返回 `404 NOT_FOUND`，同样使用四字段结构（不是 HTML/纯文本）。

### 3.3 其它

- **分页**：v1.0 无列表型接口，故未定义分页约定；Sprint 3 引入列表接口时在此补充。
- **幂等**：v1.0 无幂等键约定；重复上传同一文件会产生新的 `task_id`（去重策略属 M1 P2 范围）。
- **限流**：契约未声明具体阈值；`CODEBUDDY.md` 要求上线前接入 `slowapi`。

---

## 4. 错误码总表

| `code` | HTTP | 含义 | 决策来源 | 触发接口 |
|---|---|---|---|---|
| `VALIDATION_ERROR` | 400 | 请求体 / 查询 / 路径参数未通过 Pydantic 校验 | CODEBUDDY.md | 5 |
| `UNAUTHORIZED` | 401 | 缺少或无法解析认证态 | M5 §3 验收 1 | 2、3、4、5 |
| **`FORBIDDEN`** | **403** | **跨租户访问被拒（ADR-0003）** | **ADR-0003 §3.3** | 2、3、4、5 |
| `NOT_FOUND` | 404 | 通用资源不存在（含未注册路由） | CODEBUDDY.md | 任意 |
| `DOCUMENT_NOT_FOUND` | 404 | 文档不存在 / 不在当前租户可见范围 | M1 §5.4 | 3、4 |
| `FILE_TOO_LARGE` | 413 | 超过 `MAX_UPLOAD_SIZE_MB`（默认 100MB） | M1 §3 验收 2 | 2 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | MIME 不在白名单 | M1 §3 验收 3 | 2 |
| **`KG_VERSION_NOT_ACTIVE`** | **409** | 指定 `kg_version` 非 active（`writing`/`failed`/`superseded`） | **ADR-0002 §3.2** | 4、5 |
| **`TASK_INTERRUPTED`** | **409** | 进程重启导致在途任务被回收置 `failed` | **ADR-0001 §3.2** | 3（作为 `error.code` 呈现） |
| `NOT_IMPLEMENTED` | 501 | 契约已定稿、实现留待 Sprint 3 | Sprint 1 边界 | 4、5 |
| `INTERNAL_ERROR` | 500 | 未预期的服务端异常（已记日志，含 `trace_id`） | CODEBUDDY.md | 任意 |
| `HTTP_ERROR` | 原样 | 未登记 HTTP 状态的兜底，保留原始状态码语义 | CODEBUDDY.md | 任意 |

**关键约定**

1. `KG_VERSION_NOT_ACTIVE` **一律 409**。M2 §5.4 原草案写作 404，**已作废**并同步修正（依据 ADR-0002 §3.2 与 M3 §4.1）。
   语义：查询层只认 `status = active`，指定非 active 版本时**必须显式拒绝，严禁静默降级**到最新版。
2. `TASK_INTERRUPTED` 不单独占用一个端点——它是**文档状态机**的一种失败原因，通过 `GET /documents/{id}/status` 的 `error.code` 暴露（M5 §3 验收 4）。
3. 错误码枚举在 `contracts/openapi.yaml` 中以 `ErrorCode` schema 完整列出，
   并带 `x-enum-descriptions`（中文语义）与 `x-enum-sources`（规格 / ADR 出处），前端可据此做文案映射。
4. 新增错误码的顺序：**先改 `backend/app/core/errors.py`** → 重新导出契约 → 更新本文档。

---

## 5. 接口详解

### 5.1 `GET /api/v1/health` — 健康检查

| 项 | 内容 |
|---|---|
| 认证 | **不需要**（唯一豁免租户上下文的接口） |
| 参数 | 无（连 `X-Trace-Id` 都不在参数表中，但仍会被回显） |
| 实现状态 | ✅ 真实可用 |

**200 响应**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "checks": { "database": "up" },
  "time": "2026-09-16T08:30:00Z",
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | `"ok" \| "degraded"` | ✅ | `degraded` = 依赖异常但进程可服务 |
| `version` | `string` | ✅ | 与 `openapi.yaml` 的 `info.version` 一致 |
| `checks.database` | `"up" \| "down"` | ✅ | 仅探测连通性（`SELECT 1`），**不代表 RLS 已生效** |
| `time` | `date-time` | ✅ | 服务端 UTC 时间 |
| `trace_id` | `string` | ✅ | — |

> **依赖异常时仍返回 200**，只把 `status` 降级为 `degraded`——避免负载均衡因单实例依赖抖动直接摘除全部流量。

### 5.2 `POST /api/v1/documents/upload` — 上传文档（异步）

| 项 | 内容 |
|---|---|
| 认证 | 必须（`bearerAuth`，或开发态 `X-Org-Id` / `X-Actor-Id`） |
| 请求体 | `multipart/form-data`，字段名 **`file`** |
| 限制 | MIME 白名单：`application/pdf`、`application/vnd.openxmlformats-officedocument.wordprocessingml.document`、`text/csv`；单文件 ≤ 100MB |
| 实现状态 | ✅ 校验 + 落库真实；⛔ **不注册异步执行体**，文档会停在 `pending` |

**200 响应**

```json
{
  "task_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
  "status": "pending",
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | `uuid` | ✅ | 与 `documents.id` 一致；M2 抽取任务复用同一 id 空间 |
| `status` | `"pending"` | ✅ | 受理后恒为 `pending`（枚举仅此一值） |
| `trace_id` | `string` | ✅ | — |

**错误分支**

| HTTP | `code` | 触发条件 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 缺少 `file` 字段等 |
| 401 | `UNAUTHORIZED` | 无认证态 |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | MIME 不在白名单（`detail.allowed_mime_types` 给出白名单） |
| 413 | `FILE_TOO_LARGE` | 超过 `detail.max_size_bytes` |

**安全 / 隐私**

- 文件名**以 SHA-256 落库**（`documents.filename_hash`），响应与日志**均不含原文**。
- 存储键格式（ADR-0003 §3.5）：`{org_id}/{doc_id}/{filename_hash}`，`completed` 后才写入 `storage_key`（M1 §4.3）。

> **已知局限**：大小校验发生在 multipart 已接收之后（Starlette 先落临时文件），属**非流式限流**；Sprint 3 需在反向代理 / 网关层追加同源限制。

### 5.3 `GET /api/v1/documents/{document_id}/status` — 查询解析状态

| 项 | 内容 |
|---|---|
| 认证 | 必须 |
| 路径参数 | `document_id`（uuid） |
| 实现状态 | ✅ 真实（读 `documents` 表） |

**200 响应**

```json
{
  "task_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
  "status": "processing",
  "progress": null,
  "error": null,
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | `uuid` | ✅ | 等于路径上的 `document_id` |
| `status` | `"pending" \| "processing" \| "completed" \| "failed"` | ✅ | M1 硬约束 H1 的状态机，**不得新增取值** |
| `progress` | `number \| null`（0–1） | ❌ | 粗粒度进度；不可估计时为 `null`。当前映射：`pending→0.0`、`completed→1.0`、其余 `null` |
| `error` | `DocumentError \| null` | ❌ | 仅 `status = failed` 时非空 |
| `trace_id` | `string` | ✅ | — |

**`error` 子结构**

```json
{ "code": "TASK_INTERRUPTED", "message": "Task interrupted by process restart", "detail": null }
```

- `error` **不含** `trace_id`（同一响应体已在外层提供）。
- `detail` 中**不回显** `documents.error_detail` 原文（M1 §4.1 标注敏感）。
- 契约同时保留 `documents.status = failed` 时**不会**再出现 `409` 顶层错误的约定：失败是**资源状态**，不是本次请求的错误。

**错误分支**：400（路径参数非 UUID）、401、**403**（跨租户）、404（不存在）。

> 轮询建议：首次 2s，3 次后降为 10s。

### 5.4 `GET /api/v1/documents/{document_id}/graph` — 文档图谱子图

| 项 | 内容 |
|---|---|
| 认证 | 必须 |
| 路径参数 | `document_id`（uuid） |
| 实现状态 | ⛔ **501 `NOT_IMPLEMENTED`**（Neo4j 查询属 Sprint 3） |
| 规格出处 | `specs/m2-extract-kg.md` §5.4（Sprint 1 已登记） |

**200 响应（契约）**

```json
{
  "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
  "kg_version": "20260320T1430Z-01H9X9ABCDEF",
  "version_status": "active",
  "nodes": [
    {
      "id": "e-001",
      "label": "Entity",
      "entity_type": "公司",
      "canonical_name": "示例科技有限公司",
      "confidence": 0.93,
      "kg_version": "20260320T1430Z-01H9X9ABCDEF"
    }
  ],
  "edges": [
    {
      "id": "r-001",
      "type": "AFFILIATED_WITH",
      "source": "e-001",
      "target": "e-002",
      "properties": { "share_pct": 51.0, "since": "2021-03-01" }
    }
  ],
  "node_count": 1,
  "relation_count": 1,
  "truncated": false,
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `doc_id` | `uuid` | ✅ | — |
| `kg_version` | `string` | ✅ | 本次返回的图谱版本，取自当前 `active` 版本 |
| `version_status` | `"active"` | ✅ | **恒为 `active`**，是 ADR-0002 一致性在契约上的可见表达 |
| `nodes[].label` | `"Document" \| "Chunk" \| "Entity" \| "Evidence"` | ✅ | 对齐 Neo4j 标签 |
| `nodes[].entity_type` / `canonical_name` / `confidence` | — | ❌ | 仅 `:Entity` 有意义 |
| `nodes[].kg_version` | `string` | ✅ | 必须等于响应的 `kg_version` |
| `edges[].type` | `"HAS_CHUNK" \| "MENTIONS" \| "SUPPORTED_BY" \| "AFFILIATED_WITH" \| "SUPPLIES_TO" \| "PARTY_TO"` | ✅ | 对齐 Neo4j 关系类型 |
| `edges[].source` / `target` | `string` | ✅ | 节点 `id` |
| `edges[].properties` | `object` | ✅ | 关系属性（如 `share_pct` / `since` / `amount` / `role`） |
| `node_count` / `relation_count` | `int` | ✅ | 截断后的实际条数 |
| `truncated` | `bool` | ✅ | 是否因超过 **500 节点**上限被截断（对齐 M3 §3 验收 1） |

**隐私**：**刻意不含 `pii_flags`**（M2 §5.3 禁止外泄）。

**错误分支**

| HTTP | `code` | 触发条件 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `document_id` 非 UUID |
| 401 | `UNAUTHORIZED` | 无认证态 |
| 403 | `FORBIDDEN` | 跨租户（ADR-0003） |
| 404 | `DOCUMENT_NOT_FOUND` | 本租户内不存在该文档 |
| **409** | **`KG_VERSION_NOT_ACTIVE`** | 该文档无 `active` 版本。**严禁静默降级**到旧版本或返回空图（ADR-0002 §3.2） |
| 501 | `NOT_IMPLEMENTED` | Sprint 1 当前行为 |

**架构约束**（M2 §5.5）：图谱查询**必须**经 M2 的查询层，绕过 M2 直写 Neo4j 应被 lint / CI 拦截。

### 5.5 `POST /api/v1/agent/query` — 图谱问答

| 项 | 内容 |
|---|---|
| 认证 | 必须 |
| 实现状态 | ⛔ **501 `NOT_IMPLEMENTED`**（M3 检索链路属 Sprint 3） |

**请求体**

```json
{
  "question": "A 公司的子公司的供应商是否同时是 B 公司的股东？",
  "scope": "cross_doc",
  "doc_id": null,
  "kg_version": "20260320T1430Z-01H9X9ABCDEF"
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `question` | `string` | ✅ | `minLength: 1`；单轮，不做多轮上下文 |
| `scope` | `"single_doc" \| "cross_doc"` | ❌ | 默认 `cross_doc`；为 `single_doc` 时 **`doc_id` 必填**，否则 400 |
| `doc_id` | `uuid \| null` | ❌ | 仅 `single_doc` 使用 |
| `kg_version` | `string \| null` | ❌ | 缺省取最新 `active` 版本；显式传入非 active 版本 → **409** |

**200 响应（契约）**

```json
{
  "answer": "是。示例子公司 A 的供应商 C 同时持有 B 公司 12% 股权 [source: doc-9/page-3/chunk-12]",
  "citations": [
    {
      "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
      "page": 3,
      "chunk_id": "chunk-12",
      "char_offset": 480,
      "snippet": "……供应商 C 持有本公司 12% 股权……"
    }
  ],
  "route": "m3_graphqa",
  "confidence": "high",
  "refused": false,
  "refusal_reason": null,
  "kg_version": "20260320T1430Z-01H9X9ABCDEF",
  "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `answer` | `string` | ✅ | 含 `[source: ...]` 标记；**拒答时恒为 `"无法回答"`** |
| `citations[]` | `object[]` | ✅ | `{doc_id, page, chunk_id, char_offset, snippet}` |
| `route` | `"m3_graphqa" \| "m4_affiliation"` | ✅ | 意图路由结果 |
| `confidence` | `"high" \| "medium" \| "low"` | ✅ | `low` 时前端**必须**标记「建议人工复核」（M3 §3 验收 6） |
| `refused` | `bool` | ✅ | 是否拒答 |
| `refusal_reason` | `"no_grounded_evidence" \| "out_of_scope" \| "low_confidence" \| null` | ❌ | 仅 `refused = true` 时非空 |
| `kg_version` | `string` | ✅ | 实际使用的版本（必为 `active`） |
| `trace_id` | `string` | ✅ | — |

**硬约束**

1. **引用覆盖率 100%**：`refused = false` 时，答案的每个事实句都必须能回溯到 `citations[]`；
   不足即**必须拒答**，**严禁**编造引用（M3 §3 验收 3 / 反证条件 F3）。
2. `POST /qa/{id}/feedback` 等审计 / 反馈端点**不在 v1.0 契约内**（严格 5 接口）。

**错误分支**：400（校验 / `single_doc` 缺 `doc_id`）、401、403、**409 `KG_VERSION_NOT_ACTIVE`**、501。

---

## 6. 契约同步机制（机器强制）

```
backend/app/schemas/*.py  ──(唯一真源)──►  uv run python scripts/export_openapi.py
                                                │
                                                ▼
                                    contracts/openapi.yaml  （提交入库）
                                                │
                               阶段 3.2：frontend  npm run gen:api
                                                ▼
                                    frontend/…/api-types.ts
                                                │
                               阶段 3.3：CI 重新生成 → git diff --exit-code
```

1. **真源是后端 Pydantic 模型**，不是 YAML。改字段 → 先改模型 → 重新导出 → 提交生成物。
2. **禁止手工编辑** `contracts/openapi.yaml`（文件头已写入警示注释）。
3. 导出**确定性**保证（否则 CI diff 永远失败）：
   - `info.version` 取常量 `APP_VERSION`，不含时间戳 / 随机值；
   - 映射统一 `sort_keys=True`，路径预先排序；
   - 统一 UTF-8 + `\n`，YAML 宽度固定。
   - 自检：`uv run python scripts/export_openapi.py --check`（CI 用，文件不一致即非 0 退出）。
4. 校验当前一致性（本地即可跑）：

   ```bash
   cd backend
   uv run python scripts/export_openapi.py
   git diff --exit-code ../contracts/openapi.yaml
   uv run pytest -q
   ```

---

## 7. 实现状态与 Sprint 3 债务

| 项 | Sprint 1 状态 | 偿还动作 |
|---|---|---|
| `/health` | ✅ 真实 | — |
| `/documents/upload` | ✅ MIME/大小校验 + 落 `documents`（`pending`） | 接入 `TaskManager.submit()` |
| `/documents/{id}/status` | ✅ 读库 + 403/404 语义 | 状态流转由 worker 驱动 |
| `/documents/{id}/graph` | ⛔ 501 | Neo4j 子图查询 + **仅取 active `kg_version`**（ADR-0002） |
| `/agent/query` | ⛔ 501 | M3 意图路由 + 引用生成 + 拒答兜底 |
| `TaskManager.recover()` | ⛔ 未实现（`TASK_INTERRUPTED` 暂不会被真实产生） | ADR-0001 §3.2：启动扫描孤儿任务置 `failed` |
| Saga 写入时序 / `kg_versions.status` | ⛔ 未启用 | ADR-0002 §2 |
| PostgreSQL RLS + `SET LOCAL` | ⛔ SQLite 兜底（**不支持 RLS**） | ADR-0003 §3.6 |
| 开发态 `X-Org-Id` / `X-Actor-Id` | ⚠️ 限期兜底 | 随 M5 登录一并移除 |
| 文件存储抽象层 | ⛔ 只落元数据，`storage_key` 保持 NULL | M1 §4.3 |
| 限流（`slowapi`） | ⛔ 未接入 | CODEBUDDY.md 安全底线 |
| Alembic 迁移 | ⛔ 启动时 `create_all()` | Sprint 3 引入 |

> 本表与 `backend/CODEBUDDY.md` §4 保持同步：**新增缺口必须同时登记两处**，否则视为未完成。

---

## 8. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-09-16 | 首版：5 个核心接口、统一错误体、12 个错误码、租户隔离与 403/409 语义定稿 |
