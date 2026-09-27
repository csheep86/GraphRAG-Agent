# Proposal: 知识时效改造（L0 文档日期与抽取时态字段 + L1 双时态四字段与确定性仲裁）

> **状态**：⏳ **待开工**（S9 首日启用；本文件为**事前计划**，事后证据写同目录 `integration-log.md`）
> **决策依据**：[`docs/adr/ADR-0005-temporal-knowledge-model.md`](../../docs/adr/ADR-0005-temporal-knowledge-model.md)（Accepted 2026-09-27）
> **排期**：S9（2026-11-11 → 2026-12-01），**首日 schema 冻结为硬闸门 `CP-T1`**（`docs/sprint-calendar.md` §4）
> **规格落点**：`specs/m2-extract-kg.md` §3 验收 **8 / 9 / 10** + §4.6
> **判据原型**：`temporal_poc/run_track_s.py`（**要求 n ≥ 3 达 3/3**）
>
> **不另建 `design.md` 的理由**：架构决策与多方案对比已由 **ADR-0005** 完整承载（§3 实测证据 / §4 数据模型 / §5 仲裁 / §7 被否方案与再审条件）。再写一份 `design.md` 会形成**第二真源**（`dev-doc-status.md` R7），故此处只回引。

---

## Why

图谱当前是**纯静态**的：三元组无时间属性，同一属性在不同日期的两份披露文件里
（如法定代表人 张三 → 李四）会**两条边静默共存**，问答无法区分"当前有效"与"已过期"。
`backend/` 全文搜索 `valid_from|valid_to|as_of_date|document_date` = **0 命中**。

该债项目自身早已登记（`docs/v1.1.0-demo-mvp-plan.md:399`、`docs/adr/0004-integration-seams.md:135`，
登记 v1.5+ 但未设计与实现）。

**为什么现在做**：S9 首日是 **schema 冻结日**。四源对齐做完再补时间字段 = 全链路返工。

**为什么是自研而不是引入 Graphiti**（详见 ADR-0005 §3，此处只摘结论）：
双轨 PoC 实测（同语料 / 同判分 / 重复 3 轮）——自研过期治理 **3/3**、当前值 **3/3**、
as-of 回溯 **3/3**、`valid_from` 覆盖率 **100%**、2 次 LLM 调用、**0 新增依赖**；
Graphiti **1/3**，换真实中文语义向量（`bge-small-zh-v1.5`）后 **0/3**。

---

## What Changes

1. **`Document` 加 `document_date`**（披露文件签署日 / 报告期日，可空，**取不到置 `NULL`，禁止猜测**）
2. **新增 `prompts/kg_extraction_v3.md`**：在 v2 基础上**只加** `valid_from` / `valid_to` 两个字段与对应 few-shot；
   **v2 文件不得修改**（单测 `test_v1_template_is_untouched` 同款纪律，守 H9）
3. **关系落四字段双时态 + 血缘**：`valid_from` / `valid_to` / `created_at` / `expired_at` / `source_document_id`
4. **实现仲裁 R1–R4**（确定性，不依赖 LLM / Embedding）：
   - R1 跨文档：新事实 `valid_from` **严格晚于**旧边 ⇒ 封旧边 `valid_to`，置 `expired_at`
   - R2 同文档变更句：同 `(head, relation_type)` 且 `valid_from` 相同 ⇒ 保留原文中**最晚出现**的 `tail`
   - R3 **禁止同批次互封**（实测踩出来的，不可"顺手优化"掉）
   - R4 不猜值：无显式日期 ⇒ `valid_from := document_date`、`valid_to := NULL`
5. **查询侧默认过滤**：概览 / 子图 / 问答三条链默认 `valid_to IS NULL`；补 as-of 查询
   （`valid_from <= $d AND (valid_to IS NULL OR valid_to > $d)`）
6. **`relation_type → 有效期策略` 配置表**（`volatile` / `stable`）落 `config.py`，**必须有消费点**
7. **判据脚本迁入** `backend/tests/`：`temporal_poc/` 的语料与判分迁入，**n ≥ 3 要求 3/3**

---

## Impact

**影响的契约（contracts/openapi.yaml）**

- ⚠️ **待开工首日核实（不臆断）**：`Document` 的响应 schema 是否已在契约内。
  - **若在** ⇒ 加 `document_date` 属契约变更，必须走**契约同步 5 步**（Pydantic → `export_openapi.py` 重导 → 提交生成物 → `npm run gen:api` → 零漂移校验）；
  - **若不在** ⇒ 按 CODEBUDDY「功能预留原则」第 4 条，**只落库不进契约**，门禁 `--check` 无 diff。
- 关系上的**四个时态字段落 Neo4j 属性**，**不进对外契约**（属图内部语义，不是 API 字段）。

**影响的前端（frontend/）**

- **本批次无变更**。页面「失效」视觉语义属 **L2（S10）**，不在本批次范围。

**影响的后端（backend/）**

- `db/models.py`：`Document` 加 `document_date`（nullable）
- `services/extraction/`：v3 prompt 渲染 + `valid_from` / `valid_to` 解析与归一（复用 `temporal_poc` 的 `_norm_date` 口径）
- `services/kg/`：四字段写入 + **R1–R4 仲裁**（唯一写入入口纪律不变：M2 是图谱层唯一写入入口）
- `services/graphs.py`：三条查询链默认过滤 + as-of 查询
- `core/config.py`：有效期策略表（**须有消费点**，无消费者的配置不得提交）
- `backend/tests/`：迁入判据脚本（n ≥ 3）

**影响的 Prompt（prompts/）**

- **新增** `prompts/kg_extraction_v3.md`（**不覆盖 v2**）；`EXTRACTION_PROMPT_VERSION` 切 v3，`.env` / `.env.example` 同步。

---

## Non-goals

- ❌ **不引入 Graphiti / graphiti-core**（ADR-0005 已否决，再审条件见其 §7.4）
- ❌ **不用 LLM 判定矛盾**（实测劣于确定性规则）
- ❌ **不做事件节点建模**（事实以关系上的区间表达，避免与 M4 疑点机制重复建模）
- ❌ **不做 TKG embedding / TransE-RotatE 类表示学习与 MRR 评测**（学术 KGC 路线，与"可溯源问答"不匹配）
- ❌ **不改 `kg_version` 语义**（与四字段**正交**：快照批次 vs 单条事实时效，不得互相替代）
- ❌ **不做页面视觉改造**（属 L2 / S10）
- ❌ **不重跑演示语料建图**（改抽取 schema 意味着重建图谱会改变演示数据；如需重建走独立 org，见 `docs/demo-seed-dataset.md` §4）

---

## 开工前必读（避免重复踩坑）

1. `temporal_poc/README.md` §4 **五个坑**（尤其坑 5：过度失效的根因与修法）
2. `docs/adr/ADR-0005` §5 **R1–R4** 与 §7.2 **接受的负面后果**
3. 判分**去空格归一**（模型对「陆家嘴环路 500 号」是否带空格不稳定）
4. PowerShell 内联 Cypher 会被 `$` 转义破坏 ⇒ **一律写成脚本文件跑**
