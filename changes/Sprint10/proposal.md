# Sprint 10 批次 A：证据三元组落地（`char_offset` 从占位到精确）

> **分支**：`feature/sprint-10` | **Sprint**：S10（v1.6.0，证据链与多跳）
> **日期**：2026-09-29
> **前置勘察**：[`c0-recon.md`](./c0-recon.md)（只读结论，开工前必读）
> **依据**：`docs/v1.1.0-demo-mvp-plan.md` §17.1 批次 B / C；`specs/m3-*.md` §3 验收 2（引用覆盖率）；M2 §3 验收 1

---

## 1. 为什么做

| 驱动 | 说明 |
|---|---|
| **G3 准入线** | 上线 Gate 要求「引用覆盖率 = 100%」与「多跳答对率 ≥0.80」（倒推计划 §1），两者的载体都是**可溯源、可定位**的引用 |
| **F3 / 诚实性** | `_to_citation` 已是真实回查，但 `char_offset=0` 让"高亮到 `char_offset`"这一条验收**字面过了、实际没到** |
| **S9 遗留偿还** | M2 §3 验收 1 与 `char_offset` 恒 0（登记在 `sprint-calendar` §5 S9 行） |
| **S13 的前置** | S13 的 C2 实验要统计"引用覆盖率"，粒度定不下来则口径无法复现 |

**不做会怎样**：S10 的 B（多跳）与 C（召回）做出来的答案，仍然只能"指到哪一段"，演示时点击引用高亮整段——客户一眼看出是"整段糊上去"，且 S13 无口径可用。

---

## 2. 首日冻结的裁决（**先冻结后写代码**，S9 纪律）

| # | 裁决 | 判据 |
|---|---|---|
| **D-A** | `Citation.char_offset` 语义 = **片段内相对偏移**（相对 `DocumentChunkResponse.text` 起点）；**新增 `char_end`** 字段形成区间。`0` 的语义保留为"整段引用" | `DocumentChunkResponse.text` 是片段、`char_start/char_end` 是全文偏移，两者**不同源**，不写死必然漂 |
| **D-B** | `char_offset` **一律由代码确定性换算**（`entity.char_start − chunk.char_start`），**禁止 LLM 产出** | `langextract.py:28-30` 实测模型自报偏移 **14/20 不符**；且"数值不出 LLM"是既有纪律 |
| **D-C** | 引用粒度 **双档**：主档 **span 级**（Prompt `kg_qa_v4` 让 LLM 在 evidence 条里带**实体提及文本**——是文本不是数字，代码据此回查 span）；**回退档** chunk 级（`char_offset=0`，高亮整段）。**匹配不到就回退，不猜、不编** | 既要精度，又不让模型出数字；回退档保证覆盖率不因精度改造而下降 |
| **D-D** | span 落库 = `:Entity.char_start` / `:Entity.char_end`（补上"抽取有、入图丢"这一环）。**CSV 派生实体天然无 span ⇒ 写 null，不造** | 真机：Entity 无任何 span 属性（c0 §1 事实 5）；造 span = 假数据 |
| **D-E** | `confidence` **不补齐数字**。真机覆盖率 **4.7%**（139/2948）的分层口径：LLM 抽取实体有值、CSV 派生为 null；登记口径进 `dev-doc-status.md`，**不为了好看给确定性数据编置信度** | 零假数据铁律（plan §7.2 / A16） |

---

## 3. 契约影响（**契约先行**，`CODEBUDDY.md` §契约同步铁律 5 步）

| 模型 | 变更 | 是否进契约 |
|---|---|---|
| `Citation`（`schemas/agent.py:79-84`） | 新增 `char_end: int`（与 `char_offset` 成区间）；描述改写为"片段内相对偏移" | **是**（枚举/字段进契约即对外承诺） |
| `DocumentChunkResponse` | 不变（已含 `char_start` / `char_end` / `text`） | — |

流程：改 Pydantic → `uv run python scripts/export_openapi.py` → 提交生成物 → `npm run gen:api` → CI 零漂移校验。

---

## 4. 不做（明确边界）

- **不改引用覆盖率判据**（仍是 chunk 级 100%；span 是精度增强，不是覆盖率口径的重新定义）；
- **不重做 `:Chunk` 落库**（已完成，c0 §2 偏差 1）；
- **不给 CSV 派生实体造 `confidence` / span**（D-D / D-E）；
- **不动 `kg_qa_v3`**：新增 `kg_qa_v4`（Prompt 版本只增不覆盖，`CODEBUDDY.md` Prompt 版本管理规范）；
- **不做多跳**（批次 B）/ **不改召回策略**（批次 C）/ **不做 docx**（批次 D）。

---

## 5. 验收（批次 A 收尾逐条勾）

- [ ] `Citation.char_end` 进契约，`npm run gen:api` 后 `api.d.ts` 与契约零漂移；
- [ ] `:Entity` 真机出现 `char_start` / `char_end`（LLM 抽取实体有值，CSV 派生为 null）且有单测钉死"抽取有 → 入图不丢"；
- [ ] 真机问答的 `citations[].char_offset` **不再是全 0 恒值**：span 命中时 = 实体在片段内的相对偏移，`0 < char_offset < char_end ≤ len(chunk.text)`；
- [ ] 回退档可复现：无 span 命中时 `char_offset=0` + 日志记录回退原因（不静默）；
- [ ] 前端点击引用 → 取 `GET /documents/{id}/chunks/{chunk_id}` → 按 `[char_offset, char_end)` 高亮（真机截图入 `integration-log.md`）；
- [ ] pytest 不降、`check_seams` ERROR 0、`export_openapi --check` 无 diff。
