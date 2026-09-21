# Tasks: Sprint5.2 — 集成接缝收口（批次 A2）

> **上游**：plan §4.2 批次 A2 / §8.1–§8.2；ADR-0004 §2.1/§3。CP 闸门：批次 A2 第 1 天末 `llm_provider` 抽象完成且"只多一层"；第 2.5 天末全项落位、`check_seams.py` 相关 WARN 清零。

## 1. Provider 抽象（接缝 3，1 天）
- [x] `config.py`：`deepseek_api_key/base_url/model/request_timeout_seconds` 改名 `llm_*`（中性化）+ 新增 `llm_provider` / `parser_provider`（默认 `openai_compatible` / `mineru_cloud`）
- [x] `app/services/providers/llm.py`：`build_chat_model()` 工厂（读 `llm_provider`，openai_compatible → ChatOpenAI(llm_*)）；agents.py 调用点切换
- [x] `registry.py`：`_do_parse` 读 `parser_provider` 分发 MinerU 客户端
- [x] `.env.example` 同步改名；测试与文档引用同步（`repro_agent_query.py` / `routes/agent.py` 描述）
- [x] 单测：工厂按 provider 返回；未知 provider 显式报错（不静默）

## 2. AuthProvider 收口（接缝 1，0.5 天）
- [x] `app/services/auth/base.py`：`AuthProvider` 接口（authenticate(token) / identity_from_headers）
- [x] `app/services/auth/local.py`：`LocalAuthProvider`（包装 `app/core/auth.py` 现有逻辑——**恰好 1 个实现**）
- [x] `deps.py` 认证依赖改经 provider；`core/auth.py` 降为被包装的工具函数（不删公共 API，避免大改）
- [x] 单测：dev token / dev header / 越权路径行为不变（回归）——`test_auth.py` 既有 6 例全数通过（Bearer 优先级用例即经 provider 路径）+ `test_seams_a2.py` 新增 4 例

## 3. documents 8 预留字段（接缝 2，0.5 天）
- [x] `models.py` Document 增 8 个 nullable 列（§8.2 清单）；**不进** Pydantic 响应 schema
- [x] `export_openapi.py --check` 无 diff（预留不进契约；重导出后复核通过）
- [x] 登记 ADR-0004 §2.1 第 2 行（已登记则核对字样）——第 2 行 + §2.2 逐字段一致，无需扩写
- [x] 测试：字段默认 NULL；dev.db 存量库需重建（登记 integration-log §3）

## 4. pipeline_stages（接缝 4，0.5 天）
- [x] `config.py`：`pipeline_stages`（默认四阶段全启，顺序 = parse → extract → kg.build → risk.detect）
- [x] `app/tasks/pipeline.py`：`resolve_pipeline_stages()`（按顺序过滤已登记执行体——启停+顺序唯一消费点）
- [x] `documents.py` 上传注册首阶段经该函数；未登记阶段自动跳过（批次 B 登记后即自动生效）
- [x] 单测：启停 / 顺序 / 未登记阶段跳过（4 例）

## 5. 验证与收尾
- [x] `uv run ruff check . && uv run ruff format --check .` 全绿（0 error，70 files）
- [x] `uv run pytest -q` 全绿（**171 passed**）
- [x] `uv run python scripts/export_openapi.py --check` 无 diff
- [x] `uv run python scripts/check_seams.py`：接缝 1/3/4 相关 WARN 全部清零（ERROR 0；剩余 6 条 WARN 均为未到期项 1.3.0/1.4.0）
- [x] `integration-log.md` 证据链 + 配置改名迁移说明（§2 DEEPSEEK_*→LLM_* 破坏性变更 + §3 dev.db 重建）
