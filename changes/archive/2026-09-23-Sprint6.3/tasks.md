# Tasks: Sprint 6.3 —— 真机发现的修复批次

> 依据 `changes/Sprint6.3/proposal.md`。勾选 ≠ 通过，须有 `integration-log.md` 实测证据。
> 顺序：**契约先行** → 后端 → `npm run gen:api` → 前端。

## 1. 契约（contracts/openapi.yaml）
- [x] 新增 `POST /api/v1/graphs/versions/{version}/activate`（`operationId: activateKgVersion`，401/403/404/409/501 齐全）
- [x] 新增响应 schema `KgVersionActivationResponse`（`version` / `source_status` / `graph_mirror_status` / `superseded_versions` / `activated_at` / `trace_id`）
- [x] `uv run python scripts/export_openapi.py` 重新生成 + `--check` 零漂移（10 路径）

## 2. 后端（backend/）
- [x] T1 写侧 cast：`builder.py::_normalize_chunk_row` 把 `char_start`/`char_end`/`page` 转 int（`page` 缺失写 `null`）
- [x] T2 `_relation_type` 语义优先：`properties.relation_type` 命中枚举即直通，兜底仍为 `MENTIONS`
- [x] T2-b 同款污染补修：`fetch_graph_overview` 的 `edges[].relation` 也改语义优先（真机曾直出 `RELATION`）
- [x] T3-a `versioning.py`：`activate_by_version(org_id, version)` —— 存在性 + 仅 `ready` 可激活（幂等），否则 `KgVersionNotFoundError` / `KgVersionNotActivatableError`
- [x] T3-b `graphs.py`：`activate_kg_version()` 同步 Neo4j 镜像（目标 `active`，同 org 其它 `superseded`）
- [x] T3-c `fetch_active_kg_version` 支持可选 `db`：**PG 优先**（`ready_at` desc），无 db 时 Neo4j 兜底；PG 无记录**不**回落
- [x] T3-d 路由 `graph.py` 新增 activate 端点；`graph` / `agent` 路由注入 `DbSession`
- [x] 错误语义：404 `NOT_FOUND`（`kg_version_not_found` / `kg_version_absent_in_graph`）/ 409 `KG_VERSION_NOT_ACTIVE` / 501 图谱不可用，**未新增错误码**

## 3. 前端（frontend/）
- [x] `npm run gen:api` 同步新端点类型；`tsc --noEmit` + `eslint` 通过（本批次前端**不改 UI**，只同步类型）

## 4. 验证
- [x] `uv run ruff check app tests` + `uv run ruff format --check app tests`
- [x] `uv run pytest -q` **297 passed**（新增 10 例）
- [x] `uv run python scripts/check_seams.py`（ERROR = 0）
- [x] 真机：`activate` → 200（真源 `ready` + 镜像 `active`，旧版 `superseded`）；不存在版本 → 404 `kg_version_not_found`
- [x] 真机：`GET /graph/overview` 的 `kg_version=v-3e381d36`，`edges[].relation=PARTY_TO`（修复前 `RELATION`）
- [x] 真机：`POST /agent/query` 的 `kg_relations[].type=PARTY_TO`（修复前 `MENTIONS`），引用仍为真实 `chunk-581e8912827d`
- [x] 真机：写入 `v-smoke-cast` 后 `:Chunk` 的 `page`/`char_start`/`char_end` 均为 `INTEGER`（缺页 `NULL`），验证后已清理

## 5. 收尾
- [x] `changes/Sprint6.3/integration-log.md` 补实测证据链（§2 真机证据 + §4 两个插曲）
- [x] 登记：实体去重（6 → 18）推 S9；PG `ready` ↔ Neo4j `active` 词汇映射写入 ADR-0002 待办
- [ ] 回批次 C（前端溯源交互：点引用 → chunk 端点 → 跳原文高亮）
