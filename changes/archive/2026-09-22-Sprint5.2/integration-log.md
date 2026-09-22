# Integration Log: Sprint5.2 — 集成接缝收口（批次 A2）

> 上游：plan §4.2 批次 A2 / §8.1–§8.2；ADR-0004 §2.1/§3。
> 分支：`feature/sprint-5`；上游批次：Sprint5.1（存储抽象 + MinerU 转正，`0eaf943`）。

## 1. 变更清单

| 接缝 | 落点 | 说明 |
|---|---|---|
| 3 模型 | `app/services/providers/llm.py` | `build_chat_model()` 工厂：`llm_provider` 唯一消费点，唯一档位 `openai_compatible`；未知档位抛 `LlmProviderError`（不静默）。「只多一层」：仅构造参数收敛，无消息转换/会话管理 |
| 3 模型 | `app/tasks/registry.py` `_do_parse` | `parser_provider` 唯一消费点；非 `mineru_cloud` 档位抛 `MineruApiError`（可重试集合，重试用尽后 failed 落库） |
| 1 身份 | `app/services/auth/{base,local}.py` | `AuthProvider` 接口 + `LocalAuthProvider`（恰好 1 个实现，包装 `core.auth` 现有逻辑，校验语义零改动）；`deps.py` 认证依赖改经 `get_auth_provider()` 分发 |
| 2 数据接入 | `app/db/models.py` Document | 8 个预留字段（`source_type`/`source_ref`/`document_key`/`content_hash`/`source_version`/`acl_scope`/`acl_owner_ref`/`deleted_at`）全部 nullable、只落库、不进契约（ADR-0004 §2.2 逐字段一致） |
| 4 流水线 | `app/tasks/pipeline.py` | `resolve_pipeline_stages()`：`settings.pipeline_stages` 唯一消费点（启停 + 顺序）；`documents.py` 上传注册首阶段经 `first_pipeline_stage()`，全停时告警不抛错 |

## 2. 配置改名迁移说明（DEEPSEEK_* → LLM_*）

**破坏性变更（仅环境变量名）**：

| 旧（v1.0.0） | 新（v1.1.0） | 默认值 |
|---|---|---|
| `DEEPSEEK_API_KEY` | `LLM_API_KEY` | 空 |
| `DEEPSEEK_BASE_URL` | `LLM_BASE_URL` | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | `LLM_MODEL` | `deepseek-chat` |
| `DEEPSEEK_REQUEST_TIMEOUT_SECONDS` | `LLM_REQUEST_TIMEOUT_SECONDS` | 60 |
| —（新增） | `LLM_PROVIDER` | `openai_compatible` |
| —（新增） | `PARSER_PROVIDER` | `mineru_cloud` |
| —（新增） | `PIPELINE_STAGES` | 四阶段全启 |

**迁移动作**：本地 `.env` 按上表改名即可；值语义不变（`LLM_BASE_URL` 仍指向 DeepSeek）。`.env.example` 已同步。代码内全部消费点已切换（`agents.py` / `providers/llm.py` / `repro_agent_query.py`）；`routes/agent.py` 501 语义描述同步改为 `LLM_API_KEY`（传导至 openapi.yaml description，1 处文案 diff，无字段变化）。

**兼容性**：`Settings` 是 `extra="ignore"`，旧名 `DEEPSEEK_*` 在 `.env` 里残留**不会报错但也不会生效**——API key 会读空 → Agent 端点 501（显式失败，不静默降级），按提示改名即恢复。

## 3. dev.db 存量库重建说明

`documents` 表新增 8 列，SQLite 存量库（`backend/dev.db`）**无 ALTER 迁移**（项目尚未引入 Alembic，M1 阶段 dev 库可弃）：

```
删除 backend/dev.db → 下次启动 lifespan 自动 Base.metadata.create_all 重建
```

CI / 测试不受影响（conftest 每次用临时目录新建库）。生产 PG 迁移在引入 Alembic 时统一补（v1.1.0 内无生产部署）。

## 4. 验证证据（收尾门禁）

| 门禁 | 结果 | 时间 |
|---|---|---|
| `uv run ruff check .` + `format --check .` | ✅ 0 error，70 files formatted | 2026-09-21 |
| `uv run pytest -q` | ✅ **171 passed**（含新增 `test_seams_a2.py` 13 例：工厂档位/未知报错、AuthProvider 回归、pipeline 启停顺序、预留字段 nullable+默认 NULL） | 2026-09-21 |
| `uv run python scripts/export_openapi.py --check` | ✅ 无 diff（重新导出后复核通过；本次 diff 仅 1 处 description 文案） | 2026-09-21 |
| `uv run python scripts/check_seams.py` | ✅ **ERROR 0**；接缝 1/3/4 相关 WARN 全部清零；剩余 6 条 WARN 均为未到期项（接缝 5/6/7/8，required_from ≥ 1.3.0，合规保留） | 2026-09-21 |

### check_seams 关键 OK 项摘录

- 接缝 1 AuthProvider：实现集合 = `['LocalAuthProvider']`，无登记外实现；与 ADR-0004 §2.1 第 1 行一致
- 配置消费者：Settings 全部 36 个字段均有消费者代码行
- 预留字段双向判据：8 个字段齐全且可空，均未出现在契约中

## 5. 决策记录（按建议项采纳，无人值守协议）

| # | 决策点 | 采纳 | 依据 |
|---|---|---|---|
| D1 | `LocalAuthProvider.authenticate` 返回 `None` vs 抛 401 | 返回 `None`，401 由依赖层决定 | provider 不越权决定错误响应形态（ADR-0004 §2.1 第 1 行落点设计） |
| D2 | 未知 `parser_provider` 的错误分类 | `MineruApiError`（可重试集合），重试用尽后 failed 落 error_detail | 配置错误也走统一任务状态机，与 plan §4.4「显式失败不静默」一致 |
| D3 | 预留字段存量库迁移 | 不写 ALTER，dev.db 删除重建 | 项目无 Alembic；dev 库可弃（见 §3） |
| D4 | `build_chat_model` 的 `max_retries=0` | 重试收敛到调用方 tenacity | 避免双层重试放大等待时间（与 `agents.py` 既有策略一致） |
