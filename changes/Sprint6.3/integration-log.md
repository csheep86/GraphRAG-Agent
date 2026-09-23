# Integration Log: Sprint 6.3 —— 真机发现修复批次

**日期**：2026-09-22 ~ 2026-09-23
**触发**：`changes/Sprint6.2/integration-log.md` §4/§5 的真机发现，用户 2026-09-22 拍板「按建议执行」。
**真机环境**：本机 Docker `neo4j:latest`（7474/7687）+ SQLite `dev.db` + 真实 DeepSeek。

---

## 1. 真机发现 → 处置对照

| # | 真机现象 | 处置 | 落点 |
|---|---|---|---|
| D1 | 建图后版本停 `ready`，Neo4j active 仍是旧导入版 `20260917T090000Z-phase09`（无 `:Chunk`） | 新增**在线激活端点** | `POST /api/v1/graph/versions/{version}/activate` |
| D2 | PG `kg_versions.status` CHECK 只有 `pending/building/ready/failed`，无 `active`；`fetch_active_kg_version` 却读 Neo4j | **定 PG 为真源**（`ready` 即 active 语义）+ 读侧 PG 优先 | `versioning.activate_by_version` / `graphs.fetch_active_kg_version(db=…)` |
| D3 | `:Chunk` 的 `page`/`char_start`/`char_end` 真机存**字符串** | 写侧 cast int | `builder._normalize_chunk_row` |
| D4 | `kg_relations[].type` 全是 `MENTIONS`，真实语义在 `properties.relation_type` | **语义优先**：先取 `relation_type`，命中枚举直通，未知才兜底 `MENTIONS` | `graphs._relation_type(semantic=…)` |

> D4 补记：真机复验时发现**同一污染还有遗漏面**——`GET /graph/overview` 的 `edges[].relation`
> 直出 `type(r)`（真机显示 `RELATION`），已一并改为语义优先（现真机显示 `PARTY_TO`）。

---

## 2. 真机证据链（全部实测，非推测）

### 2.1 激活端点（200 + 404）

```
POST /api/v1/graph/versions/v-3e381d36/activate
→ 200 {"version":"v-3e381d36","source_status":"ready","graph_mirror_status":"active",
       "superseded_versions":["20260917T090000Z-phase09"],
       "activated_at":"2026-09-22T22:13:58.400409+08:00","trace_id":"5b4cedfc-…"}

POST /api/v1/graph/versions/v-doesnotexist/activate
→ 404 {"code":"NOT_FOUND","detail":{"reason":"kg_version_not_found",…}}
```

激活后 Neo4j 镜像真机状态：
```
kg_versions= [{'v':'20260917T090000Z-phase09','st':'superseded'}, {'v':'v-3e381d36','st':'active'}]
```
**在线激活闭环**——S7 起不必再手工改库。

### 2.2 读侧真源（PG）

```
GET /api/v1/graph/overview → kg_version=v-3e381d36, nodes=18, edges=3
relations=PARTY_TO,PARTY_TO,PARTY_TO        ← 修复前为 RELATION,RELATION,RELATION

POST /api/v1/agent/query 「集团整体净利润率是多少？」
→ kg_version=v-3e381d36
  citations=[{"doc_id":"22813b00-…","page":1,"chunk_id":"chunk-581e8912827d",
              "char_offset":0,"snippet":"# 2025 年度集团经营指标分析报告…"}]
  relation_types=PARTY_TO,PARTY_TO,PARTY_TO  ← 修复前为 MENTIONS,MENTIONS,MENTIONS
```

### 2.3 Chunk 写侧整型（真机写入 + 读回类型）

用 `ThreeStageKgBuilder` 真机写入临时版本 `v-smoke-cast`（**输入故意给字符串**）：
```
chunk-cast-1 输入 page="3"  char_start="0" char_end="100"
  → page=3   page_type=INTEGER NOT NULL   cs_type=INTEGER NOT NULL   ce_type=INTEGER NOT NULL
chunk-cast-2 输入 page=None
  → page=None page_type=NULL（**不**伪造页码）
```
验证后已 `DETACH DELETE` 清理（`left_chunk_cast=0`）。

---

## 3. 门禁（全绿）

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **297 passed**（新增 10 例：激活端点 5、关系语义 4、chunk cast 1） |
| `uv run ruff check app tests` / `ruff format --check` | 通过 |
| `uv run python scripts/export_openapi.py --check` | `[OK]` 零漂移（10 路径） |
| `uv run python scripts/check_seams.py` | `[OK]` ERROR = 0 |
| 前端 `npm run gen:api` + `typecheck` + `lint` | 全部通过 |

---

## 4. 真机过程中的两个插曲（已处理）

1. **Neo4j 容器中途 `Exited (255)`**（2026-09-23）——`overview` 报 501 连不上。
   `docker start neo4j` 后恢复。**提示**：真机冒烟依赖容器存活，后续批次开跑前先 `docker ps`。
2. **打桩 vs 真源冲突**：读侧改 PG 优先后，测试库是空 SQLite，PG 分支会先把「Neo4j 不可达」
   报成 409（把基础设施故障伪装成业务结论，违反 plan §4.4）。
   处置：`conftest` 加 `pg_active_kg_version`（autouse）让真源默认可用，另有
   `real_pg_get_active` 供 `test_kg_versioning` 恢复真实实现断言状态机本身。

---

## 5. 遗留（不在本批次）

- **实体去重（6 → 18）**：按 `canonical_name` 幂等 —— 推 **S9 实体消解**（已在 `proposal.md` §3 登记）。
- **ADR-0002 补记**：PG `ready` ↔ Neo4j `active` 是同一语义的两套词汇，响应里两个字段同时返回
  （`source_status` / `graph_mirror_status`），避免前端误以为存在两个状态机。

---

## 6. 环境收尾

- 后端现跑在 **8002**（本批次代码）；8001 旧代码实例已停。
- 临时日志：`backend/uvicorn8002.out.log` / `uvicorn8002.err.log`（实例占用中，用完请删）。
