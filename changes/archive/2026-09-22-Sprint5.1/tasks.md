# Tasks: Sprint5.1 — 存储抽象 + MinerU 转正（批次 A）

> **上游**：plan §4.2 批次 A / §4.3；规格 `specs/m1-async-ingest.md`。每项完成即验证并提交；证据链写同目录 `integration-log.md`。

## 0. 前置核实（动代码前）
- [x] 读 `backend/app/storage/` 现状、上传链路（`POST /documents` service）、parsing 执行器现状与 `task_retry_multiplier` 声明处
- [x] 读 `mineru_mvp/` 可复用代码与实测口径（`docs/mineru_cloud_api_spec.md` 以实测为准）
- [x] 确认 `documents.storage_key` 列现状（DDL / ORM 模型）

## 1. 存储抽象层（接缝登记）
- [x] `StorageBackend` 接口 + `LocalFSStorage` 实现（save / get / delete / 生成 storage_key）——**接缝登记结论：存储抽象不属 ADR-0004 八接缝，无需扩写 §2.1**（详见 integration-log 决策 1）
- [x] `config.py` 存储配置项（`storage_root`，只加有消费者的配置，未加 S3 开关）
- [x] 单测：落盘 / 读取 / 删除 / 路径注入防护（test_storage.py，10 例）

## 2. 上传真实落盘
- [x] `POST /documents` 经 `StorageBackend.put` 真实写盘，completed 时回填 `storage_key` 非 NULL
- [x] 集成测试：上传 → 文件存在于磁盘 → `storage_key` 非 NULL → 状态流转 pending→processing→completed

## 3. parsing 真实执行 MinerU
- [x] 复用 `mineru_mvp/` 接入 parsing 执行器：PDF → 结构化结果（页码 + 文本片段）落库（产物落存储层 `{org}/{doc}/parse/`）
- [x] MinerU 云 API 失败路径：按 plan §4.4-1 降级预案就位（`MineruApiError`/`httpx` 错误入 tenacity 可重试集合 → 用尽即 failed，不静默）
- [x] 集成测试（MockTransport 全流程 + executor 端到端；**真实云调用待用户注入 MINERU_TOKEN 后手工验收**，已在 integration-log 登记降级事实）

## 4. 欠账顺手修（B1 / B4）
- [x] B1 `retry_count`：重试回调 + completed 分支回写 DB，测试断言 retry_count == 2（3 次尝试）
- [x] B4 `task_retry_multiplier`：`wait_exponential(exp_base=task_retry_multiplier)` 真实读取（保留配置——Agent 路径已有消费者）

## 5. 验证与收尾
- [x] `uv run ruff check . && uv run ruff format --check .` 全绿（2026-09-21 实测通过）
- [x] `uv run pytest -q` 增量全绿（156 passed，基线 134 → 增 22）
- [x] `uv run python scripts/export_openapi.py --check` 无 diff（预留字段未进契约）
- [x] `uv run python scripts/check_seams.py` 无 ERROR（默认档：ERROR 0 / WARN 12 均为 A2+ 未到期项）
- [x] `integration-log.md` 记录证据链（命令 + 输出摘要 + 关键发现 + 未触碰项）
