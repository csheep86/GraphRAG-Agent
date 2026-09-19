# M2 · 实体关系抽取与知识图谱构建 — MVP 规格说明书

> **文档编号**：spec-m2
> **版本**：v1.0
> **状态**：MVP 规格（实现前）
> **上游依据**：`docs/02-product-outline.md` §3.2 M2
> **关联 Prompts**：`prompts/chunk_summary_v1.md`、`prompts/entity_relation_extract_v1.md`
> **关联研究结论**：`01-research.md` §1.4 P3（应用能力）、§3.1.2 能力 2–3；假设 A3 / A4
> **关联大纲**：`02-product-outline.md` §3.2 M2 + §6 准入线
> **关联 ADR**：[ADR-0002 Neo4j ↔ PostgreSQL 一致性边界](../docs/adr/ADR-0002-neo4j-postgres-consistency.md)、[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**5 个功能点**，严格沿用 outline §3.2）

1. **MinerU 结构化解析** PDF 表格 / 章节 / 脚注（保留版面与坐标）
2. **LangExtract 抽实体 / 关系 / 证据**（输出 `{entity, relation, evidence_span, confidence}`）
3. **跨文档实体消解**（全称 / 简称 / 曾用名 / 英文名归一）
4. **写入带版本号的 Neo4j KG**（每次写入 = 新版本，便于回滚与差异比对）
5. **中文复杂表格优先**（覆盖招股书 / 合同附表 / 凭证清单）

### 1.2 Out of Scope（明确不做）

- **多模态图片 / 视频实体抽取**（MVP 不含）
- **跨语种抽取**（**仅中文优先**，英文作为 P2 扩展）
- **自动本体 schema 生成**（**仅"建议"不"自动生效"**，本体冷启动是 M6 的职责）
- **知识图谱的可视化探索**（属 P2 扩展 E7）
- **与第三方本体对齐**（Wikidata / Schema.org 对接）（不做）

---

## 2. 核心用户故事

- 作为**审计用户**，我希望上传的合同 PDF 中的主体（如公司名）能与发票 CSV 中的抬头**自动归一**，以便我能发现"看似不同名实为同一公司"的隐性关联。
- 作为**运维 / 数据治理人员**，我希望图谱每次写入都有**版本号**，且能回滚至任意历史版本，以便我能在抽取错误时快速回退而不丢数据。
- 作为**业务用户**，我希望中文合同附表中的"股东 / 出资比例"等表格字段能被准确抽取为结构化关系，以便后续多跳查询可基于这些关系遍历。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。

1. **WHEN** M1 完成文档解析并投递 M2 任务，**THEN** M2 调用 MinerU 完成结构化解析并落中间表示（chunk 列表 + 版面坐标），**AND** 平均解析时延 P95 ≤ 30s / 100 页（中文表格型 PDF），**AND** 表格字段还原准确率 ≥ 0.85（基于 50 份样本实测）。
2. **WHEN** LangExtract 执行抽取，**THEN** 每个三元组输出 `{entity, relation, evidence_span, confidence}`，**AND** `confidence` 字段落 Neo4j 节点 / 关系属性（用于 M3 过滤），**AND** `evidence_span` 必须含 `doc_id + chunk_id + char_offset + text`。
3. **WHEN** 抽取结果包含 2 个以上名称相似但不同的实体（如"ABC 公司"与"ABC股份有限公司"），**THEN** 实体消解器返回合并候选（含相似度评分），**AND** 评分 ≥ 0.90 的候选**自动合并**（写 Neo4j + 落 `entity_merge_candidates.status=auto_merged`），**AND** 0.70–0.90 的候选**进入人工校正队列**（`status=human_review`，由 M6 处理），**AND** < 0.70 的候选**保持独立**。
4. **WHEN** 任一抽取结果写入 Neo4j，**THEN** 该次写入生成一个版本号 `kg_version`（ISO 时间戳 + ULID 后缀），**AND** 写入顺序**严格**为「**先 PG 后 Neo4j**」（**ADR-0002**）：① `kg_versions` **插入** `status = writing` → ② 写入 Neo4j（**必须 `MERGE`**，以 `(id, kg_version)` 为幂等键，保证重放安全）→ ③ 成功置 `active` / 失败置 `failed` 并记 `error_code` / `error_detail`，**AND** 不删除或覆盖历史版本（历史版本仅 `superseded` 标记，不删），**AND** PostgreSQL `kg_versions` 表记录 `{version, org_id, doc_id, status, error_code?, error_detail?, reconciled_at?, trace_id, created_at, updated_at}`。
5. **WHEN** 抽取过程中 LangExtract 抛错或超时，**THEN** tenacity 指数退避重试 ≤ 3 次（初始 1s、倍数 2），**AND** 最终失败触发 M5 审计 `extract.fail` 事件，**AND** `documents.status` 置为 `failed` 且 `error_code` 落库。
6. **WHEN** 抽取完成且 `kg_version` 落库，**THEN** M2 投递索引更新事件（`kg_version` 标识），**AND** M3 / M4 可立即消费该版本。
7. **WHEN** 任意接口被调用，**THEN** 日志携带 `trace_id`，**AND** token 用量与耗时字段打点（用于成本仪表盘，对应准入线 C3）。

> **关联 MVP 准入线**：A3（解析质量实测）/ A4（抽取 precision ≥ 0.85）；C1（增益 ≥ 10%）/ C2（召回 ≥ 0.80）/ C3（成本可控）。

---

## 4. 数据模型概要

### 4.1 Neo4j 节点（M2 主写入）

| Label | 关键属性 | 说明 |
|---|---|---|
| `:Document` | `id, filename_hash, mime, uploaded_at, kg_version` | 文档节点（M1 元数据 + M2 写入） |
| `:Chunk` | `id, doc_id, text, page, bbox, kg_version` | 文档块（带版面坐标） |
| `:Entity` | `id, type, canonical_name, aliases[], confidence, pii_flags[], kg_version` | 实体（公司 / 自然人 / 法人 / 地址 / 证件号等） |
| `:Evidence` | `doc_id, chunk_id, char_offset, text, kg_version` | 证据（指向原文 span） |

### 4.2 Neo4j 关系（M2 主写入）

| Type | 关键属性 | 端点 | 示例 |
|---|---|---|---|
| `:HAS_CHUNK` | - | `:Document` → `:Chunk` | 文档-块 |
| `:MENTIONS` | `confidence` | `:Chunk` → `:Entity` | 块-实体 |
| `:SUPPORTED_BY` | `confidence` | `:Entity` / 关系 → `:Evidence` | 实体 / 关系-证据 |
| `:AFFILIATED_WITH` | `type, share_pct, since` | `:Entity` → `:Entity` | 关联（股权 / 任职 / 地址 / 法人） |
| `:SUPPLIES_TO` | `contract_id, amount` | `:Entity` → `:Entity` | 供应关系 |
| `:PARTY_TO` | `role` | `:Entity` → `:Document` | 合同当事人 |
| `:HAS_FINANCIAL_INDICATOR` | `relation_name, derived` | `:Entity` → `:Entity` | 实体↔财务指标（桥梁抽取） |
| `:OPERATES_SEGMENT` | `relation_name, derived` | `:Entity` → `:Entity` | 实体经营业务板块（桥梁抽取） |
| `:RELATED` | `relation_name, derived` | `:Entity` → `:Entity` | 通用实体关联兜底（桥梁抽取） |

### 4.3 关键属性约束

| 字段 | 类型 | 敏感 | 说明 |
|---|---|---|---|
| `:Entity.canonical_name` | STRING | 否 | 主名（消解后的标准名） |
| `:Entity.aliases` | LIST<STRING> | 否 | 别名列表（含曾用名 / 简称 / 英文名） |
| `:Entity.confidence` | FLOAT | 否 | 抽取置信度 0–1 |
| `:Entity.pii_flags` | LIST<STRING> | **是** | 敏感标记（身份证 / 银行账号等），**日志禁输出** |
| `:AFFILIATED_WITH.share_pct` | FLOAT | 否 | 持股比例 |
| `:AFFILIATED_WITH.since` | DATE | 否 | 起算日期 |

### 4.4 PostgreSQL 表 `kg_versions`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `version` | TEXT | 是 | ISO 时间戳 + ULID（如 `20260320T1430Z-01H9X9...`） |
| `org_id` | UUID | 是 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `doc_id` | UUID | 是 | 来源文档 |
| `status` | TEXT | 是 | **`writing / active / superseded / failed`**（**ADR-0002**：`writing` = 写入中；**仅 `active` 对外可查**） |
| `node_count` | INT | 否 | 本版本新增 / 更新的节点数 |
| `relation_count` | INT | 否 | 本版本新增 / 更新的关系数 |
| `error_code` | TEXT | 否 | Neo4j 写失败时的错误码（**ADR-0002**） |
| `error_detail` | TEXT | 否 | 失败明细（**敏感**，日志禁输出） |
| `reconciled_at` | TIMESTAMP | 否 | 对账收敛时间（**ADR-0002 §3.4**，`NULL` = 未对账） |
| `created_at` | TIMESTAMP | 是 | 创建时间 |
| `updated_at` | TIMESTAMP | 是 | 最近状态变更时间（对账超时判定依赖此列） |
| `trace_id` | UUID | 是 | 本次抽取的 trace_id |

### 4.5 PostgreSQL 表 `entity_merge_candidates`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | UUID | 是 | 候选 id |
| `org_id` | UUID | 是 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `left_entity_id` | UUID | 是 | 左实体 |
| `right_entity_id` | UUID | 是 | 右实体 |
| `similarity` | FLOAT | 是 | 0–1 |
| `status` | TEXT | 是 | `pending / auto_merged / human_review / rejected` |
| `created_at` | TIMESTAMP | 是 | - |
| `trace_id` | UUID | 是 | - |

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **M1 多模态接入**：消费 `documents.id` + `storage_key` + `mime_type`，**触发条件** = `M1 documents.status = completed`

### 5.2 下游被依赖

- **M3 图谱问答**：消费 Neo4j 节点 / 关系；查询由 `kg_version` 标识
- **M4 关联交易识别**：消费 `:Entity` / `:AFFILIATED_WITH` / `:PARTY_TO` / `:SUPPLIES_TO` 等节点与关系
- **M5 权限与审计**：抽取 / 消解 / 写入事件均产生 `audit_log`（`action = entity.extract / entity.merge / kg.write`）

### 5.3 与 M5 审计的耦合

- **禁止输出 `pii_flags`** 至任何日志
- 写入失败或自动合并事件必须留痕（含 `trace_id`）
- 写入事件 `detail` 仅含节点 / 关系计数 + 实体类型分布，不含原文

### 5.4 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/internal/extract` | `{doc_id, storage_key, mime_type}` | 202 接受 / 401 / 500 |
| `GET` | `/internal/kg/{doc_id}/versions` | - | 200 `{versions: [...]}` |
| `GET` | `/internal/kg/active` | - | 200 `{version, status: "active", created_at, scope}`；**仅返回 `status = 'active'` 的最新版本**（**ADR-0002**）；无 `active` 版本时返回 **409** `KG_VERSION_NOT_ACTIVE` |
| `GET` | `/api/v1/documents/{id}/graph` | - | 200 `{doc_id, kg_version, version_status: "active", nodes[], edges[], node_count, relation_count, truncated, trace_id}`；该文档无 `active` 版本时 **409** `KG_VERSION_NOT_ACTIVE`（**ADR-0002**）；跨租户 **403** `FORBIDDEN`（**ADR-0003**） |

> **`KG_VERSION_NOT_ACTIVE` 的 HTTP 状态码统一为 409**（依据 **ADR-0002** §3.2 与 [`specs/m3-graphqa-citation.md`](./m3-graphqa-citation.md) §4.1）。本节原草案写作 404，**已作废**，一律以 409 为准。
>
> **`GET /api/v1/documents/{id}/graph`** 是本模块唯一对外暴露的只读端点，登记于此以免契约与规格脱节；返回体**刻意不含 `pii_flags`**（见 §5.3），且规模上限对齐 M3 §3 验收 1（单次节点数 ≤ 500，超限 `truncated = true`）。`/internal/*` 端点仅限服务间调用，**不进入对外契约**。
>
> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。Sprint 1 已定稿的 5 个接口见 [`contracts/openapi.yaml`](../../contracts/openapi.yaml) 与 [`docs/multimodal_rag_backend_api_spec-v1.0.md`](../../docs/multimodal_rag_backend_api_spec-v1.0.md)；其中 `/api/v1/documents/{id}/graph` 的实现在 **Sprint 3**，当前占位返回 501 `NOT_IMPLEMENTED`。

### 5.5 数据流图（片段）

```
M1 (completed) → 投递 → M2
                 ↓
        MinerU 解析 → chunk 列表 + 版面坐标
                 ↓
        LangExtract 抽 entity/relation/evidence
                 ↓
        实体消解 → 自动合并 / 人工队列 / 保持独立
                 ↓
        ① kg_versions 落库（status=writing，先写 PG）
                 ↓
        ② 写入 Neo4j（MERGE 幂等，kg_version=新版本号）
                 ↓
        ③ 成功 → status=active；失败 → status=failed（不对外提供）
                 ↓
        投递 M3 / M4 索引更新事件（仅 active 版本）
        （启动 / 周期对账：writing 超时 → 探测 Neo4j → active / failed）
```

> **关键结论**：**M2 是图谱层唯一的写入入口**。**M3 / M4 仅消费**，**M5 仅审计**。这一职责切分是后续所有多跳查询与场景识别的基础——任何绕过 M2 直接写入 Neo4j 的代码路径都应被 lint 规则拦截。