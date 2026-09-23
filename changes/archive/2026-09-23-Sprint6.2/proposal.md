# Proposal: Sprint 6.2 —— 引用回查链路（批次 B）

> 落点：`changes/Sprint6.2/`（与 `integration-log.md` 同目录，批次收尾整目录移入 `changes/archive/<日期>-Sprint6.2/`）。
> 上游：`docs/v1.1.0-demo-mvp-plan.md` §5.2 批次 B；`docs/sprint-calendar.md` §3 S6 行（v1.2.0 / 1.5 周 / 引用溯源）；
> `specs/m3-graphqa-citation.md` §3 验收 2 / §4.2；前置：`changes/Sprint6.1/`（批次 A，go/no-go 判据①已达标）。
> 已拍板：**Q1** `Citation.page` 改 nullable（失配给 `null`，不伪造 1）；**Q2** 溯源走新增端点
> `GET /documents/{id}/chunks/{chunk_id}` + 前端按 `char_offset` 高亮，**不**把 chunk 全文塞进 `Citation`；
> **Q3** 顺带回写 `specs/m3-graphqa-citation.md` §4.2。

## Why

批次 A 已把证据层写进图：真机实测 `:Chunk` = 1、`:Document` = 1、`HAS_CHUNK` = 1、`MENTIONS` = 6、`chunk.page = 1`
（判据①达标，见 `changes/Sprint6.1/integration-log.md` §3）。但**消费侧仍是占位**：

- `agents.py:255` 渲染 Prompt 时 `text_chunks="<chunks not provided in Sprint 3 phase 9 skeleton>"`——LLM 拿不到原文，
  自然无从引用；
- `agents.py::_to_citation()` 恒返回 `doc_id=UUID(int=0)` / `page=1` / `char_offset=0` / `snippet=""`；
- 于是 `/agent/query` 的引用**要么恒拒答、要么是假引用**——F3（引用覆盖率 100%）仍不达标，判据②未过。

批次 B 就是把「写侧已就位的证据」接到「读侧引用」上，使**判据②**可判。

## What Changes

- **B-1 Prompt**：新增 `prompts/kg_qa_v2.md`（**不覆盖 v1**，`load_prompt("kg_qa")` 自动取最大版本）。
  占位符集合与 v1 **逐字一致**（`graph_subgraph` / `text_chunks` / `chat_history` / `question`），
  否则 `tests/test_prompt_loader.py::KG_QA_VARS` 与 `PromptTemplate.render()` 的「未知变量报错」会红。
  新增约束：证据条目**只能**取 `text_chunks` 中出现过的 `chunk-<id>`，其余一律视为不可溯源。
- **B-2 证据注入**：`GraphService.fetch_evidence_chunks()`（新增 Cypher，按实体 `MENTIONS` 反查 chunk；
  `single_doc` 时按 `:Document` 直达），`AgentService` 把它序列化进 `text_chunks`。
- **B-3 引用真实化**：`_to_citation()` 改为按 `chunk_id` 回查本轮注入的证据片段，填真实
  `doc_id` / `page`（失配 `null`）/ `char_offset` / `snippet`；**回查不到的 chunk_id 直接丢弃**
  （LLM 编造的引用不得进入 `citations`，F3）。
- **B-4 溯源端点**：新增 `GET /api/v1/documents/{document_id}/chunks/{chunk_id}`（契约先行），
  返回 `DocumentChunkResponse{doc_id, chunk_id, text, page, char_start, char_end, trace_id}`；
  数据源是批次 A 落盘的 `chunks.json`（存储层中间产物，**不进契约**），租户隔离复用 `get_scoped_document` + 存储键前缀。
- **B-5 契约**：`Citation.page` 改 nullable（Q1）；新增 `DocumentChunkResponse` 与上述路径；
  `specs/m3-graphqa-citation.md` §4.2 回写（Q3）。

## Impact

**影响的契约（contracts/openapi.yaml）**

- `Citation.page`：`integer` → `integer | null`，且从 `required` 移除；
- 新增 schema `DocumentChunkResponse`；
- 新增路径 `/api/v1/documents/{document_id}/chunks/{chunk_id}`（`getDocumentChunk`，401/403/404 齐全）；
- 收尾判据：`uv run python scripts/export_openapi.py --check` 无 diff。

**影响的前端（frontend/）**

- 本批次只产出契约；`npm run gen:api` + 类型 / Mock 对齐属**批次 C**（evidence-panel 溯源交互）。

**影响的后端（backend/）**

- `app/schemas/agent.py`（`Citation.page`）、`app/schemas/document.py`（`DocumentChunkResponse`）；
- `app/api/v1/responses.py`（`CHUNK_NOT_FOUND`）、`app/api/v1/routes/documents.py`（新路由）；
- `app/services/documents.py`（`get_document_chunk`）、`app/services/graphs.py`（`EvidenceChunk` + `fetch_evidence_chunks`）；
- `app/services/agents.py`（证据注入 + `_to_citation` 真实化）；
- `tests/`：`test_openapi_contract.py`（路径数 8 → 9）、`test_graph_and_agent_routes.py`（补打桩）、
  新增 `test_agent_citations.py` / `test_document_chunk_endpoint.py`。

**影响的 Prompt（prompts/）**

- 新增 `kg_qa_v2.md`（v1 原样保留）。

## Non-goals

- **不**动前端（批次 C）；
- **不**实现「实体级 char_offset」（`:Entity` 未落 `char_start`，`char_offset` 取 chunk 起点 0；
  实体级偏移归 Sprint 10 证据链）；
- **不**新增 `SUPPORTED_BY` 边（读侧与契约都不消费，Sprint 8）；
- **不**修 LLM 引用质量长尾（S6 §5.4 时间盒纪律：留给 v1.5，演示用受控问题集）；
- **不**偿还 `integration-log.md` §4 第 3 项「在线链路不自串联」（需用户决策，见 §6 遗留）。
