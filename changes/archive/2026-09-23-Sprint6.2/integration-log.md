# 集成实测日志：Sprint 6.2 —— 引用回查链路（批次 B）

> 规则：以**本地实际跑通的结果**为唯一标准；勾选 ≠ 通过，须有本文件的实测证据。
> 判据②（go/no-go）已于 2026-09-22 **真机闭环**，证据见 §3。

## 1. 环境

- 分支：`feature/sprint-6`；后端 `uv` 虚拟环境（SQLite `dev.db` + 本地存储）
- 基础设施：Neo4j 容器（`neo4j:latest`，7474/7687，Up）
- LLM：`deepseek-chat`（`LLM_BASE_URL=https://api.deepseek.com`，Key 已配置）

## 2. 单测 / 门禁（全部为本地真实执行结果）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `uv run ruff check app tests` | `All checks passed!` |
| 2 | `uv run ruff format --check app tests` | `85 files already formatted` |
| 3 | `uv run pytest -q` | **287 passed, 1 warning** |
| 4 | `uv run python scripts/export_openapi.py` | `[OK] 已生成 contracts/openapi.yaml` |
| 5 | `uv run python scripts/export_openapi.py --check` | `[OK] …与后端模型一致`（零漂移） |
| 6 | `uv run python scripts/check_seams.py` | `ERROR 0 / WARN 6 / OK 7` → `[OK] 接缝门禁通过` |
| 7 | `npm run gen:api` | `openapi-typescript 7.13.0` → `src/types/api.d.ts` |
| 8 | `npm run typecheck` / `npm run lint` | 均无输出（通过） |

契约落点（`git diff --stat`）：`contracts/openapi.yaml | 150 +++`；
新内容位于 `components.schemas.DocumentChunkResponse`（L209）与
`paths./api/v1/documents/{document_id}/chunks/{chunk_id}`（L1418，`operationId: getDocumentChunk`）。

## 3. 真机冒烟（判据②）——**已闭环**

前置数据（批次 A 真机建图产出，Neo4j 实测）：

```
kg_version=v-3e381d36 → Entity 18 / Document 1 / Chunk 1
(:Document {id: 22813b00-…})-[:HAS_CHUNK]->(:Chunk {id: chunk-581e8912827d})-[:MENTIONS]->(:Entity)
```

### 3.1 `POST /api/v1/agent/query`（真实 DeepSeek 调用）

请求：`{"question": "智能制造与数字服务两大板块合计贡献集团多少？", "scope": "cross_doc"}`
（`X-Org-Id` / `X-Actor-Id` = 默认租户）

响应（节选，trace_id `ac96c5f1-3a9c-4c73-b89f-9f3a6f26708c`）：

```json
{
  "answer": "智能制造与数字服务两大板块合计贡献集团营业收入的 62.3%，仍是核心增长引擎 [source: chunk-581e8912827d]。",
  "citations": [{
    "doc_id": "22813b00-fc57-4fac-bdd1-87b4631ec38c",
    "page": 1,
    "chunk_id": "chunk-581e8912827d",
    "char_offset": 0,
    "snippet": "# 2025 年度集团经营指标分析报告\\n\\n# 编制单位：战略发展部 …"
  }],
  "route": "m3_graphqa", "confidence": "high", "refused": false,
  "kg_version": "v-3e381d36",
  "token_usage": {"prompt_tokens": 1733, "completion_tokens": 66, "total_tokens": 1799}
}
```

✅ **判据②达成**：`chunk_id` 以 `chunk-` 开头且为库里真实节点 id；`doc_id`/`page`/`snippet`
均来自本轮注入的证据片段，**无**骨架版的 `UUID(int=0)` / 伪造 `page=1`。

### 3.2 `GET /api/v1/documents/{id}/chunks/{chunk_id}`

- 同租户 → **200**：`page=1`、`char_start=0`、`char_end=764`、`text` 为报告全文（含表格与要点摘要）
- 跨租户（`X-Org-Id=…0002`）→ **403** `FORBIDDEN`，`detail.reason = cross_tenant_access`
- 不存在的 chunk → **404** `NOT_FOUND`，`detail.reason = chunk_id_not_in_artifact`（**不**返回空串）

## 4. 真机暴露并修掉的问题（单测层**永远发现不了**）

1. **`NameError: name 'ChatOpenAI' is not defined` → 真机 500**
   `agents.py::_ensure_chat` 写着 `ChatOpenAI is None`，但该名字只在 `except` 分支被赋
   `None`；langchain 导入**成功**时它从未定义 → 首个真机请求即 500
   （`code=INTERNAL_ERROR`, trace_id `01f3ee89-…`）。单测把 LLM 全打桩，该分支不可达。
   处置：删除对 `ChatOpenAI` 名字的引用，只判可用性探测结果，构造统一交
   `providers.build_chat_model()`（内部才导入 `ChatOpenAI`）；
   并补回归单测 `test_ensure_chat_builds_model_without_undefined_name`
   ——**真调** `_ensure_chat`（只打桩 `build_chat_model`），把该缺陷钉在单测层。
2. **active 版本与建图产出不是同一个**：Neo4j 侧 active 仍是旧的
   `20260917T090000Z-phase09`（23 Entity，**无 Chunk**），而批次 A 真机建图落在
   `v-3e381d36`。处置（真机数据准备）：旧版置 `superseded`、`v-3e381d36` 置 `active`。
   ⚠️ **上报点**：后端**没有**在线激活端点（`grep activate` 于 `app/api/v1` 零命中），
   建图完成后版本停在 `ready`，需人工激活——与 `Sprint6.1/integration-log.md` §4 第 3 项
   「在线链路不自串联」同源。
3. **PG 与 Neo4j 两套状态机不一致（ADR-0002 §3.1/§3.2）**：PG 侧
   `kg_versions.status` 的 CHECK 只认 `pending/building/ready/failed`，**没有 `active`**；
   `active` 只存在于 Neo4j `:KgVersion`。于是「激活」只能落在 Neo4j，PG 永远停在 `ready`。
   ⚠️ **上报点**：需要拍板真源与状态取值（是给 PG 加 `active`，还是让读侧统一读 PG）。
4. **真机 `:Chunk` 的 `page`/`char_start`/`char_end` 存的是字符串**（`'1'` / `'0'` / `'764'`）。
   批次 B 在读侧做了 int 归一（响应 `page: 1` 正确），⚠️ 但写侧应落整型——登记给批次 A 后续修。

## 5. 真机观察到的**数据质量**问题（不在本批次范围，仅登记）

- `kg_nodes` 返回 18 个节点 = 6 个唯一实体 × 3（`年度集团` / `本报告汇总了集团` /
  `智能制造与数字服务两大板块合计贡献集团` / `2025 年` / `2024年` 各 3 份，id 不同）
  → 同一实体被建图三次且**未按 canonical_name 幂等去重**。
- `kg_relations[].type` 全是 `MENTIONS`，而 `properties.relation_type` 是 `PARTY_TO`，
  source/target 都是 Entity → 实体间关系查询把 `:Chunk)-[:MENTIONS]->(:Entity` 也混进来了
  （`_QUERY_ALL_ENTITY_SUBGRAPH` 未按关系类型过滤）。会直接影响批次 C 的图谱可视化。

## 6. 过程中修掉的单测层问题（反哺）

1. `_CITATION_ID_PATTERN` 原为 `chunk-[0-9A-Za-z]{4,64}`，而既有用例与契约示例用 `chunk-12`
   → 引用被误杀。处置：放宽 `{1,64}`，闸门交给 `chunk_id` 索引回查（F3 语义不变）。
2. `test_agent_fail_closed.py` 的桩缺 `nodes`、未打桩 `fetch_evidence_chunks` →
   落到真实 Neo4j 而偏离断言。处置：**补桩不改断言**。
3. `"<chunks: empty>" not in prompt` 恒不成立（Prompt 正文含该指令文案）→ 改正向断言。
4. 前端 `page` 可空后渲染成「第  页」→ `?? "?"`（**不**伪造页码）。
