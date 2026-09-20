# Sprint 4.10.3 联调日志：GET /api/v1/documents/{id}/graph

> **批次**：Sprint 4.10.3（M1 接入 + Neo4j 子图查询契约联调）
> **基线**：Sprint 4.10.2（upload + status 联调通过 6/6）
> **日期**：2026-09-18
> **分支**：`feature/sprint-4`
> **基线脚本**：`changes/Sprint4.10.2/probe.py`、`probe-output.log`、`integration-log.md`
> **本批脚本**：`changes/Sprint4.10.3/probe_graph.py`、`probe-output.log`

---

## 1. 前置核实

### 1.1 Cypher 关键事实（决定 P1 预期）

**位置**：`backend/app/services/graphs.py:121-142`

```cypher
MATCH (d:Document {id: $doc_id, kg_version: $kg_version})     -- 非 OPTIONAL
OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
WHERE c.kg_version = $kg_version
OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
WHERE e.kg_version = $kg_version
  AND ($org_id IS NULL OR e.org_id = $org_id)
WITH d, collect(DISTINCT c) AS chunks,
     collect(DISTINCT e) AS entities
LIMIT $node_limit
RETURN d, chunks, entities,
  [(c)-[r:MENTIONS]->(e) | { id: toString(id(r)), type: type(r),
    source: toString(id(c)), target: toString(id(e)),
    properties: properties(r) }] AS mentions
```

**关键事实链**：
1. 第一个 `MATCH (d:Document {...})` 是 **非 OPTIONAL**——Neo4j 中找不到匹配的 Document 节点时，整个查询返 **0 行**（不是 1 行 d=null）
2. 服务层用 `.single()`（`graphs.py:351`）→ 空结果集上 `.single()` 返 `None`
3. 服务层 line 357-358 检测 `result is None` → **返回 `([], [], False)`，不抛异常**
4. 路由层 (`documents.py:174-184`) 收到 `([], [], False)` → 构造 `DocumentGraphResponse(nodes=[], edges=[], truncated=False, version_status='active')` → **200 OK**

**结论**：Neo4j 可达 + 有 active 版本时，**任意 doc_id 都会得到 200 + 空图**——无论该 doc 在 Neo4j 中是否有 Document 节点。这是**设计行为**，不是 bug：路由层不区分「PG 有 doc 但 Neo4j 无 Document」与「PG 有 doc 且 Neo4j 有 Document 但无 Chunk」，两者一致返 200 空图。

### 1.2 Neo4j 当前状态（实测）

- `kg_version = "20260917T090000Z-phase09"`（**active 版本存在**）
- `nodes = []`, `edges = []`（**Neo4j 中有 23 个 Entity 节点，但无 Document 节点**；Cypher 第一行 `MATCH (d:Document {...})` 非 OPTIONAL，找不到 Document 时整查返回 0 行 → 空图。Entity 节点存在但不通过 document_id 与任何 Document 关联。）

**根因**：`scripts/import_to_neo4j.py` 只 MERGE `:KgVersion` + `:Entity` + 关系（见 `import_to_neo4j.py:272-309`），**不创建 `:Document` / `:Chunk` 节点**——属设计决定（Document/Chunk 由 v1.1.0 接入 MinerU + LangExtract 后填）。本批不修复，记入 v1.1.0。

### 1.3 PG 状态（实测）

- 10.2 doc_id `fae4a287-b701-4627-9020-c41a4f2ba0e0` 仍存在
- `status = "completed"`（PDF 解析已完成——骨架版返回空，但状态机本身跑通）

---

## 2. probe_graph.py 设计要点

| 设计 | 实现 | 原因 |
|---|---|---|
| **P0 前置探针** | 跑所有场景前先打一次 `/graph`，记录 `p0_status` | 避免把 P1/P2 两条互斥分支写成两套脚本 |
| **P1/P2 互斥运行** | `if p0_status == 200: run P1` / `elif == 409: run P2` | 同一 Neo4j 状态下只会命中一种 |
| **P3 必跑** | 随机 UUID，不依赖 10.2 doc_id | 与 Neo4j / PG 状态解耦 |
| **P4 必跑** | 10.2 doc_id + FOREIGN_ORG_ID | 仅依赖 PG，与 Neo4j 解耦 |
| **前置校验** | 跑 P0 前先打 `/status` 验证 doc_id 仍存在 | 防 PG 重置后 P0/P1/P4 全军覆没 |
| **trace_id 命名空间** | `77777777-7777-4777-8777-777777777770` ~ `774`（5 段连续） | 与 10.2 风格一致，便于日志比对 |
| **不测项** | G1（200 + 有数据，需 fixture）、G4（501，需停 Neo4j） | v1.1.0 + 用户明示 |
| **执行** | `uv run python ../changes/Sprint4.10.3/probe_graph.py 2>&1 \| Tee-Object -FilePath ../changes/Sprint4.10.3/probe-output.log` | 复用 10.2 命令模板 |

---

## 3. 原始输出全文（probe-output.log）

> **编码说明**：Python stdout 已通过 `PYTHONIOENCODING=utf-8` 输出 UTF-8；但 PowerShell 5.1 的 `Tee-Object` 按自身编码（GBK / 系统 OEM 代码页）解码管道内容，导致中文标题乱码。关键数据（HTTP status / UUID / JSON 字段值 / PASS/FAIL）均为 ASCII，不影响验收。乱码部分按脚本原意重写。

```
===== 前置校验: 10.2 doc_id fae4a287-b701-4627-9020-c41a4f2ba0e0 是否仍在 PG =====
URL: http://127.0.0.1:8000/api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/status  trace=77777777-7777-4777-8777-777777777700
HTTP status: 200
PG 文档状态: completed
PG 文档 task_id: fae4a287-b701-4627-9020-c41a4f2ba0e0
✓ 10.2 doc_id 仍存在，继续 P0

===== 场景 P0: 前置探针 GET /api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph =====
URL: http://127.0.0.1:8000/api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph  trace=77777777-7777-4777-8777-777777777770
HTTP status: 200
响应头 X-Trace-Id: 77777777-7777-4777-8777-777777777770
body    trace_id : 77777777-7777-4777-8777-777777777770
body:
{
  "doc_id": "fae4a287-b701-4627-9020-c41a4f2ba0e0",
  "kg_version": "20260917T090000Z-phase09",
  "version_status": "active",
  "nodes": [],
  "edges": [],
  "node_count": 0,
  "relation_count": 0,
  "truncated": false,
  "trace_id": "77777777-7777-4777-8777-777777777770"
}

===== 场景 P1: 200 + 空图 GET /api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph =====
URL: http://127.0.0.1:8000/api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph  trace=77777777-7777-4777-8777-777777777771
HTTP status: 200
响应头 X-Trace-Id: 77777777-7777-4777-8777-777777777771
body    trace_id : 77777777-7777-4777-8777-777777777771
body:
{
  "doc_id": "fae4a287-b701-4627-9020-c41a4f2ba0e0",
  "kg_version": "20260917T090000Z-phase09",
  "version_status": "active",
  "nodes": [],
  "edges": [],
  "node_count": 0,
  "relation_count": 0,
  "truncated": false,
  "trace_id": "77777777-7777-4777-8777-777777777771"
}

===== 场景 P2: 409（已跳过 —— P0 状态不是 409，或 10.2 doc_id 不可用） =====

===== 场景 P3: 404 不存在 GET /api/v1/documents/{fake-uuid}/graph =====
伪造 UUID       : 486e7b62-6d3d-4a8b-82eb-1b06f74b8065
URL: http://127.0.0.1:8000/api/v1/documents/486e7b62-6d3d-4a8b-82eb-1b06f74b8065/graph  trace=77777777-7777-4777-8777-777777777773
HTTP status: 404
响应头 X-Trace-Id: 77777777-7777-4777-8777-777777777773
body    trace_id : 77777777-7777-4777-8777-777777777773
body:
{
  "code": "DOCUMENT_NOT_FOUND",
  "message": "Document not found",
  "detail": {
    "document_id": "486e7b62-6d3d-4a8b-82eb-1b06f74b8065"
  },
  "trace_id": "77777777-7777-4777-8777-777777777773"
}

===== 场景 P4: 跨租户 403 GET /api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph =====
URL: http://127.0.0.1:8000/api/v1/documents/fae4a287-b701-4627-9020-c41a4f2ba0e0/graph  trace=77777777-7777-4777-8777-777777777774  foreign_org
HTTP status: 403
响应头 X-Trace-Id: 77777777-7777-4777-8777-777777777774
body    trace_id : 77777777-7777-4777-8777-777777777774
body:
{
  "code": "FORBIDDEN",
  "message": "Cross-tenant access denied",
  "detail": {
    "document_id": "fae4a287-b701-4627-9020-c41a4f2ba0e0",
    "reason": "cross_tenant_access"
  },
  "trace_id": "77777777-7777-4777-8777-777777777774"
}

===== 总汇总 =====
P0_probe             PASS  status=200 trace_match=True
P1_200_empty_graph   PASS  status=200 keys_match=True version_status=True nodes_empty=True edges_empty=True truncated=True trace_match=True
P3_404_not_found     PASS  code=DOCUMENT_NOT_FOUND trace_match=True
P4_403_cross_tenant  PASS  code=FORBIDDEN reason=cross_tenant_access trace_match=True
PASS: 4 / FAIL: 0 / Total: 4

===== 分支决策提示 =====
P0 = 200：跑了 P1（200 + 空图），未跑 P2（Neo4j 有 active 版本）

===== 复制粘贴提示 =====
把上面所有输出（含 ===== 场景 X ===== 标记 + 总汇总）整段贴回给 CodeBuddy 即可。
```

---

## 4. 逐项对账表

| 场景 | 预期 | 实测 | 状态 |
|---|---|---|---|
| **P0** 前置探针 | 200 / 409 / 501 之一 + trace 三方一致 | 200 + trace 三方一致 | ✅ PASS |
| **P1** 200 + 空图 | 200 + `DOCUMENT_GRAPH_KEYS` 9 字段 + `version_status='active'` + `nodes=[]` + `edges=[]` + `truncated=false` + trace 三方一致 | 全部命中 | ✅ PASS |
| **P2** 409 KG_VERSION_NOT_ACTIVE | 409 + code 一致 + detail.status='none' + trace 三方一致 | **跳过**（P0=200，Neo4j 有 active 版本） | ➖ 跳过 |
| **P3** 404 不存在 | 404 + code='DOCUMENT_NOT_FOUND' + detail.document_id=伪造值 + trace 三方一致 | 全部命中 | ✅ PASS |
| **P4** 403 跨租户 | 403 + code='FORBIDDEN' + detail.reason='cross_tenant_access' + trace 三方一致 | 全部命中 | ✅ PASS |

---

## 5. trace_id 贯通表（4 场景 × 3 列）

| 场景 | 请求头 X-Trace-Id | 响应头 X-Trace-Id | body.trace_id |
|---|---|---|---|
| P0 前置探针 | `77777777-7777-4777-8777-777777777770` | `77777777-7777-4777-8777-777777777770` | `77777777-7777-4777-8777-777777777770` |
| P1 200 + 空图 | `77777777-7777-4777-8777-777777777771` | `77777777-7777-4777-8777-777777777771` | `77777777-7777-4777-8777-777777777771` |
| P3 404 不存在 | `77777777-7777-4777-8777-777777777773` | `77777777-7777-4777-8777-777777777773` | `77777777-7777-4777-8777-777777777773` |
| P4 403 跨租户 | `77777777-7777-4777-8777-777777777774` | `77777777-7777-4777-8777-777777777774` | `77777777-7777-4777-8777-777777777774` |

（P2 跳过，不列）

**逐字符核对**：4 场景 × 3 处 = 12 处全部字符级一致 ✅

---

## 6. 关键发现

1. **P1 字段集严格等于 `DOCUMENT_GRAPH_KEYS` 9 字段**（`tests/test_graph_and_agent_routes.py:35-45`）：`doc_id, kg_version, version_status, nodes, edges, node_count, relation_count, truncated, trace_id`——**不多不少**，契约零漂移
2. **`version_status = "active"` + `kg_version = "20260917T090000Z-phase09"`**：Neo4j **存在 active 版本**，P2（409）分支需主动改状态才可触发
3. **无 Document 节点 → 200 空图**（非 404/500/501）：Cypher 第一行 `MATCH` 非 OPTIONAL → 空结果集 → 服务层 line 357-358 静默返回 `([], [], False)` → 路由层 200 空图。**符合设计意图**（路由层不区分 Neo4j 有/无 Document 节点）
4. **PG 状态机独立**：10.2 doc_id `status='completed'` 说明 PDF 解析链路跑通，但 Neo4j 子图为空——印证 Document/Chunk 节点属 v1.1.0 缺口（MinerU + LangExtract 接入后才填）
5. **编码问题**：PowerShell 5.1 + Tee-Object 按 GBK 解码 Python UTF-8 stdout，导致中文标题乱码。**关键数据全 ASCII 不影响验收**，下次修法：脚本开头 `sys.stdout.reconfigure(encoding='utf-8')` 或 PowerShell 先 `chcp 65001`。记入 v1.1.0

---

## 7. 已知 gap（v1.1.0 待办）

| 项 | 触发条件 | 优先级 | 备注 |
|---|---|---|---|
| **G1** 200 + 有 nodes/edges | Neo4j 有 Document/Chunk/Entity fixture | 中 | `import_to_neo4j.py` 不创建 Document 节点（设计决定），需 v1.1.0 接入 MinerU + LangExtract 后做端到端联调 |
| **G4** 501 Neo4j 不可用 | Neo4j 不可达 | 低 | 用户明示不测；501 语义已在阶段零 C 批次单测覆盖（`test_graph_route_501_when_neo4j_unreachable` 等） |
| **stdout 编码** | PowerShell 5.1 + Tee-Object + Python UTF-8 | 低 | 修法 1：`sys.stdout.reconfigure(encoding='utf-8')`；修法 2：PowerShell `chcp 65001` |
| **MinerU 真实解析** | v1.1.0 接入后 | 高 | 10.2 doc_id `status='completed'` 但骨架版返空 result；接入 MinerU 后应填 Chunk/Entity |

---

## 8. 契约缺口

**无**

`/documents/{id}/graph` 响应字段集与 `contracts/openapi.yaml` 的 `DocumentGraphResponse`（`app/schemas/document.py:147-201`）**完全对齐**。错误响应（404/403）的 `code / message / detail / trace_id` 字段集与全局错误契约一致。

---

## 9. 未触碰项合规确认

| 项 | 状态 |
|---|---|
| `backend/app/**` | 未触碰 |
| `frontend/**` | 未触碰 |
| `contracts/openapi.yaml` | 未触碰 |
| `prompts/**` | 未触碰 |
| `backend/CODEBUDDY.md` | 未触碰 |
| `backend/.env.development` | 未触碰 |
| `changes/Sprint4.10.3/probe_graph.py` | 10.3 新增（与 10.2 模式一致） |
| `changes/Sprint4.10.3/probe-output.log` | 10.3 新增（用户执行产物） |
| `changes/Sprint4.10.3/integration-log.md` | 10.3 新增（本文件） |

未跑 `npm run gen:api`（未改契约，无需重生 TS 类型）。

---

## 10. 下一步（10.4 /agent/query）

- 目标端点：`POST /api/v1/agent/query`（Sprint 3 阶段九契约）
- 关键前置核实：`AgentService.query` 与 DeepSeek API 的接入路径
- 预期场景：
  - 200 + answer + citations + kg_version + kg_nodes + kg_relations + token_usage + refused=false（用真实问题）
  - 200 + refused=true + refusal_reason='no_grounded_evidence'（Neo4j 空图 + DeepSeek 可达）
  - 501 NOT_IMPLEMENTED（DeepSeek 不可达 / 凭据缺失——按用户偏好决定是否测）
  - 422 校验失败（缺 question 字段 / question 过长）
  - 403 跨租户（如适用）
- 复刻 10.3 probe 模式（UV 路径 + Python requests + trace 命名空间 `88...` 系列）
- 不测项：v1.1.0 待办补全

---

## 11. 收尾确认

- 本批 4/4 PASS，**`/graph` 端点契约一致性验证通过**
- 与 10.2（upload + status）合计 10/10 PASS
- v1.0.0 收尾阶段：M1 接入 + Neo4j 子图查询契约闭环
- v1.1.0 缺口清单（§7）已留位

**批次结束。**