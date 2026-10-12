# Tasks: P6-V6 —— 拆掉 CI 上的 flaky 定时炸弹（`pg_terminate_backend` 权限竞态）

> 使用说明：本文件是**批次级**任务拆解与勾选。**勾选 ≠ 通过**，须有实测证据，
> 且与同目录 `integration-log.md` 的实测结论对账。
> 停机条件见 [`proposal.md`](./proposal.md) §6；出口判据 K1~K6 见 §5。

## 1. 契约更新

- [x] **N/A** —— 本批不动 `contracts/openapi.yaml`（纯测试基础设施修复）

## 2. 后端实现（backend/）

- [x] **V6-a 查证**：在可复现条件下把 `pg_stat_activity` 的**实际行**打出来
      （至少 `pid` / `backend_type` / `usename` / `application_name` / `state` / `query`），
      指名"谁以 superuser 挂在那个库上"
      ⇒ **抓到 `(1347, 'autovacuum worker', NULL, '', 'active', 'autovacuum: VACUUM ANALYZE public.churn')`**
- [x] 记录复现条件（跑哪条命令、与哪个用例相邻、第几次出现），写进 integration-log
      ⇒ 复现法：本地把 autovacuum 限速（`cost_delay=100ms` / `cost_limit=1`）后造
      3000 行再删，worker 即被钉在临时库上（见日志 §1.3）
- [x] **V6-b 修** `backend/tests/pg_scratch.py::drop_database()`（只改这一段，
      不许顺带重构同文件其它函数）
      ⇒ 只踢 `client backend` + 同角色 + 排除自己；其余轮询等待；helper 均为**嵌套**函数
- [x] 若为「跳过杀不掉的连接」方案：**必须同时**保留"删库失败要响"的明确报错路径
      ⇒ `RuntimeError` 列出残留连接；`DROP` 仍失败也一并转换，**不静默**

## 3. 测试

- [x] 新增**反向守卫**：造一个"存在杀不掉的连接"的场景 ⇒ 断言**报错**（不是静默通过）
      ⇒ `tests/test_pg_scratch_drop.py::test_drop_database_raises_instead_of_silently_leaving_db`
      （用 `app_rls` 占库，与 CI 同构且**必现**，不必靠等 flaky）
- [x] 本机 `test_migration_seeds_preset_roles_and_is_replayable` **连跑 ≥ 5 次**全过
      ⇒ **6/6 全过**
- [x] 本机与迁移测试（`tests/test_migrations_baseline.py`）相邻跑，确认无顺序耦合回归
      ⇒ 已含在全量 `pytest tests -q`（1251 passed / 43 skipped）内

## 4. 验证

- [x] `ruff check .` + `ruff format --check .`（**全量**，不是只跑改动文件）
      ⇒ `All checks passed!` / `294 files already formatted`
- [x] `pytest tests -q` 全量**不降**（1249 passed / 43 skipped）
      ⇒ **1251 passed / 43 skipped**（+2 = 本批新增 2 条守卫）
- [x] `check_seams.py` ⇒ OK 12 / ERROR 0 / WARN 0
- [x] `check_startup_readiness.py --self-test` ⇒ 7 条全过
- [x] CI 全量 run **四项 success**（远程验到，不是只看本地）
      ⇒ run **`38201283243`**（head `1d87a0f`）：1287 passed / 7 skipped

## 5. 收尾

- [x] 回登 `changes/P6-V6/integration-log.md`（**实测证据**：`pg_stat_activity` 真实行、
      连跑次数、CI run id）
- [x] 同步删掉 / 更正 P6-V4 提示词里那条「已知 flaky」（修掉之后它不再成立）
      ⇒ `changes/P6-V4/new-session-prompt.md` §11 第 4 条已改写为"已修掉，再红就是真失败"
- [x] 提交推送（**后端 / 架构师 / changes 分段**，跨侧不混提交）
      ⇒ `1d87a0f`（backend）+ `49d8c63`（changes）
- [x] 落成下一批提示词 `changes/P6-V6/new-session-prompt.md`
      （P6-V5：C3 真值 + TBD-7 裁决包；坐标表已逐条实读复核，
      并补上本批实测发现的 `cost_metrics` 脏数据坑）
