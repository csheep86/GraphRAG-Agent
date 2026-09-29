# Sprint 9.7 任务卡

- [x] **H1 Alembic 基线**（2026-09-28：`00f44b912817` 十表，upgrade/downgrade 往返实测通过）
  - `uv add alembic`（主依赖）✅
  - `alembic.ini` + `migrations/env.py`（settings 取 URL / Base.metadata / compare_type）✅
  - 空库 autogenerate 基线迁移，逐字审阅 ✅
  - 空库 `upgrade head` + `downgrade base` 实测 ✅
- [x] **H2 等价性测试 + 文档**（2026-09-28：pytest 508 passed）
  - `tests/test_migrations_baseline.py`：upgrade head 后 schema ≡ Base.metadata ✅
  - models.py / session.py / main.py 注释兑现（不再写「无 Alembic」）✅
  - deployment-spec D-2 / sprint-calendar S9.7 登记 ✅

## 纪律提醒

- 启动行为**不动**：create_all 仅 dev 兜底，生产升级走 §7.2 手动 `alembic upgrade head`；
- 基线迁移文件**人工审阅**后才提交（autogenerate 不盲信）；
- 不引入 compose / Dockerfile（D-1 范围）。
