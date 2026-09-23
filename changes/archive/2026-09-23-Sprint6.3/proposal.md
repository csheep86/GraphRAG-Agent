# Proposal: Sprint 6.3 —— 真机发现的修复批次（激活端点 + 真源收口 + 投影纠偏）

**日期**：2026-09-22
**触发**：Sprint 6.2 批次 B 真机冒烟（判据②已闭环）暴露的 4 项真机发现，用户 2026-09-22 拍板「按建议执行」。

## 1. 背景（真机实测，非推测）

| # | 真机现象 | 根因 |
|---|---|---|
| D1 | 建图完成后 `kg_versions` 停在 `ready`，Neo4j `:KgVersion` 的 active 仍是旧导入版本 `20260917T090000Z-phase09`（无 `:Chunk`） | **后端无在线激活端点**：`grep activate` 于 `app/api/v1` 零命中；建图只写到 `ready`，没人把 Neo4j 镜像置 `active`（与 Sprint6.1「在线链路不自串联」同源） |
| D2 | PG `kg_versions.status` CHECK 只允许 `pending/building/ready/failed`，**没有 `active`**；而 `GraphService.fetch_active_kg_version` 读的是 **Neo4j** | 双状态机：PG 用 `ready` 表达「可消费」，Neo4j 用 `active`；**读侧绕开了 PG 真源**（ADR-0002 §3.2 / `versioning.py` docstring 都写了「后续批次先查 PG」） |
| D3 | `:Chunk` 的 `page`/`char_start`/`char_end` 真机存的是**字符串**（`'1'`/`'0'`/`'764'`） | 写侧未 cast；读侧已 int 归一（`int(...)`），但字符串区间做比较会埋雷 |
| D4 | `kg_relations[].type` 全是 `MENTIONS`，而 `properties.relation_type` 是 `PARTY_TO` | **不是建图错**：该边真机 `type(r) = RELATION`（通用 token），真实语义在 `properties.relation_type`；`_relation_type()` 的「未知类型兜底 MENTIONS」把它吃掉了。图谱页与 Prompt 均被污染 |

## 2. 范围（本批次做）

1. **在线激活端点**：`POST /api/v1/graphs/versions/{version}/activate`
   - 以 **PG `kg_versions` 为真源**判定（版本存在 + 同租户 + 非 `failed`），置 `ready`（幂等）；
   - 同步 Neo4j 镜像：目标版本 `status='active'`，同 org 其它版本 `superseded`（Neo4j 侧无 CHECK 限制）；
   - 错误语义：版本不存在 → 404 `NOT_FOUND`（`reason=kg_version_not_found`）；`failed` 版本 → 409 `KG_VERSION_NOT_ACTIVE`；Neo4j 不可用 → 501。**不新增错误码**。
2. **读侧真源收口**：`fetch_active_kg_version` 支持可选 `db`——**有 db 时 PG 优先**（`status='ready'`，按 `ready_at` desc），无 db 时降级 Neo4j 兜底；`graph` / `agent` 路由注入 `DbSession`。
   - ⚠️ **不**给 PG 加 `active` 取值（SQLite 改 CHECK 需重建表 / 迁移）：PG 的 `ready` 即 active 语义，Neo4j 的 `active` 只是镜像词汇。
3. **写侧 cast**：`:Chunk` 的 `page`/`char_start`/`char_end` 落库前转 int（`page` 为 `None` 时保持 `null`）。
4. **`_relation_type` 语义优先**：先取 `properties.relation_type`（真机真实语义，如 `PARTY_TO`），命中契约枚举即直通；都不命中才兜底 `MENTIONS`。

## 3. 非范围（明确不做）

- **实体去重（6 → 18）**：按 `canonical_name` 幂等 —— 推 **S9 实体消解**（plan §9），本批次只登记。
- 受控问题集覆盖率、批次 C 前端溯源交互：属 Sprint 6.2 既有批次，本批次**不**动。
- 不建新表 / 不做 SQLite 表结构迁移。

## 4. 验收

- 契约零漂移（`export_openapi.py --check`）+ `npm run gen:api` + `tsc`/`eslint`；
- `pytest` 全绿（新增激活端点用例 + `_relation_type` 语义优先用例 + chunk cast 用例）；
- **真机复验**：调 `activate` → `GET /graph/overview` 返回 `v-3e381d36`；`POST /agent/query` 的 `kg_relations[].type` 为 `PARTY_TO`（不再是 `MENTIONS`）；新建图后 `:Chunk` 落整型。
