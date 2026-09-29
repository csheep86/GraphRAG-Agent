# Sprint 9.9 · R18 处置任务卡（契约外端点静默 Mock 清零）

> 承接 `docs/dev-doc-status.md` **R18**；用户 2026-09-29 裁决：**方案 A 全量**。
> 证据链见 `integration-log.md`，截图见 `shots/`。

## 1. P1 会话本地化（① ②）

- [x] `api/qa.ts`：删除 `listSessions` / `listMessages`；注释写明「为什么不等后端补会话表」
- [x] `store/use-chat-store.ts`：`initialize` / `selectSession` 改为同步本地操作，
      移除 `sessionsLoading` / `messagesLoading` 两个只为服务端调用存在的状态
- [x] `components/qa/session-list.tsx`：去掉骨架屏分支；空态如实说明
      「提问后在此生成 · 仅保存在本机，刷新后清空」
- [x] `components/qa/chat-panel.tsx`：副标题由「基于 N 份文档」（无来源计数）
      改为「本机会话 · 刷新后清空 · 图谱增强检索」
- [x] `api/mock/qa.ts`：删除 `MOCK_SESSIONS` / `MOCK_MESSAGES` 及其全部编造消息数组
      （只保留 `buildMockAnswer`，服务契约内 `POST /agent/query`）

## 2. P2 重新处理按钮（③）

- [x] `document-table.tsx`：按钮 `disabled` + `title` 明示「功能预留：后端尚未实现」
- [x] `store/use-document-store.ts`：删除 `reprocess` 动作（`scheduleProgress` 保留，仍服务上传）
- [x] `api/documents.ts` + `types/mock.d.ts`：删除 `reprocessDocument` 与 `ReprocessResponse`

## 3. P3 删除无消费者的契约外 API（附带）

- [x] 删除 `api/dashboard.ts` / `api/mock/dashboard.ts`
- [x] `types/mock.d.ts`：删除 `MetricOverview` / `QaHistoryItem`，并补「已随 R18 删除」留痕
- [x] `types/mock.d.ts`：`ChatSession.doc_count` 只剩 UI 编造计数的用途 ⇒ 一并删除

## 4. P4 收尾门禁

- [x] `npx tsc --noEmit` 退出码 0
- [x] `npm run lint` 0 error / 0 warning
- [x] `npm run gen:api` 后 `contracts/` 与 `api.d.ts` **零漂移**
- [x] 浏览器点验（`USE_MOCK=false` + 真实后端 + Neo4j）：`/qa` 空会话列表如实呈现、
      `/documents` 重新处理按钮禁用态、**首页 KPI 仍为真数**（不能被本次改动带
      regression）

## 5. 不做什么（划界）

- 不动契约、不新增后端接口
- 不做服务端会话持久化（`qa_logs` 只存哈希，需先裁决明文留存口径）
- 不处理上传后的 `scheduleProgress` 假推进（同红线但**不在本批次**，已登记为 R19）
