# Integration Log: Sprint 6.4 —— 批次 C：引用溯源交互（原文抽屉 + 高亮）

**日期**：2026-09-23
**真机环境**：后端 8002（`uvicorn`）+ Neo4j 容器 + 真实 DeepSeek；前端 dev server `:3000`
（`NEXT_PUBLIC_USE_MOCK=false`，见 `frontend/.env.local`；dev 注入 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002`）。

---

## 1. 交付内容（纯前端，契约零漂移）

| 文件 | 改动 |
|---|---|
| `api/client.ts` | `CONTRACT_COVERED_PATTERNS` 补 chunk 溯源端点（**关 Mock 硬门槛的关键修复**） |
| `api/documents.ts` | 新增 `getDocumentChunk(documentId, chunkId)` |
| `api/mock/documents.ts` | 新增 `MOCK_DOCUMENT_CHUNK`（仅 `USE_MOCK=true` 生效，文本内已标注为演示文本） |
| `store/use-chat-store.ts` | 抽屉状态 `chunkCitation` / `chunk` / `chunkLoading` / `chunkError` + `openChunk` / `closeChunk` |
| `components/ui/sheet.tsx`（新） | Radix Dialog 的右侧滑出形态（复用既有无障碍语义，不引第二个弹层库） |
| `components/qa/chunk-viewer.tsx`（新） | 抽屉内容：加载骨架 / 错误（保留 HTTP 状态 + `reason`）/ 全文 + 高亮 |
| `components/qa/evidence-panel.tsx` | 引用条目 → 可点击按钮（新增「查看原文 →」） |
| `components/qa/chat-message-item.tsx` | 展开后的引用条目同样可点击（新增 `onOpenChunk` prop） |
| `components/qa/chat-panel.tsx` | 透传 `openChunk` |
| `app/qa/page.tsx` | 挂载 `<ChunkViewer />`（不占三栏栅格） |

---

## 2. 真机证据链

### 2.1 关 Mock 硬门槛（§5.3 第 7 条）

`frontend/.env.local` = `NEXT_PUBLIC_USE_MOCK=false`。补登记前，`shouldMock()`
对 chunk 端点返回 **true**（走 Mock，直接违反硬门槛）。补登记后机械验证：

```
shouldMock("/api/v1/documents/{document_id}/chunks/{chunk_id}") = false
```

> 契约注释早已写明「契约新增端点时必须同步 `CONTRACT_COVERED_PATTERNS`；
> 漏更新会让新端点走 mock 而非真实接口」——批次 B 加端点时漏了这一步。

### 2.2 真实原文可回查

```
GET /api/v1/documents/22813b00-…/chunks/chunk-581e8912827d
→ text_len=764  char_start=0  char_end=764（真机，非 Mock）
```

### 2.3 高亮对齐：初版口径被真机推翻（本批次最有价值的发现）

| 口径 | 真机结果 |
|---|---|
| 初版：`[char_offset, char_offset + snippet.length)` | `highlight_match=False`（前 24 字一致、整体不等） |
| 修正：去省略号 + `indexOf` 对齐 | `index_of_align_hit=True` `start=0 len=200` |

根因：后端 `agents.py::_snippet` = `text.strip()` 截断 200 字**再加 `…`**
（真机 `snippet_len=201`）——strip 让摘录相对原文**位移**，省略号让长度多 1。
修正后算法写在 `chunk-viewer.tsx::splitHighlight`（含三步回退，见函数注释）。

### 2.4 页面可编译、可访问

```
npm run build → ✓ Generating static pages (9/9)，/qa 静态生成成功
dev server → GET http://127.0.0.1:3000/qa → 200（LEN=26210）
```

---

## 3. 门禁

| 项 | 结果 |
|---|---|
| `npm run typecheck` | 通过 |
| `npm run lint`（eslint） | 通过 |
| prettier | 仅格式化本批次 10 个改动文件（**未**动其余 21 个历史不合规文件） |
| `npm run build` | 通过 |
| 后端 `pytest` / `ruff` / `export_openapi.py --check` / `check_seams` | 不受影响（纯前端批次，契约零漂移） |

---

## 4. 待人工确认（我无法自动化点击）

浏览器打开 `http://127.0.0.1:3000/qa` → 提问 → 右侧「引用证据」点任一引用（或对话区展开引用）
→ 应滑出右侧抽屉，展示 764 字真机原文且开头 200 字高亮。
错误态可另验：把 URL 里的 `chunk_id` 改成不存在值应呈现 `404 / reason=chunk_id_not_in_artifact`
（抽屉内显式展示，**不**显示空原文）。

## 5. 遗留登记

- `Citation.char_offset` 现恒为 0（契约注释：实体级偏移待 `:Entity` 落 `char_start` 后细化）。
  前端已不依赖它做对齐，但**后端该字段目前无信息量** → 随 S9/S10「真实引用」一并细化。
- `_snippet` 的 strip + 省略号使「摘录长度 ≠ 原文区间长度」，若将来后端要按区间高亮，
  建议改为返回 `snippet_start` / `snippet_end`（**不在本批次改契约**）。

---

## 6. 受控问题集评估（§5.3 验收第 1 条，真机）

评估器：`backend/scripts/eval_controlled_qset.py`（**只评估、不调 Prompt**，plan §4.2 纪律）。
问题基于真机文档「2025 年度集团经营指标分析报告」（五大板块表 + 要点摘要）拟定 14 问，
其中 2 问为**库外题**（合同甲方 / 2026 年预测），用于验证拒答出口不被误伤。

```
总题数            : 14
非拒答            : 12
引用命中(chunk-)  : 12
引用覆盖率        : 100.0%   （目标 100%）
拒答口径不符      : 0
请求失败          : 0
结论              : PASS
```

逐问要点：

- 12 道库内题全部 `refused=false`、`confidence=high`、
  `citations[0].chunk_id = chunk-581e8912827d`（真实命中 `:Chunk`，无 `UUID(int=0)` 占位）；
- 2 道库外题 `refused=true` / `confidence=low` / `citations=[]`（答案「无法回答」），
  **无**把库外问题硬答成结论的误伤；
- 全部 14 问 `kg_version=v-3e381d36`（PG 真源生效，Sprint 6.3 的激活端点在跑）。

> 观察（**不在本 Sprint 修**）：真机图谱实体质量偏低——实体名出现
> 「本报告汇总了集团」「智能制造与数字服务两大板块合计贡献集团」这类整句，
> 数值（128,560 / 62.3%）被抽成独立节点，且同一实体重复 3 份。
> 答案正确性目前靠 **chunk 全文**兜住（引用链路可信），实体消解仍推 **S9**。
