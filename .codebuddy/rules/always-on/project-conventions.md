# 项目常驻约定（always-on）

本规则始终生效，适用于所有开发任务。完整规则以根目录 `CODEBUDDY.md` 为准，本文件为其日常编码相关要点的浓缩。

## 角色与目录边界
- 前端工作只改 `frontend/`，后端工作只改 `backend/`，规格与契约工作由架构师角色处理 `specs/`、`contracts/`。
- 发现前后端不匹配时：停止开发、报告用户、输出"接口对齐清单"，严禁擅自补全另一端逻辑。

## 接口契约
- 任何接口字段变更，先更新 `contracts/openapi.yaml`，再同步前端 TS 类型 / Mock 与后端 Pydantic 模型。
- 前端类型通过 `npm run gen:api` 从契约生成，禁止手写偏离契约的类型。

## 功能预留与接缝纪律（最易越界，必须遵守）
- **预留字段一律 nullable 且不进 API 契约**：为未来企业集成预留的 DB 字段（`source_type` / `acl_scope` / `content_hash` / `external_refs` 等）**只落库、不进 `contracts/openapi.yaml`**；判定口径 = `uv run python scripts/export_openapi.py --check` 无 diff。
- **预留必须有登记**：新增预留字段 / 表 / 接口实现，必须同步登记到 `docs/adr/0004-integration-seams.md`（接缝清单 + 用途 + 启用条件）。**禁止无登记的"顺手预留"**。
- **接口实现集合 = ADR-0004 §2.1 登记集合（不多不少）**：多一个实现即越界，少一个即少做。新增 `settings.*` 配置项必须能指出读取它的代码行，**无消费者的配置不得提交**。
- **机械校验**：`uv run python scripts/check_seams.py`（Sprint 收尾用 `--strict`）。新增实现时**先扩写 ADR-0004 §2.1 登记行、再改门禁**，漏改任一侧 CI 必红。
- **禁止为未来系统写 stub**：无法确认的集成一律"登记 + 留空位"，不写伪实现。

## SDD 变更流程（落点已定，勿用 OpenSpec CLI）
- **落点**：`changes/Sprint<N>.<M>/`，含 `proposal.md` + `tasks.md`（+ 有架构决策时 `design.md`）+ `integration-log.md`；模板见 `specs/_template/`。
- **归档**：Sprint 收尾时 `git mv` 到 `changes/archive/<日期>-Sprint<N>.<M>/`（只归档 `.md` / `.py`）。
- **禁止**：本项目**不启用 OpenSpec CLI**（决议 O-1）——**不得执行 `openspec init` / `openspec new change`**，不得把变更写到 `openspec/changes/`。
- **纪律**：每个批次都走"先写 `proposal` → 再写 `tasks` → 再动代码"；`integration-log.md` 记录实测证据链。

## 环境与依赖
- 后端一律使用 uv（`uv sync` / `uv add`），禁止 conda、poetry、pipenv；`uv.lock` 必须提交。
- 环境配置通过 `APP_ENV` 切换，默认 `development`；新配置项必须同步补入 `.env.example`。
- 前端环境变量必须以 `NEXT_PUBLIC_` 开头，禁止硬编码 API Base URL。

## 日志与安全
- 后端日志统一 loguru + JSON 格式，请求必须携带 `trace_id` 贯穿调用链。
- 日志禁止输出密钥、Token、密码等敏感信息；异常统一返回 `{code, message, detail, trace_id}`。

## Prompt 管理
- LLM Prompt 只放根目录 `prompts/`，文件名带版本号（如 `kg_qa_v1.md`）；修改即新增版本，禁止原地覆盖。

## 提交与质量门禁
- Conventional Commits：`feat` / `fix` / `docs` / `chore` / `refactor` / `test`。
- 后端 Ruff（`uv run ruff check .` + `uv run ruff format --check .`），前端 ESLint（`npm run lint`）+ 类型检查（`npm run typecheck`）。
- **pre-commit hook 暂未启用（规划于 v1.1.0）**——**不要假设提交会自动跑检查**；提交前手工跑本地检查，推送后以 CI 全量门禁为最终裁决（`.github/workflows/ci.yml` 四 job：backend / frontend / contract / ci-summary）。

## 验收与"完成"口径
- **"完成"必须有判据**：任何声称完成的任务，必须能指出它对应 `docs/acceptance-traceability-matrix.md` 的哪一行（锚点 + 判据 + 验收人）。
- **Sprint 收尾门禁**（全绿才可 tag）：`uv run ruff check . && uv run ruff format --check .`、`uv run python scripts/check_seams.py --strict`、`uv run pytest -q`、`uv run python scripts/export_openapi.py --check`、`cd frontend && npm run lint && npm run typecheck && npm run gen:api`。
- **未达标不得静默通过**：按 F1–F5 走显式降级决议（落 release notes + 决策记录）。
- **打 tag 与 bump `settings.app_version` 是同一个动作**（不 bump，接缝门禁会永久停在 WARN 档）。
