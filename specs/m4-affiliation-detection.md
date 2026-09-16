# M4 · 财务关联交易识别（首靶场景）— MVP 规格说明书

> **文档编号**：spec-m4
> **版本**：v1.0
> **状态**：MVP 规格（实现前）
> **上游依据**：`docs/02-product-outline.md` §3.2 M4
> **关联 Prompts**：`prompts/entity_relation_extract_v1.md`（场景适配模式）、`prompts/kg_qa_v1.md`
> **关联研究结论**：`01-research.md` §1.4 P3 详解、§1.5 图谱化必要性、§3.3 C1–C2
> **关联大纲**：`02-product-outline.md` §3.2 M4 + §6 准入线
> **关联 ADR**：[ADR-0001 异步任务后端选型](../docs/adr/ADR-0001-async-task-backend.md)、[ADR-0002 Neo4j ↔ PostgreSQL 一致性边界](../docs/adr/ADR-0002-neo4j-postgres-consistency.md)、[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**5 个功能点**，严格沿用 outline §3.2）

1. **PDF 合同 + CSV 发票 + CSV 凭证 + CSV 供应商主数据 四源对齐**
2. **主体-地址-法人-股东-电话 多类节点图建模**
3. **图连通分量 / 共享邻居 / 环路检测 三类算法并行**
4. **疑点清单 + 每条疑点回溯到具体合同 / 发票 / 凭证；附三方金额不一致检出**
5. **场景级门禁指标**：隐性关联召回 ≥ 0.80、误报率 ≤ 0.15、引用覆盖率 = 100%

### 1.2 Out of Scope（明确不做）

- **跨多币种 / 多税号规则的发票核验**（仅做人民币 + 同一税号格式，**多币种属 P2**）
- **与外部商业数据终端**（Wind / 企查查）的实时核验（不做，依赖人工导入）
- **关联交易披露报告自动生成**（仅生成疑点清单 + 关键证据，**披露报告由用户撰写**）
- **实时增量识别**（仅批处理，**实时增量属 P2**）
- **跨组织（多 Org）的关联交易识别**（MVP 单租户）

---

## 2. 核心用户故事

- 作为**内审 / 外审人员**，我希望系统能从合同 PDF + 发票 CSV + 凭证 CSV + 供应商主数据 CSV 中**自动识别**"同一地址 / 同一法人 / 交叉持股"的隐性关联，以便我能在审计底稿中聚焦高风险疑点。
- 作为**审计人员**，我希望每条疑点都能**回溯**到具体的合同页 / 发票号 / 凭证号，以便我能在审计复核时快速调取原件。
- 作为**审计主管**，我希望系统能检出"**合同金额 ≠ 发票金额 ≠ 凭证金额**"的不一致，以便我能在数据治理层先行排查。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。

1. **WHEN** 用户提交一组关联交易识别任务（≥ 1 PDF 合同 + ≥ 1 CSV 发票 / 凭证 / 供应商），**THEN** 系统完成四源主体对齐，**AND** 对齐成功率 ≥ 0.95（基于供应商主数据税号 + 名称 + 地址三字段匹配），**AND** 未对齐主体进入 `unaligned_subjects` 表待人工处理。
2. **WHEN** 四源对齐完成，**THEN** M4 在 Neo4j 中建立 `主体-地址-法人-股东-电话` 多类节点图，**AND** 每条节点带 `kg_version` 标识，**AND** 与 M2 已建立的通用节点**共享同一 `status = active` 的 `kg_version`**（**不分裂版本**，**ADR-0002**），**AND** 不得使用 `writing` / `failed` / `superseded` 版本。
3. **WHEN** 系统执行三类算法（连通分量 / 共享邻居 / 环路），**THEN** 任一算法命中即生成一条疑点，**AND** 疑点含 `{type, severity, entities[], evidence[], kg_version}` 结构，**AND** `type ∈ {shared_address, shared_legal_rep, shared_phone, cycle, amount_mismatch}`。
4. **WHEN** 生成疑点清单，**THEN** 每条疑点必须能回溯到 ≥ 1 个**具体**合同页 / 发票号 / 凭证号（**引用覆盖率 = 100%**），**AND** 不允许"基于启发式但无原文证据"的疑点，**AND** 对应反证条件 F3。
5. **WHEN** 三方金额不一致检出（合同金额 ≠ 发票金额 ≠ 凭证金额），**THEN** 系统生成独立的 `amount_mismatch` 类型疑点，**AND** `severity` 默认为 `high`，**AND** 给出"差额 + 三方各自金额 + 关联主体"的明细。
6. **WHEN** 场景准入指标测试（基于 200 合同 + 500 发票 + 100 凭证 + 20 组植入关联的样本），**THEN** 召回 ≥ 0.80（命中 ≥ 16 组）、误报率 ≤ 0.15、引用覆盖率 = 100%，**AND** 任意一项不达标即判定 M4 未通过准入（对应反证条件 F1 / F2 / F3）。
7. **WHEN** 用户提交任务，**THEN** 系统异步执行并返回 `task_id`（**复用 M1 的状态机与 `TaskManager`，见 ADR-0001**），**AND** 完成后通过 `GET /affiliation/tasks/{id}` 查询结果，**AND** 结果以 `affiliation_suspicions` 列表 + 每条回溯引用的结构回传，**AND** 服务重启时 `affiliation_tasks` 中遗留的 `pending` / `processing` 任务由启动回收**批量置 `failed`**（`error_code = TASK_INTERRUPTED`）。

> **关联 MVP 准入线**：C1（图谱相对 RAG 增益 ≥ 10%）/ C2（召回 ≥ 0.80 + 误报 ≤ 0.15 + 引用覆盖 = 100%）/ F1（增益 < 10% 退 RAG-first）/ F2（召回 < 0.80 暂缓图谱化）。

---

## 4. 数据模型概要

### 4.1 Neo4j 节点（M4 专属增量建模）

| Label | 关键属性 | 说明 |
|---|---|---|
| `:Subject` | `id, name, tax_id, type, kg_version` | 主体（公司 / 个体工商户 / 个人） |
| `:Address` | `id, full_address, region_code, kg_version` | 地址 |
| `:LegalPerson` | `id, name, id_type, id_hash, kg_version` | 法人 / 自然人（`id_hash` 仅哈希，不存原值） |
| `:Phone` | `id, number_hash, kg_version` | 电话（仅哈希） |
| `:Invoice` | `id, invoice_no, amount, issuer_tax_id, issue_date, kg_version` | 发票 |
| `:Voucher` | `id, voucher_no, amount, posting_date, kg_version` | 凭证 |
| `:Contract` | `id, contract_no, amount, signed_date, kg_version` | 合同 |

### 4.2 Neo4j 关系（M4 专属增量）

| Type | 端点 | 关键属性 | 说明 |
|---|---|---|---|
| `:REGISTERED_AT` | `:Subject` → `:Address` | - | 注册地址 |
| `:LEGAL_REP` | `:Subject` → `:LegalPerson` | - | 法人代表 |
| `:SHARES_HOLDER` | `:Subject` → `:Subject` | `share_pct, since` | 持股 |
| `:CONTACT_PHONE` | `:Subject` → `:Phone` | - | 联系电话 |
| `:ISSUED` | `:Subject` → `:Invoice` | - | 发票开具 |
| `:POSTED_IN` | `:Voucher` → `:Subject` | - | 凭证记账 |
| `:PARTY_TO` | `:Subject` → `:Contract` | `role` | 合同当事人 |

### 4.3 PostgreSQL 表 `affiliation_suspicions`（新增）

| 字段 | 类型 | 必填 | 敏感 | 说明 |
|---|---|---|---|---|
| `id` | UUID | 是 | 否 | PK |
| `org_id` | UUID | 是 | 否 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `suspicion_type` | TEXT | 是 | 否 | `shared_address / shared_legal_rep / shared_phone / cycle / amount_mismatch` |
| `severity` | TEXT | 是 | 否 | `high / medium / low` |
| `entities` | JSONB | 是 | 否 | 涉及主体 id 列表 |
| `evidence` | JSONB | 是 | 否 | 引用列表（合同 / 发票 / 凭证的具体标识） |
| `kg_version` | TEXT | 是 | 否 | 关联的图谱版本 |
| `trace_id` | UUID | 是 | 否 | - |
| `status` | TEXT | 是 | 否 | `open / dismissed / confirmed` |
| `created_at` | TIMESTAMP | 是 | 否 | - |
| `reviewed_by` | UUID | 否 | 否 | 复核人（M5 用户） |
| `reviewed_at` | TIMESTAMP | 否 | 否 | - |

### 4.4 PostgreSQL 表 `affiliation_tasks`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | UUID | 是 | task_id（复用 M1 的 task_id 形态） |
| `org_id` | UUID | 是 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `doc_ids` | UUID[] | 是 | 关联文档 id 列表 |
| `status` | TEXT | 是 | `pending / processing / completed / failed`（**ADR-0001**，唯一真值源 = PostgreSQL） |
| `retry_count` | INT | 否 | 当前已重试次数（**H8**，每次重试写回） |
| `error_code` | TEXT | 否 | 失败错误码（含 `TASK_INTERRUPTED`） |
| `error_detail` | TEXT | 否 | 失败明细（**敏感**，日志禁输出） |
| `result_summary` | JSONB | 否 | 完成后填入 `{total, by_type, top_5_severity}` |
| `trace_id` | UUID | 是 | - |
| `created_at` | TIMESTAMP | 是 | - |
| `updated_at` | TIMESTAMP | 是 | 最近状态变更时间 |
| `completed_at` | TIMESTAMP | 否 | - |

### 4.5 PostgreSQL 表 `unaligned_subjects`（新增）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | UUID | 是 | PK |
| `org_id` | UUID | 是 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `raw_name` | TEXT | 是 | 原始名（如发票抬头） |
| `source_doc_id` | UUID | 是 | 来源文档 |
| `reason` | TEXT | 是 | 未对齐原因（名称不一致 / 税号缺失 / 多候选） |
| `candidates` | JSONB | 否 | 候选主数据 id 列表 |
| `status` | TEXT | 是 | `pending / aligned / ignored` |
| `created_at` | TIMESTAMP | 是 | - |

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **M2 实体关系抽取**：消费 `:Entity` / `:AFFILIATED_WITH` / `:PARTY_TO` / `:SUPPLIES_TO` 等**通用**节点与关系
- **M5 权限与审计**：调用 M5 校验访问权限；疑点产生事件写 `audit_log`

### 5.2 下游被依赖

- **M5 权限与审计**：消费 `affiliation_suspicions` 与 `affiliation_tasks` 写入
- **M3 意图路由**：当问题意图为"关联交易识别"时**路由到 M4**

### 5.3 与 M5 审计的耦合

- **禁止输出** 法人身份证号哈希 / 电话哈希 / 税号原文 至日志
- 疑点状态变更（`open / dismissed / confirmed`）必须留痕（含 `actor_id` 与 `trace_id`）

### 5.4 算法模式（草案）

```cypher
// 共享地址：≥ 2 个 Subject 注册到同一地址
MATCH (s1:Subject)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(s2:Subject)
WHERE s1 <> s2 AND s1.kg_version = $kg AND s2.kg_version = $kg
RETURN s1, s2, a

// 共享法人：≥ 2 个 Subject 由同一 LegalPerson 代表
MATCH (s1:Subject)-[:LEGAL_REP]->(l:LegalPerson)<-[:LEGAL_REP]-(s2:Subject)
WHERE s1 <> s2 AND s1.kg_version = $kg AND s2.kg_version = $kg
RETURN s1, s2, l

// 环路：A → B → C → A 持股
MATCH path = (a:Subject)-[:SHARES_HOLDER*2..4]->(a)
WHERE a.kg_version = $kg
RETURN nodes(path), relationships(path)

// 三方金额不一致
MATCH (c:Contract {contract_no: $c})<-[:PARTY_TO]-(s:Subject)
MATCH (i:Invoice {invoice_no: $i})-[:ISSUED]->(s)
MATCH (v:Voucher {voucher_no: $v})-[:POSTED_IN]->(s)
WHERE c.amount <> i.amount OR i.amount <> v.amount OR c.amount <> v.amount
RETURN c, i, v, c.amount, i.amount, v.amount
```

### 5.5 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/affiliation/detect` | `{doc_ids: [...]}` | 202 `{task_id, status: "pending"}` |
| `GET` | `/affiliation/tasks/{id}` | - | 200 `{task_id, status, result_summary?}` |
| `GET` | `/affiliation/suspicions` | query: `severity?, type?, status?` | 200 疑点列表 |
| `PATCH` | `/affiliation/suspicions/{id}` | `{status: "dismissed" \| "confirmed"}` | 200 |

> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。

> **关键结论**：**M4 是"图谱刚需"的唯一 MVP 承载**——若 M4 未通过准入线（召回 ≥ 0.80 / 误报 ≤ 0.15 / 引用覆盖 = 100%），**整个 MVP 退回 RAG-first 产品形态**（对应反证条件 F1）。**M4 的成败决定了项目 MVP 是否成立**。