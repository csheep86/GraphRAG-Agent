# GraphRAG\-Agent \+ Harness \+ SDD 多模态知识库全栈开发指南

> 核心思维：单仓库 \+ 契约先行 \+ SDD驱动 \+ CodeBuddy插件执行。
> 协作模式：模拟"A做前端、B做后端"，双方通过 `contracts/openapi.yaml` 和 `specs/` 强制对齐标准。
> 技术栈（**运行时组件，已按本地实测收敛**）：MinerU \+ LangExtract \+ LangChain \+ DeepSeek \+ FastAPI \+ Pydantic \+ React（Next.js 16）\+ Neo4j \+ PostgreSQL \+ loguru \+ slowapi \+ tenacity。
> 工具链：VSCode \+ CodeBuddy 插件（Plan / Craft / Ask 三模式）\+ Pencil 插件（**仅阶段八 UI 设计稿使用**）。
> **已排除项（勿再按技术栈理解）**：**Milvus**（阶段十四明确"跳过 Milvus，只跑通 Neo4j + Agentic-RAG"）、**MCP**（仅作为 CodeBuddy 内置能力出现在"防幻觉铁律"中，**不是规划组件**）。
> 执行原则：先独立 MVP 验证，再集成组装；本地实测结果反哺规范文档；机器强制同步契约；无法匹配的功能先预留空位，严禁强行同步开发。
> 企业底线：环境隔离、异步任务、存储抽象、日志可观测、测试分层、CI 自动化、安全限流、错误统一、Prompt 版本化、依赖锁定、格式化统一、跨平台换行符一致。
> 操作环境：VSCode \+ CodeBuddy 插件 \+ Pencil 插件。

> **⚠️ 文档适用边界（2026-09-21 标注，先读这一段）**
>
> 1. **覆盖范围**：本指南当前覆盖 **阶段一 ～ 阶段十七 = Sprint 1 ～ 8**（至 tag `v1.4.0`）。**阶段十八 ～ 二十二（Sprint 9 ～ 13，至 `v2.0.0`）尚未编写**（缺口登记：`docs/v2.0.0-ship-backward-plan.md` §5.2 **D-4**）。
> 2. **口径优先级**：Sprint 9 ～ 13 的**排期、闸门与验收口径**，以 `docs/v1.1.0-demo-mvp-plan.md`（**v3.0**）与 `docs/v2.0.0-ship-backward-plan.md` 为**唯一真源**；本指南若与二者冲突，**以二者为准**。
> 3. **交付口径修订**：**`v1.4.0` 是中途演示点（Demo），不是交付版**；**最终交付 = `v2.0.0`（Sprint 13）**。本指南中凡出现"Demo-MVP 完成点 / 完成"的表述，均按此修订理解。
> 4. **验收对账**：逐条判据（谁验、怎么验、到哪一步）见 `docs/acceptance-traceability-matrix.md`。
> 5. **OpenSpec CLI 已停用**：本指南"环境准备"中"安装 OpenSpec CLI"与"`openspec init`"两步**已作废**（决议 **O-1**：SDD 变更落点为 `changes/Sprint<N>.<M>/`，**不启用 OpenSpec CLI**）。**不要安装、不要执行 `openspec init` / `openspec new change`**——它会重新生成 `.codebuddy/commands/opsx/` 并把落点指向 `openspec/changes/`。详见下方第 6 / 9 步的作废说明与 `docs/v2.0.0-ship-backward-plan.md` §6.1。
> 
> 

# 🚦 执行顺序与验收总览

## 📌 分支策略（关键）

**每个 Sprint 全程在自己的 feature 分支上开发，只有 Sprint 最终收尾时才合并到 main。**

- Sprint 1 分支：`feature/scaffolding`

- Sprint 2 分支：`feature/sprint-2`

- Sprint 3 分支：`feature/sprint-3`

- Sprint 4 分支：`feature/sprint-4`
- Sprint 5 分支：`feature/sprint-5`（Demo-MVP 之一：真解析与在线建图，tag v1.1.0）
- Sprint 6 分支：`feature/sprint-6`（Demo-MVP 之二：引用溯源，tag v1.2.0）
- Sprint 7 分支：`feature/sprint-7`（Demo-MVP 之三：M4 疑点清单最小版，tag v1.3.0）
- Sprint 8 分支：`feature/sprint-8`（Demo-MVP 之四：审计与演示打磨，tag v1.4.0 = **Demo-MVP 完成点（中途演示点，非交付版）**）

**以下为 PRD MVP 1.0 追加段（plan v3.0 新增，阶段十八～二十二，本指南尚未展开，口径见 `docs/v1.1.0-demo-mvp-plan.md` §16～§20）**：

- Sprint 9 分支：`feature/sprint-9`（M4 完整化：四源对齐 + PRD 三类算法 + 实体消解，tag v1.5.0）
- Sprint 10 分支：`feature/sprint-10`（证据链与多跳：≥3 跳 + Chunk 真实引用 + docx，tag v1.6.0）
- Sprint 11 分支：`feature/sprint-11`（M5 完整化 + RLS 全量 + 内网双轨，tag v1.7.0）
- Sprint 12 分支：`feature/sprint-12`（M6 完整版：本体冷启动 + 校正 GUI + 增量重算 + 成本仪表盘，tag v1.8.0）
- Sprint 13 分支：`feature/sprint-13`（C1~C3 实验闭环，tag **v2.0.0 = PRD MVP 1.0 完成点**）

**禁止在 Sprint 中途合并到 main**。 提前合并会导致最终收尾时 `merge --no-ff` 无事可做，或产生混乱。

> **⚠️ 交付口径**：**`v1.4.0` 不是交付版**，对外沟通时不得称"MVP 1.0 已完成"；**交付版 = `v2.0.0`（Sprint 13）**，其充要条件是 plan §3.2 B 段五条全满足且 §15 承接表逐行勾选（或已有显式降级登记）。

## 📌 Sprint 收尾动作（必须执行）

```Bash
# 0. 先 bump 应用版本（与打 tag 是同一个动作，见下）
#    backend/app/core/config.py -> settings.app_version = vX.Y.0

# 1. 打附注 tag（语义化版本）
git tag -a vX.Y.0 -m "Sprint N done: <摘要>"

# 2. 合并回 main
git checkout main
git merge --no-ff feature/sprint-N -m "merge: sprint N done (vX.Y.0)"

# 3. 推送到 GitHub
git push origin main
git push --tags
```

> **打 tag 与 bump `settings.app_version` 是同一个动作**：该值是 `export_openapi.py` 输出的 `info.version`，也是 `check_seams.py` 版本闸门的**唯一输入**。不 bump 这个值，接缝门禁会永久停在"未到期只记 WARN"的档位——**越界与少做就没人拦**（T12 裁决，plan §3.3）。

关于 tag 的历史说明：

- `sprint-1-done`（轻量 tag，指向脚手架完成点）作为历史记录保留，不再用于 Sprint 收尾。

- 从 Sprint 1 开始，所有 Sprint 收尾统一用语义化版本附注 tag：`v0.1.0 / v0.2.0 / v0.3.0 / v1.0.0`；**Demo-MVP 段** `v1.1.0 / v1.2.0 / v1.3.0 / v1.4.0`（Sprint 5~8）；**PRD MVP 1.0 追加段** `v1.5.0 / v1.6.0 / v1.7.0 / v1.8.0 / v2.0.0`（Sprint 9~13）。**全量计划详见 `docs/v1.1.0-demo-mvp-plan.md`（v3.0）§13 阶段总表**。

Sprint 验收不通过怎么办：

1. 把失败命令的完整输出复制给 CodeBuddy（Ask 模式），问它"这是什么原因，怎么修"。

2. 不要跳步骤，先把当前 Sprint 验收通过，再进入下一个。

3. 卡住超过 2 小时，把报错和进度发给 CodeBuddy，让它重新规划当前 Sprint。

## 模式切换速查表

- Plan 模式：规划、设计、写文档、生成规范。不改业务代码。

- Craft 模式：写代码、建文件、跑命令。

- Ask 模式：查资料、问报错、解释代码。只读。

口诀：写文档用 Plan → 写代码用 Craft → 遇报错用 Ask → 再切回 Craft 修。

# 一、环境准备（手动执行）

1. 安装 VSCode。

2. VSCode 扩展市场搜索 CodeBuddy 并安装，扫码登录。

3. VSCode 扩展市场搜索 Pencil 并安装，邮箱验证激活。

4. 安装 Node\.js 18\+、Python 3\.11\+、Git、Docker Desktop。

5. 安装 `uv`：

```PowerShell
# 【执行环境】PowerShell（不要用 CMD）
# 【权限】普通用户
# 【工作目录】任意目录
# 【作用】安装 uv 工具，用于创建 Python 虚拟环境、安装依赖。
irm https://astral.sh/uv/install.ps1 | iex
```

6. ~~安装 OpenSpec CLI~~ → **⚠️ 该步骤已作废（2026-09-21 决议 O-1），跳过**：

```Bash
# 【状态】已停用——不要执行
# 【原因】本项目不启用 OpenSpec CLI。SDD 变更落点为 changes/Sprint<N>.<M>/（方案 A′），
#         三件套模板在 specs/_template/，无需任何全局 CLI。
#         决议见 docs/v2.0.0-ship-backward-plan.md §6.1 / §7。
# 【风险】若已安装无害，但不得执行 openspec init / openspec new change——
#         会重新生成 .codebuddy/commands/opsx/ 并把落点写向 openspec/changes/。
```

7. 注册并申请必要的 API Key（关键）

    - DeepSeek：访问 [https://platform\.deepseek\.com/](https://platform.deepseek.com/) ，注册并创建 API Key，必须充值少量金额（约 10 元）。

    - MinerU：访问 [https://mineru\.net/](https://mineru.net/) ，注册并申请 Token。

8. 克隆仓库到本地并验证

```Bash
# 【执行环境】CMD 或 PowerShell 或 VSCode 集成终端
# 【权限】普通用户
# 【工作目录】你希望存放项目的父目录（例如 D:\code）
# 【作用】从 GitHub 克隆仓库并进入项目目录。
cd /d D:\code
git clone https://github.com/<你的GitHub用户名>/GraphRAG-Agent.git
cd GraphRAG-Agent
git status
```

9. ~~在项目根目录执行 `openspec init --tools codebuddy`~~ → **⚠️ 该步骤已作废，跳过**：

```Bash
# 【状态】已停用——不要执行
# 【原因】该命令会重新生成 .codebuddy/commands/opsx/，并把变更落点指向 openspec/changes/，
#         与本项目决议的方案 A′（落点 changes/Sprint<N>.<M>/）冲突。
# 【正确做法】克隆仓库后直接开始：.codebuddy/ 已随仓库提供；
#             SDD 事前动作见 docs/dev-doc-status.md §9.1。
```

📌 **`uv run`**** 与 ****`.venv`**** 的关系**

- `uv venv` 创建 `.venv`，`uv add` 添加依赖。

- `uv run xxx` 自动使用当前目录 `.venv`，不需要手动 activate。

- 整个文档统一用 `uv run`，不写 `activate`。



📌 **`.nvmrc`**** 与 Node 版本说明**

- `.nvmrc` 内容为 `22`：声明项目用 Node\.js 22 LTS。

- 为什么是 22 而不是 18：`next@16+` 要求 `node>=20.9`。Node 18 会在 `npm ci` 触发 `EBADENGINE`。

- CI 里也用 22，与 `.nvmrc` 一致。



📌** ****`.python-version`**** 说明**

- 内容为 `3.11`，声明项目用 Python 3\.11。



**📌 ****`npx create-next-app@latest ...`**** 长命令逐段拆解**

```Bash
npx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
```

# 二、Sprint 1：骨架与规范

## 阶段一：全量脚手架初始化

### 1\.1 初始化前端和后端目录

【使用模式：Craft】

```Plain Text
请帮我执行以下初始化命令：
1. 在根目录下创建 frontend/，使用【非交互式】命令初始化 Next.js：
   npx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
2. 在根目录下创建 backend/，使用【非交互式】命令初始化 Python 项目：
   uv init backend --python 3.11 --no-workspace
3. 创建版本锁定文件：.python-version（内容 3.11）、.nvmrc（内容 22）
4. 建立特性分支并提交：
   git checkout -b feature/scaffolding
   git add .
   git commit -m "chore: init frontend and backend"
```

### 1\.2 全量脚手架配置

【使用模式：Plan】

```Plain Text
你是 AI 编程脚手架专家。请基于 harness + SDD + OpenSpec + Superpowers 理念，在当前项目根目录初始化一个多模态知识库项目。

请严格按以下要求执行：

1. 创建目录结构：
   - docs/、specs/_template/、contracts/、prompts/、changes/archive/
   - mineru_mvp/input/、mineru_mvp/output/
   - langextract_mvp/output/、bridge_web_demo/、langchain_mvp/
   - tests/unit/、tests/integration/、tests/e2e/
   - .github/workflows/
   - backend/app/storage/、backend/app/tasks/、backend/app/prompts/
   - .codebuddy/rules/always-on/、.codebuddy/rules/model-decision/、.codebuddy/rules/glob/
   - .codebuddy/skills/、.codebuddy/agents/

2. 在项目根目录（与 .git 同级）创建 CODEBUDDY.md，逐字写入以下规则：
# CODEBUDDY.md - GraphRAG-Agent 项目规则

## 角色隔离
- 处理 frontend/ 时，你是前端开发（A），只允许修改 frontend/。
- 处理 backend/ 时，你是后端开发（B），只允许修改 backend/。
- 处理 specs/ 和 contracts/ 时，你是架构师。

## 防幻觉铁律
1. 不得调用任何未在项目中明确定义、也未在 CodeBuddy 中内置的工具或技能。
2. 不得假设存在外部工具（尤其是 skill-creator、xxx-builder 这类不存在的工具）。
3. 所有文件操作必须通过创建、修改文件或执行终端命令完成。
4. 对某个操作不确定时，必须先停下来问我，不许自行发明工具或命令。
5. 以上约束不限制 CodeBuddy 内置的基础能力：读取文件、搜索代码、编辑文件、执行终端命令、调用 MCP Server。

## 契约同步铁律
1. 修改任何接口字段，必须先更新 contracts/openapi.yaml。
2. 更新完契约，必须检查并更新 frontend/ 的 TS 类型和 Mock 数据。
3. 更新完契约，必须更新 backend/ 的 Pydantic 模型和接口逻辑。
4. 前端必须运行 npm run gen:api，确保 TS 类型与契约一致。

## 功能预留原则（极其重要！）
1. 暂时无法匹配的功能先预留空位，不要强行同步开发。
2. 严禁 AI 在前后端不匹配时，自动去补全另一端的逻辑。
3. 一旦发现不匹配，立刻停止，报告给我，并输出一份"接口对齐清单"。

## 实测结果反哺规则
1. 所有第三方组件的对接规范，必须以本地实际跑通的结果为唯一标准。
2. 若官方文档与本地实际输出冲突，以本地实际输出为准。

## 环境与依赖规则
1. 每个子项目只允许使用 uv 创建 .venv，禁止混用 conda、poetry、pipenv。
2. 必须提交 uv.lock 到 Git。
3. 必须提供 .env.example 作为模板，.env 及变体必须加入 .gitignore。
4. 通过 APP_ENV 环境变量切换环境配置，默认 development。
5. 前端使用 NEXT_PUBLIC_ 前缀暴露变量，禁止硬编码 Base URL。

## 密钥管理规则
1. 生产环境密钥通过 GitHub Secrets 或云厂商 KMS 注入。
2. 开发环境使用 .env.development，不得包含生产密钥。
3. 任何密钥泄露，必须立即在对应平台轮换。

## 日志与可观测性规则
1. 后端统一使用 loguru，输出 JSON 格式日志。
2. 每个请求携带 trace_id，贯穿整个调用链。
3. 关键路径打点记录耗时和 token 用量。

## 错误响应规范
1. 所有异常统一由全局异常处理器拦截，返回 JSON：{code, message, detail, trace_id}。
2. HTTP 状态码与业务错误码分离。

## 异步任务规范
1. 长耗时任务必须异步处理，上传接口立即返回 task_id。
2. 前端通过轮询 /documents/{id}/status 获取进度。
3. 任务状态流转：pending → processing → completed → failed。
4. 任务失败必须支持重试，使用 tenacity 实现指数退避。

## 存储规范
1. 文件存储使用抽象层，开发用本地文件系统，生产可切 S3。
2. 上传文件大小限制 100MB，MIME 类型白名单校验。

## Prompt 版本管理规范
1. 所有 LLM Prompt 存放在根目录 prompts/ 下，带版本号（如 kg_qa_v1.md）。
2. Prompt 修改必须新增版本，不允许原地覆盖历史版本。
3. Python 代码通过 prompt_loader.py 从文件系统加载 Prompt，禁止硬编码。

## 安全底线
1. 所有外部输入必须经 Pydantic 严格校验。
2. 所有对外 API 必须配置限流（slowapi）。
3. 日志中禁止输出密钥、Token、密码等敏感信息。

## 代码质量规范
1. 后端使用 Black + Ruff 格式化，前端使用 Prettier + ESLint。
2. 提交前必须通过 pre-commit hook。

## 跨平台一致规范
1. 仓库统一使用 LF 换行符，通过 .gitattributes 强制。
2. 脚本涉及文件字节比较时，必须先对 CRLF 做归一化，避免误报。

## Git 提交规范
使用 Conventional Commits：feat / fix / docs / chore / refactor / test

3. 创建 3 个 Harness Rules（always-on / model-decision / glob）。

4. 创建 13 个 Superpowers 技能（每个在 .codebuddy/skills/<技能名>/SKILL.md 下，中文，含名称、用途、触发条件、执行步骤、输出格式）：
   ① brainstorming ② writing-plans ③ executing-plans ④ test-driven-development
   ⑤ systematic-debugging ⑥ verification-before-completion ⑦ requesting-code-review
   ⑧ subagent-driven-development ⑨ using-superpowers ⑩ writing-skills
   ⑪ dispatching-parallel-agents ⑫ using-git-worktrees ⑬ finishing-a-development-branch
   （不要使用任何名为 skill-creator 的工具，直接创建目录和文件即可。）

5. 创建 prompts/ 下的 5 个业务运行时提示词模板（带版本号，英文写核心提示词，末尾附中文说明）：
   kg_qa_v1.md, document_parse_v1.md, entity_relation_extract_v1.md, chunk_summary_v1.md, intent_router_v1.md

6. 创建 specs/_template/ 下的 3 个 OpenSpec 风格模板文件（包含可填充占位格式）：
   proposal.md, design.md, tasks.md

7. 创建 README.md，用中文说明目录分工。

8. 语言规范：CODEBUDDY.md、README.md、rules/、specs/_template/ 用中文；prompts/ 用英文+中文说明；13 个技能 SKILL.md 用中文。

9. 在项目根目录创建 .gitignore，必须逐字写入以下完整内容：
   # Python
   .venv/
   __pycache__/
   *.pyc
   *.pyo
   *.pyd
   .env
   .env.*
   !.env.example

   # Node / Next.js
   node_modules/
   .next/
   out/
   build/
   dist/
   npm-debug.log*
   yarn-debug.log*
   yarn-error.log*
   .pnpm-debug.log*

   # 项目特定
   uploads/
   **/output/*
   !**/output/.gitkeep
   *.log
   *.db
   *.db-journal

   # 系统文件
   .DS_Store
   Thumbs.db

   # CodeBuddy 临时计划文件
   .codebuddy/plans/

10. 在项目根目录创建 .gitattributes，逐字写入以下内容：
    # 统一换行符为 LF（跨平台一致）
    * text=auto eol=lf

    # 二进制文件不做换行转换
    *.png binary
    *.jpg binary
    *.jpeg binary
    *.gif binary
    *.ico binary
    *.pdf binary
    *.db binary

    # Windows 批处理文件保持 CRLF
    *.bat text eol=crlf
    *.cmd text eol=crlf

11. 完成后列出完整文件树，逐一检查 CODEBUDDY.md 中引用的每个路径是否都有对应文件。

12. 【关键补充】确认无误后，在根目录执行 Git 提交：
    git add .
    git commit -m "chore: init project scaffolding and SDD structure"

13. 【关键补充 - 分支流程】提交完成后，把 feature/scaffolding 分支推送到远程（建立追踪），但【不要】提前合并到 main：
    git push -u origin feature/scaffolding

    说明（重要）：
    - Sprint 1 的其余阶段（Spec 生成、契约设计、前端类型、CI 校验）都继续在 feature/scaffolding 分支上开发。
    - 只有 Sprint 1 最终收尾时，才统一执行 git checkout main && git merge --no-ff feature/scaffolding，并打 v0.1.0 tag。
    - 提前合并到 main 会导致 Sprint 1 收尾时 merge 无事可做，或产生分支历史混乱。

    完成后报告：当前分支、git log --oneline 最近 5 条、git status --short、远程分支是否创建成功（git ls-remote --heads origin）。
```

## 阶段二：需求探索与 Spec 生成

### 2\.1 第一轮：发散

【使用模式：Plan】

```Plain Text
[R] 你是一位专注企业知识管理的资深产品分析师。
[C] 背景信息：我要做一个多模态知识库系统，支持 PDF、DOCX、CSV 上传，自动解析、抽取实体关系、构建知识图谱，并支持基于知识图谱的问答。
[T] 请输出结构化调研验证报告：
1. 市场机会与痛点地图（Top 5）。
2. 竞品分析（ChatPDF/Notion AI 为什么没完全解决）。
3. 切入建议与 GO/NO-GO 判断。
[约束]
- 先拆解任务为待办清单。
- 关键结论加粗。
- 完成后写入 docs/01-research.md。
```

### 2\.2 第二轮：收敛

【使用模式：Plan】

```Markdown
[R] 你是一位精通 RAG 和知识图谱的产品经理，偏好 MVP 思维。
[C] 基于 docs/01-research.md。
[T] 请输出产品整体大纲：
1. 产品定位。
2. 目标用户画像。
3. MVP 功能模块（不超过 6 个）。
4. 模块优先级（P0/P1/P2）。
5. 用户主流程。
[约束]
- 每个模块功能点不超过 5 个。
- 完成后写入 docs/02-product-outline.md。
```

### 2\.3 第三轮：精确

【使用模式：Plan】

```Plain Text
[R] 你是一位严谨的技术产品经理。
[C] 基于 docs/02-product-outline.md，技术栈为 FastAPI + React + MinerU + LangExtract + LangChain + Neo4j。
[T] 请为每个 P0 模块输出详细 MVP 规格，写入 specs/ 目录下对应的 .md 文件，并生成汇总 PRD 文档 docs/03-prd.md：
1. 模块边界：In Scope / Out of Scope。
2. 核心用户故事。
3. 验收标准：WHEN [操作] THEN [响应] AND [条件]。
4. 数据模型概要。
5. 模块间依赖关系。
[约束]
- 每个模块 In Scope 不超过 5 个功能点。
```

## 阶段三：极简契约先行（3\.1 / 3\.2 / 3\.3 三子阶段）

> 说明：本项目采用后端驱动契约（Backend\-Driven Contract）——以 FastAPI 的 Pydantic 模型为契约真源，通过 `app.openapi()` 自动导出 `contracts/openapi.yaml`，前端通过 `openapi-typescript` 消费该契约。契约不会与后端代码脱节，CI 的 `git diff --exit-code` 会阻止契约漂移。
> 
> 

### 3\.1 契约 \+ 后端骨架（可运行程度）

【使用模式：Plan → 遇到澄清时回答，然后切 Craft 执行】

在 Plan 模式发送：

```Plain Text
请基于 specs/ 目录下的规范文档和 docs/adr/ 下的 3 份 ADR，设计后端 API 契约。

要求：
1. 输出到 contracts/openapi.yaml。
2. 必须包含 5 个核心接口：
   - GET  /api/v1/health
   - POST /api/v1/documents/upload（返回 task_id，异步）
   - GET  /api/v1/documents/{id}/status
   - GET  /api/v1/documents/{id}/graph
   - POST /api/v1/agent/query
3. 统一错误响应结构：{code, message, detail, trace_id}。
4. 错误码枚举必须包含（来自 ADR-0001/0002/0003）：
   - TASK_INTERRUPTED（ADR-0001）
   - KG_VERSION_NOT_ACTIVE（ADR-0002）
   - 403 租户隔离语义（ADR-0003）
5. 所有接口必须包含 org_id 租户隔离语义（请求头或认证态注入）。
6. 同时生成 docs/multimodal_rag_backend_api_spec-v1.0.md（人类可读版）。

【机器强制同步机制】
- 后端：在 backend/ 中编写脚本，通过 FastAPI 的 app.openapi() 自动导出 contracts/openapi.yaml。
- 前端：在 frontend/ 中安装 openapi-typescript，配置 npm 脚本 gen:api。
- CI 中加入"契约校验"步骤：重新生成 TS 类型，git diff --exit-code，若类型文件有变化则失败。

【CRLF 归一化要求（关键）】
scripts/export_openapi.py 在做 --check 字节比较前，
必须先对磁盘文件内容做 content.replace(b"\r\n", b"\n") 归一化。
原因：Git 在 Windows 上可能把工作区文件转成 CRLF，导致误报不一致。
即使 .gitattributes 已配置 * text=auto eol=lf，也应该做这层防御。

【Prompt 版本管理】
- Prompt 存放在根目录 prompts/ 下，带版本号。
- 写一个 backend/app/prompts/prompt_loader.py 从文件系统加载 Prompt，禁止硬编码。
```

**CodeBuddy 会提出澄清问题**，你按以下推荐回答：

- graph 端点响应体：选 A（返回节点\+边明细，含 kg\_version，按 ADR\-0002 仅取 active 版本）。

- backend 本次做到什么程度：选 A 的精简版——health 真实可用、upload/status 落 PG（SQLite 兜底）、graph/query 501 占位；不做 TaskManager/Saga/RLS/Neo4j 真实查询。

- openapi\.yaml 是否纳入其余端点：选 B（严格只要 5 个）。

- 如何执行跨目录修改：选 C（分阶段且每阶段停下确认：3\.1 契约\+后端 → 3\.2 前端 → 3\.3 CI）。

**关于 dev 数据库**：同意 SQLite 临时兜底，但要在 `backend/CODEBUDDY.md` 和 `docs/adr/ADR-0003` 标注"SQLite 仅 Sprint 1 契约验证用，Sprint 3 必须切 PostgreSQL 并启用 RLS"。

关于 `KG_VERSION_NOT_ACTIVE` 统一取 409：同意，并同步把 `specs/m2-extract-kg.md` §5\.4 里的 404 改为 409。

关于 `/health` 豁免 org 上下文：同意。

#### 3\.1 验收（手动在终端执行）：

```Bash
cd d:/AIProject/GraphRAG-Agent/backend

# 1. 依赖同步
uv sync

# 2. 运行测试
uv run pytest -v
# 期望：全部 passed

# 3. 契约导出幂等性
uv run python scripts/export_openapi.py
git diff ../contracts/openapi.yaml   # 应无输出
uv run python scripts/export_openapi.py
git diff ../contracts/openapi.yaml   # 应无输出（幂等性成立）

# 4. 冒烟：服务能启动
uv run uvicorn app.main:app --reload --port 8000
# 另一个终端：curl http://127.0.0.1:8000/api/v1/health
```

3\.1 通过后提交：

```Plain Text
阶段 3.1 验收全部通过。请提交本次变更：
git add .
git commit -m "feat: add openapi contracts and backend skeleton (Sprint 1.3.1)"
```

### 3\.2 前端类型生成

【使用模式：Craft】

```Plain Text
请执行阶段 3.2：前端类型生成。

要求：
1. 在 frontend/ 中安装 openapi-typescript（devDependency）：
   npm install -D openapi-typescript
2. 在 frontend/package.json 增加脚本：
   "gen:api": "openapi-typescript ../contracts/openapi.yaml -o src/types/api.d.ts"
3. 创建目录 frontend/src/types/（如果不存在）。
4. 运行 npm run gen:api，生成 src/types/api.d.ts。
5. 验证幂等性（用真证据，不要假阳性）：
   - 用 SHA256 连续生成 3 次，哈希应完全一致
   - 用 git diff --no-index 做文件级比对，应零差异
6. 打开 src/types/api.d.ts，确认包含：
   - 5 个接口的 path 类型
   - 错误码枚举（components["schemas"]["ErrorCode"] 的联合类型）
7. 在 frontend/CODEBUDDY.md（不存在则新建）写明：
   "修改 contracts/openapi.yaml 后，必须运行 npm run gen:api 同步类型。"
8. 完成后列出：新增脚本、api.d.ts 行数、三次 SHA256 结果。

不要修改 backend/、contracts/、.github/。
```

3\.2 通过后提交：

```Plain Text
阶段 3.2 验收通过。请提交：
git add frontend/
git commit -m "feat: add openapi typescript codegen (Sprint 1.3.2)"
```

### 3\.3 CI 契约校验

【使用模式：Craft】

```Plain Text
请执行阶段 3.3：CI 契约校验工作流。

要求：
1. 在 .github/workflows/ci.yml 创建完整流水线：
   - 触发：push 到 main、所有 pull_request
   - 后端 Job：安装 uv → uv sync → uv run ruff check . → uv run ruff format --check . → uv run pytest
     （注意：working-directory: backend，因为 uv 需要定位到 pyproject.toml）
   - 前端 Job：Node 22 → npm ci → npm run lint → npm run gen:api
   - 契约校验 Job（关键）：
     a. 检查 backend/：uv run python scripts/export_openapi.py --check
     b. 检查 frontend/：npm run gen:api 后，git diff --exit-code frontend/src/types/api.d.ts
     任一 diff 不为空则 Job 失败。
2. 所有 Job 失败时输出失败摘要到 $GITHUB_STEP_SUMMARY。

注意：next@16+ 要求 node>=20.9，故 CI 使用 Node 22 LTS，
与根 .nvmrc 保持一致。不要用 Node 18。

不要修改业务代码，只新增/修改 .github/workflows/ 下的文件。
```

3\.3 通过后提交：

```Plain Text
阶段 3.3 验收通过。请提交：
git add .github/
git commit -m "ci: add contract validation workflow (Sprint 1.3.3)"
```

## ✅ Sprint 1 最终验收

```Plain Text
# 核心文件检查
ls specs/*.md                           # 至少 5 个 Spec 文件
ls docs/adr/*.md                        # 3 个 ADR 文件
ls contracts/openapi.yaml               # 契约存在
ls docs/multimodal_rag_backend_api_spec-v1.0.md   # 人类可读版存在
ls .github/workflows/ci.yml             # CI 存在
ls .python-version .nvmrc .gitattributes # 版本锁定 + 换行符规范
ls frontend/src/types/api.d.ts          # 前端类型生成

# 后端测试
cd backend && uv run pytest -v && cd ..

# 前端类型幂等
cd frontend && npm run gen:api && git diff src/types/api.d.ts && cd ..
```

Sprint 1 最终收尾（此时才合并到 main）：

```Plain Text
Sprint 1 全部完成。请执行最终收尾：

1. 确认当前在 feature/scaffolding 分支。
2. 提交所有剩余变更（如果有）：
   git status --short
   （如果有改动，git add . && git commit -m "chore: sprint 1 final cleanup"）

3. 打附注 tag：
   git tag -a v0.1.0 -m "Sprint 1 done: scaffolding + contracts + CI ready"

4. 合并回 main 并推送：
   git checkout main
   git merge --no-ff feature/scaffolding -m "merge: sprint 1 done (v0.1.0)"
   git push origin main
   git push --tags

5. 完成后报告：
   - 当前分支
   - git log --oneline 最近 10 条
   - git tag 输出
   - git ls-remote --tags origin 输出
   - git status --short
```

**推送后去 GitHub Actions 验证**：

- 打开仓库 → Actions 标签

- 查看最新 workflow run

- 检查 4 个 job：`backend`、`frontend`、`contract`（关键，必须绿）、`ci-summary`

# 三、Sprint 2：MVP 独立验证

## 阶段四：MinerU MVP

【使用模式：Craft】

```Plain Text
请参考 MinerU 官方文档（https://mineru.net/apiManage/docs），在根目录的 mineru_mvp/ 下创建最小可运行脚本。

注意：独立测试目录，使用独立 uv 虚拟环境，不要放进 backend/。

【MinerU API 流程（实测为准，v4 接口）】
1. POST /api/v4/file-urls/batch  申请上传链接，返回 batch_id 和 file_urls
2. PUT 上传本地 PDF 到 OSS 预签名链接（不带 Content-Type）
3. 轮询 GET /api/v4/extract-results/batch/{batch_id}
   状态流转：waiting-file -> pending -> running -> done
4. 从 full_zip_url 下载结果 zip 并解压到 output/

【认证要求】
所有请求头必须携带：Authorization: Bearer <MINERU_TOKEN>
漏掉会返回 401，被 tenacity 重试 3 次后才报错，浪费约 7 秒。

【要求】
1. 创建 .env.example 和 .env（放真实 Token）。
   - .env 变量名：MINERU_TOKEN
   - 确认 .env 已被 .gitignore 忽略，不会提交。
2. run_mvp.py 实现：本地 PDF -> MinerU API -> 输出 Markdown + JSON 到 output/。
3. 使用 httpx + tenacity 实现重试（最多 3 次，指数退避：1s -> 2s -> 4s）。
4. 执行命令统一用 uv run python run_mvp.py。
5. 确认 mineru_mvp/output/ 下保留 .gitkeep，并用 git add -f 强制加入版本库
   （**/output/* 会忽略它，必须 -f 绕过）。
6. Windows GBK 控制台打印 "•" 等特殊字符会报 UnicodeEncodeError，
   请显式设置 sys.stdout.reconfigure(encoding="utf-8") 或改用 ASCII 符号。

【兼容 v1 / v2 输出结构】
- MinerU VLM 模型默认输出 *_content_list_v2.json（官方文档只提 v1）。
- v1 结构：顶层是条目列表，表格 HTML 在 item["body"]。
- v2 结构：顶层是页列表，每页嵌套条目列表，表格 HTML 在 item["content"]["html"]。
- 解析时请兼容两种格式，自动检测。

【复杂 PDF 测试】
另写 make_complex_pdf.py，用 reportlab 生成复杂 PDF，包含：
标题 + 说明段落 + 4 列 5 行表格（含数值和百分比，需支持负数）+ 摘要列表。
中文用 CID 字体 STSong-Light（reportlab 内置，无需额外字体文件）。
把这个 PDF 作为输入，重新跑一次 run_mvp.py。
读取 output/ 下的 content_list_v2.json，检查表格内容有没有被正确结构化出来。

【约束】
- 独立 MVP 目录，不要放进 backend/。
- 不要修改 backend/、frontend/、contracts/。

【完成后报告】
1. 生成文件列表
2. 执行结果（含状态流转日志）
3. 表格解析结果（HTML 原文，行数列数）
4. output 目录清单
5. 与官方文档不一致的实测差异（实测结果反哺规则）
```

### 验收标准

核心文件检查：

```PowerShell
# 必须存在
dir mineru_mvp/run_mvp.py
dir mineru_mvp/make_complex_pdf.py
dir mineru_mvp/pyproject.toml
dir mineru_mvp/uv.lock
dir mineru_mvp/.env.example
dir mineru_mvp/input/complex_table.pdf

# .env 必须存在但被忽略
git check-ignore mineru_mvp/.env
# 期望：输出 mineru_mvp/.env（表示被忽略）

# .gitkeep 必须被强制跟踪
git ls-files mineru_mvp/output/
# 期望：mineru_mvp/output/.gitkeep
```

执行验证：

```PowerShell
cd mineru_mvp
uv run python run_mvp.py
# 期望：API 200 -> 上传成功 -> 轮询到 done -> 解压到 output/complex_table/
```

打开该文件，确认：

- 存在 1 个 `type: "table"` 条目

- 表格 HTML 为 4 列 × 6 行（含表头）

- 数值和百分比全部正确（含负号 `-8.3%`）

安全确认：

```PowerShell
git status --short
# .env 绝对不能出现在列表里
```

### 实测反哺记录

### 通过后提交

```PowerShell
git add mineru_mvp/
git commit -m "feat: mineru mvp validated (Sprint 2.4)"
git push origin feature/sprint-2
```

## 阶段五：LangExtract MVP

【使用模式：Craft】

```Python
请参考 LangExtract 源码，在根目录的 langextract_mvp/ 下创建最小可运行脚本。

注意：独立测试目录，独立 uv 虚拟环境，不要放进 backend/。

【LangExtract 调用 DeepSeek 的 6 条实测要点（务必全部配置）】
1. 显式传 provider="openai"。
   原因：langextract/providers/patterns.py 的 OLLAMA_PATTERNS 含 ^deepseek，
   不显式指定会被 Ollama Provider 抢走。
2. use_schema_constraints=False。
   原因：DeepSeek 不支持 OpenAI 的 json_schema 严格结构化输出，
   langextract 默认会生成 {"type":"json_schema","strict":true}，DeepSeek 会拒绝。
   回退到 json_object 模式。
3. fence_output=False。
   原因：走原生 JSON 输出，不要再包 ``` 代码块。
4. tokenizer=UnicodeTokenizer()（★ 最关键）。
   原因：默认 RegexTokenizer 的 _LETTERS_PATTERN = r"[^\W\d_]+" 会把
   连续汉字整段当成一个 token（如 "云计算板块实现收入" 是一个 token），
   导致中文实体名（人名、公司名）无法对齐原文，char_interval 全为 None，
   GraphRAG 溯源直接断链。
   UnicodeTokenizer 逐字切分 CJK，实测 0 告警、全部 MATCH_EXACT。
   导入方式：from langextract.core.tokenizer import UnicodeTokenizer
5. base_url 填 https://api.deepseek.com（不带 /chat/completions），
   openai SDK 会自动拼接路径。
6. 模型名填 deepseek-chat（或 deepseek-reasoner）。

【要求】
1. 使用 DeepSeek 作为 OpenAI Provider，创建 .env.example 和 .env。
   - .env 变量名：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
   - 确认 .env 已被 .gitignore 忽略，不会提交。
2. 模拟文本 -> LangExtract 抽取 -> 输出 JSONL 到 output/extractions.jsonl。
3. 使用 uv run python run_mvp.py 运行并给出结果。
4. 确认 langextract_mvp/output/ 下保留 .gitkeep，并用 git add -f 强制加入版本库
   （**/output/* 会忽略它，必须 -f 绕过）。
5. 脚本头部用注释记录上述 6 条差异（实测结果反哺规则）。
6. 运行完成后打印每一条抽取的摘要，末尾校验 char_interval 为 null 的条目数
   应为 0，否则说明 tokenizer 没生效。
7. Windows GBK 控制台打印特殊字符会报 UnicodeEncodeError，
   请显式设置 sys.stdout.reconfigure(encoding="utf-8")。

【模拟文本要求】
一段中文企业年报摘录，包含：
公司名、营收数字、同比增长率、业务板块、控股关系、持股比例、人物职务。
建议包含 2 个以上子公司和 1-2 位高管，方便验证关系抽取和中文溯源。

【约束】
- 独立 MVP 目录，不要放进 backend/。
- 不要修改 backend/、frontend/、contracts/。

【完成后报告】
1. 生成文件列表
2. 执行结果（含抽取条数和对齐状态）
3. 抽取出的实体关系示例
4. output 目录清单
5. char_interval 为 null 的条目数（必须为 0）
6. 与官方文档不一致的实测差异
```

### 验收标准

核心文件检查：

```PowerShell
dir langextract_mvp/run_mvp.py
dir langextract_mvp/pyproject.toml
dir langextract_mvp/uv.lock
dir langextract_mvp/.env.example
dir langextract_mvp/sample_text.txt

# .env 必须存在但被忽略
git check-ignore langextract_mvp/.env
# 期望：输出 langextract_mvp/.env

# .gitkeep 必须被强制跟踪
git ls-files langextract_mvp/output/
# 期望：langextract_mvp/output/.gitkeep
```

执行验证：

```PowerShell
cd langextract_mvp
uv run python run_mvp.py
# 期望：0 条对齐告警，全部定位原文，char_interval 为 null 的条目数 = 0
```

安全确认：

```PowerShell
git status --short
# .env 绝对不能出现在列表里
```

### 实测反哺记录

差异 6 说明（务必牢记）：

- 默认 RegexTokenizer 对中文年报：3 条 few\-shot 对齐失败，4 个中文实体 `char_interval` 为 None，无法溯源。

- UnicodeTokenizer（逐字切分 CJK）：0 条失败，全部 `MATCH_EXACT`。

- 这是 GraphRAG 溯源的硬伤，Sprint 3 后端接入 LangExtract 时必须同样传 UnicodeTokenizer。

### 通过后提交

```PowerShell
git add langextract_mvp/
git commit -m "feat: langextract mvp validated (Sprint 2.5)"
git push origin feature/sprint-2
```

## 阶段六：Bridge Pipeline

【使用模式：Craft】

```Plain Text
请参考 docs/mineru_cloud_api_spec.md 和 docs/langextract_spec.md，
制定桥接规范并实现 Bridge Pipeline。

【重要：三份规范文档可能缺失】
docs/ 下的 mineru_cloud_api_spec.md / langextract_spec.md /
bridge-pipeline-specification-v1.0.md 如果不存在，
请先依据 mineru_mvp/ 和 langextract_mvp/ 的实测代码补齐这三份 spec，
再开始实现桥接。规范必须以实测为准，不能照抄官方文档。

【MinerU 输出路径（实测为准）】
- MinerU 输出在 mineru_mvp/output/<任务子目录>/ 下，不是直接放在 output/ 根目录。
- 脚本需要递归遍历 output/ 下的子目录，按 mtime 取最新的 full.md。
- 每个任务子目录里有：
  - full.md                    -> 最终 Markdown，表格以 HTML 嵌入
  - *_content_list.json        -> v1 结构（条目列表，表格 HTML 在 item["body"]）
  - *_content_list_v2.json     -> v2 结构（页列表嵌套，表格 HTML 在 item["content"]["html"]）
- 如果 full.md 不存在，回退到解析 v2 json，提取 content.text 和 content.html。

【LangExtract 调用要求（阶段五实测，务必全部配置）】
1. provider="openai"（否则 deepseek* 被 Ollama Provider 抢走）
2. use_schema_constraints=False（DeepSeek 不支持 json_schema 严格模式）
3. fence_output=False（走原生 JSON 输出）
4. tokenizer=UnicodeTokenizer()（★ 中文溯源硬伤，不传则 char_interval 全为 null）
5. base_url = https://api.deepseek.com（不带 /chat/completions）
6. 模型名 deepseek-chat

【Prompt 约束（阶段六实测，差异 7）】
- 要求模型"逐字对齐原文"。
- 表格数值实体：数值与单位必须分开，
  数值放在 entity 文本，单位放在 attributes。
  例：不要把 "128,560 万元" 当作一个实体，而应输出 entity="128,560",
  attributes={unit:"万元"}。
  原因：原文中数值和单位不连续，拼成一个串会导致 char_interval 找不到。
- 实测效果：未定位实体 14 -> 6（表格数值 100% 定位）。

【Bridge Pipeline 要求】
1. 读取 mineru_mvp/output/ 下最新的 full.md。
2. 提取纯文本，清洗（去 HTML 标签、多余空白、页眉页脚），记录清洗前后字符数。
3. 送入 LangExtract，输出实体关系 JSON 到 bridge_web_demo/output.json。
4. 每条实体必须携带 grounded / char_interval / alignment_status 三个字段。
5. 严格遵循 docs/bridge-pipeline-specification-v1.0.md。

【单页面 HTML 可视化工具】
在 bridge_web_demo/ 下写单页面可视化（前端 + 极简 FastAPI 后端）：
1. 上传 PDF。
2. 触发 Bridge Pipeline。
3. 实时展示流程状态（含步骤级耗时）。
4. 展示抽取结果列表，自动渲染知识图谱视图（Canvas 力导向即可，零外部 CDN）。
5. FastAPI 接口：POST /api/jobs 返回 202，状态轮询 pending->processing->completed，
   GET /api/jobs/{id}/result 返回实体关系 JSON，未知 job 404，非 PDF 400。
6. 严格遵循 docs/bridge-pipeline-specification-v1.0.md。

【约束】
- 独立 MVP 目录，不要放进 backend/。
- 不要修改 backend/、frontend/、contracts/、mineru_mvp/（只读其 output/）。
- .env 必须被 .gitignore 忽略。
- output/ 下保留 .gitkeep 并用 git add -f 强制入库。
- 如根 .gitignore 对 uploads/ 目录不生效，在 MVP 内补一份局部 .gitignore。

【完成后报告】
1. 生成文件列表
2. 执行结果（含读取的 full.md 路径、清洗前后字符数、实体数、关系数、未定位实体数、耗时）
3. 实体关系示例
4. FastAPI 冒烟测试结果
5. output 目录清单
6. 与官方文档不一致的实测差异
```

### 验收标准

核心文件检查：

```PowerShell
dir bridge_web_demo/bridge_pipeline.py
dir bridge_web_demo/mineru_client.py
dir bridge_web_demo/server.py
dir bridge_web_demo/index.html
dir bridge_web_demo/pyproject.toml
dir bridge_web_demo/uv.lock
dir bridge_web_demo/.env.example
dir bridge_web_demo/output.json
dir docs/mineru_cloud_api_spec.md
dir docs/langextract_spec.md
dir docs/bridge-pipeline-specification-v1.0.md

# .env 必须存在但被忽略
git check-ignore bridge_web_demo/.env
# 期望：输出 bridge_web_demo/.env

# .gitkeep 必须被强制跟踪
git ls-files bridge_web_demo/output/
# 期望：bridge_web_demo/output/.gitkeep
```

执行验证：

```PowerShell
cd bridge_web_demo
uv run python bridge_pipeline.py
# 期望：读取到 full.md，实体数 >= 20，未定位实体 <= 10
```

FastAPI 冒烟：

```PowerShell
uv run uvicorn server:app --port 8100
# 另一个终端：
curl http://127.0.0.1:8100/api/health
# 期望：200
```

安全确认：

```PowerShell
git status --short
# .env 绝对不能出现在列表里
```

### 实测反哺记录

差异 7 说明（务必牢记）：

- 未定位实体从 14 降到 6，表格数值 100% 定位。

- 剩余 6 个未定位为模型输出的指标名/描述性短语（如"营业收入"、"集团"），属模型侧问题，不要在桥接层强行修补。

- Sprint 3 后端 `prompts/entity_relation_extract_v1.md` 必须带上这条对齐约束。

### 通过后提交

```PowerShell
git add bridge_web_demo/ docs/
git commit -m "feat: bridge pipeline validated (Sprint 2.6)"
git push origin feature/sprint-2
```

## 阶段七：LangChain Agent MVP

【使用模式：Craft】

```Markdown
请参考 LangChain 官方文档，在 langchain_mvp/ 下创建最小可运行脚本。

注意：独立测试目录，独立 uv 虚拟环境，不要放进 backend/。

【重要：LangChain 1.x 已换代】
- 官方最新推荐 langchain.agents.create_agent（LangGraph CompiledStateGraph 底座）。
- 旧文档里的 create_react_agent / AgentExecutor / return_intermediate_steps 已不再适用。
- create_agent 签名：create_agent(model, tools, *, system_prompt=None,
  middleware=(), response_format=None, ...)
  注意参数是 system_prompt=（不是 prompt=），写错会直接 TypeError。
- 思考过程获取：用 agent.stream({...}, stream_mode="values")，
  逐帧取 state["messages"]，自行维护 seen 游标（values 模式返回累积列表）。
- ChatOpenAI.use_responses_api（1.6.2 新增，默认 None）：
  实测直连 https://api.deepseek.com 时默认值可用，但为稳妥显式传 False。

【要求】
1. 使用 uv 建独立虚拟环境，安装 langchain langchain-openai python-dotenv。
2. 创建 .env.example 和 .env，读取 DeepSeek API Key。
   - .env 变量名：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
   - 确认 .env 已被 .gitignore 忽略，不会提交。
3. 读取 bridge_web_demo/output.json 的实体关系 JSON，
   定义工具 search_knowledge_graph(query: str) -> str。
4. 创建 ReAct Agent，用户输入"帮我查一下智能制造的营收"，
   Agent 自动调用工具并生成回答。
5. 使用 uv run 运行，打印 Agent 思考过程和最终回答。
6. 确认 langchain_mvp/output/ 下保留 .gitkeep，并用 git add -f 强制加入版本库。
7. Windows 环境：
   - 显式设置 sys.stdout.reconfigure(encoding="utf-8")。
   - 中文实参不要走 `python -c "中文"` 命令（PowerShell 会 GBK 乱码），
     改用 argparse 从源码里读（源码必须 UTF-8）。
8. 必须提交 uv.lock 到 Git（CODEBUDDY.md 要求）。

【工具实现要点（阶段七实测）】
- DeepSeek 会自行改写工具入参：
  输入 "帮我查一下华辰智能的营收" -> 工具收到 {"query": "华辰智能 营收"}。
  工具必须做 2-gram 模糊匹配，不能假设 query 是干净实体名。
- 分层匹配建议：
  - 完整实体名命中 -> 高分（90）
  - 关键词被实体名包含 -> 中分（70）
  - 字符重叠（bigram） -> 低分（40）
- 工具返回必须包含：实体名、类型、匹配分、grounded、char_interval、
  alignment_status、属性、关联关系。

【防幻觉约束】
- system_prompt 中明确：未命中实体不得臆造，不得把图谱内其它主体的数据
  归因到查询对象；如查询主体不在图谱中，直接说明"图谱中没有该实体"。
- system_prompt 中明确：所有文字输出（含工具调用前的思考说明）使用简体中文，
  否则 temperature=0 下 DeepSeek 仍会用英文写思考句。

【数据源提醒】
- 输入是 bridge_web_demo/output.json，结构为 schema_version 1.0。
- 每条实体带 grounded / char_interval / alignment_status。

【约束】
- 独立 MVP 目录，不要放进 backend/。
- 不要修改 backend/、frontend/、contracts/、mineru_mvp/、bridge_web_demo/。

【完成后报告】
1. 生成文件列表
2. 执行结果（含 Agent 思考过程、工具调用、耗时）
3. 最终回答
4. output 目录清单
5. 与官方文档不一致的实测差异
```

### 验收标准

```PowerShell
# 核心文件
dir langchain_mvp/kg_tools.py
dir langchain_mvp/agent_react.py
dir langchain_mvp/pyproject.toml
dir langchain_mvp/uv.lock
dir langchain_mvp/.env.example

# .env 必须被忽略
git check-ignore langchain_mvp/.env

# uv.lock 必须入库
git ls-files langchain_mvp/uv.lock
# 期望：langchain_mvp/uv.lock

# .gitkeep 必须被跟踪
git ls-files langchain_mvp/output/

# 执行
cd langchain_mvp
uv run python agent_react.py "帮我查一下智能制造的营收"
# 期望：Agent 调用工具、给出基于图谱的回答
```

### 实测反哺记录

差异 4 说明（务必牢记）：

- Agent 会把主体\+指标拼成一个 query 传给工具。

- 工具层必须做分词 \+ 2\-gram 分层模糊匹配，否则会大量误判"无命中"。

- Sprint 3 后端 `search_knowledge_graph` 工具设计必须继承这一点。

### 通过后提交

```PowerShell
git add langchain_mvp/
git commit -m "feat: langchain agent mvp validated (Sprint 2.7)"
git push origin feature/sprint-2
```

## Sprint 2 收尾流程

四个 MVP 全部验收通过后，按以下 4 步收尾。

### 第 1 步：运行产物停止跟踪

`bridge_web_demo/output.json` 是运行产物，每次跑 Pipeline 都会变。Sprint 2 结束时应停止跟踪，避免长期 diff 噪音。

在 `bridge_web_demo/.gitignore` 末尾追加一行：

```Plain Text
output.json
```

然后在项目根目录执行：

```PowerShell
git rm --cached bridge_web_demo/output.json
git status --short
```

期望看到（关键）：

```Plain Text
D  bridge_web_demo/output.json      （从版本库移除，本地文件保留）
M  bridge_web_demo/.gitignore       （修改未暂存）
```

验证本地文件未被误删：

```Plain Text
dir bridge_web_demo\output.json
# 期望：文件仍存在
```

### 第 2 步：提交收尾变更

```PowerShell
git add bridge_web_demo/.gitignore
git status --short
```

期望：

```PowerShell
M  bridge_web_demo/.gitignore
D  bridge_web_demo/output.json
```

提交推送：

```PowerShell
git commit -m "chore: sprint 2 final cleanup (ignore runtime artifacts)"
git push origin feature/sprint-2
```

推送超时处理：如遇 `curl 28` / `Connection was reset`，先用 `git ls-remote origin main` 做读写分离诊断：

- 读也失败 \-\> 网络问题，重试 3\-5 次；仍失败则 `git config --global http.version HTTP/1.1` 再重试。

- 读成功、写失败 \-\> 临时抖动，直接重试即可。

### 第 3 步：打 v0\.2\.0 附注 tag

```PowerShell
git tag -a v0.2.0 -m "Sprint 2 done: 4 MVP validated (MinerU/LangExtract/Bridge/LangChain)"
```

### 第 4 步：合并 main 并推送

```PowerShell
git checkout main
git pull origin main
git merge --no-ff feature/sprint-2 -m "merge: sprint 2 done (v0.2.0)"
git push origin main
git push --tags
```

期望 merge 结果：约 30 个文件、10000\+ 行插入，覆盖 mineru\_mvp / langextract\_mvp / bridge\_web\_demo / langchain\_mvp / docs 五个目录。

### Sprint 2 收尾验收

```PowerShell
git log --oneline -8
git tag
git ls-remote --tags origin
git status --short
```

期望：

- `git log` 顶部是 merge commit，往下能看到 4 个 MVP 提交 \+ v0\.1\.0。

- `git tag` 显示 `sprint-1-done`、`v0.1.0`、`v0.2.0` 三个 tag。

- `git ls-remote --tags` 能看到远程也有 v0\.1\.0 / v0\.2\.0。

- `git status --short` 无输出。

最后去 GitHub Actions 确认 CI 最新 run 全绿：

- 4 个 job 都是 Success（不是 skipped）：`后端`、`前端`、`契约校验`、`流水线汇总`。

- 特别是「契约校验」job，它跑契约漂移门禁，绿了说明 openapi\.yaml / Pydantic / TS 类型三方对齐。

### Sprint 2 收尾完成标志

- `main` 顶部是 `merge: sprint 2 done (v0.2.0)`

- 本地与远程 tag `v0.2.0` 一致

- CI 全绿

- 工作区干净

# 四、Sprint 3：全栈开发

## 阶段八：Pencil UI 设计稿

### 8\.0 前置准备

```PowerShell
cd d:/AIProject/GraphRAG-Agent
git checkout main
git pull origin main
git status --short          # 期望无输出
git checkout -b feature/sprint-3
git push -u origin feature/sprint-3
```

确认项：

- VSCode 已安装 Pencil 插件并邮箱激活

- CodeBuddy 插件已登录

- 工作区干净

### 8\.1 创建设计稿

#### 步骤 1：打开 Pencil 面板并保存文件

1. VSCode 左侧活动栏点击铅笔图标，打开 Pencil 面板。

2. 按 `Ctrl+Shift+S`，另存为到：

```PowerShell
d:/AIProject/GraphRAG-Agent/frontend/design.pen
```

（Pencil 面板内没有 Save 按钮，必须用 VSCode 原生另存为）

#### 步骤 2：在 Pencil 底部输入框粘贴以下提示词

```Markdown
你是一位资深企业级 SaaS 产品设计师。请严格基于以下产品需求文档（PRD）的核心逻辑，设计 4 个核心页面（P01 工作台首页、P02 文档管理页、P03 知识问答页、P04 知识图谱页）。

【业务上下文】
这是一个多模态知识库系统，支持 PDF/DOCX 上传，通过 MinerU 解析、LangExtract 抽取实体关系构建知识图谱，并提供基于图谱的 RAG 问答。

【核心页面设计要求】
1. P01 工作台首页：顶部数据看板。必须有 4 个数据卡片（已处理文档数、KG 实体总数、今日问答次数、成功率）。下方分左右两栏：左侧"最近文档处理列表"（文件名、状态、时间），右侧"最近问答历史"。
2. P02 文档管理页：数据表格为核心。顶部有明显的"上传文档"主按钮。表格列需包含：文件名、类型、状态、实体数、上传时间、操作（查看图谱/重新处理）。要设计状态标签（处理中蓝、已完成紫、失败红）。
3. P03 知识问答页：三栏布局。左侧"历史会话列表"（含新建按钮），中间"对话区"（用户气泡、AI回答气泡、引用来源折叠条），右侧"引用证据面板"（图谱节点/关系路径）。
4. P04 知识图谱页：全屏画布 + 右侧抽屉面板。画布展示力导向图（彩色实体节点 + 关系连线），右侧展示选中节点详情（名称、类型、属性、关联关系）。画布左下角需有图例。

【UI/UX 约束】
- 企业级后台风格，数据可视化优先，暗色科技风
- 配色参考：#0F1117 主背景、#1A102E 卡片底色、#4F8EF7 主操作色、#3D0399 成功态、#EF4D44 失败态
- 中文界面，字体清晰
- 每个页面画板尺寸统一 1200×800，页面之间水平排列（x 坐标依次递增 1240）
```

#### 步骤 3：导出为 PNG

1. 生成完毕后，在画布中按住 Shift 多选 4 个画板。

2. 右侧属性面板底部找到 `Export layers (4)` 按钮。

3. 设置：倍率 2x，格式 PNG。

4. 导出到 `frontend/` 目录，命名为：

    - `design_p01.png`（工作台首页）

    - `design_p02.png`（文档管理页）

    - `design_p03.png`（知识问答页）

    - `design_p04.png`（知识图谱页）

验收：4 张图在 `frontend/` 目录下，清晰可读，每张能看清布局和文字。

---

### 8\.2 Ask 模式读设计稿

1. CodeBuddy 面板切换到 Ask 模式（只读，不改代码）。

2. 把 `design_p01.png` \~ `design_p04.png` 这 4 张图拖拽到对话框。

3. 发送以下提示词：

```Plain Text
请查看我上传的 4 张设计稿图片，这是基于 PRD 设计的 4 个核心页面：
1. design_p01.png - 工作台首页
2. design_p02.png - 文档管理页
3. design_p03.png - 知识问答页
4. design_p04.png - 知识图谱页

整体风格为暗色科技风 SaaS 后台。

请告诉我：
1. 你从设计稿中读取到了哪些布局结构、组件类型、关键交互？
2. 这些设计稿需要的接口，与当前 contracts/openapi.yaml 的 5 个接口有哪些缺口？
3. 按项目规范【功能预留原则】，这些缺口应该如何处理？

不要修改任何代码，只做分析。
```

验收：CodeBuddy 输出详细的页面结构解析 \+ 接口缺口清单。

### 8\.3 Craft 模式生成前端代码

切换到 Craft 模式，发送：

```Plain Text
很好，分析非常精准。现在请正式进入前端代码生成阶段。

【执行原则】
- 严格以 4 张设计稿为视觉标准
- 不要修改 backend/ 和 contracts/，不要强行开发缺失的后端接口
- 缺失接口一律用 Mock 数据，建立独立 API 层方便后续切换

【具体要求】
1. 代码写到 frontend/ 目录下
2. 严格还原暗色科技风配色、布局（顶部栏 60px、侧栏 200px）、间距和组件风格
3. 使用 shadcn/ui 组件库
4. 建立独立 API 层（src/api/），使用 src/types/api.d.ts 中的类型。缺失的 Mock 结构扩展写到 src/types/mock.d.ts，不要动 contracts
5. 使用 Zustand 管理全局状态
6. 创建 frontend/.env.development、.env.production、.env.local.example：
   - NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
   - NEXT_PUBLIC_APP_ENV=development
   - 所有 .env.local 加入 .gitignore
7. 统一界面文案为中文
8. 每完成一个页面，运行 npm run dev 并截图给我看效果；如果无法截图，用 SSR 断言 + build + 路由状态码验证
9. 不要修改 backend/ 的任何代码
10. 如果运行 npm run dev 报错，请在当前对话告诉我，不要自己乱改配置
```

验收：

- `npx tsc --noEmit` 0 error

- `npx eslint src --max-warnings=0` 0 error

- `npm run build` 编译成功

- 浏览器打开 `http://localhost:3000`，4 个页面均可访问

---

### 8\.4 Git 收尾

按顺序执行，每步确认输出后再进行下一步：

```PowerShell
# 第 1 步：先检查状态
git status --short

# 第 2 步：检查最近 commit（CodeBuddy 可能已自动提交过前端代码）
git log --oneline -5
```

情况 A：如果 log 里已看到 `feat: frontend UI complete...`，说明 CodeBuddy 已提交，只需补交未提交的小改动：

```PowerShell
git add frontend/ .gitignore
git status --short           # 确认无 node_modules
git commit -m "chore: update .gitignore for env files"
git push origin feature/sprint-3
```

情况 B：如果 log 里没有前端提交，需要手动提交：

```PowerShell
git add frontend/ .gitignore
git status --short           # 期望看到几十个 A 开头的源码文件
                             # 绝对不应出现 frontend/node_modules/ 或 frontend/.next/
git commit -m "feat: frontend UI complete with mock api (Sprint 3.8)"
git push origin feature/sprint-3
```

### 8\.5 验收清单

```Bash
✅ frontend/design.pen              —— 4 页面设计稿源文件
✅ frontend/design_p01.png          —— 工作台首页
✅ frontend/design_p02.png          —— 文档管理页
✅ frontend/design_p03.png          —— 知识问答页
✅ frontend/design_p04.png          —— 知识图谱页
✅ frontend/src/app/                —— 4 个页面代码 + layout
✅ frontend/src/api/                —— 独立 API 层 + Mock
✅ frontend/src/store/              —— Zustand 全局状态
✅ frontend/src/components/ui/      —— shadcn/ui 组件
✅ frontend/.env.development        —— 已入库（无密钥）
✅ frontend/.env.local.example      —— 已入库
✅ frontend/.env.local              —— 已忽略（含真实配置）
✅ git log 显示前端提交记录
✅ git push 成功推送到 origin/feature/sprint-3
✅ npx tsc --noEmit 0 error
✅ npx eslint src --max-warnings=0 0 error
✅ npm run build 编译成功
```

### 8\.6 设计稿迭代流程

设计稿被 Pencil 修改后：

1. 重新导出 PNG 覆盖 `frontend/design.png`。

2. 新开一个对话，附上新图片。

3. 提示词：

```PowerShell
我更新了设计稿 frontend/design.png。请对比当前 frontend/ 的实现代码，找出与设计稿不一致的地方，并只改动不一致的部分。
要求：
1. 不要重写已经正确的组件。
2. 改完后运行 npm run dev 截图给我确认。
```

# 阶段九：后端开发与 Agentic\-RAG

## 编号说明

## 9\.0 前置准备

### 步骤 1：确认分支与环境

```PowerShell
cd d:/AIProject/GraphRAG-Agent
git branch --show-current          # 期望：feature/sprint-3
git status --short                 # 期望：无输出
docker ps --filter "name=neo4j"    # 期望：STATUS = Up
Select-String -Path backend/.env.development -Pattern "DEEPSEEK_API_KEY|NEO4J_PASSWORD|NEO4J_URI"
```

**若 Neo4j 未启动：**

```PowerShell
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest
Start-Sleep -Seconds 30
docker ps --filter "name=neo4j"
```

若 `.env.development` 未配置：从 `backend/.env.example` 复制并填入真实值（`DEEPSEEK_API_KEY`、`NEO4J_URI=bolt://``localhost:7687`、`NEO4J_USER=neo4j`、`NEO4J_PASSWORD=password`）。

### 步骤 2：修复根 `.gitignore`（关键）

打开根 `.gitignore`，找到 env 相关规则，必须是下面这样：

```Plain Text
.env
.env.*
!.env.example

# 仅放行 frontend 目录下的「不含密钥」的环境模板
# backend/.env.* 一律保持忽略（含 DeepSeek API Key）
!frontend/.env.development
!frontend/.env.production
!frontend/.env.local.example

**/.env.local
**/.env.local.*
!frontend/.env.local.example
```

关键点：`!frontend/...` 而不是 `!**/...`，避免放行 `backend/.env.development`。

### 步骤 3：验证 `.gitignore` 生效

```Plain Text
git check-ignore -v backend/.env.development    # 期望有输出（被忽略）
git check-ignore -v backend/.env                # 期望有输出（被忽略）
git check-ignore -v frontend/.env.development   # 期望无输出（被放行）
```

## 9\.1 后端 Service 骨架

### **提示词（Craft 模式）**

```Plain Text
进入 Sprint 3 阶段九 9.1：后端 Service 骨架。

【当前环境】
- Neo4j 已运行在 Docker：bolt://localhost:7687，用户名 neo4j，密码 password
- backend/.env.development 已配好 DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、NEO4J_*
- 后端骨架在 backend/，用 uv 管理依赖
- 契约 contracts/openapi.yaml 定义了 5 个接口
- 策略：本阶段跳过 Milvus，只跑通 Neo4j + Agentic-RAG

【本次目标：只做 service 骨架，不要一次做完所有事】
1. 补全 backend/app/services/ 下的核心 service：
   - TaskManager（含 recover_orphan_tasks() 供 lifespan 调用）
   - DocumentService（upload 返回 task_id，异步解析）
   - GraphService（对接 Neo4j，Cypher 查询）
   - AgentService（LangChain Agent + DeepSeek + 图谱检索）
2. 每个 service 的输入输出严格遵守 contracts/openapi.yaml
3. 所有第三方 API 调用必须使用 tenacity 重试

【必须遵守的架构约束】
1. 任务类型（TaskSpec/TaskStatus/RecoveryReport/TaskExecutorFn/TaskType）放
   backend/app/tasks/types.py 独立模块，避免 manager 和 registry 循环导入
2. BackgroundTasks 由路由层注入，不放在 TaskManager 内部
3. TaskManager 只做「落 pending + 注册执行体」，不写内存字典（ADR-0001 §3.1）
4. recover_orphan_tasks 由 main.py lifespan startup 触发（ADR-0001 §3.2）
5. asyncio.Semaphore(settings.task_parse_concurrency) 限流（ADR-0001 §3.3）
6. 所有 Cypher 必须带 WHERE n.kg_version = $kg_version（ADR-0002 §3.2）
7. service 层不直接读 org_id，由路由层注入 Identity（ADR-0003）
8. Prompt 一律通过 backend/app/prompts/prompt_loader.py 从根目录 prompts/ 加载，禁止硬编码

【tenacity 用法强制约束】
- 只用简单 API：stop_after_attempt(N) + wait_exponential(multiplier=X, max=Y)
- 严禁使用 multiplier_getter 参数（本地 tenacity 9.1.4 不存在此参数，会直接 TypeError）
- 严禁使用 reraise=True 后去 except RetryError（reraise=True 时抛的是原始异常，RetryError 永远不会到达）

【环境文件处理】
- pydantic-settings 会读 backend/.env，但你的配置在 backend/.env.development
- 请把 .env.development 复制一份为 backend/.env（本地文件，已被 .gitignore 忽略，不会入库）

【测试要求】
- uv run pytest 必须全绿
- 状态枚举只用合法值：pending / processing / completed / failed
- 新增 1 个测试验证 BackgroundTasks 真实推进状态

【约束】
- 不要修改 contracts/openapi.yaml（发现不一致只在报告里上报，不改）
- 不要修改 frontend/
- 后端所有命令用 uv run 前缀
- 路由层 501 暂不替换

【完成后报告】
- 新增文件列表（按路径列全）
- 修改文件列表 + 变更点
- uv run pytest 结果
- 与契约的对齐情况
- 与 ADR-0001/0002/0003 的对照
```

### 执行决策点

### 验收

```PowerShell
cd backend
uv run pytest -v
# 期望：34 passed（或更多），0 failed

cd ..
git status --short
# 期望：约 15 个文件，绝不出现 backend/.env*
```

### Git 收尾

```PowerShell
# 1. 看状态
git status --short

# 2. 添加
git add backend/ .gitignore

# 3. 再确认（关键：检查是否误加 .env）
git status --short
# 期望：约 15 个文件
# 绝对不能出现：backend/.env 或 backend/.env.development

# 4. 提交
git commit -m "feat: backend services skeleton with task manager, graph, agent (Sprint 3.9.1)"

# 5. 推送
git push origin feature/sprint-3
```

如果第 3 步看到 `.env` 被加进来：立刻 `git reset`，检查 `.gitignore` 是否按 9\.0 步骤 2 修复过。

---

## 9\.2 Neo4j 集成 \+ 数据导入

```Plain Text
进入 Sprint 3 阶段九 9.2：Neo4j 集成 + 数据导入。

【背景】
- Neo4j 运行在 bolt://localhost:7687，用户 neo4j，密码 password
- GraphService 已有骨架，但 Neo4j 库是空的
- Sprint 2 阶段六的产物在 bridge_web_demo/output.json（schema_version 1.0）

【本次目标】
1. 编写 backend/scripts/import_to_neo4j.py：
   - 从 bridge_web_demo/output.json 读实体和关系
   - 按 ADR-0002 三段式写入：
     a. 创建 KgVersion 节点，状态 writing
     b. Cypher MERGE 实体节点（带 kg_version 属性）和关系边
     c. 成功后 KgVersion 置 active；失败置 failed 并清理
   - tenacity 重试（stop_after_attempt(3) + wait_exponential(multiplier=1.0)）
   - argparse 接收 --input / --kg-version / --dry-run / --purge 参数
   - 输出统计：实体数、关系数、耗时、kg_version

2. 执行脚本，实际写入 Neo4j

3. Cypher 验证：
   - MATCH (n) RETURN count(n)
   - MATCH ()-[r]->() RETURN count(r)
   - MATCH (n {name:'数据安全合规'})-[r]-(m) RETURN n,r,m LIMIT 10

4. 更新 GraphService，新增 fetch_all_subgraph() 或扩展 fetch_document_subgraph()，
   让它可以对全部导入数据做查询，不只依赖 PG 里的 document_id

【关系写入强制要求（关键）】
- output.json 的 relations[].head / tail 字段存的是【实体名】（如"智能制造"），
  而 entities[].id 是【实体 ID】（如 e1）——两者不是一回事
- 写入关系前必须先建 name_to_id 映射，把实体名解析为实体 ID
- 无法解析的端点要【上报】到 warn 列表，不要静默丢弃
- 写入完成后【必须回读 Neo4j 真实计数】与期望值比对：
  如果 count(r) 与预期不符，抛错并触发三段式失败补偿
  这一步是防止"脚本打印写入 12 条，实际 count(r)=0"的静默丢失

【约束】
- 不改 contracts/openapi.yaml
- 不改 frontend/
- 所有命令用 uv run 前缀
- 脚本放 backend/scripts/
- 完成后报告：脚本路径、执行结果统计、Cypher 验证输出、GraphService 变更点

【过程中若发现契约缺口】
- 只上报，不改契约
- 例如 GraphEdge.type 契约枚举可能不包含 output.json 里的关系类型，
  此时做【受控投影】映射到契约内合法枚举值，真实类型保留在 properties.relation_name
```

### 验收

- `bridge_web_demo/output.json` 实体数 ≈ Neo4j 中 `count(n)`（KgVersion 节点另计）

- Cypher 查询返回非空

- `scripts/import_to_neo4j.py` 支持重复执行（MERGE 保证幂等）

- 关系写入后回读计数与期望值一致（若不一致应主动抛错）

### Git 收尾

```PowerShell
git status --short
git add backend/
git status --short           # 确认无 .env
git commit -m "feat: neo4j data import script + graph service extension (Sprint 3.9.2)"
git push origin feature/sprint-3
```

## 9\.3 替换 501 路由 \+ 文档更新

```Plain Text
进入 Sprint 3 阶段九 9.3：替换 501 路由 + 文档更新。

【本次目标】
1. 替换 backend/app/api/v1/routes/documents.py 里的 GET /documents/{id}/graph：
   - 从 501 → GraphService.fetch_document_subgraph()
   - 输出严格遵循 contracts/openapi.yaml 的 DocumentGraphResponse

2. 替换 backend/app/api/v1/routes/agent.py 里的 POST /agent/query：
   - 从 501 → AgentService.query()
   - 输出严格遵循 AgentQueryResponse

3. 更新 backend/CODEBUDDY.md：
   - 移除 SQLite 临时兜底声明
   - 改为说明当前数据存储：SQLite（PG 模拟）+ Neo4j（active KG 版本）

4. 补 backend/.env.example 中 Neo4j 变量的注释说明

【关键约束：Literal 类型别名禁止属性访问】
- contracts/openapi.yaml 里 route / confidence / refusal_reason 等字段是内联枚举，
  在 Python 里对应 Literal[...] 类型别名，不是 Enum 类
- Literal['a','b'].A 或 Literal['a','b'].B 会抛 AttributeError（因为 Literal 是类型别名对象）
- 必须【直接用字符串字面量】：
     route="m3_graphqa"          # 正确
     route=QueryRoute.M3_GRAPHQA # 错误，AttributeError
- 字面量取值以 contracts/openapi.yaml 的 enum 定义为准（全小写）
- 不要改成 StrEnum（会改变 Pydantic schema 渲染 → 契约漂移 → CI 挂）

【故障语义边界（重要）】
- 证据不足/超出范围 → 200 返回，refused=true + refusal_reason
- LLM 传输故障/未配置/调用失败 → 抛 AgentUnavailableError → 路由层转 501
- Neo4j 不可达 → 抛 GraphUnavailableError → 路由层转 501
- 不要把基础设施故障伪装成拒答（会导致测试结果随本机环境漂移）

【tenacity 用法】
- 只用 stop_after_attempt(N) + wait_exponential(multiplier=X, max=Y)
- 严禁 multiplier_getter
- 严禁 reraise=True 后去 except RetryError（改捕 Exception 或直接 reraise=False）

【测试隔离要求】
- 测试不得依赖外部 Neo4j
- conftest.py 里把 NEO4J_URI 指向不可达端口（如 bolt://127.0.0.1:1）
- 确保 pytest 全绿不随本机 Neo4j 状态漂移

【约束】
- 不改 contracts/openapi.yaml
- 不改 frontend/
- 所有命令用 uv run 前缀
- 完成后跑 uv run pytest，全绿才提交
- 报告：替换的端点、新增/修改文件、pytest 结果、与契约的对齐情况

【若发现契约缺口】
- 只上报，不改契约
- 例如 AgentQueryResponse 缺 kg_nodes / kg_relations / token_usage，
  按契约不添加，写一个 test 钉死这个边界，记入 Sprint 4 契约刷新清单
```

### 验收

```PowerShell
cd backend
uv run pytest -q                          # 期望：全绿
uv run ruff check .                       # 期望：All checks passed
uv run ruff format --check .              # 期望：files already formatted
uv run python scripts/export_openapi.py --check   # 期望：[OK] 契约零漂移
```

### 真实链路验证

（PowerShell 里必须用 `Invoke-RestMethod`）

终端 1：启动后端

```PowerShell
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

终端 2：发请求（PowerShell 原生方式，避免 curl 转义坑）

```PowerShell
$body = @{
    question = "智能制造有哪些财务指标？"
    scope = "cross_doc"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/agent/query" `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Org-Id"="00000000-0000-4000-8000-000000000001"} `
  -Body $body
```

期望：返回 200 状态 \+ 一段中文回答（可能因数据质量导致 `refused=true`，但 HTTP 应为 200）。

如果返回 500：让 CodeBuddy 用 Ask 模式读 `backend/app/services/agents.py` 全文件，重点检查：

- 是否还有 `Literal[...].XXX` 属性访问

- 是否还有 `except RetryError` 死代码

- 是否还有 `multiplier_getter` 参数

### Git 收尾

```PowerShell
git status --short
git add backend/
git status --short           # 确认无 .env
git commit -m "feat: replace 501 routes with graph + agent service (Sprint 3.9.3)"
git push origin feature/sprint-3
```

## 9\.4 阶段九收尾

### 验收清单（6 项全绿才收尾）

```PowerShell
# 1. 后端测试
cd backend
uv run pytest -q
# 期望：69+ passed

# 2. Ruff 检查
uv run ruff check .
uv run ruff format --check .
# 期望：All checks passed / files already formatted

# 3. 契约零漂移
uv run python scripts/export_openapi.py --check
# 期望：[OK] ... 与后端模型一致

# 4. 前端构建（PowerShell 里用 npm.cmd，不用 npm）
cd ../frontend
npm.cmd run build
# 期望：Compiled successfully

# 5. Neo4j 数据
# 浏览器打开 http://localhost:7474，运行：
# MATCH (n:Entity) RETURN count(n)
# 期望：23

# 6. 工作区干净
cd ..
git status --short
# 期望：无输出
```

### 收尾命令

```PowerShell
# 1. 切到 main 并拉取
git checkout main
git pull origin main

# 2. 合并 feature/sprint-3（保留合并历史）
git merge --no-ff feature/sprint-3 -m "merge: sprint 3 done (v0.3.0)"

# 3. 打附注 tag
git tag -a v0.3.0 -m "Sprint 3 done: full-stack + neo4j + agentic-rag"

# 4. 推送
git push origin main
git push --tags
```

### 最终确认

```PowerShell
git log --oneline -8
git tag
git ls-remote --tags origin
git status --short
```

期望：

- `git log` 顶部是 `merge: sprint 3 done (v0.3.0)`

- `git tag` 显示：`sprint-1-done`、`v0.1.0`、`v0.2.0`、`v0.3.0`

- 远程 tag 列表包含 `v0.3.0`

- `git status` 无输出

### CI 验证

打开 [https://github\.com/csheep86/GraphRAG\-Agent/actions](https://github.com/csheep86/GraphRAG-Agent/actions)，确认最新 run 4 个 job 全绿：

- 后端（ruff \+ pytest）

- 前端（lint \+ gen:api）

- 契约校验（前后端漂移门禁）

- 流水线汇总

---

## 附：全局决策速查表

# 五、Sprint 4：联调与发布

## 0：契约缺口刷新

### 0\.0 前置说明

背景：Sprint 3 执行过程中上报 8 条契约缺口，统一在 Sprint 4 阶段十\.0 偿还。阶段十\.0 是联调（阶段十）的前置批次，先把契约对齐、隐患修掉，再切真实 API。

原则：

- 契约真源永远是 `backend/app` 的 Pydantic 模型，通过 `scripts/export_openapi.py` 导出 `contracts/openapi.yaml`

- 生成物（`contracts/openapi.yaml` \+ `frontend/src/types/api.d.ts`）只能通过脚本重生成，禁止手改

- spec 文件（`specs/`）修改走架构师角色，只追加不修改现有行，先出 diff 待审

- 每批次独立 commit，主题单一，不混提交

批次划分：

---

### 0\.1 通用约束（每批次必贴）

```Plain Text
【环境】
- 项目：GraphRAG-Agent
- 本地路径：d:/AIProject/GraphRAG-Agent
- 当前分支：feature/sprint-4
- 基线 tag：v0.3.0
- 契约真源：backend/app 的 Pydantic 模型 → scripts/export_openapi.py → contracts/openapi.yaml
- 前端契约类型：frontend/src/types/api.d.ts（由 npm.cmd run gen:api 生成）

【生成物规则（关键）】
- contracts/openapi.yaml 和 frontend/src/types/api.d.ts 都是生成物
- 「不改 frontend/」的约束不适用于 api.d.ts——允许通过 gen:api 重生成
- 生成物禁止手改；重生成后必须与契约零漂移

【红线】
- Literal 类型别名禁止属性访问，直接用字符串字面量
- tenacity 只用 stop_after_attempt + wait_exponential(multiplier, max)
  严禁 multiplier_getter；严禁 reraise=True 后 except RetryError
- 测试不得依赖真实 Neo4j / LLM；conftest 里 NEO4J_URI 指向不可达端口
- 中文注释，关键步骤写清楚
- 遇到报错先停下来报告，不要自己乱改
- 不要顺便改用户没要求的东西
- 若执行 ruff format .，提交前 git status --short 核对文件清单
- push 失败直接重试，不要 reset / 不改 remote URL
- 先出 diff 待审，审过再提交

【验证链】
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
（如改 schema / 路由描述）uv run python scripts/export_openapi.py --check
cd ../frontend
（如改 schema / 路由描述）npm.cmd run gen:api
npm.cmd exec tsc -- --noEmit
npm.cmd exec eslint src -- --max-warnings=0
npm.cmd run build
```

### 0\.2 批次 A：契约字段扩展

目标：扩 `AgentQueryResponse` 加 `kg_nodes` / `kg_relations` / `token_usage`，后端填充，前端适配。

顺序：

1. 先反转反向守卫测试（不删断言，只改语义）：`test_agent_response_has_no_undocumented_fields` → `test_agent_response_has_documented_graph_fields`

2. 扩 schema：复用已有 `GraphNode` / `GraphEdge`，不要自创 `KgNode` / `KgRelation`

    - `kg_nodes: list[GraphNode] = []`

    - `kg_relations: list[GraphEdge] = []`

    - `token_usage: TokenUsage | None = None`（Optional 默认 None，拒答分支不调 LLM 拿不到 token）

3. 新增 `TokenUsage`：`prompt_tokens` / `completion_tokens` / `total_tokens`，`int` 默认 0

4. AgentService 填充：`_fetch_subgraph_for_question` 一次检索产出 Prompt 文本 \+ 结构化数据（用 `_SubgraphResult` dataclass 同源）；`token_usage` 双路径探测（LangChain `usage_metadata` / OpenAI 兼容 `response_metadata.token_usage`），拿不到就 `None`，禁止造假

5. 前端适配：`gen:api` → `qa.ts` 解降级 → P03 引用证据面板消费真实 `kg_nodes` / `kg_relations`；空数据展示「暂无引用证据」占位

6. Mock 层同步补三字段，双轨不破坏

验收：

- pytest passed（原 69 → 78）

- export \-\-check 零漂移

- tsc / eslint / build 全绿

批次拆分规则：若测试文件与上一批重叠，允许合并为同一 commit，不强行拆分。

---

### 0\.3 批次 B：枚举扩展

前置（重要）：先出分析清单，不直接改代码。

分析清单要求：

1. 读 sources：`specs/m2-*.md` / `bridge_web_demo/output.json` / `schemas/document.py` / `services/graphs.py` 投影逻辑

2. 输出「枚举对齐清单」：spec 声明 / 实际数据 / 契约当前值 / 映射现状

3. 列出「建议新增的枚举值」\+ 逐条依据（不得自创，必须来自 spec 或实际数据）

4. 列出「不建议加入」的类型 \+ 理由

5. 列出执行计划 \+ 风险清单

6. 等用户确认后再改代码

改代码时：

- Literal 只增不删，追加新值

- 删除对应投影降级规则（从「被投影为 MENTIONS」变直通）

- 未知类型仍兜底 MENTIONS \+ `properties.relation_name`

- 测试反转：原「投影为 X」的断言改为「直通为 X」

- spec 同步：只追加对应行，先出 diff 待审，不改现有行

验收：契约 enum 增 N 值 \+ description 微调；api\.d\.ts union 增 N 值；pytest 全绿。

---

### 0\.4 批次 C：描述刷新

目标：刷新过期 description / docstring，反映当前真实行为。

撰写规则：

- 已实装部分：写清 Service / 方法 / 返回类型

- 尚未接入部分：如实标注（如「执行体当前返回空结果」），指向后续版本待办

- 禁止只写「已实装」而不写局限，否则会再制造漂移

- 不要堆砌内部符号（如 `TaskManager` 类名），只描述行为

- 引用其他端点的节奏说明时不要复述（避免双处措辞不一致）

同族措辞处理：

- 先 grep 全仓，列出所有同族位置

- 逐条判断是否纳入本批

- 运行时错误体 message 单独处理：改前必须 grep 前端有无硬编码依赖该字符串；有依赖 → 先报告，不改

验收：契约 diff 只有 description 类字段变；api\.d\.ts 只有注释变，类型零变化；pytest 全绿。

---

### 0\.5 批次 D1：代码隐患修复

目标：缺口 5（子图构造异常兜底）\+ 缺口 6（`_refuse()` 复用）。

缺口 5 修复要点：

- `fetch_all_subgraph` / `fetch_document_subgraph` 的 Pydantic 构造包进 try

- 构造失败 → 抛 `GraphUnavailableError`（501），不静默降级为空结果

- 异常 message 必须带字段信息（如 `canonical_name: Input should be a valid string`）

- 抽出 `_project_nodes` / `_project_edges` 复用，避免双处重复

- 语义：fail\-fast（一条脏数据 → 整个查询 501），不伪装成空结果

缺口 6 修复要点：

- 拒答分支的 inline 构造改为调用 `self._refuse()`

- 行为不变：`kg_nodes=[]` / `kg_relations=[]` / `token_usage=None`

补测试：

- 构造失败抛 `GraphUnavailableError`（不是空结果）

- 反向守卫：合法 payload 仍正常投影

- `_refuse()` 被调用（spy 计数）

- 拒答返回结构符合契约

---

### 0\.6 待办登记模板

```Plain Text
【本批只做一件事：待办登记】
在 backend/CODEBUDDY.md §4 缺口表末尾追加 N 行：
| 编号：简短标题 | 现状描述 | 处置（版本） |

【约束】
- 只改 backend/CODEBUDDY.md 一个文件
- 只追加，不动其他任何内容
- 不新建 backlog 文件，不动 changes/ 目录
- 不跑 export / pytest（纯文档追加）
- 先出 diff 待审，先不提交
```

### 0\.7 批次完成的标准动作

每批次完成后固定执行：

```PowerShell
git status --short          # 核对改动文件
git add <精确路径>           # 不用 git add .
git status --short          # 再次确认无 .env / .venv / node_modules
git commit -m "<主题单一>"
git push                    # 失败直接重试，不 reset
git log --oneline -N
git --no-pager show --stat HEAD
```

commit message 规范：`<type>: <主题> (Sprint4.10.0.<批次>)`，type 用 `feat` / `fix` / `docs`。

### 通用陷阱速查表

### 全局决策速查表

### 交付总览

- 7 个 commit：A（含 A\-2a/A\-2b 合并逻辑）、B、C、C2、D1、close

- 契约零漂移：全程 `export_openapi.py --check` 通过

- 测试：69 → 87 passed（\+18 例）

- 前端：4 页面 \+ API 层 \+ Mock 双轨 \+ 引用证据面板接入真实数据

- 移出 Sprint 4 的项：D2（PG 真源）、S4\-4（registry docstring）、E1/E2（数据质量）→ 全部记入 v1\.1\.0

## 阶段十：联调（前端 Mock → 真实 API）

> 承接：阶段零（V3\.8）完成契约缺口刷新后，Sprint 4 进入阶段十（联调）。
> 阶段十的批次编号从 10\.1 开始（不是 10\.0，避免与阶段零混淆）。
> 阶段零 = 契约缺口刷新（V3\.8）；阶段十 = 联调（V3\.9）。
> 
> 

### 10\.0 阶段定位与原则

目标：验证契约内 4 个真实接口（upload / status / graph / agent\-query）在真实链路（FastAPI \+ Neo4j \+ DeepSeek）下与契约完全对齐。

核心原则：

1. 双轨不破坏：契约内接口走真实，契约外接口继续走 Mock（避免 UI 全红）

2. 每批独立验收：一批跑通再进下一批，不跳步

3. 观察优先于执行：probe 脚本由 CodeBuddy 写，用户手动执行，报错现场判断

4. 只改能改的：不碰 contracts、不跑 gen:api、不改业务代码（发现缺陷记 v1\.1\.0）

5. 工作产物不入库：`changes/` 目录全程未跟踪，阶段十三统一归档

批次划分：

> 历史 commit message 里保留原编号（`Sprint4.10.1.5` / `Sprint4.10.1.6`），与 git log 保持一致；笔记里用新编号 10\.1\.1 / 10\.1\.2。
> 
> 

---

### 10\.1 环境准备（前置）

必做检查（PowerShell）：

```PowerShell
# Neo4j 在跑
docker ps --filter "name=neo4j"

# 数据已导入（期望 23 Entity + 1 KgVersion）
docker exec -it neo4j cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n)"

# DeepSeek Key 有效（期望 200）
Invoke-RestMethod -Method Get -Uri "https://api.deepseek.com/v1/models" `
  -Headers @{ "Authorization" = "Bearer <key>" }

# 启动后端（保持窗口不关）
cd d:/AIProject/GraphRAG-Agent/backend
uv run uvicorn app.main:app --reload --port 8000

# 启动前端（保持窗口不关）
cd d:/AIProject/GraphRAG-Agent/frontend
npm.cmd run dev

# 探活（期望 200 + checks.database=up）
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

关键事实：

- `/health` 响应 `database` 字段在 `checks.database`（非顶层）

- `trace_id` 中间件：合法 UUID 透传，非法/缺失则生成

- `X-Trace-Id` 响应头 \+ body `trace_id` 必须一致

---

### 10\.1\.1 前端 dev 注入 X\-Org\-Id（原 10\.1\.5）

问题：前端 `client.ts` 完全不发 `X-Org-Id`，后端 dev header 双空时 `raise UNAUTHORIZED`（401）。切真实 API 后所有请求挂。

修复（只改 `frontend/src/api/client.ts` \+ `frontend/.env.development`）：

```TypeScript
// client.ts 顶部常量区
const DEV_DEFAULT_ORG_ID =
  process.env.NEXT_PUBLIC_DEV_DEFAULT_ORG_ID ||
  "00000000-0000-4000-8000-000000000001";

// request() headers 注入（关键：读 raw env 不用 fallback 后的 APP_ENV）
headers: {
  Accept: "application/json",
  ...(process.env.NEXT_PUBLIC_APP_ENV === "development"
    ? { "X-Org-Id": DEV_DEFAULT_ORG_ID }
    : {}),
  ...(isFormData ? {} : { "Content-Type": "application/json" }),
  ...init.headers,
},
```

```Bash
# .env.development 加一行
NEXT_PUBLIC_DEV_DEFAULT_ORG_ID=00000000-0000-4000-8000-000000000001
```

关键约束：

- 注入条件用 `process.env.NEXT_PUBLIC_APP_ENV === "development"`（raw env），不用 `APP_ENV` 常量（有 fallback 到 development，prod 忘设 env 会误注入）

- FormData 也注入 X\-Org\-Id（与 multipart boundary 无关）

- 只注入 X\-Org\-Id，不注入 X\-Actor\-Id（后端自动补 default）

---

### 10\.1\.2 接口级 Mock 开关（原 10\.1\.6）

问题：切 `USE_MOCK=false` 后，8 个契约外接口（listDocuments 等）会 404，UI 全红。

修复（`frontend/src/api/client.ts`）：

```TypeScript
/**
 * 契约内端点路径模式（唯一真源）。
 * 契约新增端点时必须同步这里；漏更新会让新端点走 mock 而非真实接口。
 */
const CONTRACT_COVERED_PATTERNS: RegExp[] = [
  /^\/api\/v1\/agent\/query$/,
  /^\/api\/v1\/documents\/upload$/,
  /^\/api\/v1\/documents\/[^/]+\/graph$/,
  /^\/api\/v1\/documents\/[^/]+\/status$/,
];

/**
 * 接口级 mock 判定：
 *  - USE_MOCK=true → 全 Mock
 *  - USE_MOCK=false → 仅契约内走真实；契约外仍 Mock
 */
export function shouldMock(path: string): boolean {
  if (USE_MOCK) return true;
  return !CONTRACT_COVERED_PATTERNS.some((re) => re.test(path));
}
```

调用方改动：所有 `if (USE_MOCK)` → `if (shouldMock("/api/v1/..."))`。

关键约束：

- 命名 `shouldMock` 不是 `useMock`：`use*` 前缀触发 `react-hooks/rules-of-hooks` 误报

- 路径正则精确锚定 `^$`，路径参数用 `[^/]+`

- `getDocumentStatus` / `getDocumentGraph` 之前无 Mock 分支（永远走真实），本批补齐 Mock 分支

- `getDefaultEntityId` 改为永远返回 `MOCK_DEFAULT_ENTITY_ID`（契约外 \+ 不发请求）

---

### 10\.2 upload \+ status 联调

探针脚本：`changes/Sprint4.10.2/probe.py`（Python \+ requests）。

6 个场景：

关键事实：

- `task_id == document_id`（同一 UUID）：upload 响应的 `task_id` 直接作为 `/{id}/status` 路径参数

- MIME 由 multipart part 的 Content\-Type header 决定，不从文件名推断

- 检查顺序：先 MIME 后大小：上传 100MB \.bin → 先触发 415，到不了 413；要测 413 用 `.pdf` 扩展名

- `.exe` 的 MIME 是 `application/x-msdownload`（不是 `application/octet-stream`）：断言放宽为「不在白名单内」

- 100MB 文件用 sparse file：`f.seek(100*1024*1024); f.write(b"\x01")`，物理占用≈0

执行命令：

```PowerShell
cd d:/AIProject/GraphRAG-Agent/backend
uv run python ../changes/Sprint4.10.2/probe.py 2>&1 | Tee-Object -FilePath ../changes/Sprint4.10.2/probe-output.log
```

### 10\.3 graph 联调

探针脚本：`changes/Sprint4.10.3/probe_graph.py`。

关键前置事实（决定 P1 预期）：

```PowerShell
MATCH (d:Document {id: $doc_id, kg_version: $kg_version})   -- 非 OPTIONAL
OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
...
```

因果链：

1. `MATCH (d:Document ...)` 非 OPTIONAL → 无 Document 节点 → 0 行

2. 服务层 `.single()` → `None`

3. 服务层 `if result is None: return [], [], False` → 空图

4. 路由层 → 200 \+ 空图（不是 404、不是 500）

反直觉但正确：PG 里有 document 记录 → 200 空图；Neo4j 有无 Document 节点不影响状态码（这是设计决定，非 bug）。

4 个场景：

不测：

- G1（200 \+ 有数据）：需 fixture，属 v1\.1\.0（MinerU \+ LangExtract 接入后）

- G4（501）：用户明示，避免搞挂 Neo4j

---

### 10\.4 agent\-query 联调

探针脚本：`changes/Sprint4.10.4/probe_agent.py`。

前置核实（重要）：

1. `fetch_all_subgraph` 的 Cypher（`_QUERY_ALL_ENTITY_SUBGRAPH`）：

    - fail\-open：`WHERE $org_id IS NULL OR properties(n)['org_id'] IS NULL OR properties(n)['org_id'] = $org_id`

    - 23 个 Entity 节点无 org\_id 属性键 → 命中第二分支 → 任何 org\_id 都拉到全部 23 Entity

    - 租户隔离缺口 → 归 v1\.1\.0（接入 MinerU 时同步改 fail\-closed）

2. 拒答条件：`citations` 为空 → `_refuse()` → `answer="无法回答"` \+ `refused=true` \+ `refusal_reason="no_grounded_evidence"` \+ `kg_nodes=[]` \+ `kg_relations=[]` \+ `token_usage=None`

3. `answer` 契约明说固定值：`openapi.yaml:84-86` \+ `_refuse()` 硬编码 \+ JSON 解析失败 fallback，三处一致

4 个场景：

关键陷阱：FastAPI 校验错误状态码是 400，不是 422

- 契约 `openapi.yaml:699-704` 写 400

- handler `exception_handlers.py:96` 硬编码 400

- ErrorCode `errors.py:36-37` 默认 400

- FastAPI 默认 422 被全局 `_handle_validation_error` 主动改写为 400

- 不要凭 FastAPI 默认猜 422——必须读契约

---

### 10\.5 通用约束（每批次必贴）

```Plain Text
【环境】
- 项目：GraphRAG-Agent
- 本地路径：d:/AIProject/GraphRAG-Agent
- 当前分支：feature/sprint-4
- 基线 tag：v0.3.0
- 契约真源：backend/app 的 Pydantic 模型 → scripts/export_openapi.py → contracts/openapi.yaml
- 前端契约类型：frontend/src/types/api.d.ts（gen:api 生成）

【红线】
- 不改 contracts/openapi.yaml 手写内容
- 不改 frontend/src/ 业务源码；允许 gen:api 重生成 api.d.ts
- 不改 backend/app/** 业务代码（除非本批明确要求）
- 不跑 gen:api（除非本批改契约）
- 不启动新服务（uvicorn / next dev 已在跑）
- 中文注释，关键步骤写清楚
- 遇到报错先停下来报告，不要自己乱改
- 不要顺便改用户没要求的东西

【probe 脚本约定】
- Python + requests（不用 PowerShell）
- 脚本顶部 docstring：环境前置 / 场景列表 / 不测项及理由
- 每场景独立 try/except，单场景失败不影响后续
- trace_id 命名空间：每批次一个前缀（如 10.2 用 ...000-006、10.3 用 77777、10.4 用 88888）
- 每个响应打印：URL + method + status + trace 三方对照 + body
- 结尾总汇总 + return code 0/1（便于 CI 集成）
- 临时文件用 tempfile.TemporaryDirectory()
- 执行命令：cd backend && uv run python ../changes/<批次>/probe.py

【用户手动执行】
- 不在 CodeBuddy 对话里跑脚本
- 先审脚本再跑
- 报错立即停下来报告，不自己乱改
- 跑完贴输出全文给 CodeBuddy 写 log
```

### 10\.6 阶段十陷阱速查表

---

### 10\.7 阶段十决策速查表

---

### 10\.8 阶段十交付总览

提交历史：

```Plain Text
d7b21ecb docs: register agent/query tenant isolation gap (Sprint4.10.4)
ea75ed7f feat: route only contract-covered endpoints to real backend (Sprint4.10.1.6)
854d546f feat: dev-only X-Org-Id default in api client (Sprint4.10.1.5)
```

工作产物（`changes/` 未跟踪）：

```Plain Text
changes/Sprint4.10.1/            环境准备 + health
changes/Sprint4.10.1.5/          dev 认证头（= 笔记 10.1.1）
changes/Sprint4.10.1.6/          接口级 Mock 开关（= 笔记 10.1.2）
changes/Sprint4.10.2/            upload + status（probe.py + log）
changes/Sprint4.10.3/            graph（probe_graph.py + log）
changes/Sprint4.10.4/            agent/query（probe_agent.py + log + evidence_neo4j.py）
```

验收结果：

关键产出：

- 前端双轨机制完整（契约内真实 / 契约外 Mock）

- dev 认证头注入（X\-Org\-Id）

- 4 个契约内接口全部真实链路验证

- v1\.1\.0 缺口登记 1 行（agent/query 缺 PG 前置租户隔离）

移出 Sprint 4 的项：

---

### 10\.9 批次编号规范

规则：

理由：

- `.5` / `.6` 看不出是「第几个补丁」，读者会困惑「10\.1\.3 / 10\.1\.4 去哪了」

- `.1` / `.2` 一眼看出是「10\.1 的第 1、2 个补丁」

commit message 例外：

- 已经打过的 commit message（如 `Sprint4.10.1.5`）保持原样，不 rewrite 历史

- 笔记里用规范编号（10\.1\.1 / 10\.1\.2），commit message 里保留历史编号

---

### 10\.10 跨阶段通用规则

1. probe 脚本语言：优先 Python

    - 涉及 multipart 上传、4xx/5xx 处理、跨平台编码时，Python 一次过；PowerShell 会连环撞坑

2. UUID 禁手抄

    - log 中引用 probe 输出的 UUID 必须复制粘贴，禁止手打

    - 典型陷阱：`5555` ↔ `4555` 段间同字符错位

3. 契约状态码以 openapi\.yaml 为准

    - 不要凭框架默认猜（FastAPI 默认 422，本服务改写成 400）

4. 可选场景必须「always PASS」

    - 可选场景抛异常不扣分，避免污染总汇总

5. runtime timeout 必须覆盖重试链路上限

    - `timeout ≥ 单次调用 timeout × 重试次数 + 退避总和`

6. 每个场景独立 try/except

    - 单场景失败不阻断后续，最后总汇总统一判 PASS/FAIL

## 阶段十一：测试分层

### 开工前检查

```PowerShell
cd d:/AIProject/GraphRAG-Agent
git status --short     # 期望无输出（工作区干净）
git log --oneline -3   # 顶部应是阶段十最后 commit
uv run pytest -q       # 期望 87 passed
```

### 11\.1 测试现状盘点

#### 步骤 11\.1\.A · 出方案（Plan 模式）

意图：让 AI 扫一遍现有测试，找出「已实装但完全无测试」的模块。只读，不写。

这一步容易踩的坑：

完整提示词（整段复制到 Plan 模式）：

```Plain Text
进入 Sprint 4 阶段十一·11.1：测试现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 分支：feature/sprint-4
- 基线 tag：v0.3.0（阶段零到十全部完成）
- 后端 pytest 87 passed
- 前端零测试（阶段十 10.1 探查已核实：无 .test.ts / 无 jest / vitest 配置）
- 阶段十一目标是「测试分层」，不是全覆盖
- Sprint 4 核心是 v1.0.0 收尾
- 阶段零决策：Playwright 装但最小化，CI 不依赖真实后端

【硬约束】
- 不落盘任何文件（不写 inventory-report.md，不建 changes/Sprint4.11.1/）
- 只在对话里输出分析
- 不改任何文件

【本步目标】
1. 后端测试现状盘点：
   - 用 pytest --collect-only -q 实测每个测试文件的测试数
   - 按模块分类：schemas / services / api routes / tasks / 契约 export / conftest
   - 每个文件的覆盖类型（单测 / 集成 / 契约 / 回归探针）+ 隔离情况
   - 列出「已实装但无测试」的模块 / 端点
   - services 方法级覆盖清单（哪些有测试、哪些无）

2. 后端测试缺口分析：
   - 哪些「已实装但测试薄」？
   - 哪些是高风险路径（涉及 LLM / Neo4j / 契约）？
   - 按优先级分：高（影响 v1.0.0 可交付性）/ 中 / 低

3. 前端测试现状：
   - 引用阶段十结论，不重复核实
   - 列出可测试单元（纯函数 / api 映射 / store actions / 组件）
   - 评估引入 vitest + testing-library 成本
   - 是否建议引入？给理由

4. E2E 现状：
   - 确认无 E2E
   - 如果装 Playwright，建议哪 3 条冒烟路径
   - 是否依赖真实后端

5. 出「阶段十一建议范围」：
   - 11.2 补哪几个测试文件（列出测试名 + 断言要点）
   - 11.3 前端组件测试：做 / 跳过 / 最小化 + 理由
   - 11.4 E2E：装 / 跳过
   - 哪些放 v1.1.0

6. 出「阶段十一预估工时」（含是否在 Sprint 4 预算内）

【约束】
- 只读
- 不跑新测试命令（允许 pytest --collect-only）
- 不装任何依赖
- 不改 contracts / frontend / backend 代码
- 不跑 gen:api
- 中文回答
- 路径统一用 d:/AIProject/GraphRAG-Agent

【完成后输出 1-6 项分析报告】
```

#### 步骤 11\.1\.B · 裁决（普通对话）

意图：AI 出了报告，你按「Sprint 4 是收尾」的原则收紧范围。

这一步容易踩的坑：

完整提示词：

```Plain Text
11.1 盘点审核通过。5 个裁决：

【1. 11.2 后端范围】
只做 🔴 高优先级（tasks + auth 层，2~3 个文件 ≈ 2.5h）。
🟡 中优先级（services 辅助函数）放 v1.1.0。
理由：
- tasks / auth 完全未测，被 ADR-0001 §3.2 / M1 §3 验收 8 显式要求
- 14 个辅助函数已通过集成测试间接覆盖
- 2.5h 合理，4.5h 超预算

【2. 11.3 前端测试】
跳过，放 v1.1.0。
理由：零测试基建 + TS 编译期已覆盖契约语义 + UI 已联调通过 + 完整方案 5~7h 超预算

【3. 11.4 E2E】
跳过，放 v1.1.0。
理由：USE_MOCK=true 默认不依赖后端 + 3 条冒烟只能测渲染不爆错 + 1.5~2h 性价比低

【4. Sprint 4 预算】
阶段十一 ≤ 2.5h + 阶段十二 + 阶段十三 ≤ 1.5h = 总 ≤ 4h

【5. v1.0.0 限制声明】
做，但在阶段十三统一写 docs/release-notes/v1.0.0.md（本批不做）

【关于 plan todos 冲突】
本轮不落盘 inventory-report.md。
如需留痕，可落到 changes/Sprint4.11.1/（未跟踪，不提交），但非必需。

【下一步：11.2 第一批】
先做 test_task_recovery.py。
按 TDD 顺序：先读 backend/app/tasks/manager.py 全文 + 现有 conftest，再写测试。
不写业务代码（如发现 bug 先报告，不改）。
```

### 11\.2 每批通用流程（4 步）

每个测试文件都走这 4 步。下面先给通用模板，再给 3 批的实际填充。

#### 通用流程总览

```Plain Text
Step A：Plan 模式 → 探查 + 出方案
       ↓ 审方案（贴给人工审）
Step B：普通对话 → 核实 N 处证据
       ↓ 审证据（贴给人工审）
Step C：Craft 模式 → 落盘测试文件
       ↓ 审脚本全文（PowerShell Get-Content 打印，贴人工审）
Step D：PowerShell → 手动跑 → 手动 commit + push
       ↓ 进下一批 Step A
```

#### 通用避坑提示（每批都适用）

---

### 11\.2 第一批：test\_task\_recovery\.py

#### 步骤 11\.2\.A · 探查 \+ 出方案（Plan 模式）

意图：让 AI 先读源码，说明它打算测什么、怎么测。你先审方案，别让它直接写。

这一步容易踩的坑：

- AI 忘了「全表扫描函数」的特性——`recover_orphan_tasks` 是全表扫描，测试不能写死 reclaimed 数

- AI 没意识到要用 seed \+ DELETE 收尾

完整提示词：

```Plain Text
进入 11.2 第一批：test_task_recovery.py。

目标：覆盖 recover_orphan_tasks + list_in_flight_task_ids
（ADR-0001 §3.2 / M1 §3 验收 8 显式要求）。

先做只读探查 + 出方案，不写测试代码：

1. 读 backend/app/tasks/manager.py 全文：
   - recover_orphan_tasks 函数（行为 / 状态推进 / 错误码落库）
   - list_in_flight_task_ids 函数（状态过滤逻辑）
   - TaskManager.submit / get_status 的接口
2. 读 backend/app/tasks/types.py：
   - TaskSpec / TaskStatus / TaskType / RecoveryReport 定义
3. 读 backend/tests/conftest.py：
   - 现有 client / dev_headers / cross_tenant_headers 夹具
   - 是否复用
4. 读 backend/tests/test_documents.py：
   - 现有「造 documents 记录」的范式

【出测试方案】
- 拟 9 个 test case（列出名字 + 断言要点）：
  1-2. pending / processing → failed（两种在途态都回收）
  3. error_code = TASK_INTERRUPTED + error_detail 非空
  4. completed 不回退
  5. failed 原错误码不被覆盖
  6. reclaimed 数 == 调用前在途集合长度（不写死常数）
  7. 二次调用 reclaimed == 0（幂等）
  8. list_in_flight_task_ids 只含 pending/processing
  9. 回收后无在途
- 隔离策略：
  - seed_document 夹具（seed + DELETE 收尾）
  - 全表扫描函数必须用「调用前集合为基准」，不写死常数
  - _ensure_schema 是否 module autouse

【出风险与坑位】
- 全表扫描与其它用例遗留数据的冲突
- 跨测试污染的避免

【约束】
- 只读，不改代码
- 先出方案，不写测试
- 复用阶段十的隔离风格
```

审核点：

- 9 个 case 是否覆盖完整

- 必须：case 6 用 `len(before)` 而非 `== 2` 这种写死常数

- seed 夹具 function 级 \+ DELETE 收尾

#### 步骤 11\.2\.B · 核实证据（普通对话）

意图：方案里有些假设（如「夹具怎么用」），先核实再落盘。

完整提示词：

```Plain Text
方案审核通过。落盘前先核实 3 件事（贴证据）：

【核实 1：seed_document 夹具用法】
读 backend/tests/conftest.py + test_documents.py：
- 有没有现成的 seed_document 夹具？
- 它是 session 级还是 function 级？
- 它怎么拿 SessionLocal？
- 收尾是 DELETE 还是 rollback？
贴出夹具实际代码。

【核实 2：_ensure_schema module autouse 的写法】
读现有测试文件：
- 是否有 module 级 autouse 的 init_db()？
- 或依赖 client 夹具触发生命周期？
贴出现有范式。

【核实 3：recover_orphan_tasks 全表扫描的边界】
读 manager.py：
- 是全表扫描所有 documents？
- 还是只扫当前 session 可见的？
- 与其它测试的 documents 记录会冲突吗？
贴出函数关键行。

【3 处核实完，贴证据 + 确认后，写测试文件】
```

审核点：

- 证据是源码原文，不是 AI 复述

- 明确「全表扫描」→ 测试用相对基准

#### 步骤 11\.2\.C · 落盘（Craft 模式）

完整提示词：

```Plain Text
3 处核实通过。落盘 backend/tests/test_task_recovery.py。

【9 个 test case（最终）】
1. test_recover_orphan_tasks_marks_pending_as_failed
2. test_recover_orphan_tasks_marks_processing_as_failed
3. test_recover_orphan_tasks_records_task_interrupted_error_code
4. test_recover_orphan_tasks_keeps_completed_as_is
5. test_recover_orphan_tasks_keeps_failed_as_is
6. test_recover_orphan_tasks_reclaims_exactly_in_flight_rows
7. test_recover_orphan_tasks_is_idempotent
8. test_list_in_flight_task_ids_returns_only_pending_and_processing
9. test_list_in_flight_task_ids_is_empty_after_recover

【关键设计约束】
- case 6 断言用 len(before) 而非写死常数
- seed_document 夹具 function 级 + DELETE 收尾
- _ensure_schema module autouse → init_db()
- 不跨文件 import 其他测试的夹具
- 顶部 docstring 说明隔离策略 + 不依赖真实 Neo4j / LLM

【约束】
- 只写 backend/tests/test_task_recovery.py，不触业务代码
- 如发现真实缺陷，先报告不改

【完成后】
贴出 test_task_recovery.py 全文给我审（不执行）。
```

用户动作（AI 只贴摘要时）：

```PowerShell
Get-Content d:/AIProject/GraphRAG-Agent/backend/tests/test_task_recovery.py
```

把打印的全文贴给人工审。

审核点：

- case 6 是否用 `len(before)` 而非写死

- seed 夹具是否正确

- import 段路径是否正确

#### 步骤 11\.2\.D · 跑 \+ 提交（PowerShell）

```PowerShell
# D.1 单跑
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest tests/test_task_recovery.py -v
# 期望：9 passed

# D.2 全量回归
uv run pytest -q
# 期望：96 passed（87 + 9）

# D.3 提交
cd d:/AIProject/GraphRAG-Agent
git status --short     # 确认只有新测试文件 + changes/ 未跟踪
git add backend/tests/test_task_recovery.py
git status --short
git commit -m "test: cover recover_orphan_tasks and list_in_flight_task_ids (Sprint4.11.2)"
git push
git status --short
git log --oneline -3
```

注意：`git add` 前先 `git status --short` 确认无 `.env` / `.venv` / `node_modules`。push 失败直接重试，不 reset。

---

### 11\.2 第二批：test\_document\_parse\_executor\.py

#### 步骤 11\.2\.A · 探查 \+ 出方案（Plan 模式）

完整提示词：

```Markdown
进入 11.2 第二批：test_document_parse_executor.py。

目标：document_parse_executor 的完整生命周期 + tenacity 重试 + 失败落库。

先做只读探查 + 出方案，不写测试代码：

1. 读 backend/app/tasks/registry.py 全文：
   - document_parse_executor 函数
   - _do_parse 函数
   - tenacity 配置（stop_after_attempt + wait_exponential 参数）
   - 状态推进逻辑（pending → processing → completed / failed）
   - error_code / error_detail 落库方式
2. 读 backend/app/tasks/types.py
3. 读现有 conftest
4. 读现有 test_documents.py（BackgroundTasks 时序）

【出测试方案】
6 个 test case：
1. pending → processing → completed
2. 已 completed 早 return（spy 证伪 _do_parse 未被调用）
3. tenacity 2 失败 + 1 成功 → completed
4. tenacity 用尽 → failed + call_count = max_attempts
5. error_code = INTERNAL_ERROR + error_detail 含异常摘要
6. 缺失 document → 无异常 + 无 DB 副作用

【隔离策略（关键）】
- 直调 asyncio.run(executor(spec))，不走 TestClient / BackgroundTasks
- monkeypatch _do_parse：路径先核实（下一轮 Step B）
- 零等待：monkeypatch.setattr(get_settings(), "task_retry_initial_seconds", 0.0)
- fake 必须 async def
- seed_document 夹具 + DELETE 收尾

【出风险与坑位】
- monkeypatch 路径是否正确（先核实调用行）
- B3 约束：本模块不调用 recover_orphan_tasks
- B1 约束：不断言 Document.retry_count 的值

【约束】
- 只读，不改代码
- 先出方案，不写测试
- 复用 11.2 第一批的隔离风格
```

#### 步骤 11\.2\.B · 核实证据（普通对话）

这一步是全阶段最容易踩坑的地方——monkeypatch 路径错了，测试会假装 PASS（跑的是真实 `_do_parse`），根本测不到重试逻辑。

完整提示词：

```Markdown
方案审核通过。落盘前先核实 3 件事（贴证据）：

【核实 1：_do_parse 的 monkeypatch 路径（关键）】
读 backend/app/tasks/registry.py 里 document_parse_executor 函数内部：
- _do_parse 是怎么被调用的？
  - 裸名调用 `await _do_parse(...)` → monkeypatch 路径 = app.tasks.registry._do_parse
  - `from .registry import _do_parse` → 路径要改
  - 本地变量 → 路径要改
- 贴出调用行原文

【核实 2：settings 字段名】
读 backend/app/core/config.py：
- task_retry_max_attempts 字段名 + 默认值
- task_retry_initial_seconds 字段名 + 默认值
- tenacity 的 wait_exponential 用的哪个字段作 multiplier
- 贴出定义

【核实 3：SessionLocal 用法】
读 backend/tests/conftest.py + test_task_recovery.py：
- 有没有现成 session 夹具？
- 还是测试要自己 from app.db.session import SessionLocal？
- 11.2 第一批的 seed_document 是怎么拿 session 的？
- 贴出关键代码

【3 处核实完，贴证据 + 确认 monkeypatch 路径后，写测试文件】
【约束】
- 只读核实，先不写测试
- 测试文件顶部加注释说明 B3 约束（不与 recover_orphan_tasks 混用）
```

审核点：

- 核实 1 必须贴调用行原文，不是复述

- 如果 AI 说「路径没问题」，追问「贴出调用行原文」

#### 步骤 11\.2\.C · 落盘（Craft 模式）

完整提示词：

```Markdown
3 处核实通过。落盘 backend/tests/test_document_parse_executor.py。

【6 个 test case（最终）】
1. test_executor_pushes_pending_to_completed
2. test_executor_skips_already_completed
3. test_executor_retries_io_then_succeeds
4. test_executor_retries_exhausted_marks_failed
5. test_executor_failed_state_records_error_code_and_detail
6. test_executor_handles_missing_document_gracefully

【关键设计约束】
- 直调 asyncio.run(document_parse_executor(spec))
- monkeypatch.setattr("app.tasks.registry._do_parse", fake_async)
- fake 必须 async def
- 零等待：monkeypatch.setattr(get_settings(), "task_retry_initial_seconds", 0.0)
- seed_document 夹具 function 级 + DELETE 收尾
- _ensure_schema module autouse
- 顶部 docstring：
  - 说明 B3 约束（不与 recover_orphan_tasks 混用）
  - 说明 B1 约束（不断言 retry_count）
  - 说明不依赖真实 Neo4j / LLM

【约束】
- 只写 backend/tests/test_document_parse_executor.py，不触业务代码
- 如发现真实缺陷，先报告不改

【完成后】
贴出全文给我审（不执行）。
```

用户动作：

```PowerShell
Get-Content d:/AIProject/GraphRAG-Agent/backend/tests/test_document_parse_executor.py
```

审核点：

- monkeypatch 路径与 Step B 核实的一致

- fake 是 `async def`

- 零等待注入在 `production_env` 类似的 fixture 里（自动恢复）

#### 步骤 11\.2\.D · 跑 \+ 提交

```PowerShell
# D.1 单跑（注意看耗时——若零等待生效，应 < 1s）
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest tests/test_document_parse_executor.py -v
# 期望：6 passed in ~0.3s

# D.2 全量
uv run pytest -q
# 期望：102 passed（96 + 6）

# D.3 提交
cd d:/AIProject/GraphRAG-Agent
git status --short
git add backend/tests/test_document_parse_executor.py
git status --short
git commit -m "test: cover document_parse_executor state machine and retry (Sprint4.11.2)"
git push
git status --short
git log --oneline -3
```

本批特有：如果 AI 报告 B1 / B4 缺陷（`retry_count` 从不更新 / `task_retry_multiplier` 从不消费）→ 本批不修，记下等收尾统一登记。

---

### 11\.2 第三批：test\_auth\.py

#### 步骤 11\.2\.A · 探查 \+ 出方案（Plan 模式）

完整提示词：

```Markdown
进入 11.2 第三批：test_auth.py。

目标：auth 核心函数覆盖（parse_bearer_token / identity_from_dev_headers / get_current_identity）。

先做只读探查 + 出方案，不写测试代码：

1. 读 backend/app/core/auth.py 全文：
   - Identity 类（字段 / frozen？）
   - parse_bearer_token 函数（格式 / 异常 / 返回）
   - identity_from_dev_headers 函数（开/关分支 + 优先级）
   - 生产环境禁用 dev header 的逻辑
2. 读 backend/app/api/deps.py：
   - get_current_identity 依赖注入
   - Authorization 和 X-Org-Id 的优先级
3. 读 backend/tests/conftest.py：
   - 现有 dev_headers / cross_tenant_headers 夹具
4. 读 backend/tests/test_error_contract.py：
   - 现有 401 测试覆盖方式（避免重复）

【出测试方案】
6 个 case：
1. parse_bearer_token dev format → Identity
2. parse_bearer_token 非法格式（参数化 3 子类）
3. parse_bearer_token 生产环境拒 dev token
4. identity_from_dev_headers 生产环境 → None
5. identity_from_dev_headers 开发环境 → Identity
6. get_current_identity Bearer 优先

【隔离策略】
- 直调函数 + asyncio.run(get_current_identity(...))
- HTTPAuthorizationCredentials 手动构造
- production_env fixture：monkeypatch.setattr(get_settings(), "app_env", "production")
- monkeypatch 自动恢复

【出风险与坑位】
- production_env fixture 安全性（is_production 是 @property）
- 与现有 401 测试是否重复

【约束】
- 只读，不改代码
- 先出方案，不写测试
- 如发现 auth 逻辑有真实缺陷，先报告不改
```

#### 步骤 11\.2\.B · 核实证据

完整提示词：

```Markdown
方案审核通过。落盘前核实 3 件事（贴证据）：

【核实 1：parse_bearer_token 的异常 message】
读 backend/app/core/auth.py：
- 各异常分支的 message 原文（用于断言）
- dev 前缀 + 生产环境 → 抛什么 message
- dev 前缀 + 段数错 → 抛什么
- dev 前缀 + UUID 非法 → 抛什么
- 非 dev 前缀 → 抛什么
贴出原文。

【核实 2：identity_from_dev_headers 的 4 子路径】
读 auth.py：
- dev_org_header_enabled=False → 返回？
- 两个 header 都 None → 返回？
- 任一 header UUID 非法 → 抛什么？
- 只有 X-Org-Id / 只有 X-Actor-Id / 两个都有 → 返回？
贴出函数关键行。

【核实 3：conftest 的默认环境】
读 backend/tests/conftest.py：
- 模块顶部是否强制设置 APP_ENV / ALLOW_DEV_ORG_HEADER？
- 默认 test 环境下 dev_org_header_enabled 是 True 还是 False？
贴出原文。

【3 处核实完，贴证据 + 确认后，写测试文件】
```

#### 步骤 11\.2\.C · 落盘（Craft 模式）

完整提示词：

```Python
3 处核实通过。落盘 backend/tests/test_auth.py。

【6 个 case（含 1 个参数化 3 子类）】
1. test_parse_bearer_token_dev_format_returns_identity
2. test_parse_bearer_token_invalid_format_raises_unauthorized（3 子类参数化）
3. test_parse_bearer_token_dev_format_in_production_rejected
4. test_identity_from_dev_headers_returns_none_in_production
5. test_identity_from_dev_headers_returns_identity_when_enabled
6. test_get_current_identity_prefers_bearer_over_dev_headers

【关键设计约束】
- production_env fixture：monkeypatch.setattr(get_settings(), "app_env", "production")
  - 单行实现，无 try/finally（pytest monkeypatch 自动恢复）
- case 6 直调 asyncio.run(get_current_identity(credentials=..., x_org_id=..., x_actor_id=...))
- HTTPAuthorizationCredentials(scheme="Bearer", credentials=token) 手动构造
- 顶部 docstring 说明：parse_bearer_token 优先检查 is_production，再检查格式
  （防止生产环境泄露 token 格式），该优先级由 case 3 锁定

【约束】
- 只写 backend/tests/test_auth.py，不触业务代码
- 与现有 test_error_contract.py::test_missing_authentication_returns_401 不重复

【完成后】
贴出全文给我审（不执行）。
```

用户动作：

```PowerShell
Get-Content d:/AIProject/GraphRAG-Agent/backend/tests/test_auth.py
```

审核点：

- `production_env` fixture 单行，无 try/finally

- case 2 参数化的 3 个 message 与源码逐字一致

- case 6 的 Bearer 与 dev\_headers 用不同 UUID（否则区分不出优先级）

#### 步骤 11\.2\.D · 跑 \+ 提交

```Bash
# D.1 单跑
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest tests/test_auth.py -v
# 期望：8 passed（参数化展开）

# D.2 全量
uv run pytest -q
# 期望：110 passed（102 + 8）

# D.3 提交
cd d:/AIProject/GraphRAG-Agent
git status --short
git add backend/tests/test_auth.py
git status --short
git commit -m "test: cover auth token parsing and identity priority (Sprint4.11.2)"
git push
git status --short
git log --oneline -4
```

### 11\.2 收尾：登记 v1\.1\.0 缺陷

#### 步骤 11\.2\.E · 出 diff（Craft 模式）

意图：把 11\.2 第二批发现的疑似缺陷登记到 `backend/CODEBUDDY.md §4`。

这一步容易踩的坑：

完整提示词：

```Markdown
11.2 三批全部完成，+23 tests，87 → 110。

【统一登记 v1.1.0 缺陷到 backend/CODEBUDDY.md §4 缺口表末尾】
追加 2 行：

| B1：Document.retry_count 列存在但 executor 从不更新 | 列已声明（Schema 有），executor 从不写；要么漏写、要么该删列。11.2 第二批测试不锁定该值 | v1.1.0 疑似缺陷 |
| B4：Settings.task_retry_multiplier 在**任务退避路径**未被读取 | 字段定义 default=2.0, gt=1；`app/services/agents.py` 以 `exp_base` 读它（Agent 退避生效），但 `app/tasks/registry.py` / `scripts/import_to_neo4j.py` 只用 `task_retry_initial_seconds` 作 multiplier——**任务重试改该配置无效果**。措辞修正：不是"从未被消费"，而是"读它的地方不全"；因此 `check_seams.py` 的配置消费者判据**拦不到它**，必须靠 S5 批次 A 的验收项落实 | v1.1.0 疑似缺陷（配置项与代码脱节） |

【以下不登记】
- B5（生产环境拒 dev token 优先于格式检查）：不是缺陷，是设计意图未文档化；第三批测试已锁定优先级语义
- B2（_RETRYABLE_EXCEPTIONS 未含 httpx.TimeoutException）：当前设计正确
- B3（recover 与 executor 竞态）：测试隔离约束，非缺陷

【约束】
- 只改 backend/CODEBUDDY.md 一个文件
- 只追加 2 行到 §4 缺口表末尾
- 不改其他内容
- 先出 diff，不提交

【完成后】
- 贴出 §4 追加的 2 行 diff
- 顺带报告：11.2 是否还有未完成项（预期：无）
```

#### 步骤 11\.2\.F · 提交

```SQL
cd d:/AIProject/GraphRAG-Agent
git status --short     # 确认只有 CODEBUDDY.md 变化
git add backend/CODEBUDDY.md
git status --short
git commit -m "docs: register B1/B4 task retry config defects (Sprint4.11.2)"
git push
git status --short
git log --oneline -3
```

### 附：常见 AI 反问 \& 应答

---

### 附：全阶段重走检查清单

开工前：

- `git status --short` 无输出

- `uv run pytest -q` 显示 87 passed

- 已读 V3\.7 文档（含 V3\.9 阶段十增补）

11\.1：

- Plan 模式 → 贴 11\.1\.A 提示词

- 审报告 → 贴 11\.1\.B 裁决

11\.2 第一批：

- Step A 探查

- Step B 核实（seed 夹具）

- Step C 落盘 → PowerShell 打印全文 → 审

- Step D 跑（9 passed）→ 提交（`bf21dbe3`）

11\.2 第二批：

- Step A 探查

- Step B 核实（monkeypatch 路径必须贴调用行原文）

- Step C 落盘 → 打印全文 → 审

- Step D 跑（6 passed，\< 1s）→ 提交（`0026278e`）

- 记录 B1 / B4 疑似缺陷

11\.2 第三批：

- Step A 探查

- Step B 核实（3 个 message 原文）

- Step C 落盘 → 打印全文 → 审

- Step D 跑（8 passed）→ 提交（`76f38def`）

收尾：

- Step E 登记 B1/B4 → 审 diff

- Step F 提交（`2b997718`）

- 全量回归 `uv run pytest -q` 显示 110 passed

---

### 使用说明

1. 按操作顺序组织：先 11\.0 开局 → 11\.1 盘点 → 11\.2 三批 → 收尾

2. 每步包含：意图 / 避坑提示 / 完整提示词 / 审核点

3. 提示词可直接复制：不需要填空，除 11\.1\.B 里 `<列具体项>` 一处

4. 下次重走时，按检查清单逐项打勾

## 阶段十二（CI/CD 扩展 \+ pre\-commit）

### 第一部分 · 结论与速查

#### 12\.0 阶段定位与原则

目标：补齐 CI 中缺失的关键检查 \+ 修正规范文档漂移。

核心原则：

1. 克制优先：只在 CI 已覆盖的检查之外补真实缺口

2. 不重复建设：CI 已有的检查不重复加

3. 先本地验证再上 CI：本地能跑通的，CI 才可靠

4. 临时 PR 验证：改 CI 后必须开临时 PR 验证（CI 只在 push main \+ PR 时触发）

5. 规范文档同步：规范与现状不一致时一并修正

批次划分：

---

#### 12\.1 CI/CD 现状盘点（结论）

现有 CI（`.github/workflows/ci.yml`）4 个 job：

关键结论：

- ✅ contract job 已含 api\.d\.ts 零漂移门禁——预判要补的已存在，不用做

- ✅ 依赖锁定通过 `--frozen` / `npm ci` 隐式覆盖，不需独立 job

- ❌ 唯一真实缺口：前端 tsc 类型检查

- ⚠️ pre\-commit 完全缺失，但 CI 已兜底，ROI 低

- ⚠️ CODEBUDDY\.md 规范写「提交前必须通过 pre\-commit hook」，从未落地——文档漂移

- ⚠️ CI 触发范围：只 push main \+ PR，feature 分支直接 push 不跑

决策落点：

- 12\.2 只加 frontend tsc step（唯一真实缺口）

- pre\-commit 放 v1\.1\.0

- 前端 build 冒烟放 v1\.1\.0

- CI 触发范围保持现状

---

#### 12\.2 CI 改动（已提交）

改动 3 个文件：

关键设计：

**坑：****`next-env.d.ts`**** 被 gitignore**

- `frontend/tsconfig.json` 的 `include` 含 `next-env.d.ts`

- `frontend/.gitignore` 第 48 行：`next-env.d.ts` 被忽略（CI 检出后不存在）

- `layout.tsx` 有 `import "./globals.css"`

- CI 全新检出直接跑 `tsc --noEmit` 会报 `Cannot find module './globals.css'`

- 修法：CI 里先跑 `npm exec next typegen` 生成 `next-env.d.ts` \+ `.next/types`，再跑 tsc

**ci\.yml 改动**

```Diff
-#   2. frontend : ESLint + `npm run gen:api` 可执行性冒烟
+#   2. frontend : ESLint + TypeScript 类型检查 + `npm run gen:api` 可执行性冒烟
```

```Diff
- name: ESLint
         run: npm run lint
 
+      - name: 生成 Next 类型声明（next-env.d.ts 被 gitignore，CI 检出后需先生成）
+        run: npm exec next typegen
+
+      - name: TypeScript 类型检查
+        run: npm run typecheck
+
       - name: 生成 API 类型（可执行性冒烟）
         run: npm run gen:api
```

**package\.json 改动**

```Diff
"lint": "eslint",
+    "typecheck": "tsc --noEmit",
     "gen:api": "openapi-typescript ../contracts/openapi.yaml -o src/types/api.d.ts"
```

**CODEBUDDY\.md 规范修正**

改前：

```Plain Text
2. 提交前必须通过 pre-commit hook。
```

改后：

```Plain Text
2. 提交前必须通过本地检查（后端 ruff check/format、前端 eslint/typecheck）；
   推送后以 CI 全量门禁（ruff/pytest/eslint/tsc/契约零漂移）为最终裁决。
   pre-commit hook 暂未启用，规划于 v1.1.0。
```

注意：CODEBUDDY\.md 有三个（仓库根 / backend / frontend），但「pre\-commit hook」规范只在仓库根，只改那一个。

#### 12\.2 fix：修阶段十一遗留的 ruff 格式问题

触发：临时 PR 的 backend job 报 ruff I001。

根因：阶段十一 11\.2 三批落改时，验证链只跑了 pytest，漏了 ruff check \+ ruff format \-\-check。

修复：

```PowerShell
cd backend
uv run ruff check . --fix      # 修 import 顺序
uv run ruff format .           # 修文件末尾换行
uv run pytest -q               # 110 passed 不变
```

涉及文件：

- `backend/tests/test_auth.py`（import 顺序 \+ 末尾换行）

- `backend/tests/test_document_parse_executor.py`（末尾换行）

---

#### 12\.3 临时 PR 验证规则（新增）

背景：CI 只在 `push main + PR` 时触发，直接 push feature 分支不跑 CI。

规则：

1. 改 CI / 契约 / 生成物的批次，commit \+ push 后必须开临时 PR验证 CI

2. 步骤：

    - 访问 `https://github.com/csheep86/GraphRAG-Agent/compare/main...feature/sprint-4`

    - 点「Create pull request」，标题 `[临时] 验证 <批次> CI 改动`

    - 等 CI 跑完（2\~3 分钟）

    - 4 job 全绿 → 点「Close pull request」关闭（不合并）

    - 有红 → 排查

3. 不要点「Merge pull request」——阶段十三才正式合并

为什么：

- 提前发现 → 5 分钟修；等阶段十三合并 main 才发现 → 返工成本高

- 本次验证发现阶段十一遗留的 ruff 问题，正是这个规则的价值

---

#### 12\.4 陷阱速查表（阶段十二新增）

---

#### 12\.5 决策速查表（阶段十二新增）

---

#### 12\.6 交付总览

提交历史：

```Plain Text
b9490ff1 style: fix ruff import order and formatting in Sprint4.11.2 tests
3b98d609 ci: add frontend typecheck step and fix pre-commit doc drift (Sprint4.12.2)
```

改动文件：

```Plain Text
.github/workflows/ci.yml                        +2 step + 失败摘要 1 行 + 头注释
frontend/package.json                           +1 script（typecheck）
CODEBUDDY.md（仓库根）                           L66 一行替换
backend/tests/test_auth.py                      import 顺序 + 末尾换行
backend/tests/test_document_parse_executor.py   末尾换行
```

CI 验证结果：

- 临时 PR \#1：4 job 全绿（backend / frontend / contract / ci\-summary）

- PR 已关闭（不合并）

净结果：

- CI 补前端 tsc 类型检查（唯一真实缺口）

- CODEBUDDY\.md 规范与 CI 现状对齐

- 阶段十一遗留的 ruff 问题修复

跳过项（放 v1\.1\.0）：

---

#### 12\.7 跨阶段通用规则（阶段十二新增）

1. 每批落改的验证链

    - 必含：`pytest` \+ `ruff check .` \+ `ruff format --check .`（后端）；`tsc --noEmit` \+ `eslint` \+ `build`（前端）

    - 不得只跑 pytest——阶段十一的教训

2. 改 CI / 契约 / 生成物 → 开临时 PR 验证

    - CI 只在 push main \+ PR 时触发

    - 临时 PR 验证通过后关闭，不合并

3. gitignore 的坑

    - `next-env.d.ts` 被忽略 → CI 需先 `next typegen` 生成

    - 提交前 `git status --short` 核对：不该出现 `.env` / `.venv` / `node_modules`

4. 规范文档与现状同步

    - CODEBUDDY\.md 规范过时时一并修正

    - 修规范时先核实路径（三个 CODEBUDDY\.md：根 / backend / frontend）

---

### 第二部分 · 完整操作手册

#### 使用说明

- 按实际操作顺序组织：12\.1 盘点 → 12\.2 落改 → 12\.3 验证 CI → 收尾

- 每步先看「意图」（这一步在学什么），再看「避坑提示」，最后复制「完整提示词」贴到 CodeBuddy

- 每个提示词都可直接复制

---

#### 12\.1 CI/CD 现状盘点

##### 步骤 12\.1\.A · 出方案（Plan 模式）

意图：让 CodeBuddy 扫一遍现有 CI / pre\-commit / 依赖锁定，找出真实缺口。只读，不写。

避坑提示：

完整提示词（整段复制到 Plan 模式）：

```Plain Text
进入 Sprint 4 阶段十二·12.1：CI/CD 扩展 + pre-commit 现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 分支：feature/sprint-4
- 基线 tag：v0.3.0（阶段零到十一全部完成）
- 后端 pytest 110 passed（阶段十一 +23）
- 前端零测试（阶段十一裁决：11.3 / 11.4 跳过，放 v1.1.0）
- V3.7 计划：阶段十二 = CI/CD 扩展 + pre-commit
- 现有 CI：.github/workflows/ci.yml（4 job：backend / frontend / contract / ci-summary）
- Sprint 4 剩余预算：阶段十二 + 阶段十三 ≈ 1.5h，**不要大改 CI**

【硬约束】
- 不落盘任何文件
- 只在对话里输出分析
- 不改任何文件（不改 .github/、.pre-commit-config.yaml、pyproject.toml、package.json）

【本步目标】
1. 现有 CI 盘点：
   - 读 .github/workflows/ci.yml 全文
   - 列出 4 个 job 各自做什么（触发条件 / steps / 检查项）
   - 每个 job 跑的命令清单（pytest / ruff / tsc / eslint / build / gen:api / export_openapi --check 等）
   - 制作「覆盖检查矩阵」，逐项标注「本地 / CI / 都无」：
     - 后端 pytest
     - 后端 ruff check + format
     - 契约零漂移（export_openapi.py --check）
     - 前端 tsc
     - 前端 eslint
     - 前端 build
     - api.d.ts 生成物零漂移（gen:api + git diff --exit-code）
     - 依赖锁定文件未漂移（uv.lock / package-lock.json）
   - 哪些检查有、哪些无

2. pre-commit 现状：
   - 是否存在 .pre-commit-config.yaml
   - 是否存在 .husky/ 或 frontend/.husky/
   - package.json 是否有 husky / lint-staged 配置
   - pyproject.toml 是否有相关配置
   - 明确报告「有 / 无」

3. 依赖锁定现状：
   - backend 是否有 uv.lock
   - frontend 是否有 package-lock.json / pnpm-lock.yaml / yarn.lock
   - CI 是否用锁定文件安装（还是每次解析最新）

4. 出「CI/CD 现状表」：
   - 每项检查：本地有 / CI 有 / 都无
   - 哪些是「已在 CI」的（不需重复）
   - 哪些是「有配置但未在 CI 跑」
   - 哪些是「缺失的」

5. 出「阶段十二建议方案」（**克制优先**）：
   - 是否补「生成物零漂移」job（api.d.ts / openapi.yaml 重生成后 git diff）
   - 是否补「pre-commit 到 CI」（验证 hook 配置本身）
   - 是否补「依赖锁定」验证
   - pre-commit hooks 建议：
     - 后端：ruff check / ruff format 是否要加？
     - 前端：eslint / prettier 是否要加？
     - 通用：尾随空格 / 文件结尾换行 / 大文件拦截
     - 是否**跳过** pre-commit（因为已有 CI，本地 hook 收益低）
   - 每项注明：做 / 不做 / 放 v1.1.0 + 理由

6. 出「阶段十二预估工时」：
   - 每个子项耗时
   - 总工时
   - 是否在 ≤ 1h 预算内

7. 出「阶段十二风险评估」：
   - 改 CI 可能引入失败
   - 加 pre-commit 可能阻塞本地提交
   - 依赖锁定可能锁定旧版本导致无法升级
   - 是否需要回滚策略

【约束】
- 只读，不改任何文件
- 不跑新的 CI 命令（如 act / gh workflow run）
- 不装任何依赖
- 不改 .github / .pre-commit-config.yaml / pyproject.toml / package.json
- 中文回答
- 路径统一用 d:/AIProject/GraphRAG-Agent

【完成后输出】
1. 现有 CI 盘点（4 job 逐项 + 覆盖检查矩阵）
2. pre-commit 现状（有 / 无）
3. 依赖锁定现状（有 / 无）
4. CI/CD 现状表（本地 / CI / 都无）
5. 阶段十二建议方案（每项含理由）
6. 阶段十二预估工时
7. 阶段十二风险评估
8. 需要用户裁决的问题清单
```

##### 步骤 12\.1\.B · 裁决（普通对话）

意图：AI 出了报告，你按「Sprint 4 是收尾」的原则收紧范围。

避坑提示：

完整提示词：

```Plain Text
12.1 盘点审核通过。5 项裁决：

【1. 前端 tsc 进 CI】
做。但先本地跑 `npx tsc --noEmit` 确认零错误（用户执行）。
若存量错误 ≤ 3 且好修 → 本阶段修完上 CI；
若 > 3 或难修 → 本阶段只记录，放 v1.1.0。

【2. CI push 触发范围】
保持现状（只 push main + PR）。
理由：
- 扩 feature 分支会消耗 Actions 额度
- 本地跑 pytest / tsc 更快
- PR 时跑 CI 已足够拦问题
- 阶段十 / 十一全程直接 push feature 分支，没出问题

【3. 前端 build 冒烟】
放 v1.1.0。
理由：耗时 2~4min 翻倍 CI 时长，tsc 先拦大部分。

【4. pre-commit】
放 v1.1.0。
理由：CI 已兜底全部检查；本地 hook 增量收益低 + Windows CRLF 环境噪音风险。

【5. tsc 检出存量错误】
先看结果再定（见【1】）。

【追加：CODEBUDDY.md 规范修正】
盘点发现的「规范与现状不一致」是真实文档漂移，本阶段一并修正。
改前：「提交前必须通过 pre-commit hook」
改后：「提交前必须通过本地检查（后端 ruff check/format、前端 eslint/typecheck）；推送后以 CI 全量门禁（ruff/pytest/eslint/tsc/契约零漂移）为最终裁决。pre-commit hook 暂未启用，规划于 v1.1.0。」
不本批立即改——等 tsc 处理完，和 CI 改动同批提交。

【接下来等用户贴回 tsc 结果，再决定 CI 改动方案】
```

#### 12\.2 CI 改动

##### 步骤 12\.2\.A · 前置验证 tsc（PowerShell）

意图：CI 加 tsc step 前，先本地确认 tsc 零错误。

动作：

```Plain Text
cd d:/AIProject/GraphRAG-Agent/frontend
npm.cmd exec tsc -- --noEmit
```

结果处理：

---

##### 步骤 12\.2\.B · 出方案（Plan 模式）

意图：让 AI 出 ci\.yml \+ package\.json \+ CODEBUDDY\.md 的 diff 草案。

避坑提示：

完整提示词：

```Plain Text
tsc 本地结果：**0 error**（`npm.cmd exec tsc -- --noEmit` 无输出）。

【确认走最简路径】
CI 只加 1 个 step，不修存量错误。

【请出 12.2 改动方案（Plan 模式，不改代码）】
目标：给 frontend job 加 tsc step + 修正 CODEBUDDY.md 规范漂移。

1. 读 .github/workflows/ci.yml 的 frontend job 全文：
   - 现有 steps 顺序
   - 依赖安装步骤
   - lint / gen:api 步骤
2. 出「ci.yml 改动方案」：
   - tsc step 放在哪个位置（lint 之后？gen:api 之后？）
   - step 命令（npm run typecheck / npm exec tsc --noEmit / npx tsc --noEmit？）
   - 是否需要加 package.json 的 script（如 "typecheck": "tsc --noEmit"）
   - step name / 失败摘要
   - 贴出改动 diff 草案
3. **先核实 tsconfig 与 gitignore**：
   - frontend/tsconfig.json 的 include 是否含 next-env.d.ts / .next/types？
   - frontend/.gitignore 是否忽略 next-env.d.ts？
   - 如果 CI 检出后 next-env.d.ts 不存在，tsc 会不会报 Cannot find module？
   - 是否需要先 npm exec next typegen？
4. 读 CODEBUDDY.md（**先核实路径——仓库根 / backend / frontend 三处**）：
   - 用 Get-ChildItem -Recurse -Filter CODEBUDDY.md 找出哪个有「pre-commit hook」规范
   - 贴出「改前原文」
   - 给「改后文本」草案（与 CI 现状对齐）
5. 出验收标准：
   - ci.yml 语法有效（不破坏现有 4 job）
   - 本地 `npm run lint` + tsc step 命令都能跑通
   - CODEBUDDY.md 改动只改那一行
6. 出风险与坑位：
   - tsc step 在 CI ubuntu 下是否与本地一致
   - 是否需要 next typegen
   - 是否会触发 CI 时长增加

【约束】
- 只读，不改文件
- 先出方案，贴 diff 草案
- 不跑 CI / 不跑 act / 不装依赖
- 不修改 contracts / frontend/src / backend/app
```

##### 步骤 12\.2\.C · 核实证据（普通对话）

意图：核实三件事再落改——CODEBUDDY\.md 路径、next typegen 可用性、typegen 后 tsc 仍零错。

避坑提示：

完整提示词：

```Plain Text
12.2 方案审核通过，方向正确，`next-env.d.ts` 被 gitignore 的坑挖得关键。但有两处必须先核实：

【核实 1：CODEBUDDY.md 路径】
你说规范在仓库根 CODEBUDDY.md L66，但阶段零到十一改的都是 backend/CODEBUDDY.md。
请执行：
  Get-ChildItem -Path d:/AIProject/GraphRAG-Agent -Recurse -Filter "CODEBUDDY.md" -File | Select-Object FullName

如果两个都存在，检查两个文件是否都有「提交前必须通过 pre-commit hook」类规范——两个都要改。
如果只有 backend/，改 backend/CODEBUDDY.md。

【核实 2：next typegen 命令可用性】
在本地 frontend/ 下跑：
  npm.cmd exec next typegen
验证：
1. 命令能跑（不报「未知命令」）
2. 生成了 next-env.d.ts
3. 生成后 `npm.cmd exec tsc -- --noEmit` 仍 0 error
贴出命令输出。

若 typegen 不可用，fallback 方案：
- CI 里用 echo 写 next-env.d.ts 三行标准内容
- 或把 next-env.d.ts 从 .gitignore 移出并提交（需评估是否影响其他流程）

【核实完贴证据 + 确认后，进入落改阶段】
```

用户动作：

```PowerShell
# 核实 1：找三个 CODEBUDDY.md
Get-ChildItem -Path d:/AIProject/GraphRAG-Agent -Recurse -Filter "CODEBUDDY.md" -File | Select-Object FullName

# 核实 2：typegen 可用性 + typegen 后 tsc
cd d:/AIProject/GraphRAG-Agent/frontend
npm.cmd exec next typegen
npm.cmd exec tsc -- --noEmit
```

##### 步骤 12\.2\.D · 落改 \+ 审 diff（Craft 模式）

意图：让 AI 落改 3 个文件，贴出 diff。

完整提示词：

```Plain Text
两处核实通过：

【核实 1：CODEBUDDY.md 路径】
三个文件都存在，但「pre-commit hook」规范**只在仓库根** CODEBUDDY.md L66。
backend / frontend 的 CODEBUDDY.md 无此条。
修正：只改根 CODEBUDDY.md L66，不动 backend / frontend。

【核实 2：next typegen 可用性 + typegen 后 tsc】
- `npm.cmd exec next typegen` 输出 "✓ Types generated successfully"
- typegen 后 `npm.cmd exec tsc -- --noEmit` 仍 0 error
方案可行，无需 fallback。

【落改 3 个文件】
1. .github/workflows/ci.yml（frontend job 加 2 step + 失败摘要 1 行 + 头注释）
2. frontend/package.json（scripts 加 "typecheck": "tsc --noEmit"）
3. CODEBUDDY.md（仓库根，L66 一行替换）

请落改（Craft 模式），贴出三处 diff。

【约束】
- 不改 backend / frontend 的 CODEBUDDY.md
- 不改 contracts / backend/app
- 不改 frontend/src
- 不改其他 CI job
- 落改后本地验证：cd frontend && npm.cmd run lint && npm.cmd run typecheck（应全绿）
- 不执行 git 提交，由用户手动

【commit message（审过后）】
ci: add frontend typecheck step and fix pre-commit doc drift (Sprint4.12.2)
```

用户动作：

```PowerShell
# 本地验证（在 frontend/ 下）
cd d:/AIProject/GraphRAG-Agent/frontend
npm.cmd run lint
npm.cmd run typecheck
```

##### 步骤 12\.2\.E · 提交（PowerShell）

```PowerShell
cd d:/AIProject/GraphRAG-Agent
git status --short     # 期望 3 个 M + 6 个 ?? changes/
git add .github/workflows/ci.yml CODEBUDDY.md frontend/package.json
git status --short
git commit -m "ci: add frontend typecheck step and fix pre-commit doc drift (Sprint4.12.2)"
git push
git status --short
git log --oneline -3
```

注意：

- `git add` 前先 `git status --short` 核对

- 不应有 `package-lock.json` 改动（加 script 不动 lock）

- CRLF warning 是预期，不是错误

- push 失败直接重试，不 reset

---

#### 12\.3 临时 PR 验证 CI

##### 步骤 12\.3\.A · 开临时 PR

意图：CI 只在 push main \+ PR 时触发，直接 push feature 分支不跑。开临时 PR 触发 CI。

动作：

1. 浏览器打开：

```PowerShell
https://github.com/csheep86/GraphRAG-Agent/compare/main...feature/sprint-4
```

2. 点「Create pull request」

3. 标题：`[临时] 验证 12.2 CI 改动`
描述：`临时 PR，仅用于触发 CI 验证，绿了立即关闭`

4. 点「Create pull request」

5. 等 CI 跑（2\~3 分钟）

避坑提示：

##### 步骤 12\.3\.B · 看 CI 结果

4 个 job 期望全绿：

如果有红：

1. 不要点 Close，先点红色 job 看报错

2. 贴报错给人工/CodeBuddy 判断

3. 修 → commit → push → CI 自动重跑

本次实际踩到的坑：

CI backend job 报 `ruff I001 Import block is un-sorted or un-formatted in tests/test_auth.py`——阶段十一 11\.2 三批落改时只跑了 pytest，漏了 ruff。

##### 步骤 12\.3\.C · 修复阶段十一遗留的 ruff 问题

完整提示词（Craft 模式）：

```Plain Text
临时 PR 的 backend job 报 ruff I001：
tests/test_auth.py 的 import block 未排序。

【根因】
阶段十一 11.2 三批落改时，验证链只跑了 pytest，漏了 ruff check + ruff format --check。

【修复】
1. cd backend && uv run ruff check . --fix      # 修 import 顺序
2. uv run ruff format .                          # 修文件末尾换行
3. uv run ruff check .                           # 期望 All checks passed
4. uv run ruff format --check .                  # 期望 all files already formatted
5. uv run pytest -q                              # 期望 110 passed 不变

【约束】
- 只改 backend/tests/ 下的测试文件
- 不改业务代码
- 如 ruff format 动了非测试文件，先停下来报告
- 修完后贴出 git diff（确认只是格式调整）
- 不执行 git 提交，由用户手动

【commit message（审过后）】
style: fix ruff import order and formatting in Sprint4.11.2 tests
```

##### 步骤 12\.3\.D · 提交修复

```PowerShell
cd d:/AIProject/GraphRAG-Agent
git status --short     # 期望只有测试文件 M
git --no-pager diff backend/tests/     # 确认只是格式调整
git add backend/tests/test_auth.py backend/tests/test_document_parse_executor.py
git status --short
git commit -m "style: fix ruff import order and formatting in Sprint4.11.2 tests"
git push
git status --short
git log --oneline -3
```

##### 步骤 12\.3\.E · 重看 CI \+ 关闭 PR

1. 刷新 PR 页面 → push 新 commit 会自动触发 CI

2. 期望 4 job 全绿

3. 绿了 → 点页面底部「Close pull request」（不点 上面的「Merge pull request」）

4. 确认顶部状态从 `Open` 变 `Closed`

避坑提示：

- 关闭后不要再点 Reopen（会触发多余 CI）

- 关闭 ≠ 合并——真正合并到 main 在阶段十三

---

#### 12\.4 收尾

##### 回 CodeBuddy

```Markdown
阶段十二 CI 验证完成，全绿（PR #1 已关闭，不合并）。

【结果】
- 临时 PR 4 job 全绿（backend / frontend / contract / ci-summary）
- 修复过程中的两次改动：
  1. 3b98d609 - ci: 加 frontend typecheck step + 修 CODEBUDDY.md 规范漂移
  2. b9490ff1 - style: 修 ruff import order 和 formatting（阶段十一遗留）
- 临时 PR 已关闭（不合并）

【发现并修复的遗留问题】
阶段十一 11.2 三批落改时，验证链漏跑了：
- uv run ruff check .
- uv run ruff format --check .
导致 test_auth.py / test_document_parse_executor.py 有 import 顺序 + 末尾换行问题。
已在 b9490ff1 修复。

【阶段十二收尾】
- 12.2 CI 改动已提交并验证
- 12.3 是否还有未完成项？
- 阶段十二正式结束，准备进阶段十三
```

### 附 A：每步教什么

---

### 附 B：常见 CodeBuddy 反问 \& 应答

---

### 附 C：全阶段重走检查清单

开工前：

- `git status --short` 无输出

- `uv run pytest -q` 显示 110 passed

12\.1：

- Plan 模式 → 贴 12\.1\.A 提示词

- 审报告 → 贴 12\.1\.B 裁决

12\.2：

- 本地跑 `npm.cmd exec tsc -- --noEmit` → 确认 0 error

- Plan 模式 → 贴 12\.2\.B 出方案

- 核实 CODEBUDDY\.md 路径 \+ next typegen 可用性

- Craft 模式 → 贴 12\.2\.D 落改

- 本地验证 `npm run lint` \+ `npm run typecheck`

- PowerShell 提交（`3b98d609`）

12\.3：

- 开临时 PR

- 看 CI（本次报 ruff 错）

- Craft 模式修复 → 提交（`b9490ff1`）

- 重看 CI → 全绿

- 关闭 PR（不合并）

收尾：

- `git status --short` 只剩 changes/ 未跟踪

- 记录「验证链必含 ruff」的教训

---

### 使用说明

1. 第一部分放笔记前面（查阅用）：做了什么、避哪些坑

2. 第二部分放笔记后面（重走用）：每个提示词可整段复制

## 阶段十三（归档 \+ tag v1\.0\.0 \+ 合并 main）

### 第一部分 · 结论与速查

#### 13\.0 阶段定位与原则

目标：把 Sprint 4 的全部工作整理为可发布状态（归档 \+ tag \+ 合并 main）。

核心原则：

1. 合并前先验证：临时 PR 跑 CI，绿了才合并 main

2. 先合并后打 tag：对齐 v0\.3\.0 惯例，tag 打在 main 的 merge commit

3. \-\-no\-ff 保留 merge commit：作为 tag 锚点 \+ 回滚锚点

4. tag 前核对 commit：tag 必须指向 merge commit，不是 feature 分支头

5. tag push 即公开：核对无误再 push

6. 网络抖动直接重试：不 reset、不改 remote

批次划分：

---

#### 13\.1 现状盘点（结论）

关键发现（部分超出预判）：

v1\.1\.0 待办汇总（8 大类，详见 release notes）：

- A\. 架构性未实现（4）：PG RLS / kg\_versions PG 真源 / Agent Tool 循环 / 存储抽象层

- B\. 文档漂移（4\+1）：S4\-1\~S4\-4 \+ S4\-1 遗留 6 处

- C\. 疑似缺陷（3）：B1 retry\_count / B4 task\_retry\_multiplier / \_refuse trace\_id

- D\. 数据质量（2）：E1 孤立节点 / E2 实体命名

- E\. 租户隔离（1）：agent/query fail\-open

- F\. 前端（2）：listDocuments 走 Mock / scheduleProgress mock\-only

- G\. 脚本编码（1）：Python stdout

- H\. 探针工具化（1）：probe 脚本移 scripts/

---

#### 13\.2 内容落盘（4 commit）

commit 顺序与内容：

关键设计：

**归档命名规范**

```Plain Text
changes/archive/2026-09-20-Sprint4.10.1/
changes/archive/2026-09-20-Sprint4.10.1.5/
changes/archive/2026-09-20-Sprint4.10.1.6/
changes/archive/2026-09-20-Sprint4.10.2/
changes/archive/2026-09-20-Sprint4.10.3/
changes/archive/2026-09-20-Sprint4.10.4/
```

- 格式：`YYYY-MM-DD-<原名>`

- 保留批次粒度（不合并为单一目录）

- `.gitkeep` 保留

- ignored 的 `*.log` / `pycache/` 随目录物理迁移但仍不入库

**spec 状态刷新**

```Diff
- > **状态**：MVP 规格（实现前）
+ > **状态**：MVP 规格（v1.0.0 已交付，实现态见 backend/CODEBUDDY.md §4）
```

- 5 份 spec（m1\~m5）\+ `docs/03-prd.md` 同步

- m2 特殊：因同时有 501 措辞修复，全部归 commit 2

**版本号统一（关键发现）**

必须同步改 `backend/uv.lock`：

- `backend/pyproject.toml`：`version = "0.1.0"` → `"1.0.0"`

- `backend/uv.lock:42`：`version = "0.1.0"` → `"1.0.0"`（否则 CI `uv sync --frozen` 红）

- `frontend/package.json`：`0.1.0` → `1.0.0`

- `frontend/package-lock.json:3,9`：两处 `0.1.0` → `1.0.0`

- `backend/app/core/config.py`：不动（已 1\.0\.0）

刷新命令（官方工具，非手改）：

```PowerShell
cd backend
uv lock  # 自动更新 uv.lock 里的 backend version
uv lock --check  # 验证
```

**release notes**

新建 `docs/release-notes/v1.0.0.md`（72 行，7 节）：

1. 范围（16 commits / 35 files / \+2394 −274）

2. 模块级交付（M1 / M2 / M3 / M5）

3. 契约变更（\+110 行）

4. 前端（CONTRACT\_COVERED\_PATTERNS / dev X\-Org\-Id / P03）

5. CI 门禁（4 job \+ 新增 typecheck）

6. 验证证据（pytest 110 \+ 10\.1\~10\.4 联调）

7. 已知限制（= §4 摘要）\+ 升级/回滚

---

#### 13\.3 合并发布（跨分支）

执行顺序：

```PowerShell
1. push feature/sprint-4
2. 开临时 PR → CI 绿 → 关闭（不合并）
3. git checkout main && git pull
4. git merge --no-ff feature/sprint-4 -m "merge: sprint 4 done (v1.0.0)"
5. git push origin main
6. 等 main CI 绿
7. git tag -a v1.0.0 -m "Sprint 4 done: v1.0.0 full-stack + agentic-rag hardening"
8. git log --oneline -1 v1.0.0  # 核对指向 merge commit
9. git push origin v1.0.0
10. git ls-remote --tags origin  # 验证 5 个 tag
```

关键约束：

---

#### 13\.4 陷阱速查表

---

#### 13\.5 决策速查表

---

#### 13\.6 交付总览

提交历史（4 个阶段十三 commit \+ 1 个 merge commit）：

```Plain Text
4638bbaf merge: sprint 4 done (v1.0.0)          ← tag v1.0.0 指向
24e37ba8 docs: mark S4-1~S4-4 repaid and register residual gaps (Sprint4.13)
834c4032 chore: bump manifests to v1.0.0 (Sprint4.13)
b550e26a docs: fix stale doc drift in specs, api-spec, frontend comments, registry (Sprint4.13)
78a5e21d chore: archive sprint4 evidence, mark specs delivered, add v1.0.0 release notes (Sprint4.13)
```

改动规模（merge commit 汇总）：

```Plain Text
56 files changed, 5460 insertions(+), 298 deletions(-)
```

tag 清单：

```Plain Text
sprint-1-done  (lightweight)
v0.1.0         (annotated)
v0.2.0         (annotated)
v0.3.0         (annotated)
v1.0.0         (annotated) ← 本次
```

CI 结果：

- 临时 PR \#2：4 job 全绿

- main CI \#8（`merge: sprint 4 done (v1.0.0)`）：4 job 全绿，41s

v1\.0\.0 交付内容：

v1\.1\.0 已知限制（8 大类 18 项，详见 release notes \+ `backend/CODEBUDDY.md` §4）

---

#### 13\.7 跨阶段通用规则

1. 发布顺序不可颠倒

    - push feature → 临时 PR 验证 → merge \-\-no\-ff → push main → main CI 绿 → tag → push tag

    - 不得先打 tag 后 push main

2. tag 前必核对

    - `git log --oneline -1 <tag>` 必须指向目标 commit

    - tag 一旦 push 即公开，重打需删远程

3. 版本号统一

    - 改 `pyproject.toml` 必须跑 `uv lock`

    - 改 `package.json` 必须同步 `package-lock.json`

    - 三处（config / manifest / lock）必须一致

4. merge 保留记录

    - 用 `--no-ff` 强制 merge commit

    - message 格式对齐历史里程碑：`merge: sprint N done (vX.Y.Z)`

5. 回滚策略

    - merge commit 是回滚锚点（`git revert -m 1 <merge>`）

    - tag 未 push 前可删可重打

    - main 已 push 后不 force push，用 revert

---

## 第二部分 · 完整操作手册

### 使用说明

- 按实际操作顺序组织：13\.1 盘点 → 13\.2 内容落盘 → 13\.3 合并发布

- 每步先看「意图」，再看「避坑提示」，最后复制「完整提示词」

- 每个提示词都可直接复制

---

### 13\.1 现状盘点

#### 步骤 13\.1\.A · 出方案（Plan 模式）

意图：让 CodeBuddy 扫一遍 changes / specs / tag / main 差异，找出收尾要处理的所有事。只读，不写。

避坑提示：

完整提示词（整段复制到 Plan 模式）：

```Plain Text
进入 Sprint 4 阶段十三·13.1：归档 + tag v1.0.0 + 合并 main 的现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 分支：feature/sprint-4
- 基线 tag：v0.3.0（Sprint 3 里程碑）
- 阶段零到十二全部完成，pytest 110 passed，CI 4 job 全绿（临时 PR 验证过）
- V3.7 计划：阶段十三 = 归档 changes/ → archive/ + spec 状态刷 completed + tag v1.0.0 + 合并 main
- Sprint 4 剩余预算：阶段十三 ≈ 1h

【硬约束】
- 不落盘任何文件
- 只在对话里输出分析
- 不改任何文件
- 不执行 git commit / tag / merge / push

【本步目标（只读盘点，全部贴证据）】
1. changes/ 目录现状：
   - 列出 changes/ 下所有子目录 / 文件
   - 哪些已跟踪 / 哪些未跟踪（git status）
   - 判断：全部进 archive/ 还是部分保留？
   - 归档命名规范（与 V3.7 既有约定一致？）

2. specs/ 目录现状：
   - 列出 specs/ 下所有 spec 文件（m1~m5）
   - 每个 spec 的「状态」字段当前值
   - 哪些需要刷成 completed？
   - 是否有 spec 状态字段？还是靠文档约定？

3. docs/release-notes/ 现状：
   - 是否存在这个目录？
   - 是否有历史 release notes（v0.1.0 / v0.2.0 / v0.3.0）？
   - 如果有，参考格式；如果没有，建议格式

4. tag 现状：
   - git tag --list 全部 tag
   - git ls-remote --tags origin（远程 tag）
   - v0.3.0 的 tag 类型（lightweight / annotated）

5. main 分支现状：
   - git log --oneline main -5
   - main 与 feature/sprint-4 的差异
   - 是否 fast-forward 可合并？还是需要 --no-ff？

6. 待处理清单汇总：
   - 从 backend/CODEBUDDY.md §4 缺口表读出所有 v1.1.0 待办
   - 整理成清单
   - 是否有其他散落的待办

7. **版本号核实（关键）**：
   - backend/app/core/config.py 的 app_version
   - backend/pyproject.toml 的 version
   - **backend/uv.lock 是否记录 backend 项目自身的 version**
   - frontend/package.json 的 version
   - frontend/package-lock.json 是否记录项目 version（lockfileVersion 3 有两处）
   - 这些是否一致？

8. 阶段十三执行顺序建议：
   - 归档 changes/ 何时做
   - spec 状态刷 completed 何时做
   - release notes 何时写
   - tag v1.0.0 打在哪
   - 合并用 --no-ff 还是 fast-forward
   - push 顺序
   - 合并后 CI 是否自动跑？如何验证？

9. 风险评估：
   - 合并 main 后 CI 红怎么办
   - tag 打错能否删除 / 重打
   - 合并冲突的可能点

【约束】
- 只读，不改任何文件
- 不执行 git commit / tag / merge / push
- 不跑 CI
- 中文回答
- 路径统一用 d:/AIProject/GraphRAG-Agent

【完成后输出】
1. changes/ 现状 + 归档建议
2. specs/ 现状 + 状态刷新清单
3. docs/release-notes/ 现状 + 建议格式
4. tag 现状
5. main 与 feature/sprint-4 差异
6. v1.1.0 待办汇总清单
7. **版本号一致性核实结果**
8. 阶段十三执行顺序建议
9. 风险评估 + 回滚策略
10. 需要用户裁决的问题清单
```

#### 步骤 13\.1\.B · 裁决（普通对话）

意图：AI 出报告后，按「Sprint 4 是收尾」\+「对齐 v0\.3\.0 惯例」原则裁决 10 项。

完整提示词：

```Plain Text
13.1 盘点审核通过。10 项裁决：

1. 归档命名：A（保留 6 个批次目录 archive/YYYY-MM-DD-Sprint4.10.x/）
2. 证据链：保持 ignore（只存 .md + .py，log/pyc 不入库）
3. probe 脚本：归档保留在 changes/archive/ 下，不移到 backend/scripts/
4. spec 状态值：MVP 规格（v1.0.0 已交付，实现态见 backend/CODEBUDDY.md §4）；docs/03-prd.md 一并
5. 顺带修 S4-1~S4-4：本批一起修，拆独立 commit
6. release notes：新建 docs/release-notes/v1.0.0.md
7. tag：main merge commit + annotated
8. 合并：--no-ff
9. 版本号统一：本批统一到 1.0.0（**含 uv.lock / package-lock.json**）
10. CI tag 触发：接受现状

【本批只做 13.2（内容落盘），不做 13.3（合并发布）】

按顺序做 4 个 commit：
- commit 1: 归档 + spec 状态 + release notes
- commit 2: 修 S4-1~S4-4 文档漂移（含 m2 的 2 行）
- commit 3: 版本号统一到 1.0.0
- commit 4: 补 _refuse() trace_id + S4-1 遗留到 §4 缺口表

【约束】
- 不执行 git commit（由用户手动，你只落改 + 出 diff）
- 不改 contracts/
- 不改 backend/app/ 业务代码
- 每个 commit 前贴出改动文件清单 + 关键 diff 给用户审
```

### 13\.2 内容落盘

#### 步骤 13\.2\.A · CodeBuddy 落改（Craft 模式）

完整提示词（把 13\.1\.B 的裁决整段贴过去，加具体要求）：

```Plain Text
（贴 13.1.B 的裁决）

【落改顺序】
1. 先做 commit 1：归档 + spec 状态 + release notes
   - 归档：先 git add changes/Sprint4.10.*（未跟踪目录），再 git mv 到 changes/archive/2026-09-20-Sprint4.10.*
   - 刷 specs/m1~m5 的第 5 行状态 + docs/03-prd.md 第 5 行
   - 新建 docs/release-notes/v1.0.0.md（7 节格式）

2. commit 2：修 S4-1~S4-4 文档漂移
   - S4-1: docs/multimodal_rag_backend_api_spec-v1.0.md:137
   - S4-2: specs/m2-extract-kg.md:157（501 措辞 + 句首「契约草案」→「已定稿并落库」）
   - S4-3: frontend/src/api/client.ts:23 / api/graph.ts:43 / api/qa.ts:61 / .env.development:13
   - S4-4: backend/app/tasks/registry.py:135-138 docstring
   - **m2 的 2 行（状态 + 501 措辞 + 句首）全归 commit 2**

3. commit 3：版本号统一
   - **先跑 uv lock 刷新 backend/uv.lock**（关键）
   - 改 backend/pyproject.toml / frontend/package.json / frontend/package-lock.json
   - 不动 backend/app/core/config.py

4. commit 4：缺口登记
   - backend/CODEBUDDY.md §4 追加 _refuse trace_id + S4-1 遗留
   - 标记 S4-1~S4-4 四行为 ✅ 已偿还（Sprint 4.13）

【约束】
- 不执行 git commit（用户手动）
- 每个 commit 前贴文件清单 + 关键 diff
- 只改本批涉及的文件
```

用户动作：

1. 贴给 CodeBuddy

2. 它落改后，自己手动 4 个 commit（每步 `git status --short` 核对）

#### 步骤 13\.2\.B · 手动 4 个 commit（PowerShell）

```PowerShell
cd d:/AIProject/GraphRAG-Agent

# commit 1（去掉 m2）
git add changes/ specs/m1-async-ingest.md specs/m3-graphqa-citation.md specs/m4-affiliation-detection.md specs/m5-permission-audit.md docs/03-prd.md docs/release-notes/v1.0.0.md
git status --short
git commit -m "chore: archive sprint4 evidence, mark specs delivered, add v1.0.0 release notes (Sprint4.13)"

# commit 2（含 m2）
git add docs/multimodal_rag_backend_api_spec-v1.0.md specs/m2-extract-kg.md frontend/src/api/client.ts frontend/src/api/graph.ts frontend/src/api/qa.ts frontend/.env.development backend/app/tasks/registry.py
git status --short
git commit -m "docs: fix stale doc drift in specs, api-spec, frontend comments, registry (Sprint4.13)"

# commit 3（含 uv.lock）
git add backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
git status --short
git commit -m "chore: bump manifests to v1.0.0 (Sprint4.13)"

# commit 4
git add backend/CODEBUDDY.md
git status --short
git commit -m "docs: mark S4-1~S4-4 repaid and register residual gaps (Sprint4.13)"
```

验证：

```PowerShell
git status --short     # 无输出
git log --oneline -6   # 顶部 4 个是本次 commit
```

### 13\.3 合并发布

#### 步骤 13\.3\.A · push feature \+ 临时 PR（第一段）

完整提示词/命令：

```PowerShell
# 1. push feature
git push
```

浏览器打开：

```Plain Text
https://github.com/csheep86/GraphRAG-Agent/compare/main...feature/sprint-4
```

- 标题：`[临时] 验证 13.2 归档 + 版本号 CI`

- 点「Create pull request」

- 等 CI 绿（2\~3 分钟）

- 点「Close pull request」关闭（不合并）

#### 步骤 13\.3\.B · merge \+ push main（第二段）

```PowerShell
# 2. 本地 merge
git checkout main
git pull origin main
git merge --no-ff feature/sprint-4 -m "merge: sprint 4 done (v1.0.0)"

# 核对（先不 push）
git status --short    # 无输出
git log --oneline -3  # 顶部 merge commit

# 3. push main
git push origin main
```

去 GitHub Actions 看 main CI（`on.push.branches: [main]` 自动触发）：

- 4 job 全绿才继续

#### 步骤 13\.3\.C · tag v1\.0\.0（第三段）

```PowerShell
# 4. 打 annotated tag
git tag -a v1.0.0 -m "Sprint 4 done: v1.0.0 full-stack + agentic-rag hardening"

# 5. 核对 tag 指向（关键）
git log --oneline -1 v1.0.0     # 必须指向 merge commit
git tag -l -n1 v1.0.0           # 显示 annotation message

# 6. push tag
git push origin v1.0.0

# 7. 最终验收
git tag                          # 5 个 tag
git log --oneline -3
git status --short               # 无输出
git ls-remote --tags origin      # 5 个远程 tag
```

### 附 A：每步教什么

---

### 附 B：常见 CodeBuddy 反问 \& 应答

---

### 附 C：全阶段重走检查清单

开工前：

- `git status --short` 无输出

- `uv run pytest -q` 显示 110 passed

- 已读 V3\.7 文档（含 V3\.11 阶段十二增补）

13\.1：

- Plan 模式 → 贴 13\.1\.A 提示词

- 审报告 → 贴 13\.1\.B 裁决

13\.2：

- Craft 模式 → CodeBuddy 落改

- 手动 4 个 commit（每步核对）

- `git log --oneline -6` 确认

13\.3：

- push feature

- 临时 PR → CI 绿 → 关闭

- checkout main → merge \-\-no\-ff → push main

- main CI 绿

- tag \-a v1\.0\.0 → 核对 → push tag

- `git ls-remote --tags origin` 验证 5 个 tag

收尾：

- `git status --short` 无输出

- 飞书记录阶段十三笔记

---

## 🎉 Sprint 4 完整回顾

Sprint 4 总计：20 commits / 56 files / \+5460 −298

v0\.3\.0 → v1\.0\.0 里程碑：

- 4 个契约内接口真实联调通过

- 110 个 pytest 全绿

- 4 job CI 全绿

- 双轨机制（Mock ↔ 真实）完整

- v1\.1\.0 待办清单 18 项

## 验收一下交付

```PowerShell
cd d:/AIProject/GraphRAG-Agent

# 确认 tag 存在
git tag
# 应该看到 v1.0.0

# 确认指向正确
git log --oneline -1 v1.0.0
# 应该显示 4638bbaf merge: sprint 4 done (v1.0.0)

# 确认远程同步
git status --short
# 应该无输出

# 浏览器打开
# https://github.com/csheep86/GraphRAG-Agent/releases
# 或者
# https://github.com/csheep86/GraphRAG-Agent/tree/v1.0.0
```

```PowerShell
# 后端
cd backend
uv run pytest -q          # 期望 110 passed
uv run ruff check .       # 期望 All checks passed

# 前端
cd ../frontend
npm.cmd run lint          # 期望 0 error
npm.cmd run typecheck     # 期望 0 error
npm.cmd run build         # 期望 Compiled successfully
```

## 演示项目

```PowerShell
# 终端 1（后端）
cd backend
uv run uvicorn app.main:app --reload --port 8000

# 终端 2（前端）
cd frontend
npm.cmd run dev

# 浏览器
# http://localhost:3000
```

---

# 🚀 Sprint 5~8：Demo-MVP 增量交付（v1.1.0 → v1.4.0）

> **总纲**：v1.0.0 是"工程外壳"（PRD §5 黄金路径 7 步只通 2 步）。Sprint 5~8 用四个小步把黄金路径全部走通，终点 **v1.4.0 = 首个可给客户现场演示、全链路无假数据的 Demo-MVP**。
> **详细计划（实施前必读）**：`docs/v1.1.0-demo-mvp-plan.md`——含现状资产盘点、演示剧本、每 Sprint 验收清单、降级预案、风险登记册。
> **核心诊断**：v1.0.0 的状态是"消费端就绪、生产端空缺"——读路径（图谱查询、问答、引用校验、拒答）全通，写路径（落盘、解析、在线建图、chunk 证据）全缺。四个 Sprint 的本质就是**把写路径一段段接上，每接一段关一个前端 Mock 开关**。
> **硬验收总纲（新增铁律）**：每个 Sprint 收尾时，对应前端页面的 Mock 必须关闭（`USE_MOCK` 相关路由走真实接口），演示剧本对应步骤不允许出现任何假数据（含那个假的"1248 份文档"）。唯一豁免：settings 页（后端零接口，保持现状或隐藏路由）。
> **方法论不变**：Plan 模式盘点（只读）→ 用户裁决 → Craft 模式落改 → 手动 commit → Sprint 收尾三件套（tag + merge --no-ff + push）。
> **敏捷纪律**：每个 Sprint 都有独立演示点，任何时刻中止都留下一个可演示的增量；明确不做的清单见计划文档 §10（RBAC / RLS / 另两类算法 / Agent Tool 循环 / 多格式 / C1~C3 实验 / E2 Prompt 重设计 / 图谱时效边等全部推迟 v1.5+）；**企业系统集成只预留接缝、零真实对接**（计划文档 §8~§9 / ADR-0004）。

---

# 六、Sprint 5：真解析与在线建图（v1.1.0）

## 阶段十四：存储抽象 + MinerU 转正 + 在线抽取建图

### 14.0 阶段定位与原则

目标：接上 v1.0.0 的两条断链——文件真实落盘（`storage_key` 不再恒 NULL）；上传 completed 后**自动触发**抽取→建图（告别手工跑 import 脚本）。约 3 周（v2.1：+0.5 周，容纳批次 A2 集成预留位），分支 `feature/sprint-5`。

核心原则：

1. **预研转正，不重写**：`mineru_mvp/`、`langextract_mvp/`、`bridge_web_demo/` 已验证的代码是蓝本，转正进 `backend/app/`，严禁从零重写。
2. **契约先行依旧**：新增接口（文档列表、全局图谱、实体详情）先改 `contracts/openapi.yaml` → `npm run gen:api` → 再写实现。
3. **ADR-0002 三段式写入不破坏**：在线建图必须复用既有 `:KgVersion` 状态机语义。
4. **顺手修 B 类缺陷**：B1 `retry_count` / B4 `task_retry_multiplier` 在动 `documents.py` 时一并偿还。
5. **干净基线**：批次 B 动工前清空 Neo4j 预研数据（E1/E2 残留），重建干净基线。E1/E2 只做"重接后重新评估并登记结论"，**Prompt 抽取规范重设计不在本 Sprint**（v1.5+）。
6. **预留不实现**：为未来企业系统集成预留接缝（字段 + 接口 + 事件出口），**只预留、不做任何真实对接**；预留字段一律 nullable 且**不进 API 契约**（根 `CODEBUDDY.md` §功能预留原则 / ADR-0004）。

批次划分：

- **批次 A**：存储抽象层落盘 + `storage_key` 回填 + parsing 状态真实执行 MinerU + B1/B4 修复
- **批次 A2（集成预留位，净增 2.5 天）**：Provider 抽象（`parser_provider` / `llm_provider`，去 `deepseek_` 硬编码，净增 1 天）+ `documents` 补 8 个可空预留字段（0.5 天）+ `AuthProvider` 接口收口（0.5 天）+ `EXECUTOR_REGISTRY` 阶段命名规范化与 `pipeline_stages` 配置（0.5 天）。**`domain_events` 不在本 Sprint，落 Sprint 7 批次 D**
- **批次 B**：completed → 自动触发 LangExtract → 三段式写入 Neo4j + `kg_versions` 落 PG 真源表 + E1/E2 重接后重新评估（**只评估，不改 Prompt**）
- **批次 C**：文档列表 / 全局图谱 / 实体详情接口 + 前端 documents / graph 页关 Mock + 新路径登记进 `CONTRACT_COVERED_PATTERNS`（关 Mock 硬门槛）

### 14.1 批次 A·B：后端链路（Plan → Craft）

#### 步骤 14.1.A · 盘点（Plan 模式，只读）

完整提示词（整段复制到 Plan 模式）：

```Plain Text
进入 Sprint 5 阶段十四·批次 A+B 的现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 基线：tag v1.0.0（工程外壳：状态机/契约/CI 就绪，黄金路径 2/7）
- 目标：上传 PDF → 真实落盘 → MinerU 解析 → completed 自动触发 LangExtract 抽取 → ADR-0002 三段式写入 Neo4j → kg_versions 落 PG
- 预研蓝本：mineru_mvp/（云 API 已验证）、langextract_mvp/（抽取+原文定位已验证）、bridge_web_demo/（全链路已打通）
- 详细计划：docs/v1.1.0-demo-mvp-plan.md §4

【硬约束】
- 不落盘任何文件、不改任何代码
- 只在对话里输出分析

【本步目标（全部贴证据）】
1. 存储抽象层设计：落盘目录结构、storage_key 命名规则（建议 filename_hash，对齐前端 mock.d.ts 注释）、completed 时回填点在哪
2. MinerU 转正路径：mineru_mvp/ 哪些代码可直接搬进 backend/app/services/？密钥配置如何并入 .env 体系？
3. 在线抽取触发点：documents 状态机在哪里挂"completed → 抽取任务"？异步还是同步？复用 tasks/ 框架还是新建？
4. 三段式写入复用：import 脚本的写入逻辑如何抽成 service？KgVersion 状态机语义是否需要变？
5. kg_versions PG 真源表：表结构、与 Neo4j 的一致性校验点
6. B1/B4 缺陷确认：backend/CODEBUDDY.md §4 对应条目的现状
7. E1/E2 数据清理方案：清空 Neo4j 预研数据的命令与时机（**E1/E2 只做"重接后重新评估并登记结论"，Prompt 重设计不在本 Sprint**）
8. 集成预留位落点（批次 A2）：Provider 抽象（parser/llm）需改造的 MinerU/DeepSeek 调用点清单；`documents` 8 个可空预留字段的命名与用途；`AuthProvider` 如何包装现有 dev header 逻辑；`EXECUTOR_REGISTRY` 阶段命名规范化方案与 `pipeline_stages` 配置形态
9. 疑问清单（需要用户裁决的问题）

【约束】
- 只读；中文回答；路径统一用 d:/AIProject/GraphRAG-Agent

【完成后输出】
1. 存储抽象设计草案
2. MinerU/LangExtract 转正映射表（预研文件 → 目标文件）
3. 在线建图触发链路图
4. kg_versions 表结构
5. B1/B4 修复方案
6. 数据清理方案
7. 需要用户裁决的问题清单
```

#### 步骤 14.1.B · 裁决后落改（Craft 模式）

用户裁决要点（默认裁决，可改）：

1. 存储：本地目录 `backend/storage/`（或独立卷挂载点），`storage_key = {filename_hash}.{ext}`，目录进 .gitignore
2. MinerU：云 API 模式转正，密钥并入 backend/.env；`PRIVATE_DEPLOY_ENABLED` 配置占位（不实现）
3. 触发：复用 tasks/ 异步框架，completed 后入队抽取任务，新增 extracting 状态（若契约状态枚举需扩，先改契约）
4. 写入：import 脚本逻辑抽为 `app/services/kg_writer.py`（或并入 graphs.py），三段式语义不变
5. B1/B4 本批一起修，独立 commit
6. 数据清理：批次 B 动工前清空 Neo4j，彩排数据用 bridge 重新灌入一次作为基线

Craft 提示词（把上面裁决整段贴过去）：

```Plain Text
（贴 14.1.B 裁决）

按批次 A → B 顺序落改：
- 批次 A：存储抽象 + MinerU 转正 + storage_key 回填 + B1/B4 修复
- 批次 B：抽取任务入队 + kg_writer service + kg_versions PG 表 + E1/E2 清理

【约束】
- 契约变更必须先改 contracts/openapi.yaml 并跑 gen:api
- 不执行 git commit（用户手动）
- 每个批次结束贴改动文件清单 + 关键 diff 给用户审
- 新增测试对齐测试分层规范（单元/集成/契约）
```

#### 步骤 14.1.A2 · 集成预留位（批次 A2，Craft 模式）

> 前置：`docs/adr/0004-integration-seams.md` 已裁决（8 接缝）。本步骤**只预留，不实现任何真实对接**。

```Plain Text
进入 Sprint 5 阶段十四·批次 A2：集成预留位（净增 2.5 天）。

【当前背景】
- 决策依据：docs/adr/0004-integration-seams.md（8 接缝）+ 根 CODEBUDDY.md §功能预留原则（第 4~6 条）
- 目标交付形态：企业内网本地部署（外部 API 是临时态，必须可切换）
- **预算硬顶 2.5 天**：第 1 天末（CP1）、第 2.5 天末（CP2）各看表一次（计划文档 §4.5）；超时不挤占批次 B，按计划文档 §4.4 第二条降级

【四项动作（只做这四项）】
1. Provider 抽象（净增 1 天）：parser_provider / llm_provider，配置去 `deepseek_` 硬编码（OpenAI 兼容）；PRIVATE_DEPLOY_ENABLED 配置占位（**合规形态：有读取代码行 + 显式报未实现**，ADR-0004 §3 例外登记）
2. documents 补 8 个可空字段（0.5 天）：source_type / source_ref / document_key / content_hash / source_version / acl_scope / acl_owner_ref / deleted_at
3. AuthProvider 接口收口（0.5 天）：收口到 app/services/auth/，仅实现 LocalAuthProvider（包装现有 dev header / token 校验）；不建 users 表
4. 流水线接缝（0.5 天）：EXECUTOR_REGISTRY 阶段命名规范化（document.parse → document.extract → kg.build → risk.detect）+ settings.pipeline_stages 配置

【硬约束】
- 预留字段一律 nullable 且**不进 contracts/openapi.yaml**（根 CODEBUDDY.md §功能预留原则 第 4 条）
- 不做动态插件加载、不做通用连接器框架、不为未来系统写 stub
- **接口实现集合 = ADR-0004 §2.1 登记集合**：通常 1 个实现（如 LocalAuthProvider）；**接缝 5 事件出口例外，为 db + log 两个本地实现**；出现登记外实现（如 LdapAuthProvider）即越界（根 CODEBUDDY.md §功能预留原则 第 6 条）
- **新增 `settings.*` 必须能指出读取它的代码行**，无消费者的配置不得提交（例外仅 PRIVATE_DEPLOY_ENABLED / settings.log_export，且必须"显式报未实现"）
- 不建 users / document_sources / external_refs / domain_events 表（分别留 Pro 阶段 / Sprint 7）
- 不执行 git commit；契约零漂移 CI 必须保持绿

【完成后输出】
1. 改动文件清单 + 关键 diff
2. export_openapi.py --check 无 diff 的证据
3. ADR-0004 §4「未来如何扩展」是否需要补写
4. **批次 A2 检查点结论（CP1 / CP2）**：4 项（provider / 8 字段 / AuthProvider / pipeline_stages）是否各有且仅有 1 个实现；未完成项与降级登记（→ docs/release-notes/v1.1.0.md）
5. 需要用户裁决的问题清单
```

### 14.2 批次 C：接口补齐 + 前端关 Mock（Craft 模式）

```Plain Text
进入 Sprint 5 阶段十四·批次 C：接口补齐 + 前端关 Mock。

【本步目标】
1. GET /api/v1/documents：分页列表（真实数据，含 status/storage_key）
2. GET /api/v1/graph/overview + GET /api/v1/graph/entities/{id}：全局图谱与实体详情
3. 以上全部契约先行：先改 openapi.yaml → gen:api → 实现 → 契约零漂移 CI 绿
4. 前端关 Mock：documents 列表、graph 全局/实体详情改为真实接口（对齐既有 USE_MOCK 双轨机制）

【验收（对齐 docs/v1.1.0-demo-mvp-plan.md §4.3，完整清单以计划文档为准）】
- 前端 documents 页显示真实列表，无假数 1248
- graph 页显示真实图谱与实体详情
- GET /documents 与 graph 两条新路径已登记进 CONTRACT_COVERED_PATTERNS
- pytest + CI 4 job 全绿

【约束】
- 不执行 git commit；每步贴 diff 审查
```

### 14.3 Sprint 5 收尾验收

```PowerShell
cd d:/AIProject/GraphRAG-Agent

# 后端
cd backend
uv run pytest -q              # 期望全绿（增量后数量 ≥ 110）
uv run ruff check .           # 期望 All checks passed

# 前端
cd ../frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run gen:api           # 幂等，无 diff
npm.cmd run build

# 端到端（演示点验证）
# 终端 1: uv run uvicorn app.main:app --reload --port 8000
# 终端 2: npm.cmd run dev
# 浏览器走查：上传真实 PDF → 状态流转到 completed → 无人工干预，graph 页自动长出新实体，kg_version 可见
# 核对 storage_key 非 NULL：GET /api/v1/documents/{id}

# 关 Mock 硬门槛（v2.1 新增）：NEXT_PUBLIC_USE_MOCK=false 下 documents / graph 页零假数据（不再出现 1248）
# 预留字段合规（v2.1 新增）：uv run python scripts/export_openapi.py --check 无 diff
# provider 可切（v2.1 新增）：改 settings.llm_provider / parser_provider 后主链路仍通，无裸 deepseek_ 硬编码

# 预留字段双向判据（v2.2 新增）：documents 表 8 个预留列存在且均 nullable
#   （--check 只证明"未进契约"，不能证明"已建列"——只加 3 个字段照样能过旧验收）
# 接缝边界（v2.2 新增）：AuthProvider 实现类仅 LocalAuthProvider（无登记外实现）；pipeline_stages 可启停单阶段（如仅关 document.extract）
# 接缝门禁（v2.3）：uv run python scripts/check_seams.py 无 ERROR——上面几条的机械执行器（已接入 CI backend job）
#   注意：本 Sprint 用默认档（接缝 5/6/7/8 未到期记 WARN，不阻塞）；--strict 是 v1.4.0 完成点的口径
# 配置消费者（v2.2 新增）：本 Sprint 新增的 settings.* 每项都能指出读取它的代码行
```

收尾三件套（对齐既有惯例）：

```PowerShell
git push
# 临时 PR 验证 CI 绿 → 关闭
git checkout main && git pull
git merge --no-ff feature/sprint-5 -m "merge: sprint 5 done (v1.1.0)"
git push origin main
# main CI 绿后：
git tag -a v1.1.0 -m "Sprint 5 done: real parsing + online KG build"
git log --oneline -1 v1.1.0   # 核对指向 merge commit
git push origin v1.1.0
```

避坑提示：

- MinerU 云 API 不稳：走降级预案（手工放置解析产物，批次 B 照常），但必须在 `docs/release-notes/v1.1.0.md` 登记降级事实
- 版本号统一三处（pyproject / uv lock / package.json + lock），对齐阶段十三 13.7 规则
- 新建 `docs/release-notes/v1.1.0.md`（七节格式对齐 v1.0.0）

---

# 七、Sprint 6：引用溯源（v1.2.0）

## 阶段十五：Chunk 证据节点 + 引用回查 + 前端溯源交互

### 15.0 阶段定位与原则

目标：让每个答案论断可回溯到原文。**关键认知：后端校验逻辑零改动复用**——`agents.py` 的引用前缀校验（`chunk-`/`doc-`）与拒答唯一出口已存在并在运行，当前因为图谱里没有 chunk 证据节点所以覆盖率恒 0。本 Sprint 的本质是**给数据端补上证据节点**，不是写新校验。约 1.5 周，分支 `feature/sprint-6`。

**硬时间盒（本 Sprint 特有纪律）**：

- 第 3 天做 go/no-go 判定：chunk 级引用跑不通 → 立即降级为**文档级引用**（`doc-` 前缀路径已支持），演示故事不断
- 时间盒内禁止修 LLM 引用质量问题——长尾留给 v1.5，演示用受控问题集

批次划分：

- **批次 A**：建图时同步写 `:Chunk` 节点（原文片段 + 文档内位置）；实体/关系关联支撑 chunk
- **批次 B**：子图注入携带 chunk 文本；LLM 引用 `chunk-` 前缀通过既有校验
- **批次 C**：前端 evidence-panel 引用点击 → 跳转原文高亮（前端唯一净新增交互）

### 15.1 完整提示词（Plan 模式盘点）

```Plain Text
进入 Sprint 6 阶段十五的现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 基线：tag v1.1.0（真解析 + 在线建图已通）
- 目标：chunk 级引用溯源，F3（引用覆盖率 100%）在受控问题集上首次达标
- 关键事实：agents.py 引用前缀校验与拒答出口已存在（见 F3 注释），本 Sprint 补数据端
- 详细计划：docs/v1.1.0-demo-mvp-plan.md §5

【本步目标（全部贴证据）】
1. :Chunk 节点设计：属性（chunk_id 前缀规则、原文、文档内位置）、与 :Entity/:KgVersion 的关系边
2. LangExtract 产物映射：langextract 的原文定位（char_interval）如何映射成 chunk 位置？
3. 子图注入改造：GraphService 查询如何携带 chunk 文本？AgentService prompt 注入格式怎么变？
4. 前端溯源交互：evidence-panel 点击 → 原文高亮的数据链路（契约是否需要新增字段）
5. 受控问题集设计：演示口径 10~15 问的选取标准
6. 降级预案触发条件：什么信号出现就切文档级引用？

【约束】
- 只读；不改 agents.py 既有校验逻辑；中文回答

【完成后输出】
1. :Chunk 数据模型
2. 抽取产物→chunk 映射方案
3. prompt 注入格式变更
4. 契约变更清单（若有）
5. 受控问题集初稿
6. go/no-go 判定标准
```

### 15.2 落改与验收

裁决要点（默认）：`:Chunk` 挂在 `:Document` 下、`SUPPORTS` 边连实体；契约新增字段先改 openapi.yaml；问题集 12 问固定进 `docs/` 或 `tests/` 资产。

Sprint 收尾验收：

```PowerShell
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest -q               # 全绿
cd ../frontend
npm.cmd run gen:api && npm.cmd run typecheck && npm.cmd run build

# 端到端（演示点验证）
# 1. 上传演示 PDF，问受控问题集 12 问
# 2. 期望：全部非拒答，每问引用覆盖率 100%，引用标注为 chunk- 前缀
# 3. 点击引用标注 → 跳转原文片段并高亮
# 4. 问一个图谱无支撑的问题 → 期望 refused=true（拒答兜底仍有效）
# 5. :Chunk 节点带 acl_scope 属性（值可为空，但字段必须存在）
# 6. 关 Mock 硬门槛（v2.1 新增）：qa 页溯源交互走真实链路，演示剧本第 4 步零假数据（会话列表 Mock 豁免）
```

收尾三件套：同 Sprint 5，tag 换 `v1.2.0`，message 用 `Sprint 6 done: chunk-level citation (F3 met on controlled set)`。

避坑提示：

- 如果走降级（文档级引用），release notes 必须写明"chunk 级为 v1.5 议题"
- 不要在时间盒内调 LLM prompt 追引用质量——先降级，后复盘

---

# 八、Sprint 7：M4 疑点清单最小版（v1.3.0）

## 阶段十六：同法人/同地址算法 + 疑点接口 + 疑点页

### 16.0 阶段定位与原则

目标：交付 PRD 核心 M4 的最小闭环——**只做 1 类算法**："同一法人 / 同一注册地址跨公司"（规则型）。约 2 周（v2.1：+0.5 周，容纳批次 D 事件出口与第 8 接缝），分支 `feature/sprint-7`。

选型理由（已裁决，勿改）：数据现成（图谱已有跨公司实体）、Cypher 两跳遍历即可、演示冲击力强（审计师一眼就懂）；资金往来类需要新抽取字段（等于给 M1/M2 加需求），推迟 v1.5。

批次划分：

- **批次 A**：图谱补 `:Subject`（法人）/ `:Address` 节点（LangExtract 产物映射）+ Cypher 两跳规则算法
- **批次 B**：`affiliation_cases` 表（疑点+状态+证据引用）+ `GET /api/v1/affiliation/suspects` 接口（契约先行）+ `external_refs` 表（外来实体 ID ↔ 图谱实体 ID，只建表不做对接）+ **第 8 接缝「外部数据导入」**（`app/services/external_data/` 收口 + 导入文件 schema + 手工导入 CLI，不建表）
- **批次 C**：前端疑点清单页（复用 documents 表格组件）+ 每条疑点带证据链引用（复用 Sprint 6 溯源交互）
- **批次 D（v2.1 新增，由 Sprint 5 移入）**：`domain_events` 表 + `EventSink` 接口（仅 db/log 实现）；事件 `document.parsed` / `kg.updated` / `risk.suspect_created` / `qa.answered`；只落库不派发

### 16.1 完整提示词（Plan 模式盘点）

```Plain Text
进入 Sprint 7 阶段十六的现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 基线：tag v1.2.0（引用溯源已通）
- 目标：M4 最小版——同法人/同地址跨公司疑点识别闭环
- 详细计划：docs/v1.1.0-demo-mvp-plan.md §6

【本步目标（全部贴证据）】
1. :Subject/:Address 节点设计：从 LangExtract 抽取产物映射的规则、与 :Entity 的关系边
2. Cypher 算法：两跳遍历（公司→法人/地址→公司）的查询设计、去重与置信度规则
3. affiliation_cases 表结构：疑点字段、状态流转（open→confirmed/dismissed）、证据引用外键
4. 契约草案：GET /affiliation/suspects 的请求/响应体
5. 前端疑点页复用清单：documents 表格组件哪些可直接复用
6. 演示 PDF 体检：现有演示文档抽取出的法人/地址字段质量是否够（不达标→换文档，不修抽取）

【约束】
- 只读；中文回答

【完成后输出】
1. 数据模型 + 算法设计
2. 表结构 + 契约草案
3. 前端复用映射
4. 演示文档体检结论
5. 需要用户裁决的问题清单
```

### 16.2 落改与验收

裁决要点（默认）：算法跑在建图完成后（离线批处理入队，复用 tasks 框架）；疑点状态流转接口本 Sprint 只做读取（写接口 v1.5）；契约先行不变。

Sprint 收尾验收：

```PowerShell
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest -q               # 全绿
cd ../frontend
npm.cmd run gen:api && npm.cmd run typecheck && npm.cmd run build

# 端到端（演示点验证）
# 1. 用演示数据集跑疑点算法
# 2. 期望：疑点清单页 ≥3 条疑点，每条含涉及公司、疑点类型、可点击回原文的证据引用
# 3. 每条疑点关联的 kg_version 与当前 active 版本一致
# 4. domain_events 出现 risk.suspect_created；external_refs 表 local_id 可关联图谱实体
# 5. 关 Mock 硬门槛（v2.1 新增）：疑点清单页走真实接口（/affiliation/suspects 已登记 CONTRACT_COVERED_PATTERNS）
```

收尾三件套：tag `v1.3.0`，message 用 `Sprint 7 done: M4 minimal - shared legal-person/address detection`。

避坑提示：

- 演示 PDF 抽取质量不达标 → 换文档，严禁在 Sprint 内现场修抽取
- 算法结果依赖 E1/E2 数据债：确认 Sprint 5 已清基线，否则疑点全是噪声

---

# 九、Sprint 8：审计与演示打磨（v1.4.0 = Demo-MVP 完成点）

## 阶段十七：审计闭环 + 欠账清偿 + 演示彩排

### 17.0 阶段定位与原则

目标：补齐审计最小闭环、清偿治理欠账、固化演示资产。约 1 周，分支 `feature/sprint-8`。本 Sprint 收尾 = **Demo-MVP 达成**（黄金路径 7/7、零假数据）。

批次划分：

- **批次 A 审计闭环**：`qa_logs` + `audit_log` 两张表 + 2 个只读查询接口（按 trace_id / 按租户列表）+ 前端 audit 页关 Mock
- **批次 B 欠账顺手清**：slowapi 限流（H7，60 req/min/IP → 429）；agent/query 租户隔离 fail-open 收口（E 类）
- **批次 C 治理批次（半天，一次性结清三笔）**：
  1. spec 回填：`kg_nodes/kg_relations/token_usage` 三字段 + `GraphEdge.type` 枚举扩展回写 M2/M3 spec 与 PRD §6.1
  2. PRD 状态修正：`docs/03-prd.md` 状态行改为"Demo-MVP（v1.4.0）已交付，MVP 1.0 完整深度未完成"
  3. 新增铁律进 `CODEBUDDY.md`：**契约变更必须同步回写对应 spec**（堵住无声漂移）
- **批次 D 演示打磨**：种子数据集固化；演示彩排脚本（按计划文档 §3.1 六步剧本走查）；settings 页处置（隐藏路由或加"演示环境"标注）

- **批次 E 集成接缝收口（v2.1 新增）**：`ExportSink` 接口 + JSON/CSV 实现（`backend/app/services/export/`）；`settings.log_export` 可观测开关占位；按 `docs/adr/0004-integration-seams.md` 核对 8 接缝落地情况并补写"未来如何扩展"实施记录

### 17.1 完整提示词（Plan 模式盘点）

```Plain Text
进入 Sprint 8 阶段十七的现状盘点（只读分析，不改代码，不落盘）。

【当前背景】
- 基线：tag v1.3.0（M4 疑点清单已通）
- 目标：Demo-MVP 收官——审计闭环 + 欠账清偿 + 演示打磨
- 详细计划：docs/v1.1.0-demo-mvp-plan.md §7

【本步目标（全部贴证据）】
1. audit_log/qa_logs 表设计：事件粒度、trace_id 关联、写入点梳理（上传/建图/问答/疑点各环节 ≥7 条的达成路径）
2. 只读接口契约草案：按 trace_id 查 / 按租户分页列表
3. slowapi 接入点：中间件位置、限流键（IP）、429 错误体是否对齐 H3 统一错误格式
4. fail-open 现状：agent/query 租户隔离的收口方案（最小改动）
5. spec 回填清单：kg_nodes 三字段 + GraphEdge.type 枚举在 M2/M3 spec 与 PRD §6.1 的落点
6. PRD 状态行现状与目标措辞
7. CODEBUDDY.md 新铁律的落点章节（注意：**预留字段规则已于 Sprint 5 动工前提前落地**，本批只做核对）
8. 演示彩排脚本骨架：六步剧本 × 每步的前置条件与验证点
9. 集成接缝收口清单（批次 E，v2.1 新增）：按 docs/adr/0004-integration-seams.md 核对 8 接缝落地情况；ExportSink 收口点；settings.log_export 开关占位

【约束】
- 只读；中文回答

【完成后输出】
1. 表结构 + 接口契约草案
2. 限流方案
3. fail-open 收口方案
4. spec 回填 diff 预览
5. 彩排脚本骨架
6. 需要用户裁决的问题清单
```

### 17.2 Sprint 8 收尾验收（= Demo-MVP 总验收）

```PowerShell
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest -q               # 全绿
uv run ruff check .
cd ../frontend
npm.cmd run lint && npm.cmd run typecheck && npm.cmd run gen:api && npm.cmd run build

# 端到端（Demo-MVP 总走查，对齐 PRD §5 黄金路径 7 步）
# 1. 上传 2 份演示 PDF → task_id → 状态轮询到 completed
# 2. 自动建图：Neo4j 新 kg_version + PG kg_versions 行
# 3. 疑点算法产出 ≥3 条，每条引用可回原文
# 4. 受控问题集 12 问：引用覆盖率 100%，无拒答误伤
# 5. 审计页：全程同一 trace_id ≥7 条记录可见
# 6. 限流：ab/hr 压到 >60 req/min → 期望 429
# 7. 全程无一处 Mock 数据（settings 豁免）

# 8. 集成接缝（v2.1 新增）：8 个接缝全部落地；export_openapi.py --check 与 npm run gen:api 均无 diff
# 9. 关 Mock 硬门槛（v2.1 新增）：全站 NEXT_PUBLIC_USE_MOCK=false 走查通过（settings 豁免）

# 治理核对
# git log 可见三笔欠账偿还的独立 commit（spec 回填 / PRD 状态 / CODEBUDDY 铁律）
# docs/adr/0004-integration-seams.md 已定稿，含各接缝"未来如何扩展"
```

收尾三件套：tag `v1.4.0`，message 用 `Sprint 8 done: Demo-MVP complete (golden path 7/7, zero mock)`。

### 17.3 Demo-MVP 达成声明（release notes 必含）

`docs/release-notes/v1.4.0.md` 除七节格式外，必须包含：

1. **达成声明**：黄金路径 7/7 通过的证据（走查记录）
2. **降级事实**（若有）：chunk 级引用 / MinerU 接入的降级情况如实登记
3. **已知限制**：v1.5+ 推迟清单（对齐计划文档 §10），明确 RBAC / RLS / Agent Tool 循环 / C1~C3 实验 / E2 Prompt 重设计 / 图谱时效边未做；**企业系统集成为"只预留零集成"**（ADR-0004）

---

## 附：Sprint 5~8 每步教什么

- Sprint 5 教"预研转正"：MVP 目录的验证代码如何变成主链路服务（映射表驱动，不重写）
- Sprint 6 教"数据端补齐"：校验逻辑已存在时，先补数据而不是改校验；时间盒 + 降级的执行纪律
- Sprint 7 教"最小算法选型"：规则型先行（数据现成、可解释），统计型推迟；范围蔓延的抵抗力
- Sprint 8 教"治理收账"：spec 回填、PRD 状态修正、新铁律——增量交付如何不留无声漂移

## 附：Sprint 5~8 陷阱速查

| 陷阱 | 对策 |
|---|---|
| 把预研代码从零重写 | 一律先出"预研→目标"映射表，逐文件对照转正 |
| 在线建图破坏 ADR-0002 语义 | kg_writer 必须复用 KgVersion 状态机，契约测试兜底 |
| 契约改了 spec 没回填 | Sprint 8 批次 C 一次性结清 + CODEBUDDY 新铁律（此后每次都同步） |
| 时间盒内修 LLM 引用质量 | 第 3 天 go/no-go，降级文档级引用，复盘留给 v1.5 |
| 演示 PDF 抽取质量差现场修 | 换文档，抽取修复是 v1.5 议题 |
| 版本号三处不一致 | 对齐阶段十三 13.7：pyproject + uv lock / package.json + lock 同步 |
| 降级不登记 | release notes 如实写，严禁伪装成完整实现 |
| 预留字段误入契约 | nullable 且不进契约（根 `CODEBUDDY.md` §功能预留原则）；`export_openapi.py --check` + `npm run gen:api` 无 diff 兜底 |
| 接缝预留做成过度设计 | 只做三件便宜事；Sprint 5 批次 A2 净增硬顶 2.5 天；不做插件加载 / 连接器框架 / stub |

