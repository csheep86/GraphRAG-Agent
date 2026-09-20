# Sprint 4 阶段十 · 10.1.6 联调记录：接口级 Mock 开关

**批次**：Sprint 4.10.1.6
**执行时间**：2026-09-18（UTC+8）
**基线 tag**：v0.3.0
**分支**：feature/sprint-4
**执行人**：CodeBuddy（auto）
**前置批次**：Sprint 4.10.1.5（client.ts X-Org-Id 注入补丁 + dev server PID 3560 持续运行）

---

## 1. 背景与目标

### 1.1 问题
`USE_MOCK=false` 切换后，前端 10 个契约外接口（`listDocuments` / `listRecentDocuments` / `reprocessDocument` / `getGraphOverview` / `getEntityDetail` / `getDefaultEntityId` / `listSessions` / `listMessages` / `getMetricOverview` / `getRecentQaHistory`）调用真实后端时全部 404，导致 UI 全红。
契约仅实装 4 个核心接口（upload / status / graph / agent/query），其余 UI 占位接口按「功能预留原则」继续走 Mock。

### 1.2 目标
实现**接口级 Mock 开关**：契约内接口在 `USE_MOCK=false` 时走真实，契约外接口永远走 Mock，不论 `USE_MOCK` 值。单一真源在 `client.ts`，调用方按 path 模板决策。

---

## 2. 修改清单

### 2.1 源码改动（6 个文件）

| 文件 | 改动 | 净行数 |
|---|---|---|
| `frontend/src/api/client.ts` | 新增 `CONTRACT_COVERED_PATTERNS`（路径正则白名单）+ `shouldMock(path)` 函数 | +22 |
| `frontend/src/api/documents.ts` | `listDocuments` / `listRecentDocuments` / `uploadDocument` / `reprocessDocument` 改用 `shouldMock`；`getDocumentStatus` 新增 mock 分支（USE_MOCK=true 时返回完成态） | +5 / -1 |
| `frontend/src/api/graph.ts` | `getGraphOverview` / `getEntityDetail` 改用 `shouldMock`；`getDefaultEntityId` 简化为永远 mock（契约外 + 不发请求）；`getDocumentGraph` 新增 mock 分支 | +8 / -3 |
| `frontend/src/api/qa.ts` | `listSessions` / `listMessages` / `sendQuestion` 改用 `shouldMock` | +3 / -3 |
| `frontend/src/api/dashboard.ts` | `getMetricOverview` / `getRecentQaHistory` 改用 `shouldMock` | +2 / -2 |
| **小计** | | **+40 / -9** |

### 2.2 mock 数据补全（2 个文件）

| 文件 | 改动 |
|---|---|
| `frontend/src/api/mock/documents.ts` | 新增 `MOCK_DOCUMENT_STATUS`（status=completed / progress=1 / task_id / trace_id） |
| `frontend/src/api/mock/graph.ts` | 新增 `MOCK_DOCUMENT_GRAPH`（2 节点 + 1 边 + kg_version="..." + version_status="active" + trace_id） |

> mock 类型复用 `components["schemas"]["DocumentStatusResponse"]` 与 `DocumentGraphResponse`，不另建类型（按裁决 2）。

---

## 3. 关键 diff

### 3.1 `frontend/src/api/client.ts`

```diff
 export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
 
+/**
+ * 契约内端点路径模式（Sprint 4.10.1.6 起唯一真源）。
+ * 路径参数（如 {document_id}）用 [^/]+ 占位；精确锚定 ^$ 避免误匹配。
+ * 契约新增端点时必须同步这里；漏更新会让新端点走 mock 而非真实接口。
+ */
+const CONTRACT_COVERED_PATTERNS: RegExp[] = [
+  /^\/api\/v1\/agent\/query$/,
+  /^\/api\/v1\/documents\/upload$/,
+  /^\/api\/v1\/documents\/[^/]+\/graph$/,
+  /^\/api\/v1\/documents\/[^/]+\/status$/,
+];
+
+/**
+ * 接口级 mock 判定：
+ *  - USE_MOCK=true → 全 Mock（开发态零依赖）
+ *  - USE_MOCK=false → 仅契约内端点走真实；契约外端点仍走 Mock（避免 UI 全红）
+ */
+export function shouldMock(path: string): boolean {
+  if (USE_MOCK) return true;
+  return !CONTRACT_COVERED_PATTERNS.some((re) => re.test(path));
+}
+
 export type ErrorResponse = components["schemas"]["ErrorResponse"];
```

> **命名说明**：原计划命名 `useMock`，但 `use*` 前缀触发 `react-hooks/rules-of-hooks` 误报（eslint 13 errors），改为 `shouldMock`。

### 3.2 `frontend/src/api/documents.ts`（4 处调用点 + 1 处 mock 分支）

```diff
-import { USE_MOCK, delay, mockId, request } from "./client";
+import { delay, mockId, request, shouldMock } from "./client";
 import {
   MOCK_DOCUMENTS,
+  MOCK_DOCUMENT_STATUS,
   MOCK_DOCUMENT_TOTAL,
   MOCK_RECENT_DOCUMENTS,
 } from "./mock/documents";

-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/documents")) {
     await delay(260);
     ... // listDocuments
   }
-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/documents")) {
     await delay(200);
     return MOCK_RECENT_DOCUMENTS.slice(0, limit);
   }
-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/documents/upload")) {
     await delay(720);
     return { status: "pending", ... };
   }

 export async function getDocumentStatus(documentId: string) {
+  if (shouldMock("/api/v1/documents/{id}/status")) {
+    await delay(180);
+    return MOCK_DOCUMENT_STATUS;
+  }
+
   return request<...>(`/api/v1/documents/${documentId}/status`);
 }

-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/documents/{id}/reprocess")) {
     await delay(420);
     return { task_id: mockId("task"), ... };
   }
```

### 3.3 `frontend/src/api/graph.ts`（4 处）

```diff
-import { USE_MOCK, delay, request } from "./client";
+import { delay, request, shouldMock } from "./client";
 import {
   MOCK_DEFAULT_ENTITY_ID,
+  MOCK_DOCUMENT_GRAPH,
   MOCK_GRAPH_OVERVIEW,
   getMockEntityDetail,
 } from "./mock/graph";

-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/graph/overview")) { ... }
-  if (USE_MOCK) {
+  if (shouldMock("/api/v1/entities/{id}")) { ... }

-  if (USE_MOCK) return MOCK_DEFAULT_ENTITY_ID;
-  return null;
+  // 契约外 + 不发请求：永远 mock，避免 p04 首屏因返回 null 而空白聚焦。
+  // TODO: 契约补齐 `/api/v1/entities/default` 后改回 `if (shouldMock(...))` 三元判定。
+  return MOCK_DEFAULT_ENTITY_ID;

 export async function getDocumentGraph(documentId: string) {
+  if (shouldMock("/api/v1/documents/{id}/graph")) {
+    await delay(220);
+    return MOCK_DOCUMENT_GRAPH;
+  }
+
   return request<...>(`/api/v1/documents/${documentId}/graph`);
 }
```

### 3.4 `frontend/src/api/qa.ts`（3 处）

```diff
-import { USE_MOCK, delay, request } from "./client";
+import { delay, request, shouldMock } from "./client";

-  if (USE_MOCK) { ... return MOCK_SESSIONS; }
+  if (shouldMock("/api/v1/qa/sessions")) { ... return MOCK_SESSIONS; }

-  if (USE_MOCK) { ... return MOCK_MESSAGES[sessionId] ?? []; }
+  if (shouldMock("/api/v1/qa/sessions/{id}")) { ... return MOCK_MESSAGES[sessionId] ?? []; }

-  if (USE_MOCK) { ... return buildMockAnswer(payload.question); }
+  if (shouldMock("/api/v1/agent/query")) { ... return buildMockAnswer(payload.question); }
```

### 3.5 `frontend/src/api/dashboard.ts`（2 处）

```diff
-import { USE_MOCK, delay, request } from "./client";
+import { delay, request, shouldMock } from "./client";

-  if (USE_MOCK) { ... return MOCK_METRIC_OVERVIEW; }
+  if (shouldMock("/api/v1/metrics/overview")) { ... return MOCK_METRIC_OVERVIEW; }

-  if (USE_MOCK) { ... return MOCK_RECENT_QA_HISTORY.slice(0, limit); }
+  if (shouldMock("/api/v1/qa/history")) { ... return MOCK_RECENT_QA_HISTORY.slice(0, limit); }
```

### 3.6 `frontend/src/api/mock/documents.ts`（新增 MOCK_DOCUMENT_STATUS）

```typescript
import type { components } from "@/types/api";
import type { DocumentListItem } from "@/types/mock";

type DocumentStatusResponse = components["schemas"]["DocumentStatusResponse"];

/** ... 既有 MOCK_DOCUMENTS / MOCK_DOCUMENT_TOTAL / MOCK_RECENT_DOCUMENTS ... */

/**
 * USE_MOCK=true 时 `getDocumentStatus` 直接返回完成态（Sprint 4.10.1.6）：
 * 让 p02 上传后状态轮询立刻进完成态，无需真实后端。
 * progress=1 表示完成（schema 限定 0–1，不是 0–100）。
 */
export const MOCK_DOCUMENT_STATUS: DocumentStatusResponse = {
  status: "completed",
  progress: 1,
  task_id: "00000000-0000-4000-8000-000000000001",
  trace_id: "00000000-0000-4000-8000-0000000000aa",
};
```

### 3.7 `frontend/src/api/mock/graph.ts`（新增 MOCK_DOCUMENT_GRAPH）

```typescript
import type { components } from "@/types/api";
import type { EntityDetail, GraphOverviewResponse } from "@/types/mock";

type DocumentGraphResponse = components["schemas"]["DocumentGraphResponse"];

/** ... 既有 MOCK_GRAPH_OVERVIEW / ENTITY_DETAILS / getMockEntityDetail ... */

/**
 * USE_MOCK=true 时 `getDocumentGraph` 直接返回最小图谱（Sprint 4.10.1.6）：
 * 2 节点 + 1 边，让 p04 文档级力导向图可渲染。
 */
export const MOCK_DOCUMENT_GRAPH: DocumentGraphResponse = {
  doc_id: "00000000-0000-4000-8000-000000000001",
  kg_version: "00000000-0000-4000-8000-0000000000aa",
  node_count: 2,
  relation_count: 1,
  truncated: false,
  version_status: "active",
  trace_id: "00000000-0000-4000-8000-0000000000bb",
  nodes: [
    { id: "e-mock-001", kg_version: "...0aa", label: "Entity", canonical_name: "数据安全合规", entity_type: "主题", confidence: 0.95 },
    { id: "e-mock-002", kg_version: "...0aa", label: "Entity", canonical_name: "数据分级分类", entity_type: "规范", confidence: 0.92 },
  ],
  edges: [
    { id: "r-mock-001", source: "e-mock-001", target: "e-mock-002", type: "RELATED" },
  ],
};
```

---

## 4. 静态验证

### 4.1 命令与结果

| 命令 | 结果 |
|---|---|
| `tsc --noEmit` | ✅ exit 0 / 0 error |
| `eslint src --max-warnings=0` | ✅ exit 0 / 0 error / 0 warning（命名 `shouldMock` 后通过） |
| `next build` | ✅ `Compiled successfully in 952ms` / TypeScript `Finished in 2.5s` / 9 静态页生成 |
| `uv run pytest -q`（backend） | ✅ **`87 passed`** 不变（与 10.1 baseline 一致，本次未改后端） |

### 4.2 ESLint 首次报错与修正
- 首次跑 `eslint` 时 `useMock` 函数名触发 13 处 `react-hooks/rules-of-hooks` 误报（任何 `use*` 前缀函数被强制当作 React Hook）
- 4 处 `USE_MOCK is defined but never used` 警告（API 文件不再直接引用全局 USE_MOCK）
- **修正**：全局改名 `useMock` → `shouldMock`；4 文件 import 移除 `USE_MOCK`
- 复跑：✅ 0 error / 0 warning

---

## 5. 客户端 shouldMock() 决策模拟

### 5.1 脚本
临时写 `frontend/verify-mock-switch.mjs`（跑完 `Remove-Item` 删除），复刻 `client.ts` 第 27-40 行的 `shouldMock` 决策，遍历 12 个 path × 2 种 USE_MOCK = 24 个判定。

### 5.2 决策矩阵

| API 函数 | USE_MOCK=true | USE_MOCK=false |
|---|---|---|
| `qa.sendQuestion` | Mock | **Real** |
| `documents.uploadDocument` | Mock | **Real** |
| `documents.getDocumentStatus` | Mock | **Real** |
| `graph.getDocumentGraph` | Mock | **Real** |
| `documents.listDocuments / listRecentDocuments` | Mock | Mock |
| `documents.reprocessDocument` | Mock | Mock |
| `graph.getGraphOverview` | Mock | Mock |
| `graph.getEntityDetail` | Mock | Mock |
| `qa.listSessions` | Mock | Mock |
| `qa.listMessages` | Mock | Mock |
| `dashboard.getRecentQaHistory` | Mock | Mock |
| `dashboard.getMetricOverview` | Mock | Mock |

**结论**：
- USE_MOCK=true: 全部 12 行 Mock ✅（含契约内 4 个）
- USE_MOCK=false: **4 Real + 8 Mock** ✅（契约内 4 走真实；契约外 8 走 Mock）

### 5.3 Live probe `/api/v1/agent/query`（契约内接口联通验证）

```
POST /api/v1/agent/query
Headers: { X-Org-Id: "00000000-0000-4000-8000-000000000001" }
Body: { "question": "哪些文档涉及数据安全合规？", "scope": "cross_doc" }
```

| 项 | 实测 |
|---|---|
| HTTP status | **200** |
| `X-Trace-Id` (header) | `35aabe0a-3a04-454f-b8a8-e4c4c66a136c` |
| `trace_id` (body) | `35aabe0a-3a04-454f-b8a8-e4c4c66a136c`（一致 ✅） |
| `answer` | `"无法回答"` |
| `refused` | `true` |
| `refusal_reason` | `"no_grounded_evidence"`（合规触发：现有 KG 节点未覆盖该 question 的语义检索） |
| `route` | `"m3_graphqa"` |
| `confidence` | `"low"` |
| `kg_version` | `"20260917T090000Z-phase09"`（与 Neo4j `:KgVersion.version` 一致 ✅） |
| `kg_nodes` / `kg_relations` | `[]` / `[]`（拒答时空列表 ✅） |
| `token_usage` | `null`（拒答未调 LLM ✅） |

> 验收要点：
> - ✅ 契约内接口 200 OK + 拒答分支
> - ✅ trace_id 贯通
> - ✅ `kg_version` 与 Neo4j active 版本一致（ADR-0002 §3.2）
> - ✅ 拒答时 `kg_nodes` / `kg_relations` 为空（合约：`refused=true` 时非空约束解除）
> - ✅ `confidence=low` 时前端 UI 应标记「建议人工复核」（p03 UI 既有逻辑）

---

## 6. 待执行：浏览器端到端验证（CLI 不可达，转交用户）

作为 CLI agent，无法直接打开浏览器执行 DevTools Network 观察。请按以下 4 场景验证：

### 6.1 场景 A：USE_MOCK=true 浏览 4 页
1. `frontend/.env.local` 含 `NEXT_PUBLIC_USE_MOCK=true`（覆盖 10.1.5 的 false）
2. 重启 dev server（`Ctrl+C` 当前 PID 3560 后再 `npm.cmd run dev`），或保持现有 dev server 改 .env.local 后热重载
3. 浏览器 `http://localhost:3000` 浏览 p01 / p02 / p03 / p04
4. **预期**：DevTools Network 零请求到 `127.0.0.1:8000`；UI 全部用 Mock 数据展示；p02 表格有 7 条文档、p04 图谱有 7 节点 8 边、p03 问答用 mock 答案

### 6.2 场景 B：USE_MOCK=false 发问
1. `frontend/.env.local` 改 `NEXT_PUBLIC_USE_MOCK=false`
2. 重启 dev server / 热重载
3. 浏览器进 `/qa`，输入问题（如"哪些文档涉及数据安全合规？"）发送
4. **预期**：DevTools 看到 1 个 `POST /api/v1/agent/query` 请求 → 200 OK；UI 显示拒答答案；trace_id 与后端日志一致

### 6.3 场景 C：USE_MOCK=false p02 列表
1. 同 6.2 的 .env.local
2. 浏览器进 `/documents`（p02）
3. **预期**：DevTools **零** `GET /api/v1/documents` 请求；表格仍有 7 条 mock 文档；上传按钮可点击（点击后真实 POST `/api/v1/documents/upload`）

### 6.4 场景 D：USE_MOCK=true 上传 / 状态
1. 改 .env.local `NEXT_PUBLIC_USE_MOCK=true`
2. 浏览器进 p02 上传（任意 PDF）
3. **预期**：上传走 Mock（task_id 是 mockId()）；轮询 status 立即返回 `MOCK_DOCUMENT_STATUS`（status=completed / progress=1）；DevTools 零请求到 8000

### 6.5 失败回退

| 现象 | 排查 |
|---|---|
| USE_MOCK=true 但有请求到 8000 | 检查 `.env.local` 是否生效；`shouldMock` 决策矩阵（§5.2）应显示全 Mock |
| USE_MOCK=false 但契约外接口有请求 | 检查 `CONTRACT_COVERED_PATTERNS` 是否漏配；新端点应同步加正则 |
| /agent/query 真实调用 401 | 检查 dev server 是否重启加载新 .env.development；`X-Org-Id` 是否随 10.1.5 注入 |
| /agent/query 真实调用 501 | 后端 DeepSeek / Neo4j 链路未实装；本次联调可忽略（拒答分支已验证） |

---

## 7. 契约缺口清单（待后端补全，10.1.6 暂以 Mock 兜底）

| 接口 | 现状 | 触发接口级 mock | TODO |
|---|---|---|---|
| `GET /api/v1/documents?q=&status=&page=` | **契约缺失** | shouldMock=true → Mock | 后端补 `documents` 列表端点（支持 q / status / page）+ Pydantic 模型 |
| `POST /api/v1/documents/{id}/reprocess` | **契约缺失** | shouldMock=true → Mock | 后端补重新处理端点 |
| `GET /api/v1/graph/overview` | **契约缺失** | shouldMock=true → Mock | 后端补全局图谱概览（含 nodes / edges / doc_count / entity_count） |
| `GET /api/v1/entities/{id}` | **契约缺失** | shouldMock=true → Mock | 后端补实体详情（含 attributes / relations） |
| `GET /api/v1/entities/default` | **契约缺失** | 已简化为永远 Mock | 后端补默认聚焦实体端点；改回 `if (shouldMock(...))` 三元判定 |
| `GET /api/v1/qa/sessions` | **契约缺失** | shouldMock=true → Mock | 后端补会话列表 |
| `GET /api/v1/qa/sessions/{id}` | **契约缺失** | shouldMock=true → Mock | 后端补会话消息列表 |
| `GET /api/v1/qa/history?limit=` | **契约缺失** | shouldMock=true → Mock | 后端补最近问答历史 |
| `GET /api/v1/metrics/overview` | **契约缺失** | shouldMock=true → Mock | 后端补工作台指标卡 |

> 接口对齐清单触发条件未触发（无前后端漂移，仅前端缺数据兜底）。按 CODEBUDDY.md「功能预留原则」汇报用户决策。

---

## 7.1 可选优化清单（v1.1.0 候选，非契约缺口）

下列项**不阻塞 10.1.6 提交**，但建议在后续迭代消化：

### 7.1.1 `DocumentStatusResponse.progress` 字段前端未消费（dead field）

- **现象**：`DocumentStatusResponse.progress`（`0–1` 粗粒度进度，schema 限定 0.0–1.0 + null）在前端 components / app / store / lib 下 **0 处消费点**。
- **现状 UI**：`store/use-document-store.ts` 的 `scheduleProgress`（43–60 行）只更新 `status` + `entity_count`，进度展示完全由 `status` + `entity_count=1024+` 派生。
- **当前 mock**：`MOCK_DOCUMENT_STATUS.progress = 1`（schema 合规，与后端 `completed → 1.0` 映射一致）。即便删掉此字段也不影响 UI 行为（schema 标记 `progress?` optional）。
- **未来 UI**：若要做进度条，可直接由 `status` 派生——`pending → 0`、`processing → null`（spinner）、`completed → 1`、`failed → null`，无需新增字段或回放后端 progress。
- **验收**：✅ 无 UI bug；✅ schema 合规；✅ mock 与后端实测一致。
- **建议**：v1.1.0 阶段若新增进度条组件，复用 `status` 派生即可，不必单独依赖 `progress`。

---

## 8. 本次未触碰的项目（合规确认）

| 项 | 状态 |
|---|---|
| `contracts/openapi.yaml` | **未修改** |
| `frontend/src/types/api.d.ts` | **未修改**（不跑 gen:api） |
| `frontend/src/types/mock.d.ts` | **未修改**（mock 类型复用 api.d.ts） |
| `frontend/src/components/**` | **未修改**（约束） |
| `frontend/src/app/**` | **未修改**（约束） |
| `frontend/src/api/mock/{qa,dashboard}.ts` | **未修改** |
| `frontend/package.json` / `tsconfig.json` / `eslint.config.mjs` | **未修改** |
| `backend/**`（含 `app/**`、`tests/**`、`pyproject.toml`、`uv.lock`） | **未修改** |
| `backend/.env.development` | **未修改** |
| `backend/CODEBUDDY.md` / `frontend/CODEBUDDY.md` / 根 `CODEBUDDY.md` | **未修改** |

新增的运行时文件（gitignored，不提交）：
- `frontend/verify-mock-switch.mjs`（已 `Remove-Item` 删）

---

## 9. 下一步

- **10.2**：联调 `/health` + `/documents/{id}/status`（契约内接口），前端 UI 端到端验证 dev 注入与 trace_id 贯通
- **10.3**：联调 `/documents/{id}/graph`（Neo4j 子图）
- **10.4**：联调 `/documents/upload`（异步受理 + 状态机轮询）
- **10.5**：联调 `/agent/query`（LLM 链路 + 拒答分支，§5.3 live probe 已验证）
- 后续：补全 §7 契约缺口后回归本批 `CONTRACT_COVERED_PATTERNS`，移除对应 mock 分支

进程保留：
- uvicorn（10.1 启动）：PID 10644 / reloader 12416 / server 11992
- `next dev`（10.1.5 启动）：PID 3560，监听 localhost:3000（当前 USE_MOCK=false）