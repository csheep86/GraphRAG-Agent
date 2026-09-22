# Proposal: Sprint5.1 — 存储抽象 + MinerU 转正（批次 A）

> **上游依据**：`docs/v1.1.0-demo-mvp-plan.md` §4.2 批次 A / §4.3 验收清单（行级对齐）；规格锚点 `specs/m1-async-ingest.md`。
> **分支**：`feature/sprint-5` | **Sprint**：5（阶段十四，tag `v1.1.0`）| **日历**：2026-09-21 → 10-11（`docs/sprint-calendar.md` §2）。

## Why

v1.0.0 工程外壳存在两条断链（plan §4.1）：① 上传文件未真实落盘（`documents.storage_key` 恒 NULL）；② parsing 状态是空转（MinerU 未接入主链路）。黄金路径步骤 1（上传→解析）要求文件真实持久化并解析出结构化文本。同时，企业本地部署底线（plan §3.4）要求外部服务依赖收敛到统一抽象，本批次先落**存储抽象**（开发本地 FS / 生产可切 S3 的接缝，ADR-0004 接缝位），为后续 Provider 抽象（批次 A2）立样板。

## What Changes

- 落地 `backend/app/storage/` 抽象层（目录已预留，仅 `__init__.py`）：`StorageBackend` 接口 + `LocalFSStorage` 实现（开发档）；生产 S3 只登记 ADR-0004，**不写 stub**。
- 上传链路真实落盘：`POST /documents` 保存文件 → completed 时回填 `storage_key`（真实路径/对象键）。
- parsing 状态真实执行 MinerU：复用 `mineru_mvp/` 已跑通代码，产出结构化解析结果（页码 + 文本片段）落库。
- 顺手修 B1 `retry_count` / B4 `task_retry_multiplier` 欠账（plan §4.2 批次 A 明列）。

## Impact

**影响的契约（contracts/openapi.yaml）**

- 无新增端点；`Document` schema 若需暴露 `storage_key` **不进契约**（内部字段，预留纪律：`export_openapi.py --check` 无 diff）。

**影响的前端（frontend/）**

- 无（本批次后端内部链路；documents 页关 Mock 在批次 C）。

**影响的后端（backend/）**

- `backend/app/storage/`（新增）；上传 service 落盘 + `storage_key` 回填；parsing 执行器接 MinerU；`config.py` 存储配置项（须有消费者）；`task_retry_multiplier` 修复（任务退避路径真实读取或删除该配置——按 CODEBUDDY「无消费者的配置不得提交」处置）。

**影响的 Prompt（prompts/）**

- 无（本批次不触抽取 Prompt，LangExtract 在批次 B）。

## Non-goals

- **不做** Provider 抽象（`parser_provider` / `llm_provider`）——批次 A2。
- **不做** LangExtract 抽取 / Neo4j 建图 ——批次 B。
- **不做** `GET /documents` 列表接口与前端关 Mock ——批次 C。
- **不做** `domain_events` ——已移至 Sprint 7 批次 D（plan §4.2）。
- **不做** S3 真实实现——只登记 ADR-0004 接缝清单（登记集合不多不少）。
