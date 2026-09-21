# M6 · 本体管理与增量更新 — MVP 规格说明书

> **文档编号**：spec-m6
> **版本**：v0.1（草案，待 Sprint 12 启动前升 v1.0）
> **状态**：MVP 规格草案（**v3.0 计划纳入 Sprint 12**，承接 `docs/v1.1.0-demo-mvp-plan.md` §19.1 A/B/C/D 四批次与 §15.1 第 5 行；**本草案定稿时点 = Sprint 11 收尾前**）
> **上游依据**：`docs/02-product-outline.md` §3.2 M6 + `docs/03-prd.md` §2（P1 模块）+ `docs/v1.1.0-demo-mvp-plan.md` §19
> **关联 Prompts**：`prompts/entity_relation_extract_v1.md`（**仅参数化复用，不修改**）；与 `prompts/kg_qa_v1.md`（冷启动建议 LLM 调用载体）
> **关联研究结论**：`docs/v1.1.0-demo-mvp-plan.md` §12 R12（前端 GUI 工时风险）
> **关联大纲**：`docs/02-product-outline.md` §3.2 M6 + §6 准入线（C3 单位成本）
> **关联 ADR**：[ADR-0002 Neo4j ↔ PostgreSQL 一致性边界](../docs/adr/ADR-0002-neo4j-postgres-consistency.md)、[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**4 个功能点**，严格沿用 plan §19.1 A/B/C/D 四批次）

1. **本体冷启动**（Cold Start，批次 A）：从首批 50 份样本**自动建议**实体 / 关系类型（复用 `entity_relation_extract_v1.md` 的 schema-suggestion 模式，**不新增 Prompt 版本**）；**人工确认后才生效**（未确认不写入图谱，对应 GAP-F2）
2. **本体校正 GUI**（批次 B）：实体合并 / 拆分 / 重命名三个动作（**只做三件**，plan §12 R12）；与 Sprint 9 落地的 `entity_merge_candidates` 表绑定
3. **增量重算**（批次 C）：新增 / 修改文档**只重算受影响子图**，不触发全量重建；依赖 `content_hash` / `source_version` 标识变化范围
4. **成本仪表盘**（批次 D）：每千页处理时长 / token 用量 / 人工校正工时；**增量 vs 全量成本比**（**C3 准入线的度量载体**）

### 1.2 Out of Scope（明确不做）

- **自动本体 schema 生成**：**仅"建议"不"自动生效"**（M6 的价值前提，对应 GAP-F2）——任意 LLM 建议的 schema 必须经 GUI 用户确认
- **本体版本对比 GUI**（plan §12 R12 收口）
- **撤销栈**（同上）
- **批量校正**（一次提交合并 N 个；R12 收口）
- **多模态本体**（图片 / 视频，**MVP 不含**）
- **跨租户本体共享**（每 org 独立 schema，ADR-0003）
- **本体导入 / 导出**（与第三方本体对齐属 P2，与 M2 §1.2 一致）
- **Schema 自动选择算法**（**仍是建议**，由人在 GUI 中确认）

---

## 2. 核心用户故事

- 作为**业务治理人员**，我希望从空文档集开始就能"建议一组"合理的本体（实体类型 + 关系类型），以便我能快速开始抽取工作，**而不是先要请架构师配 schema**。
- 作为**审计 / 业务用户**，我希望能把"我识别错误"的两实体合并、把一实体拆成两个、或给实体改名，以便抽取错误被快速修复，**且增量重算不引发全量重建**（避免成本爆炸）。
- 作为**运维 / 数据治理人员**，我希望校正动作触发**增量重算**，**不要全量重建**，以便我能在合理成本内完成修复。
- 作为**架构师 / 成本治理人员**，我希望看到 token 用量、单文档处理成本与增量/全量成本比，**以便判断 C3 准入线是否可达**（TBD-7 数值阈值在 Sprint 13 收敛）。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。

### 3.1 冷启动（对应批次 A）

1. **WHEN** 用户调用冷启动接口（`POST /api/v1/ontology/cold-start`，入参 `{domain_description}`），**THEN** 系统调用 `kg_qa_v1.md`（轻量 LLM 调用，**不修改 prompt**）建议一组 `entity_types` / `relation_types`，**AND** 仅"建议"不"自动生效"（用户必须确认），**AND** 响应体 `{suggested_entity_types, suggested_relation_types, trace_id}`，**AND** 未确认的 schema **不写入** `ontology_schemas` 表。
2. **WHEN** 用户在 M6 校正 GUI 确认 schema（`POST /api/v1/ontology/confirm`，入参 `{version, entity_types, relation_types}`），**THEN** 系统写入 `ontology_schemas` 表（`status = active`，`version = 1` 或下一序号），**AND** 后续 M2 抽取调用 `entity_relation_extract_v1.md` 时将 `entity_types` / `relation_types` 参数**从该表读取**（v1 已支持模板参数化，第 16~18 行实测），**AND** 重复确认返回 HTTP 409 `SCHEMA_VERSION_NOT_ACTIVE`。

### 3.2 校正 GUI（对应批次 B）

3. **WHEN** 用户提交"合并"动作（`POST /api/v1/ontology/merge`，入参 `{left_entity_id, right_entity_id}`），**THEN** 系统更新 Neo4j `:Entity` 节点（**`MERGE` 幂等键 = `(id, kg_version)`**，沿用 ADR-0002 §3.1），**AND** 更新 `entity_merge_candidates` 表对应行 `status = applied`（**字段对齐 M2 §4.5**——**M2 当前枚举为 `pending / auto_merged / human_review / rejected`，无 `applied`**；**M6 落地时必须先升版 M2 spec §4.5 加 `applied` 枚举值**，**且**同步在 `backend/app/schemas/` 加 Pydantic 枚举、`uv run python scripts/export_openapi.py` 重导契约、`npm run gen:api` 重生前端类型——**严格按后端 CODEBUDDY §3 契约同步铁律 5 步走**），**AND** 触发增量重算事件（详见 §3.3 验收 6），**AND** M5 写 `audit_log`（`action = ontology.merge`）。
4. **WHEN** 用户提交"拆分"动作（`POST /api/v1/ontology/split`，入参 `{entity_id, new_entities: [{canonical_name, ...}]}`），**THEN** 系统创建 N 个新 `:Entity` 节点并把原 `:Entity` 的关系迁移到对应新节点（按规则匹配：曾用名 / 同名 / 其他，**默认同名**），**AND** 原节点置 `status = split`，**AND** 触发增量重算。
5. **WHEN** 用户提交"重命名"动作（`POST /api/v1/ontology/rename`，入参 `{entity_id, new_canonical_name}`），**THEN** 系统更新 `:Entity.canonical_name`，**AND** 把旧名写入 `:Entity.aliases`（沿用 M2 §4.1），**AND** 触发增量重算。

### 3.3 增量重算（对应批次 C）

6. **WHEN** 任一校正动作（验收 3/4/5）执行，**THEN** 增量重算**不重建全图**，仅重写受影响子图（节点数增量 = 校正节点数），**AND** `kg_versions` 表新增一行 `status = writing → active`（**仅文档级 `kg_version`，不全局翻**，沿用 ADR-0002 三段式），**AND** 新 `kg_version` 写入 `ontology_actions.result_kg_version`。
7. **WHEN** 增量重算完成且 `kg_version` 落库，**THEN** M3 / M4 可立即消费该版本（沿用 ADR-0002，`status = active` 才对外可查），**AND** M2 §3 验收 4 的时序约束（**先 PG 后 Neo4j + `MERGE` 幂等键**）必须保持。

### 3.4 成本仪表盘（对应批次 D）

8. **WHEN** M2 / M3 任意接口被调用，**THEN** `token_usage`（输入 / 输出）与耗时字段落 `cost_metrics` 表（每日聚合，沿用 M2 §3 验收 7），**AND** `single_doc_cost = token_usage_total / doc_count`（按文档 ID 聚合），**AND** 增量 / 全量成本比 = `incremental_cost / full_rebuild_cost`，**AND** `GET /api/v1/cost/dashboard` 端点返回该指标（按 `date_from` / `date_to` 过滤）。
9. **WHEN** C3 准入线判定（TBD-7 阈值在 Sprint 13 §20.1 D 收敛），**THEN** 仪表盘提供**逐文档成本排行**与**增量/全量趋势**两视图，**AND** **不得**改写阈值（仅展示），**AND** 阈值常量定义在 `backend/app/core/config.py`，可经 `.env` 覆盖（沿用 CODEBUDDY 配置规范）。

### 3.5 跨模块硬约束

10. **WHEN** 任意 M6 接口被调用，**THEN** 日志携带 `trace_id`（经 M5 注入），**AND** 严禁 LLM 自动修改 `ontology_schemas`（必须经 GUI 用户确认，对应 GAP-F2）。
11. **WHEN** 任意 M6 接口被调用，**THEN** 校验用户对该 `org_id` 的校正权限（按 `user_roles.scene_scope = "ontology"`，**新增** scene，与 M5 §4.3 对齐），**AND** 跨 org 访问由 **ADR-0003 RLS** 拦截（**FORCE ROW LEVEL SECURITY + 受限 DB 角色 + `SET LOCAL app.current_org`**，详见 §18.1 C 承接）。

---

## 4. 数据模型概要

### 4.1 PostgreSQL 表 `ontology_schemas`（新增，对应批次 A）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `version` | INT | 是 | 否 | PK + idx | 版本号（自增；每 org 独立自增） |
| `org_id` | UUID | 是 | 否 | idx | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `entity_types` | JSONB | 是 | 否 | - | LLM 建议 + 用户确认的实体类型集合（数组，每项 `{name, description?}`） |
| `relation_types` | JSONB | 是 | 否 | - | 同上（每项 `{name, head_types, tail_types, description?}`） |
| `domain_description` | TEXT | 是 | 否 | - | 领域描述（用户输入） |
| `suggested_by_llm` | BOOL | 是 | 否 | - | 是否由 LLM 建议（true）/ 人工直接编辑（false） |
| `confirmed_by_user` | UUID | 是 | 否 | idx | 确认人 user_id（M5 表） |
| `confirmed_at` | TIMESTAMP | 是 | 否 | idx | 确认时间 |
| `status` | TEXT | 是 | 否 | idx | **`active / superseded`**（**仅 `active` 对外可查**，沿用 ADR-0002 状态机） |
| `trace_id` | UUID | 是 | 否 | - | 本次操作的 trace_id |
| `created_at` | TIMESTAMP | 是 | 否 | - | - |
| `updated_at` | TIMESTAMP | 是 | 否 | - | 状态变更时间 |

### 4.2 PostgreSQL 表 `ontology_actions`（新增，对应批次 B 审计）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `id` | UUID | 是 | 否 | PK | - |
| `org_id` | UUID | 是 | 否 | idx | 租户 ID（**ADR-0003**） |
| `action_type` | TEXT | 是 | 否 | idx | **`merge / split / rename`**（**仅三值**，plan §12 R12 收口） |
| `target_entities` | JSONB | 是 | 否 | - | 涉及实体 ID 列表（merge 2 个 / split N 个 / rename 1 个） |
| `actor_id` | UUID | 是 | 否 | idx | 操作人（M5 users.id） |
| `kg_version` | TEXT | 是 | 否 | idx | 操作时的 `kg_version`（用于回放） |
| `result_kg_version` | TEXT | 否 | 否 | idx | 增量重算后的新版本（NULL = 增量重算未完成或失败） |
| `error_code` | TEXT | 否 | 否 | - | 增量重算失败时的错误码（沿用 ADR-0002） |
| `error_detail` | TEXT | 否 | 是 | - | 失败明细（**敏感**，日志禁输出原文） |
| `trace_id` | UUID | 是 | 否 | idx | 本次操作的 trace_id |
| `created_at` | TIMESTAMP | 是 | 否 | idx | - |

### 4.3 PostgreSQL 表 `cost_metrics`（新增，对应批次 D + M2 §3 验收 7）

| 字段 | 类型 | 必填 | 敏感 | 索引 | 说明 |
|---|---|---|---|---|---|
| `id` | BIGSERIAL | 是 | 否 | PK | - |
| `org_id` | UUID | 是 | 否 | idx | 租户 ID（**ADR-0003**） |
| `date` | DATE | 是 | 否 | idx | 聚合日期（按 org + date 唯一） |
| `token_usage_input` | BIGINT | 是 | 否 | - | 当日输入 token |
| `token_usage_output` | BIGINT | 是 | 否 | - | 当日输出 token |
| `token_usage_total` | BIGINT | 是 | 否 | - | 总 token |
| `doc_count` | INT | 是 | 否 | - | 处理文档数（去重） |
| `single_doc_cost` | FLOAT | 是 | 否 | - | 单文档处理成本（`token_usage_total / doc_count`） |
| `incremental_cost` | FLOAT | 否 | 否 | - | 当日增量重算成本（可空） |
| `full_rebuild_cost` | FLOAT | 否 | 否 | - | 当日全量重建成本（可空，仅触发全量重建时落） |
| `cost_ratio` | FLOAT | 否 | 否 | - | 增量 / 全量成本比（**显著 < 1.00**，C3 准入线之一） |
| `created_at` | TIMESTAMP | 是 | 否 | - | - |
| `updated_at` | TIMESTAMP | 是 | 否 | - | - |

> **关键约束**：C3 准入线（plan §21.3）要求"增量 / 全量成本比显著 < 1.00"——`cost_metrics.cost_ratio` **是该约束的取证字段**。**Sprint 13 收尾必须用本表实测值裁决**。

### 4.4 与 M2 §4.5 `entity_merge_candidates` 表的接口对齐（**已核项目实际**）

> **关键约束**（基于已读 `specs/m2-extract-kg.md` §4.5）：M2 当前定义 `entity_merge_candidates.status` 枚举为 **`pending / auto_merged / human_review / rejected`**（**4 个值，无 `applied`**）。M6 GUI 消费的合并候选由 M2 §3 验收 3 提供（`similarity ∈ [0.70, 0.90]` 进入 `human_review`）。

| `entity_merge_candidates` 字段 | M2 §4.5 当前状态 | M6 落地所需的变更 |
|---|---|---|
| `status ∈ {pending, auto_merged, human_review, rejected}` | ✅ 已声明（4 值） | **M6 落地前必须升版 M2 spec**：在 M2 §4.5 表注脚加"M6 合并动作后置 `applied`"，**新增第 5 枚举值 `applied`**；**M2 §3 验收 3 也补一条对应说明**，保持两 spec 一致 |
| `left_entity_id` / `right_entity_id` / `similarity` | ✅ 已声明 | 不变 |
| `trace_id`（首次创建时落） | ✅ 已声明 | 不变（M6 校正时复用同一 `trace_id`，不另落） |

> **关键契约同步动作**（M6 Sprint 12 落地 checklist 第 1 项）：
> 1. **升版 M2 spec**：`specs/m2-extract-kg.md` §4.5 状态枚举加 `applied`，§3 验收 3 加补一条
> 2. **改 Pydantic 模型**：`backend/app/schemas/document.py`（或独立 `ontology.py`）的 `EntityMergeStatus` 枚举加 `applied`
> 3. **重导契约**：`uv run python scripts/export_openapi.py`（后端 CODEBUDDY §3 第 2 步）
> 4. **重导前端类型**：`cd frontend && npm run gen:api`（后端 CODEBUDDY §3 第 4 步）
> 5. **CI 契约零漂移校验**：`uv run python scripts/export_openapi.py --check` 与 `npm run gen:api` 无 diff
>
> **未走完前 5 步**，`/api/v1/ontology/merge` 端点不得对外实现——这是 §3.2 B 契约同步铁律的硬约束。

### 4.5 Neo4j 节点变更（与 M2 §4.1 对齐）

- `:Entity` 节点新增属性 `status`（取值 `active / split`，沿用 §3.2 验收 4）
- `:Entity.aliases` 复用 M2 §4.3（验收 5 重命名动作写入）
- `:Entity` 的 `id, kg_version` 仍为 MERGE 幂等键（沿用 ADR-0002 §3.1）

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **M2 实体关系抽取**：消费 M2 写入的 Neo4j `:Entity` 节点 / 关系；M6 校正与 M2 抽取共用 `kg_version` 标识
- **M5 权限与审计**：调用 M5 校验用户对 `org_id` 的校正权限（`scene_scope = "ontology"` 新增）；每次校正动作写 `audit_log`
- **M3 问答结果反馈**：M6 校正动作触发后，**问答结果应能立即反映**新图谱（沿用 M3 §3 验收 6 对 `kg_version` active 的消费）

### 5.2 下游被依赖

- **M2 抽取参数注入**：M2 调用 `entity_relation_extract_v1.md` 时，`entity_types` / `relation_types` 从 `ontology_schemas`（`status = active` 最新版本）读取；**不修改 prompt v1**（符合 PRD §7 "MVP 不新增 Prompt 版本" + CODEBUDDY H9）

### 5.3 与 M2 实体消解（`entity_merge_candidates`）的耦合

- M6 GUI 消费的合并候选由 M2 §3 验收 3 提供（`similarity ∈ [0.70, 0.90]` 进入 `human_review`）
- M6 GUI 提交"合并"动作后，把 `entity_merge_candidates.status` 从 `human_review` 改为 `applied`（**前提：M2 spec §4.5 已先升版加 `applied` 枚举**，详见 §4.4）
- **接口字段对齐**（与 M2 §4.5 一致）：`left_entity_id` / `right_entity_id` / `similarity` / `status`

### 5.4 与 M5 审计的耦合

- 校正动作 `merge / split / rename` 写 `audit_log`（`action = ontology.{merge,split,rename}`）
- 仪表盘查询由 `cost_metrics` 表直接读取（不审计，仅业务日志）
- **新增 scene 校验**：M5 §4.3 `user_roles.scene_scope` 新增 `"ontology"` 值（与现有 `affiliation` / `qa` 并列）

### 5.5 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/api/v1/ontology/cold-start` | `{domain_description}` | 200 `{suggested_entity_types, suggested_relation_types, trace_id}`；**仅建议，未生效** |
| `POST` | `/api/v1/ontology/confirm` | `{version, entity_types, relation_types}` | 200 `{version, status: "active"}`；409 `SCHEMA_VERSION_NOT_ACTIVE`（重复确认） |
| `POST` | `/api/v1/ontology/merge` | `{left_entity_id, right_entity_id}` | 200 `{kg_version, status: "applied"}`；403 跨 org（`FORBIDDEN`） |
| `POST` | `/api/v1/ontology/split` | `{entity_id, new_entities: [{canonical_name, ...}]}` | 200 `{kg_version, status: "applied"}` |
| `POST` | `/api/v1/ontology/rename` | `{entity_id, new_canonical_name}` | 200 `{kg_version, status: "applied"}` |
| `GET` | `/api/v1/ontology/active` | - | 200 `{version, entity_types, relation_types, status: "active"}`；409 无 active |
| `GET` | `/api/v1/cost/dashboard` | query: `date_from?, date_to?` | 200 `{token_usage_total, single_doc_cost, cost_ratio, by_date: [...]}` |

> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。
>
> **新增 7 个端点全部进入契约**：与 `OPENAPI` 门禁模式一致（M5 §3 同步契约铁律）；§3.2 B 段硬约束要求 §4 H10 契约先行。

---

## 6. 配置项

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `ONTOLOGY_LLM_SUGGEST_TIMEOUT` | INT | `30`（秒） | 冷启动 LLM 建议超时（避免批处理被拖死） |
| `INCREMENT_REBUILD_BATCH_SIZE` | INT | `100`（节点） | 增量重算每批节点数（避免大事务） |
| `COST_RATIO_ALERT_THRESHOLD` | FLOAT | `0.5` | 增量 / 全量成本比告警阈值（仅日志告警，不阻断） |

> 与 M2 §3 验收 7 的 `token_usage` 打点共用 `backend/app/core/config.py`，可经 `.env` 覆盖。

---

## 7. 与 PRD §2 口径冲突的说明（**v0.1 草案专属**）

> **本节为 v0.1 草案专属说明**，定稿时（v1.0）删除。

PRD §2（`docs/03-prd.md:55`）当前写"**M6 | 本体管理与增量更新 | P1（不在本期 MVP） | —**"——M6 不在 MVP 1.0 范围。

但 `docs/v1.1.0-demo-mvp-plan.md` §15.1 第 5 行（v3.0 变更）已把"**完整 M6**"吸收进 MVP 1.0，由 Sprint 12 承接：

> 旧口径：M6 不在 MVP
> v3.0 裁决：**完整 M6 进入 MVP**（C3 的验证载体）
> 承接：S12

**本 spec 落地即兑现 v3.0 承诺**。

**建议同步动作**（不在本草案范围内）：
- Sprint 12 启动前同步更新 PRD §2 状态行 / 表格（"P1 → P0，Sprint 12 承接"）；
- 附录 C 落清单加 `specs/m6-ontology-incremental.md`（与 5 份 spec 同列）。

---

## 8. 关键结论

> **M6 是 MVP 的"可持续运营"基础**——任意抽取系统都会犯错，没有校正闭环等于一次性玩具；没有成本仪表盘等于"承诺可达但无法证明"。

**对 PRD MVP 1.0 的差异化贡献**：
1. **M6 §3.1 冷启动**——把"先配 schema 才能用"的开销降到接近零（**对应 §3.1 B 类门槛**，plan §3.1）
2. **M6 §3.2 校正 GUI**——把"系统识别错误"的修复成本降到分钟级（**对应 §3.1 C 类门槛**，人工反馈交互需"AI 反馈、人工确认"）
3. **M6 §3.3 增量重算**——把"修一处"的修复代价降到全量的几分之一（**对应 C3 准入线**："增量 / 全量成本比显著 < 1.00"）
4. **M6 §3.4 成本仪表盘**——把"是否可达"从主观判断变成**实测可证**（**对应 TBD-7 收敛载体**）

**没有 M6 = MVP 1.0 不可持续运营**——Sprint 12 不能推迟。

---

## 9. 关联关系总览

| 关联文档 | 关系 |
|---|---|
| `specs/m2-extract-kg.md` §3 验收 3 / §4.5 | M6 消费 M2 实体消解候选；`status` 枚举同步扩展 |
| `specs/m3-graphqa-citation.md` §3 验收 6 | M6 校正后 M3 可观测新 `kg_version` |
| `specs/m5-permission-audit.md` §4.3 / §5.3 | M6 校验 `scene_scope = "ontology"` + RLS |
| `prompts/entity_relation_extract_v1.md` 第 16~18 行 | M6 参数化复用（**不修改**） |
| `prompts/kg_qa_v1.md` | M6 冷启动建议的 LLM 调用载体（**不修改**） |
| `docs/v1.1.0-demo-mvp-plan.md` §15.1 第 5 行 / §19 | M6 承接 |
| `docs/v1.1.0-demo-mvp-plan.md` §12 R12 | M6 GUI 工时风险（**只做三动作**） |
| `docs/03-prd.md` §2 / 附录 C | M6 状态行待同步（Sprint 12 启动前动作） |
| `ADR-0002 Neo4j ↔ PostgreSQL 一致性边界` §3.1 | M6 增量重算复用三段式 + MERGE 幂等键 |
| `ADR-0003 跨租户资源隔离粒度` §3.1 | M6 全量表带 `org_id` + RLS |
| `docs/dev-doc-status.md` | M6 spec 状态跟踪 |

---

## 10. v1.0 定稿 Checklist（**Sprint 12 开工闸门**，Sprint 11 收尾前完成）

> 依据 `docs/v2.0.0-ship-backward-plan.md` §5.2 D-1（本 spec 升 v1.0 是 S12 的开工闸门）。逐项勾选后才可置"版本：v1.0"。

- [ ] **§4.4 与 M2 §4.5 接口对齐复核**：确认 M2 §4.5 已加 `applied` 枚举（依赖 P1-4，S9 顺路完成）；若未加，本 spec 不得升 v1.0
- [ ] **PRD §2 / 附录 C 同步**：`docs/03-prd.md` §2 的 M6 行由"P1（不在本期 MVP）"改为"M6 进入 MVP 1.0，Sprint 12 承接"；附录 C 落清单加本 spec
- [ ] **本 spec §7 删除**：§7 是"v0.1 草案专属"的口径冲突说明，定稿后删除（口径已收敛进 PRD）
- [ ] **契约漂移核验**：`uv run python scripts/export_openapi.py --check` 与 `npm run gen:api` 均无 diff（本 spec §5.5 的 7 个端点届时须已进 `contracts/openapi.yaml`，否则说明契约未先行）
- [ ] **配置项消费者核验**：§6 的三个配置项（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `INCREMENT_REBUILD_BATCH_SIZE` / `COST_RATIO_ALERT_THRESHOLD`）在实现时**每个都必须能指出读取它的代码行**（根 `CODEBUDDY.md` §功能预留原则 第 6 条 / ADR-0004 §3 硬规则 5）——**无消费者的配置不得提交**
- [ ] **接缝登记核验**：M6 若引入新的 `settings.*` 或新实现类，核是否需要同步 `ADR-0004` §2.1 / `check_seams.py` 登记集合
- [ ] **版本行改写**：`> **版本**：v0.1（草案…）` → `> **版本**：v1.0`；`> **状态**：…` 去掉"草案"字样
- [ ] **回填 `docs/dev-doc-status.md`**：P1-3 置 ✅ 并注明日期

---

> **草案结束**。本 spec 自 v0.1 起即为 Sprint 12 的执行依据底稿；**v1.0 定稿的唯一增补内容 = §10 checklist 全部勾选**（§1~§6 的边界/验收/数据模型/端点/配置在 v0.1 已成型，定稿不重写）。