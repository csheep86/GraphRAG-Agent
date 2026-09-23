# Proposal: Sprint 6.4 —— 批次 C：引用溯源交互（原文抽屉 + 高亮）

**日期**：2026-09-23
**来源**：`docs/v1.1.0-demo-mvp-plan.md` §5.2 批次 C / §5.3 验收清单第 2、7 条；
`changes/Sprint6.2/tasks.md` §3 第 26 行留的批次 C 占位。
**前置**：Sprint 6.2 批次 B 已交付 `GET /api/v1/documents/{id}/chunks/{chunk_id}`（真机跑通）；
Sprint 6.3 已把三批工作固化为 3 个 commit。

---

## 1. 目标 / 非目标

**目标**

1. 点击引用标注（右侧「引用证据」面板 + 对话区展开的引用列表）→ 打开**原文抽屉**，
   展示该 `chunk_id` 的**真实原文全文**，并按引用位置**高亮**。
2. 满足 §5.3 **关 Mock 硬门槛**：qa 页溯源交互走真实链路，演示剧本第 4 步零假数据。
3. 加载 / 错误 / 跨租户等状态均有明确呈现，**不**用空内容或占位文本冒充原文。

**非目标**

- 不新建路由（不去动 `/documents` 页，抽屉收敛在 qa 页内）；
- 不做 PDF 原文渲染（本批次只渲染后端返回的 `text`）；
- 不做多片段连续阅读 / 上一处下一处导航（留给 v1.5）；
- 不改后端、不改契约（契约零漂移）。

## 2. 方案：qa 页内右侧抽屉

- 触发点两处：① `evidence-panel.tsx` 的「原文证据」条目；② `chat-message-item.tsx`
  展开后的引用条目。二者共用 store 里的同一份抽屉状态。
- 抽屉形态：新增 `components/ui/sheet.tsx`（Radix Dialog 的右侧滑出版），
  内容组件 `components/qa/chunk-viewer.tsx`，挂在 `app/qa/page.tsx`（不占三栏栅格）。
- 数据流：`openChunk(citation)` → `api/documents.getDocumentChunk()` →
  `DocumentChunkResponse`（`text` / `page` / `char_start` / `char_end`）。

### 2.1 高亮口径（真机修正，见 `integration-log.md` §3.3）

契约 `Citation` 注释：`char_offset` 是 **chunk 内**偏移（批次 B 恒为 0）；`snippet` 是
`chunk.text.strip()` 截断 200 字**再加省略号**的摘录（真机 `snippet.length=201`）。

因此**不能**直接按「`char_offset` 起点 + `snippet.length` 长度」切——strip 会造成位移、
省略号会多算 1 字（真机实测 `highlight_match=false`）。本批次采用：

1. 去掉尾部省略号 → 用 `indexOf` 在全文里定位摘录**实际位置**（命中即用）；
2. 找不到才回退契约口径 `char_offset`；
3. 都不成立 → **不高亮**，只展示全文（绝不伪造位置）。

### 2.2 本批次唯一的"必改"后端侧缺陷（前端侧）

`client.ts::CONTRACT_COVERED_PATTERNS` **漏登记** chunk 端点 → `USE_MOCK=false` 时
`shouldMock()` 返回 `true`，该端点会走 **Mock**（契约注释已写明"契约新增端点时必须同步这里；
漏更新会让新端点走 mock 而非真实接口"）。
这与 §5.3 关 Mock 硬门槛直接冲突，本批次补登记。

## 3. 验收

| # | 判据 | 口径 |
|---|---|---|
| 1 | 点击引用 → 抽屉打开并展示**真实**原文全文 | 真机（后端 8002 + Neo4j），非 Mock |
| 2 | 高亮命中引用片段 | 按 §2.1 区间；越界降级不高亮 |
| 3 | 跨租户 403 / 缺失 404 | 抽屉内显式呈现错误原因，**不**显示空原文 |
| 4 | 关 Mock 硬门槛 | `NEXT_PUBLIC_USE_MOCK=false` 下 chunk 端点走真实（补 pattern 后） |
| 5 | 门禁 | `npm run typecheck` / `lint` / `gen:api` 通过；后端门禁不受影响 |
