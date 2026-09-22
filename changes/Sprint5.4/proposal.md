# Sprint 5 批次 C · 接口补齐 + 关 Mock（`GET /documents` + 图谱概览 + 实体详情）

- **状态**：Proposed
- **基线**：264fe52（Sprint 5 批次 B 收口；四道门禁全绿：pytest 226 / ruff / check_seams ERROR 0 / openapi 无漂移）
- **目标版本**：v1.1.0
- **计划执行人**：后端开发（B）+ 前端开发（A）
- **上游**：plan §4.2 批次 C；Sprint5.3（在线抽取建图）、Sprint5.2（接缝收口）

## 1. 范围（做什么）

| # | 子目标 | 落地形态 | 备注 |
|---|---|---|---|
| C-1 | `GET /api/v1/documents` 文档列表（薄） | `routes/documents.py` 新增 `list_documents()`；按 `org_id` 过滤，支持 `q`（filename_hash 模糊匹配——文件名原文不落库，**仅按 hash 前缀匹配**）/ `status` / `page` / `page_size` | 关联需求：前端 p02「文档管理」表格（4 类筛选 + 分页）。**对齐现有 mock**：DocumentListItem 与 `frontend/src/types/mock.d.ts` 字段一一对应 |
| C-2 | `GET /api/v1/graph/overview` 全局图谱概览 | `routes/graph.py`（新文件）+ `GraphService.fetch_graph_overview()`；调用现有 `fetch_all_subgraph()`，附加 doc_count / kg_version 摘要 | 关联需求：前端 p04「知识图谱」力导向图。**节点上限 500 + truncated 标记**（与 `DocumentGraphResponse` 一致） |
| C-3 | `GET /api/v1/entities/{entity_id}` 实体详情 | `routes/graph.py` `get_entity_detail()`；查询 Neo4j `Entity` 节点 + 出边邻居 + 属性 | 关联需求：前端 p04 实体详情面板。属性 / 出边（source+target_id+target_name）扁平返回 |
| C-4 | 端点登记 `CONTRACT_COVERED_PATTERNS` | `frontend/src/api/client.ts` 新增 3 条 regex；`USE_MOCK=false` 时自动走真实接口 | 关 Mock 硬门槛：p02 / p04 真实数据可见 |
| C-5 | 前端 types 收口 | `frontend/src/types/mock.d.ts` 删除 DocumentListResponse / GraphOverviewResponse / EntityDetail 三个 mock-only 类型，替换为 `components["schemas"][...]` 别名 | **出接口对齐清单**：原 mock 类型清单 + 删除原因 + 替换映射 |
| C-6 | `.env.example` + `docs/release-notes/v1.1.0.md` 收尾 | 配置无新增（仅薄接口）；release notes 登记"演示页零假数据" | — |

## 2. 不做什么（边界纪律）

按 CODEBUDDY.md §功能预留原则 + plan §4.4：

- **不**引入分页参数透传到 settings（前端默认 page_size=10 / max=100 写在 schema 即可，避免 settings.* 无消费者入坑 R4）
- **不**做文档级 vs 全局 kg_version 区分；overview 恒取 active
- **不**支持文档级关键字精确搜索（filename_hash 是 SHA-256 不可逆，模糊匹配只能做 hash 前缀；演示场景量小可接受）
- **不**做实体属性的透传 PII 字段（如 `pii_flags`）；`GraphNode` schema 已刻意外泄（modules §M2 §5.3）
- **不**新增 settings.* / ADR §2.1 登记集合（无新接缝）；`check_seams.py` ERROR 必须仍为 0
- **不**新增 `kg_versions` 表 / 8 个预留字段（批次 B 已落；本批只做读路径）
- **不**为单测引入 Neo4j 容器；测试沿用批次 A 既有 `bolt://127.0.0.1:1` 不可达路径，校验 501 即可
- **不**动 frontend/ `frontend/src/app/documents` / `frontend/src/app/graph` 的视觉表现——只换数据源

## 3. 依赖与前置

- 已有资产：`app/services/graphs.py::fetch_all_subgraph()`（Sprint 4.10.0 落）、`DocumentGraphResponse` schema（已有节点/边模型）；`frontend/src/api/{documents,graph}.ts` 现有 mock 调用面
- ADR：ADR-0002 §3.2（kg_version 强制 active）、ADR-0003（org_id 只来自认证态）、ADR-0004 §3（无新接缝）
- 配置：`settings.app_version` 保持 1.1.0

## 4. 风险与兜底

| # | 风险 | 缓解 |
|---|---|---|
| R1 | Neo4j 不可用 → overview / entity 接口持续 501 | 路由层把 `GraphUnavailableError` 转 501 `NOT_IMPLEMENTED`（与 `/documents/{id}/graph` 同模板） |
| R2 | 列表 `q` 匹配 `filename_hash` 前缀在 SQLite 上索引效率低 | 文件量级 demo（<10 万），前缀 LIKE 可接受；规模超阈值再考虑冗余 `filename_display` 列（ADR-0004 §3 留位，不落本批） |
| R3 | `entity_count` 在文档列表中跨文档累加，与 `:Chunk` 抽取质量挂钩（Sprint 6 才真实落值） | 本批定义为 `documents.kg_version_id IS NOT NULL` 时为 `null` → 取 `count(kg_versions.entity_count)`；语义详见 `DocumentListItem.entity_count` 字段说明 |
| R4 | 前端 `mock` 关闭后第一次拉到空数据（无 kg_version） | 前端表格组件已支持空态（`MOCK_DOCUMENT_TOTAL = 1248` 之外的空态分支）；本批仅切数据源，组件行为不变 |
| R5 | 类型收口导致 `frontend/src/api/mock/{documents,graph}.ts` 文件被删除 | 仅保留 mock 仍用的部分（`MOCK_RECENT_DOCUMENTS` 等）；删除前确认无其他 import |

## 5. 验收（plan §4.3 + sprint-calendar §3）

| # | 项 | 指标 | 检验命令 |
|---|---|---|---|
| V1 | 接缝门禁 | ERROR 0 | `uv run python scripts/check_seams.py` |
| V2 | 契约零漂移 | 无 diff | `uv run python scripts/export_openapi.py --check` |
| V3 | 后端测试 | ≥ 232 passed（新增 ≥ 6） | `uv run pytest -q` |
| V4 | ruff 全过 | 0 错 | `uv run ruff check .` + `uv run ruff format --check .` |
| V5 | 列表接口 | 同租户 + 跨租户 403 + q/status 过滤 + 关键字（hash 前缀） | `tests/test_documents_list.py` |
| V6 | 概览接口 | 同租户 + Neo4j 不可用 501 | `tests/test_graph_routes.py` |
| V7 | 实体详情接口 | 存在 200 + 不存在 404 + 跨租户 403 | `tests/test_graph_routes.py` |
| V8 | 前端类型 | `npm run gen:api` 无 diff；`src/types/api.d.ts` 含新 6 个 schema | 见 PR diff |
| V9 | 前端 lint + typecheck | 全过 | `cd frontend && npm run lint && npm run typecheck` |
| V10 | Mock 关闭 | `NEXT_PUBLIC_USE_MOCK=false` 下 documents / graph 页零假数据 | `CONTRACT_COVERED_PATTERNS` 登记 + 手测 |
| V11 | release notes | `docs/release-notes/v1.1.0.md` 写明"演示页零假数据 + 已知限制" | — |

## 6. 收尾

- Conventional Commits：`feat(api): GET /documents list` / `feat(api): graph overview + entity detail` / `feat(frontend): wire real list + overview + entity` / `chore(sprint5.4): integration log`
- `integration-log.md` §4 验证矩阵 + §5 接口对齐清单（删除 mock 类型清单）
- 收尾 commit 后跑四道门禁并贴结果摘要