# Tasks: Sprint 6.1 —— Chunk 证据节点与页码落地（批次 A）

> 与 `docs/v1.1.0-demo-mvp-plan.md` §16~§20（Sprint 级）分工：本文件是批次级拆解。勾选 ≠ 通过，须有 `integration-log.md` 实测证据。
> 门禁口径（S5 收尾更正）：接缝门禁 = **默认档 + ERROR = 0**（`--strict` 仅 v1.4.0 完成点）。

## 1. 契约更新
- [x] 无契约变更（写侧中间产物不进契约）；收尾 `uv run python scripts/export_openapi.py --check` 无 diff

## 2. 后端实现（backend/）
- [x] A-1 `langextract.py`：`ExtractedChunk` 数据类 + `ExtractionResult.chunks` + `to_json_dict()["chunks"]`
- [x] A-1 `registry.py::_do_extract`：写 `chunks.json`（`build_extract_artifact_key(..., "chunks.json")`）
- [x] A-2 新增 `app/services/parsing/page_index.py`：`build_page_index()` / `locate()` / `locate_range()`（失配 → `None`）
- [x] A-2 `registry.py::_do_extract`：读 `content_list.json` → 建索引 → 回填每个 chunk 的 `page`（缺产物时 `page = None`，**不**失败）
- [x] A-3 `builder.py`：`KgBuildRequest` 增 `chunks` + `document`（`KgDocumentRef`: doc_id / acl_scope）
- [x] A-3 `builder.py`：stage-1.5 `MERGE (:Document)`（含 `acl_scope` 继承）
- [x] A-3 `builder.py`：stage-2.5 分批 `MERGE (:Chunk)`
- [x] A-3 `builder.py`：stage-4 `(d)-[:HAS_CHUNK]->(c)` + 实体区间归属 `(c)-[:MENTIONS]->(e)`
- [x] A-3 `registry.py::_do_kg_build`：读 `chunks.json` 传入构建请求（缺文件 → 显式报错，不静默跳过）
- [x] A-2 补：`content_list.json` 支持 **v1（离线库，`page_idx`）/ v2（云 API，页列表索引）**两种实测形态
- [x] 修：`_CYPHER_STAGE1B_INDEXES` 的 `IS NODE KEY` → `IS UNIQUE`（社区版不支持 NODE KEY，实测阻塞 kg.build）

## 3. 前端实现（frontend/）
- [x] 无（批次 C）

## 4. 验证
- [x] `uv run ruff check .` + `uv run ruff format --check .` 通过
- [x] `uv run pytest -q` **267 passed**（基线 244，新增 23 例）
- [x] 新增单测：`test_page_index.py`(11) / `test_kg_build_chunks.py`(9) / `test_langextract_chunks.py`(4)
- [x] `uv run python scripts/check_seams.py` ERROR = 0
- [x] `uv run python scripts/export_openapi.py --check` 无 diff
- [x] 真机冒烟：上传 `mineru_mvp/input/complex_table.pdf` → `status/extract_status/kg_build_status` 全 `completed`
      （**注**：在线链路不自串联，extract / kg.build 为复位状态后按执行体顺序触发——见 integration-log §4.3）
- [x] **go/no-go 判据①**：`MATCH (c:Chunk)` = 1；`MATCH (d:Document)` = 1；
      `MATCH ()-[:HAS_CHUNK]->()` = 1；`MATCH (:Chunk)-[:MENTIONS]->(:Entity)` = 6；`chunk.page = 1` → **达标**
- [ ] **go/no-go 判据②**：由判据① + 批次 B 的 `_to_citation` 消费共同判定；在批次 B 收口时执行

## 5. 收尾
- [x] `changes/Sprint6.1/integration-log.md` 补实测证据链（含页对齐命中率、判据①结论）
- [x] 未达标 → 按建议项降级（`doc-` 前缀）+ release notes 登记 —— 本批次判据①达标，无需降级
