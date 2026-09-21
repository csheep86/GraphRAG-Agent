# GraphRAG-Agent 多模态知识库

基于 **harness + SDD + Superpowers** 理念构建的多模态知识库项目：解析多模态文档（PDF / 图片 / 网页等），抽取实体与关系构建知识图谱，并提供图谱增强的检索问答（GraphRAG）服务。

> **OpenSpec 已停用**：本项目**不使用 OpenSpec CLI**（决议 O-1）。SDD 变更的落点是 `changes/Sprint<N>.<M>/`；`openspec/` 目录仅作历史留痕，**不得写入**，也不得执行 `openspec init` / `openspec new change`。

## 项目状态与文档入口

| 文档 | 用途 |
|---|---|
| [`docs/03-prd.md`](./docs/03-prd.md) | **需求真源**：6 个 P0 模块（M1–M6）、H1–H12 硬约束、黄金路径 7 步 |
| [`docs/v1.1.0-demo-mvp-plan.md`](./docs/v1.1.0-demo-mvp-plan.md) | **交付计划 v3.0**：阶段总表、tag 规划、承接表 |
| [`docs/v2.0.0-ship-backward-plan.md`](./docs/v2.0.0-ship-backward-plan.md) | **倒推计划**：上线闸门 G1–G5 + §7 决策记录 |
| [`docs/acceptance-traceability-matrix.md`](./docs/acceptance-traceability-matrix.md) | **验收对账**：H1–H12 / C1–C3 / F1–F5 → 判据 → 验收人 |
| [`docs/dev-doc-status.md`](./docs/dev-doc-status.md) | **文档状态跟踪**（唯一活表）+ 批次开工 / 收尾 checklist |
| [`specs/`](./specs/) | 模块规格权威目录（`m1`～`m6`）；`_template/` 为 SDD 三件套模板 |
| [`CODEBUDDY.md`](./CODEBUDDY.md) | 项目规则：契约铁律 / 接缝纪律 / 质量门禁 |

> **交付状态**：**`v1.0.0` = 工程外壳**（真实上传 / 状态机 / 重试 / 契约零漂移门禁已就绪；解析、图谱、问答链路为占位）。**目标交付 = `v2.0.0`（Sprint 13）**，判定条件见倒推计划 §3。**`v1.4.0` 仅为中途演示点（Demo），不是交付版**，对外不得称"MVP 1.0 已完成"。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 16.3.5 + React 19 + TypeScript + Tailwind CSS 4（App Router，src-dir） |
| 后端 | Python 3.11 + FastAPI + Pydantic + loguru + slowapi + tenacity |
| 文档解析 | MinerU（PDF → Markdown / 结构化输出） |
| 信息抽取 | LangExtract（实体 / 关系抽取） |
| 编排 | LangChain（RAG / Agent 链路 MVP） |
| 存储 | Neo4j（图谱） + PostgreSQL（关系数据） + 文件存储抽象层 |
| 包管理 | 前端 npm / 后端 uv（禁止 conda、poetry、pipenv） |

## 目录速查表

| 目录 | 用途 |
|---|---|
| `frontend/` | Next.js 前端应用（前端开发 A 角色负责） |
| `backend/` | Python 后端应用（后端开发 B 角色负责） |
| `backend/app/` | 后端应用代码目标布局：`storage/`（存储抽象层）、`tasks/`（异步任务）、`prompts/`（Prompt 加载）。当前 `backend/src/backend/` 为 uv init 生成的初始布局，业务代码将迁移至 `backend/app/` |
| `docs/` | 项目文档（架构说明、调研笔记、决策记录） |
| `specs/` | 项目规格权威目录，`_template/` 存放 SDD 三件套模板（proposal / design / tasks） |
| `openspec/` | **OpenSpec 工作区（已停用，仅历史留痕）**：`openspec/specs/` 与 `openspec/changes/archive/` 均为空。**变更以 `specs/` + ADR + `changes/` 为准**；**不得写入本目录**（决议 O-1） |
| `contracts/` | API 契约（`openapi.yaml`），前后端共同遵守的唯一接口事实源 |
| `prompts/` | LLM Prompt 模板，带版本号（如 `kg_qa_v1.md`），只增版本不改历史 |
| `changes/` | 变更工作目录：每个批次一个 `changes/Sprint<N>.<M>/`，内含 SDD 三件套（`proposal.md` / `design.md` / `tasks.md`）与联调证据（`integration-log.md` + 探针脚本 + 日志）。**工作期不入库**，批次收尾归档为 `changes/archive/<日期>-Sprint<N>.<M>/` 并 `git add`（**只归档 `.md` 与 `.py`**，`*.log` / `*.pyc` 不入库） |
| `mineru_mvp/` | MinerU 解析 MVP：`input/` 放待解析文件，`output/` 存解析结果 |
| `langextract_mvp/` | LangExtract 抽取 MVP，`output/` 存抽取结果 |
| `bridge_web_demo/` | Web 桥接演示 |
| `langchain_mvp/` | LangChain 编排 MVP |
| `tests/` | 测试：`unit/` 单元、`integration/` 集成、`e2e/` 端到端 |
| `.github/workflows/` | CI 工作流 |
| `.codebuddy/rules/` | Harness 规则：`always-on/` 常驻、`model-decision/` 模型自主决策、`glob/` 按文件匹配触发 |
| `.codebuddy/skills/` | 技能库：**13 个 Superpowers 开发流程技能（已启用）** + 6 个 `openspec-*` 技能（**已停用，仅留痕**，见决议 O-1）；`openspec-*` 的 `description` 已标注禁止调用 |
| `.codebuddy/agents/` | 自定义代理定义 |

## 开发约定（摘要）

完整规则见 [`CODEBUDDY.md`](./CODEBUDDY.md)，要点：

- **契约先行**：改接口先改 `contracts/openapi.yaml`，再同步前后端；前端运行 `npm run gen:api` 生成 TS 类型（输出 `src/types/api.d.ts`，**禁止手改生成物**）
- **功能预留与接缝纪律**：预留字段只落库、**不进契约**（判定口径 = `export_openapi.py --check` 无 diff）；**预留必须有登记**（`docs/adr/0004-integration-seams.md`）；接口实现集合 = ADR-0004 §2.1 登记集合，**不多不少**，由 `check_seams.py` 机械校验
- **环境**：通过 `APP_ENV` 切换环境（默认 `development`）；前端变量用 `NEXT_PUBLIC_` 前缀，禁止硬编码 Base URL
- **依赖**：后端只用 uv，`uv.lock` 必须提交；`.env` 模板见 `.env.example`，`.env*` 已入 `.gitignore`
- **Prompt**：统一存放 `prompts/`，经 `prompt_loader.py` 加载，禁止硬编码
- **质量门禁**：`pre-commit hook 暂未启用`——提交前手工跑本地检查，推送后以 CI 全量门禁（backend / frontend / contract 三 job）为最终裁决
- **提交**：Conventional Commits（`feat` / `fix` / `docs` / `chore` / `refactor` / `test`）；**打 tag 与 bump `settings.app_version` 是同一个动作**
- **验收口径**：任何"完成"必须能指出它对应 [`docs/acceptance-traceability-matrix.md`](./docs/acceptance-traceability-matrix.md) 的哪一行（锚点 + 判据 + 验收人）；未达标走 F1–F5 显式降级，**不得静默通过**
- **第三方对接**：以本地实测跑通结果为唯一标准，文档冲突时以实测为准

## 开发环境

- Node 22+（见 `.nvmrc`）
- Python 3.11（见 `.python-version`，推荐 uv 管理）

```bash
# 后端
cd backend && uv sync

# 前端
cd frontend && npm install
```
