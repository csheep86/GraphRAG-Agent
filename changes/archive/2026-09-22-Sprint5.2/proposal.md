# Proposal: Sprint5.2 — 集成接缝收口（批次 A2）

> **上游依据**：`docs/v1.1.0-demo-mvp-plan.md` §4.2 批次 A2 / §8.1 接缝 1/3/4 / §8.2；ADR-0004 §2.1 / §3。
> **分支**：`feature/sprint-5` | **Sprint**：5 | **预算**：净增 2.5 天。

## Why

目标交付形态是企业内网本地部署：外部服务依赖（MinerU 云 / DeepSeek）是临时态，必须收敛到统一 Provider 抽象（plan §3.4-1）；企业集成预留字段一旦表结构落定再补就要数据迁移（plan §8）；`check_seams.py` 的 1.1.0 到期判据（AuthProvider 恰好 1 实现、`llm_provider`/`parser_provider`/`pipeline_stages` 有消费者、8 预留字段齐全）在 tag `v1.1.0` 打出瞬间自动上闸——本批次必须先于 Sprint 收尾全部落位。

## What Changes

1. **Provider 抽象（接缝 3）**：配置去 `deepseek_` 硬编码 → 中性 `llm_*` 配置 + `llm_provider` 开关；`parser_provider` 开关由 parsing 执行体消费；LLM 调用点（agents.py）改经工厂。
2. **AuthProvider 收口（接缝 1）**：`app/services/auth/` 落 `AuthProvider` 接口 + **恰好一个** `LocalAuthProvider`（包装现有 dev header 逻辑）；不建 `users` 表。
3. **documents 8 预留字段（接缝 2 的 A2 份额）**：`source_type`/`source_ref`/`document_key`/`content_hash`/`source_version`/`acl_scope`/`acl_owner_ref`/`deleted_at`，全部 nullable、**不进契约**；`IngestionSource` 接口不建（T10 裁决）。
4. **pipeline_stages（接缝 4）**：`settings.pipeline_stages`（启停+顺序）+ `app/tasks/pipeline.py` 消费点；EXECUTOR_REGISTRY 命名对齐四阶段规范（本批次仅 `document.parse`，`document.extract`/`kg.build` 随批次 B、`risk.detect` 随 S7 登记）。

## Impact

- **契约**：零变更（预留字段不进 `openapi.yaml`，`export_openapi.py --check` 必须无 diff）。
- **后端**：`config.py`（配置改名+新增）、`services/auth/`（新）、`services/providers/`（新）、`tasks/pipeline.py`（新）、`tasks/registry.py`（parser_provider 消费）、`services/agents.py`（LLM 工厂化）、`db/models.py`（8 字段）、`.env.example`。
- **前端 / prompts**：不动。
- **破坏性**：`deepseek_*` 配置改名 `llm_*`（.env 需同步；登记进 integration-log）。

## Non-goals

- 不建 `IngestionSource` / `EventSink` / `ExportSink`（S7/S8 承接，登记集合之外即越界）；
- 不做 `domain_events`（已移至 S7 批次 D）；
- 不做批次 B 的链式触发（extract/kg.build 只出现在 pipeline_stages 默认值里，无执行体时自动跳过）。
