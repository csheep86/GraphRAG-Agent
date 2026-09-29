# c0 前置勘察：证据层与置信度的真机现状

> **分支**：`feature/sprint-10`（S10 / v1.6.0，证据链与多跳）
> **日期**：2026-09-29
> **性质**：**只读勘察**，不改任何数据。开工前必读——它直接改写 plan §17 批次 B / C 的范围。
> **探针**：`changes/Sprint10/probe_a0_evidence_state.py`（可复跑：`cd backend && uv run python ../changes/Sprint10/probe_a0_evidence_state.py`）

---

## 1. 真机事实（Neo4j，active kg_version）

| # | 事实 | 数字 | 出处 |
|---|---|---|---|
| 1 | `:Chunk` 落库 **355** 条，`char_start` / `char_end` **100% 非空且为 INTEGER** | 355 / 355 / 355 | 探针 §1、§2 |
| 2 | `:Chunk.page` 仅 **30** 条非空（CSV 派生 chunk 的 `page` 为 null，是 R14 的**刻意**设计） | 30 / 355 | 探针 §1 |
| 3 | `:Chunk.id` 形态合规（`chunk-<12hex>`，符合 R16） | `chunk-6d3a1d928e29` | 探针 §2 |
| 4 | `:Entity` **2948** 条，`confidence` 非空 **139** 条（**覆盖率 4.7%**） | 139 / 2948 | 探针 §3 |
| 5 | `:Entity` **没有**任何字符区间属性（`char_start` / `char_end` / `evidence_span` 全为 0 非空） | 属性键全集见下 | 探针 §4 |
| 6 | 证据边：`HAS_CHUNK` **355** / `MENTIONS` **482**；`:RELATION` 3645 条中 `confidence` 非空 **69** | 482 / 2948 实体 ≈ 16% | 探针 §5、§6 |

`Entity` 属性键全集（真机）：
`canonical_name / confidence / created_at / date / entity_type / gate / group_id / id / in_time / kg_version / labels / mention / name / name_embedding / org_id / out_time / summary / trace_id / uuid`

---

## 2. 与 plan §17 描述的**三处偏差**（必须据实修正，不能照抄计划干活）

| plan 原文 | 真机结论 | 对范围的影响 |
|---|---|---|
| 批次 B「建图时写 `:Chunk`（原文片段 + 文档内位置）」 | **已完成**（Sprint 6 批次 A-3，builder stage-2.5/4a/4b）：`char_start`/`char_end`/`page`/`text` 全部落库且类型为 int（builder 记过一次 string 事故，已修） | **不重做**。批次 B 剩下的只有「`_to_citation` 的 `char_offset=0` 占位」 |
| 批次 C「`confidence` 落 Neo4j（现状读出来是 `None`）」 | **写侧一直在写**（`builder.py:393` `n.confidence = e.confidence`）；真机覆盖率 **4.7%** ⇒ 真因是**抽取侧绝大多数实体没有置信度**（CSV 派生是确定性数据，天然无置信度概念），不是"落库没做" | **不能靠"补写"解决**，更不能给确定性数据造一个置信度（零假数据铁律）⇒ 改为「口径登记 + 分层」 |
| 批次 C「`evidence_span` 结构化（含 `char_offset`）」 | **确是真缺口**：抽取侧 `ExtractedEntity.char_start/char_end` **有值**，但入图时**被丢弃**（builder 写 Entity 的 Cypher 不含 span 字段） | 真缺口就一处：**把抽取已有的 span 带进图** |

---

## 3. 引用粒度的现状（决定 `char_offset` 能不能精确）

- Prompt `kg_qa_v3.md`：`evidence` 是 **`chunk_id` 级**（`[source: <chunk_id>]`，`evidence: ["chunk-581e8912827d"]`）⇒ LLM 只能指到"哪一段"，**指不到哪一句**；
- `_to_citation`（`agents.py:810-844`）已是**真实回查**（`doc_id` / `page` / `snippet` 都真，非骨架占位），唯一残留占位是 `agents.py:842` 的 `char_offset=0`；
- `DocumentChunkResponse.text` 是**片段原文**（非全文），而 `char_start`/`char_end` 是**文档全文**偏移 ⇒ 前端在片段内高亮必须用**片段内相对偏移**（= 全文偏移 − chunk.char_start），两者口径不同，必须在契约里写死。

**结论**：要让"点击引用 → 高亮到具体位置"，必须解决两件事——① span 进图（偏差 3）；② `char_offset` 由**代码确定性换算**，**绝不能让 LLM 产出数字**（`langextract.py:28-30` 实测：模型自报偏移 top20 中 **14/20 不符**，且违反"数值不出 LLM"纪律）。
