# Tasks: Sprint 6.4 —— 批次 C：引用溯源交互（原文抽屉 + 高亮）

> 依据 `changes/Sprint6.4/proposal.md`。勾选 ≠ 通过，须有 `integration-log.md` 实测证据。
> 本批次**纯前端**：不改后端、不改契约（`export_openapi.py --check` 必须仍为无 diff）。

## 1. 契约 / Mock 口径
- [x] 无契约变更；收尾 `uv run python scripts/export_openapi.py --check` 无 diff
- [x] `client.ts::CONTRACT_COVERED_PATTERNS` 补 `/^\/api\/v1\/documents\/[^/]+\/chunks\/[^/]+$/`
      （真机：`shouldMock` 由 true → **false**；漏登记会违反 §5.3 关 Mock 硬门槛）

## 2. API 层
- [x] `api/documents.ts` 新增 `getDocumentChunk(documentId, chunkId)` → `DocumentChunkResponse`
- [x] `api/mock/documents.ts` 补 `MOCK_DOCUMENT_CHUNK`（仅 `USE_MOCK=true` 生效，形状对齐契约）

## 3. 状态与 UI
- [x] `store/use-chat-store.ts`：抽屉状态（`chunkCitation` / `chunk` / `chunkLoading` / `chunkError`）+ `openChunk` / `closeChunk`
- [x] 新增 `components/ui/sheet.tsx`（Radix Dialog 右侧滑出版）
- [x] 新增 `components/qa/chunk-viewer.tsx`：加载骨架 / 错误（403·404 显示 `reason`）/ 全文 + 高亮
- [x] `evidence-panel.tsx`：引用条目改为可点击按钮 → `openChunk`
- [x] `chat-message-item.tsx` + `chat-panel.tsx`：对话区引用条目同样可点击
- [x] `app/qa/page.tsx` 挂载 `<ChunkViewer />`
- [x] 高亮口径**真机修正**：`snippet` 经 strip + 截断 + `…`（真机长度 201）→
      改「去省略号 + `indexOf` 对齐」，回退 `char_offset`，都不成立则不高亮
      （初版按 `char_offset + snippet.length` 实测 `highlight_match=False`）

## 4. 门禁
- [x] `npm run gen:api`（契约未变，无 diff）
- [x] `npm run typecheck`、`npm run lint` 通过
- [x] `npm run build` 通过（`/qa` 静态生成成功）
- [x] 后端门禁不受影响：`uv run pytest -q` / `ruff` / `check_seams`

## 5. 真机验证（integration-log）
- [x] `NEXT_PUBLIC_USE_MOCK=false` 下 chunk 端点走真实（补 pattern 后 `shouldMock=false`）
- [x] 真机回查：chunk `text_len=764` / `char_start=0` / `char_end=764`
- [x] 高亮对齐机械验证：`index_of_align_hit=True`（`start=0 len=200`）
- [x] dev server `GET /qa` → 200（LEN=26210）
- [ ] **人工点击确认**：浏览器 `/qa` 提问 → 点引用 → 抽屉展示真机原文且首 200 字高亮
      （我无法自动化点击，已在 integration-log §4 列出步骤）
- [ ] 错误态人工确认：不存在 `chunk_id` → 抽屉呈现 404 `reason`，不显示空原文

## 6. 收尾
- [x] `changes/Sprint6.4/integration-log.md` 补实测证据链
- [x] 提交：`feat(qa): Sprint 6.4 批次 C——引用溯源抽屉与原文高亮`
- [ ] 回 §5.3 验收：受控问题集（10~15 问真机覆盖率）随后集中跑
