# M1 · 多模态文档接入与异步解析 — MVP 规格说明书

> **文档编号**：spec-m1
> **版本**：v1.0
> **状态**：MVP 规格（v1.0.0 已交付，实现态见 backend/CODEBUDDY.md §4）
> **上游依据**：`docs/02-product-outline.md` §3.2 M1
> **关联 Prompts**：`prompts/document_parse_v1.md`
> **关联研究结论**：`01-research.md` §3.4 验证里程碑 M0–M1；假设 A3（解析质量实测）
> **关联大纲**：`02-product-outline.md` §3.2 M1 + §6 准入线
> **关联 ADR**：[ADR-0001 异步任务后端选型](../docs/adr/ADR-0001-async-task-backend.md)、[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**5 个功能点**，严格沿用 outline §3.2）

1. **PDF / DOCX / CSV 上传 + MIME 与大小校验**（单文件 ≤ 100MB，MIME 白名单）
2. **上传接口立即返回 `task_id`**（UUIDv4），后端异步执行解析
3. **前端轮询 `GET /documents/{id}/status`**，状态机 `pending → processing → completed / failed`
4. **解析失败指数退避重试**（tenacity，初始 1s、倍数 2、上限 3 次）
5. **每请求携带 `trace_id` 进入下游链路**（为 M5 审计提供锚点）

### 1.2 Out of Scope（明确不做）

- **图片 / 视频 / 网页等扩展输入**（MVP 不含，属 P2）
- **文档版本对比 / 合并**（属 P2 法务条款一致性扩展）
- **文档加密 / DRM / 水印**（属 P2 企业治理增强）
- **实时协作编辑**（不做）
- **跨系统连接器**（ERP / OA / 工单 / 邮件）（属 P2 扩展 E5）

---

## 2. 核心用户故事

- 作为**审计 / 财会用户**，我希望上传 PDF / DOCX / CSV 后立即得到一个 `task_id`，**不必长时间等待同步返回**，以便我能在等待期间继续操作界面。
- 作为**审计 / 财会用户**，我希望前端能实时显示文档解析进度（`pending / processing / completed / failed`），以便我知道何时可以开始查询或识别。
- 作为**系统运维人员**，我希望解析失败时系统能**自动指数退避重试**，并在最终失败时给出明确的错误码与 `trace_id`，以便我能快速定位问题。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。每条 In Scope 功能点至少 1 条验收。

1. **WHEN** 用户上传一个 ≤ 100MB 且 MIME 在白名单内的 PDF / DOCX / CSV 文件，**THEN** 接口立即返回 `{task_id, status: "pending"}` 与 HTTP 200，**AND** 响应时间 P95 ≤ 500ms，**AND** 返回的 `task_id` 为 UUIDv4 格式。
2. **WHEN** 用户上传的文件超过 100MB，**THEN** 接口返回 HTTP 413 + 错误码 `FILE_TOO_LARGE`，**AND** 响应体符合 `{code, message, detail, trace_id}`，**AND** 不触发任何后端解析任务。
3. **WHEN** 用户上传的文件 MIME 不在白名单（`application/pdf`、`application/vnd.openxmlformats-officedocument.wordprocessingml.document`、`text/csv`），**THEN** 接口返回 HTTP 415 + 错误码 `UNSUPPORTED_MEDIA_TYPE`，**AND** 不写入存储。
4. **WHEN** 任务进入 `processing` 后 MinerU 解析失败，**THEN** tenacity 触发指数退避重试（初始 1s、倍数 2、上限 3 次），**AND** 最终失败时 `documents.status` 置为 `failed` 且 `error_code` / `error_detail` 落库，**AND** M5 写一条 `document.parse.fail` 审计。
5. **WHEN** 前端轮询 `GET /documents/{id}/status`，**THEN** 响应包含 `{task_id, status, progress?, error?}`，**AND** `status` 仅在 `[pending, processing, completed, failed]` 之内，**AND** 轮询间隔建议首次 2s、3 次后降为 10s。
6. **WHEN** 解析成功完成，**THEN** 文件写入存储抽象层（开发本地 / 生产可切 S3），**AND** 元数据落 PostgreSQL `documents` 表，**AND** 投递 M2 任务（`M2 → POST /internal/extract`，携带 `documents.id` + `storage_key` + `mime_type`）。
7. **WHEN** 任意接口被调用，**THEN** 请求日志携带 `trace_id`（UUIDv4，贯穿 M1–M5 全链路），**AND** 响应头 `X-Trace-Id` 回显，**AND** 错误响应 `detail.trace_id` 与之一致。
8. **WHEN** 服务进程重启，**THEN** 启动阶段（`TaskManager.recover()`）扫描 PostgreSQL `documents` 表，将遗留的 `pending` / `processing` 任务**批量置为 `failed`**（**ADR-0001**），**AND** `error_code = TASK_INTERRUPTED`、`error_detail` 记录「进程重启导致任务中断」、`updated_at` 刷新，**AND** 每个被回收任务写一条 M5 审计（`action = task.recover.orphan`，含 `trace_id`），**AND** 状态**绝不允许**因进程重启而永久停留于 `pending` / `processing`。

> **关联 MVP 准入线**：C2（引用覆盖率 = 100% 在 M3 / M4 验证）；F3（直接 NO-GO 条件）。M1 本体指标 = P95 ≤ 500ms + 解析成功率 ≥ 0.95。

---

## 4. 数据模型概要

### 4.1 PostgreSQL 表 `documents`（新增）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `id` | UUID | 是 | 否 | PK | 主键，与 `task_id` 一致 |
| `filename_hash` | TEXT | 是 | **是** | idx | 原始文件名 SHA-256（日志禁输出原文） |
| `mime_type` | TEXT | 是 | 否 | - | 白名单内 MIME |
| `size_bytes` | BIGINT | 是 | 否 | - | 文件字节数 |
| `status` | TEXT | 是 | 否 | idx | `pending / processing / completed / failed` |
| `uploaded_by` | UUID | 是 | 否 | idx | 上传用户 id（M5 权限） |
| `org_id` | UUID | 是 | 否 | idx | 租户 ID（M5） |
| `storage_key` | TEXT | 否 | 否 | - | 抽象层存储键，`completed` 后填写 |
| `error_code` | TEXT | 否 | 否 | - | 失败时的错误码 |
| `error_detail` | TEXT | 否 | **是** | - | 失败明细，**日志禁输出** |
| `retry_count` | INT | 否 | 否 | - | 当前已重试次数 |
| `created_at` | TIMESTAMP | 是 | 否 | idx | 创建时间 |
| `updated_at` | TIMESTAMP | 是 | 否 | - | 最近状态变更时间 |
| `trace_id` | UUID | 是 | 否 | idx | 上传请求的 trace_id |

> **启动回收语义**（**ADR-0001**）：`status` 的**唯一真值源**是 PostgreSQL（**严禁**只存进程内存）。服务启动时 `TaskManager.recover()` 执行 `UPDATE documents SET status='failed', error_code='TASK_INTERRUPTED', ... WHERE status IN ('pending','processing')`，使进程重启不再产生"僵尸任务"（见 §3 验收 8）。

### 4.2 Neo4j 写入

**M1 不在 Neo4j 写入任何节点**，**仅在 PostgreSQL 落文档元数据**。Neo4j 节点写入是 M2 的职责。

### 4.3 存储抽象层

- **接口契约**：`Storage.put(key, stream) → str`、`Storage.get(key) → bytes`
- **`storage_key` 前缀规则**（**ADR-0003** 强制）：`storage_key = "{org_id}/{doc_id}/{filename_hash}"`；**MVP 单 Org 也必须按此格式写入**（避免 P2 迁移历史文件）；`Storage.get(key)` **必须校验 key 前缀与当前 `org_id` 一致**，防止越权读取他人文件
- **开发环境**：本地文件系统（`./storage/`）
- **生产环境**：S3 / OSS / MinIO（实现阶段切）
- **选型 TBD**（见 PRD §8 TBD-1）

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **无**（M1 是链路的起点）

### 5.2 下游被依赖

- **M2 实体关系抽取**：M1 完成后投递 `POST /internal/extract {doc_id, storage_key, mime_type, kg_version?}`，携带 `trace_id`
- **M5 权限与审计**：M1 上传 / 状态变更 / 失败事件均触发 M5 审计写入

### 5.3 与 M5 审计的耦合

- 每个 `document.upload` / `document.parse` / `document.fail` 事件产生一条 `audit_log`
- **不输出敏感字段**至日志：`filename` 上传名可能含敏感信息，**审计日志只记 `filename_hash` 与 `mime`，不记原文名**
- 每次上传调用 M5 权限校验（`actor_id` 是否属于 `org_id`、是否具备 `document.upload` 权限）

### 5.4 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/documents` | `multipart/form-data`，字段 `file` | 200 `{task_id, status: "pending"}`；413 / 415 错误响应 |
| `GET` | `/documents/{id}/status` | - | 200 `{task_id, status, progress?, error?}`；404 文档不存在 |

> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。

### 5.5 数据流图（片段）

```
用户上传 → MIME / 大小校验 → 写 documents(pending)
        → 投递异步任务（TaskManager.submit）→ documents.status=processing
        → tenacity 重试 ≤3 次 → documents.status=completed / failed
        → completed 投递 M2 → M2 创建 Neo4j 节点（kg_version）

服务启动 → TaskManager.recover() → 遗留 pending / processing 批量置 failed（TASK_INTERRUPTED）
```

> **关键结论**：**M1 只保证"上传成功 + 解析成功 + 状态可查"，**不保证**抽取 / 图谱 / 问答的结果质量。**这是 M1 的边界，也是 M2–M4 存在的理由。**