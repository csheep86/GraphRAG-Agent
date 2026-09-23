# Sprint 6.1 实测记录（批次 A：Chunk 证据节点与页码落地）

> 每个结论都要能复跑，记录"怎么测的"。本文件随批次收尾移入 `changes/archive/<日期>-Sprint6.1/`。
> 门禁口径（S5 收尾更正）：接缝门禁 = **默认档 + ERROR = 0**（`--strict` 仅 v1.4.0 完成点）。

## 1. T0 环境基线（2026-09-22）

| 项 | 实测 |
|---|---|
| 分支 / 基线 | `main` @ `ef254f70`，tag `v1.1.0`，`git status` 空 → 新建 `feature/sprint-6` |
| 基线门禁 | `ruff check` / `ruff format --check` 通过；`pytest -q` **244 passed**；`check_seams` **ERROR 0 / WARN 6 / OK 7**；`export_openapi --check` 无 diff |
| Neo4j | 容器 `neo4j:latest` 存在但 **stopped** → `docker start neo4j` 后 `bolt://localhost:7687` `verify_connectivity` OK。库内既有：`23 :Entity` + `12 HAS_FINANCIAL_INDICATOR` + `1 :KgVersion(active, 20260917T090000Z-phase09)`；**`:Document` / `:Chunk` = 0** |
| LLM | `.env` 仍是旧键名 `DEEPSEEK_*`（Sprint 5 批次 A2 已改名 `llm_*`）→ `llm_api_key` 为空、`/agent/query` 会 501。**已按授权改名**为 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`，实测 `GET {LLM_BASE_URL}/models` = **200**（models: `deepseek-flash`、`deepseek-v4-pro`…） |
| MinerU | `MINERU_TOKEN` 为空 → `document.parse` 对 PDF 直接抛错。**已按授权**从 `mineru_mvp/.env` 注入（len=51） |
| 本地库 / 存储 | `backend/dev.db`、`backend/storage/` 均不存在（S5 收尾口径：首次启动自动建表） |

## 2. 页码可行性（A-2 前置实测）

两份**真实 MinerU 产物**结构不同，必须都支持：

| 来源 | 结构 | 页码来源 | 对齐实测 |
|---|---|---|---|
| 离线 `mineru_mvp/output/complex_table/` | **v1**：扁平条目列表，每项 `{"bbox":..., "page_idx": 0, "text": ..., "type": ...}` | `page_idx`（**0-based**） | 顺序游标 `find`：**10 / 10 命中**（带 text 的条目共 10 项） |
| 云 API（`document.parse` 真机） | **v2**：`[[block, ...], [block, ...]]` 页列表嵌套条目 | **外层索引 + 1**（块内**无** `page_idx`，文本在 `content.title_content` / `content.paragraph_content` 的 `{"type":"text","content":...}` 叶子） | 11 个 block（title 5 / paragraph 5 / table 1），文本块命中 → 判出 `page = 1` |

两条共同事实：`full.md` **不含任何页分隔标记**（`<!-- -->` 0 处、`page` 正则 0 命中），页码只能靠 `content_list` 对齐反推。

## 3. 真机管线实测（判据①）

驱动方式：起真服务（`uvicorn app.main:create_app`，127.0.0.1:8123）→ `POST /api/v1/documents/upload`（`complex_table.pdf`，`curl -F "file=@...;type=application/pdf"`）→ 跑 parse → 触发 extract / kg.build。

```
POST /api/v1/documents/upload        → 202（task 22813b00…，真 MinerU 云解析成功，markdown 1358 bytes）
document_extract_artifacts_stored    → entity_count=6, chunk_count=1, chunk_with_page=1
kg_build_artifacts_loaded            → entity_count=6, chunk_count=1, evidence_edge_count=7
documents 表                          → status=completed, extract_status=completed, kg_build_status=completed
```

Neo4j 结果（复跑命令：`MATCH (c:Chunk) RETURN count(c)` 等）：

| 判据 | 结果 |
|---|---|
| `MATCH (c:Chunk) RETURN count(c)` | **1** ✅（`chunk-581e8912827d`，`char_start=0`、`char_end=764`、**`page=1`**） |
| `MATCH (d:Document) RETURN count(d)` | **1** ✅ |
| `MATCH ()-[:HAS_CHUNK]->()` | **1** ✅ |
| `MATCH (:Chunk)-[:MENTIONS]->(:Entity)` | **6** ✅ |
| `kg_versions`（PG） | `v-3e381d36`，`status=ready` ✅ |

**判据①：达标。**

## 4. 过程中修掉 / 撞上的问题（均有实测证据）

1. **`IS NODE KEY` 在社区版不可用**（阻塞）：kg.build stage-1 报
   `Node Key constraint requires Neo4j Enterprise Edition`（容器 `neo4j:latest` = Community）。
   → 降级为社区版可用写法 `REQUIRE (n.id, n.kg_version) IS UNIQUE`（唯一性这个幂等前提保留），
   代码注释写明依据。**需上报**：与历史实现有偏离。
2. **历史遗留约束冲突**：DB 内已存在 `entity_id_version_unique`（UNIQUENESS，同名属性不同约束类型）
   → `CREATE CONSTRAINT entity_id_version` 被拒（`Conflicting constraint already exists`，id=6）。
   → 真机验证前 `DROP CONSTRAINT entity_id_version_unique`（**只删约束，不删数据**）。
   遗留的 23 个 `:Entity` / `:KgVersion(phase09)` 未动。
3. **在线链路不自串联**（既有缺口，**需上报**）：上传后只有 `document.parse` 入队，
   extract / kg.build **不会自动触发**（`documents.extract_status` 长期为 `NULL`）；
   且 `TaskManager.submit()` 对 `status not in {pending, processing}` 直接跳过、
   `document_extract_executor` 对 `extract_status == completed` 直接 return，
   即**没有可重跑的入口**。本次验证靠「复位阶段状态 + 直接调执行体」完成。
4. **测试会因真实凭据变慢 / 漂移**：注入 `MINERU_TOKEN` 后单个上传用例 `0.11s → 37s`、
   全量 pytest `3.67s → 226s`（用例真的去调 MinerU 云 API）。
   → `tests/conftest.py` 按既有「确定性降级」口径补 `MINERU_TOKEN=""` / `LLM_API_KEY=""`，
   全量回到 **4.48s**。需要真实调用的用例应 `monkeypatch` 显式开启。
5. **页码首判为 None**：`full.md` 开头有不属于任何条目的前缀，首个 chunk `char_start=0`
   落不到已知区间 → 新增 `PageIndex.locate_range()` 按**重叠度**判页（真机上即为 `page=1`）。

## 5. 本批次门禁（收口）

| 门禁 | 结果 |
|---|---|
| `uv run ruff check .` | ✅ All checks passed |
| `uv run ruff format --check .` | ✅ 90 files already formatted |
| `uv run pytest -q` | ✅ **267 passed**（基线 244，新增 23 例：page_index 11 / kg_build_chunks 9 / langextract_chunks 4，另修 `test_kg_build_executor` 补 `chunks.json`） |
| `uv run python scripts/check_seams.py` | ✅ ERROR 0 / WARN 6 / OK 7 |
| `uv run python scripts/export_openapi.py --check` | ✅ 无 diff（本批次不进契约） |

## 6. 遗留 / 未决

- 判据②（`/agent/query` 返回 `chunk-` 前缀引用）需等**批次 B** 的 `_to_citation` 消费，本批次未做。
- 第 4 条第 1 / 3 项需在批次 B 收口时上报用户决策。
