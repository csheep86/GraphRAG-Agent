# P5-I · 集成实录（M6 批次 B：**本体校正 GUI**）

> **日期**：2026-10-09　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：`main` = `cf2fab9e`（CI run `37791505100` 四 job 全绿）
> **边界**：[`proposal.md`](./proposal.md) §3（10 条 Non-goals，逐条对照）
> **角色隔离**：契约（`7fbe8881`）→ 后端（`8142ecc6`）→ 契约测试登记（`4d50fd1`）→ 前端（`733a88cc`）→ docs
> **花销**：¥0（本批未接 `cold-start` 的 LLM 调用）

---

## 1. 决策裁决（**D3 / D4 / D5 / D6 四条为必答，先裁决后动手**）

| # | 裁决 | 理由 / 证据 |
|---|---|---|
| **D1** | ✅ 主题 = **M6 批次 B：本体校正 GUI（三动作）** | 四批次里唯一「前置已清 + 排期已到」：D 被 TBD-7 挡着 |
| **D2** | ✅ **不新增配置** | 无 `settings.*` 新增；`check_seams.py` 仍 **OK 12** |
| **D3** ⚠️ | ✅ **取 A**：新增 `GET /api/v1/ontology/candidates` | spec §1.1 第 2 条要求 GUI 与 `entity_merge_candidates` **绑定**。契约原 28 条 path 中**无**候选读端点（该表只在 merge 的描述里作为被 `human_review → applied` 更新的表出现）。取 A 才兑现绑定；B 要登记偏离；C 拿不到置信度 / 判分信号等候选元数据。**已走契约先行五步** |
| **D4** ⚠️ | ✅ **取 A**：新增路由 `/ontology` + 三动作弹窗 + 侧栏一项 | 取 B 要先打通 `GraphCanvas` 选中态与校正弹窗（另一条改动链），本批不摊 |
| **D5** ⚠️ | ✅ **取 A**：回显 `kg_version` + **真的**刷新图谱视图 | 只弹 Toast（B）则 spec §5.1 第 3 条在 UI 上证不到。实现：动作成功后 `await useGraphStore.getState().load()` ⇒ `GET /graph/overview`（**已切版本继承读** ⇒ 刷新后是完整图谱） |
| **D6** ⚠️ | ✅ **追加 4 条 pattern**（**19 ⇒ 23**） | 漏登记的后果**不是报错**而是**静默走假数据**：`USE_MOCK=false` 时点三动作打到本地 mock，页面显示"成功"而图谱一行没变。已机械验证（§3 判据 4） |
| **D7** | split 只填**名称列表（≥2）** | `OntologyNewEntity` 只有 `canonical_name`；前端**不**假造关系信息（P5G-3） |
| **D8** | 显示 `kg_version` | 自 P5-I0 起恒 29 字符，无溢出 / 截断问题；**不**从字符串推断父子（真源 `ontology_actions`，ADR-0008 §3） |
| **D9** | 不新增审计点 | M5 中间件全覆盖；仅在 `ACTION_BY_ROUTE_NAME` 登记 `ontology.candidates`（否则回落 `http.get.<path>` 并打 WARNING） |
| **D10** | 契约**会动** | 路径 **28 ⇒ 29**，新增 `OntologyCandidate` / `OntologyCandidateListResponse` |
| **D11** | **¥0** | 不接 `cold-start` 的 LLM 调用 |

## 2. 决策补充登记（proposal §5）

- **P5I-1** 候选端点跨租户 ⇒ **空集**（不是 403）：列表类端点泄露不了单条资源存在性；403 会让「队列为空」与「无权访问」在 UI 上无法区分。与 `GET /audit/trace/{id}` 同口径。
- **P5I-2** 候选响应**不带 `trace_id`**：spec §5.5 只有 `cold-start` 列了它 ⇒ 冲突时以 spec 为准。
- **P5I-3** 前端**不做**角色判断：只把 403 显示成「被拒绝（403 …）」。
- **P5I-4** 实体**只从候选行选**：不另造实体搜索端点（超出 D3 那一条）。
- **P5I-5** `signals` 进契约（可空），UI 只在 hover 里回显判分依据，不做渲染面板。

## 3. 登记点（**四处**，漏一处 CI 必红）

| # | 位置 | 变化 |
|---|---|---|
| 1 | `app/services/rbac/policy.py::CONTRACT_PATH_RESOURCE` | 加 `/api/v1/ontology/candidates`（`test_contract_paths_are_all_registered` 双向锁） |
| 2 | `backend/tests/test_rbac.py::PROTECTED_ENDPOINTS` | **9 ⇒ 10** |
| 3 | `backend/tests/test_openapi_contract.py` | `CORE_PATHS` 加一条 + `operation_ids` 计数 **28 ⇒ 29** |
| 4 | `app/services/audit.py::ACTION_BY_ROUTE_NAME` | 加 `"list_ontology_candidates": "ontology.candidates"` |

> ⚠️ **第 3 处是跑全量 pytest 才暴露的**（子集测试不会红）：第一次全量跑出
> `test_core_paths_match_contract` / `test_operation_ids_are_unique` 两条红。
> 这是**必改登记项**，不是放宽断言 —— 记此一笔，免得下批再漏。

## 4. 验收判据的机器输出（**12 条**）

| # | 判据 | 机器输出 |
|---|---|---|
| 1 | 契约先行 | `export_openapi.py --check` → `[OK] …与后端模型一致`；yaml 顶层路径数 **29**（`Select-String "^  /api/v1/" \| Measure-Object` = 29） |
| 2 | 后端候选端点（真 PG） | `uv run pytest tests/test_ontology_candidates.py -q` → **4 passed**：`status` 过滤生效（回来的行全是 `human_review` 且是本用例 id 的子集）、跨 org 读不到（B 看得到自己的、看不到 A 的）、非法 `status` → 400 `VALIDATION_ERROR`、无身份 → 403 |
| 3 | 前端 API 模块 | `frontend/src/api/ontology.ts` + `mock/ontology.ts` 齐备，类型只取 `components["schemas"]["Ontology*"]`；`tsc --noEmit` 通过 |
| 4 | Mock 门禁同步（D6） | 编译 `client.ts` 后以 `NEXT_PUBLIC_USE_MOCK=false` 实跑：`shouldMock` 对 `candidates` / `merge` / `rename` / `split` 均为 **false**，对契约外 `/api/v1/ontology/confirm` 为 **true**（设计如此） |
| 5 | 三动作 UI 可用 | `npm run typecheck` ✅ / `npm run lint` ✅ / `npm run build` ✅（路由表含 `○ /ontology`） |
| 6 | 动作成功可见新版本 | 成功后页面显示响应回来的 `kg_version`，并 `await useGraphStore.load()`（真请求 `GET /graph/overview`）+ 重载候选列表（合并后该行 `human_review → applied` ⇒ 从当前筛选消失） |
| 7 | 错误分支不静默 | `use-ontology-store.ts::describeActionError` 按 `ApiError.status` 分档：403（跨租户 / 无权限，**不是 404**）/ 404 `ENTITY_NOT_FOUND` / 409 `KG_VERSION_NOT_ACTIVE` / 400，弹窗内 `role="alert"` 显示，**不**假造成功 |
| 8 | 契约零漂移 | `export_openapi.py --check` 零 diff；`npm run gen:api` 后 `src/types/api.d.ts` 随契约更新（新增 `OntologyCandidate*`），CI 的 `git diff --exit-code -- frontend/src/types/api.d.ts` 由 CI 终裁 |
| 9 | 护栏不倒退 | `check_startup_readiness.py` → **`[OK]` 17 / `[~~]` 0 / `[--]` 0**；`check_seams.py` → **ERROR 0 / WARN 0 / OK 12** |
| 10 | pytest 不降 | 本地全量（带真图三开关）**1143 passed / 4 skipped / 2 failed**（2 条 failed = 本地既有环境债 `test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty` 与 `test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，CI 上有受控种子语料 ⇒ 绿）；比基线 1138 passed **+5**（4 条新候选用例 + 1 条 RBAC 参数化用例自动派生） |
| 11 | spec §10.1.1 已更新 | 追加「2026-10-09（P5-I）」两行（批次 B 已落地 / 仍缺什么），**编号未重排、原文未覆盖**（R5）；矩阵 M6 行同步追加 P5-I 段落 |
| 12 | CI 四 job 全绿 | 见 §6（**回登**） |

## 5. 隔离红线（ADR-0003 §4.1，**本批动的是租户隔离相关路径的前端入口**）

- 跑 `tests/test_guardrails.py` + `test_guardrails_graph.py` + `test_guardrails_rls.py`
  + `test_rbac.py` + `test_ontology_correction_actions.py` + `test_ontology_placeholder_endpoints.py`
  ⇒ **108 passed**；既有断言**一条未放宽**。
- **T1 跨 org 越权**（G-9）与 **T2 并发串租户**（G-10）在 **PostgreSQL** 上执行、纳入 CI 必过项、
  **未标 `local_only`**。
- 新增端点的跨租户断言写在 `test_ontology_candidates.py::test_other_org_rows_are_invisible_to_current_tenant`：
  不只断言「B 看不到 A」，还断言「B **看得到自己的**」——否则一个恒返回空集的端点也能过。

## 6. 过程中回切点（`check_session_drift.py`）

- **S1** 读到本批 **10 条** Non-goals ✅（不是「没有边界」）
- **S2** 2 个文件 / 11 行（docs 段改动，远低于阈值）✅
- **S3** 无新增 `Settings` 字段 ⇒ 无需同步 `.env.example` ✅
- **S5** 无新增孤立模块 ✅

三句自答：

1. **有没有顺手做的？** —— 没有。四处登记 + 契约测试计数都是**新增端点的必改项**；
   `ACTION_BY_ROUTE_NAME` 那条是防中间件回落打 WARNING，同属端点自带接线。
2. **有没有为躲坑而绕路？** —— 没有。两处绕路都被拦下并正面处理：
   ① lint 规则 `react-hooks/set-state-in-effect` 禁止在 effect 里 setState ⇒
   改为给表单组件加 `key`（动作 + 候选 id）整体重挂载，而不是加 eslint-disable；
   ② `npm ci` 被本机 safe-delete 策略拦截（850 文件 > 500 阈值）⇒
   用 `npm install` 恢复依赖后 `typecheck` / `lint` 才可信（**没有**跳过这步）。
3. **验收判据是真跑出来的吗？** —— 是：全部来自脚本 / CI 输出（§4 第 4 条是编译后实跑
   `shouldMock()`，不是读代码推断）。

## 7. CI 终裁（回登）

> 待推送后回登：`gh run watch <id> --exit-status` 退出码 0，四 job 全绿。
