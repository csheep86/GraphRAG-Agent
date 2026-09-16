# ADR-0003 · 跨租户资源隔离粒度：API 层注入 `org_id` + DB 层 RLS

| 项 | 内容 |
|---|---|
| **ADR 编号** | ADR-0003 |
| **对应 TBD** | **TBD-5**（跨租户资源隔离粒度） |
| **状态** | **Accepted（已接受）** |
| **决策日期** | 2026-09-16 |
| **决策者** | 架构师 |
| **关联模块** | M5（主）、M1–M4（全量消费） |
| **关联规格** | [`specs/m5-permission-audit.md`](../../specs/m5-permission-audit.md) §4.1–§4.4 / §5.3、[`specs/m1-async-ingest.md`](../../specs/m1-async-ingest.md) §4.1 / §4.3 |
| **关联硬约束** | **H6**（私域部署禁云外发）、假设 **A12**（私域硬需求）、M5 §1.2（「MVP 单 Org，多 Org 属 P2」） |

---

## 1. 背景（Context）

M5 要求「角色 / 文档 / 场景三粒度权限」与「操作审计」，并明确 **MVP 为单 Org、多 Org 属 P2**（M5 §1.2）。但**单租户 ≠ 不需要租户维度**：

- 隔离粒度决定 **schema 索引设计、全部查询写法、`storage_key` 组织方式**——这些是**根属性**；
- 一旦按「无 `org_id`」实现，P2 开启多 Org 时需 **给每张表加列 + 审计每条查询**，任何遗漏都是**跨租户越权**；
- 私域部署下，**数据不出内网 + 不串租户**是不可妥协的底线（H6 / A12）。

**失败代价不对称**：漏写一次 `WHERE org_id` 即数据泄露；而**预留字段的成本近乎为零**。

---

## 2. 决策（Decision）

**API 层强制注入 `org_id` + DB 层启用 PostgreSQL RLS（行级安全），双层防御；存储层 `storage_key` 以 `org_id` 为前缀。**

四条强制要求：

| # | 要求 |
|---|---|
| **1** | **所有核心表（PostgreSQL）必须含 `org_id` 字段**（`UUID NOT NULL` + 索引） |
| **2** | **启用 PostgreSQL RLS**（`ENABLE` + `FORCE ROW LEVEL SECURITY`） |
| **3** | **`storage_key` 必须以 `org_id` 为前缀** |
| **4** | **查询强制经 ORM / 中间件注入 `org_id` 过滤，严禁裸写 SQL** |

---

## 3. 实现要求（Mandatory）

### 3.1 schema：核心表补 `org_id`

| 表 | 现状 | 动作 |
|---|---|---|
| `documents`（M1 §4.1） | ✅ 已有 `org_id` | 保持 |
| `users`（M5 §4.1） | ✅ 已有 `org_id` | 保持 |
| `kg_versions`（M2 §4.4） | ❌ 缺失 | **补 `org_id`** |
| `entity_merge_candidates`（M2 §4.5） | ❌ 缺失 | **补 `org_id`** |
| `qa_logs`（M3 §4.3） | ❌ 缺失 | **补 `org_id`** |
| `affiliation_suspicions`（M4 §4.3） | ❌ 缺失 | **补 `org_id`** |
| `affiliation_tasks`（M4 §4.4） | ❌ 缺失 | **补 `org_id`** |
| `unaligned_subjects`（M4 §4.5） | ❌ 缺失 | **补 `org_id`** |
| `audit_log`（M5 §4.4） | ❌ 缺失 | **补 `org_id`**（审计查询也要按 org 隔离，M5 §3 验收 7） |
| `user_roles`（M5 §4.3） | ❌ 缺失 | **补 `org_id`** |
| `roles`（M5 §4.2） | ❌ 缺失 | **全局字典表，RLS 豁免**（需在规格中显式声明豁免，避免成为隐蔽越权口） |

- 所有 `org_id` 必须建索引，且**复合索引以 `org_id` 打头**（RLS 策略的性能前提）。
- **禁止 `org_id IS NULL` 的兜底语义**（会把「未设上下文」变成「全租户可见」）。

### 3.2 RLS 策略

```sql
-- 以 documents 为例，其它表同构
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;   -- 关键：表 owner 默认绕过 RLS

CREATE POLICY tenant_isolation ON documents
  USING      (org_id = current_setting('app.current_org')::uuid)
  WITH CHECK (org_id = current_setting('app.current_org')::uuid);
```

**必须同时满足的三个前提，缺一不可**：

1. **`FORCE ROW LEVEL SECURITY`**：否则**表 owner 绕过策略**，RLS 形同虚设；
2. **应用使用「非 owner、非 superuser」的受限数据库角色**连接（`BYPASSRLS` 必须为 `false`）；
3. **每个请求 / 事务内 `SET LOCAL app.current_org = :org_id`**（必须用 `SET LOCAL` 而非 `SET`，否则连接池复用时会串租户）。

### 3.3 请求级注入（API 层）

- `org_id` 从**认证态**（M5 `POST /auth/login` 签发的 token）解析，**严禁**从请求 body / query 直接读取（否则可被篡改）。
- 由 M5 统一中间件在**事务开启后、业务查询前**执行 `SET LOCAL`。
- **MVP 单 Org 场景**：`org_id` 取默认 Org 常量，但**字段、策略、`SET LOCAL` 必须真实生效**——**禁止把策略写成 `USING (true)`**（那是「假装有隔离」，比没有更危险）。

### 3.4 ORM 与「严禁裸 SQL」

- 统一使用 **SQLAlchemy ORM**；通过 `with_loader_criteria` 或全局事件钩子**自动附加 `org_id` 过滤**。
- **禁止** `text()` 拼接 / 手工字符串 SQL 等旁路写法。
- 以 **lint 规则 / CI 检查**拦截业务层裸 SQL（与 M2 §5.5「绕过 M2 直写 Neo4j 应被 lint 拦截」同构）。

### 3.5 存储层

- 规则：`storage_key = "{org_id}/{doc_id}/{filename_hash}"`。
- `Storage.get(key)` **必须校验 key 前缀与当前 `org_id` 一致**，防止越权读取他人文件。
- MVP 单 Org 也必须按此格式写入，**避免 P2 迁移历史文件**。

---

## 4. 后果（Consequences）

### 正面
- ✅ **越权防御下沉到 DB**：单点漏写过滤不再直接导致泄露（DB 兜底）。
- ✅ **P2 多 Org 平滑开启**：字段 / 策略 / 存储前缀已就位，**无需 schema 迁移**。
- ✅ **审计可隔离**：`audit_log` 按 org 隔离（对齐 M5 §3 验收 7）。

### 负面（已知并接受）
- ⚠️ **引入 RLS 运维复杂度**：需专用 DB 角色、连接池必须正确 `SET LOCAL`、调试时「查不到数据」的排查成本上升。
- ⚠️ **测试必须覆盖多 Org**：单 Org 测试无法证明 RLS 生效，**必须新增跨 org 越权用例**（否则隔离只是「纸面」的）。
- ⚠️ **轻微性能开销**：策略表达式求值 + 索引需以 `org_id` 打头。

---

## 5. 备选方案与取舍

| 方案 | 拒绝理由 |
|---|---|
| **仅 API 层过滤** | 一次漏写即越权泄露；无兜底，风险不可接受。 |
| **仅 DB 层（无请求级注入）** | 缺少可信的 `org_id` 上下文来源；且 M5 仍需在路由层做 RBAC 权限校验。 |
| **每 Org 独立 schema / 独立数据库** | MVP 单 Org 下运维过重；作为 P2 大规模租户的可选演进方向。 |
| **存储层不隔离** | P2 需**迁移全部历史文件**，成本与风险极高。 |
| **不做预留，等 P2 再加** | 需给每张表加列 + 逐条审计查询，**任何遗漏都是安全洞**。 |

---

## 6. 对既有规格 / 契约的影响（**需同步，勿自动补全**）

| # | 文件 | 需变更点 |
|---|---|---|
| 1 | `specs/m5-permission-audit.md` | §4.2 `roles` 需显式声明「全局字典表，RLS 豁免」；§4.3 `user_roles` 补 `org_id`；§4.4 `audit_log` 补 `org_id` |
| 2 | `specs/m5-permission-audit.md` | §3 新增验收：**跨 org 查询返回空 / 403**，并断言 RLS 已生效 |
| 3 | `specs/m2-extract-kg.md` | §4.4 / §4.5 补 `org_id` |
| 4 | `specs/m3-graphqa-citation.md` | §4.3 `qa_logs` 补 `org_id` |
| 5 | `specs/m4-affiliation-detection.md` | §4.3 / §4.4 / §4.5 补 `org_id` |
| 6 | `specs/m1-async-ingest.md` | §4.3 存储抽象层补 `storage_key` 前缀规则（`{org_id}/{doc_id}/{filename_hash}`） |
| 7 | `contracts/openapi.yaml`（实现阶段） | 所有列表 / 详情端点的租户隔离与 403 语义 |

> **注意**：本 ADR 一旦落地，**M1–M4 的全部规格表都需补 `org_id`**——这是横向基础设施的固有代价，**必须在实现前一次性对齐**。

---

## 7. 参考
- `specs/m5-permission-audit.md` §1.2 / §3 验收 1 / §3 验收 7 / §4.1–§4.4 / §5.3
- `specs/m1-async-ingest.md` §4.1 / §4.3
- `docs/03-prd.md` §4（H6）、§6.2、§8（TBD-5）
- `CODEBUDDY.md`「安全底线」「存储规范」
- 假设 A12（`docs/01-research.md`）

---

> **ADR-0003 结束。** 状态 **Accepted**，落地前须完成 §6 的规格 / 契约同步。
