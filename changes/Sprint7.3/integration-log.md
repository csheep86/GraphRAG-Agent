# Sprint 7.3 批次 C —— 集成日志（前端疑点清单页）

> **状态**：**已完成**——门禁全绿 + 浏览器点验于 2026-09-24 由用户完成（§7.3）。
> 对照任务清单见 `tasks.md`；决策点见 `proposal.md`。

## 章节 ↔ 任务对照表

| 本节 | 对应 `tasks.md` | 真机证据要求 |
|---|---|---|
| §1 基线 | —（开工前快照） | ✅ `node -v` / `npm -v` / `.env.development` / 后端真机疑点 |
| §2 事前核实 | §0 | ✅ 六项各自的命令输出（含 `char_offset` 实测结论） |
| §3 决策签字 | `proposal.md` | ✅ C1–C6 结论表 |
| §4 API 层 | §1 | ✅ 文件清单 + `typecheck` |
| §5 Store 与轮询 | §2 | ✅ 轮询时序已在浏览器实测（「检测中…」→ 完成刷新） |
| §6 页面与组件 | §3 | ✅ 构建产物含 `/affiliation`；视觉与交互已人工点验 |
| §7 关 Mock 硬门槛 | §4 | ✅ 后端 + 浏览器全通 |
| §8 门禁 | §5 | ✅ lint / typecheck / `gen:api` 零 diff / build 四条 |
| §9 收尾 | §6 | ✅ 本日志 + 缺口登记；⚠️ `dev-doc-status.md` / 矩阵未同步 |

## 1. 基线（开工前快照）

```
$ node -v
v24.21.0
$ npm -v
11.19.0
$ Select-String frontend/.env.development
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_USE_MOCK=true          # 开发态默认 Mock；本批次验收需置 false

$ 后端真机（批次 B 遗留，本批次直接复用，未重新跑检测）
Invoke-RestMethod /api/v1/affiliation/suspicions
→ HTTP_OK total=10 task_id=9be54ebd-fb3a-4c50-b6fc-dc97ec8e3490
```

## 2. 事前核实（§0 六项）

| # | 核实项 | 结论 | 证据 |
|---|---|---|---|
| 1 | `api.d.ts` 含 Affiliation 五个 schema | ✅ | `AffiliationSuspicionItem`(:512)、`AffiliationTaskResponse`(:708)、`AffiliationSuspicionListResponse`(:599)、`AffiliationDetectResponse`(:413)、`AffiliationSuspicionPatchResponse`(:652) |
| 2 | `CONTRACT_COVERED_PATTERNS` 含四条 affiliation 路径 | ✅ 已登记（批次 B 完成），本批只核对 | `src/api/client.ts:45-48` |
| 3 | chunk 回查端点可用 + `char_offset` 恒 0 的处置 | ✅ 端点可用（数据源 `chunks.json`，不依赖图谱）；`char_offset` 恒 0 已由 **S6 用 `indexOf` 对齐解决** | `release-notes/v1.2.0.md:114/118`；实现 `chunk-viewer.tsx`（本批提取到 `lib/highlight.ts`） |
| 4 | 图标可用性 | ✅ `lucide-react` 导出 `ShieldAlert`；`ShieldCheck` 已被「权限审计」占用，故疑点用 `ShieldAlert`（不同分组） | `src/lib/nav.ts` |
| 5 | 契约不支持分页 | ✅ `AffiliationSuspicionListResponse` 只有 `total` / `task_id` / `items`，无 `page` | `api.d.ts:599-620` |
| 6 | 无现成真轮询实现 | ✅ `src/` 内 `setInterval` 命中 0 次，documents 页是 `setTimeout` 假推进 → 本批是首个真轮询 | 全仓搜索 |

## 3. 决策签字

| 编号 | 裁决内容 | 结论 | 证据 |
|---|---|---|---|
| C1 | "跑检测"的 `doc_ids` 来源 | ✅ 采纳建议：一键对**全部 completed 文档**跑（`listDocuments({status:"completed"})`） | `use-affiliation-store.ts` `detect()` |
| C2 | 证据回原文方案 | ✅ 采纳建议：复用 S6 chunk 端点 + `indexOf` 对齐；**并追加处置**（见 §7.2 缺口） | `lib/highlight.ts` + `suspicion-detail-sheet.tsx` |
| C3 | 轮询口径 | ✅ 采纳建议：首次 2s，3 次后降 10s；终止 `completed`/`failed` | `schedulePoll()`；契约注释 + `02-product-outline.md:196` |
| C4 | Mock 数据 | ✅ 采纳建议：有，但主体名用「示例甲 / 示例乙」**与真机招商局系不同名**，让"关 Mock 零假数据"一眼可验 | `src/api/mock/affiliation.ts` |
| C5 | 复核范围 | ✅ 采纳建议：只确认 / 驳回，**不做撤销**（后端已终态改不回，返 400） | 表格与抽屉按钮 `disabled={reviewed}` |
| C6 | `splitHighlight` 复用方式 | ✅ 采纳建议①：提取到 `src/lib/highlight.ts`，`chunk-viewer.tsx` 改为引用（两份实现会漂移） | `lib/highlight.ts`；`chunk-viewer.tsx` import 变更 |

## 4. API 层（§1）

新增 `src/api/affiliation.ts`：`detectAffiliation` / `getAffiliationTask` / `listAffiliationSuspicions` / `reviewAffiliationSuspicion`，各自 `shouldMock(path)` + `request<T>()`，照 `src/api/graph.ts` 模板。
新增 `src/api/mock/affiliation.ts`：`MOCK_SUSPICIONS`（3 条：共享法人 1 + 共享地址 2，含 1 条已复核样本）。
`src/types/mock.d.ts` 追加 Affiliation 契约既有类型别名（**未**手写与契约重名的类型）。

```
$ npm.cmd run typecheck   → exit 0
```

## 5. Store 与轮询（§2）

新增 `src/store/use-affiliation-store.ts`（zustand，三态照 `use-document-store`）：

- `load()`：空批次（`task_id = null`）按**空态**渲染，不报错；
- `detect()`：拉 completed 文档 → `POST detect` → 进轮询；
- 轮询：**首个真轮询**（模块级 `pollTimer` 句柄，`detect()` 重入先掐上一轮，避免叠加）；2s → 3 次后 10s；`failed` 展示后端 `error_code`，**不**当空列表；
- `openDetail()`：**并发回查该疑点每条证据**的 chunk 全文，单条失败不影响其余（`doc_id` 为 `null` 时按契约说明无法回查，不伪造 id）；
- `review()`：成功后本地更新 `status` / `reviewed_at` / `reviewed_by`。

## 6. 页面与组件（§3）

| 文件 | 说明 |
|---|---|
| `src/app/affiliation/page.tsx` | `"use client"` + `PageShell` + `PageHeader`（照 `documents/page.tsx`） |
| `src/components/affiliation/suspicion-toolbar.tsx` | 跑检测按钮（running 时禁用 + 转圈 + 任务状态文案）+ 类型 / 状态筛选（照 `document-toolbar.tsx`，直接渲染文案避水合闪烁） |
| `src/components/affiliation/suspicion-table.tsx` | 表格 + 骨架屏 + 空态（区分「还没跑过检测」与「筛选无匹配」）+ 错误条；类型/状态筛选为**前端内存过滤**（契约只支持 `task_id` 一个查询参数） |
| `src/components/affiliation/suspicion-detail-sheet.tsx` | 证据抽屉：主体列表 + 每条证据的原文（回查结果 / 失败说明 / 骨架）+ 底部复核 |
| `src/components/common/suspicion-badges.tsx` | 类型 / 严重度 / 状态三枚标签，文案与语义色集中在 `lib/status.ts` 的 `SUSPICION_*_META` |
| `src/lib/highlight.ts` | 从 `chunk-viewer.tsx` 提取的 `splitHighlight`（含 S6 真机教训注释） |
| `src/lib/nav.ts` | 加「疑点清单」/`/affiliation`（workspace 组，非 placeholder） |

```
$ npm.cmd run build → Compiled successfully；Route (app) 含 ○ /affiliation
```

## 7. 关 Mock 硬门槛（§4，plan §6.3 第 7 行）

### 7.1 后端侧（已真机验证）

```
GET /api/v1/affiliation/suspicions
→ total=10  task_id=9be54ebd-fb3a-4c50-b6fc-dc97ec8e3490  trace=7d56952b-…

证据回查（逐条取 evidence[0]）：
shared_legal_rep  chunk_len=1096 ev_len=1096 index_of=0 hit=True
shared_address    chunk_len=1013 ev_len=1013 index_of=0 hit=True
…（10/10 全部 hit=True，零失败）

shouldMock 路径命中（USE_MOCK=false 时判据）：
/api/v1/affiliation/detect                              match=True
/api/v1/affiliation/tasks/9be54ebd-…                    match=True
/api/v1/affiliation/suspicions                          match=True
/api/v1/affiliation/suspicions/2c6d1e3f-…               match=True
```
四条路径全部命中 `CONTRACT_COVERED_PATTERNS` → `USE_MOCK=false` 时 `shouldMock()` 恒返回 `false`，**疑点页走真实接口**，Mock 数据不参与。

### 7.2 ⚠️ 缺口登记：证据粒度是 chunk 级，不是提及级

真机 10/10 条的 `evidence.text` 与 chunk 全文**等长**（`ev_len == chunk_len`，`index_of=0`）——证据取的是整段 chunk，不是实体提及片段。若照 `splitHighlight` 渲染，会把**整段原文全部标黄**，等于"高亮了几千字"= 没有高亮且**误导**。

- **本批次处置**：整段场景改**淡底 + 标注**「证据粒度为原文片段（chunk 级）；实体提及级定位待 Sprint 10」；只有片段是全文真子集时才 `<mark>` 高亮。
- **不宣称**：片段级定位（`char_offset` 恒 0）是 `plan.md:619` 明确归 S10 的验收项，本批次**没有**做到，也没有伪造。
- 影响范围：仅呈现方式，不影响"点击证据回原文"这一验收点（§6.3 第 1 行达标）。

### 7.3 ✅ 浏览器内交互点验（2026-09-24 用户完成）

1. 关 Mock 打开 `/affiliation`：10 条、主体名招商局系（非「示例甲」）✅
2. 复核落库：点确认 / 驳回后，后端查得 `confirmed=4 / dismissed=1`，其中 2 条 `reviewed_at`（06:02:48 / 06:03:12）与点击时间吻合，`reviewed_by` 有值 ✅
3. 证据抽屉实开：涉及主体（id 级展示）+ 多证据原文并发回查 + 底部复核按钮 + `trace` 可见 ✅
4. 「跑一次检测」：按钮变「检测中…」+ 任务状态文案 → 完成后列表刷新（后端重跑产出新一批 10 条）✅

**行为说明（设计使然，非 bug）**：重跑检测后列表全部回到「待复核」——契约口径是「默认返回**最近一条 completed 任务**的疑点」（批次 B 决策 B2），新任务产出新一批 `open` 疑点；旧任务的复核记录仍在库里（按旧 `task_id` 查询可见）。**演示注意**：复核完不要立刻重跑，否则屏幕上的复核状态会"消失"。

### 7.4 ⚠️ 缺口登记（浏览器点验新发现）：证据原文含未清洗的 HTML 表格标记

抽屉实开发现 chunk 原文混有 `<table>` / `<tr>` / `<td>` 等标记（年报表格被解析为 HTML 后未转纯文本）。这是**解析层数据质量问题**（批次 A / S6 链路），**不归本批次（前端）修**；前端按原文原样展示，未做任何"美化"（不伪造干净文本）。建议随 S10 数据质量欠账一并处理。

## 8. 门禁（§5）

```
$ npm.cmd run lint       → 0 error / 0 warning
$ npm.cmd run typecheck  → tsc --noEmit exit 0
$ npm.cmd run gen:api    → 重新生成后 git diff --exit-code src/types/api.d.ts → 0
                           （契约零漂移：本批次零契约变更）
$ npm.cmd run build      → Compiled successfully，路由含 /affiliation
```

## 9. 收尾（§6）

- ✅ 本日志已写；
- ✅ `docs/dev-doc-status.md` / `docs/acceptance-traceability-matrix.md` 的 M4 前端侧同步已完成（2026-09-24 随批次 D 收尾一并处理）；
- ⚠️ 未 bump `app_version`（Sprint 7 的 v1.3.0 tag 在批次 D 收尾统一处理）；
- **未擅自处置声明**：本批次只动 `frontend/`（角色隔离）。改动 `src/components/qa/chunk-viewer.tsx` 仅为把 `splitHighlight` 移到 `lib/`（C6），未改其行为。发现证据粒度为 chunk 级后**未**自行改后端，按 §7.2 登记缺口。
