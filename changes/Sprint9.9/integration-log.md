# Sprint 9.9 · R18 处置 —— 实测证据链

> 完成日期：2026-09-29。范围：只动 `frontend/`；`contracts/openapi.yaml` **零变更**（门禁已验）。

## 0. 结论

Sprint 9.8 收尾审计发现「首页之外仍有 3 处调用落在契约外端点、`USE_MOCK=false` 时静默走 Mock」，本批次按用户裁决的**方案 A 全量**清零：**屏幕上不再有任何一处假数据来自契约外端点。**

## 1. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| ① | `api/qa.ts` | 删 `listSessions` / `listMessages`，注释写明"为何不等后端补会话表" |
| ② | `store/use-chat-store.ts` | `initialize` / `selectSession` 改同步本地操作；删两个只为服务端调用存在的 loading 态 |
| ③ | `components/qa/session-list.tsx` | 删骨架屏分支；空态如实说明「提问后在此生成 · 仅保存在本机，刷新后清空」 |
| ⑦ | `api/documents.ts` + `types/mock.d.ts` | 删 `reprocessDocument` / `ReprocessResponse` |
| ⑧ | 删 `api/dashboard.ts` + `api/mock/dashboard.ts` | 契约外且零消费者的两个假数据源 |
| ⑨ | `types/mock.d.ts` | 删 `MetricOverview` / `QaHistoryItem` / `ChatSession.doc_count` |

## 2. 为什么不做方案 B（后端补端点）

决定性事实：`qa_logs` **S8 已建已写**，但按脱敏纪律（H5）**只存 `question_hash` / `answer_hash`，不存问答原文** ⇒ 补一个 `/qa/sessions` 端点也**重建不出会话内容**。真要做服务端会话，需先裁决「是否明文留存问答」，属独立范围（挂矩阵 M3-7 已登记的未排期项）。

## 3. 门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| 类型 | `npx tsc --noEmit` | 退出码 **0** |
| Lint | `npm run lint` | 无输出，0 error / 0 warning |
| 契约零漂移 | `npm run gen:api` 后 `git status --porcelain contracts/` | **空** |

## 4. 浏览器点验（`USE_MOCK=false` + 真实后端 + Neo4j）

| 截图 | 页面 | 实测结论 |
|---|---|---|
| `shots/01-qa-local-sessions.png` | `/qa` | 会话列表为空并如实说明；无编造会话 |
| `shots/02-documents-reprocess-disabled.png` | `/documents` | 文档列表为真（共 13 份）；「重新处理」按钮禁用灰态 |
| `shots/03-home-kpi-regression.png` | `/` | **无 regression**：KPI 仍为真数 2,625 / 3,576 / 13 / 已激活 |

## 5. 红线自查

- **零新增数字**：本批次只**删除**数字来源，未补任何替代数字。
- **同红线但未处置**（超出 R18 裁决范围，已登记 `docs/dev-doc-status.md` **R19**）：
  `use-document-store` 的 `scheduleProgress` 在**真实上传后**仍用 `setTimeout` 假推进状态，并编造 `entity_count = 1024 + random`。留待用户裁决。
| ⑥ | `document-table.tsx` + `store/use-document-store.ts` | 「重新处理」按钮 `disabled` +「功能预留：后端尚未实现」；删 store 动作 |
| ⑤ | `api/mock/qa.ts` | 删 `MOCK_SESSIONS` / `MOCK_MESSAGES` 及全部编造消息数组，只留 `buildMockAnswer` |
| ④ | `components/qa/chat-panel.tsx` | 副标题「基于 N 份文档」（无来源计数）→「本机会话 · 刷新后清空 · 图谱增强检索」 |

