# Tasks: Sprint 6.2 —— 引用回查链路（批次 B）

> 与 `docs/v1.1.0-demo-mvp-plan.md` §5.2（批次 B）分工：本文件是批次级拆解。勾选 ≠ 通过，须有 `integration-log.md` 实测证据。
> 门禁口径（S5 收尾更正）：接缝门禁 = **默认档 + ERROR = 0**（`--strict` 仅 v1.4.0 完成点）。

## 1. 契约更新（contracts/openapi.yaml）
- [x] `Citation.page` → nullable（Q1：失配给 `null`，不伪造 1）
- [x] 新增 `DocumentChunkResponse` schema
- [x] 新增路径 `GET /api/v1/documents/{document_id}/chunks/{chunk_id}`（`operationId: getDocumentChunk`，401/403/404 齐全）
- [x] `uv run python scripts/export_openapi.py` 重新生成并确认零漂移（**本批次唯一必须跑命令的步骤**）
  - 实测：`export_openapi.py` → `[OK] 已生成 contracts/openapi.yaml`；`--check` → `[OK] …与后端模型一致`
  - 连带：`cd frontend && npm run gen:api`（契约同步铁律 §4）已执行，`src/types/api.d.ts` 同步出新端点 + `page?: number | null`

## 2. 后端实现（backend/）
- [x] B-1 新增 `prompts/kg_qa_v2.md`（占位符集合与 v1 一致；要求证据只能取已注入的 `chunk-<id>`）
- [x] B-2 `graphs.py`：`EvidenceChunk` 数据类 + `fetch_evidence_chunks()`（按实体 `MENTIONS` 反查；`single_doc` 按 `:Document` 直达）
- [x] B-2 `agents.py::query`：子图检索后拉证据片段 → 序列化进 `text_chunks`（空为 `<chunks: empty>`）
- [x] B-3 `agents.py::_to_citation`：按 `chunk_id` 回查本轮证据 → 真实 `doc_id` / `page` / `snippet`；回查不到即丢弃（F3）
- [x] B-4 `documents.py::get_document_chunk` + 路由（数据源 `chunks.json`；跨租户 403、缺失 404）
- [x] B-4 `responses.py` 增 `CHUNK_NOT_FOUND`（复用 `ErrorCode.NOT_FOUND`，**不**新增错误码）

## 3. 前端实现（frontend/）
- [x] `npm run gen:api` 重出 `src/types/api.d.ts`；`tsc --noEmit` + `eslint` 通过
- [x] `page` 可空的两处渲染兜底：`evidence-panel.tsx` / `chat-message-item.tsx` 改 `第 {citation.page ?? "?"} 页`
      （否则 `null` 会渲染成「第  页」——**不**伪造页码，只显示未知）
- [ ] 批次 C：点击引用标注 → 调新端点取全文并高亮（本批次只做类型与兜底，UI 联动留给批次 C）

## 4. 验证
- [x] `uv run ruff check app tests` 通过（`All checks passed!`）；`uv run ruff format app tests` 已格式化 3 个文件
- [x] `uv run pytest -q` 全绿：**286 passed**（基线 267；新增 `test_agent_citations` 11 例 + `test_document_chunk_endpoint` 6 例 + 契约用例 2 处扩展）
- [x] `uv run python scripts/check_seams.py` → **ERROR 0 / WARN 6**（默认档门槛 = ERROR 0）
- [x] `uv run python scripts/export_openapi.py --check` 无 diff
- [x] `frontend`：`npm run typecheck` + `npm run lint` 均无输出（通过）
- [x] 真机冒烟：`POST /api/v1/agent/query`（受控问题）→ `citations` 非空且 `chunk_id` 以 `chunk-` 开头
      （`chunk-581e8912827d` / `doc_id=22813b00-…` / `page=1` / 真实 snippet，trace_id `ac96c5f1-…`）
- [x] 真机冒烟：`GET /api/v1/documents/{id}/chunks/{chunk_id}` 返回真实原文片段
      （200 全文 + 跨租户 403 `cross_tenant_access` + 缺失 404 `chunk_id_not_in_artifact`）
- [x] **go/no-go 判据②**：`chunk-` 前缀引用**真机跑通**，无需降级为 `doc-` 前缀
- [x] 真机反哺修复：`_ensure_chat` 不再引用未定义的 `ChatOpenAI`（真机 500）+
      回归单测 `test_ensure_chat_builds_model_without_undefined_name`（`pytest` 287 passed）

## 5. 收尾
- [x] `specs/m3-graphqa-citation.md` §4.2 回写（Q3：`page` nullable + chunk 回查端点）
- [x] `changes/Sprint6.2/integration-log.md` 补实测证据链（§3 真机判据② + §4/§5 真机新发现）
- [ ] 上报用户决策（真机发现，详见 `integration-log.md` §4/§5）：
      1. 后端**无在线激活端点**（建图后停 `ready`），与 Sprint 6.1「在线链路不自串联」同源；
      2. PG `kg_versions.status` 无 `active`、Neo4j 才有 → 双状态机不一致，需拍真源；
      3. `:Chunk` 的 `page`/`char_start`/`char_end` 真机存的是**字符串**（写侧待修）；
      4. 数据质量：实体未按 `canonical_name` 幂等（6 → 18）、`kg_relations` 混入 `MENTIONS` 边。
- [ ] 上报用户决策：`Sprint6.1/integration-log.md` §4 第 1 项（`IS NODE KEY` → `IS UNIQUE` 偏离）与第 3 项（在线链路不自串联）
