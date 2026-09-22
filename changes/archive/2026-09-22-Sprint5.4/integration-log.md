# Sprint 5 批次 C 集成日志

## 批次定位

**目标**：把前端用 mock 数据兜底的三处功能对齐到后端实装契约，补齐 3 个端点 + 收口 mock 兜底：

| 端点 | 路径 | 用途 |
| --- | --- | --- |
| 文档列表 | `GET /api/v1/documents` | p02 文档管理表格 |
| 全局图谱概览 | `GET /api/v1/graph/overview` | p04 知识图谱力导向图 |
| 实体详情 | `GET /api/v1/entities/{entity_id}` | p04 实体详情面板 |

## 契约变更

新增 Pydantic 模型：

- `DocumentFileType`（`Literal["PDF", "DOCX", "CSV"]`）
- `DocumentListItem` / `DocumentListResponse`
- `GraphCategory`（`Literal["topic", "norm", "org", "system"]`）
- `GraphOverviewNode` / `GraphOverviewEdge` / `GraphOverviewResponse`
- `EntityAttribute` / `EntityRelation` / `EntityDetail`

新增错误码：`ENTITY_NOT_FOUND`（404），对齐文档级 `DOCUMENT_NOT_FOUND` 的语义层级。

新增查询参数 schema：

- `GET /documents`：`q`（filename_hash 前缀，hex）、`status`、`page`、`page_size`

## 后端变更

### 新增 service

- `app/services/documents.py::list_documents()`
  - 强制 `org_id` 过滤（ADR-0003）；
  - `q` → `filename_hash LIKE 'q%'`（hex 前缀匹配）；
  - Python 切片分页（演示量级 < 1000，**不**用 SQL OFFSET）；
  - 一次性批量查 `(kg_version_id → entity_count)` 映射，避免 N+1；
  - 时间文案由后端语义直接给出（`HH:MM` / `昨天 HH:MM` / `MM-DD HH:MM`），避免 SSR/CSR 时区差。

- `app/services/graphs.py::fetch_graph_overview()`
  - 全局实体节点轻量投影 + 边投影；
  - 统计值（doc_count / entity_count / relation_count）复用 PG 真源（批次 B 起 PG 为唯一真源，Neo4j `:KgVersion` 降级为冗余镜像）；
  - 节点上限 500，超限 `truncated = true`（与 `DocumentGraphResponse` 对齐）。

- `app/services/graphs.py::fetch_entity_detail()`
  - 单节点 + 1 跳出边邻居（上限 50）；
  - 实体不存在 → `EntityNotFoundError`（继承 `GraphUnavailableError`，路由层转 404）；
  - **属性过滤**：剥离 `id` / `kg_version` / `org_id` / `pii_flags` / `canonical_name` / `type` / `confidence` 等已在契约字段中显式携带的字段，避免在 attributes 面板重复展示。

新增异常：

- `EntityNotFoundError`：刻意继承 `GraphUnavailableError`，路由层转 404 ENTITY_NOT_FOUND；与跨租户 403 语义严格分离。

### 新增路由

- `app/api/v1/routes/graph.py`（新文件）：`/graph/overview` + `/entities/{entity_id}` 两个端点；与 `routes/documents.py` 同源 `GraphService.instance()`，**不**创建新单例。

- `routes/documents.py::list_documents_endpoint`：新增 `GET /documents`，FastAPI Query 做字段类型 + 范围校验（`page >= 1`, `page_size <= 100`），`status` 枚举值手工校验（FastAPI Query 不支持 `Literal` 自动校验）。

### `router.py` 收口：5 路径 → 8 路径

```diff
- CORE_PATHS = { /health, /documents/upload, /documents/{id}/status, /documents/{id}/graph, /agent/query } (5)
+ CORE_PATHS = { /health, /documents, /documents/upload, /documents/{id}/status,
+                /documents/{id}/graph, /graph/overview, /entities/{id}, /agent/query } (8)
```

## 前端变更

### 类型收口

- `src/types/api.d.ts`：`npm run gen:api` 重新生成（含 `ENTITY_NOT_FOUND` 错误码 + 3 个新端点）。

- `src/types/mock.d.ts`：
  - 同名契约类型改为 `components["schemas"]` 别名引用（**删除手写复刻**）：
    - `DocumentFileType` / `DocumentListItem` / `DocumentListResponse`
    - `GraphCategory` / `GraphOverviewNode` / `GraphOverviewEdge` / `GraphOverviewResponse`
    - `EntityAttribute` / `EntityRelation` / `EntityDetail`
  - 仍为 mock 的预留类型：`MetricOverview` / `QaHistoryItem` / `ChatSession` / `ChatMessage` 等。

### API 客户端收口

- `src/api/client.ts`：`CONTRACT_COVERED_PATTERNS` 增补 3 条正则：
  - `^\/api\/v1\/documents$`
  - `^\/api\/v1\/graph\/overview$`
  - `^\/api\/v1\/entities\/[^/]+$`

- `src/api/documents.ts`：
  - `listDocuments` 改用 `q` 字段（与后端一致）；
  - URL 拼接补 `page` / `page_size`；
  - mock 分支也按契约返回 `page` / `page_size` / `trace_id`。

- `src/api/graph.ts`：
  - `getEntityDetail` 改为「找不到则抛 404」（契约语义）；mock 同步抛 `ENTITY_NOT_FOUND`；
  - `getGraphOverview` / `getEntityDetail` 文档注释从「契约缺失，需后端补」改为「✅ 契约已实装」。

### Mock 数据形态对齐契约

- `src/api/mock/documents.ts`：
  - `id` / `task_id` 改为合法 UUID 格式；
  - `filename` 改为伪造 SHA-256 hex（64 字符），**不**回显原文「M5 §4.5 禁文件名原文」；
  - `uploaded_at` 改为合法 ISO8601 datetime；
  - mock 返回结构补 `page` / `page_size` / `trace_id`。

- `src/api/mock/graph.ts`：
  - `GraphOverviewResponse` 增 `kg_version` / `truncated` / `trace_id`；
  - `EntityDetail` 字段名收敛到契约：`name` → `canonical_name`，`tag` → `entity_type`，删除 `display_code`（前端改用 `id` 展示）。

### 组件层适配

- `src/store/use-document-store.ts`：`listDocuments({ keyword })` → `listDocuments({ q: keyword })`（内部 state 名 `keyword` 保留，与 UI 控件对齐）。

- `src/store/use-graph-store.ts`：
  - `getEntityDetail` 失败路径加 `detailError: string | null`，与契约 4 类错误（`ENTITY_NOT_FOUND` / `FORBIDDEN` / `NOT_IMPLEMENTED` / 其它）一一映射；
  - 竞态保护保留（仅当 `selectedId` 未切换时写入 detail）。

- `src/components/graph/entity-detail-panel.tsx`：
  - `detail.name` → `detail.canonical_name`；
  - `detail.tag` → `detail.entity_type`；
  - `{detail.display_code} 关联 {N} 个节点` → `{detail.id} · 关联 {N} 个节点`；
  - 新增 `detailError` 三段分支空态文案。

## 测试覆盖

### 后端新增（18 例）

- `tests/test_documents_list.py`（8 例）：
  - 跨租户隔离（ADR-0003 回归）；
  - 空表 / status 过滤 / q 前缀匹配 / 分页 / 字段集断言；
  - 非法 status / 超限 page_size → 400 VALIDATION_ERROR；
  - 未认证 → 401 UNAUTHORIZED。

- `tests/test_graph_overview_and_entity.py`（10 例）：
  - `GET /graph/overview`：501 / 409 / 200 / 401 / 契约 403 响应；
  - `GET /entities/{id}`：404 / 200 / 501 / 409 / 401。

### 合计：244 passed（基线 226 + 新增 18）

## 四道门禁

| 门禁 | 结果 |
| --- | --- |
| `ruff check .` | All checks passed |
| `pytest -q` | 244 passed |
| `python scripts/check_seams.py` | ERROR 0 / OK 7 / WARN 6 |
| `python scripts/export_openapi.py --check` | 无 drift |

| 前端 | 结果 |
| --- | --- |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm run gen:api` | 已重新生成（含 `ENTITY_NOT_FOUND` + 3 端点） |

## 待办（开发侧）

1. 删除 `backend/dev.db`（新增 `kg_versions` 表 + `documents` 5 列）：开发库仍持有旧的 schema，重启后 Alembic 会自动迁移；或手动 `rm backend/dev.db` 让 `create_app()` 重建。
2. 前端 dev server 启动后默认走 mock（`USE_MOCK=true`），可直接看到新形态数据；切到真实接口只需把 `NEXT_PUBLIC_USE_MOCK=false` 写入 `.env.local`。
3. 下次提交建议：把 `docs/v1.1.0-demo-mvp-plan.md` §4.2 批次 C 的验收清单勾选完毕；批次 D 是「文档重处理 / 抽取统计 / kg_version 切换」等更深的功能扩展，目前仍未启动。

## 接口对齐清单

| 前端调用 | 后端契约 | 后端实装 | mock 兜底 |
| --- | --- | --- | --- |
| `GET /documents?q=&status=&page=&page_size=` | ✅ | ✅ | ✅ |
| `GET /graph/overview` | ✅ | ✅ | ✅ |
| `GET /entities/{id}` | ✅ | ✅ | ✅ |

**结论**：批次 C 接口全部对齐，无跨端缺口。