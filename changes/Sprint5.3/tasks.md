# Sprint 5 批次 B · tasks

> 收口纪律（沿用 A2）：每勾一项必须跑对应门禁；commit 信息走 Conventional Commits。

## 0. 起点门禁（确认基线）

- [x] **T0.1** 确认 `feature/sprint-5` 分支 / working tree clean / 基线 `3562c73`
- [x] **T0.2** 跑四道门禁基线：`ruff check`/`format --check` / `pytest` / `check_seams` / `export_openapi --check` 全绿（ERROR=0、pytest 171）

## 1. 脚手架：目录、配置、Prompt 入口

- [x] **T1.1** 新建 `backend/app/services/extraction/__init__.py`（占位：导出版本/错误）
- [x] **T1.2** 新建 `backend/app/services/kg/__init__.py`（占位：导出 builder/versioning）
- [x] **T1.3** `backend/app/core/config.py` 新增 9 个 settings（每个有 `@property` 间接消费者亦可）：
  - `extraction_provider: str = "langextract"`
  - `extraction_max_chars_per_chunk: int = 4000`
  - `extraction_max_entities_per_doc: int = 500`
  - `extraction_max_relations_per_doc: int = 1000`
  - `extraction_prompt_version: str = "kg_extraction_v1"`
  - `kg_build_batch_size: int = 500`
  - `kg_version_strategy: str = "per_org"`（仅 `per_org` 一档；后续 `global` 留 Pro）
  - `agent_fail_closed: bool = True`
  - `pipeline_stages` 默认值扩为 `"document.parse,document.extract,kg.build"`
- [x] **T1.4** `prompts/kg_extraction_v1.md`（E1 实体 + E2 关系 共用 prompt v1 模板，含 few-shot 框架）
- [x] **T1.5** `backend/app/prompts/prompt_loader.py` 增加 v1 入口：`load_kg_extraction_v1()`，模板路径 `kg_extraction_v1.md`
- [x] **T1.6** 验证：`ruff check .` / `ruff format --check .` / `pytest` 全绿

## 2. ORM：KgVersion 真源表

- [x] **T2.1** `backend/app/db/models.py` 新增 `KgVersion`：
  - `__tablename__ = "kg_versions"`
  - 字段：`id` (Uuid PK) / `org_id` (Uuid, NOT NULL, indexed) / `version` (String(64), NOT NULL) / `status` (String(16), NOT NULL, in {pending,building,ready,failed}) / `source_doc_ids` (JSON, NOT NULL) / `entity_count` (Int, NOT NULL, default=0) / `relation_count` (Int, NOT NULL, default=0) / `created_at` / `updated_at` / `ready_at` (nullable) / `trace_id` (Uuid, NOT NULL, indexed)
  - `__table_args__`：复合索引 `ix_kg_versions_org_id_status`、`CheckConstraint(status IN ...)`
  - 新增 `DOCUMENT_EXTRACT_STATUS_VALUES` 等常量
- [x] **T2.2** `backend/app/db/session.py` `init_db()` 自动纳入新表（沿用 `Base.metadata.create_all` 模式）
- [x] **T2.3** 验证：新增 `tests/test_kg_versions_orm.py`（约束 / 默认值 / 状态机合法值），pytest 全绿

## 3. 服务层：extraction（LangextractClient）

- [x] **T3.1** `backend/app/services/extraction/langextract.py`：
  - `LangextractError(Exception)` 业务错误
  - `LangextractClient` 类，构造参数来自 settings；方法 `extract_entities_relations(*, document_id, full_md_text, trace_id) -> ExtractionResult`（entities: list[dict], relations: list[dict]）
  - 默认 **mockable**——`_default_call_llm` 用占位生成器（按字符切分 + 简单模板填充）保证零外部依赖；真实 `langextract` SDK 留 `_evaluate_client_call_llm`（带 `_EVALUATE_GATED` 提示与 TODO 注释）
  - 严格遵守 `extraction_max_*` 上限裁剪
- [x] **T3.2** `backend/app/services/extraction/__init__.py` 导出 `LangextractClient` / `LangextractError` / `ExtractionResult`
- [x] **T3.3** `tests/test_langextract_client.py`：mockable 路径（无 LLM）+ 上限裁剪 + 异常透传 + trace_id 透传，pytest 全绿

## 4. 服务层：kg（KgBuilder + ThreeStageKgBuilder + Versioning）

- [x] **T4.1** `backend/app/services/kg/versioning.py`：
  - `KgVersioningService` 封装 `kg_versions` 表的 CRUD
  - 方法：`create_pending(org_id, source_doc_ids, trace_id)` / `mark_building(version_id)` / `mark_ready(version_id, entity_count, relation_count)` / `mark_failed(version_id, error_code, error_detail)` / `get_active(org_id) -> KgVersion | None`
- [x] **T4.2** `backend/app/services/kg/builder.py`：
  - `KgBuilder` 抽象协议（不继承 `ABC`——`Protocol` 形式），`build(*, kg_version, entities, relations, org_id, trace_id) -> BuildStats`
  - `ThreeStageKgBuilder` 实现：
    - **stage-1**：在 Neo4j 上 `MERGE (:KgVersionMirror {version: $v, status: 'ready', org_id: $org, trace_id: $t})` 并给所有节点 / 关系类型 `MERGE` 索引约束（幂等）
    - **stage-2**：批量 `UNWIND $entities AS e MERGE (n:Entity {id: e.id, kg_version: $v}) ON CREATE SET n = e` 分批（按 `kg_build_batch_size`）
    - **stage-3**：`UNWIND $relations AS r MATCH (a {id: r.source}), (b {id: r.target}) MERGE (a)-[rel:RELATION {kg_version: $v}]->(b)` 分批
  - Neo4j 驱动复用 `GraphService._driver`（**不**重建连接）
- [x] **T4.3** `backend/app/services/kg/__init__.py` 导出 `KgBuilder` / `ThreeStageKgBuilder` / `KgVersioningService`
- [x] **T4.4** `tests/test_kg_builder.py`：stage-1/2/3 三段被独立 mock，验证调用顺序与批切片；Neo4j 不可用 → `GraphUnavailableError` 透传
- [x] **T4.5** `tests/test_kg_versioning.py`：状态机迁移 + 复合索引查询路径

## 5. 任务执行体：document.extract 与 kg.build

- [x] **T5.1** `backend/app/tasks/registry.py` 新增 `document_extract_executor(spec)`：
  - 真实推进 `documents.extract_status` 字段；初始新增列（**预留**，不进契约）
  - 状态机：`pending → processing → completed`，失败 → `failed` + `error_code` / `error_detail`
  - tenacity 重试（沿用 `_RETRYABLE_EXCEPTIONS` + `task_retry_*` 配置）
  - 重试计数回写 `documents.retry_count`（沿用 B1 修复路径）
  - 输入：`full.md`（来自 storage `build_parse_artifact_key(..., "full.md")`），输出：entities/relations JSON 入 storage `build_extract_artifact_key(..., "entities.json"/"relations.json")`
  - **`_do_extract`** 真实执行：调 `LangextractClient.extract_entities_relations`；mockable 入口
- [x] **T5.2** 同文件新增 `kg_build_executor(spec)`：
  - 状态机：`pending → building → ready`；失败 → `failed`
  - 输入：storage 里 `entities.json` / `relations.json`；输出：Neo4j 实体 / 关系
  - 推进 `kg_versions` 表：先 `mark_building`、成功后 `mark_ready`、失败 `mark_failed`
  - 重试与失败处理同 `document_parse_executor`
- [x] **T5.3** `EXECUTOR_REGISTRY` 注册两条新阶段
- [x] **T5.4** `tests/test_document_extract_executor.py`：状态机 / retry / mockable / 失败落库
- [x] **T5.5** `tests/test_kg_build_executor.py`：状态机 / kg_versions 表联动 / 三段式 mock 校验

## 6. Agent fail-closed（ADR-0003 强化）

- [x] **T6.1** `backend/app/services/agents.py` 在 `_validate_subgraph` 之后新增 PG cross-check：
  - 取子图里出现的所有 `source_doc_ids`（来自 Neo4j 节点 `Document.id`），逐个查 PG `documents` 表 `org_id`
  - 任一 `org_id != current_org_id` → 抛 `AgentUnavailableError("KG_TENANT_LEAK")`（路由层 → 403 FORBIDDEN）
  - 受 `settings.agent_fail_closed` 控制：`False` 时仅日志告警，不阻塞（默认 `True`）
- [x] **T6.2** `backend/app/api/v1/routes/agent.py` 路由层把 `AgentUnavailableError("KG_TENANT_LEAK")` 转 `403`
- [x] **T6.3** `backend/app/core/errors.py` 新增错误码 `KG_TENANT_LEAK`
- [x] **T6.4** `tests/test_agent_fail_closed.py`：跨租户子图 → 403；同租户正常；fail-closed off 路径

## 7. E1/E2 评测模板

- [x] **T7.1** `prompts/kg_extraction_v1.md`：E1 实体 + E2 关系 共用 prompt，含 few-shot 占位
- [x] **T7.2** `backend/tests/fixtures/eval_e1.jsonl` ≥ 2 条样例（输入短文本 + 期望实体）
- [x] **T7.3** `backend/tests/fixtures/eval_e2.jsonl` ≥ 2 条样例（输入短文本 + 期望关系）
- [x] **T7.4** `tests/test_extraction_prompt_v1.py`：模板加载 + 占位替换 + 评测 fixture 解析
- [x] **T7.5** `tests/test_prompt_loader.py` 增加 `kg_extraction_v1` 用例

## 8. 文档侧最小同步（不擅自动 frontend/）

- [x] **T8.1** `backend/app/api/v1/responses.py` `TaskStatusResponse` 增加可选字段 `extract_status` / `kg_build_status`（**可选**，不影响契约）
- [x] **T8.2** `contracts/openapi.yaml` 验证：`export_openapi --check` 仍无 diff（如有 diff 则整改）
- [x] **T8.3** `changes/Sprint5.3/integration-log.md` 完整收口（§2 改名 / §3 存量库重建 / §4 验证矩阵 / §5 ADR 旁证）

## 9. 收尾四道门禁 + commit

- [x] **T9.1** `uv run python scripts/check_seams.py` → ERROR 0
- [x] **T9.2** `uv run python scripts/export_openapi.py --check` → 无 diff
- [x] **T9.3** `uv run python -m pytest -q` → 全绿（≥ 200 passed）
- [x] **T9.4** `uv run ruff check .` + `uv run ruff format --check .` → 全过
- [x] **T9.5** 提交：`feat(backend,extraction): langextract client + document.extract stage`
- [x] **T9.6** 提交：`feat(backend,kg): three-stage kg builder + kg_versions PG true source`
- [x] **T9.7** 提交：`feat(backend,agent): fail-closed cross-tenant guard`
- [x] **T9.8** 提交：`feat(prompts): kg_extraction_v1 E1/E2 template + fixtures`
- [x] **T9.9** 提交：`chore(sprint5.3): integration log + readme link`