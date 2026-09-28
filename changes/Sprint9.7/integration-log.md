# Sprint 9.7 集成日志（证据链）

> 全部为 2026-09-28 真机实跑（Windows / SQLite；PG 实测留 S11 compose 就绪后）。

## 批次 H1：Alembic 基线

- `uv add "alembic>=1.13,<2.0"` → **主依赖**（生产现场要跑 `upgrade head`）；
  实装 alembic 1.x + mako 1.4.3。
- `alembic.ini`：URL 留空、由 `env.py` 从 `app.core.config` 取（避免双真源）；
  ini 保持 ASCII（configparser 在 Windows 按 locale 解码，中文注释会炸——已踩过并写注释）。
- `migrations/env.py`：`target_metadata = Base.metadata`、`compare_type=True`、
  自动挂 `backend/` 进 `sys.path`（测试可从任意 cwd 调）。
- 基线迁移 `00f44b912817`：**对空库** autogenerate（dev.db 已有表会生成空迁移，
  临时 `DATABASE_URL=sqlite:///./_alembic_empty.db`），生成后逐字审阅——
  十表（documents / kg_versions / affiliation_tasks / affiliation_suspicions /
  unaligned_subjects / audit_log / qa_logs / ontology_schemas / domain_events /
  external_refs），含 ADR-0004 登记的预留字段（只落库、不进契约）。
- 空库实测：`upgrade head` → `current == 00f44b912817 (head)` →
  `downgrade base` 清空 → 再 `upgrade head` 成功（可回滚）。

## 批次 H2：等价性测试 + 注释兑现

- `tests/test_migrations_baseline.py` 2 条全过：
  ① upgrade head 后表集合 + 逐表列集合 ≡ `Base.metadata`（**加表 / 加列忘写迁移必红**）；
  ② downgrade base 无残留表。
- `migrations/` 加入 ruff `extend-exclude`（autogenerate 产物人工审阅入库，不进 lint）。
- 注释兑现：`models.py`（「无 Alembic」→ 基线说明）/ `session.py init_db` /
  `main.py:33`（「Sprint 3 接入后移除」→ 启动行为不动的原因：不在 lifespan 跑迁移，
  多实例并发风险）。
- 全量门禁：pytest **508 passed**（506 → 508）；ruff check / format 通过。

## 明确不做（proposal §3）

- compose / Dockerfile（D-1 / S11）；不在 lifespan 跑迁移（双路径风险）；
- PG 实测（本机无 PG 容器，留 D-1 批次）。

## 复现命令

```bash
cd backend
uv run alembic upgrade head          # 对 DATABASE_URL 指向的库
uv run alembic downgrade base
uv run pytest tests/test_migrations_baseline.py -q
```
