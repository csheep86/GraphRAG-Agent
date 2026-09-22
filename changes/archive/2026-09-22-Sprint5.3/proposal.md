# Sprint 5 批次 B · 在线抽取建图（LangExtract → 三段式 Neo4j + kg_versions PG + fail-closed + E1/E2 模板）

- **状态**：Proposed
- **基线**：3562c73（Sprint 5 批次 A2 收口；四道门禁 ERROR=0、pytest 171、ruff 全过、openapi 一致）
- **目标版本**：v1.1.0
- **计划执行人**：后端开发（B）/架构（接缝登记）

## 1. 范围（做什么）

按 `docs/v1.1.0-demo-mvp-plan.md` §4.2 批次 B 推进：

| # | 子目标 | 落地形态 | 备注 |
|---|---|---|---|
| B-1 | LangExtract 抽取（实体 / 关系） | `backend/app/services/extraction/langextract.py`（仅 `langextract` 一档，**不抽象**为 provider） | 与 MineruClient 同形：具体类 + `settings.extraction_provider` 切换键；**不**进 check_seams 登记（ADR-0004 §3 第 4 条：仅"实现类 = 登记集合"才强制，**单实现**的内部类不构成接缝） |
| B-2 | `document.extract` 流水线阶段 | `backend/app/tasks/registry.py` 新增 `document_extract_executor`，串联 `parse → extract → kg.build` | 与 `document.parse` 同模板：tenacity 重试 + 状态机真实推进 + `documents.extract_status` 字段 |
| B-3 | ADR-0002 三段式 Neo4j 写入 | `backend/app/services/kg/builder.py`（`ThreeStageKgBuilder`：stage-1 schema MERGE / stage-2 batch LOAD / stage-3 cross-batch links），复用 `scripts/import_to_neo4j.py` 实战口径 | 不重写导入脚本；**抽**其核心三段为 Python 服务供执行体调用 |
| B-4 | `kg_versions` PG 真源表 | `backend/app/db/models.py` 新增 `KgVersion` ORM（id / org_id / version / status / source_doc_ids / entity_count / relation_count / created_at / updated_at / ready_at / trace_id），Neo4j 上保留 `:KgVersionMirror` 冗余镜像 | ADR-0002 §3.2 的状态机迁到 PG；Neo4j `kg_version` 标签查询降级为兜底 |
| B-5 | `kg.build` 流水线阶段 | `backend/app/tasks/registry.py` 新增 `kg_build_executor`：读 storage 里 extract 产物 → 调 KgBuilder → 写 `kg_versions.status = ready` / `failed` | 与 B-2 共用 retry 模板 |
| B-6 | `/agent/query` fail-closed | `backend/app/services/agents.py` 收紧 `_validate_subgraph`：跨租户子图（kg_version 同租户但 source_doc_ids 跨 PG `documents.org_id`）→ 抛 `AgentUnavailableError("KG_TENANT_LEAK")`，路由层转 403 | ADR-0003 强化：现有 `_validate_subgraph` 只校验 kg_version，新增 PG documents cross-check；**禁止**静默吞错 |
| B-7 | E1/E2 收口模板（评测 gold） | `prompts/kg_extraction_v1.md`（E1 实体抽取 + E2 关系抽取共用 prompt）+ `tests/fixtures/eval_e1_*.jsonl` / `eval_e2_*.jsonl`（少量评测样本） | 模板进 `app/prompts/prompt_loader.py` v1 入口；评测样本仅用于 Sprint 6+ 评测，不进契约 |
| B-8 | pipeline_stages 配置扩字 | `settings.pipeline_stages` 默认值由 `"document.parse"` 改为 `"document.parse,document.extract,kg.build"`；保留启停与顺序能力（A2 已就位） | 行为变化：上传文件后串行跑完三段才"completed"；前端状态轮询拿到的 `task_type` 序列为 parse → extract → kg.build |

## 2. 不做什么（边界纪律）

按 CODEBUDDY.md §功能预留原则 与 plan §4.4 降级预案：

- **不**新增 `ExtractionProvider` 抽象接口（与 MineruClient 同模式仅做具体类）；A2 CP 闸门「只多一层」——同一类别的"单实现 + 切换键"已在 A2 验证无需抽象。
- **不**接 LLM / LangExtract 真实云端调用（默认 mockable：空 LLM 客户端 + 假实体关系生成；评测时再切真实 `langextract` 端点）。
- **不**做 chunk 合并 / 去重（沿用 A2 §4.4 降级预案"chunk 合并外置"，留 Sprint 7+）。
- **不**做跨文档实体消解（接缝 7 留 Sprint 7 批次 B）。
- **不**做时效边 `valid_from`/`valid_to`（ADR-0004 §5 第 3 条登记 v1.5+）。
- **不**新建 `chunks` PG 表（Neo4j 上的 `(:Chunk)` 节点已由 import_to_neo4j.py 维护；本批次 LangExtract 从存储层 `full.md` 自取自切）。
- **不**动 `documents` 8 个预留字段的 nullable 与契约状态（ADR-0004 §3 第 1 条铁律）。
- **不**新增 `frontend/` 接口（仅契约暴露 `kg_versions` / `document.extract` / `kg.build` 状态字段；前端 Mock 化继续）。
- **不**扩 ADR-0004 §2.1 第 4 行登记（接缝 4 阶段命名 A2 已扩好；本批次只增阶段条目，不动接缝登记集合）。

## 3. 依赖与前置

- 已有资产：`backend/app/services/parsing/mineru.py`（同模式参照）、`scripts/import_to_neo4j.py`（三段式实战口径直接复用）、`scripts/check_seams.py`（判据 2 必须为新 settings 指明消费者）、`langextract_mvp/run_mvp.py`（E1/E2 模板对齐实测）。
- ADR：ADR-0002 §3.2（kg_version 状态机迁 PG）、ADR-0003 §4（多租户隔离）、ADR-0004 §3（接缝判据）。
- 配置：`settings.app_version` 保持 1.1.0（基线已就位）；新 settings 一律 ≤ 1.1.0 到期、必须给出消费者代码行。

## 4. 风险与兜底

- **R1 真实 LLM 不可用**：默认 mockable（fake entity/relation 生成器）；评测前临时切真实端点。
- **R2 三段式 Neo4j 大数据量内存峰值**：`settings.kg_build_batch_size` 上限（默认 500 行 / 批）+ `settings.kg_version_max_entities_per_doc`（默认 500）硬性裁剪。
- **R3 fail-closed 误杀**：触发条件**仅限** PG `documents.org_id != current_org_id`；本租户 + 邻租户对照表一致性由 `_validate_subgraph` 强校验；不在抽样路径上。
- **R4 settings 无消费者**：`check_seams.py` 判据 2 自 1.1.0 起 ERROR——新增 settings 必须在同 commit 内指出消费者代码行（行号可被脚本反向核对）。
- **R5 契约漂移**：`export_openapi.py --check` 必须无 diff；任何 `kg_versions` schema 仅落 PG 内部模型，不进 OpenAPI。

## 5. 验收（plan §4.3 + sprint-calendar §2）

| 项 | 指标 | 检验命令 |
|---|---|---|
| V1 接缝门禁 | ERROR 0 | `uv run python scripts/check_seams.py` |
| V2 契约零漂移 | 无 diff | `uv run python scripts/export_openapi.py --check` |
| V3 后端测试 | ≥ 200 passed（新增 ≥ 29） | `uv run python -m pytest -q` |
| V4 ruff 全过 | 0 错 | `uv run ruff check .` + `uv run ruff format --check .` |
| V5 流水线串行 | parse → extract → kg.build 三段 `documents` 状态真实推进；test_document_extract_executor.py + test_kg_build_executor.py 覆盖 | 见 tests/ |
| V6 fail-closed | 跨 org_id 子图 → 403；同租户同 kg_version 子图正常返回 | test_agent_fail_closed.py |
| V7 E1/E2 模板 | prompt_loader 加载 v1，fixture eval 样本 ≥ 2 / 2 | test_extraction_prompt_v1.py |

## 6. 收尾

- Conventional Commits：`feat(backend): ...` / `feat(backend,extraction): ...` / `feat(backend,kg): ...` / `feat(backend,agent): fail-closed` / `feat(prompts): kg_extraction_v1`
- `integration-log.md` 至少含 §2 改名迁移（若有）+ §3 存量库重建说明（KG 三段式 + kg_versions PG 字段映射）+ §4 验证矩阵 + §5 ADR/契约铁律旁证
- 收尾 commit 后跑四道门禁并贴结果摘要