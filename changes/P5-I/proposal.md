# P5-I · **M6 批次 B：本体校正 GUI**（merge / split / rename 三动作）

> **日期**：2026-10-09　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-I0/integration-log.md`](../P5-I0/integration-log.md)（`main` = `bbe4388d`，CI run `37790726279` 四 job 全绿；
> 开工实测最新绿 run = `37791505100` / commit `cf2fab9e`）
> **边界**：本文件 §3（**10 条** Non-goals，逐条对照）｜**花销**：预期 **¥0**（本批不接 `cold-start` 的 LLM 调用）
> **任务拆解**：[`tasks.md`](./tasks.md)
> **跨角色批次**：契约（架构师）→ 后端（B）→ 前端（A）三段，**顺序不可颠倒**，每段单独提交

---

## 1. 目标（一句话）

把 m6 §1.1 **批次 B「本体校正 GUI」**做出来：前端能**选到实体**并真的发起
`merge` / `split` / `rename`（后端三端点 P5-G 已真实现），动作成功后能看到**新的 `kg_version`**，
并把图谱视图刷到新版本。

三刀：

1. **候选列表端点**（D3 = **A**）：新增 `GET /api/v1/ontology/candidates`
   （`entity_merge_candidates` 分页 + `status` 过滤）——spec §1.1 第 2 条要求 GUI **与该表绑定**，
   契约里现有的 28 条 path **没有**候选读端点 ⇒ 走**契约先行五步**。
2. **后端落点**（B）：schema + service + 路由 + RBAC 登记 + 真 PG 用例（含跨 org 断言）。
3. **前端 GUI**（A）：新路由 `/ontology` + 候选表 + 三动作弹窗 + `kg_version` 回显 + 图谱刷新，
   并在 `client.ts` 同步 `CONTRACT_COVERED_PATTERNS`（否则关 Mock 后**静默走假数据**）。

**同批必做**：更新 `specs/m6-ontology-incremental.md` §10.1.1 的落地状态表
（批次 B 由「未开工」改为事实；**编号不重排**，守 R5）。

## 2. 为什么是这一刀

### 2.1 三条机械理由

1. **它是 m6 §1.1 四批次里唯一「前置已清 + 排期已到」的一项**：A（冷启动建议）与 C（增量重算）已落地，
   **D（成本仪表盘）被 `cost_ratio` 阈值（TBD-7，Sprint 13 才收敛）挡着**，只剩 B 没做。
2. **它的最后一个前置在 P5-I0 刚被清掉**：P5-I0 修的是「连续第 4 次校正必然 500」
   （版本号撑爆 `String(64)`）——人手连点 4 次 rename 就会撞到。P5-H §2.2 当年把 GUI 往后排的理由已全部失效：
   读侧的洞 **P5-H 已堵**（三条读路径已切版本继承读）；版本号 **P5-I0 已修**（定长 29 字符）。
3. **判据可机械、且不需要新算法**：点了之后返 200 + `status="applied"` + 新 `kg_version`，
   图谱刷新后能看到校正结果 ⇒ **本批不重造后端**（Non-goal 1）。

### 2.2 为什么**不是**这两条

| 候选 | 不做的原因 |
|---|---|
| **剩余读路径切换 + `agents.py` 接线**（P5-H §9 指针 1 / 3） | 属**另一条价值链**（后端读侧完整性）。GUI 走的是 `fetch_graph_overview`，**已切**继承读 |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | `cost_ratio` 阈值 TBD-7 **Sprint 13** 才收敛 ⇒ 现在拿不到判据 |

## 3. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不动后端三动作的实现**：`app/services/kg/correction.py` 与 `routes/ontology.py` 的
   merge / split / rename **主流程一行不改**（P5-G 已真实现 + 真图用例钉住）。
2. **不改写侧**：`app/services/kg/incremental.py` **一行不改**
   （P5F-3「增量重写节点数 = 校正节点数」必须继续成立；版本号格式 P5-I0 刚定，**不许再改**）。
3. **不做剩余读路径切换**：`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` /
   `list_attendance_anomalies` / `explain_attendance_anomaly` / `fetch_document_subgraph` /
   `agents.py` 检索 **本批不动**（P5-H §9 指针 1，逐条登记，不许顺手做）。
4. **不做多跳推理的 id 级图遍历**（P5-H 的 **P5H-6** 限制本批不解）。
5. **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`**：批次 D。
6. **不新增第三方依赖**：前端用现有 Radix + cva + tailwind-merge；后端用现有栈。
7. **不做 RBAC 前端化**：后端已有 `require_permission`（`PROTECTED_ENDPOINTS` 9 条）；
   前端**没有** RBAC（`frontend/src/app/roles/page.tsx:6` 明写功能预留）⇒ 本批**不**造角色判断，
   入口可见性只能沿用 `frontend/src/lib/nav.ts` 的 `disabled` / `placeholder` / `badge` 三个字段。
8. **不做批量校正 / 撤销栈 / 本体版本对比 GUI**：m6 §1.2 明列 Out of Scope。
9. **不做 i18n**：项目**无** i18n，中文文案**硬编码**（`frontend/src/lib/nav.ts:22` 注释明写）。
10. **不改 `specs/m6-ontology-incremental.md` 的章节编号**：只更新 §10.1.1 的落地状态表
    （P5-I0 建的、专为这种更新留的位置；**不重排、不覆盖原文**，守 **R5**）。

## 4. 决策（**D3 / D4 / D5 / D6 四条为必答，先裁决后动手**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **M6 批次 B：本体校正 GUI（三动作）** |
| **D2** | 是否新增配置 | **不新增**（无 `settings.*` 新增；`check_seams.py` 的「无消费者配置」判据保持 OK 12） |
| **D3** ⚠️**必答** | **候选列表从哪来**（spec §1.1 第 2 条要求与 `entity_merge_candidates` 表**绑定**） | ✅ **取 A**：新增 `GET /api/v1/ontology/candidates`（分页 + `status` 过滤），**先走契约先行五步**。<br>**不取 B**（只手动选两个实体 ⇒ 与 spec「绑定」不符，须登记偏离）；**不取 C**（复用 `GET /graph/overview` ⇒ 无候选元数据：相似度 / 判分信号 / 状态） |
| **D4** ⚠️**必答** | 前端落点 | ✅ **取 A**：新增路由 `/ontology`（`frontend/src/app/ontology/page.tsx`）+ 三动作弹窗，侧栏 `frontend/src/lib/nav.ts` 加一项（图标 `Split`）。<br>**不取 B**（嵌进 `/graph` 页）：要打通 `GraphCanvas` 选中态与校正弹窗，属另一条改动链，本批不摊 |
| **D5** ⚠️**必答** | 动作成功后怎么表现新版本 | ✅ **取 A**：显示响应的 `kg_version` + **真的**触发图谱刷新（`useGraphStore.load()` ⇒ `GET /graph/overview`，该路径已切版本继承读 ⇒ 刷新后是**完整**图谱而非只有受影响子图）。<br>**不取 B**（只弹 Toast）：spec §5.1 第 3 条「校正后问答 / 图谱立即反映新图谱」在 UI 上证不到 |
| **D6** ⚠️**必答** | Mock 与契约门禁 | ✅ **必须**在 `frontend/src/api/client.ts:32-61` 追加 `/api/v1/ontology/*` 的 pattern（现 **19** 条 ⇒ 追加 `candidates` / `merge` / `rename` / `split` 四条 ⇒ **23** 条）；`mock/ontology.ts` **只在 `shouldMock()` 为真时命中**。<br>**判据**：`NEXT_PUBLIC_USE_MOCK=false` 下点三动作打到的是**真后端** |
| **D7** | split 的 `new_entities` 怎么填 | `OntologyNewEntity` 目前**只有 `canonical_name`**（`openapi.yaml:2762-2772`，省略号刻意不展开）⇒ 前端只让填**名称列表（≥2）**。**不许**在前端假造关系信息（P5-G 的 P5G-3：split 的关系迁移只取「默认同名」一条规则） |
| **D8** | 版本号要不要在 UI 上显示 | **要显示**：自 P5-I0 起版本号**恒 29 字符**（`<YYYYMMDDTHHMMSSZ>-inc-<8hex>`）⇒ 不需要担心溢出 / 截断；**但不要**从字符串推断父子关系（真源是 `ontology_actions`，ADR-0008 §3） |
| **D9** | 审计 | **不新增审计点**：M5 中间件已全量覆盖三端点（`PROTECTED_ENDPOINTS` 9 条）；新候选端点同样由中间件覆盖，仅在 `ACTION_BY_ROUTE_NAME` 登记业务 action 名（否则中间件回落 `http.get.<path>` 并打 WARNING） |
| **D10** | 契约会不会动 | **会动**：新增 1 条 path（**28 ⇒ 29**）+ `components.schemas` 新增 `OntologyCandidate` / `OntologyCandidateListResponse` |
| **D11** | 成本敞口 | 本批 **¥0**（`cold-start` 属批次 A，本批不接它的 LLM 调用） |

## 5. 本批需要登记的**决策补充**

| # | 冲突点 | 本批取法 | 登记理由 |
|---|---|---|---|
| **P5I-1** | 候选端点**跨租户**该返 403 还是空集 | **空集**（`items=[]` / `total=0`，与 `GET /audit/trace/{id}` 同口径） | 列表类端点泄露不了单条资源的存在性；返回 403 会让「待复核队列为空」和「无权访问」在 UI 上无法区分。测试**仍在 PG 上显式断言跨 org 读不到**（§9 / 判据 2） |
| **P5I-2** | 候选响应带不带 `trace_id` | **不带**（与 `OntologyActionResponse` / `OntologyActiveResponse` 一致） | spec §5.5 只有 `cold-start` 响应列了 `trace_id`，其余端点没有 —— 冲突时**以 spec 为准**（`schemas/ontology.py` 文件头已登记该取舍） |
| **P5I-3** | 前端要不要按角色隐藏入口 | **不隐藏**（只做错误展示：403 → 「当前角色无本体权限」） | Non-goal 7：前端无 RBAC；造角色判断属另一条价值链。**跨租户 403 与无权限 403 在 UI 上都显示为「被拒绝」**，不假造成功 |
| **P5I-4** | 实体从哪选 | **只从候选行选**（`left_entity_id` / `right_entity_id`） | 引入实体搜索端点要新增契约端点（超出 D3 的那一条）；候选行已提供三动作所需的实体 id |
| **P5I-5** | `signals` 要不要进契约 / 上 UI | **进契约**（`dict \| None`，可空），UI 只在 hover 里回显判分依据 | 它是「为什么判这一档」的唯一载体（M2 §4.5.1）；不上 UI 就没有消费者 ⇒ 只做 `title` 级回显，不做渲染面板 |

## 6. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **契约先行** | `openapi.yaml` 新增 `GET /api/v1/ontology/candidates` + `components.schemas`；`export_openapi.py --check` 零 diff（**28 ⇒ 29 路径**） |
| 2 | **后端候选端点** | 真 PG 用例：`status` 过滤生效、`org_id` 强制（**跨 org 读不到**）、非法 `status` → 400 `VALIDATION_ERROR` |
| 3 | **前端 API 模块** | `frontend/src/api/ontology.ts` 存在，类型**只**取 `components["schemas"]["Ontology*"]`；`mock/ontology.ts` 齐备 |
| 4 | **Mock 门禁同步**（D6） | `NEXT_PUBLIC_USE_MOCK=false` ⇒ `shouldMock("/api/v1/ontology/merge") === false`；`true` 时走 mock 且**不**发请求 |
| 5 | **三动作 UI 可用** | 能选到实体并发起 merge / split / rename；`typecheck` + `lint` + `build` 三连绿 |
| 6 | **动作成功可见新版本**（D5） | UI 显示响应回来的 `kg_version`，刷新图谱后能看到校正结果（改名 ⇒ 新名；合并 ⇒ 被并入侧消失） |
| 7 | **错误分支不静默** | 404 `ENTITY_NOT_FOUND` / 403（跨租户，**不是 404**）/ 409 `KG_VERSION_NOT_ACTIVE` 三条在 UI 上有可辨识反馈（不吞错、不假造成功） |
| 8 | **契约零漂移** | `export_openapi.py --check` 零 diff；CI 的 `gen:api` + `git diff --exit-code -- frontend/src/types/api.d.ts` 通过 |
| 9 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0；`check_seams.py` 仍 ERROR 0 / WARN 0 / OK 12 |
| 10 | **pytest 不降** | CI **≥ 1139 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 11 | **spec §10.1.1 已更新** | 批次 B 改为已落地 + 仍缺什么；**编号未重排**（R5） |
| 12 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

## 7. 隔离红线（**ADR-0003 §4.1**，本批动的是租户隔离相关路径的前端入口）

本批**必须**带上两类测试，且**在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only`**：

- **T1 跨 org 越权**（G-9，`test_guardrails_graph.py` + `test_guardrails_rls.py`）；
- **T2 并发串租户**（G-10，`backend/tests/test_guardrails.py:328`）。

新增的候选端点**必须**显式断言「跨 org 读不到」；既有断言**一律不许放宽**。
