# Proposal: Sprint 6.1 —— Chunk 证据节点与页码落地（批次 A）

> 落点：`changes/Sprint6.1/`（与 `integration-log.md` 同目录，批次收尾整目录移入 `changes/archive/<日期>-Sprint6.1/`）。
> 上游：`docs/sprint-calendar.md` §3 S6 行（v1.2.0 / 1.5 周 / 引用溯源 / 第 3 天 go-no-go）；`specs/m3-graphqa-citation.md` §3 验收 / §4.2 Chunk 层。

## Why

Sprint 5 收尾实测（T0 复核）：`backend/app/services/agents.py::_to_citation()` 输出 `chunk_id = UUID(int=0)`、`page = 1`、`char_offset = 0` 恒为占位，且 `agents.py:96` 明确注释「在线链路无 Chunk 层（Sprint 6 补）」。Neo4j 侧现状（本机实测）：23 `:Entity` + 12 `HAS_FINANCIAL_INDICATOR`，**`:Document` / `:Chunk` 节点数 = 0**。

而读侧 Cypher 早已就位：`graphs.py::_QUERY_DOCUMENT_SUBGRAPH` 写的就是
`(:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity)`，
即**读侧等写侧**。本批次把「Chunk 证据层」补上，是 F3（引用溯源）首次达标的**唯一前置**。

关键事实（实测反哺，CODEBUDDY.md「实测结果反哺规则」）：`full.md` **不含任何页分隔标记**（`<!-- -->` 0 处），页码**只能**靠 `content_list.json` 文本对齐反推——本机用 `mineru_mvp/output/complex_table/` 真实产物实测：**11 项中 10 项有 text，顺序游标对齐 10/10 命中**，`page_idx` 存在且**从 0 计**。故判页可行，但属 best-effort：多页文档若某段在 `full.md` 中被改写（表格转 HTML）可能失配 → 失配必须给 `null`，**不伪造 1**。

## What Changes

- **A-1** `LangextractClient` 暴露切块产物：`ExtractionResult` 新增 `chunks: list[ExtractedChunk]`（`chunk_id` / `char_start` / `char_end` / `text` / `page`），`to_json_dict()` 增加 `chunks` 键；`document.extract` 执行体落 `chunks.json` 到 `{org_id}/{doc_id}/extract/`。
- **A-2** 新增 `app/services/parsing/page_index.py`：`PageIndex.from_content_list(markdown, content_list)` 按文本顺序游标对齐产出 `(char_start, char_end, page)` 区间；`locate(char_offset)` 二分判定 → `int | None`（失配 = `None`，不兜底假页码）；`page` 一律 `page_idx + 1`（**1-based**，契约 `Citation.page` 示例值 = 1）。
- **A-3** `ThreeStageKgBuilder` 扩写为五段式（保持 stage-1/2/3 语义不变，新增两段半 + 一段）：
  - stage-1.5：`MERGE (:Document {id, kg_version})`，`acl_scope` 从 `documents.acl_scope` 继承；
  - stage-2.5：分批 `MERGE (:Chunk {id, kg_version})`（`char_start` / `char_end` / `page` / `org_id` / `acl_scope`）；
  - stage-4：`(d)-[:HAS_CHUNK]->(c)` + 实体按字符区间归属落 `(c)-[:MENTIONS]->(e)`。
- **A-4** 单测：`test_page_index.py`（对齐命中 / 失配 / 边界 / 1-based）、`test_kg_build_chunks.py`（stage-1.5 / 2.5 / 4 的 Cypher 段与幂等）、`test_langextract_chunks.py`（chunks 产物与 `chunk-` 前缀）。

## Impact

**影响的契约（contracts/openapi.yaml）**

- 无。本批次只补**写侧**数据结构，`chunks.json` 是存储层中间产物（`build_extract_artifact_key`，不进契约），`acl_scope` 属已登记的预留字段（ADR-0004：预留字段不进契约）。收尾判据：`export_openapi.py --check` 无 diff。

**影响的前端（frontend/）**

- 无。批次 C 才动前端。

**影响的后端（backend/）**

- `app/services/extraction/langextract.py`：`ExtractedChunk` + `ExtractionResult.chunks` + `to_json_dict()`；
- `app/services/parsing/page_index.py`：**新增**；
- `app/tasks/registry.py`：`_do_extract` 读 `content_list.json` 判页 + 写 `chunks.json`；`_do_kg_build` 读 `chunks.json` 并传入 `KgBuildRequest`；
- `app/services/kg/builder.py`：新增三个 Cypher 段 + `KgBuildRequest.chunks` / `document`；
- `tests/`：`test_page_index.py` / `test_kg_build_chunks.py` / `test_langextract_chunks.py`。

**影响的 Prompt（prompts/）**

- 无（本批次不动抽取 Prompt；`kg_qa_v2.md` 属批次 B）。

## Non-goals

- **不**改契约、不生成前端类型（批次 B/C）；
- **不**填 `agents.py` 的引用占位（`_to_citation` 仍是占位，批次 B 才消费本批次产物）——**本批次结束前 `/agent/query` 行为不变**，是刻意的分批验证；
- **不**落 `(chunk)-[:SUPPORTED_BY]->(relation)` 边：读侧 Cypher 与 `Citation` 均不消费它，落了即「无消费者的实现」（Sprint 8 引入证据链时再补）；
- **不**重跑 / 清理 Neo4j 中 `20260917T090000Z-phase09` 的旧 `:Entity` 数据（无 `:Document` / `:Chunk`，与本批次新增版本互不干扰）；
- **不**偿还 E1 / E2（S5 已登记 `unresolved`，归 S13 条件吸收）。
