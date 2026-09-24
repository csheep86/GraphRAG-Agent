# Tasks: Sprint 7.3 批次 C —— 前端疑点清单页

> **状态**：**已完成并通过验收**——§4 浏览器点验于 2026-09-24 由用户完成（证据见 `integration-log.md` §7.3）。
> **前置**：`changes/Sprint7.2` 已提交且真机可用（10 条疑点可查）；决策 **C1–C6 已按建议采纳**（`proposal.md`）。
> **角色**：本批次只动 `frontend/`。发现证据粒度为 chunk 级后**未**自行改后端，按 `integration-log.md` §7.2 登记缺口。

## 0. 事前核实（**未完成不得往后走**）

- [x] **C1 / C2 / C3 / C4 / C5 已签字**（+ 实施中新增 **C6**：`splitHighlight` 提取到 `lib/highlight.ts` 两处共用）
- [x] **核实契约类型已生成**：`AffiliationSuspicionItem`(:512) / `AffiliationSuspicionListResponse`(:599) / `AffiliationTaskResponse`(:708) / `AffiliationDetectResponse`(:413) / `AffiliationSuspicionPatchResponse`(:652) 均在
- [x] **核实 `CONTRACT_COVERED_PATTERNS` 已含四个 affiliation 路径**：`client.ts:45-48`（批次 B 已登记，本批只核对）；真机复验四条请求路径全部命中 → `USE_MOCK=false` 时 `shouldMock()` 恒 false
- [x] **核实 Sprint 6 溯源交互真实现状**：chunk 端点可用（数据源 `chunks.json`，不依赖图谱）；`char_offset` 恒 0 已由 S6 用 `indexOf` 对齐解决（真机 `index_of_align_hit=True`）→ C2 直接复用，不新造方案
- [x] **核实图标**：`ShieldAlert` 可用；`ShieldCheck` 已被「权限审计」占用，疑点改用 `ShieldAlert`（不同分组）
- [x] **核实契约不支持分页**：`AffiliationSuspicionListResponse` 无 `page` / `page_size` → 不做分页

## 1. API 层（`src/api/affiliation.ts` + `src/api/mock/affiliation.ts`）

- [x] 四个函数：`detectAffiliation(docIds)` / `getAffiliationTask(taskId)` / `listAffiliationSuspicions(taskId?)` / `reviewAffiliationSuspicion(id, status)`
- [x] 每个函数照 `src/api/graph.ts` 模板：`if (shouldMock(path))` → mock 分支；否则 `request<T>()`
- [x] 类型**只**引 `components["schemas"][...]`（或在 `types/mock.d.ts` 做别名），**未**手写与契约重名的类型
- [x] Mock 数据字段严格对齐 `AffiliationSuspicionItem`；主体名用「示例甲 / 示例乙」**与真机不同名**，让"关 Mock 零假数据"一眼可验

## 2. Store（`src/store/use-affiliation-store.ts`）

- [x] zustand，三态照 `use-document-store.ts`：`loading` / `initialized` / `error`
- [x] `load()`：空批次（后端 200 + `task_id = null`）按空态渲染，不报错
- [x] `detect()`：`POST /affiliation/detect` → 拿 `task_id` → 进轮询
- [x] **轮询**（C3）：首次 2s，3 次后降为 10s，终止 `completed` / `failed`；模块级 `pollTimer` 句柄，`detect()` 重入先掐上一轮（**首个真轮询**，未沿用 documents 页的 `setTimeout` 假推进）
- [x] `review(id, status)`：成功后本地更新；已终态按钮禁用（**不做"撤销"**——后端返 400，做了就是假交互）
- [x] `openDetail()`：**并发回查该疑点每条证据**的 chunk 全文；`doc_id` 为 `null` 按契约说明无法回查，**不伪造 id**

## 3. 页面与组件

- [x] `src/lib/nav.ts` 加导航项「疑点清单」/`/affiliation`（非 placeholder）
- [x] `src/app/affiliation/page.tsx`：`"use client"` + `PageShell` + `PageHeader`
- [x] `src/components/affiliation/suspicion-table.tsx`：列 = 类型 / 严重度 / 涉及主体 / 证据 / 状态 / 操作；骨架屏 + 空态（区分「还没跑过检测」与「筛选无匹配」）+ 错误条
- [x] 三枚徽章：新增 `SUSPICION_*_META`（照 `DOCUMENT_STATUS_META`），复用 `ui/badge.tsx`
- [x] `src/components/affiliation/suspicion-detail-sheet.tsx`：证据抽屉（照 `qa/chunk-viewer.tsx`）；**整段 chunk 场景改淡底 + 标注**，不整段标黄（`integration-log.md` §7.2）
- [x] `src/components/affiliation/suspicion-toolbar.tsx`：跑检测按钮（running 禁用 + 任务状态文案）+ 类型 / 状态筛选
- [x] 复核按钮：确认 / 驳回，已复核禁用 + `title` 说明「不可改回待复核（契约限定）」

## 4. 关 Mock 硬门槛（plan §6.3 第 7 行）

- [x] `NEXT_PUBLIC_USE_MOCK=false` 下打开疑点页，**条数与后端真机一致**：10 条、招商局系真机数据（浏览器截图核验）
- [x] 复核一条 → 刷新页面后状态仍为 `confirmed`（**落库证据**）：点确认 / 驳回后后端查得 `confirmed=4 / dismissed=1`，其中 2 条 `reviewed_at` 与当次点击时间戳吻合，复核人与时间均已落库
- [x] 证据抽屉能取到 chunk 全文：**真机 10/10 条回查成功**（`index_of` 命中，零失败）；浏览器抽屉实开核验正常（多证据并发回查、底部复核按钮、trace 可见）
- [x] 「跑一次检测」轮询：按钮变「检测中…」+ 任务状态文案 → 完成后列表刷新（后端重跑产出新一批 10 条）

## 5. 门禁

- [x] `npm run lint` → 0 error / 0 warning
- [x] `npm run typecheck`（`tsc --noEmit`）→ exit 0
- [x] `npm run gen:api` 后 `git diff --exit-code -- src/types/api.d.ts` → **契约零漂移**（本批次零契约变更）
- [x] `npm run build` → 通过，路由含 `/affiliation`

## 6. 收尾

- [x] 补 `integration-log.md`（基线 / 事前核实 / 决策 / API / store / 页面 / 关 Mock / 门禁 / 未擅自处置声明）
- [x] 缺口登记：证据粒度为 chunk 级（`ev_len == chunk_len`），片段级定位归 S10，未伪造高亮
- [x] `docs/dev-doc-status.md` + `docs/acceptance-traceability-matrix.md` 同步（2026-09-24 随批次 D 收尾一并完成：M4 前端侧登记 + 黄金路径步骤 4 刷新 + 两处缺口同步进矩阵）
- [x] 未 bump `app_version`（Sprint 7 的 v1.3.0 tag 在批次 D 收尾统一处理）
