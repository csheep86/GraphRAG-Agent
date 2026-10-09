# P5-I · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（**10 条** Non-goals，逐条对照）
> **执行模式**：无人值守，逐任务验证通过即提交；**跨角色三段各自单独提交**
> **起点**：`main` = `cf2fab9e`（CI run `37791505100` 四 job 全绿，2026-10-09 开工实测）
> **开工自检实测**：`check_startup_readiness.py` = `[OK]` **17** / `[~~]` 0 / `[--]` 0；
> `check_seams.py` = ERROR 0 / WARN 0 / **OK 12**；`export_openapi.py --check` 零 diff（**28 路径**）；
> 本地 `pytest`（带真图三开关）= **1138 passed / 4 skipped / 2 failed**（2 条 failed = 本地既有环境债 g25，CI 上绿）；
> 前端 `npm run typecheck` + `npm run lint` 绿（`npm ci` 被本机 safe-delete 拦截 ⇒ 用 `npm install` 恢复依赖）

---

## T1 · 契约段（**架构师**）—— 单独一笔提交

- [ ] `backend/app/core/openapi.py` 的 `ontology` tag 描述（**契约描述真源**，不是 `openapi.yaml`）：
  - [ ] 追加「**候选读端点** `GET /ontology/candidates`（本批新增，绑定 `entity_merge_candidates`）」
  - [ ] 保留「`active` / `confirm` / `cold-start` 仍是占位」的事实陈述（**不许**写成已实现）
- [ ] `backend/app/schemas/ontology.py`（Pydantic = 契约字段真源）：
  - [ ] 新增 `OntologyCandidate`：`id` / `left_entity_id` / `right_entity_id` / `similarity` /
        `status`（5 值 Literal）/ `signals`（`dict | None`，P5I-5）/ `created_at`
  - [ ] 新增 `OntologyCandidateListResponse`：`total` / `items` / `page` / `page_size`
        **不带 `trace_id`**（P5I-2：spec §5.5 只有 cold-start 列了它）
  - [ ] docstring 写明：字段投影自 `entity_merge_candidates`（M2 §4.5），`status` 五值取自模型 CHECK 约束
- [ ] `uv run python scripts/export_openapi.py` ⇒ 此时**无路径变化**（模型未被引用不进 yaml）；`--check` 零 diff
- [ ] `cd frontend && npm run gen:api` ⇒ `src/types/api.d.ts` 预期零变更（同上）

## T2 · 后端段（**后端开发 B**）—— 单独一笔提交

- [ ] `backend/app/services/ontology.py`：新增 `list_merge_candidates(...)`
  - [ ] `org_id` **强制**取自认证态（ADR-0003 §3.3）；跨租户 ⇒ 空集（P5I-1）
  - [ ] `status` 过滤：非法值 **400 `VALIDATION_ERROR`**（**不**静默当全量，与 `services/audit.py` 同口径）
  - [ ] 分页：`page` 1-based / `page_size` 默认 50、上限 100（与 `GET /audit` 同口径，不另造口径）
  - [ ] 排序 `created_at DESC`
- [ ] `backend/app/api/v1/routes/ontology.py`：
  - [ ] 新增 `GET /candidates`（`operation_id="listOntologyCandidates"`）
  - [ ] `dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_READ)]`
  - [ ] `responses={**TENANT_ERROR_RESPONSES, **VALIDATION_ERROR}`
  - [ ] ⚠️ merge / split / rename **主流程一行不改**（Non-goal 1）
- [ ] 登记三处（漏一处 CI 必红）：
  - [ ] `app/services/rbac/policy.py::CONTRACT_PATH_RESOURCE` 加 `/api/v1/ontology/candidates`
        （`test_rbac.py::test_contract_paths_are_all_registered` 双向锁）
  - [ ] `backend/tests/test_rbac.py::PROTECTED_ENDPOINTS` 加 `"/ontology/candidates": "GET"`（**9 ⇒ 10 条**）
  - [ ] `app/services/audit.py::ACTION_BY_ROUTE_NAME` 加 `"list_ontology_candidates": "ontology.candidates"`
- [ ] `uv run python scripts/export_openapi.py` ⇒ **路径 28 ⇒ 29**；`--check` 零 diff
- [ ] 测试 `backend/tests/test_ontology_candidates.py`（**真 PG**，不标 `local_only`）：
  - [ ] A org 造 3 行（`human_review` ×2 / `applied` ×1）+ B org 造 1 行
  - [ ] 判据：`status=human_review` 过滤生效（只回 2 行）、`total` / `page_size` 回显正确
  - [ ] 判据：B org 身份 ⇒ **看不到 A org 的行**（`items` 里不含 A 的行，且只含自己的行）
  - [ ] 判据：非法 `status` ⇒ **400**
  - [ ] 清理：`finally` 按 `id` 精确删除（不留残留 —— P5-I0 §6.4 的全表计数教训）
- [ ] `uv run ruff check .` + `uv run ruff format .`
- [ ] 跑 `test_ontology_candidates.py` + `test_rbac.py` + `test_ontology_correction_actions.py` 子集

## T3 · 前端段（**前端开发 A**）—— 单独一笔提交

- [ ] `cd frontend && npm run gen:api` ⇒ `src/types/api.d.ts` 应**新增** `OntologyCandidate*` 类型（**禁止手改**）
- [ ] `src/api/client.ts`：`CONTRACT_COVERED_PATTERNS` 追加 4 条
      （`/api/v1/ontology/candidates` / `/merge` / `/rename` / `/split`，**19 ⇒ 23**）—— D6 硬要求
- [ ] `src/api/ontology.ts`：`listMergeCandidates` / `mergeEntities` / `splitEntity` / `renameEntity`；
      类型**只**取 `components["schemas"]["Ontology*"]`
- [ ] `src/api/mock/ontology.ts`：`MOCK_MERGE_CANDIDATES`（只在 `shouldMock()` 为真时命中）
- [ ] `src/store/use-ontology-store.ts`：候选列表 + `statusFilter` + `submitting` + `error` +
      `lastKgVersion`；动作成功后 `await useGraphStore.getState().load()`（D5 = A）
- [ ] `src/components/ontology/candidate-table.tsx` + `correction-dialog.tsx`
      （Radix + cva + tailwind-merge 自研 UI；中文硬编码；**不用 antd / 不做 i18n**）
- [ ] `src/app/ontology/page.tsx`：`PageShell` + `PageHeader` + 工具栏 + 候选表 + 弹窗 + 版本回显条
- [ ] `src/lib/nav.ts`：`workspaceNav` 加 `{ label: "本体校正", href: "/ontology", icon: Split }`
- [ ] 错误分支（判据 7）：`ApiError.status` 403 / 404 / 409 分别给可辨识中文反馈，**不吞错、不假造成功**
- [ ] `npm run typecheck` + `npm run lint` + `npm run build` 三连绿

## T4 · docs 段（**架构师**）—— 单独一笔提交

- [ ] `specs/m6-ontology-incremental.md` **§10.1.1 落地状态表**：
  - [ ] 第 2 行：补「候选读端点 `GET /ontology/candidates`（P5-I）」
  - [ ] **新增**「批次 B（本体校正 GUI）**已落地**（P5-I）」+ 仍缺什么
        （`active` / `confirm` / `cold-start` 仍占位；冷启动 LLM 未接；`min_length=2` 已随 GUI 复核）
  - [ ] ⚠️ **编号不重排、不覆盖原文**（R5 / Non-goal 10）
- [ ] `docs/acceptance-traceability-matrix.md` M6 行：追加 P5-I 状态与仍缺项
- [ ] `changes/P5-I/integration-log.md`：决策 D3 / D4 / D5 / D6 的裁决与理由、12 条判据的机器输出、CI run id

## T5 · 门禁与收口

- [ ] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [ ] `check_seams.py` 仍 ERROR 0 / WARN 0 / **OK 12**
- [ ] `check_session_drift.py`：S1 应读到**本批 10 条** Non-goals；S5 对本批新增模块给出归属回答
- [ ] **隔离红线**：G-9 T1（跨 org 越权）/ G-10 T2（并发串租户）全绿且**断言未放宽**
      （`test_guardrails_graph.py` + `test_guardrails_rls.py` + `test_guardrails.py:328`）
- [ ] 本地 `pytest`（带 `GRAPH_REAL_NEO4J_*` 三开关）⇒ 不应低于 1138 passed / 4 skipped / 2 failed（本地口径）
- [ ] 分段提交 + 推送 + **CI 四 job 全绿**（`gh run watch <id> --exit-status` 退出码 0）
- [ ] 收口：按 `new-session-prompt.md` §11 的**实际结果**更新下一批指针（落成 `changes/P5-J/new-session-prompt.md`）
