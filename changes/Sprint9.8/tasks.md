# Sprint 9.8 · 前端观感对齐（基准 = `docs/demo.html`）

> **编号更正（2026-09-29）**：本批次最初误建为 `Sprint9.7`，而 **9.7 已被占用**
> （2026-09-28 完成的 **Alembic 迁移基线**，提交 `818195bd`，见
> `docs/sprint-calendar.md:78`）。当时未检查目录即 `write_to_file`，
> **覆盖了 9.7 已完成的 `tasks.md`**——已从 `818195bd` 恢复，本批次整体迁至
> **Sprint9.8**。**教训**：新建 `changes/` 目录前先 `ls`/`git ls-files`，
> 与 `tests/` 空壳那次同源——**目录外观不可信，先核实**。

## 0. 背景与决议（proposal 要点；正式 proposal.md 待补）

- **目标**：把 `frontend/` 的观感与信息架构对齐 `docs/demo.html`
  （「恩仕卫浴 · 企业知识图谱平台」，1300+ 行自包含静态原型）。
- **这不是新想法，是已有基准的扩展**：`frontend/src/lib/nav.ts:54` 早已写明
  「对齐 `docs/demo.html:409-416` 的 7 个业务域」——DOMAIN 组 7 个域就是照它建的。
  本批次把这条从**导航**扩展到**观感 + 页面骨架**。
- **排期决议（用户 2026-09-29）**：**插入 S10 之前的独立前端批次**，
  先定型观感与交互，再让 S10（证据链/多跳展示）与 S12（校正 GUI / 成本仪表盘）
  按它落功能。⇒ 本批次是 **S10 / S12 的前置**。

### ⚠️ 头号纪律冲突：demo.html 里的数字全是编的

demo 是**视觉原型**，其中的 KPI 与状态是示意值，例如：

| 位置 | demo 里的数字 |
|---|---|
| 首页总览（`:458-478`） | 图谱实体 **48,620** / 关系边 **216,340** / 今日查询 **1,284** / 待处理预警 **23** |
| 数据源接入（`:1174-1177`） | 已接入系统 **5** / 待接入 **2** / 今日同步 **28,420** / 成功率 **99.8%** |
| 业务域卡（`:489` 等） | 考勤 **127** / 售后 **342** |

而 `docs/v1.1.0-demo-mvp-plan.md` §7.2 的硬门槛是「**演示剧本 6 步零假数据**」，
决策 **A16** 要求「**诚实可核**」。

⇒ **红线**：照抄这些数字即视为造假。每个数字必须能追到真实接口；
接口取不到就显示 `—` 或「未接入」，**不得**用 demo 的示意值填充，
也**不得**为凑数字新增假接口。这一条优先于"看起来像 demo"。

## 0.5 P0 主题反转（**最先做**）：深色侧栏 + 浅色内容区

> **用户 2026-09-29 的原话痛点**：「现在的 UI 全黑乎乎的，我的 demo 右侧是白的，
> 从用户角度出发才有比较好的感受」⇒ 这是观感问题的**根因**，也是本批次
> **收益最高、成本最低**的一项（纯前端、不动契约、不碰后端）。

### 根因（已核，不是猜）

| 事实 | 位置 |
|---|---|
| `--background: #0b0b0f`（近黑），`body` 直接吃这个变量 | `globals.css:19` + `:122-128` |
| **侧栏与内容区共用同一变量** ⇒ 一起黑 | `sidebar.tsx:84` 的 `bg-background` |
| 全站无主题切换（`@custom-variant dark` 已声明但搜不到 `darkMode` / `next-themes`） | — |

而 `docs/demo.html` 的形态是**侧栏深色（`#0d2137→#132d4a` 渐变）+ 内容区浅色（`#eef2f7`）**，
两者**解耦**。⇒ 本项的本质不是"换个配色"，是**把侧栏与内容区拆成两套底色**。

### 任务

- [x] **解耦**：新增侧栏专用深色变量（`--sidebar-from/to/foreground/muted/accent/active/hover`），
      `sidebar.tsx` 改用 `sidebar-surface` 渐变；`--background` 改为 `#eef2f7`
- [x] 变量组整体反转：`--card` → 白 / `--foreground` → `#1c2b3a` / `--border` → `#e2e8f0`
- [x] ⚠️ `--muted-foreground` 调深：`#8b8b98` → `#5a6b7d`；侧栏内文字另给一套浅色值
      （`--sidebar-foreground #b8cade` / `--sidebar-muted #5c7896`）
- [x] 复核**为深底设计**的项：`--status-*` 压深、`--node-*` 改 demo 图例同色系、
      `--bubble-user` `#1b2436`→`#1a73e8`（气泡内字色反白）、
      hover 态 `bg-white/[0.0X]`→`bg-foreground/[0.0X]`（侧栏保留白叠加）
- [x] **图谱页实测结论**：画布**保持白底**（与 demo `.graph-card` 一致，**不需要**深色容器）；
      边色 `#33333f`→`#c5d5e5`、激活边→`#1a73e8`、节点标签→`#1c2b3a` / `#5a6b7d`，
      实测 `shots/02-graph.png` 标签清晰可读
- [x] 收敛硬编码：**实测不止 3 文件 6 处**——`bg-white/[0.0X]` 有 24 文件 44 处，
      为深底调的裸 hex 有 11 文件；已全量收敛（新增 `--severity-*` 替代 `#f87171`/`#facc15`）
- [x] **一次改到位**：不留"一半深一半浅"的中间态

### 改动面评估（已核）

配色集中在 `:root` 变量组 + `@theme inline` 映射，组件基本走 token，
硬编码深色类**仅 6 处** ⇒ **实测不成立**：`bg-white/[0.0X]` 24 文件 44 处 +
深底裸 hex 11 文件。已全量收敛，实际耗时一天内。
⇒ **证据链见 `changes/Sprint9.8/integration-log.md`，截图见 `shots/`。**

## 1. P1 勘察（已完成 2026-09-29，未改代码）

### 1.1 视觉底座逐项比对（`docs/demo.html` CSS vs `frontend/` P0 后现状）

| 维度 | demo | frontend 现状 | 判定 |
|---|---|---|---|
| 侧栏底色 | `linear-gradient(180deg,#0d2137,#132d4a)` | `--sidebar-from/to` 同值渐变 | ✅ P0 已对齐 |
| 内容区底色 | `body{background:#eef2f7}` | `--background:#eef2f7` | ✅ P0 已对齐 |
| **正文字号** | `body{font-size:13px}` | **未设，回落 16px** | ❌ 密度偏松 → P2 |
| 内容区 padding | `.content{padding:22px 24px 32px}` | `px-6 py-6`（24/24） | ⚠️ 底部缺 32px → P2 |
| 页面标题 | `.page-head h2{18px/600}` + `.sub{12px #8296a8}` | `22px/600` + `13px` | ❌ 偏大 → P2 |
| KPI 卡 | 4 列 `gap:14px`；label 11.5px / value 22px / 语义色 `.kpi.blue` 等 | `gap-4`(16px)；label 12px / value 28px / **无语义色** | ❌ → P2 |
| 区块标题 | `.section-ttl{13px/600 + 右侧.line 分隔线}` | **无此组件** | ❌ 新增 → P2 |
| 业务域网格 | `.domain-grid` 4 列 `gap:14` + `.domain-card:hover` 上浮 + 蓝边 | **无此组件** | ❌ 新增 → P2/P3 |
| 通用卡片 | `.card{白 / 1px #e8eef5 / radius 12 / 阴影 .04}` | `Card` 白 / `#e2e8f0` / `rounded-xl` | ✅ 一致量级 |

### 1.2 现有页面清单（`app/` 下确证 11 个 `page.tsx`）

| 路由 | demo 对应 | 判定 |
|---|---|---|
| `/` | 首页总览 `:452` | **需改**（P3） |
| `/documents` | 无独立页（demo 无） | 已有，仅密度对齐 |
| `/qa` | 知识问答 `:201` | 已有，仅密度对齐 |
| `/graph` | 全局图谱总览 `:1079` | 已有（P0 已实测） |
| `/affiliation` | 无 | 已有，仅密度对齐 |
| `/attendance` + `qa`/`attribution`/`compliance` | 考勤域 | 已有，仅密度对齐 |
| `/audit` | 无 | 已有，仅密度对齐 |
| `/settings` | 无 | 已有（placeholder） |

### 1.3 缺的视图 + 契约核查（**结论：两个都无端点**）

契约 `contracts/openapi.yaml` 共 **19 个端点**，全量核对后：
**没有任何**「数据源接入」或「权限与角色」相关端点 ⇒ 与预估一致。
⇒ 移交 P4 裁决（placeholder vs 本批次不做）。

### 1.4 ⚠️ 红线级发现：首页 4 个 KPI 目前是**假数据**

| 事实 | 位置 |
|---|---|
| `getMetricOverview()` 打 `/api/v1/metrics/overview` | `api/dashboard.ts:16` |
| **该端点不在契约的 19 个端点内**，也不在 `CONTRACT_COVERED_PATTERNS` | `api/client.ts:32-61` |
| ⇒ `shouldMock()` 对契约外端点**恒返回 true**——**即使 `USE_MOCK=false` 也走 Mock** | `api/client.ts:68-71` |
| 数据来自 `MOCK_METRIC_OVERVIEW` | `api/mock/dashboard.ts` |
| 类型注释自己写着「契约缺失，需后端补」 | `types/mock.d.ts:71` |

⇒ 当前首页显示的「已处理文档数 / KG 实体总数 / 今日回答次数 / 回答成功率」
**全是 mock 常量**，且关掉 Mock 开关也不会变真。这与 §0 红线同类，
只是"恰好不是抄 demo 的数字"。**P3 必须一并解决**，否则首页观感对齐了、
数字仍是假的——比不对齐更糟。

**出路（已核，契约内可得）**：`GET /api/v1/graph/overview` 返回
`entity_count` / `relation_count` / `doc_count` / `kg_version`（`api.d.ts:2312-2345`），
且**已在 `CONTRACT_COVERED_PATTERNS`**（`client.ts:41`）⇒ 关 Mock 即真。
⇒ P3 用契约内端点重建 KPI，取不到的口径显示 `—`。

## 2. P2 视觉底座（纯前端、零后端依赖）

- [x] 侧栏：深色渐变 + 分组标题 + 激活态左侧蓝色指示条（对齐 demo `.nav-item.active::before`）
- [x] 页面骨架组件化：`page-head`（标题 + 副标题）/ `kpi-row` / `section-ttl` /
      卡片网格（对应 demo 的 `.domain-grid` / `.ds-grid`）
- [x] 全局底色与字号密度对齐（`#eef2f7` / `13px`）
- [x] **保持** `nav.ts` 里 6 个业务域的 `disabled` + 「规划中」状态——
      给它们可点的路由等于宣称已交付（A16），**本批次不得放开**

## 3. P3 首页总览（`/`）

- [x] 改成 demo home 形态：KPI 行 + 业务域卡片网格（点击进入）
- [x] **每个数字必须可核**：实体/边数量走真实图谱接口，取不到显示 `—`
- [x] 业务域卡上的计数（demo 的 `127` / `342`）**一律不填示意值**

## 4. P4 两个管理页（待裁决后再动）

- [x] **裁决（2026-09-29，采纳建议项）**：**做 `placeholder`**——有路由、不接后端、
      UI 明示「功能预留」。理由：契约 19 个端点确证无对应端点（§1.3），
      但 demo 有这两个入口，留空位比"侧栏有入口、点了 404"诚实；
      与 `nav.ts` 既有的 `placeholder` 语义一致（`/settings` 已是同款先例）。
- [ ] ~~原待裁决项~~（已裁决）契约无端点时，
      按「暂无法匹配的功能先预留空位」铁律，做成 `placeholder`（有路由、不接后端），
      或**本批次不做**。⇒ **先写裁决，再动手**
- [x] 若做 placeholder：UI 上必须明示"功能预留"（沿用 A16 的 `badge` / `notice` 插槽）
      （已做，见 `integration-log.md` §7.4）

## 5. P5 收尾门禁

- [x] `npx tsc --noEmit` / `npm run lint` 全过（`integration-log.md` §4 / §7.5：双双 0）
- [x] 契约未动 ⇒ `npm run gen:api` 后 `git diff` 应为空（动了说明越界）
      （§4 / §7.5：`contracts/` 与 `api.d.ts` 零漂移）
- [x] **零漂移校验**：本批次**不得**产生 `contracts/openapi.yaml` 的变更
- [x] 浏览器点验：截图与 `docs/demo.html` 逐屏对照（§3 + §7.7；差异列表见
      `integration-log.md` §6 / §7.8）——**真数终验**：Neo4j 起容器后
      `shots/17-home-neo4j-up.png` 四张 KPI 全部真数
      （实体 2,625 / 关系 3,576 / 文档 13 / 已激活 attendance-demo-v1），
      `shots/18-graph-neo4j-up.png` 图谱页真实渲染

## 6. 不做什么（划界）

- **不动契约、不新增后端接口**（纯前端批次）
- **不接假数据**（见 §0 红线）
- **不放开** 6 个业务域的 `disabled` 状态
- 不做业务域内的新功能（属各自 Sprint）

## 7. 与 Sprint 9 批次 C 的关系

| | 批次 C（M4 完整化 / 实体消解） | 本批次（前端观感） |
|---|---|---|
| 是否在关键路径 | **是**（S12 前置 → S13 上线 Gate G3） | 否，但**是 S10 / S12 的前置** |
| 改动目录 | `backend/` + `contracts/` + 迁移 | 仅 `frontend/` |
| 是否动契约 | **是** | **否**（P5 有校验） |

⇒ 两者**目录不冲突，理论上可并行**。

### 排期结论（2026-09-29）：**先做本批次，不必等批次 C**

1. **零冲突**：本批次只动 `frontend/`，批次 C 动的是 `backend/` + `contracts/` + 迁移
2. **底座先行**：P0（主题）→ P2（页面骨架）→ P3（首页）是**依赖顺序**。
   若先做页面再改主题，等于把页面重做一遍；先改主题则后续都建在正确的底座上
3. **不占关键路径**：批次 C（实体消解）才是通往 S13 上线 Gate 的那条链，
   本批次不阻塞它，反过来它也不阻塞本批次
4. **收益立即可见**：观感是每天都要面对的东西，早改早受益

**前提**：务必守住"纯前端、不动契约"——一旦越界就会与批次 C 的契约改动打架。
