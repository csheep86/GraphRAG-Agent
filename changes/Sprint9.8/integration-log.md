# Sprint 9.8 · P0 主题反转 —— 实测证据链

> 完成日期：2026-09-29。范围：只动 frontend/（35 个文件），contracts/openapi.yaml 零变更（门禁已验）。

## 0. 结论

根因是侧栏与内容区共用一个 --background。已拆成 --sidebar-* 与内容区两组独立变量：
内容区反转成 demo 的 #eef2f7 浅底，侧栏保留深色渐变。7 个页面全部实测截图复核，
无"一半深一半浅"残留。

## 1. 根因复核（改前实测，非转述 tasks.md）

| 事实 | 改前位置 | 复核方式 |
|---|---|---|
| `--background: #0b0b0f`，body 直接吃该变量 | globals.css:19 + :122-128 | 读文件 |
| 侧栏与内容区共用同一变量，一起黑 | sidebar.tsx:84 `bg-background` | 读文件 |
| 全站无主题切换 | 搜 `dark:` 命中 0，仅 layout.tsx 挂了无人消费的 `dark` 类 | 搜索 |

demo.html 是解耦的：`.sidebar` 渐变 `#0d2137→#132d4a`（:18），`body` 底色 `#eef2f7`（:11）。

### 1.1 与 tasks.md 的偏差（实测反哺）

tasks.md §0.5 写「收敛硬编码：仅 3 个文件 6 处」。**实测不止**：

- `bg-white/[0.0X]` 深底叠加白：**24 个文件 44 处**（浅底上等于无反馈）
- 为深底调的裸 hex：**11 个文件**（`#f87171` / `#facc15` / `#a78bfa` / `#8ab4ff` /
  `#14141a` / `#33333f` / `#4b7bff` / `#f4f4f6` / `#8b8b98`）

按「一次改到位」执行，全部收敛；未留中间态。

## 2. 改了什么

### 2.1 globals.css：令牌组整体反转 + 侧栏独立成组

| 令牌 | 改前（深底） | 改后（浅底） | 依据 |
|---|---|---|---|
| `--background` | `#0b0b0f` | `#eef2f7` | demo body |
| `--foreground` | `#f4f4f6` | `#1c2b3a` | demo body |
| `--border` / `--input` | `#22222b` / `#2a2a35` | `#e2e8f0` / `#dfe8f2` | demo 边框 |
| `--primary` / `--ring` | `#3b82f6` | `#1a73e8` | demo 主蓝 |
| `--muted-foreground` | `#8b8b98` | `#5a6b7d` | 见下条 |
| `--destructive` | `#ef4444` | `#c92a2f` | demo `.down` |

`--muted-foreground` 特意没照抄 demo 的 `#8296a8`（白底约 2.9:1，不达 AA），
取 demo `.ds-status` 的 `#5a6b7d`（约 5.4:1）。

新增侧栏专用一组（不再复用 `--background`）：

| 令牌 | 值 | 依据 |
|---|---|---|
| `--sidebar-from` / `--sidebar-to` | `#0d2137` / `#132d4a` | demo `.sidebar` |
| `--sidebar-foreground` | `#b8cade` | demo `.nav-item` |
| `--sidebar-muted` | `#5c7896` | demo `.nav-group` |
| `--sidebar-accent` / `--sidebar-active` | `#1a73e8` / `rgba(26,115,232,.18)` | demo `.nav-item.active` |
| `--sidebar-hover` | `rgba(255,255,255,.05)` | demo `.nav-item:hover` |

另新增 `--severity-high/mid/low`（`#c92a2f` / `#b26a00` / `#1e8e4a`，取自
demo `.pill.*`），替掉散落 8 个文件的 `#f87171` / `#facc15`。

### 2.2 为深底设计的项，逐项复核

| 项 | 处置 |
|---|---|
| `--status-*` | 压深：pending `#6b7d8f` / processing `#1a73e8` / completed `#6d28d9` / failed `#c92a2f` |
| `--node-*` | 白底上 `#22d3ee` 发飘，改 demo 图例同色系：`#1a73e8` / `#00a6a6` / `#e08a00` / `#7c5cd6` |
| `--bubble-user` | `#1b2436` 配深字不可读 → `#1a73e8` + 气泡内字色反白（demo `.msg.user .bubble`） |
| hover 态 | `bg-white/[0.0X]` → `bg-foreground/[0.0X]`；侧栏仍用 `--sidebar-hover` 白叠加 |

### 2.3 组件

- `sidebar.tsx`：改用 `sidebar-surface` 渐变 + `text-sidebar-foreground`；
  激活态 = `bg-sidebar-active` + 白字 + 左侧 3px 蓝指示条（对齐 demo
  `.nav-item.active::before`）。**6 个业务域的 disabled +「规划中」原样保留**。
- `top-bar.tsx`：`bg-background` → `bg-card`（白，对齐 demo `.topbar`），hover 改 `bg-muted`。
- `chat-message-item.tsx`：助手气泡改 `bg-muted`（demo `#f4f7fb`），用户气泡字色反白。
- `graph-canvas.tsx` / `graph-legend.tsx`：画布随卡片变白，边色 `#33333f`→`#c5d5e5`、
  激活边 `#4b7bff`→`#1a73e8`、标签 `#f4f4f6`→`#1c2b3a` 与 `#8b8b98`→`#5a6b7d`；
  图例面板 `bg-[#14141a]/85`→`bg-card/85`。
- `layout.tsx` + `globals.css`：移除无人消费的 `dark` 类与 `@custom-variant dark`
  （改前全仓搜 `dark:` 命中 0，留着是死代码）。

## 3. 实测证据（真跑起来截图，非代码推断）

方式：`next dev -p 3101` + `NEXT_PUBLIC_USE_MOCK=true`，Edge headless
（`--window-size=1600,1000`）截图，存 `changes/Sprint9.8/shots/`。

| 截图 | 页面 | 实测结论 |
|---|---|---|
| `01-home.png` | `/` | 侧栏深色渐变 + 内容区 `#eef2f7` + 白卡片 |
| `02-graph.png` | `/graph` | 白底画布，深色节点标签清晰可读 |
| `03-qa.png` | `/qa` | 用户气泡蓝底白字、助手气泡浅灰 |
| `04-documents.png` | `/documents` | 白底表格，状态标签紫/蓝/红/灰均可辨 |
| `05-compliance.png` | `/attendance/compliance` | 严重度红/橙标签用 `--severity-*` 后可辨 |
| `06-settings.png` | `/settings` | 「演示环境」说明卡转浅底，无深底残留 |
| `07-audit.png` | `/audit` | 审计表格浅底、图标色与文字对比正常 |
| `08-attendance.png` | `/attendance` | 考勤域页浅底一致 |

### 3.1 一个实测踩坑（记录避免复现）

第一次截图时 `/graph` 一直骨架屏、首页 KPI 全 `--`。排查：**不是主题问题**，
是 `frontend/.env.local` 的 `NEXT_PUBLIC_USE_MOCK=false` 而后端未起，请求 8000 失败。
改以进程级 `NEXT_PUBLIC_USE_MOCK=true` 起 dev 后正常。⇒ 以后跑起来看一眼前先确认 Mock 开关，
否则会把"没数据"误读成"主题坏了"。

## 4. 门禁实测

| 门禁 | 命令 | 结果 |
|---|---|---|
| 类型 | `npx tsc --noEmit` | 退出码 **0** |
| Lint | `npm run lint` | 无输出，0 error / 0 warning |
| 契约零漂移 | `npm run gen:api` 后 `git status --porcelain contracts/` | **空** |
| 越界检查 | `git status --porcelain` | 35 个文件**全部在 `frontend/src/`** |

## 5. 红线自查

- **零假数据**：本批次未新增任何数字。demo 的 `48,620 / 216,340 / 1,284 / 23`
  一个都没抄。P0 阶段截图里的 KPI 曾是 Mock 返回值——该做法已被 P1 勘察推翻
  （Mock 返回值同样是假数据），P3 已整体换源到契约内 `GET /graph/overview`，
  最终态见 §7.7：四张 KPI 全部真数，取不到的口径显示 `—`。
- **6 个业务域的 disabled +「规划中」原样保留**，未给任何可点路由。
- **不动契约、不碰后端**：`contracts/` 与 `backend/` 零变更。

## 6. 与 demo.html 的剩余差异（留给 P1/P2）

| 差异 | 归属 |
|---|---|
| 侧栏宽 200px vs demo 230px；侧栏无品牌区 | P2 |
| 无 `page-head` / `kpi-row` / 卡片网格骨架组件 | P2 |
| 首页仍是"概览 + 最近文档/问答"，非 demo 的 KPI + 业务域网格 | P3 |
| demo 有「数据源接入」「权限与角色」，前端无（契约大概率无端点） | P4 待裁决 |

## 7. P2/P3/P4（2026-09-29）

### 7.1 P2 视觉底座

| 项 | 改后 | demo 依据 |
|---|---|---|
| 正文字号 | `body{font-size:13px}` | 同左 |
| 容器 padding | `px-6 pt-[22px] pb-8` | `.content` 22/24/32 |
| 页头 | 18px + 12px 副标题 | `.page-head` |
| KPI 卡 | 11.5px label / 22px value + 语义色 | `.kpi` |
| 新增组件 | `SectionTitle` / `DomainCard` | `.section-ttl` / `.domain-card` |

新增 token：`--kpi-*`、`--tag-*`、`--elevation-*`（阴影用 `--elevation-*`，
避免与 Tailwind `--shadow-*` 同名自引用）。

### 7.2 P3 首页：数据源换掉（红线）

原 KPI 走 `getMetricOverview()` → `/api/v1/metrics/overview`，**契约外** ⇒
`shouldMock()` 恒 true ⇒ 关 Mock 也是假数。已换成契约内
`GET /api/v1/graph/overview`，并在 store 注释里写明为什么不消费前者。

「最近问答历史」同理（`/api/v1/qa/history` 契约外）⇒ 改为明示「未接入」，
不再渲染 Mock 列表。

### 7.3 起后端后的实测（USE_MOCK=false）

| 端点 | 结果 |
|---|---|
| `GET /api/v1/documents` | 真实：`total 13` |
| `GET /api/v1/graph/overview` | `NOT_IMPLEMENTED`：Neo4j 未就绪（7687 拒连） |

⇒ 第 3 张 KPI 由 `overview.doc_count` 改走 `documents.total`（能出真数 **13**）；
另 2 张保持 `—`，并按错误码区分文案：
`NOT_IMPLEMENTED` →「图谱存储未就绪（Neo4j 不可用）」，
而非笼统的「暂无 active 版本」。

### 7.4 P4 裁决：做 placeholder

契约 19 个端点确证无「数据源接入」「权限与角色」。裁决**做 placeholder**
（理由见 `tasks.md` §4）：留空位比「侧栏有入口、点了 404」诚实，
与 `/settings` 同款先例。新增 `/data-sources`、`/roles`，通
`PlaceholderPage` 明示「功能预留」，**不填任何数字**（demo 的
「已接入 5 / 同步 28,420 / 成功率 99.8%」一个没抄）。

### 7.5 门禁复跑（P2/P3/P4）

`tsc` 0 · `lint` 0 · `gen:api` 后 `contracts/` 与 `api.d.ts` **零漂移** ·
13 个路由全部 200。

### 7.7 Neo4j 就绪后的真数确认（2026-09-29 收尾）

容器 `kg-poc-neo4j`（`neo4j:5.26-community`，端口 7474/7687，口令与
`backend/.env` 一致）此前 `Exited (137)`，`docker start` 后 Bolt 正常监听。
后端 8000 无需重启（`GraphService` 懒加载连接，重试即通）。

| 端点 | 结果 |
|---|---|
| `GET /api/v1/graph/overview` | **真数**：`entity_count 2625` / `relation_count 3576` / `doc_count 4` / `kg_version attendance-demo-v1` |
| `GET /api/v1/documents` | 真数：`total 13` |

截图（`NEXT_PUBLIC_USE_MOCK=false`，3000 端口，Edge headless 1600×1000）：

| 截图 | 页面 | 实测结论 |
|---|---|---|
| `shots/17-home-neo4j-up.png` | `/` | 四张 KPI **全部真数**：2,625 / 3,576 / 13 / 已激活（attendance-demo-v1），`—` 与「未就绪」文案消失 |
| `shots/18-graph-neo4j-up.png` | `/graph` | 画布渲染真实图谱，页头「4 位文档 · 2,625 个实体 · 3,576 条关系」与 overview 一致 |

**口径备注（诚实可核，防误读）**：

- `entity_count 2625 / relation_count 3576` 来自 **PG `kg_versions` 真源**
  （`graphs.py::_fetch_graph_overview_stats`，建图时回填），与 Neo4j 里
  按 `kg_version` 裸数（Entity 2764 / 关系 4011）不同——前者是 PG 落库口径，
  属既有设计（避免 Cypher 全表扫描），**不是数据对不上**。
- `doc_count 4`（overview）vs `documents.total 13`（文档库）：前者只统计
  **挂在该 active 版本下**的文档（ADR-0002 只读 active），后者是全库文档数。
  两个数字各自真实、口径不同，首页 KPI 卡的 hint 已分别写明。

### 7.8 剩余差异（收尾时点）

- 无阻塞项。`backend/_uvicorn8000.out` 仍为运行日志（后端在跑，停后可删）。
- `/graph` 画布 500 节点投影在 2625 实体的版本里视觉密度高（节点挤在边缘），
  属布局/采样策略问题，**不属本批次**（纯前端观感批次未改图谱逻辑），
  留给 S10 证据链/多跳展示时一并看。
- ⚠️ **本批次未覆盖、但同红线的一处遗留**：收尾时全量审计了前端调用 ↔ 契约覆盖
  （19 个 `CONTRACT_COVERED_PATTERNS` vs `api/*.ts` 全部 `request()` 路径），
  发现**首页之外仍有 3 处**调用落在契约外端点，关 Mock 也静默走 Mock
  （`/qa/sessions` / `/qa/sessions/{id}` / `POST /documents/{id}/reprocess`）。
  已登记为 `docs/dev-doc-status.md` **R18**，**处置待用户裁决**——本批次不擅自改。
