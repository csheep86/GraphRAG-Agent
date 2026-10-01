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
| **4** | **查询强制经 ORM / 中间件注入 `org_id` 过滤，严禁裸写 SQL**；**该应用层过滤为常设防线，不因 RLS 生效而移除**（理由见 §3.7 裁决一） |

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

#### 3.1.1 落地记述（Sprint 8.1 批次 A，2026-09-24）

`audit_log` / `qa_logs` 两张表**已按本节就位**（`backend/app/db/models.py`）：

| 差异项 | 本 ADR / spec 原文 | 落地实现 | 登记理由 |
|---|---|---|---|
| `audit_log` 主键 | `specs/m5-permission-audit.md` §4.4 写 **`BIGSERIAL`** | **`Uuid` 主键**（`default=uuid.uuid4`） | 全仓既有无 `BIGSERIAL` 表，且 `BIGSERIAL` 需 DB 序列才能生成 id，与「SQLite 开发态替身」（§3.6）和将来的 IdM 对齐都不兼容；牺牲「紧凑整型」换 schema 一致性，已按「差异必登记」写在这里（批次决策 **A9**） |
| `qa_logs` 主键 | `specs/m3-graphqa-citation.md` §4.3 同上 | **`Uuid` 主键** | 同上 |
| 索引 | §3.1「复合索引 `org_id` 打头」 | `ix_audit_log_org_id_{ts,action,status,trace_id}`、`ix_qa_logs_org_id_{created_at,trace_id}` | 守本节第 1 条 |
| `trace_id` 列类型 | spec 未明写 | **`Uuid`** | `trace_id` 由请求中间件生成 UUIDv4（M1 验收 7），存 UUID 而非字符串：索引更窄，也避免将来出现「装得进字符串的非法值」 |

- `audit_log.status` 增加 `CheckConstraint('success','failure')`（取值即 M5 §4.4 的两档，无第三态）；
- 写入点**唯一** = 审计中间件（Sprint 8.1 决策 **A1**：全量写 + allowlist 排除 `health`），非各服务显式埋点；
- `user_roles` / `roles` / `users` / `entity_merge_candidates` **本批次未建**（`roles` 系 S11，`users` / `user_roles` 同）——本表第 8 / 9 / 10 行的动作仍挂着。

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

### 3.6 SQLite 兜底与切换 PostgreSQL 的裁决

#### 3.6.1 Sprint 1 临时兜底（**历史记述；已裁决终止**）

> **SQLite 仅作为 Sprint 1 契约验证阶段的临时兜底，不支持 RLS。** 本节约定的偿还动作**截至 Sprint 10.5 仍未完成**，属**逾期的已知债**——不得因为「一直这么跑着」而被视为可继续。

| 项 | 约定 |
|---|---|
| 适用范围 | `APP_ENV ∈ {development, test}`，`DATABASE_URL` 默认 `sqlite:///./dev.db` |
| 生产禁止 | `APP_ENV=production` 且驱动为 sqlite 时**应用启动直接失败**（`backend/app/core/config.py::_guard_production_sqlite`），禁止静默降级 |
| 隔离兜底 | RLS 缺位期间，`org_id` 过滤**只由应用层保证**（查询强制带 `org_id`，跨租户返回 `403 FORBIDDEN`） |
| 索引 | 仍按 §3.1 **`org_id` 打头**建复合索引（如 `ix_documents_org_id_status`），避免切库时返工 |
| 其它兜底 | `X-Org-Id` / `X-Actor-Id` 开发态请求头（`ALLOW_DEV_ORG_HEADER=true` 且非生产才生效）**同样限期移除**，见 `backend/CODEBUDDY.md` §2 |
| 偿还动作 | 切 PostgreSQL → §3.1 补全各表 `org_id` → §3.2 建 `ENABLE`/`FORCE` 策略 → §3.3 事务内 `SET LOCAL app.current_org` → 删除本节全部兜底分支 |
| 风险声明 | 本节生效期间，§3.2「DB 层兜底」**实际未生效**，越权防御强度**低于本 ADR 的目标状态**；**不得据此认为隔离已完成** |

#### 3.6.2 裁决（2026-10-01）：直接切换 PostgreSQL，**不再以 SQLite 作为开发态替身**

| 项 | 裁决 |
|---|---|
| **决策** | **开发 / 测试 / 生产一律使用 PostgreSQL**；不再把 SQLite 当「PG 的开发态替身」——`backend/CODEBUDDY.md` §1 中「PostgreSQL 的本地等价替身」这一**定位就此废止** |
| **版本** | **PostgreSQL 16.x**（`docs/deployment-spec.md` §2 组件清单）；**固定小版本 tag**，遵守 D-N：`:latest` 是不可复现的同义词 |
| **理由** | SQLite 与 PG 在**并发模型（单写锁 vs MVCC）、UUID 存储格式、事务隔离级别、RLS** 上均不同 ⇒ **SQLite 上跑绿的测试不能证明 PG 上正确**。考勤 / 薪酬数据下，这类差异会在**客户现场才暴露**——那是本 ADR 最贵的暴露时机（例：`backend/app/scripts/probe_temporal_state.py` 已踩过「`Uuid` 列在 SQLite 里存无连字符格式」的方言坑） |
| **附加偿还** | 清理 SQLite 兜底分支：`app/db/session.py` 的 `check_same_thread` 特判、`.env.example` 的「开发态替身」说明、`backend/CODEBUDDY.md` §1 / §2 的限期声明 |
| **风险声明** | 切换后**必然暴露一批 SQLite 下测不出的缺陷**（尤其并发）。这是**预期代价**，不得以「以前都好好的」为由回退 |

### 3.7 应用层过滤为常设防线 + 信创降级退路（2026-10-01 补）

**裁决一：应用层 `org_id` 过滤不得因 RLS 存在而移除。**

1. **DB 层 RLS 可能被降级或不可用**——客户若有国产化（信创）要求而选用**非 PG 兼容内核**的数据库（如达梦，Oracle 兼容为主），RLS 无法平移；此时若应用层过滤已被当作「兜底」拆除，隔离**直接击穿**。
2. 双层防御的价值恰在于**两层各自独立成立**；任一层被当成「另一层的备份」而弱化，即退化为单层。

⇒ 应用层过滤由「RLS 缺位期间的兜底」**升格为常设防线**，与 RLS 并列，**不设移除条件**。

**裁决二：部署单元 = 一个租户。**

默认隔离为**方案 A（一套部署 + `org_id` + RLS）**；但**部署单元按「一套 compose = 一个租户」设计**，使方案 B（每子公司独立部署）退化为「多起几套」，**不需要改代码**（部署侧同步见 `docs/deployment-spec.md` §1.1）。

**信创兼容分级**（选型参考，不构成承诺）：

| 国产库 | 内核来源 | RLS 可平移性 |
|---|---|---|
| 人大金仓 KingbaseES | PG 内核 | 好 |
| GaussDB / openGauss | PG 内核 | 好 |
| 达梦 DM | Oracle 兼容为主 | **差——需重做** |

⇒ 遇非 PG 兼容内核时：**牺牲 DB 层 RLS，保留应用层过滤**。隔离强度降级但**不击穿**；该降级必须**显式登记并告知客户**，不得静默。

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

### 4.1 必须补的两类测试（**2026-10-01 登记 · 待纳入开发需求与 CI 围栏**）

> 登记目的：后续梳理开发需求与围栏时**不得遗漏**。截至登记日，两类用例**均为缺口**。

| # | 用例 | 断言 | 缺口后果 |
|---|---|---|---|
| **T1** | **跨 org 越权**：以 A org 身份查询 / 读取 B org 的资源（`documents`、`audit_log`、`qa_logs`、存储 `storage_key`） | 返回**空**或 `403`；**不得**返回 B 的数据 | 隔离只是纸面 |
| **T2** | **并发串租户**：多线程 / 多协程**同时**以不同 `org_id` 发起请求，**必须覆盖连接池复用路径** | 每个请求**只**看到自己 org 的数据；**不得**串号 | `SET LOCAL` 误写成 `SET`、或连接泄漏 ⇒ **A 公司看到 B 公司的考勤 / 薪酬** |

**T2 为何单独列出**：RLS + 连接池是本 ADR **唯一可能产出「静默跨租户泄露」**的组合——它在**单 org、串行**测试里永远测不出来，只在真实并发下暴露。T2 不落地，**§3.2 的三前提不可宣称已守**。

**围栏要求**：两类用例**均须在 PostgreSQL 上执行**（SQLite 无 RLS，在其上跑无意义），纳入 CI 必过项；**禁止**标 `local_only` 绕过（否则「看着绿、其实没跑」）。

---

## 5. 备选方案与取舍

| 方案 | 拒绝理由 |
|---|---|
| **仅 API 层过滤** | 一次漏写即越权泄露；无兜底，风险不可接受。 |
| **仅 DB 层（无请求级注入）** | 缺少可信的 `org_id` 上下文来源；且 M5 仍需在路由层做 RBAC 权限校验。 |
| **每 Org 独立 schema / 独立数据库** | MVP 单 Org 下运维过重。**2026-10-01 更新**：仍**不作为默认**（默认方案 A），但**部署单元按「一套 compose = 一个租户」设计**（§3.7 裁决二）⇒ 客户要求子公司**物理隔离**时只需多起几套，**不改代码**。 |
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
| 7 | `contracts/openapi.yaml`（实现阶段） | 所有列表 / 详情端点的租户隔离与 403 语义（Sprint 1 已定稿 5 个核心接口） |
| 8 | `backend/CODEBUDDY.md` §1 / §2 | **§1 的「SQLite = PostgreSQL 本地等价替身」定位已废止**（§3.6.2 裁决），改为一律 PG；§2 开发态请求头的限期声明仍待偿还 |
| 9 | `docs/deployment-spec.md` §1.1 / §2 | §1.1 补「**一套 compose = 一个租户**」的部署单元定义（§3.7 裁决二）；§2 的 PG 位由「留空待 S11」改为**就位**（PG 16.x 固定小版本 tag） |
| 10 | `backend/app/db/session.py`、`backend/.env.example` | 清理 SQLite 兜底分支（`check_same_thread` 特判、「开发态替身」说明），见 §3.6.2「附加偿还」 |
| 11 | `specs/m5-permission-audit.md` §3 | 补 **T2 并发串租户**验收（§4.1）：多 org 并发请求不得串号；T1 / T2 **均须在 PG 上跑** |

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
