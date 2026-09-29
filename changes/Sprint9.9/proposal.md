# Sprint 9.9 —— R18 处置：前端「契约外端点静默 Mock」清零

> 登记日期：2026-09-29。**临时插入的微批次**，承接 Sprint 9.8 收尾审计发现的
> `docs/dev-doc-status.md` **R18**，由用户在同一天裁决采纳「方案 A 全量」。

## 1. 为什么做

Sprint 9.8 P3 已把**首页 KPI** 从假数据源换掉，收尾审计（19 个
`CONTRACT_COVERED_PATTERNS` vs `frontend/src/api/*.ts` 全部 `request()` 路径）
发现**首页之外仍有 3 处**调用落在契约外端点。契约外端点的 `shouldMock()` **恒返回
true**（`api/client.ts:68-71`）⇒ `NEXT_PUBLIC_USE_MOCK=false` 时屏幕上显示的是
Mock 值，而**没有任何报错信号**——比"明显报错"更危险。

| # | 调用 | 被谁消费 | 改前在真机模式下的表现 |
|---|---|---|---|
| ① | `GET /api/v1/qa/sessions`（`api/qa.ts:12`） | `use-chat-store.initialize` | 问答页会话列表显示编造的 `MOCK_SESSIONS` |
| ② | `GET /api/v1/qa/sessions/{id}`（`api/qa.ts:22`） | `use-chat-store.selectSession` | 会话消息同样是 Mock |
| ③ | `POST /api/v1/documents/{id}/reprocess`（`api/documents.ts:147`） | `use-document-store.reprocess` | 文档页「重新处理」看似成功、实为空动作 |

## 2. 为什么不做方案 B（后端补端点）——决定性事实

> `qa_logs` 表 **S8 已建并已写**（矩阵 M5 行 / M3-3 均已更正），但按脱敏纪律
> （H5）**只存 `question_hash` / `answer_hash`，不存问答原文**。

⇒ 补一个 `/qa/sessions` 端点也**重建不出会话内容**。真要做服务端会话，需先裁决
「是否明文留存问答」这一产品 / 合规问题，属独立范围（建议挂矩阵 **M3-7** 那行已
登记的未排期项），**不**在本批次内做。

## 3. 改什么

| # | 处置 | 诚实性依据 |
|---|---|---|
| ① ② | 会话列表改由 `use-chat-store` **本地维护**（移除两个 API 调用、两个 loading 态与全部编造的 Mock 会话数据）；UI 明示「本机会话 · 刷新后清空」 | 列表里每条都对应一次**真实**发生过的本地问答（答案是 `POST /agent/query` 的真实返回） |
| ③ | 文档表「重新处理」按钮 `disabled` + `title` 明示「功能预留：后端尚未实现」；删除 store 动作与 API 函数 | 沿用本仓库既有先例（`nav.ts` `disabled` 的「规划中」、`/data-sources` placeholder） |
| 附带 | 删除已无消费者的 `api/dashboard.ts` / `api/mock/dashboard.ts` 及 `MetricOverview` / `QaHistoryItem` / `ReprocessResponse` 三个契约外类型 | 它们是首页假 KPI 的源头，**留着就会诱导下一个人拿它往屏幕上填数字** |

## 4. 明确不做

- **不动契约、不碰后端**（纯前端批次；契约零漂移由 P5 门禁校验）
- 不做服务端会话持久化（见 §2，属独立范围）
- 不在 UI 上声称任何"历史会话 / 云端同步"能力
- **不新增任何数字**：本批次只**删除**数字来源，不补一个替代数字
