# Tasks: Sprint5.1 — 存储抽象 + MinerU 转正（批次 A）

> **上游**：plan §4.2 批次 A / §4.3；规格 `specs/m1-async-ingest.md`。每项完成即验证并提交；证据链写同目录 `integration-log.md`。

## 0. 前置核实（动代码前）
- [ ] 读 `backend/app/storage/` 现状、上传链路（`POST /documents` service）、parsing 执行器现状与 `task_retry_multiplier` 声明处
- [ ] 读 `mineru_mvp/` 可复用代码与实测口径（`docs/mineru_cloud_api_spec.md` 以实测为准）
- [ ] 确认 `documents.storage_key` 列现状（DDL / ORM 模型）

## 1. 存储抽象层（接缝登记）
- [ ] `StorageBackend` 接口 + `LocalFSStorage` 实现（save / get / delete / 生成 storage_key），ADR-0004 §2.1 登记行扩写（先登记后改门禁）
- [ ] `config.py` 存储配置项（如 `STORAGE_BACKEND=local_fs`、根目录），**每项指出消费代码行**
- [ ] 单测：落盘 / 读取 / 删除 / 路径注入防护

## 2. 上传真实落盘
- [ ] `POST /documents` 经 `StorageBackend.save` 真实写盘，completed 时回填 `storage_key` 非 NULL
- [ ] 集成测试：上传 → 文件存在于磁盘 → `storage_key` 非 NULL → 状态流转 pending→processing→completed

## 3. parsing 真实执行 MinerU
- [ ] 复用 `mineru_mvp/` 接入 parsing 执行器：PDF → 结构化结果（页码 + 文本片段）落库
- [ ] MinerU 云 API 失败路径：按 plan §4.4-1 降级预案就位（失败→failed 状态 + 重试，不静默）
- [ ] 集成测试（真实调用一次小 PDF；API 不可用时按降级预案登记事实）

## 4. 欠账顺手修（B1 / B4）
- [ ] B1 `retry_count`：确认计数真实递增并有测试
- [ ] B4 `task_retry_multiplier`：任务退避路径真实读取该配置，或删除配置（二选一，登记进 integration-log）

## 5. 验证与收尾
- [ ] `uv run ruff check . && uv run ruff format --check .` 全绿
- [ ] `uv run pytest -q` 增量全绿
- [ ] `uv run python scripts/export_openapi.py --check` 无 diff（预留字段未进契约）
- [ ] `uv run python scripts/check_seams.py` 无 ERROR（默认档）
- [ ] `integration-log.md` 记录证据链（命令 + 输出摘要 + 关键发现 + 未触碰项）
