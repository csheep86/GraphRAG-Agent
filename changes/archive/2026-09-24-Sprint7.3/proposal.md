# Change: Sprint 7.3 批次 C —— 前端疑点清单页

> **状态**：**待签字，代码未动工**。
> **上游**：`changes/Sprint7.2`（批次 B）已提交——四端点进契约（10 → 14 路径）、`npm run gen:api` 已跑、`CONTRACT_COVERED_PATTERNS` 四个新路径**已登记**、后端真机 10 条疑点可查（6 片演示数据 + `v-s71a-fe1c4dc3`）。
> **范围出处**：`docs/v1.1.0-demo-mvp-plan.md:276`（批次 C 原文：疑点清单页 + 证据链引用复用 Sprint 6 溯源交互）与 §6.3 验收清单第 1 / 2 / 7 行。

## Why

批次 B 把疑点做成了**后端可读、可复核**，但**人还看不见**：演示剧本第 5 步（客户视角）
"疑点清单页看到系统自动识别的关联交易疑点，每条带证据链"目前仍是空的——前面四步
（上传 / 看图 / 提问 / 溯源）都已真实，缺这一步则 M4 在演示里等于不存在。

更实际的一点是：**只有页面跑起来，才能验证批次 B 的契约是好用的**。批次 B 的单测是
我自己写的断言，前端是第一个"按契约自然使用"的消费者——形状别扭（比如 `evidence`
缺 `doc_id`、状态迁移不可逆）会在这一批立刻暴露。

## What Changes

**只动 `frontend/`**（角色隔离：本批次我是前端开发 A）。

| 层 | 文件 | 动作 |
|---|---|---|
| API | `src/api/affiliation.ts` | 新增：`detectAffiliation` / `getAffiliationTask` / `listAffiliationSuspicions` / `reviewAffiliationSuspicion`，照 `src/api/graph.ts:29-38` 的 `shouldMock` + `request<T>()` 模板 |
| Mock | `src/api/mock/affiliation.ts` | 新增：`MOCK_AFFILIATION_TASK` / `MOCK_SUSPICION_LIST`，字段严格对齐 `api.d.ts` 的 `AffiliationSuspicionItem` |
| Store | `src/store/use-affiliation-store.ts` | 新增（zustand，照 `use-document-store.ts` 的三态写法）：`items / total / taskId / status / loading / initialized / error` + `load / detect / review` |
| 页面 | `src/app/affiliation/page.tsx` | 新增：`"use client"` + `PageShell` + `PageHeader`（照 `documents/page.tsx:13-43`） |
| 组件 | `src/components/affiliation/suspicion-table.tsx`、`suspicion-detail-sheet.tsx` | 新增：表格照 `documents/document-table.tsx`；证据抽屉照 `qa/chunk-viewer.tsx` |
| 元数据 | `src/lib/status.ts`（或同目录新文件） | 新增 `SUSPICION_SEVERITY_META` / `SUSPICION_TYPE_META` / `SUSPICION_STATUS_META`，照 `DOCUMENT_STATUS_META`（`lib/status.ts:18`） |
| 导航 | `src/lib/nav.ts` | `workspaceNav` 加一项（`sidebar.tsx` / `top-bar.tsx` 都从这里读） |

**不改**：`contracts/openapi.yaml`（后端契约已是真源，本批次**零契约变更**——若实施中发现
必须改契约，按根 `CODEBUDDY.md` 契约同步铁律**停下报告**，不得自行改后端）。

## 决策点（**签字后方可动工**）

| # | 待裁决 | 选项 | 建议 |
|---|---|---|---|
| **C1** | 页面上"跑检测"按钮的 `doc_ids` 从哪来 | ① 一键对**当前租户全部 completed 文档**跑；② 复用 documents 页的多选，把选中 id 传进来；③ 后端新增"全租户"语义（后端改） | ✅ **建议 ①**。演示最顺（点一下就跑完全库），且不需要改后端；演示集只有 6 片，耗时 ~4s。② 会引入跨页状态传递（documents 页选中的文档要带到 affiliation 页），本批次不值得；③ 属后端范围扩张，且会让"检测覆盖哪些文档"变得不可控 |
| **C2** | 证据引用如何"回原文" | ① 复用 `GET /documents/{id}/chunks/{chunk_id}` + Sprint 6 的抽屉高亮；② 只展示 `evidence.text` 摘要，不做跳转 | ✅ **建议 ①**（plan §6.2 原文要求"复用 Sprint 6 溯源交互"）。**但有一处已知缺陷必须先说清**：`Citation.char_offset` 恒 0（S6 遗留，见 `docs/dev-doc-status.md`），所以高亮**不能**靠偏移量，改用 `evidence.text` 在 chunk 全文里做子串匹配；`page` / `char_start` / `char_end` 只作展示。匹配不上时**降级为"展示 chunk 全文不高亮"并在抽屉里说明**，不静默空白 |
| **C3** | 检测任务的轮询口径 | ① 首次 2s，3 次后降为 10s；② 固定 2s | ✅ **建议 ①**：契约注释（`api/documents.ts:99-102`）与 `docs/02-product-outline.md:196` 两处口径一致，不新造。终止条件 `completed` / `failed`；`failed` 时展示 `error_code`（后端对"无 active 版本"会回 `KG_VERSION_NOT_ACTIVE`，那是**真失败**，不是空列表） |
| **C4** | 是否需要 Mock 数据 | ① 需要（`USE_MOCK=true` 开发态不空白）；② 不需要，直接真实 | ✅ **建议 ①**：仓库默认 `.env.development` 是 `NEXT_PUBLIC_USE_MOCK=true`，不做 mock 会让开发态页面空白。**但** mock 数据必须**形状对齐契约、内容可识别为假**（`MOCK_` 前缀 + 注释），且**关 Mock 后零假数据**——plan §6.3 第 7 行的硬门槛就是这条 |
| **C5** | 复核交互的范围 | ① 每条两个按钮（确认 / 驳回），本地乐观更新后重拉；② 加批量复核；③ 加"撤销" | ✅ **建议 ①**。契约的 `AffiliationSuspicionPatchRequest` 只允许 `confirmed` / `dismissed`，且**已终态不可改回**（后端返 400）——所以"撤销"在后端不支持，做了就是假交互。批量复核无现成组件，不在本批 |

## Impact

- **受影响的前端文件**：见上表（全部新增 + `src/lib/nav.ts` 一处修改）。
- **受影响的用户**：演示剧本第 5 步首次可真实演示；审计师视角的"疑点 + 证据链"闭环成立。
- **不受影响**：后端契约 / 后端代码 / 数据库——本批次零后端改动。

## Non-goals（**明确不做**）

- **不做**审计页（Sprint 8）、**不做**疑点跳转图谱实体详情（无现成交互，且会让本批次膨胀）；
- **不做**分页（`AffiliationSuspicionListResponse` 明确不支持分页，见 `api.d.ts:589`）；
- **不做**自动触发检测（B7 已裁决：显式触发；自动投递属 S8）；
- **不做**"假进度"：任务真实状态来自 `GET /affiliation/tasks/{id}`，**不**用 `setTimeout` 模拟推进（那是 `use-document-store.ts:38-60` 的 Mock 时代写法，真实链路不得沿用）；
- **不补**后端任何字段——发现缺字段就停下报"接口对齐清单"（根 `CODEBUDDY.md` 功能预留原则 第 3 条）。
