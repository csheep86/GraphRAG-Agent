# Integration Log: Sprint5.1 批次 A（存储抽象 + MinerU 转正）

> 执行日期：2026-09-21 | 分支 `feature/sprint-5` | 上游 plan §4.2 批次 A / §4.3

## 变更清单

| 文件 | 变更 |
|---|---|
| `backend/app/storage/base.py` | 新增：`StorageBackend` 接口（put/get/delete/exists/size）+ `StorageKeyError` |
| `backend/app/storage/local_fs.py` | 新增：`LocalFSStorage`（路径注入防护 + org 前缀校验） |
| `backend/app/storage/__init__.py` | 重写：`build_storage_key`（保留）+ `build_parse_artifact_key` + `get_storage` 工厂 |
| `backend/app/services/parsing/{__init__,mineru}.py` | 新增：MinerU 异步客户端（申请链接→PUT→轮询→zip→md/content_list） |
| `backend/app/core/config.py` | 新增 8 个配置：`storage_root` + 7 个 `mineru_*`（均有消费者） |
| `backend/app/services/documents.py` | 上传真实落盘：put 先于 DB 写入（无幽灵行） |
| `backend/app/tasks/registry.py` | `_do_parse` 真实执行（PDF→MinerU→产物落存储层）；B1（retry_count 回写）；B4（exp_base 读 task_retry_multiplier）；completed 回填 storage_key |
| `backend/pyproject.toml` | httpx 由 dev 组提升为主依赖 |
| `backend/.env.example`、`.gitignore`、`tests/conftest.py` | 配置模板 / 忽略 storage 目录 / 测试隔离 STORAGE_ROOT |
| 测试 | 新增 `test_storage.py`（10 例）、`test_mineru_client.py`（6 例）；增补 `test_documents.py`（落盘 2 例）与 `test_document_parse_executor.py`（6 例） |

## 验证证据（2026-09-21）

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 63 files already formatted
uv run pytest -q              → 156 passed, 1 warning in 2.99s（基线 134 → 增 22）
uv run python scripts/export_openapi.py --check → [OK] 契约零漂移
uv run python scripts/check_seams.py             → ERROR 0 / WARN 12 / OK 5（通过）
```

WARN 12 均为**未到期**的批次 A2 / S7 / S8 项（AuthProvider、provider 抽象、预留字段、domain_events 等），非本批次欠账。

## 关键实现决策（含文档依据）

1. **存储抽象不是接缝**：`StorageBackend` 不进 ADR-0004 §2.1 登记集合（登记集合不多不少；存储抽象属 CODEBUDDY「存储规范」，S3 生产档由部署阶段替换实现）。S3 实现**未写 stub**（ADR-0004 §3 第 2 条）。
2. **storage_key 回填时点**：上传时即落盘文件（Starlette 临时文件随请求销毁，异步任务须能取回字节），DB 列按 M1 §4.1 在 completed 时回填；executor 按 `{org}/{doc}/{filename_hash}` 确定性重建键读取。
3. **put 先于 DB 写入**：put 失败无 DB 行（4xx）；DB 失败至多孤儿文件，优于「行存在但无文件」。
4. **非 PDF 跳过解析**：docx（S10）/ csv（S9）承接结构化解析，本批次照常推进 completed，日志显式登记（`document_parse_skipped_unsupported_parser`），不静默。
5. **MinerU 不做内层重试**：外层 executor 已有 tenacity 指数退避（M1 验收 4），双层重试放大等待；`MineruApiError` / `httpx.HTTPError` 加入可重试集合。
6. **文件名不外发**：MinerU `display_name = {doc_id}.pdf`（M5 §4.5 敏感纪律）。
7. **B4 修复口径**：`wait_exponential(multiplier=task_retry_initial_seconds, exp_base=task_retry_multiplier)`——配置从「声明存在无消费」变为退避路径真实读取（保留配置而非删除，因 Agent 路径已有消费者）。

## 降级与登记事实

- **MinerU 真实调用未在本机执行**（本地 `.env` 未配置 `MINERU_TOKEN`）：单测以 httpx.MockTransport 全流程覆盖（含 running→done 轮询、failed、超时、缺产物路径）；真实 PDF 云调用留待用户注入 token 后的手工验收（plan §4.4 降级预案 1 的精神：外部 API 不可用时以可复现单测 + 登记代替，链路不静默）。
- `uv.lock` 已随 `uv sync` 更新（httpx 主依赖化）。

## 未触碰项

`frontend/`、`contracts/openapi.yaml`（零漂移）、`prompts/`、`specs/`、ADR-0004（登记集合未扩写——见决策 1）、`app/api/` 路由层（无契约变更）。
