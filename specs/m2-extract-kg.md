# M2 · 实体关系抽取与知识图谱构建 — MVP 规格说明书

> **文档编号**：spec-m2
> **版本**：v1.0
> **状态**：MVP 规格（**2026-09-27 追加**：§3 **验收 8 / 9 / 10**（知识时效，双时态四字段 + 确定性仲裁）与 §4.6 时态字段，依据 **[ADR-0005](../docs/adr/ADR-0005-temporal-knowledge-model.md)**，承接 **S9（L0 批次 A / L1 schema 冻结首日）**；编号按矩阵 §7 第 1 条**只追加不重排**；v1.0.0 已交付；**v1.2.0 / Sprint 6 落地 `:Chunk` 证据节点**（原文片段 + `page` / `char_start` / `char_end` + `acl_scope`；`acl_scope` **只落属性、查询不做穿透过滤** → S11）；**2026-09-24 补做 S6 侧验收对账**——逐条见 `docs/acceptance-traceability-matrix.md` §3.4，**并更正「`confidence` 不落库」这一过期口径（实测已落库）**；实现态与缺口见 `backend/CODEBUDDY.md` §4 与本文件 §6）
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
3. **WHEN** 抽取结果包含 2 个以上名称相似但不同的实体（如"ABC 公司"与"ABC股份有限公司"），**THEN** 实体消解器返回合并候选（含相似度评分），**AND** 评分 ≥ 0.90 的候选**自动合并**（写 Neo4j + 落 `entity_merge_candidates.status=auto_merged`），**AND** 0.70–0.90 的候选**进入人工校正队列**（`status=human_review`，由 M6 处理），**AND** < 0.70 的候选**保持独立**。（**注**：M6 的 `POST /api/v1/ontology/merge` 会把 `human_review` 的候选置为 `applied`——该处置动作已于 **2026-10-08 P5-G 批次**落地，见 §4.5 注脚；**本验收只管 M2 产出候选，不覆盖这个处置动作**。）
4. **WHEN** 任一抽取结果写入 Neo4j，**THEN** 该次写入生成一个版本号 `kg_version`（ISO 时间戳 + ULID 后缀），**AND** 写入顺序**严格**为「**先 PG 后 Neo4j**」（**ADR-0002**）：① `kg_versions` **插入** `status = writing` → ② 写入 Neo4j（**必须 `MERGE`**，以 `(id, kg_version)` 为幂等键，保证重放安全）→ ③ 成功置 `active` / 失败置 `failed` 并记 `error_code` / `error_detail`，**AND** 不删除或覆盖历史版本（历史版本仅 `superseded` 标记，不删），**AND** PostgreSQL `kg_versions` 表记录 `{version, org_id, doc_id, status, error_code?, error_detail?, reconciled_at?, trace_id, created_at, updated_at}`。
5. **WHEN** 抽取过程中 LangExtract 抛错或超时，**THEN** tenacity 指数退避重试 ≤ 3 次（初始 1s、倍数 2），**AND** 最终失败触发 M5 审计 `extract.fail` 事件，**AND** `documents.status` 置为 `failed` 且 `error_code` 落库。
6. **WHEN** 抽取完成且 `kg_version` 落库，**THEN** M2 投递索引更新事件（`kg_version` 标识），**AND** M3 / M4 可立即消费该版本。
7. **WHEN** 任意接口被调用，**THEN** 日志携带 `trace_id`，**AND** token 用量与耗时字段打点（用于成本仪表盘，对应准入线 C3）。
8. **WHEN** 文档进入抽取，**THEN** `Document.document_date`（披露文件签署日 / 报告期日）被解析并落库（**取不到则留 `NULL`，禁止猜测**），**AND** 该日期作为本批次抽取的**默认事实日期**传入抽取链路（**ADR-0005 §4**）。
9. **WHEN** 抽取产出一条关系，**THEN** 该关系携带 `valid_from` / `valid_to` / `created_at` / `expired_at` / `source_document_id` 五属性（**ADR-0005 §4**），**AND** `valid_from` 在文本无显式日期时**取 `document_date`**、文本显式写了期间时取文本值，**AND** `valid_to` 仅在文本显式写了失效 / 期间终点时才有值（**否则 `NULL`，禁止推断区间**，规则 R4），**AND** `valid_from` 覆盖率 ≥ **0.90**（`temporal_poc` 实测基线 = **1.00**）。
10. **WHEN** 写入 Neo4j 时同一 `(head, relation_type)` 出现 `valid_from` **更晚**的新事实，**THEN** 旧边的 `valid_to` 被置为新事实的 `valid_from`、`expired_at` 置为写入时刻（规则 R1），**AND** 旧边**不被物理删除**（as-of 查询仍可查到），**AND** 「当前有效」查询（`valid_to IS NULL`）**返回且仅返回一条**该 `(head, relation_type)` 的边，**AND** 同一批次（同一文档）内写入的边**互不失效**（规则 R3），**AND** 同一 `valid_from` 的多条边按规则 R2 保留原文中最晚出现的 `tail`。

> **关联 MVP 准入线**：A3（解析质量实测）/ A4（抽取 precision ≥ 0.85）；C1（增益 ≥ 10%）/ C2（召回 ≥ 0.80）/ C3（成本可控）。
>
> **验收 8–10 的时效判据与重跑方式**（可复现）：`temporal_poc/corpus.py` 两期语料 →
> `temporal_poc/run_track_s.py`（n ≥ 3，**要求 3/3**：当前值正确 + as-of 回溯正确 + 历史保留）。
> 该脚本是**验收 9 / 10 的机械判据原型**，落地时迁入 `backend/tests/`。
> 判分口径注意**去空格归一**（模型对「陆家嘴环路 500 号」是否带空格不稳定，不去空格会把"答对"误判为"答错"）。

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
| `status` | TEXT | 是 | `pending / auto_merged / human_review / rejected`（**M6 已启用第 5 个值 `applied`，见本表下方注脚**） |
| `created_at` | TIMESTAMP | 是 | - |
| `trace_id` | UUID | 是 | - |

> **注脚：`applied` = M6 已启用（2026-10-08 升版，P5-G 批次）**
>
> `status` 第 5 个值 `applied`，由 **M6 校正动作** `POST /api/v1/ontology/merge` 在合并
> **真的生效**后写入：`human_review` → `applied`。写入方 =
> `backend/app/services/kg/correction.py::merge_entities`（P5-G，2026-10-08 落地）。
>
> **M2 实现阶段（含 Sprint 9）不落该值**——`similarity ∈ [0.70, 0.90]` 的候选仍**只进**
> `human_review`（**§3 验收 3 口径不变**）：M2 只负责**产出**候选，处置归 M6。
>
> ⚠️ **原「M6 落地前须先升版本表并走契约同步 5 步」的处置（2026-10-08 实读后修正）**：
> 那 5 步里的 ②「改 Pydantic `EntityMergeStatus` 枚举」**无对象**——该枚举在本仓
> **不存在**，且 `entity_merge_candidates` **只写不读、不进契约**（`models.py` 的既有
> 裁决口径：不为"走出 diff"而造端点）；③④⑤ 三步在契约先行批次**已做**（三条校正
> 路径与 `status: const: applied` 均已在 `contracts/openapi.yaml` 内）。
> ⇒ 实际要落的只有 ①「升版本表」（= 本注脚这次升版）与「真写 `status='applied'`」
> 这个代码动作，二者已在 **P5-G 同批**完成。详见 `changes/P5-G/integration-log.md` §2.2。
>
> **本注脚只声明第 5 个取值的来源，不改变 M2 自身的实现范围与验收口径。**

> **列类型偏离（S9.13-1，Sprint 9.13 实测登记）**：`left_entity_id` / `right_entity_id`
> 落库为 **TEXT**，不是本表起草时写的 `UUID`。**理由（实测，非偏好）**：图谱侧实体 id 是
> **稳定字符串**（主体层 `SUBJECT:<税号>`，通用层 `ent_<uuid>`），**没有任何 UUID 可存**；
> 硬按 UUID 建列 ⇒ 要么写不进去，要么另造一套"字符串→UUID"的假映射（比偏离更糟）。
> 判定：`entity_merge_candidates` 的左右两边必须能**直接回查图节点**，故列类型与图 id 对齐。

### 4.5.1 主体层实体消解判据（**Sprint 9.13 冻结**）

> 出处：§3 验收 3 + §4.5 表。**纪律（plan §20 R14 + `c0-recon` D-3）**：判据先冻结，
> 冻结后才写算法；**判据里没写的信号，不许进代码**。

**1. 范围**：候选对只在 **`:Subject` 主体层**生成。理由（实测，不是偏好）：主体 id =
`SUBJECT:<税号>`，**跨文档稳定**；`:Entity` 通用层 id = `ent_<uuid>`（每次抽取都变）
⇒ 同一公司就是两个节点，无从配对（同一事实亦登记于 `specs/m4` §6 的降级段）。
⇒ **通用层消解本批不做**，登记 **S9.13-2**。

**2. 候选来源（blocking，不做全 O(n²) 比较）**：

- **B1** canonical 主体 × canonical 主体：规范化名（`normalize_name`，口径见 `specs/m4`
  §4.6.5）非空且**首 2 字相同**；
- **B2** 未对齐主体 × canonical 主体：`unaligned_subjects.raw_name` 与候选主体同上判据；
- 其余配对**不生成**（不把全部主体两两比较，噪声对没有审计价值）。

**3. 信号（全确定性、零 LLM —— 判分不得依赖模型）**：

- **S1 名称相似度**：`name_sim = max(jaccard₂(norm_a, norm_b), SequenceMatcher.ratio(norm_a, norm_b))`
  （字符 2-gram Jaccard 与 `difflib` 比率取**较大值**）。
  取 `max` 的理由：jaccard 对**长度差**敏感、ratio 对**子串插入**敏感，任一"强证据"成立即算
  相似；**不引入可调权重**（与 `specs/m4` §4.7.1 第 4 条「无阈值可调」同精神——调参即给
  "凑够 N 条"留后门）。
- **S2 结构加分**：共享法人 / 共享电话 / 共享地址，每项 **+0.05**，**合计上限 +0.10**；
  **单独出现（`name_sim < 0.70`）不产生候选**——结构相同是「**关联方**」的证据，
  不是「**同一主体**」的证据（把同一法人名下两家公司合并，等于抹掉 M4 要找的隐性关联）。
- `similarity = min(1.0, name_sim + struct_bonus)`，再经下述否决。

**4. 三条否决 / 降级（审计正确性优先于召回）**：

- **N1 税号冲突**：双方都有**合法且不同**的税号 ⇒ `similarity = min(similarity, 0.85)`
  ⇒ **永不 auto_merged**。理由：不同统一社会信用代码 = 法律上不同主体。
  与 §3 验收 3 举例（「ABC 公司」/「ABC 股份有限公司」）**不冲突**——举例是**无 id** 的
  抽取实体场景。
- **N2 多候选**：同一 raw 主体有 **> 1** 个 ≥ 0.90 的候选 ⇒ **全部降为 `human_review`、
  不合并**（并错两家比漏并一家危险，沿用 S9.11 裁决 D-B）。
- **N3 税号相同** ⇒ 本就是同一节点，**不产生候选**。

**5. 三档处置**：

| `similarity` | `status` | 图侧动作 | 表 |
|---|---|---|---|
| ≥ 0.90 | `auto_merged` | 摄入流水线内**归一到 canonical 节点**（边指向 canonical），**不是**事后改写图 | 落 1 行 |
| 0.70–0.90 | `human_review` | **不动图** | 落 1 行 |
| < 0.70 | —（保持独立） | 不动 | **不落行** |

- `pending` / `rejected` 本阶段**无写入方**（显式登记，不假装已有）；
  `applied` 仍是 M6 前向预留（§4.5 注脚 + S9.11 裁决 **D-C**：Pydantic 枚举加值、
  **运行时不写该值**、契约侧零改动）。
- `human_review` **无读端点**（S9.11 裁决 D-B 同口径：不为没有 UI 的队列造参数）
  ⇒ 缺口 **S9.13-2**。

**6. 真机判据（可核，合成语料 90 行待对齐）**：

- 消解前：未对齐 **4**（对齐率 86/90 = 0.9556，**S9.11 的判据不被推翻**）；
- 消解后：**`auto_merged` 1 条**并入 canonical ⇒ **终态对齐率 = 87/90 = 0.9667**（≥ 0.95）；
- **N1 的反例必须可见**：故意留一条「名称极像但有合法税号、且与主数据不同」的源行
  （`vouchers.csv[PZ2026-0008]`，`name_sim ≈ 0.89`）⇒ 只能落 `human_review`，**不得**
  被自动合并——判据若把它并了，说明 N1 没生效；
- 候选表行数与三档分布**逐条可核**；**误并 0**——不得出现把「税号不同的两个主体」
  并入同一节点。

**7. 本批次不做**：`applied` / `pending` / `rejected` 写入、`:Entity` 通用层消解、
**已入图历史节点的事后物理合并**（本批的"合并"发生在**摄入时**，重跑才生效）、
任何阈值或权重调参。

### 4.6 时态字段（**ADR-0005**，S9 承接）

> 依据 **[ADR-0005 知识图谱时效模型](../docs/adr/ADR-0005-temporal-knowledge-model.md)**。
> 路线 = **自研双时态 + 确定性仲裁**（双轨 PoC 实测：自研过期治理 **3/3** vs Graphiti **0/3**，见 ADR §3）。
> 本小节只定义**字段与规则**，实现的分期见 `docs/optimization-plan-2026-09.md` §3 P3。

#### 4.6.1 四字段双时态（落在**关系**上）

| 字段 | 维度 | 类型 | 空值语义 |
|---|---|---|---|
| `valid_from` | 事实维 | DATE | 不可空；无显式日期取 `document_date`（R4） |
| `valid_to` | 事实维 | DATE | **`NULL` = 仍有效** |
| `created_at` | 摄入维 | TIMESTAMP | 不可空（本条边写入时刻） |
| `expired_at` | 摄入维 | TIMESTAMP | `NULL` = 仍是当前边 |
| `source_document_id` | 血缘 | UUID | 不可空（事实来源文档） |

**两套维度必须分开**：事实维 = 现实中成立区间（来自文档）；摄入维 = 系统何时知道 / 被推翻。
**与 `kg_version` 正交**：`kg_version` 是图谱**快照**批次，四字段是**单条事实**成立区间，**不得互相替代**。

#### 4.6.2 仲裁规则（确定性，不依赖 LLM / Embedding）

| # | 规则 | 动作 |
|---|---|---|
| **R1** | 跨文档：新事实 `valid_from` **严格晚于**旧边 | 旧边 `valid_to := 新边.valid_from`；`expired_at := 写入时刻` |
| **R2** | 同文档变更句：同 `(head, relation_type)` 且 `valid_from` 相同 | 保留 `tail` 在原文中**最晚出现**者；其余 `valid_to := valid_from` |
| **R3** | 禁止同批次互封 | 失效动作不作用于同批次（同一文档）内刚写入的边 |
| **R4** | 不猜值 | 无显式日期 ⇒ `valid_from := document_date`、`valid_to := NULL` |
| **R4-b** | 文档级作用域继承（Sprint 10.5 增补） | 条款自身无候选窗口 ⇒ 继承所属文档自称条款**逐字声明**的 `(施行日, 有效期至)`；没写 ⇒ `NULL`；跨文档窗口不同 ⇒ 留空（见下方 4.6.4） |

> ⚠️ **R3 是实测踩出来的**（`temporal_poc/README.md` §4 坑 5）：首版用 `<=` 且不排除同批次，
> 「由张三变更为李四」先写出的新值边会被后写出的旧值边**反过来封掉**，当前值全线阵亡。
> **照抄时不要"顺手优化"掉 R3。**

#### 4.6.4 文档级作用域继承（R4-b 的实现边界）

> 出处：[ADR-0005 §5 R4-b](../docs/adr/ADR-0005-temporal-knowledge-model.md)，
> 实测记录 [`changes/P6-U/12-document-scope-inheritance.md`](../../changes/P6-U/12-document-scope-inheritance.md)。
> 11 号记录定的是「桥接边继承**条款自身**窗口」；本节定的是「条款**自身没有**窗口时怎么办」。

- **适用对象**：仅作用域继承的落点是**确定性派生的桥接边**（`:RELATION` 上的
  `valid_from` / `valid_to`），不是 `:Entity` 属性——实体属性不加时态字段。
- **取值源**：称为文档的**自称条款**行必须含 `本规定` / `本制度` / `本办法` /
  `本细则` 之一，窗口用**确定性正则**读出（施行日复用
  `app.services.parsing.document_date.resolve_document_date`；失效日取其同构
  解析器）。**不经 LLM。**
- **歧义处理**：同一条款实体被多个窗口不同的文档产生 ⇒ 剔除，不继承（与 11 号
  「恰好 1 个候选才继承」同纪律）。
- **禁止项**：按文件名 / 路径 / 标题年份推定；把施行日当成失效日；覆盖条款自身
  已有的更细窗口。
- **边界一致性**：本规则与 11 号共用同一份口径模块
  （`backend/scripts/_bridge_window.py`），**不允许任何一处另写一份过滤语句**。

#### 4.6.5 as-of 视图的证据位次（R5 的实现边界）

> 出处：[ADR-0005 §5 R5](../docs/adr/ADR-0005-temporal-knowledge-model.md)，
> 诊断记录
> [`changes/P6-U/probe_as_of_ranking.py`](../../changes/P6-U/probe_as_of_ranking.py)。

- **触发条件**：仅 `as_of` 非 `None`。缺省视图该位次恒为 `0` ⇒ **缺省零变化**。
- **判定对象**：候选链**最后一跳**的 `valid_from` / `valid_to`；日期缺失 ⇒ `1`
  （不可判定），但仍然留在候选里。
- **插入位置**：sort key 中**紧跟 `_TEMPORAL_RANK`、位于 `tuple(ids)` 之前**⇒
  只为打平的候选裁决，不会为了时点证据牺牲更短或更有解释力的链。
- **与 R4 的关系**：R4 管的是"不许编日期"，本规则管的是"多条链打平时谁出场"；
  让位是**排序**，不动数据、也不删除候选。
- **为什么不能省**：12 条候选在四个语义维度上全平 ⇒ 没有这一位，输出由节点 id
  字典序决定。这属于口径空缺，不是优化。

#### 4.6.3 有效期策略表（`relation_type → 策略`，L1 交付）

| 策略 | 含义 | 适用（初稿，随 M6 本体收敛） |
|---|---|---|
| `volatile` | 易变，新事实到达即封旧边 | `LEGAL_REP`、`REGISTERED_AT`、`AFFILIATED_WITH`、`OPERATES_SEGMENT` |
| `stable` | 稳定，同值重复出现不另建边 | `PARTY_TO`、`HAS_FINANCIAL_INDICATOR`（带报告期，按 `valid_from` 区分年度） |

> **配置纪律**：该表落 `backend/app/core/config.py`（可经 `.env` 覆盖），
> **必须有消费点**——无消费者的配置不得提交（CODEBUDDY「功能预留原则」第 6 条）。

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
> **契约已定稿并落库于 `contracts/openapi.yaml`**。Sprint 1 已定稿的 5 个接口见 [`contracts/openapi.yaml`](../../contracts/openapi.yaml) 与 [`docs/multimodal_rag_backend_api_spec-v1.0.md`](../../docs/multimodal_rag_backend_api_spec-v1.0.md)；其中 `/api/v1/documents/{id}/graph` 已随 **v1.0.0（Sprint 4）** 实装（读 Neo4j 子图，仅消费 `status = active` 的版本），实现态与残留缺口见 `backend/CODEBUDDY.md` §1.1 / §4。

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

---

## 6. 已登记的实现缺口（**S6 收尾补做，2026-09-24**）

> 本节按 `docs/dev-doc-status.md` §9.2 第 6 项维护：**实现态与规格的差距必须落在规格侧**，避免只活在 `backend/CODEBUDDY.md` 里。S6 收尾当时未执行 §9.2 第 3 项的逐条对账，本节为**历史补做**（核实日期统一为 2026-09-24）。逐条对账见 `docs/acceptance-traceability-matrix.md` §3.4。

| # | 缺口 | 现状 | 承接 |
|---|---|---|---|
| **S6.1-1** | §3 验收 1 的**解析时延 P95 ≤ 30s / 100 页**与**表格还原率 ≥ 0.85** 未测量 | S6 只有**单次**真机成功（`content_list` v1 结构 10/10 对齐、v2 结构判出 `page=1`），**无 50 份样本评测** | **未排期**（属 A3 解析质量实测，建议随 S10 解析层一并做） |
| **S6.1-2** | 社区版无 `IS NODE KEY`，幂等键降级为 `IS UNIQUE` | 唯一性（幂等前提）**保留**，属**有依据的降级**（`IS NODE KEY` 需企业版），已在代码注释写明 | 无版本变更则保持 |
| **S6.1-3** | **在线链路不自串联**：上传后 extract / kg.build 不自动触发 | S6.1 §4.3 已上报；2026-09-24 补做时**未验证是否已闭合**（不假设已修） | 待核实 |
| **S6.2-1** | `Citation.char_offset` **恒为 0**（§3 验收 2 要求的提及级定位） | 2026-09-24 复核仍为 0；实体 `char_start` / `char_end` **有值**但未进 citation。**2026-09-30（S10 批次 A）上游已偿还**：span **入图**（`:Entity.char_start` / `char_end`）+ `char_offset` **由代码确定性换算**（`entity.char_start − chunk.char_start`，禁止 LLM 产出）；引用分**双档**（span 主档 / chunk 回退档 + 告警）。⚠️ **端到端 `char_offset` 非 0 仍待真机补验**（需 PG + LLM，`kg_qa_v4` 是否让模型遵循新证据格式）⇒ 未证前不得宣称"引用已精确到句" | **S11**（与 PG 切换一并补验） |
| **S6.2-2** | **实体消解未做**：同一实体重复 3 份、整句被抽成实体名（6 → 18 节点） | ✅ **2026-09-29（S9.13 批次 C3）已偿还**：`entity_merge_candidates` 建表 + 迁移 `b3e5a1c70d42`，消解器 `app/services/kg/entity_resolution.py`（纯函数、零 LLM），判据冻结在 §4.5.1；真机候选 **5 条**（`auto_merged` 1 / `human_review` 4）、终态对齐率 **87/90**。**未闭口部分显式登记为 S9.13-2**（见下） | 保持（**S9.13-2**：人工队列无读端点 + `:Entity` 通用层消解未做） |
| **S6.2-3** | §3 验收 6 的**建图后索引更新事件未投递** | `services/kg/` 下**零 publish**；当前靠调用方**显式调激活端点**衔接（非事件驱动） | **未排期**（接缝 5 出口已于 S7.4 就位） |
| **S6.4-1** | §3 验收 7 的 **C3 成本聚合未建** | token 用量已在响应返回（真机 `total 1799`），无聚合表 | **S13** |
| **S9.13-1** | `entity_merge_candidates.left/right_entity_id` 为 **TEXT**，与 §4.5 起草时的 `UUID` 不一致 | 2026-09-29 登记：图谱侧实体 id 是**稳定字符串**（主体层 `SUBJECT:<税号>`），**没有 UUID 可存**；硬按 UUID 建列 ⇒ 写不进去或另造"字符串→UUID"假映射 | 无（**有依据的偏离**，理由写在 §4.5 表下） |
| **S9.13-2** | ① `human_review` 人工队列**无读端点**；② `:Entity` **通用层消解未做** | 2026-09-29 登记：① 沿用 S9.11 裁决 D-B（无 UI 的队列不造参数）；② 通用层 id = `ent_<uuid>` **每次抽取都变**，同一公司就是两个节点 ⇒ 无从配对，需先解决跨文档 id 稳定性 | **S12（M6 校正 GUI）** / 通用层未排期 |

> **口径更正（2026-09-24）**：本文件状态行、矩阵 §3.1、`plan.md` §15.3 三处长期写着「M2 **`confidence` 不落库**」——**经代码核实为错误**：`kg/builder.py:322-330 / 342` 已把 `confidence` 写入 Neo4j 的**节点与关系**属性，且带完整取值纪律（`< 0.5` 丢弃、超限降序裁剪、缺值不猜）。三处均已更正，**理由记录于此以防被旧口径改回**。