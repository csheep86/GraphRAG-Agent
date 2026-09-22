# Integration Log: Sprint5.3 — 在线抽取建图（批次 B）

> 上游：plan §4.2 批次 B；ADR-0002 §3.1/§3.2（三段式写入 + kg_versions PG 真源）、ADR-0003 §4（fail-closed）、ADR-0004 §2.1（接缝登记）。
> 分支：`feature/sprint-5`；上游批次：Sprint5.2（集成接缝收口，见 `changes/Sprint5.2/integration-log.md`）。

## 1. 变更清单

| 落点 | 说明 |
|---|---|
| `app/services/extraction/{__init__,langextract}.py` | `LangextractClient`：接缝 3 抽取档位（`extraction_provider` 唯一消费点，唯一档位 `langextract`）；默认 mockable 正则抽取器（ORG/DATE/MONEY + PARTY_TO 共现），LLM 真调用留位显式报错；chunk 切分（`extraction_max_chars_per_chunk`）+ char_offset 反推；实体/关系上限裁剪（confidence 降序）；关系端点漂移丢弃（与 stage-3 MATCH 语义一致） |
| `app/services/kg/{__init__,versioning,builder}.py` | `KgVersioningService`：kg_versions 状态机（pending → building → ready/failed，ADR-0002 §3.2）；`ThreeStageKgBuilder`：ADR-0002 §3.1 三段式写入（stage-1a KgVersionMirror MERGE + 1b/1c 索引 → stage-2 实体批 → stage-3 关系批），`kg_build_batch_size` 批切片，session_factory 可注入（测试零 Neo4j 依赖） |
| `app/tasks/registry.py` | 登记执行体 `document_extract_executor` / `kg_build_executor`（与 `document.parse` 同模式：tenacity 指数退避 + 阶段级失败落库）；`_RETRYABLE_EXCEPTIONS` 扩 `LangextractError` / `GraphUnavailableError`；kg.build 复用 payload 指定 kg_version_id 时不重复建版本，且回填 `documents.kg_version_id` |
| `app/tasks/types.py` / `manager.py` | TaskType 扩为三段 Literal；`submit()` 经 `resolve_executor()` 分发（未知 task_type 显式失败） |
| `app/db/models.py` | 新增 `KgVersion` ORM（org_id 复合索引打头、CheckConstraint 限 status）；Document 追加 5 个阶段字段（`extract_status`/`extract_retry_count`/`kg_build_status`/`kg_build_retry_count`/`kg_version_id`）——全部 nullable、只落库、不进契约 |
| `app/services/agents.py` + `routes/agent.py` + `responses.py` + `errors.py` | fail-closed 链路：`AgentService.query` 在 LLM 装配前经 `GraphService.validate_kg_version_tenant_boundary` 校验 active kg_version 子图租户纯度；泄漏 → `AgentTenantLeakError`（`AgentUnavailableError` 子类）→ 路由层**先于父类分支**捕获转 **403 `KG_TENANT_LEAK`**；`agent_fail_closed=False` 时仅告警放行（逃生阀） |
| `prompts/kg_extraction_v1.md` | E1（实体）+ E2（关系）共用模板，占位符 `{{text}}`/`{{language}}`，经 `prompt_loader` 从文件系统加载（禁止硬编码） |
| `app/storage/__init__.py` | `build_extract_artifact_key` / `build_kg_artifact_key`（`{org_id}/{doc_id}/{extract|kg}/{filename}`） |
| `backend/app/core/config.py` | 新增 8 个 settings（见 §2），全部有消费点（check_seams Settings 44 字段 OK） |

## 2. 新增配置（`.env.example` 已同步）

| 变量 | 默认值 | 唯一消费点 |
|---|---|---|
| `EXTRACTION_PROVIDER` | `langextract` | `LangextractClient.from_settings()` |
| `EXTRACTION_MAX_CHARS_PER_CHUNK` | 4000 | 同上（chunk 切分） |
| `EXTRACTION_MAX_ENTITIES_PER_DOC` | 500 | 同上（上限裁剪） |
| `EXTRACTION_MAX_RELATIONS_PER_DOC` | 1000 | 同上（上限裁剪） |
| `EXTRACTION_PROMPT_VERSION` | `kg_extraction_v1` | 同上（prompt 加载） |
| `KG_BUILD_BATCH_SIZE` | 500 | `ThreeStageKgBuilder`（批切片） |
| `KG_VERSION_STRATEGY` | `per_org` | 同上（未支持值显式报错） |
| `AGENT_FAIL_CLOSED` | `true` | `AgentService.query`（ADR-0003 §4） |

## 3. dev.db 存量库重建说明

新增 `kg_versions` 表 + `documents` 5 列，SQLite 存量库（`backend/dev.db`）**无 ALTER 迁移**（沿用 A2 处理口径）：

```
删除 backend/dev.db → 下次启动 lifespan 自动 Base.metadata.create_all 重建
```

CI / 测试不受影响（conftest 每次用临时目录新建库）。

## 4. 契约变更（经 export_openapi 同步）

`/agent/query` 新增 **403 `KG_TENANT_LEAK`** 响应声明 + 错误码枚举扩一项。diff 共 4 处（枚举 + 描述 ×3），无既有字段变化。
**前端待办**（角色隔离，本次未动 frontend/）：`npm run gen:api` 重新生成类型（错误码枚举新增 `KG_TENANT_LEAK`）。

## 5. 验证证据（收尾门禁）

| 门禁 | 结果 | 时间 |
|---|---|---|
| `uv run ruff check .` + `format --check .` | ✅ 0 error，82 files formatted | 2026-09-21 |
| `uv run pytest -q` | ✅ **226 passed**（新增 55 例：langextract client 12 / kg_builder 10 / kg_versioning 9 / document_extract_executor 7 / kg_build_executor 5 / agent_fail_closed 6 / extraction_prompt_v1 + fixtures 6） | 2026-09-21 |
| `uv run python scripts/export_openapi.py --check` | ✅ 无 diff（重导出后复核通过；本次 diff 仅 KG_TENANT_LEAK 相关 4 处） | 2026-09-21 |
| `uv run python scripts/check_seams.py` | ✅ **ERROR 0** / WARN 6（均为未到期项：接缝 5/6/7/8，required_from ≥ 1.3.0，合规保留）；Settings 全部 44 字段有消费者；documents 8 预留字段双向判据 OK | 2026-09-21 |

### 测试隔离说明

- `ThreeStageKgBuilder` 经 `session_factory` 注入假会话（记录 Cypher + 参数），Neo4j 零依赖；
- `kg_build_executor` 以假类整体替换 `registry.ThreeStageKgBuilder`；
- fail-closed 用例对 `GraphService.fetch_active_kg_version` / `AgentService._fetch_subgraph_for_question` / `GraphService.validate_kg_version_tenant_boundary` / `AgentService._ensure_chat` 四点打桩（防本地 `.env` 配置 LLM key 时意外真实调用）；
- 既有 4 例 agent 流水线测试补边界校验打桩（批次 B 在链路中新增了必经校验点）。

## 6. 决策记录（按建议项采纳，无人值守协议）

1. **`source_doc_ids` 落库为字符串数组**：`json.dumps` 不支持 UUID 原生类型；`KgVersioningService` 入库转 str、出库转 UUID（模型注释已注明）。
2. **403 双成因合并描述**：`KG_TENANT_LEAK` 与 `FORBIDDEN` 同为 403，契约 description 合并表述，避免 last-wins 覆盖丢失语义。
3. **路由层子类陷阱**：`AgentTenantLeakError` 继承 `AgentUnavailableError`，路由 `except` 顺序必须先子类后父类（501 ≠ 数据质量事故）；已加双向守卫测试。
4. **`kg_build_executor` 回填 `documents.kg_version_id`**：无论新建还是复用 kg_version 行，统一回填（阶段列，不进契约）。
