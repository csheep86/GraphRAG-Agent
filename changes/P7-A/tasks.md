# P7-A · 任务清单

> **性质**：盘点批次。任务顺序即执行顺序，**做完一条勾一条**。

## T1 · 机器基准

- [x] 跑 `check_startup_readiness.py` ⇒ 取三档结论（15 OK / 0 部分 / 2 挂起 / 地雷 1 项）
- [x] 跑 `check_seams.py` ⇒ ERROR 0 / WARN 0 / OK 10
- [x] 确认工作区干净（`HEAD` = `e4f29d91`，无未提交改动）

## T2 · 实跑环境重建（**无 PG 就谈不上 T1 / T2 的实测**）

- [x] 起 `postgres:16-alpine` 容器 + 建 `graphrag_test` 库
- [x] 补 `public` schema 授权给 `app_owner` / `app_rls`（PG 15+ 默认不授予）
- [x] `alembic upgrade head`（10 个迁移全跑到 head，含 RLS 策略迁移）
- [x] `init_rls_roles.py` ⇒ 14 张租户表 ENABLE + FORCE + 策略
- [x] 起真 `neo4j:5.26-community`（既有容器 `graphrag-neo4j`，口令 `graphragdev`）
- [x] 全量 pytest **有图**：`930 passed / 3 skipped / 3 xfailed`
- [x] 全量 pytest **无图**：`923 passed / 10 skipped / 3 xfailed`（差值 7 ⇒ 量化图谱侧本地盲区）

## T3 · 逐条 G 落表

- [x] G-1 ~ G-26 全部落到「文件 + 行号 + 是否仍带 xfail + 档位」
- [x] G-13（作废）/ G-16（无机械判据）显式标注为不适用
- [x] 反向守卫 `test_g21_production_sqlite_guard_still_present` 单独确认仍绿

## T4 · T1 / T2 专项（ADR-0003 §4.1）

- [x] T1 四个对象（`documents` / `audit_log` / `qa_logs` / `storage_key`）定位齐全
- [x] T2 并发用例确认覆盖连接池复用（24 请求 / 8 并发）
- [x] 两者确认：`_require_postgres()` 在用例内（非 SQLite 可过）、**未标 `local_only`**、进 CI 必过

## T5 · 弱化形态与结构盲区

- [x] 拉全仓 `xfail` / `skipif` / `local_only` 标记，逐条归位
- [x] 登记 readiness 脚本的两个盲区（`skipif` 不计档、`local_only` 不计档）
- [x] 登记 G-11 条件 `xfail` 的性质（有旁立守卫 ⇒ **不构成缺口**，仅留说明）

## T6 · 回写需求基线

- [x] §2.2 G-10 状态：`🟡 骨架已就位` ⇒ `✅ 已生效`
- [x] §3.1 B6 / B11 行订正（P3-B 已补齐 / CI 已起 Neo4j）
- [x] §2.2 G-23 补「恒绿失效 ⇒ 转正无意义（R-9）」
- [x] §2.2 G-11 / G-25 补限定语（条件 xfail / skipif 本地跳过）
- [x] §5 各清单刷新为本次实测数字
- [x] §8 追加「2026-10-05 全量对账」记录段

## T7 · 优先级与排期调整

- [x] 给出剩余缺口的优先级排序（P0 / P1 / P2 / P3）
- [x] 据优先级**确认或调整**阶段 ②–⑤ 顺序，并把理由写进 `integration-log.md` §6

## T8 · 收尾门禁与提交

- [x] `pytest` passed 不减（仍 930）、`ruff check` / `ruff format --check` / `check_seams` /
      `export_openapi.py --check` / `check_session_drift` S1–S5 全绿
- [x] 收尾三问自答并写进日志
- [x] Conventional Commits 提交
