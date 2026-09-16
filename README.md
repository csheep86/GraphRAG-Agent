# GraphRAG-Agent 多模态知识库

基于 **harness + SDD + OpenSpec + Superpowers** 理念构建的多模态知识库项目：解析多模态文档（PDF / 图片 / 网页等），抽取实体与关系构建知识图谱，并提供图谱增强的检索问答（GraphRAG）服务。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 15 + TypeScript + Tailwind CSS（App Router，src-dir） |
| 后端 | Python 3.11 + FastAPI + Pydantic + loguru + slowapi + tenacity |
| 文档解析 | MinerU（PDF → Markdown / 结构化输出） |
| 信息抽取 | LangExtract（实体 / 关系抽取） |
| 编排 | LangChain（RAG / Agent 链路 MVP） |
| 包管理 | 前端 npm / 后端 uv（禁止 conda、poetry、pipenv） |

## 目录速查表

| 目录 | 用途 |
|---|---|
| `frontend/` | Next.js 前端应用（前端开发 A 角色负责） |
| `backend/` | Python 后端应用（后端开发 B 角色负责） |
| `backend/app/` | 后端应用代码目标布局：`storage/`（存储抽象层）、`tasks/`（异步任务）、`prompts/`（Prompt 加载）。当前 `backend/src/backend/` 为 uv init 生成的初始布局，业务代码将迁移至 `backend/app/` |
| `docs/` | 项目文档（架构说明、调研笔记、决策记录） |
| `specs/` | 项目规格权威目录，`_template/` 存放 SDD 模板（proposal / tasks / design） |
| `openspec/` | OpenSpec 工具链工作区（变更管理与规格同步），与 `specs/` 分工：`openspec/` 面向工具化变更流程，`specs/` 面向人工维护的规格文档 |
| `contracts/` | API 契约（`openapi.yaml`），前后端共同遵守的唯一接口事实源 |
| `prompts/` | LLM Prompt 模板，带版本号（如 `kg_qa_v1.md`），只增版本不改历史 |
| `changes/` | 变更记录，`archive/` 存放已归档变更 |
| `mineru_mvp/` | MinerU 解析 MVP：`input/` 放待解析文件，`output/` 存解析结果 |
| `langextract_mvp/` | LangExtract 抽取 MVP，`output/` 存抽取结果 |
| `bridge_web_demo/` | Web 桥接演示 |
| `langchain_mvp/` | LangChain 编排 MVP |
| `tests/` | 测试：`unit/` 单元、`integration/` 集成、`e2e/` 端到端 |
| `.github/workflows/` | CI 工作流 |
| `.codebuddy/rules/` | Harness 规则：`always-on/` 常驻、`model-decision/` 模型自主决策、`glob/` 按文件匹配触发 |
| `.codebuddy/skills/` | 技能库：6 个 openspec-* 工具链技能 + 13 个 Superpowers 开发流程技能 |
| `.codebuddy/agents/` | 自定义代理定义 |

## 开发约定（摘要）

完整规则见 [`CODEBUDDY.md`](./CODEBUDDY.md)，要点：

- **契约先行**：改接口先改 `contracts/openapi.yaml`，再同步前后端；前端运行 `npm run gen:api` 生成 TS 类型
- **环境**：通过 `APP_ENV` 切换环境（默认 `development`）；前端变量用 `NEXT_PUBLIC_` 前缀，禁止硬编码 Base URL
- **依赖**：后端只用 uv，`uv.lock` 必须提交；`.env` 模板见 `.env.example`，`.env*` 已入 `.gitignore`
- **Prompt**：统一存放 `prompts/`，经 `prompt_loader.py` 加载，禁止硬编码
- **提交**：Conventional Commits（`feat` / `fix` / `docs` / `chore` / `refactor` / `test`）
- **第三方对接**：以本地实测跑通结果为唯一标准，文档冲突时以实测为准

## 开发环境

- Node 18+（见 `.nvmrc`）
- Python 3.11（见 `.python-version`，推荐 uv 管理）

```bash
# 后端
cd backend && uv sync

# 前端
cd frontend && npm install
```
