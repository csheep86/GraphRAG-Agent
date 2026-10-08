# 新会话开场提示词 · P5-I（M6 批次 B：**本体校正 GUI**）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：上一批（**P5-I0**）已收口（`main` = `bbe4388d`，CI run `37790726279` 四 job 全绿）、
> 不会再回来。开工所需坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 的**五份仓库内文件**。
>
> ⚠️ **本批是跨角色批次**：契约（架构师）→ 后端（B）→ 前端（A）三段，**顺序不可颠倒**
> （契约先行铁律）。三段各自单独提交。
>
> 使用时：把本文件**全文**复制到新会话作为第一条消息。

---

## 0. 本批一句话

把 m6 §1.1 **批次 B「本体校正 GUI」**做出来：前端能**选到实体**并真的发起
`merge` / `split` / `rename`（后端三端点 P5-G 已真实现），动作成功后能看到**新的 `kg_version`**，
并把图谱视图刷到新版本。

**同批必做**：① 若 §5 **D3** 判定要新增候选列表端点 ⇒ 先走**契约先行五步**；
② 更新 `specs/m6-ontology-incremental.md` §10.1.1 的落地状态表（批次 B 由「未开工」改为事实）。

**不做**：成本仪表盘（批次 D）、剩余读路径切换（P5-H 的债）、`alert` 表（P2）。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 0 | **`changes/P5-I0/new-session-prompt.md`**（可选） | 上一批的开工提示词。不想读完整实录时，看它就能知道「为什么先做版本号定长」以及本批的前置是怎么被清掉的 |
| 1 | **`changes/P5-I0/integration-log.md` §5 / §6.4** | 上一批实录。**重点 §5.1**（`String(64)` 的**两个面**：产品产物 vs 测试数据，别再把它们混成一件事）、**§6.4**（一次「看起来像改坏了」的伪失败，根因是全局计数断言被残留击穿） |
| 2 | **`contracts/openapi.yaml:5006 / 5088 / 5170`** | 三端点的真契约：`POST /api/v1/ontology/merge` / `rename` / `split`；请求 `OntologyMergeRequest` / `OntologyRenameRequest` / `OntologySplitRequest`；响应统一 `OntologyActionResponse{kg_version, status}`（`status` 恒 `"applied"`，同步） |
| 3 | **`backend/app/api/v1/routes/ontology.py:176-311`** | 三端点的路由与 RBAC（`require_permission`）现状；同文件另有 `GET /ontology/active`、`POST /ontology/confirm`、`POST /ontology/cold-start`（**仍是占位**） |
| 4 | **`frontend/src/api/compliance.ts` + `frontend/src/api/client.ts:32-71`** | 前端 API 模块的标准写法 + **Mock 门禁真身**：`CONTRACT_COVERED_PATTERNS` 现 **19 条**；`NEXT_PUBLIC_USE_MOCK=false` 时对契约外端点**恒走 Mock** ⇒ 新增 `/api/v1/ontology/*` 后**必须**同步追加 pattern，否则静默假数据 |
| 5 | **`frontend/src/components/documents/upload-dialog.tsx` + `frontend/src/app/documents/page.tsx:22-42`** | 「弹窗 + 表单 + 校验 + 提交」最佳复用范例（Radix + cva + tailwind-merge 自研 UI，**不是 antd**；**无 i18n**，中文硬编码） |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B~P5-I0 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-I/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **本批预期要动契约**（§5 **D3**）⇒ 走完同步五步：**不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

> ⚠️ **契约描述的真源是 `backend/app/core/openapi.py`，不是 `contracts/openapi.yaml`**
> （后者是 `export_openapi.py` 的导出产物，手改会被 `--check` 判漂移）。P5-I0 刚在这里踩过一次。

**角色隔离**（三段，**每段单独提交**）：

| 段 | 角色 | 允许改的范围 | 顺序 |
|---|---|---|---|
| ① 契约 | **架构师** | 只 `contracts/openapi.yaml`（由脚本导出，不手改）+ `backend/app/core/openapi.py` | 第一 |
| ② 后端 | **后端开发 B** | 只 `backend/`（`schemas/` `routes/` `services/` + 测试） | 第二 |
| ③ 前端 | **前端开发 A** | 只 `frontend/`（含 `npm run gen:api` 生成的 `src/types/api.d.ts`） | 第三 |

**分支**：沿用 P4 / P2-C / P5-B~P5-I0 —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-I / 为什么是这一刀

### 2.1 三条机械理由

1. **它是 m6 §1.1 四批次里唯一「前置已清 + 排期已到」的一项**：
   A（冷启动建议）与 C（增量重算）已落地，**D（成本仪表盘）被 `cost_ratio` 阈值
   （TBD-7，Sprint 13 才收敛）挡着**，只剩 B 没做。
2. **它的最后一个前置在 P5-I0 刚被清掉**：P5-I0 修的是「连续第 4 次校正必然 500」
   （版本号撑爆 `String(64)`）——**人手连点 4 次 rename 就会撞到**。不做它先开门，
   GUI 上线当天就炸。P5-H §2.2 当年把 GUI 往后排的理由也已全部失效：
   - 「必须先堵读侧的洞」⇒ **P5-H 已堵**（版本继承读，三条读路径已切）；
   - 「版本号会撑爆」⇒ **P5-I0 已修**（改为定长 29 字符）。
3. **判据可机械、且不需要新算法**：点了之后返 200 + `status=applied` + 新 `kg_version`，
   图谱刷新后能看到校正结果。后端已有真实现与真图用例 ⇒ **本批不重造后端**。

### 2.2 为什么**不是**这两条

| 候选 | 不做的原因 |
|---|---|
| **剩余读路径切换 + `agents.py` 接线**（P5-H §9 指针 1 / 3） | 属**另一条价值链**（后端读侧完整性）。它不是 spec 排期项，也不影响 GUI 能不能用 —— GUI 走的是 `fetch_graph_overview`，**已切**继承读 |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | `cost_ratio` 阈值 TBD-7 **Sprint 13** 才收敛 ⇒ 现在拿不到"显著 < 1.00"的判据 |

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（**28 路径**）
uv run pytest -q                                      # 本地口径基线见 §7
cd d:\AIProject\GraphRAG-Agent\frontend
npm ci ; npm run typecheck ; npm run lint
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

> 本机 Neo4j / PG 容器若停了：`docker start graphrag-neo graphrag-pg`。
> 真图用例三开关：`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。

---

## 4. 明确不做（**10 条 Non-goals**，逐条对照）

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

---

## 5. 决策表（**本批需要你自己裁决并在 integration-log 登记**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **M6 批次 B：本体校正 GUI（三动作）** |
| **D2** | 是否新增配置 | **预期不新增**；若确需 ⇒ ① 有真实消费者 ② 同步 `.env.example` ③ 不得占位 |
| **D3** ⚠️**必答** | **候选列表从哪来**（spec §1.1 第 2 条要求与 `entity_merge_candidates` 表**绑定**） | **契约里没有**候选读端点（28 条 path 中无之；该表只在 merge 的描述里作为被 `human_review → applied` 更新的表出现）。三选一：<br>**A（建议取此）** 新增 `GET /api/v1/ontology/candidates`（分页 + `status` 过滤）⇒ **先走契约先行五步**；<br>**B** 不新增，GUI 只做「手动选两个实体」⇒ 与 spec「绑定」**不符**，**必须在 integration-log 写明偏离**；<br>**C** 复用 `GET /graph/overview` 图上点选 ⇒ **无候选元数据**（置信度 / 来源），也**不满足**绑定要求 |
| **D4** ⚠️**必答** | 前端落点 | **A（建议）** 新增路由 `/ontology`（`frontend/src/app/ontology/page.tsx`）+ 三动作弹窗，侧栏 `frontend/src/lib/nav.ts` 加一项；<br>**B** 嵌进现有 `/graph` 页（`EntityDetailPanel` 上加「校正」按钮）。<br>⚠️ 取 B **必须**回答：图谱页的选中态怎么与校正弹窗打通（`GraphCanvas` 的选中态在哪） |
| **D5** ⚠️**必答** | 动作成功后怎么表现新版本 | **A（建议）**：显示响应的 `kg_version` + 触发图谱刷新（`/graph/overview` 已切继承读 ⇒ 刷新后能看到**完整**图谱而非只有受影响子图）；<br>**B** 只弹 Toast ⇒ spec §5.1 第 3 条「校正后问答 / 图谱立即反映新图谱」**在 UI 上证不到** |
| **D6** ⚠️**必答** | Mock 与契约门禁 | **必须**在 `frontend/src/api/client.ts:32-61` 追加 `/api/v1/ontology/*` 的 pattern（现 19 条）；且 `frontend/src/api/mock/ontology.ts` 只在 `shouldMock()` 为真时命中。**判据**：`NEXT_PUBLIC_USE_MOCK=false` 下点三动作打到的是**真后端** |
| **D7** | split 的 `new_entities` 怎么填 | `OntologyNewEntity` 目前**只有 `canonical_name`**（`openapi.yaml:2762-2772`，省略号刻意不展开）⇒ 前端只让填**名称列表**（≥2）。**不许**在前端假造关系信息（P5-G 的 P5G-3：split 的关系迁移只取「默认同名」一条规则） |
| **D8** | 版本号要不要在 UI 上显示 | 若要显示：自 P5-I0 起版本号**恒 29 字符**（`<YYYYMMDDTHHMMSSZ>-inc-<8hex>`）⇒ **不需要**担心溢出 / 截断；**但不要**从字符串推断父子关系（真源是 `ontology_actions`，ADR-0008 §3） |
| **D9** | 审计 | 本批不新增审计点；M5 中间件已全量覆盖三端点（`PROTECTED_ENDPOINTS` 9 条） |
| **D10** | 契约会不会动 | **预期要动**（D3 取 A 时）。若最终判定不动 ⇒ 登记理由 |
| **D11** | 成本敞口 | 本批**预期 ¥0**（`cold-start` 属批次 A，**本批不接它的 LLM 调用**） |

---

## 6. 已完成（**前序批次，别重做**）

- ✅ **版本号定长**（P5-I0，`main` = `c3371ad1`）：`<stamp>-inc-<8hex>` 恒 29 字符；
  含「连续 8 级长度恒定」判据 + 「旧写法第 4 级 = 69 > 64」看门狗。**GUI 的前置已清**。
- ✅ **版本链读侧**（P5-H，`f503e8a4`）：`fetch_graph_overview` / `fetch_reasoning_path` /
  `scan_attendance_compliance` 按**版本继承读**读图（**ADR-0008**）。
- ✅ **M6 三端点接线**（P5-G）：真实现 + RBAC（6 ⇒ 9）+ `entity_merge_candidates.status = applied`。
- ✅ **增量重算**（P5-F）/ **M5 统一脱敏**（P5-E）/ **私域出向管控**（P5-D）/ **M6 第一批**（P5-C）。
- ✅ **P5-I0 顺手清掉的三笔文档债**：`openapi.py` 的 `ontology` tag 描述、spec §5.5 端点状态句、
  DR-B6 / DR-B7 与 G-9 / G-10 的口径对账。
- ⚠️ **继续有意不做**：`alert` 表（P2，**已连续六批**）；成本仪表盘（批次 D）；
  剩余读路径切换（§4 第 3 条）。

---

## 7. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1139 passed / 5 skipped / 0 failed**（run `37786962196` / commit `166e4122`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*` 三开关） | P5-I0 实读 **1138 passed / 4 skipped / 2 failed** —— 2 条 failed 是**本地特有的既有环境债**（`test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty` 与 `test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，依赖 CI 才有的受控种子语料；**CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿**） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**28 路径**；D3 若新增端点 ⇒ 数字会变，**必须**写明新数字） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **9 条** |
| `CONTRACT_COVERED_PATTERNS` | `frontend/src/api/client.ts:32-61`，现 **19 条**（D6 追加后数字会变） |
| 版本号长度 | 自 P5-I0 起 **恒 29 字符**（`app/services/kg/incremental.py::_next_version`） |
| 前端 | `npm ci` + `typecheck` + `lint` **本地可跑**（CI 内亦绿）；`api.d.ts` 是 `gen:api` 生成物，**禁止手改** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读；本文件成文时是 **run `37790726279` / commit `bbe4388d`** |

> ⚠️ **跑子集前先看 `changes/P5-I0/integration-log.md` §6.4**：有一条既有用例的断言是
> **全表计数**（`assert len(rows) == 1`），库里有任何残留都会让它红，
> 症状看起来像"最近的改动把它弄坏了"。**先回读库确认，别急着查自己的 diff。**

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **契约先行**（D3 取 A 时） | `openapi.yaml` 新增 `GET /api/v1/ontology/candidates` + `components.schemas`；`export_openapi.py --check` 零 diff |
| 2 | **后端候选端点**（D3 取 A 时） | 真 PG 用例：`status` 过滤生效、`org_id` 强制（**跨 org 读不到**） |
| 3 | **前端 API 模块** | `frontend/src/api/ontology.ts` 存在，类型**只**取 `components["schemas"]["Ontology*"]`；`mock/ontology.ts` 齐备 |
| 4 | **Mock 门禁同步**（D6） | `NEXT_PUBLIC_USE_MOCK=false` ⇒ `shouldMock("/api/v1/ontology/merge") === false`；`true` 时走 mock 且**不**发请求 |
| 5 | **三动作 UI 可用** | 能选到实体并发起 merge / split / rename；`typecheck` + `lint` + `build` 三连绿 |
| 6 | **动作成功可见新版本**（D5） | UI 显示响应回来的 `kg_version`，刷新图谱后能看到校正结果（改名 ⇒ 新名；合并 ⇒ 被并入侧消失） |
| 7 | **错误分支不静默** | 404 `ENTITY_NOT_FOUND` / 403（跨租户，**不是 404**）/ 409 `KG_VERSION_NOT_ACTIVE` 三条在 UI 上有可辨识反馈（不吞错、不假造成功） |
| 8 | **契约零漂移** | `export_openapi.py --check` 零 diff；CI 的 `gen:api` + `git diff --exit-code -- frontend/src/types/api.d.ts` 通过 |
| 9 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0；`check_seams.py` 仍 OK 12 |
| 10 | **pytest 不降** | CI **≥ 1139 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 11 | **spec §10.1.1 已更新** | 批次 B 改为已落地 + 仍缺什么；**编号未重排**（R5） |
| 12 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

- **GUI 能用 ≠ 读侧已完整**：剩余读路径与 `agents.py` 检索**仍单版本**，M4 端到端问答**仍未**吃到版本继承读。
- **GUI 能用 ≠ 多跳推理跨版本已通**：**P5H-6** 限制仍在。
- **候选列表端点 ≠ `human_review` 队列完备**：M2 的 S9.13-2 仍缺。
- **三动作可用 ≠ 冷启动建议可用**：`POST /ontology/cold-start` 属批次 A，本批**不接**它的 LLM 调用。
- **前端无 RBAC ≠ 后端没权限**：后端 `require_permission` 在跑；前端只是**没有**按角色隐藏入口的手段（本批不造）。
- **`CONTRACT_COVERED_PATTERNS` 追加了 ≠ 数据是真的**：没追加 ⇒ 关 Mock 时**静默走假数据**。
- **`gen:api` 绿 ≠ 契约对**：真源顺序是 `backend/app/core/openapi.py` → `export_openapi.py` → yaml → `api.d.ts`。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）⇒ **以 CI 为终裁**（R-10）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **本批动的是租户隔离相关路径的前端入口**（三端点都是 `org_id` 强制过滤键）：
  须带上 **ADR-0003 §4.1** 的两类测试 **T1 跨 org 越权**（G-9，`test_guardrails_graph.py` +
  `test_guardrails_rls.py`）与 **T2 并发串租户**（G-10，`tests/test_guardrails.py:328`）——
  **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only` 绕过**；它们**已有的断言不许放宽**；
  新增的候选端点**必须**显式断言跨 org 读不到。

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 **契约（架构师）/ 后端（B）/ 前端（A）/ docs** **分段** Conventional Commits，
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10）；CI 红了先看是不是批次摊太大，
**不许先改测试让它绿**。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §7 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | D3 判定「绑定候选表」要新增端点、但新增会触碰既有契约的某条约定；或 m6 §1.1 第 2 条的绑定口径被判定为要改正文 |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？（如：D3 取 B「手动选两个实体」并登记偏离）
3. 真不行了 —— **报告时带上**：哪份 spec / ADR 的哪一行、要加 / 改什么、为什么绕不过去、
   **你试过的替代方案**。不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **剩余读路径切换** + **`agents.py` 接线**（P5-H §9 指针 1）：M4 端到端才算真正吃到版本继承读。
2. **多跳推理改为 id 级图遍历**（取消 **P5H-6** 限制）。
3. **`GET /cost/dashboard` + `cost_metrics`**（m6 §3.4 验收 8 / 9）与 MVP 准入 **C3-a / C3-b**；
   `cost_ratio` 阈值 TBD-7 **Sprint 13** 收敛前拿不到判据。
4. **给 `kg_versions` 加 `parent_version` 列**（需迁移 + **G-6**）；**顺带**裁决
   `kg_versions.version` 与 `ontology_actions.kg_version` / `result_kg_version` **三列**的
   `String(64)` 上限 —— 若将来版本号要承载更多信息，这三列要一起动。
5. **概览三个统计值口径**（P5H-4）：有了 GUI 才有消费者，建议与本批的后续迭代同批裁。
6. **`human_review` 队列读端点**（M2 的 S9.13-2）。
7. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续六批**有意不做）。
8. **`ontology/confirm` / `cold-start` / `active` 仍是占位**（批次 A）：
   契约不会告诉你哪些端点是占位 —— 现在只有 `backend/app/core/openapi.py` 的 tag 描述会，
   ⇒ 实现它们之前**先看那一段**。
9. **`test_kg_build_executor.py::test_kg_build_reuses_existing_kg_version_row` 的
   `assert len(rows) == 1`**（P5-I0 §6.4）：全表计数断言容易被残留击穿 ⇒ 改成"只数与本用例有关的行"。
   **纯健壮性，建议并入任一批次顺手做，不单独开工**。
10. **`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`**（m6 §6 另两个配置项）：
    在对应批次回填，**别顺手补齐**。
11. **日志 `message` 正文的脱敏**：逐个把 `mask()` 补到写敏感值的日志语句上。
