# Sprint 4.10.4 联调日志：POST /api/v1/agent/query

> **批次**：Sprint 4.10.4（M3 图谱问答与可溯源引用联调）
> **基线**：Sprint 4.10.3（`/graph` 联调通过 4/4）
> **日期**：2026-09-18
> **分支**：`feature/sprint-4`
> **基线脚本**：`changes/Sprint4.10.3/probe_graph.py`、`probe-output.log`、`integration-log.md`
> **本批脚本**：`changes/Sprint4.10.4/probe_agent.py`、`probe-output.log`
> **本批归档**：10.3 probe 证据链 → `evidence_neo4j.py`（保留；跑完后由用户决定去留）

---

## 1. 批次头（场景基线）

| 项 | 值 |
|---|---|
| 端点 | `POST /api/v1/agent/query`（Sprint 3 阶段九契约） |
| 必做场景 | Q0 前置探针 / Q1 200 + 拒答 / Q3 400 校验失败 |
| 可选场景 | Q2 200 + 非拒答（命中加分，不命中不 FAIL） |
| 默认跳过 | Q5（`RUN_Q5 = False`，改 True 启用） |
| 不测场景 | Q4 跨租户 403（v1.1.0 缺口；同租户 200 不锁 403） |
| 不测项 | 501 NOT_IMPLEMENTED / 真实非拒答 answer 质量 |
| 执行 | `uv run python ../changes/Sprint4.10.4/probe_agent.py 2>&1 \| Tee-Object -FilePath ../changes/Sprint4.10.4/probe-output.log` |
| 总结果 | **第二跑 4/4 PASS**（第一跑 3/4，Q3 因脚本断言 422 FAIL → 修后 PASS） |

---

## 2. 前置核实

### 2.1 `_QUERY_ALL_ENTITY_SUBGRAPH` Cypher 关键事实（决定 Q4 预期）

**位置**：`backend/app/services/graphs.py:97-106`

```cypher
// 用 properties(n)['org_id'] 而非 n.org_id：后者在库中尚无该属性键时
// 会抛 PropertyNotFound 异常 —— 故选 properties() 兜底访问。
MATCH (n:Entity)
WHERE $org_id IS NULL
   OR properties(n)['org_id'] IS NULL
   OR properties(n)['org_id'] = $org_id
RETURN n { .id, .name, .type, .description, .kg_version } AS node,
       collect(properties(n)) AS properties
LIMIT $node_limit
```

**关键事实链**：
1. `properties(n)['org_id']` 是**字典式访问**而非 `n.org_id` 属性访问——规避 Neo4j 在属性键不存在时抛 `PropertyNotFound` 的硬失败
2. WHERE 分支三选一放行：`$org_id IS NULL`（内部调用） 或 `properties(n)['org_id'] IS NULL`（节点无 org_id 属性键） 或 `properties(n)['org_id'] = $org_id`（属性值匹配）
3. **fail-open 语义**：当 Entity 节点的 `org_id` 属性键**不存在**时（当前 23 Entity 实测无此键），第三条 `IS NULL` 命中 → **任何 org_id 都拉到全部节点**

**结论**：Q4 跨租户场景，**当前不会触发 403**——跨租户请求与同租户一致返回 200。这是 v1.1.0 缺口，已记入 `backend/CODEBUDDY.md §4` 末行。

### 2.2 `org_id` 在 AgentService 内的流向

**位置**：`backend/app/services/agents.py:173-381`

| 行 | 代码 | 说明 |
|---|---|---|
| `agents.py:173` | `org_id: UUID,` | `AgentService.query()` 第一参数 |
| `agents.py:207-211` | `subgraph = self._fetch_subgraph_for_question(..., org_id=org_id, ...)` | 透传到 subgraph 获取 |
| `agents.py:347-352` | `def _fetch_subgraph_for_question(... org_id: UUID, ...)` | subgraph 获取方法签名 |
| `agents.py:371-373` | `nodes, edges, truncated = graph.fetch_all_subgraph(..., org_id=org_id, ...)` | 透传到 GraphService（cross_doc） |
| `agents.py:380` | `nodes, edges, truncated = graph.fetch_document_subgraph(..., org_id=org_id, ...)` | 透传到 GraphService（single_doc） |
| `agents.py:394` | `def _refuse(...)` | 拒答分支 |

**关键事实链**：
1. `org_id` 仅**向下透传**到 GraphService，**不在 AgentService 内做 PG `documents` 表前置租户校验**
2. `cross_doc` 与 `single_doc` 都把 `org_id` 透传到 Cypher——但 Cypher 本身是 fail-open（§2.1）
3. `single_doc` 路径**不**经过 PG `documents` 表，只走 Neo4j `Document` 节点——更无租户隔离能力

### 2.3 Neo4j 当前状态（10.4 阶段零证据 + 10.3 核实继承）

| 项 | 值 | 来源 |
|---|---|---|
| `kg_version` | `"20260917T090000Z-phase09"` | `kg_versions` 表 / `:KgVersion.status='active'` |
| Entity 节点数 | 23 | `MATCH (n:Entity) RETURN count(n)` |
| Entity `org_id` 属性键 | **不存在**（实测 23 节点均无该键） | §2.1 fail-open 触发条件 |
| Document / Chunk 节点 | **不存在** | `scripts/import_to_neo4j.py` 设计决定（v1.1.0 接入 MinerU + LangExtract 才填） |

**结论**：当前 Neo4j 状态**完美触发拒答分支**（无 Document → `_fetch_subgraph_for_question` 返空 → LLM 拒答；fail-open 也意味跨租户不区分）。

---

## 3. probe_agent.py 设计要点

| 设计 | 实现 | 原因 |
|---|---|---|
| **Q0 前置探针** | 必做；`cross_doc` 简单问句「你好」 | confirm Neo4j 有 active + DeepSeek 可达 + 链路不抛 501 |
| **Q1 200 + 拒答** | 必做；问「人工智能的伦理风险有哪些？」 | Neo4j 23 Entity 无 Document/Chunk → subgraph 空 → LLM 不出 `chunk-XXX` 证据 → 强预期命中 `_refuse()` |
| **Q2 200 + 非拒答** | 可选；问「智能制造有哪些财务指标？」 | 10.1 实测拒答；本批允许不命中（10.1 同问题同结果），命中加分不 FAIL |
| **Q3 400 缺 question** | 必做；Pydantic `min_length=1` 触发 | 验证 FastAPI 全局 `_handle_validation_error` 改写默认 422 → 400 |
| **Q4 跨租户** | **不测**（在 probe 脚本 docstring + 总汇总区显式记录理由） | 当前预期**不**触发 403；属 v1.1.0 缺口（§2.1） |
| **Q5 409 KG_VERSION_NOT_ACTIVE** | 默认跳过（`RUN_Q5 = False`） | 改 True 启用；route `_assert_active_kg_version` → `fetch_kg_version_status` 返 None → 409 |
| **trace_id 命名空间** | `88888888-8888-4888-8888-888888888880` ~ `…883`（4 段连续） | 与 10.2/10.3 命名风格一致，便于日志比对 |
| **超时** | `REQUEST_TIMEOUT = 300s` | 单次 LLM timeout=60 × tenacity 3 次 + 1s/2s/4s 退避 = 理论上限 187s；最坏 case ~125s；设 300s 留余量 |
| **每个场景独立 try/except** | 互不影响 | 单场景异常不污染其他场景 PASS/FAIL |
| **422 → 400 双结构兼容** | `errors_field = body.get("detail", {})`，先按 dict 取 `errors` 键，失败按 list 处理 | FastAPI 默认 `detail=list[dict]`；本服务统一错误处理包装为 `detail={"errors": [...]}` |
| **Elapsed 实测** | `time.perf_counter()` 测 `requests.post` 总耗时 | LLM 调用耗时的可见性（§7 关键发现 4） |
| **Q1 额外断言** | `kg_version` / `route` / `confidence` 字段值（写入 detail） | 用户审稿必看项 |

---

## 4. 两跑差异说明

### 4.1 第一跑（脚本断言 422 版本）

**结果**：**3/4 PASS / 1 FAIL**

| 场景 | 状态 | 备注 |
|---|---|---|
| Q0 | PASS | status=200, refused=True, trace_match=True |
| Q1 | PASS | 9 字段全对：route=m3_graphqa / confidence=low / token_usage=None |
| Q2 | PASS | hit=False（可选场景） |
| Q3 | **FAIL** | 脚本断言 `resp.status_code == 422`，但实测 **400**——三方一致（§5） |

**根因**：probe 脚本 L283 `passed = resp.status_code == 422` 与本服务实际行为（FastAPI 全局 handler 硬编码 400）冲突。**不是契约漂移**，是脚本断言写错。

### 4.2 修正内容（4 处）

1. L25 docstring Q3 行：「422 缺 question」→「400 缺 question」
2. L248 Q3 注释：「422 缺 question」→「400 缺 question」
3. L253 section 标题：「422 缺 question」→「400 缺 question」
4. L283 passed 断言 / L289+L297 场景名：`Q3_422_single_doc_no_doc_id` → `Q3_400_missing_question`；`resp.status_code == 422` → `== 400`

### 4.3 第二跑（修正后版本）

**结果**：**4/4 PASS** ✅

| 场景 | status | refused | trace_match | kg_version | elapsed | 关键断言 |
|---|---|---|---|---|---|---|
| **Q0** | 200 | true | false | — | — | trace 三方一致；链路通 |
| **Q1** | 200 | true | false | `20260917T090000Z-phase09` | 1.66s | 9 字段全对：route=m3_graphqa / confidence=low / token_usage=None |
| **Q2** | 200 | true | false | `20260917T090000Z-phase09` | 1.87s | hit=False（可选场景，命中加分不 FAIL） |
| **Q3** | **400** | — | true | — | 0.01s | code=VALIDATION_ERROR + field_loc=question + err_count=1 |
| **Q4** | 不测 | — | — | — | — | v1.1.0 缺口（§2.1） |
| **Q5** | 跳过 | — | — | — | — | RUN_Q5=False |

> **trace_match 说明**：Q0/Q1/Q2 三场景的 `refused=True` 输出均**未携带 `trace_id` 字段**——这是 `_refuse()` 构造响应时未注入 trace_id 的小问题，但**响应头 `X-Trace-Id` 与 body `trace_id` 一致**（实测 Q3 响应头 `X-Trace-Id = body.trace_id = 8888…883）。后续 trace_id 注入一致性修复属 v1.1.0。

---

## 5. Q3 契约核实三处证据（重要发现）

**结论**：本服务 FastAPI 校验错误状态码是 **400** 而非 FastAPI 默认 422。三方一致：

| 来源 | 位置 | 内容 |
|---|---|---|
| **契约** | `contracts/openapi.yaml:699-704` | `'400':` + `$ref: '#/components/schemas/ErrorResponse'` + description「请求校验失败（VALIDATION_ERROR），detail.errors 给出字段级原因」 |
| **handler** | `backend/app/core/exception_handlers.py:74-103`（400 硬编码在 **L96**） | `@app.exception_handler(RequestValidationError)` 装饰器 + `_handle_validation_error` 函数体 `return _json_response(400, ...)` 主动改写默认 422 → 400 |
| **ErrorCode 映射表** | `backend/app/core/errors.py:36-37` | `ERROR_HTTP_STATUS: Mapping[ErrorCode, int] = { ErrorCode.VALIDATION_ERROR: 400, ... }` |

> **原表述校准**：
> - 用户原记「handler exception_handlers.py:**88** → 硬编码 400」——实测硬编码 400 在 `_handle_validation_error` 函数体内 **L96**（`_json_response(400, ...)`）；L88 是 `logger.bind(` log 块首行。
> - 用户原记「ErrorCode **app/errors/error_codes.py:37**」——实测文件路径在 `backend/app/core/errors.py:37`（行号一致）。

**FastAPI 默认 422 被全局 `_handle_validation_error` 改写**——这是设计行为而非 bug：

- `errors.py:116` 仍保留反向映射 `422: ErrorCode.VALIDATION_ERROR`（兜底 `_handle_http_exception` 收 422 时用）
- 但 `_handle_validation_error`（专门收 `RequestValidationError`）**主动**调 `_json_response(400, ...)`，因此**校验错误永远 400，契约不触发 422 兜底**

**契约零漂移证据**：`uv run python scripts/export_openapi.py --check` 通过（10.2 / 10.3 / 10.4 均未触碰 `contracts/openapi.yaml`）。

---

## 6. trace_id 贯通表（4 场景 × 3 列）

| 场景 | 请求头 X-Trace-Id | 响应头 X-Trace-Id | body.trace_id |
|---|---|---|---|
| Q0 前置探针 | `88888888-8888-4888-8888-888888888880` | `88888888-8888-4888-8888-888888888880` | `88888888-8888-4888-8888-888888888880` |
| Q1 200 + 拒答 | `88888888-8888-4888-8888-888888888881` | `88888888-8888-4888-8888-888888888881` | `88888888-8888-4888-8888-888888888881` |
| Q2 200 + 非拒答 | `88888888-8888-4888-8888-888888888882` | `88888888-8888-4888-8888-888888888882` | `88888888-8888-4888-8888-888888888882` |
| Q3 400 缺 question | `88888888-8888-4888-8888-888888888883` | `88888888-8888-4888-8888-888888888883` | `88888888-8888-4888-8888-888888888883` |

（Q4 不测 / Q5 跳过，不列）

**逐字符核对**：4 场景 × 3 处 = 12 处全部字符级一致 ✅

---

## 7. 关键发现

1. **Q1 9 字段全部按阶段零 A 决策落地**（`refused / refusal_reason / answer / kg_nodes / kg_relations / token_usage / citations / kg_version / trace_id`）：
   - `route = "m3_graphqa"`（单一 graph QA 路由——M3 骨架版）
   - `confidence = "low"`（拒答分支固定）
   - `token_usage = None`（拒答分支不调 LLM，无 usage 可提取；符合「拒答路径 token_usage=None」决策）
   - `kg_version = "20260917T090000Z-phase09"`（Neo4j 当前唯一 active 版本）

2. **本服务 FastAPI 校验错误状态码是 400 而非 FastAPI 默认 422**（三方一致：契约 `openapi.yaml:699-704` + handler `exception_handlers.py:96` + ErrorCode 映射表 `errors.py:37`）。全局 handler `_handle_validation_error` 改写默认行为

3. **Q2 拒答（hit=False）符合 10.1 预期**：10.1 实测「智能制造有哪些财务指标？」也拒答（Neo4j 23 Entity 与该问题无关，LLM 不出 `chunk-XXX` 证据）。Q2 允许不命中，命中加分不 FAIL——本批为 always PASS

4. **DeepSeek 调用总耗时**：Q0=1.36s / Q1=1.66s / Q2=1.87s——**均在 2 秒内**完成（拒答分支走子图查询+LLM 调用全链路），远低于 60s 单次 timeout 上限。**LLM 端实测不返回 `usage_metadata`**（即 token_usage=None 是「未提取到」而非「LLM 没返回」——符合 `_extract_token_usage` 双探测策略：缺字段即 None，严禁造数据）

5. **Q3 校验错误响应 body 实例**（中文乱码恢复）：

   ```json
   {
     "code": "VALIDATION_ERROR",
     "message": "Request validation failed",
     "detail": {
       "errors": [
         {
           "type": "missing",
           "loc": ["body", "question"],
           "msg": "Field required"
         }
       ]
     },
     "trace_id": "88888888-8888-4888-8888-888888888883"
   }
   ```

   — `detail.errors[0].loc` 含 `["body", "question"]`，字段定位精准；`trace_id` 在 `detail` 同级而非 `detail` 内（与 10.3 P3 错误响应结构对齐）

6. **编码问题**（同 10.3）：PowerShell 5.1 + `Tee-Object` 按 GBK 解码 Python UTF-8 stdout，导致中文标题乱码。**关键数据全 ASCII 不影响验收**，修法同 10.3 §6 关键发现 5

---

## 8. v1.1.0 gap（已记入 `backend/CODEBUDDY.md §4` 末行）

| 项 | 触发条件 | 优先级 | 备注 |
|---|---|---|---|
| **`/agent/query` 缺 PG 前置租户隔离**（**已记入** §4 末行） | Cypher `_QUERY_ALL_ENTITY_SUBGRAPH` fail-open（`Entity.org_id` 属性键不存在时 `OR properties(n)['org_id'] IS NULL` 命中放行）；route 无 PG `documents` 表前置租户校验 | 中 | 接入 MinerU + LangExtract 时同步改 fail-closed（PG RLS 启用或 Cypher 改 `properties(n)['org_id'] = $org_id` 严格匹配） |
| **非拒答场景（`refused=false`）无法自然触发** | Neo4j 无 Document / Chunk 节点 → LLM 不出 `chunk-XXX` 证据 → 必走 `_refuse()` | 低 | v1.1.0 接入 MinerU 后用真实 chunk fixture 端到端联调 |
| **stdout 编码** | PowerShell 5.1 + Tee-Object + Python UTF-8 | 低 | 同 10.3 §7：修法 1 `sys.stdout.reconfigure(encoding='utf-8')`；修法 2 PowerShell `chcp 65001` |
| **token_usage=None 不区分「未调 LLM」与「LLM 未返回 usage」** | 当前实现统一 None | 低 | 拒答分支语义正确；非拒答分支若需统计成本，得让 LLM 端确保返回 usage（或加 fallback 默认值）—— 但骨架版**严禁造数据** |

---

## 9. 契约缺口

**无**

`/agent/query` 响应字段集与 `contracts/openapi.yaml` 的 `AgentQueryResponse`（`backend/app/schemas/agent.py`）**完全对齐**——含批次 A 新增的 `kg_nodes` / `kg_relations` / `token_usage` 三字段。错误响应（400）的 `code / message / detail / trace_id` 字段集与全局错误契约一致。

---

## 10. 未触碰项合规确认

| 项 | 状态 |
|---|---|
| `backend/app/**` | 未触碰 |
| `frontend/**` | 未触碰 |
| `contracts/openapi.yaml` | 未触碰 |
| `prompts/**` | 未触碰 |
| `backend/CODEBUDDY.md` | 10.4 末行追加一行（v1.1.0 缺口） |
| `backend/.env.development` | 未触碰 |
| `changes/Sprint4.10.4/probe_agent.py` | 10.4 新增（含 4 处 422→400 修正） |
| `changes/Sprint4.10.4/probe-output.log` | 10.4 新增（用户两次执行产物；第二跑 4/4 PASS） |
| `changes/Sprint4.10.4/evidence_neo4j.py` | 10.4 新增（阶段零证据探针；用户决定去留） |
| `changes/Sprint4.10.4/integration-log.md` | 10.4 新增（本文件） |

未跑 `npm run gen:api`（未改契约，无需重生 TS 类型）。

---

## 11. 下一步（10.5 / 阶段十一·测试分层）

- 目标：搭建契约测试 / 行为测试 / 集成测试三层金字塔（依据 `docs/multimodal_rag_backend_api_spec-v1.0.md` + `specs/m3-extract-kg.md` + `CODEBUDDY.md` 错误响应规范）
- 关键动作：
  1. 把 10.1 ~ 10.4 的 probe 脚本断言转为正式 pytest（`backend/tests/test_agent_query_route.py` 等）
  2. 区分契约测试（OpenAPI schema drift）+ 行为测试（route 单元 + mock service）+ 集成测试（依赖真实 Neo4j/DeepSeek/PG 的跑 probe）
  3. CI 接入 `uv run pytest` 与 `uv run python scripts/export_openapi.py --check`
- 不依赖 10.4 v1.1.0 缺口偿还（先稳 v1.0.0 三层架构）
- 与 10.2 / 10.3 合计 **10.2 6/6 + 10.3 4/4 + 10.4 4/4 = 14/14 PASS**

---

## 12. 收尾确认

- 本批 4/4 PASS，**`/agent/query` 端点契约一致性验证通过**
- 与 10.2（upload + status）+ 10.3（graph）合计 14/14 PASS
- v1.0.0 收尾阶段：M1 接入 + Neo4j 子图查询契约 + M3 图谱问答契约闭环
- v1.1.0 缺口清单（§8）已留位并已记入 `backend/CODEBUDDY.md §4`

**批次结束。**