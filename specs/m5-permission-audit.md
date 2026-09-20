# M5 · 权限隔离与审计留痕 — MVP 规格说明书

> **文档编号**：spec-m5
> **版本**：v1.0
> **状态**：MVP 规格（v1.0.0 已交付，实现态见 backend/CODEBUDDY.md §4）
> **上游依据**：`docs/02-product-outline.md` §3.2 M5
> **关联 Prompts**：**无**（M5 不消费 Prompt）
> **关联研究结论**：`01-research.md` §3.1.2 能力 6；GAP-T6；假设 A12（私域硬需求）
> **关联大纲**：`02-product-outline.md` §3.2 M5 + §6 准入线
> **关联 ADR**：[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**5 个功能点**，严格沿用 outline §3.2）

1. **角色 / 文档 / 场景三粒度权限**（RBAC + ABAC 最小组合）
2. **操作审计 + `trace_id` 全链路 JSON 日志**（loguru）
3. **敏感字段过滤**（日志禁输出合同金额 / 发票号 / 税号 / 法人姓名 / 银行账号 / 身份证 / 电话）
4. **私域部署开关**（禁云外发请求；LLM 调用允许"私域模型 / 私有化部署 / Mock"）
5. **限流与误用告警**（slowapi，遵循 `CODEBUDDY.md` 安全底线）

### 1.2 Out of Scope（明确不做）

- **复杂 ABAC 策略引擎**（OPA / Casbin 集成）（**MVP 仅最小组合**，复杂策略属 P2）
- **SSO / SAML / OIDC 集成**（**MVP 仅本地账号**，企业 SSO 属 P2）
- **多租户多 Org 拆分**（**MVP 单 Org**，多 Org 属 P2 扩展 E6）
- **数据加密静态 / 传输加密细节**（**MVP 依赖基础设施层**，应用层不重复实现）
- **审计日志的归档与冷存储**（**MVP 仅在线可查**，归档属 P2）

---

## 2. 核心用户故事

- 作为**合规 / 审计主管**，我希望每个用户的每个操作都有**唯一 `trace_id` 留痕**，以便我能在合规审查时串联完整操作链。
- 作为**CISO / 安全负责人**，我希望日志中**不出现**合同金额、发票号、税号、法人姓名等敏感字段，以便系统满足合规审计要求而**不引入新的泄露面**。
- 作为**系统管理员**，我希望所有 API 接口按 IP / 用户**限流**，触发限流时同步留痕告警，以便我能发现异常使用模式。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。

1. **WHEN** 用户发起任意 API 调用，**THEN** 系统校验"用户是否拥有该文档 / 场景的访问权限"，**AND** 无权限时返回 HTTP 403 + 错误码 `FORBIDDEN` + 响应体 `{code, message, detail, trace_id}`，**AND** 同步写 `audit_log`（`action=permission.denied`）。
2. **WHEN** 任一 API 调用成功 / 失败，**THEN** 系统写一条 `audit_log`，**AND** 字段含 `{ts, action, actor_id, actor_ip, doc_id?, resource, status, trace_id, detail?}`，**AND** loguru 输出 JSON 格式。
3. **WHEN** 任意字段命中敏感字段表（合同金额 / 发票号 / 税号 / 法人姓名 / 银行账号 / 身份证 / 电话 / 上传文件名），**THEN** 系统在写入日志前**自动脱敏**（详见 §4.5），**AND** 严禁原文落库，**AND** 落库前由单元测试断言"无敏感字段原文"。
4. **WHEN** 系统检测到外部网络出向调用（云端 LLM / 第三方 API）且 `private_deploy.enabled=true`，**THEN** 阻断请求并返回 HTTP 503 + 错误码 `PRIVATE_DEPLOY_BLOCKED`，**AND** 触发 M5 审计 `private_deploy.violation` 事件。
5. **WHEN** 用户在 1 分钟内调用某接口超过 N 次（默认 `N=60`，可配置），**THEN** slowapi 触发限流并返回 HTTP 429 + 错误码 `RATE_LIMITED`，**AND** 同步写 `audit_log`（`action=rate_limit.triggered`），**AND** 累计触发次数超阈值的 IP 写入 `alert` 表（P2）。
6. **WHEN** 任意审计日志写入，**THEN** 必须含 `trace_id` 字段（UUIDv4），**AND** `trace_id` 在全链路（M1 → M2 → M3 / M4 → M5）中保持一致，**AND** 响应头 `X-Trace-Id` 回显。
7. **WHEN** 管理员查询审计日志（`GET /audit`），**THEN** 仅返回当前用户有权限查看的记录（按 `actor / org` 隔离），**AND** 任意敏感字段值已脱敏，**AND** 默认按 `ts DESC` 分页（页大小 50，可配置）。
8. **WHEN** 任一查询在 `org_id = A` 的请求上下文中访问属于 `org_id = B` 的记录（**ADR-0003**），**THEN** PostgreSQL **RLS** 策略拦截，**AND** 列表查询返回**空集**、按 id 直取返回 **HTTP 403**，**AND** **不得**返回任何跨 org 数据，**AND** 集成测试**必须**包含「跨 org 越权」用例以断言 RLS **已真实生效**（三前提：`FORCE ROW LEVEL SECURITY` + 非 owner 受限 DB 角色 + `SET LOCAL app.current_org`），**AND** 禁止将策略写成 `USING (true)`。

> **关联 MVP 准入线**：A12（私域硬需求）+ `02-product-outline.md` §6 准入线（无独立数值指标，作为基础设施贯穿）。

---

## 4. 数据模型概要

### 4.1 PostgreSQL 表 `users`（新增）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `id` | UUID | 是 | 否 | PK | - |
| `username` | TEXT | 是 | 否 | unique | 登录名 |
| `password_hash` | TEXT | 是 | **是** | - | bcrypt / argon2 哈希 |
| `org_id` | UUID | 是 | 否 | idx | 所属租户（MVP 单 org 预留） |
| `status` | TEXT | 是 | 否 | - | `active / disabled` |
| `created_at` | TIMESTAMP | 是 | 否 | - | - |
| `updated_at` | TIMESTAMP | 是 | 否 | - | - |

### 4.2 PostgreSQL 表 `roles`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | UUID | 是 | PK |
| `name` | TEXT | 是 | `admin / auditor / analyst / viewer` |
| `description` | TEXT | 否 | - |

> **RLS 豁免声明**（**ADR-0003**）：`roles` 为**全局字典表**（无租户维度），**显式豁免** RLS。**豁免必须在代码评审中被显式确认**，避免其成为隐蔽的越权入口；`roles` 仅允许存放系统预置角色，**禁止**写入任何租户业务数据。

### 4.3 PostgreSQL 表 `user_roles`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `org_id` | UUID | 是 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `user_id` | UUID | 是 | - |
| `role_id` | UUID | 是 | - |
| `doc_scope` | JSONB | 否 | 文档级粒度（如 `{"doc_ids": [...], "tags": [...]}`） |
| `scene_scope` | JSONB | 否 | 场景级粒度（如 `["affiliation", "qa"]`） |
| `granted_by` | UUID | 是 | 授权人 |
| `granted_at` | TIMESTAMP | 是 | - |

### 4.4 PostgreSQL 表 `audit_log`（新增）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `id` | BIGSERIAL | 是 | 否 | PK | - |
| `org_id` | UUID | 是 | 否 | idx | 租户 ID（**ADR-0003**，RLS 隔离键，审计查询按 org 隔离，见 §3 验收 7） |
| `ts` | TIMESTAMP | 是 | 否 | idx | 时间戳 |
| `action` | TEXT | 是 | 否 | idx | 操作类型（如 `document.upload / qa.refused / permission.denied`） |
| `actor_id` | UUID | 否 | 否 | idx | 操作用户（系统事件为 NULL） |
| `actor_ip` | TEXT | 否 | 否 | - | 客户端 IP |
| `doc_id` | UUID | 否 | 否 | idx | 关联文档 |
| `resource` | TEXT | 是 | 否 | - | 资源标识（如 `document:uuid / qa:uuid`） |
| `status` | TEXT | 是 | 否 | idx | `success / failure` |
| `trace_id` | UUID | 是 | 否 | idx | 全链路 trace_id |
| `detail` | JSONB | 否 | **是** | - | 明细（**敏感字段已脱敏**） |

### 4.5 敏感字段脱敏规则（应用层）

| 字段类别 | 脱敏策略 | 示例 |
|---|---|---|
| 合同金额 | 完整数字 → 掩码 | `1,234,567.89` → `***,***.00` |
| 发票号 | 保留前缀 4 位 + 掩码 | `INV202403150001` → `INV2****0001` |
| 税号 | SHA-256 + salt 哈希 | 原文 → 64 字符 hex |
| 法人姓名 | SHA-256 + salt 哈希 | 原文 → 64 字符 hex |
| 银行账号 | 仅保留后 4 位 | `6228 **** **** 1234` |
| 身份证 | SHA-256 + salt 哈希 | 原文 → 64 字符 hex |
| 电话 | 仅保留后 4 位 | `138****1234` |
| 文件名 | SHA-256 哈希（与 `documents.filename_hash` 复用） | 原文 → 64 字符 hex |

> **关键约束**：**敏感字段原文不得落库**。**落库前由单元测试断言"无敏感字段原文"**（实现阶段在 M5 的 CI 中加入）。

### 4.6 配置项 `private_deploy`（env）

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `PRIVATE_DEPLOY_ENABLED` | BOOL | `false`（开发） / `true`（生产） | 私域部署开关 |
| `ALLOWED_EGRESS_HOSTS` | LIST | `[]` | 出向白名单（开发环境允许 LLM API） |

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **无**（M5 是横向能力，**被** M1–M4 调用）

### 5.2 下游被依赖

- **M1 上传**：上传 / 状态变更 / 失败事件均写入 M5
- **M2 抽取**：抽取 / 消解 / 写入事件均写入 M5
- **M3 问答**：每次问答 / 拒答事件均写入 M5
- **M4 关联交易**：疑点产生 / 状态变更事件均写入 M5

### 5.3 跨模块耦合（**M5 提供三个统一基础设施**）

- **统一 `trace_id` 注入中间件**（FastAPI dependency）：所有请求进入时生成 / 透传 `trace_id`，响应头 `X-Trace-Id` 回显
- **统一权限校验装饰器**（`@require_permission(scope)`）：所有受保护接口在路由层声明权限范围
- **统一敏感字段脱敏工具函数**（`mask(field, category)`）：所有写日志前必须经过脱敏
- **统一 `org_id` 注入中间件**（**ADR-0003**）：`org_id` **仅**从认证态（`POST /auth/login` 签发的 token）解析，**严禁**从请求 body / query 读取；在**事务开启后、业务查询前**执行 `SET LOCAL app.current_org = :org_id`（**必须 `SET LOCAL`**，避免连接池串租户），与 PostgreSQL **RLS** 配合形成双层隔离；业务层**禁止裸写 SQL**（须经 ORM / 统一过滤注入）

### 5.4 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/auth/login` | `{username, password}` | 200 `{token, trace_id}`；401 |
| `GET` | `/audit` | query: `action?, actor_id?, ts_from?, ts_to?, trace_id?, page?, page_size?` | 200 审计列表（分页） |
| `GET` | `/audit/{id}` | - | 200 单条详情；403 / 404 |
| `GET` | `/users/me` | - | 200 `{id, username, roles, trace_id}` |

> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。

> **关键结论**：**M5 是 MVP 的"基础设施层"**，**不是独立功能**。**它提供的三个统一组件**（trace_id 中间件 / 权限装饰器 / 脱敏工具）**被 M1–M4 共同消费**。任何模块若绕过这三个组件直接写日志 / 校验权限 / 处理敏感字段，**都应被代码评审驳回**——这是私域部署与合规审计的门票。