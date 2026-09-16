---
name: multimodal-kb-scaffolding
overview: 在 GraphRAG-Agent 根目录初始化多模态知识库项目脚手架：创建完整目录结构、逐字写入 CODEBUDDY.md 项目规则、创建 Harness Rules、13 个 Superpowers 技能、5 个英文提示词模板、3 个 OpenSpec 风格模板及 README，最后输出完整文件树。
todos:
  - id: create-dirs
    content: 批量创建全部目录结构并为空目录添加 .gitkeep 占位
    status: completed
  - id: write-core-docs
    content: 逐字写入 CODEBUDDY.md 并编写中文 README.md
    status: completed
    dependencies:
      - create-dirs
  - id: create-harness-rules
    content: 创建 3 个 Harness Rules（always-on / model-decision / glob）
    status: completed
    dependencies:
      - create-dirs
  - id: create-superpowers-skills
    content: 使用 [skill:skill-creator] 创建 13 个 Superpowers 技能 SKILL.md
    status: completed
    dependencies:
      - create-harness-rules
  - id: create-prompts
    content: 创建 5 个英文提示词模板（含中文说明头与变量占位符）
    status: completed
    dependencies:
      - create-dirs
  - id: create-spec-templates
    content: 创建 specs/_template/ 下 proposal.md、tasks.md、design.md 模板
    status: completed
    dependencies:
      - create-dirs
  - id: verify-filetree
    content: 校验文件完整性并向用户输出完整文件树
    status: completed
    dependencies:
      - write-core-docs
      - create-superpowers-skills
      - create-prompts
      - create-spec-templates
---

## Product Overview
在 GraphRAG-Agent 仓库（已有 frontend/、backend/、openspec/、.codebuddy/openspec-* 技能）基础上，基于 harness + SDD + OpenSpec + Superpowers 理念，初始化多模态知识库项目的工程脚手架。产出为纯文档与目录结构，不涉及业务代码。

## Core Features
- **目录结构**：一次性创建全部要求的目录（docs、specs/_template、contracts、prompts、changes/archive、mineru_mvp/input|output、langextract_mvp/output、bridge_web_demo、langchain_mvp、tests/unit|integration|e2e、.github/workflows、backend/app/storage|tasks|prompts、.codebuddy/rules/always-on|model-decision|glob、.codebuddy/skills、.codebuddy/agents）；空目录放置 .gitkeep 以便提交
- **CODEBUDDY.md**：根目录创建，按用户提供的中文原文逐字写入（角色隔离、契约同步铁律、功能预留原则等 16 组规则）
- **Harness Rules**：创建 3 个规则文件——always-on/project-conventions.md（始终生效）、model-decision/code-review.md（模型自主决策）、glob/test-files.md（匹配测试文件时触发）
- **13 个 Superpowers 技能**：brainstorming、writing-plans、executing-plans、test-driven-development、systematic-debugging、verification-before-completion、requesting-code-review、subagent-driven-development、using-superpowers、writing-skills、dispatching-parallel-agents、using-git-worktrees、finishing-a-development-branch，每个为 .codebuddy/skills/<name>/SKILL.md
- **5 个英文提示词模板**：prompts/ 下 kg_qa_v1.md、document_parse_v1.md、entity_relation_extract_v1.md、chunk_summary_v1.md、intent_router_v1.md（英文正文 + 文件头中文用途说明，含变量占位符）
- **3 个 OpenSpec 风格模板**：specs/_template/ 下 proposal.md、tasks.md、design.md
- **README.md**：中文项目说明（项目定位、目录速查表、技术栈、开发约定）
- **交付物**：完成后列出完整文件树

## Constraints
- 不修改任何已有文件（openspec/、.codebuddy/ 既有技能、backend/src/、frontend/ 保持原样）
- 根目录 specs/ 与 changes/ 与已有 openspec/ 并存，README 说明分工
- 本次不做 git commit；contracts/ 仅留占位，openapi.yaml 属后续 SDD 变更

## Tech Stack
- 脚手架类型：纯 Markdown 文档 + 目录结构（无业务代码）
- 现有项目基座（不动）：frontend/ = Next.js 15 + TS + Tailwind（src-dir + App Router）；backend/ = uv + Python 3.11（src/backend/ 布局）
- 规范体系：harness（CODEBUDDY.md + .codebuddy/rules）、SDD（specs/ 模板）、OpenSpec（openspec/ 工具链）、Superpowers（.codebuddy/skills/）

## Implementation Approach
1. **先建目录骨架**：用一次批量操作创建全部目录；对其中不放内容的目录放置 `.gitkeep`（docs/、contracts/、changes/archive/、mineru_mvp/input|output、langextract_mvp/output、bridge_web_demo/、langchain_mvp/、tests/unit|integration|e2e、.github/workflows/、backend/app/storage|tasks|prompts、.codebuddy/agents/）。已含实际文件的目录（specs/_template/、prompts/、.codebuddy/rules/*）不放 .gitkeep
2. **CODEBUDDY.md 逐字写入**：严格按用户提供的原文（从 `# CODEBUDDY.md - GraphRAG-Agent 项目规则` 到 `使用 Conventional Commits：feat / fix / docs / chore / refactor / test`），不做任何改写、增删标点或空行调整
3. **Harness Rules 分层设计**：
   - `always-on/project-conventions.md`：浓缩 CODEBUDDY.md 中与日常编码直接相关的约定（Conventional Commits、uv 依赖管理、.env 规范、日志脱敏），始终注入上下文
   - `model-decision/code-review.md`：模型自行判断是否启用的审查规则（契约一致性检查、Pydantic 校验、错误响应结构、测试覆盖）
   - `glob/test-files.md`：仅当操作匹配 `**/tests/**`、`**/test_*.py`、`**/*.test.ts(x)` 等测试文件时生效（测试组织、命名、断言风格约定）
4. **13 个 SKILL.md（按用户修正：不使用 skill-creator，直接创建）**：直接在 `.codebuddy/skills/<技能名>/SKILL.md` 创建固定目录与文件；正文用中文，每个文件包含五要素：技能名称、用途、触发条件、执行步骤、输出格式；与既有 6 个 openspec-* 技能并存，目录名即技能名
5. **5 个英文 Prompt 模板**：统一结构（文件头 HTML 注释中文说明 → Role / Context / Task / Constraints / Output Format / Examples 占位），使用 `{{variable}}` 占位符，与 CODEBUDDY.md 的 Prompt 版本管理规范对齐（文件名带 _v1，后续只增版本不改写）
6. **3 个 OpenSpec 风格模板**：proposal.md（Why / What Changes / Impact）、tasks.md（编号 checklist，支持 `- [ ]` 勾选）、design.md（Context / Goals / Non-Goals / Decisions / Risks），保持与 openspec 工具链 artifact 语义兼容
7. **README.md**：项目定位（多模态知识库 GraphRAG Agent）、目录速查表（含 specs/ 与 openspec/ 分工说明、backend/app/ 与 backend/src/ 关系说明）、技术栈、开发环境约定（uv / .env / npm run gen:api / APP_ENV）

## Implementation Notes
- Windows 环境下写入文件使用绝对路径（d:/AIProject/GraphRAG-Agent/...），换行符默认 LF（与仓库现有文件一致，Git autocrlf 已配置）
- 不触碰 frontend/、backend/src/、openspec/、.codebuddy/commands/ 下任何已有文件，避免破坏已初始化的工具链
- .gitkeep 为空文件，仅作目录占位保证可提交
- 完成后用文件树命令验证并输出完整结构给用户；不执行 git add/commit

## Directory Structure Summary
全部为新增文件，无修改：

```
d:/AIProject/GraphRAG-Agent/
├── CODEBUDDY.md                                          # [NEW] 项目规则总纲（用户原文逐字写入）
├── README.md                                             # [NEW] 中文项目说明与目录速查表
├── docs/
│   └── .gitkeep                                          # [NEW] 项目文档占位
├── specs/
│   └── _template/
│       ├── proposal.md                                   # [NEW] 变更提案模板（Why/What Changes/Impact）
│       ├── tasks.md                                      # [NEW] 任务拆解模板（编号 checklist）
│       └── design.md                                     # [NEW] 设计文档模板（Context/Goals/Decisions/Risks）
├── contracts/
│   └── .gitkeep                                          # [NEW] API 契约目录占位（openapi.yaml 属后续变更）
├── prompts/
│   ├── kg_qa_v1.md                                      # [NEW] 知识库问答 Prompt v1（英文+中文说明）
│   ├── document_parse_v1.md                              # [NEW] 文档解析 Prompt v1
│   ├── entity_relation_extract_v1.md                     # [NEW] 实体关系抽取 Prompt v1
│   ├── chunk_summary_v1.md                               # [NEW] 分块摘要 Prompt v1
│   └── intent_router_v1.md                               # [NEW] 意图路由 Prompt v1
├── changes/
│   └── archive/
│       └── .gitkeep                                      # [NEW] 已归档变更占位
├── mineru_mvp/
│   ├── input/.gitkeep                                    # [NEW] MinerU 解析输入占位
│   └── output/.gitkeep                                   # [NEW] MinerU 解析输出占位
├── langextract_mvp/
│   └── output/.gitkeep                                   # [NEW] LangExtract 输出占位
├── bridge_web_demo/.gitkeep                              # [NEW] Web 桥接演示占位
├── langchain_mvp/.gitkeep                                # [NEW] LangChain MVP 占位
├── tests/
│   ├── unit/.gitkeep                                     # [NEW] 单元测试占位
│   ├── integration/.gitkeep                              # [NEW] 集成测试占位
│   └── e2e/.gitkeep                                      # [NEW] 端到端测试占位
├── .github/
│   └── workflows/.gitkeep                                # [NEW] CI 工作流占位
├── backend/
│   └── app/
│       ├── storage/.gitkeep                              # [NEW] 存储抽象层目标布局占位
│       ├── tasks/.gitkeep                                # [NEW] 异步任务模块占位
│       └── prompts/.gitkeep                              # [NEW] 后端 Prompt 加载占位
└── .codebuddy/
    ├── rules/
    │   ├── always-on/project-conventions.md              # [NEW] 常驻项目约定规则
    │   ├── model-decision/code-review.md                 # [NEW] 模型自主决策的代码审查规则
    │   └── glob/test-files.md                            # [NEW] 测试文件触发规则（glob 匹配）
    ├── skills/
    │   ├── brainstorming/SKILL.md                        # [NEW] 需求头脑风暴技能
    │   ├── writing-plans/SKILL.md                        # [NEW] 编写实施计划技能
    │   ├── executing-plans/SKILL.md                      # [NEW] 执行计划技能
    │   ├── test-driven-development/SKILL.md             # [NEW] TDD 技能
    │   ├── systematic-debugging/SKILL.md                # [NEW] 系统化调试技能
    │   ├── verification-before-completion/SKILL.md      # [NEW] 完成前验证技能
    │   ├── requesting-code-review/SKILL.md               # [NEW] 发起代码审查技能
    │   ├── subagent-driven-development/SKILL.md          # [NEW] 子代理驱动开发技能
    │   ├── using-superpowers/SKILL.md                    # [NEW] 技能体系入口/调度技能
    │   ├── writing-skills/SKILL.md                       # [NEW] 编写新技能的技能
    │   ├── dispatching-parallel-agents/SKILL.md          # [NEW] 并行代理派发技能
    │   ├── using-git-worktrees/SKILL.md                  # [NEW] git worktree 使用技能
    │   └── finishing-a-development-branch/SKILL.md       # [NEW] 分支收尾技能（共 13 个）
    └── agents/.gitkeep                                   # [NEW] 代理定义占位
```
