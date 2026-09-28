# Sprint 9.7 —— Alembic 迁移基线（D-2 前置 / CP-D0 第一半）

> 登记日期：2026-09-28。动机：`deployment-spec.md` **D-2**——`create_all`
> 只建新表不 ALTER 旧表，客户现场升级后旧库缺列、运行时才炸；`main.py:33`
> 「Sprint 3 接入 Alembic 后移除」的注释至今未兑现。S9.6 收尾后按建议顺序
> 先做与业务解耦的这项。

## 1. 方案

- `alembic` 进**主依赖**（生产现场要跑 `alembic upgrade head`，不能只进 dev）；
- `backend/alembic.ini` + `backend/migrations/`（env.py 从
  `app.core.config.get_settings().database_url` 取连接串、
  `app.db.models.Base.metadata` 作 target，`compare_type=True`）；
- **基线迁移对空库 autogenerate**（dev.db 已有表会生成空迁移，必须临时换
  空库 URL）——产出「从零建出全部表」的等价 DDL，逐字审阅后入库；
- **启动行为不动**：`init_db()`（create_all）保留为 dev / 测试兜底——
  等价性由新测试机械钉死，不搞「启动时静默跑迁移」的双路径；
- **等价性测试**（验收核心）：对临时空 SQLite 跑 `upgrade head`，
  与 `Base.metadata`（create_all 的真源）比对表集合 + 列集合 ⇒
  **今后加表 / 加列忘写迁移，CI 必红**。

## 2. 批次

| 批次 | 内容 | 验收 |
|---|---|---|
| H1 | 依赖 + alembic.ini + env.py + 基线迁移（空库 autogenerate） | 空库 `upgrade head` 成功；`downgrade base` 可回 |
| H2 | 等价性测试 + 注释兑现（models/session/main）+ 文档同步 | pytest 全绿；deployment-spec D-2 状态更新 |

## 3. 明确不做

- **compose / Dockerfile 不做**（属 D-1 / S11，CP-D0 第二半）；
- **不改启动行为**（不在 lifespan 里跑迁移——多实例并发风险，升级流程按
  deployment-spec §7.2 由运维手动执行）；
- **不做 PG 上的实测**（本机无 PG 容器；迁移 DDL 以 SQLite 实测 + 人工审阅为准，
  PG 实测留 compose 就绪后的 D-1 批次）。
