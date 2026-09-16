# 项目常驻约定（always-on）

本规则始终生效，适用于所有开发任务。完整规则以根目录 `CODEBUDDY.md` 为准，本文件为其日常编码相关要点的浓缩。

## 角色与目录边界
- 前端工作只改 `frontend/`，后端工作只改 `backend/`，规格与契约工作由架构师角色处理 `specs/`、`contracts/`。
- 发现前后端不匹配时：停止开发、报告用户、输出"接口对齐清单"，严禁擅自补全另一端逻辑。

## 接口契约
- 任何接口字段变更，先更新 `contracts/openapi.yaml`，再同步前端 TS 类型 / Mock 与后端 Pydantic 模型。
- 前端类型通过 `npm run gen:api` 从契约生成，禁止手写偏离契约的类型。

## 环境与依赖
- 后端一律使用 uv（`uv sync` / `uv add`），禁止 conda、poetry、pipenv；`uv.lock` 必须提交。
- 环境配置通过 `APP_ENV` 切换，默认 `development`；新配置项必须同步补入 `.env.example`。
- 前端环境变量必须以 `NEXT_PUBLIC_` 开头，禁止硬编码 API Base URL。

## 日志与安全
- 后端日志统一 loguru + JSON 格式，请求必须携带 `trace_id` 贯穿调用链。
- 日志禁止输出密钥、Token、密码等敏感信息；异常统一返回 `{code, message, detail, trace_id}`。

## Prompt 管理
- LLM Prompt 只放根目录 `prompts/`，文件名带版本号（如 `kg_qa_v1.md`）；修改即新增版本，禁止原地覆盖。

## 提交规范
- Conventional Commits：`feat` / `fix` / `docs` / `chore` / `refactor` / `test`。
- 后端 Black + Ruff，前端 Prettier + ESLint，提交前过 pre-commit hook。
