# Tasks: P6-V6 —— 拆掉 CI 上的 flaky 定时炸弹（`pg_terminate_backend` 权限竞态）

> 使用说明：本文件是**批次级**任务拆解与勾选。**勾选 ≠ 通过**，须有实测证据，
> 且与同目录 `integration-log.md` 的实测结论对账。
> 停机条件见 [`proposal.md`](./proposal.md) §6；出口判据 K1~K6 见 §5。

## 1. 契约更新

- [ ] **N/A** —— 本批不动 `contracts/openapi.yaml`（纯测试基础设施修复）

## 2. 后端实现（backend/）

- [ ] **V6-a 查证**：在可复现条件下把 `pg_stat_activity` 的**实际行**打出来
      （至少 `pid` / `backend_type` / `usename` / `application_name` / `state` / `query`），
      指名"谁以 superuser 挂在那个库上"
- [ ] 记录复现条件（跑哪条命令、与哪个用例相邻、第几次出现），写进 integration-log
- [ ] **V6-b 修** `backend/tests/pg_scratch.py::drop_database()`（只改这一段，
      不许顺带重构同文件其它函数）
- [ ] 若为「跳过杀不掉的连接」方案：**必须同时**保留"删库失败要响"的明确报错路径

## 3. 测试

- [ ] 新增**反向守卫**：造一个"存在杀不掉的连接"的场景 ⇒ 断言**报错**（不是静默通过）
- [ ] 本机 `test_migration_seeds_preset_roles_and_is_replayable` **连跑 ≥ 5 次**全过
- [ ] 本机与迁移测试（`tests/test_migrations_baseline.py`）相邻跑，确认无顺序耦合回归

## 4. 验证

- [ ] `ruff check .` + `ruff format --check .`（**全量**，不是只跑改动文件）
- [ ] `pytest tests -q` 全量**不降**（1249 passed / 43 skipped）
- [ ] `check_seams.py` ⇒ OK 12 / ERROR 0 / WARN 0
- [ ] `check_startup_readiness.py --self-test` ⇒ 7 条全过
- [ ] CI 全量 run **四项 success**（远程验到，不是只看本地）

## 5. 收尾

- [ ] 回登 `changes/P6-V6/integration-log.md`（**实测证据**：`pg_stat_activity` 真实行、
      连跑次数、CI run id）
- [ ] 同步删掉 / 更正 P6-V4 提示词里那条「已知 flaky」（修掉之后它不再成立）
- [ ] 提交推送（**后端 / 架构师 / changes 分段**，跨侧不混提交）
