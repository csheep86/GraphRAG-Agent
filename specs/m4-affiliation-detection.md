# M4 · 财务关联交易识别（首靶场景）— MVP 规格说明书

> **文档编号**：spec-m4
> **版本**：v1.0
> **状态**：MVP 规格（v1.0.0 已交付；**2026-09-29 S9.12 收尾刷新实现态**——**部分实现**：五类算法（规则型两类 + 算法型三类）+ 四源对齐 + 三张 PG 表 + 四个对外端点 + 前端疑点页 + `domain_events` 事件出口已落地（`v1.3.0`）；**仅场景准入指标（§3 验收 6：200 合同 / 500 发票 / 100 凭证 / 20 组植入）未做** —— 语料规模远不足，维持登记 **S13**。判据见 **§4.7**，真机产出见 **§6**。逐条对账见 `docs/acceptance-traceability-matrix.md` §3.3；完整实现态与缺口见 `backend/CODEBUDDY.md` §4 与 `docs/release-notes/v1.3.0.md` §6）
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
| `task_id` | UUID | 是 | 否 | 产出该疑点的 `affiliation_tasks.id`（**S7.2 决策 B2 新增**，见文末注记） |
| `trace_id` | UUID | 是 | 否 | - |
| `status` | TEXT | 是 | 否 | `open / dismissed / confirmed` |
| `created_at` | TIMESTAMP | 是 | 否 | - |
| `reviewed_by` | UUID | 否 | 否 | 复核人（M5 用户） |
| `reviewed_at` | TIMESTAMP | 否 | 否 | - |

> **字段变更登记（2026-09-24，Sprint 7.2 批次 B，决策 B2，已人工确认）**：上表新增 `task_id`。
> **理由**：「一次检测 = 一条 `affiliation_tasks` 记录」后，`GET /affiliation/suspicions` 必须能回答「返回哪一批疑点」；无该字段时只能靠 `created_at` 判定最新批次（并发 / 补跑下不稳）或返回全部历史疑点（新旧混杂）。
> **执行注意**：建表即须保证有写入方——`risk.detect` 落库时写入当前任务 id，**不得建成「列存在但无人写」**（CODEBUDDY.md §功能预留原则 第 6 条：登记集合 = 实现集合）。
>
> **类型降维说明（实现期，非 spec 变更）**：本表 `entities` / `evidence` 在 spec 中为 `JSONB`、`task_id` 为 `UUID`；在 **development 的 SQLite 替身**下降维为跨方言 `JSON` 列与字符串（沿用 `kg_versions.source_doc_ids` 既有写法），**语义以 PostgreSQL 为准**（`backend/CODEBUDDY.md` §1）。

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

### 4.6 四源 CSV schema（**Sprint 9.11 冻结**）

> **冻结纪律（plan §20 R14）**：列名 / 必填 / 校验先冻结，**冻结后才写算法**。
> 本批次（S9.11）只冻结**三张结构化 CSV**；合同 PDF 走 M2 抽取链路，
> `:Contract` 节点与三方金额比对属 **批次 C2**，此处只登记不实现。

#### 4.6.1 `suppliers.csv`（供应商主数据 = **canonical 主体**）

| 列名 | 必填 | 校验 | 说明 |
|---|---|---|---|
| `supplier_id` | 是 | 非空、表内唯一 | 主数据主键 |
| `tax_id` | 是 | 18 位 + 字符集 `0-9A-HJ-NPQRTUWXY`（GB32100-2015，去易混淆字符） | **对齐第一优先级**；唯一真源（抽取侧拿不到税号，`kg/builder.py` 恒写 `None`） |
| `name` | 是 | 非空 | **对齐第二优先级** |
| `address` | 是 | 非空 | **对齐第三优先级** |

> **已知限制（登记，不掩饰）**：`tax_id` **只做格式校验，不做 GB32100 校验位**。
> 校验位算法会让合成语料为"看起来合法"而凑数——与其造假，不如诚实声明只验格式。

#### 4.6.2 `invoices.csv` / `vouchers.csv`（待对齐源）

| 列名 | 必填 | 校验 | 说明 |
|---|---|---|---|
| `invoice_no` / `voucher_no` | 是 | 非空、表内唯一 | 业务主键 ⇒ 节点 id |
| `counterparty_tax_id` | **否（可缺失）** | 非空时须合 §4.6.1 的 `tax_id` 格式 | 对齐第一优先级 |

> **「必填」是列级，「可缺失」是值级**：`counterparty_tax_id` 列**必须存在**，但值
> **允许为空**——「发票抬头没写税号」是真实业务情形，正是 §4.5 未对齐原因之一
> （此时退到名称 / 地址级）。**有值却格式非法 = 语料错误**（不是"缺失"），必须报出。
| `counterparty_name` | 是 | 非空 | 对齐第二优先级（发票抬头原文，可含别名写法） |
| `counterparty_address` | 是 | 非空 | 对齐第三优先级 |
| `amount` | 是 | 数值 > 0 | C2 的 `amount_mismatch` 三方比对用；本批次只落库不比对 |
| `issue_date` / `posting_date` | 是 | `YYYY-MM-DD` | 同上 |

> **必填列缺失 = 语料错误，不是对齐问题**：逐条报出并**终止**（不静默跳过，
> 与接缝 8 `external_data/schema.py` 同一条诚实性纪律）。

#### 4.6.3 对齐口径（**三级递减，先命中者胜**）

1. **税号**：`tax_id` 精确相等；
2. **规范化名称**：去空白 + 全角转半角 + 去后缀（`有限责任公司` / `有限公司` / `股份` / `公司`）；
3. **规范化地址**：去空白 + 全角转半角 + 去标点。

- **多候选**（任一级命中 > 1 个 canonical 主体）**不自动合并**——宁可留人工，不猜；
- **成功率** = 对齐成功行数 / 待对齐总行数（发票 + 凭证），判据 **≥ 0.95**（§3 验收 1）。

#### 4.6.4 `unaligned_subjects.reason` 取值（逐字照 §4.5）

| 取值 | 触发条件 |
|---|---|
| `tax_id_missing` | 税号缺失 / 格式非法 **且** 名称与地址都未命中 |
| `name_mismatch` | 税号已存在（或有值）但三级都未命中 |
| `multiple_candidates` | 任一级命中 > 1 个 canonical 主体 |

#### 4.6.5 图模型落点（**双标签，理由必须写明**）

本批次落 `:Entity:Subject` / `:Entity:Invoice` / `:Entity:Voucher`，关系
`(:Subject)-[:ISSUED]->(:Invoice)`、`(:Voucher)-[:POSTED_IN]->(:Subject)`
（逐字照 §4.2）。**为什么打 `:Entity` 双标签**：

- `:Subject` / `:Invoice` / `:Voucher` 是 §4.1 的语义标签，**M4 算法 Cypher 只认它**；
- 但真机读侧（`graphs.py`、`/graph/overview`）**只读 `:Entity`**，且 §4.5 的疑点证据
  回溯路径要求 `(:Subject).source_entity_ids[]` 指向被 `:Chunk-[:MENTIONS]->(:Entity)`
  引用的节点（`_QUERY_AFFILIATION_EVIDENCE`）；
- ⇒ 只打 `:Subject` 会重演 `demo/attendance/mapping.yaml:11-26` 记下的老伤
  （进得了库、查不出来）。双标签同时满足两侧，**不**是权宜之计。

`:Subject` 额外带 `address` / `tax_id` 属性（§4.1 未列 `address`，此处为三级对齐的可核留痕）；
`:Address` 节点与 `REGISTERED_AT` 关系属 **C2**（`shared_address` 一并做）。

#### 4.6.6 语料增补（**Sprint 9.12 增补，S9.11 的 §4.6.1–4.6.2 不被推翻**）

算法需要输入；S9.11 冻结的三张表**没有**电话 / 持股 / 合同三方金额 ⇒
三类算法与 `amount_mismatch` **无输入可算**。故增补（**只加列 / 加表，不改既有列语义**）：

| 目标 | 增补 | 说明 |
|---|---|---|
| `shared_phone` | `suppliers.csv` 加列 `phone` | 落 `:Phone{number_hash}` + `CONTACT_PHONE`；**只存哈希**（§4.1） |
| `shared_legal_rep` | `suppliers.csv` 加列 `legal_rep_name` + `legal_rep_id` | 落 `:LegalPerson{id_hash}` + `LEGAL_REP`；身份证号**只存哈希** |
| `shared_address` | `suppliers.csv` 已有 `address` | 落 `:Address` + `REGISTERED_AT`（§4.6.5 登记的 C2 项） |
| `cycle` | 新增 `shareholders.csv`：`holder_tax_id, held_tax_id, share_pct, since` | 落 `(:Subject)-[:SHARES_HOLDER]->(:Subject)` |
| `amount_mismatch` | `invoices.csv` / `vouchers.csv` 加列 `trade_ref`；新增 `contracts.csv` | 三方按 `trade_ref` 配对 |

**⚠️ 已知偏离（登记，不掩饰）**：spec §1.1 的合同是 **PDF**（走 M2 抽取链路）。
合成语料阶段用 `contracts.csv` 作为**三方金额的等价替身**——本批次验证的是
「算法判据与三方比对」，**不是** PDF 抽取。真机合同仍须走 M2；
替身与抽取产物的汇合点 = `:Contract` 节点属性，两者形状一致。

`contracts.csv` 列：`contract_no, trade_ref, party_a_tax_id, party_a_name, party_a_address,
party_b_tax_id, party_b_name, party_b_address, amount, signed_date`（两方各走三级对齐，
`PARTY_TO` 带 `role = A | B`）。

---

## 4.7 三类算法与金额不一致判据（**Sprint 9.12 冻结**）

> 出处：§1.1 第 3 / 4 点、§3 验收 3 / 5。**纪律（plan §20 R14 + C0 的 D-3）**：
> 判据先冻结，冻结后才写算法。**判据里没写的信号，不许进代码。**

### 4.7.1 通用判据（五类共用）

1. **无证据不产疑点**：任一命中取不到 ≥ 1 条 `:Chunk` 证据 ⇒ **丢弃**并打
   `affiliation_suspicion_dropped_no_evidence`（§3 验收 4 引用覆盖率 = 100%）；
2. **对称去重**：无向共享类用 `s1.id < s2.id`；环用「环上 id 排序后的 key」；
3. **租户 + 版本过滤**：`org_id` 与 `kg_version` 双重（ADR-0003；
   `kg_version` 不等于租户边界）；
4. **无阈值可调**：本批次**不引入任何可调参数**（tasks §2.3 D6：阈值调参 =
   给「凑够 N 条疑点」留后门）。严重度**按类型固定**（见 4.7.2）。

### 4.7.2 逐类判据

| `type` | 命中条件 | `severity` | `entities` | 备注 |
|---|---|---|---|---|
| `shared_address` | 两 `:Subject` 经 `REGISTERED_AT` 指向同一 `:Address` | medium | `[A, B, address]` | S7.1 已实现，本批次补数据 |
| `shared_legal_rep` | 两 `:Subject` 经 `LEGAL_REP` 指向同一 `:LegalPerson` | medium | `[A, B, legal_person]` | 同上 |
| `shared_phone` | 两 `:Subject` 经 `CONTACT_PHONE` 指向同一 `:Phone` | medium | `[A, B, phone]` | 本批次新增 |
| `cycle` | `SHARES_HOLDER` 有向环，**长度 2..4** | medium | 环上主体 id（**遍历顺序**） | 本批次新增 |
| `amount_mismatch` | 同一 `trade_ref` 上合同 / 发票 / 凭证金额**不全相等** | **high**（§3 验收 5 明定） | `[contract, invoice, voucher]` | 本批次新增 |

- **`cycle` 长度下限 2**：A→B→A 即交叉持股（最常见的隐性关联），**必须**算环；
  **上限 4**：超过 4 跳的路径爆炸且审计可解释性差（登记为判据，非性能妥协）。
  同一环会被多个起点各遍历一次 ⇒ 用「环上 id 排序后拼接」的 key 去重，只留一条。
- **`amount_mismatch` 三方必须齐**：`trade_ref` 下合同 / 发票 / 凭证**缺任一方 ⇒ 不产出**
  （spec 明写「三方金额不一致」，两方不等不是同一件事——**不拿两方冒充三方**）。
- **明细**：`amount_mismatch` 须给出「差额 + 三方各自金额 + 关联主体」（§3 验收 5）。
  落 `affiliation_suspicions.details`（**新列，JSONB，可空**），
  `{trade_ref, contract_amount, invoice_amount, voucher_amount, max_diff}`；
  其余类型该列为 `null`（**不**为了字段非空而塞空对象）。

### 4.7.3 本批次**不**做的事（防自我欺骗）

- 不调阈值、不加权重、不做「相似度打分」——命中即产出，判定全靠结构；
- 不做 §3 验收 6 的场景准入（200 合同 / 500 发票 / 100 凭证 / 20 组植入 ⇒ 召回 ≥ 0.80、
  误报 ≤ 0.15）：语料规模**远不足**，该判据**维持未做**（登记 S13）；
- `missing_check_in`（考勤域）不在本批次范围，常量保留不动。

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

---

## 6. 已登记的实现缺口（S7 收尾登记，2026-09-24）

> 本节按 `docs/dev-doc-status.md` §9.2 第 6 项维护：**实现态与规格的差距必须落在规格侧**，避免只活在 `backend/CODEBUDDY.md` 里。逐条对账见 `docs/acceptance-traceability-matrix.md` §3.3。

| # | 缺口 | 现状 | 承接 |
|---|---|---|---|
| **S7.2-1**（✅ 已偿还） | `unaligned_subjects`（§4.5）**只建表不写** | **S9.11 批次 C1 已偿还**：四源 schema 冻结（§4.6）+ 确定性摄入器 + 三级对齐器就位，未对齐主体真机落表并带 `reason`（对齐率判据见 `changes/archive/2026-09-29-Sprint9.11/integration-log.md`） | — |
| **算法三类 + 金额比对**（✅ 已偿还） | `shared_phone` / `cycle` / `amount_mismatch` **未实现**（无输入数据） | **S9.12 批次 C2 已偿还**：语料增补（§4.6.6）+ 摄入器落 `:Phone` / `:LegalPerson` / `:Address` / `:Contract` 与 `SHARES_HOLDER` / `PARTY_TO`，判据先冻结（§4.7）后写算法；**真机产出 9 条**（`shared_legal_rep` 1 / `shared_address` 1 / `shared_phone` 1 / `cycle` 3 / `amount_mismatch` 3），与植入的 9 组**一一对应、误报 0**；`amount_mismatch` 落 `severity=high` + `details` 三方金额明细 | — |
| **S9.12-1** | 语料是**合成 CSV**（`contracts.csv` 是 PDF 合同的替身，见 §4.6.6 偏离登记） | 真机合同仍须走 M2 抽取链路；替身与抽取产物的汇合点 = `:Contract` 节点属性（形状一致） | **M2 接入合同后回归** |
| **S9.11-1** | `unaligned_subjects` **无读端点** | 本批次裁决 **D-B**：只写不读，不新增端点、不动契约（§5.5 四端点未含它，新增 = 范围变更）；对齐率由**测试断言**给出，不靠 UI | 待定（C4 或 M6 校正 GUI 一并做） |
| **S7.2-2** | `TaskManager.list_in_flight_task_ids()` **只扫 `documents`** | `recover_orphan_tasks()` 已扩到扫 `affiliation_tasks`（ADR-0001 硬要求，**不受影响**），但该函数仍只查 `documents`，对账 `affiliation_tasks` 时查不到在途任务 | **S8**（与跨阶段投递 S7.1-5 一并收） |
| **S7.1-7**（已关闭） | M4「两层并存」（`:Entity` + `:Subject`） | ✅ **已偿还**：作为**已知限制**写入 `docs/release-notes/v1.3.0.md` §6.9（决策 D1：不建桥接边，仅以 `source_entity_ids` 维系联系）；统一工作仍归 **S9 批次 D 实体消解**（plan 第 582 行） | S9（统一） |
| **证据粒度** | `evidence.text` 为**整段 chunk**，非实体提及片段 | 真机 10/10 条 `ev_len == chunk_len`；前端改**淡底 + 标注**，**未伪造**片段级高亮；提及级定位（`char_offset` 恒 0）见 release notes §6.1 / §6.2 | **S10** |
| **数据质量** | chunk 原文含未清洗的 `<table>` / `<tr>` / `<td>` 标记 | 属解析层（批次 A / S6 链路），前端按原文原样展示、未做「美化」 | **S10** |
| **口径变更（已登记）** | `affiliation_suspicions` 增 `task_id` 列 | 决策 B2，已在 **§4.3** 登记变更（回答「GET 返回哪一批疑点」靠列、不靠 `created_at` 猜） | — |
| **口径消歧（已登记）** | 端点路径为 `suspicions` 而非 `suspects` | plan §6.2 原写 `suspects`，**以本 spec §5.5 为准**；plan 已同步（`plan.md:275` / `plan.md:289`） | — |