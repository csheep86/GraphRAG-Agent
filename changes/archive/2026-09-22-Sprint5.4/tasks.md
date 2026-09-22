# Sprint 5 批次 C · tasks

> 收口纪律（沿用 A2/B）：每勾一项必须跑对应门禁；commit 信息走 Conventional Commits。

## 0. 起点门禁（确认基线）

- [x] **T0.1** 确认 `feature/sprint-5` 分支 / working tree clean / 基线 `264fe52`
- [x] **T0.2** 跑四道门禁基线：`ruff check` / `ruff format --check` / `pytest` 226 / `check_seams` ERROR 0 / `export_openapi --check` 全绿

## 1. 脚手架：目录、目录结构

- [ ] **T1.1** 新建 `backend/app/api/v1/routes/graph.py`（图谱概览 + 实体详情两个端点）
- [ ] **T1.2** `backend/app/api/v1/router.py` 引入 `graph` 子路由并 `include_router`
- [ ] **T1.3** `backend/app/api/v1/responses.py` 新增共享错误响应常量 `VALIDATION_ERROR`（已有）+ 必要时扩 `KG_VERSION_NOT_ACTIVE` 复用

## 2. Pydantic schemas（契约唯一真源）

- [ ] **T2.1** `backend/app/schemas/document.py` 新增：
  - `DocumentListItem`：字段对齐 `frontend/src/types/mock.d.ts::DocumentListItem`（id / filename / file_type / status / entity_count / uploaded_at / time_label / task_id / trace_id）
  - `DocumentListResponse`：含 `total` / `items` / `page` / `page_size`
  - `DocumentFileType` 复用 Literal（PDF / DOCX / CSV）
- [ ] **T2.2** 新建 `backend/app/schemas/graph.py`：
  - `GraphOverviewResponse`：doc_count / entity_count / relation_count / kg_version / nodes / edges / truncated
  - `GraphOverviewNode` / `GraphOverviewEdge`（与 `GraphNode` / `GraphEdge` 区分：前者含 `seed_x` / `seed_y` / `weight`，后者仅实体投影）
  - `EntityDetail`：id / canonical_name / entity_type / confidence / kg_version / relation_count / attributes / relations
  - `EntityAttribute` / `EntityRelation`（label / value；relation / target_id / target_name）
- [ ] **T2.3** `backend/app/schemas/__init__.py` 导出新模型
- [ ] **T2.4** 验证：`ruff check .` / `ruff format --check .` / `pytest` 全绿（schema 引入但尚未接入路由）

## 3. Service 层

- [ ] **T3.1** `backend/app/services/documents.py` 新增：
  - `list_documents(*, session, identity, query: DocumentListQuery) -> DocumentListResponse`
  - 内部辅助 `_match_filename_hash(query)`：按 `filename_hash` LIKE 前缀匹配
  - `_paginate(items, page, page_size)`：纯 Python 切片（避免 SQL OFFSET 大表性能问题，留 v1.5+ 再优化）
- [ ] **T3.2** `backend/app/services/graphs.py` 新增：
  - `fetch_graph_overview(*, org_id, node_limit=500)`：复用 `fetch_all_subgraph()` + 统计 doc_count
  - `fetch_entity_detail(*, entity_id, kg_version, org_id)`：Cypher 单节点 + 出边邻居查询
  - `_QUERY_ENTITY_NODE` / `_QUERY_ENTITY_NEIGHBORS` Cypher 常量
- [ ] **T3.3** 验证：service 层新增的函数可被 import；pyflakes 无 unused（schema 引入后）

## 4. 路由层

- [ ] **T4.1** `backend/app/api/v1/routes/documents.py` 新增 `GET /`：
  - query 参数 `q`（可选）/ `status`（可选 Literal）/ `page`（默认 1）/ `page_size`（默认 10，max 100）
  - 调用 `list_documents()`，响应 `DocumentListResponse`
  - 错误响应：`TENANT_ERROR_RESPONSES` + `VALIDATION_ERROR`
- [ ] **T4.2** `backend/app/api/v1/routes/graph.py`：
  - `GET /overview`：调用 `fetch_graph_overview()`，响应 `GraphOverviewResponse`
  - `GET /entities/{entity_id}`：调用 `fetch_entity_detail()`；不存在 → 404 `ENTITY_NOT_FOUND`、跨租户 → 403 `FORBIDDEN`
  - 错误响应：`TENANT_ERROR_RESPONSES` + `NOT_IMPLEMENTED`
- [ ] **T4.3** `backend/app/core/errors.py` 新增错误码 `ENTITY_NOT_FOUND`（404）+ `DEFAULT_MESSAGES` / `ERROR_HTTP_STATUS` / `ERROR_CODE_DESCRIPTIONS` / `ERROR_CODE_SOURCES` 同步登记
- [ ] **T4.4** `backend/app/api/v1/responses.py` 新增 `ENTITY_NOT_FOUND` 响应模板
- [ ] **T4.5** `backend/app/api/v1/router.py` include `graph.router`（prefix `/graph`，tags `["graph"]`）
- [ ] **T4.6** 验证：`ruff check .` / `pytest` 全绿（routes 已注册，OpenAPI 会自动生成新路径——重导出契约后再核对）

## 5. 测试

- [ ] **T5.1** `backend/tests/test_documents_list.py`（新增 ≥3 例）：
  - `test_list_returns_only_current_org_documents`：上传 2 条同租户 + 跨租户 1 条，列表仅返回 2 条
  - `test_list_filter_by_status`：上传混合 status，filter 生效
  - `test_list_pagination`：page=2 返回正确切片
  - `test_list_q_prefix_match`：filename_hash 前缀匹配（hash 是 SHA-256 hex，固定前缀）
- [ ] **T5.2** `backend/tests/test_graph_routes.py`（新增 ≥3 例）：
  - `test_graph_overview_returns_501_when_neo4j_unavailable`：现状默认 Neo4j 不可达
  - `test_entity_detail_returns_404_when_not_found`：monkeypatch `fetch_entity_detail` 抛 `EntityNotFoundError`
  - `test_entity_detail_returns_200_with_payload`：monkeypatch 返回 fixture
- [ ] **T5.3** 验证：`pytest -q` ≥ 232 passed

## 6. 契约导出

- [ ] **T6.1** `cd backend && uv run python scripts/export_openapi.py` 生成新契约
- [ ] **T6.2** `uv run python scripts/export_openapi.py --check` 复核无 diff
- [ ] **T6.3** 核对契约内 `paths`：新增 3 条（`/api/v1/documents` / `/api/v1/graph/overview` / `/api/v1/entities/{entity_id}`），`components.schemas` 含 DocumentListItem / DocumentListResponse / GraphOverviewResponse / GraphOverviewNode / GraphOverviewEdge / EntityDetail / EntityAttribute / EntityRelation / EntityFileType 9 个新 schema + 1 个新错误码（`ENTITY_NOT_FOUND`）

## 7. 接缝门禁

- [ ] **T7.1** `uv run python scripts/check_seams.py` ERROR 仍为 0（无新接缝登记）
- [ ] **T7.2** 核对 §V-VII：docs/release-notes/v1.1.0.md 涉及接缝的段落（无新增）
- [ ] **T7.3** ADR-0004 §2.1 登记集合 = 本批实现集合（无新增，故无需动 ADR）

## 8. 前端类型同步

- [ ] **T8.1** `cd frontend && npm run gen:api`（生成 `src/types/api.d.ts`）
- [ ] **T8.2** 核对 `src/types/api.d.ts` 含 9 个新 schema + `ENTITY_NOT_FOUND` 错误码
- [ ] **T8.3** `git diff` 确认仅 `src/types/api.d.ts` + `contracts/openapi.yaml` 漂移

## 9. 前端 mock 收口

- [ ] **T9.1** `frontend/src/api/client.ts` `CONTRACT_COVERED_PATTERNS` 增 3 条：
  - `/^\/api\/v1\/documents$/`
  - `/^\/api\/v1\/graph\/overview$/`
  - `/^\/api\/v1\/entities\/[^/]+$/`
- [ ] **T9.2** `frontend/src/types/mock.d.ts` 删除 `DocumentListItem` / `DocumentListResponse` / `DocumentListQuery` / `GraphOverviewResponse` / `GraphOverviewNode` / `GraphOverviewEdge` / `GraphCategory` / `EntityDetail` / `EntityAttribute` / `EntityRelation`（全部从契约引入）；保留 `ChatSession` / `ChatMessage` / `QaHistoryItem` / `MetricOverview`（仍为 mock-only）等
- [ ] **T9.3** `frontend/src/api/documents.ts`：
  - `listDocuments()` 改用 `components["schemas"]["DocumentListResponse"]` 返回类型
  - URL 参数与契约对齐（`q` / `status` / `page` / `page_size`）
- [ ] **T9.4** `frontend/src/api/graph.ts`：
  - `getGraphOverview()` 改用 `components["schemas"]["GraphOverviewResponse"]`
  - `getEntityDetail()` 改用 `components["schemas"]["EntityDetail"]`
- [ ] **T9.5** `frontend/src/api/mock/documents.ts` 删除 `MOCK_DOCUMENTS` / `MOCK_DOCUMENT_TOTAL` / `MOCK_RECENT_DOCUMENTS`（不再 mock）；保留 `MOCK_DOCUMENT_STATUS`（仍供 upload → status mock 链路）
- [ ] **T9.6** `frontend/src/api/mock/graph.ts` 删除 `MOCK_GRAPH_OVERVIEW` / `MOCK_DEFAULT_ENTITY_ID` / `getMockEntityDetail()` / `MOCK_DOCUMENT_GRAPH`；保留或精简为只服务于文档级 `getDocumentGraph`（mock 仍可走，因旧契约 `MOCK_DOCUMENT_GRAPH` 不影响）
- [ ] **T9.7** 验证：`npm run lint` / `npm run typecheck` / `npm run gen:api`（再跑一次确认无新漂移）

## 10. 收尾四道门禁 + commit

- [ ] **T10.1** `cd backend && uv run ruff check . && uv run ruff format --check .` → 全过
- [ ] **T10.2** `cd backend && uv run pytest -q` → ≥ 232 passed
- [ ] **T10.3** `cd backend && uv run python scripts/check_seams.py` → ERROR 0
- [ ] **T10.4** `cd backend && uv run python scripts/export_openapi.py --check` → 无 diff
- [ ] **T10.5** `cd frontend && npm run lint` → 全过
- [ ] **T10.6** `cd frontend && npm run typecheck` → 全过
- [ ] **T10.7** `cd frontend && npm run gen:api` → 无 diff（仅 `src/types/api.d.ts` 已生成，无需再改）
- [ ] **T10.8** 提交：
  - `feat(api): GET /documents list + GET /graph/overview + GET /entities/{id}`
  - `feat(frontend): wire real list + overview + entity detail; drop corresponding mocks`
  - `chore(sprint5.4): integration log + release notes v1.1.0`
- [ ] **T10.9** `docs/release-notes/v1.1.0.md` 写明"演示页零假数据 + 已知限制"（如 Neo4j 不可达时 overview 501）

## 11. dev.db 处理

- [ ] **T11.1** 删除 `backend/dev.db`（若存在）；下次 `uv run app.main` 启动 lifespan 时 `Base.metadata.create_all` 会自动建 `kg_versions` 表 + `documents` 5 列（沿用 A2/B 已有处理口径）
- [ ] **T11.2** `integration-log.md` §3 登记存量库重建说明