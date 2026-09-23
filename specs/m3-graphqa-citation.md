# M3 · 图谱问答与可溯源引用 — MVP 规格说明书

> **文档编号**：spec-m3
> **版本**：v1.0
> **状态**：MVP 规格（v1.0.0 已交付；**v1.2.0 / Sprint 6 达成 chunk 级引用溯源**——`:Chunk` 证据 + 引用回查 + 前端原文高亮，受控问题集覆盖率 100%；**≥3 跳遍历待 S10**；实现态见 `backend/CODEBUDDY.md` §4）
> **上游依据**：`docs/02-product-outline.md` §3.2 M3
> **关联 Prompts**：`prompts/intent_router_v1.md`、`prompts/kg_qa_v1.md`、**`prompts/kg_qa_v2.md`（v1.2.0 / S6 新增：引用口径收窄为"只能取已注入的 `chunk-<id>`"，v1 保持不变）**
> **关联研究结论**：`01-research.md` §3.1.2 能力 1–2；§3.3 C2（引用覆盖率 = 100%）；§3.3 F3（直接 NO-GO 条件）
> **关联大纲**：`02-product-outline.md` §3.2 M3 + §6 准入线
> **关联 ADR**：[ADR-0002 Neo4j ↔ PostgreSQL 一致性边界](../docs/adr/ADR-0002-neo4j-postgres-consistency.md)、[ADR-0003 跨租户资源隔离粒度](../docs/adr/ADR-0003-tenant-isolation-rls.md)

---

## 1. 模块边界

### 1.1 In Scope（**5 个功能点**，严格沿用 outline §3.2）

1. **多跳 ≥ 3 跳查询**（沿关系链遍历）
2. **答案强制 100% 引用回溯**到原文 span `[source: 文件 + 页码 + 段落]`
3. **答案拒答兜底**（无法溯源则返回"无法回答"，**严禁 LLM 编造引用**）
4. **单文档 / 跨文档切换**（用户在 UI 显式选择检索范围）
5. **意图路由**（路由到通用问答 M3 或场景识别 M4）

### 1.2 Out of Scope（明确不做）

- **多模态答案生成**（图片 / 表格 / 图表的视觉生成）（不做）
- **答案的事实性校对**（**用户自校验**，系统仅保证溯源）
- **对话式多轮上下文记忆**（MVP 单轮问答，**多轮对话属 P2**）
- **用户反馈驱动的检索排序学习**（不做）
- **答案的多语言输出**（仅中文输出）

---

## 2. 核心用户故事

- 作为**审计 / 法务用户**，我希望每条答案都明确告诉我"它来自哪份文件的哪一页"，以便我能在合规复核时快速验证。
- 作为**业务用户**，我希望能问**3 层关系**的问题（如"A 公司的子公司的供应商是否同时是 B 公司的股东"），以便我发现跨主体的隐性关联。
- 作为**业务用户**，我希望系统在我问一个**无法溯源**的问题时**直接告诉我"无法回答"**，而不是编造看起来合理的答案（避免"幻觉"摧毁信任）。

---

## 3. 验收标准

> **格式**：**WHEN [操作] THEN [响应] AND [条件]**。

1. **WHEN** 用户提交一个多跳问题，**THEN** M3 通过 LangChain GraphCypherQAChain（或等价链路）在 Neo4j 上执行 **≥ 3 跳**遍历，**AND** 每跳关系携带 `kg_version` 过滤（**不跨版本混合**，**且该版本必须为 `status = active`**，**ADR-0002**），**AND** 查询返回的图节点数 ≤ 500（避免爆炸）。
2. **WHEN** 系统生成最终答案，**THEN** 每个事实句必须含 `[source: doc_id + page + chunk_id + char_offset]` 标记，**AND** 引用覆盖率 = 100%（**任一事实句无溯源即拒答**，对应反证条件 F3）。
3. **WHEN** 答案中任一事实句**无**可溯源证据，**THEN** 系统**拒答**并返回 `{answer: "无法回答", refused: true, refusal_reason: "no_grounded_evidence", trace_id}`，**AND** M5 写一条 `qa.refused` 审计，**AND** 严禁 LLM 自行编造引用。
4. **WHEN** 用户选择"单文档"模式（`scope=single_doc`），**THEN** Neo4j 查询加 `WHERE doc_id = :scope` 过滤，**AND** 跨文档检索被严格隔离，**AND** 响应字段 `citations` 仅含该文档的引用。
5. **WHEN** 意图路由器（`intent_router_v1.md`）判断问题属于场景识别类（如"关联交易"、"影响面"），**THEN** 路由到 M4 处理，**AND** 响应字段 `route = "m4_affiliation"`，**AND** 携带 M4 任务 `task_id`。
6. **WHEN** 系统生成答案，**THEN** 同时输出**置信度评级**（`high / medium / low`，基于图遍历结果数与 evidence 强度），**AND** `low` 置信度答案在 UI 标记"建议人工复核"。
7. **WHEN** 任意接口被调用，**THEN** 日志携带 `trace_id`，**AND** 记录"问题 → 答案 → 引用条数 → 拒答原因"的完整链路打点。

> **关联 MVP 准入线**：C2（引用覆盖率 = 100%）+ **F3（直接 NO-GO 条件）** + C1（图谱相对 RAG 增益 ≥ 10%）。

---

## 4. 数据模型概要

### 4.1 请求体（`POST /qa`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | TEXT | 是 | 用户问题 |
| `scope` | TEXT | 否 | `single_doc / cross_doc`，默认 `cross_doc` |
| `doc_id` | UUID | `scope=single_doc` 时必填 | 限定文档 |
| `kg_version` | TEXT | 否 | 指定图谱版本，默认最新 `active`；**若指定版本的 `status ≠ active`（`writing` / `failed` / `superseded`），必须显式拒绝（HTTP 409 + `KG_VERSION_NOT_ACTIVE`），严禁静默降级到最新版**（**ADR-0002**） |

### 4.2 响应体（`POST /qa`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `answer` | TEXT | 是 | 答案文本（含 `[source: ...]` 标记；拒答时为 `"无法回答"`） |
| `citations` | LIST | 是 | 引用列表，每条 = `{doc_id, page, chunk_id, char_offset, snippet}`；**Sprint 6 批次 B 起 `page` 可空**（页码由 MinerU `content_list` 文本对齐反推，失配为 `null`，**严禁兜底伪造 1**） |
| `route` | TEXT | 是 | `m3_graphqa / m4_affiliation` |
| `confidence` | TEXT | 是 | `high / medium / low` |
| `refused` | BOOL | 是 | 是否拒答 |
| `refusal_reason` | TEXT | `refused=true` 时必填 | `no_grounded_evidence / out_of_scope / low_confidence` |
| `trace_id` | UUID | 是 | 本次调用的 trace_id |
| `kg_version` | TEXT | 是 | 检索使用的图谱版本 |

### 4.3 PostgreSQL 表 `qa_logs`（新增）

| 字段 | 类型 | 必填 | 敏感 | 说明 |
|---|---|---|---|---|
| `id` | UUID | 是 | 否 | PK |
| `org_id` | UUID | 是 | 否 | 租户 ID（**ADR-0003**，RLS 隔离键，索引以 `org_id` 打头） |
| `question_hash` | TEXT | 是 | 否 | 问题哈希（**不记原文**） |
| `answer_hash` | TEXT | 是 | 否 | 答案哈希 |
| `citation_count` | INT | 是 | 否 | 引用条数 |
| `refused` | BOOL | 是 | 否 | 是否拒答 |
| `refusal_reason` | TEXT | 否 | 否 | 拒答原因 |
| `kg_version` | TEXT | 是 | 否 | 检索使用的图谱版本 |
| `trace_id` | UUID | 是 | 否 | trace_id |
| `created_at` | TIMESTAMP | 是 | 否 | - |

### 4.4 Neo4j

**仅消费**，**不新增节点**。查询模式详见 §5.4。

---

## 5. 模块间依赖关系

### 5.1 上游依赖

- **M2 实体关系抽取**：消费 Neo4j `:Entity` / `:AFFILIATED_WITH` 等节点与关系
- **M5 权限与审计**：调用 M5 校验"用户能否访问问题涉及的文档"；每次问答写 `audit_log`

### 5.2 下游被依赖

- **M4 关联交易识别**：当意图路由到 M4 时由 M4 处理（**M3 调用 M4 而非反过来**）
- **M5 权限与审计**：消费 M3 的 `qa_logs` 写入与拒答事件

### 5.3 与 M5 审计的耦合

- **禁止输出 `question` 原文** 至日志（**仅哈希**），避免敏感提问泄露
- 拒答事件必须留痕（用于发现"被拒答的问题集合"，指导本体补全与 KG 质量改进）

### 5.4 Cypher 查询模式（草案）

```cypher
// 3 跳关联：A 公司 → 子公司 → 供应商 → 股东 X
MATCH path = (a:Entity {canonical_name: $a})
      -[:AFFILIATED_WITH|SHARES_HOLDER*1..3]-
      (b:Entity)
WHERE a.kg_version = $kg_version AND b.kg_version = $kg_version
  AND ($scope = 'cross_doc' OR a.doc_id = $doc_id)
RETURN a, b, relationships(path), count(relationships(path)) AS hop_count
ORDER BY hop_count ASC
LIMIT 100
```

> **ADR-0002 强制**：`$kg_version` **必须**来自 `GET /internal/kg/active`（`status = 'active'`），**严禁**使用 `writing` / `failed` / `superseded` 版本；若请求显式指定了非 `active` 版本，**一律拒绝（HTTP 409 + `KG_VERSION_NOT_ACTIVE`）**，**不允许静默降级**到最新版。

### 5.5 API 端点草案

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| `POST` | `/qa` | `{question, scope?, doc_id?, kg_version?}` | 200 答案对象；400 / 401 / 403 / 500 |
| `GET` | `/qa/{id}` | - | 200 历史问答详情（仅本用户 / 同租户） |

> **契约草案**，实现阶段由后端开发 B 写入 `contracts/openapi.yaml`。

> **关键结论**：**M3 的"可溯源 + 拒答兜底"是产品差异化的最核心体现**。**这是相对普通 RAG 唯一结构性差异**（多跳）+ 唯一**可验证承诺**（引用覆盖率 100%）。**任何为追求"看起来能答"而放松溯源约束的优化都应被拒绝**——这是 F3 反证条件所防御的。