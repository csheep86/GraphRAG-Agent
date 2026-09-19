# CODEBUDDY.md - GraphRAG-Agent 项目规则

## 角色隔离
- 处理 frontend/ 时，你是前端开发（A），只允许修改 frontend/。
- 处理 backend/ 时，你是后端开发（B），只允许修改 backend/。
- 处理 specs/ 和 contracts/ 时，你是架构师。

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
2. 提交前必须通过本地检查（后端 ruff check/format、前端 eslint/typecheck）；推送后以 CI 全量门禁（ruff/pytest/eslint/tsc/契约零漂移）为最终裁决。pre-commit hook 暂未启用，规划于 v1.1.0。

## Git 提交规范
使用 Conventional Commits：feat / fix / docs / chore / refactor / test
